#!/usr/bin/env python3
import json
import os
import re
import socket
import subprocess
import getpass
from pathlib import Path

CONFIG=Path('/etc/gugzi-kiosk/config.json')

def ask(label, default=''):
    text=input(f'{label} [{default}]: ').strip()
    return text or default

def main():
    if CONFIG.exists():
        print('Existing configuration preserved:',CONFIG)
        return
    hostname=socket.gethostname().lower()
    ident=re.sub('[^a-z0-9_]+','_',hostname.replace('-','_')).strip('_')
    print('Configuration is local to this Pi. Credentials never go into Git.')
    name=ask('Home Assistant device name', hostname.replace('-',' ').title())
    migration=ask('Preserve old Hallway MQTT identities? yes/no','no').lower()=='yes'
    if migration:
        confirm=ask('Type HALLWAY to confirm migration','')
        if confirm!='HALLWAY':raise SystemExit('Migration not confirmed')
        base='gugzi/pi_hallway_screen'
        unique='gugzi_pi_hallway_screen'
        name='Pi Hallway Screen'
    else:
        base='gugzi/'+ident
        unique='gugzi_'+ident
    host=ask('MQTT broker IP / hostname')
    if not host or '://' in host:raise SystemExit('MQTT host must be IP or hostname without port')
    port=int(ask('MQTT port','1883'))
    user=ask('MQTT username')
    password=getpass.getpass('MQTT password: ')
    kiosk_user=ask('PiKiosk Linux user','kiosk')
    import pwd
    uid=pwd.getpwnam(kiosk_user).pw_uid
    display=ask('Wayland display','wayland-0')
    output=ask('HDMI connector','HDMI-A-1')
    bus=ask('DDC brightness bus (empty if unsupported)','')
    enabled=bool(bus.strip())
    if enabled and not bus.isdigit():raise SystemExit('DDC bus must be numeric')
    try:
        import yaml
        initial=(yaml.safe_load(Path('/etc/pikiosk/config.yaml').read_text()) or {}).get('url','')
    except Exception:
        initial=''
    dashboards={'Hallway': initial} if migration else {'Main':initial}
    cfg={
        'migration':'hallway-v2' if migration else None,
        'identity':{'name':name,'model':'Raspberry Pi'},
        'mqtt':{'host':host,'port':port,'username':user,'password':password,'base':base,'unique_id':unique},
        'kiosk':{'user':kiosk_user,'uid':uid,'wayland':display,'output':output},
        'brightness':{'enabled':enabled,'bus':int(bus) if enabled else None},
        'screen':{'schedule_on':'08:00','schedule_off':'23:00','refresh_after_wake':True,'refresh_delay':3},
        'dashboards':{'default':next(iter(dashboards)),'urls':dashboards},
        'recovery':{'enabled':True},'alerts':{'temperature':75,'disk':85},
        'update':{'repository':'GugZi/gugzi-pi-kiosk','channel':'stable'}
    }
    CONFIG.parent.mkdir(parents=True,exist_ok=True)
    CONFIG.write_text(json.dumps(cfg,indent=2))
    os.chmod(CONFIG,0o600)
    print('Created',CONFIG)

if __name__=='__main__':main()
