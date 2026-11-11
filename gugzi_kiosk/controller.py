#!/usr/bin/env python3
"""GugZi Pi Kiosk Controller - MQTT remote monitoring for PiKiosk."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import paho.mqtt.client as mqtt

VERSION = (Path(__file__).resolve().parent.parent / 'VERSION').read_text().strip()
CONFIG = Path('/etc/gugzi-kiosk/config.json')
STATE_DIR = Path('/var/lib/gugzi-kiosk')
STATE_PATH = STATE_DIR / 'state.json'


def call(args, timeout=15):
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=True)


def ddc_call(args, timeout=18):
    """Run ddcutil with a writable, private cache outside protected /root.

    The kiosk service uses ProtectHome=true, so ddcutil's default
    /root/.cache/ddcutil/dsa location is unavailable.
    """
    cache_dir = STATE_DIR / '.cache'
    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = os.environ.copy()
    env['HOME'] = str(STATE_DIR)
    env['XDG_CACHE_HOME'] = str(cache_dir)
    return subprocess.run(
        ['ddcutil', *args],
        text=True, capture_output=True, timeout=timeout, check=True, env=env
    )


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return default


class Controller:
    def __init__(self, cfg):
        self.cfg = cfg
        self.identity = cfg['identity']
        self.base = cfg['mqtt']['base']
        self.unique = cfg['mqtt']['unique_id']
        self.state = load_json(STATE_PATH, {'mode':'Manual', 'dashboard':cfg['dashboards']['default'], 'screen_requested':'ON'})
        if self.state.get('mode') not in ('Manual','Automatic','Always on','Always off'):
            self.state['mode'] = 'Manual'
        self.state.setdefault('dashboard', cfg['dashboards']['default'])
        self.state.setdefault('screen_requested','ON')
        self.lock = threading.Lock()
        self.mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.unique)
        m = cfg['mqtt']
        if m.get('username'):
            self.mqtt.username_pw_set(m['username'],m.get('password',''))
        self.mqtt.will_set(self.base+'/availability','offline',qos=1,retain=True)
        self.mqtt.on_connect = self.on_connect
        self.mqtt.on_message = self.on_message
        self.mqtt.reconnect_delay_set(2,60)
        self.last_result='Started'
        self.old_cpu=None
        self.last_brightness=None
        self.last_brightness_read=0
        self.last_kiosk_recovery=0
        self.failures=0
        self.last_refresh=0
        self.ha_online=None
        self.last_hdmi='unknown'
        self.update_available='unknown'
        self.last_update_check=0
        self.motion_last=time.monotonic()
        self.pending_brightness=None
        self.brightness_received=0
        self.last_brightness_write=0
        self.last_poll=0
        self.latest_release=VERSION
        self.release_url=''
        self.last_gh_check=0

    def publish(self, suffix, val, retain=True):
        self.mqtt.publish(self.base+'/'+suffix, val, qos=1, retain=retain)

    def persist(self):
        STATE_DIR.mkdir(parents=True,exist_ok=True)
        temp=STATE_PATH.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state,indent=2))
        os.chmod(temp,0o600)
        temp.replace(STATE_PATH)

    def wayland(self,*args):
        k=self.cfg['kiosk']
        return call(['runuser','-u',k['user'],'--','env',
                     f"XDG_RUNTIME_DIR=/run/user/{k['uid']}",
                     f"WAYLAND_DISPLAY={k['wayland']}",'wlr-randr',*args],12)

    def hdmi(self):
        output=self.cfg['kiosk']['output']
        try:
            inside=False
            for line in self.wayland().stdout.splitlines():
                if line.startswith(output+' '):
                    inside=True
                elif inside:
                    if line and not line[0].isspace():
                        break
                    if line.strip() == 'Enabled: yes': return 'ON'
                    if line.strip() == 'Enabled: no': return 'OFF'
        except Exception:
            pass
        return 'unknown'

    def hdmi_publish(self):
        real=self.hdmi()
        # Wayland disappears when Cage exits; report uncertainty, not fabricated OFF.
        self.last_hdmi=real
        self.publish('hdmi',real)

    def kiosk_running(self):
        user=self.cfg['kiosk']['user']
        def found(s):
            return subprocess.run(['pgrep','-u',user,'-f',s],capture_output=True).returncode==0
        return found('cage') and found('chromium')

    def pikiosk_reload(self):
        executable=shutil.which('pikiosk') or '/usr/local/bin/pikiosk'
        call([executable,'reload'],45)
        self.last_refresh=time.monotonic()

    def screen(self,turn_on):
        current=self.hdmi()
        if turn_on:
            if current != 'ON':
                try:
                    self.wayland('--output',self.cfg['kiosk']['output'],'--on')
                except Exception:
                    self.pikiosk_reload()
                time.sleep(2)
            if self.hdmi() != 'ON':
                raise RuntimeError('HDMI did not become active')
            waking=self.state.get('screen_requested')=='OFF'
            self.state['screen_requested']='ON'
            self.persist()
            if waking and self.cfg['screen'].get('refresh_after_wake',True):
                time.sleep(self.cfg['screen'].get('refresh_delay',3))
                self.pikiosk_reload()
        else:
            if current == 'ON':
                self.wayland('--output',self.cfg['kiosk']['output'],'--off')
            elif current == 'unknown':
                raise RuntimeError('Wayland unavailable; HDMI state unknown')
            self.state['screen_requested']='OFF'
            self.persist()
        self.hdmi_publish()

    def brightness_get(self):
        bus=self.cfg['brightness']['bus']
        raw=ddc_call(['--bus',str(bus),'getvcp','10'],16).stdout
        match=re.search(r'current value\s*=\s*(\d+).*?max value\s*=\s*(\d+)',raw,re.I|re.S)
        if not match or int(match.group(2))<=0:
            raise RuntimeError('Could not read DDC brightness')
        return round(int(match.group(1))*100/int(match.group(2)))

    def brightness_set(self,val):
        if not self.cfg['brightness']['enabled']:
            raise RuntimeError('Brightness unsupported')
        if self.state['screen_requested']=='OFF':
            raise RuntimeError('Screen requested off')
        value=max(5,min(100,int(val)))
        ddc_call(['--bus',str(self.cfg['brightness']['bus']),'setvcp','10',str(value)],18)
        actual=self.brightness_get()
        self.last_brightness=actual
        self.last_brightness_read=time.monotonic()
        self.publish('brightness',str(actual))

    def get_url(self):
        # Read the one PiKiosk URL without changing unknown configuration sections.
        import yaml
        return (yaml.safe_load(Path('/etc/pikiosk/config.yaml').read_text()) or {}).get('url','')

    def switch_dashboard(self,name):
        import yaml
        urls=self.cfg['dashboards']['urls']
        if name not in urls or not urls[name]: raise ValueError('Dashboard not configured')
        url=urls[name]
        current=urlsplit(self.get_url())
        requested=urlsplit(url)
        if (current.scheme,current.netloc)!=(requested.scheme,requested.netloc):
            raise ValueError('Dashboard must use same HA origin')
        path=Path('/etc/pikiosk/config.yaml')
        settings=yaml.safe_load(path.read_text()) or {}
        old=settings.get('url','')
        if old!=url:
            settings['url']=url
            tmp=path.with_suffix('.tmp')
            tmp.write_text(yaml.safe_dump(settings,sort_keys=False,allow_unicode=True))
            os.chmod(tmp,0o644)
            tmp.replace(path)
            try:
                self.pikiosk_reload()
            except Exception:
                settings['url']=old
                path.write_text(yaml.safe_dump(settings,sort_keys=False,allow_unicode=True))
                raise
        self.state['dashboard']=name
        self.persist()
        self.publish('dashboard',name)

    def cpu(self):
        vals=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
        current=(vals[3]+vals[4],sum(vals))
        old=self.old_cpu
        self.old_cpu=current
        if old is None or current[1]==old[1]: return 0.0
        return round(100*(1-(current[0]-old[0])/(current[1]-old[1])),1)

    def monitor(self):
        info={}
        for line in Path('/proc/meminfo').read_text().splitlines():
            k,v=line.split(':',1)
            info[k]=int(v.strip().split()[0])
        disk=shutil.disk_usage('/')
        temp=round(int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000,1)
        throttle=None
        try:
            throttle=int(call(['vcgencmd','get_throttled'],5).stdout.split('=')[1].strip(),16)
        except Exception: pass
        wifi=None
        try:
            lines=Path('/proc/net/wireless').read_text().splitlines()[2:]
            if lines: wifi=round(float(lines[0].split()[3].rstrip('.')))
        except Exception: pass
        seconds=int(float(Path('/proc/uptime').read_text().split()[0]))
        warn=temp>=self.cfg['alerts']['temperature'] or (disk.used/disk.total*100)>=self.cfg['alerts']['disk'] or (throttle is not None and bool(throttle & 0x50005))
        return {
            'cpu':self.cpu(), 'ram':round(100*(1-info['MemAvailable']/info['MemTotal']),1),
            'temperature':temp, 'disk':round(disk.used/disk.total*100,1),
            'uptime':f'{seconds//86400}d {(seconds%86400)//3600}t',
            'wifi':wifi, 'throttled':'ON' if throttle else 'OFF' if throttle is not None else 'unknown',
            'throttle_hex':hex(throttle) if throttle is not None else 'unknown',
            'kiosk':'ON' if self.kiosk_running() else 'OFF',
            'warning':'ON' if warn else 'OFF',
            'updates':self.update_available, 'result':self.last_result, 'version':VERSION
        }

    def discovery(self,kind,key,body):
        body.update({'name':body.get('name',key),'unique_id':self.unique+'_'+key,
                     'device':{'identifiers':[self.unique], 'name':self.identity['name'],
                               'manufacturer':'Raspberry Pi','model':self.identity.get('model','Raspberry Pi'),
                               'sw_version':VERSION},
                     'availability_topic':self.base+'/availability'})
        self.mqtt.publish(f'homeassistant/{kind}/{self.unique}_{key}/config',json.dumps(body),qos=1,retain=True)

    def discover(self):
        def sensor(key,label,unit=None,icon=None,state_class=False):
            d={'name':label,'state_topic':self.base+'/state',
               'value_template':'{{ value_json.'+key+' }}'}
            if unit:d['unit_of_measurement']=unit
            if icon:d['icon']=icon
            if state_class:d['state_class']='measurement'
            if key=='temperature':d['device_class']='temperature'
            self.discovery('sensor',key,d)
        for key,label,unit,icon,klass in [
            ('cpu','CPU-forbrug','%','mdi:cpu',True),('ram','RAM-forbrug','%','mdi:memory',True),
            ('temperature','CPU-temperatur','°C','mdi:thermometer',True),
            ('uptime','Oppetid',None,'mdi:clock-outline',False),
            ('result','Seneste kommando',None,'mdi:information-outline',False),
            ('disk','Diskforbrug','%','mdi:harddisk',True),
            ('wifi','Wi-Fi signal','dBm','mdi:wifi',False),
            ('throttled','Throttling',None,'mdi:speedometer',False),
            ('throttle_hex','Throttling kode',None,'mdi:chip',False),
            ('updates','Tilgængelige opdateringer',None,'mdi:package-up',False),
            ('version','Controller-version',None,'mdi:source-branch',False)]: sensor(key,label,unit,icon,klass)
        self.discovery('binary_sensor','online',{'name':'Forbindelse', 'state_topic':self.base+'/availability','payload_on':'online','payload_off':'offline','device_class':'connectivity'})
        for key,label,icon in [('kiosk','PiKiosk kører','mdi:monitor-dashboard'),('warning','Systemadvarsel','mdi:alert')]:
            self.discovery('binary_sensor',key,{'name':label,'state_topic':self.base+'/state','value_template':'{{ value_json.'+key+' }}','payload_on':'ON','payload_off':'OFF','icon':icon})
        self.discovery('switch','hdmi',{'name':'HDMI-skærm','command_topic':self.base+'/command','payload_on':'hdmi_on','payload_off':'hdmi_off','state_topic':self.base+'/hdmi','state_on':'ON','state_off':'OFF','icon':'mdi:monitor'})
        for key,name,icon in [('reload','Genindlæs dashboard','mdi:refresh'),('restart_kiosk','Genstart PiKiosk','mdi:restart'),('reboot','Genstart Raspberry Pi','mdi:restart'),('check_updates','Kontrollér opdateringer','mdi:update')]:
            self.discovery('button',key,{'name':name,'command_topic':self.base+'/command','payload_press':key,'icon':icon})
        self.discovery('select','screen_mode',{'name':'Skærmtilstand','command_topic':self.base+'/command','command_template':'mode:{{ value }}','state_topic':self.base+'/screen_mode','options':['Manual','Automatic','Always on','Always off']})
        names=list(self.cfg['dashboards']['urls'])
        self.discovery('select','dashboard',{'name':'Dashboard','command_topic':self.base+'/command','command_template':'dashboard:{{ value }}','state_topic':self.base+'/dashboard','options':names})
        if self.cfg['brightness']['enabled']:
            self.discovery('number','brightness',{'name':'Skærmens lysstyrke','state_topic':self.base+'/brightness','command_topic':self.base+'/command','command_template':'brightness:{{ value | int }}','min':5,'max':100,'step':5,'unit_of_measurement':'%','mode':'slider','icon':'mdi:brightness-6'})
        # Preserve v3.1 dashboard text entities during Hallway migration.
        if self.cfg.get('migration')=='hallway-v2':
            for name in ('Hallway','Geek Room','3D Printers','Ioniq 5'):
                key=name.lower().replace(' ','_')
                self.discovery('text','url_'+key,{
                    'name':name+' URL', 'state_topic':self.base+'/url_'+key,
                    'command_topic':self.base+'/command',
                    'command_template':'url:'+name+':{{ value }}',
                    'max':255,'mode':'text','icon':'mdi:link'
                })
        self.discovery('update','controller_update',{
            'name':'Controller-opdatering',
            'title':'GugZi Pi Kiosk Controller',
            'state_topic':self.base+'/controller_update',
            'command_topic':self.base+'/command',
            'payload_install':'install_update',
            'icon':'mdi:package-up',
            'entity_category':'config'
        })
        # Update invokes only the trusted, locally configured GitHub release updater.

    def on_connect(self,client,userdata,flags,reason_code,properties):
        if reason_code.is_failure:
            print('MQTT login failed',reason_code,flush=True)
            return
        client.subscribe(self.base+'/command',qos=1)
        client.subscribe('homeassistant/status')
        self.discover()
        self.publish('availability','online')
        self.publish('screen_mode',self.state['mode'])
        self.publish('dashboard',self.state['dashboard'])
        if self.cfg.get('migration')=='hallway-v2':
            for name in ('Hallway','Geek Room','3D Printers','Ioniq 5'):
                key=name.lower().replace(' ','_')
                self.publish('url_'+key,self.cfg['dashboards']['urls'].get(name,''))
        self.hdmi_publish()
        self.publish_state()
        self.publish_controller_update()
        print('MQTT connected',flush=True)

    def on_message(self,client,userdata,msg):
        if msg.topic=='homeassistant/status':
            if msg.payload==b'online': self.discover()
            return
        if msg.retain: return
        payload=msg.payload.decode('utf-8','replace').strip()
        if payload.startswith('brightness:'):
            try:
                value=int(float(payload.split(':',1)[1]))
                if not 5<=value<=100: return
                self.pending_brightness=value
                self.brightness_received=time.monotonic()
            except ValueError: return
            return
        if not self.lock.acquire(blocking=False):
            print('Busy; command skipped',flush=True)
            return
        threading.Thread(target=self.command_job,args=(payload,),daemon=True).start()

    def command_job(self,payload):
        try:
            if payload in ('hdmi_on','hdmi_off'):
                self.state['mode']='Manual'
                self.persist()
                self.publish('screen_mode','Manual')
                self.screen(payload=='hdmi_on')
            elif payload in ('reload','restart_kiosk'):
                self.pikiosk_reload()
            elif payload=='reboot':
                self.last_result='Reboot requested'
                self.publish_state()
                call(['systemctl','reboot'],10)
            elif payload=='check_updates':
                self.check_updates(force=True)
                self.check_controller_release(force=True)
                self.publish_controller_update()
            elif payload=='install_update':
                self.start_controller_update()
            elif payload.startswith('mode:'):
                mode=payload[5:]
                if mode not in ('Manual','Automatic','Always on','Always off'):raise ValueError('Invalid mode')
                self.state['mode']=mode
                self.persist()
                self.publish('screen_mode',mode)
                self.schedule()
            elif payload.startswith('dashboard:'):
                self.switch_dashboard(payload[10:])
            elif payload.startswith('url:') and self.cfg.get('migration')=='hallway-v2':
                _,name,url=payload.split(':',2)
                old=self.cfg['dashboards']['urls']
                if name not in ('Hallway','Geek Room','3D Printers','Ioniq 5'):
                    raise ValueError('Unknown dashboard name')
                current=urlsplit(self.get_url())
                target=urlsplit(url)
                if (target.scheme,target.netloc)!=(current.scheme,current.netloc):
                    raise ValueError('URL must use Home Assistant origin')
                old[name]=url
                config_tmp=CONFIG.with_suffix('.tmp')
                config_tmp.write_text(json.dumps(self.cfg,indent=2))
                os.chmod(config_tmp,0o600)
                config_tmp.replace(CONFIG)
                self.publish('url_'+name.lower().replace(' ','_'),url)
                self.discover()
            else: return
            self.last_result='OK: '+payload[:120]
        except Exception as exc:
            self.last_result=('ERROR: '+str(exc))[:220]
            print(self.last_result,flush=True)
        finally:
            self.hdmi_publish()
            self.publish_state()
            self.lock.release()

    def publish_state(self):
        self.publish('state',json.dumps(self.monitor()))

    def schedule(self):
        mode=self.state['mode']
        if mode=='Manual': return
        if mode=='Always on': target=True
        elif mode=='Always off': target=False
        else:
            now=datetime.now().strftime('%H:%M')
            start=self.cfg['screen']['schedule_on']
            end=self.cfg['screen']['schedule_off']
            target=True if start==end else (start<=now<end if start<end else (now>=start or now<end))
        requested=self.state['screen_requested']=='ON'
        if target!=requested:self.screen(target)

    def recover(self):
        if not self.cfg['recovery']['enabled'] or self.state['screen_requested']=='OFF':
            self.failures=0
            return
        self.failures=0 if self.kiosk_running() else self.failures+1
        now=time.monotonic()
        if self.failures>=3 and now-self.last_kiosk_recovery>600:
            self.last_kiosk_recovery=now
            self.failures=0
            self.pikiosk_reload()
            self.last_result='PiKiosk recovered'

    def check_updates(self,force=False):
        # Reports distribution package versions, not a remote arbitrary branch.
        if not force and time.monotonic()-self.last_update_check<21600:return
        self.last_update_check=time.monotonic()
        try:
            out=call(['apt','list','--upgradable'],30).stdout
            self.update_available=sum('[upgradable from:' in x for x in out.splitlines())
        except Exception:self.update_available=-1

    def check_controller_release(self, force=False):
        # Public GitHub release API. New code is never downloaded during checks.
        repo = self.cfg.get('update', {}).get('repository', '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
            self.latest_release = VERSION
            return
        now=time.monotonic()
        if not force and now-self.last_gh_check<900:
            return
        self.last_gh_check=now
        try:
            import urllib.request
            req=urllib.request.Request(
                'https://api.github.com/repos/'+repo+'/releases/latest',
                headers={'User-Agent':'GugZi-Pi-Kiosk','Accept':'application/vnd.github+json'})
            with urllib.request.urlopen(req,timeout=10) as response:
                data=json.load(response)
            tag=data.get('tag_name','')
            if re.fullmatch(r'v\d+\.\d+\.\d+',tag):
                self.latest_release=tag[1:]
                self.release_url=data.get('html_url','')
        except Exception as exc:
            print('GitHub update check:', exc, flush=True)

    def publish_controller_update(self):
        current=VERSION
        state_file=Path('/var/lib/gugzi-kiosk/update_status.json')
        update=load_json(state_file,{})
        latest=self.latest_release
        # Avoid downgrades or stale state after restarting from a new release.
        try:
            def semver(v): return tuple(map(int,v.split('.')))
            if semver(latest)<semver(current): latest=current
        except Exception:
            latest=current
        obj={'installed_version':current,'latest_version':latest,
             'title':'GugZi Pi Kiosk Controller',
             'in_progress':bool(update.get('in_progress',False))}
        if self.release_url:
            obj['release_url']=self.release_url
        self.publish('controller_update', json.dumps(obj))

    def start_controller_update(self):
        repo=self.cfg.get('update',{}).get('repository','')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):
            raise RuntimeError('GitHub repository is not configured')
        self.check_controller_release(force=True)
        if self.latest_release == VERSION:
            self.last_result='Already up to date'
            return
        # Launch in its own systemd transient unit. This survives restart
        # of the kiosk service being updated. Never accept a URL via MQTT.
        call(['systemd-run','--unit=gugzi-kiosk-updater','--collect',
              '/usr/local/bin/gugzi-kiosk','update'],timeout=12)
        self.last_result='GitHub update started'

    def run_forever(self):
        self.mqtt.connect(self.cfg['mqtt']['host'],int(self.cfg['mqtt'].get('port',1883)),60)
        self.mqtt.loop_start()
        try:
            while True:
                if time.monotonic()-self.last_poll>=30 and self.lock.acquire(blocking=False):
                    try:
                        self.schedule()
                        self.recover()
                        self.check_updates()
                        self.check_controller_release()
                        self.publish_controller_update()
                        self.hdmi_publish()
                        self.publish_state()
                        if self.cfg['brightness']['enabled'] and self.state['screen_requested']=='ON':
                            if time.monotonic()-self.last_brightness_read>120:
                                try:
                                    self.last_brightness=self.brightness_get()
                                    self.publish('brightness',str(self.last_brightness))
                                except Exception as exc:print('DDC read:',exc,flush=True)
                                self.last_brightness_read=time.monotonic()
                    except Exception as exc:print('Monitor error:',exc,flush=True)
                    finally:
                        self.last_poll=time.monotonic()
                        self.lock.release()
                if self.pending_brightness is not None and time.monotonic()-self.brightness_received>.35 and time.monotonic()-self.last_brightness_write>.8:
                    if self.lock.acquire(blocking=False):
                        try:
                            value=self.pending_brightness
                            self.pending_brightness=None
                            self.brightness_set(value)
                            self.last_brightness_write=time.monotonic()
                        except Exception as exc:print('DDC write:',exc,flush=True)
                        finally:self.lock.release()
                time.sleep(.5)
        finally:
            self.publish('availability','offline')
            self.mqtt.disconnect()
            self.mqtt.loop_stop()


def main():
    cfg=load_json(CONFIG,{})
    if not cfg:raise SystemExit('Missing /etc/gugzi-kiosk/config.json')
    Controller(cfg).run_forever()

if __name__=='__main__':main()
