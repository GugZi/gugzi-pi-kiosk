"""Optional smart kiosk policy and Home Assistant MQTT controls.

Safe defaults preserve all existing single-Pi behaviour.  No secrets or
identifiers are stored in the update-managed source directory.
"""
import json
import re
import time
from datetime import datetime
from urllib.parse import urlsplit


DEFAULTS = {
    'auto_brightness': False,
    'motion_enabled': False,
    'auto_dashboard': False,
    'recovery_enabled': True,
    'day_brightness': 80,
    'evening_brightness': 35,
    'night_brightness': 10,
    'goodnight_brightness': 5,
    'day_start': '07:00',
    'evening_start': '19:00',
    'motion_timeout': 300,
    'dashboard_day': '',
    'dashboard_evening': '',
    'dashboard_night': '',
    'dashboard_goodnight': '',
}
NUMBER_RANGES = {
    'day_brightness': (5, 100),
    'evening_brightness': (5, 100),
    'night_brightness': (5, 100),
    'goodnight_brightness': (5, 100),
    'motion_timeout': (30, 3600),
}
BOOL_KEYS = {'auto_brightness', 'motion_enabled', 'auto_dashboard', 'recovery_enabled'}
TIME_KEYS = {'day_start', 'evening_start'}
DASH_KEYS = {'dashboard_day', 'dashboard_evening', 'dashboard_night', 'dashboard_goodnight'}


def time_valid(value):
    return isinstance(value, str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value) is not None


def time_in_window(now, start, end):
    if start == end:
        return True
    return start <= now < end if start < end else now >= start or now < end


def time_period(now, day_start, evening_start):
    if time_in_window(now, day_start, evening_start) and day_start != evening_start:
        return 'day'
    if time_in_window(now, evening_start, '23:00') and evening_start != '23:00':
        return 'evening'
    return 'night'


def brightness_for(prefs, house_mode, now):
    if house_mode == 'Goodnight':
        return int(prefs['goodnight_brightness'])
    period = time_period(now, prefs['day_start'], prefs['evening_start'])
    return int(prefs[period + '_brightness'])


def validate_pref(key, value, dashboards):
    if key in BOOL_KEYS:
        if value not in ('ON', 'OFF'):
            raise ValueError('Boolean value must be ON/OFF')
        return value == 'ON'
    if key in NUMBER_RANGES:
        number = int(value)
        low, high = NUMBER_RANGES[key]
        if not low <= number <= high:
            raise ValueError('Number out of range')
        return number
    if key in TIME_KEYS:
        if not time_valid(value):
            raise ValueError('Expected HH:MM in 24-hour format')
        return value
    if key in DASH_KEYS:
        if value == 'Disabled':
            value = ''
        if value and value not in dashboards:
            raise ValueError('Unknown dashboard')
        return value
    raise ValueError('Unknown preference')


class SmartFeatures:
    def __init__(self, controller):
        self.c = controller
        self.prefs = controller.state.setdefault('smart', {})
        for key, default in DEFAULTS.items():
            if key not in self.prefs:
                self.prefs[key] = default
            try:
                validate_pref(key, 'ON' if self.prefs[key] is True else 'OFF' if self.prefs[key] is False else str(self.prefs[key]), controller.cfg['dashboards']['urls'])
            except (TypeError, ValueError):
                self.prefs[key] = default
        self.house_mode = ''
        self.motion_last = 0.0
        self.motion_online = False
        self.last_notification = ''
        self.notification_until = 0.0
        self.recoveries = 0
        self.last_recovery = ''
        self.last_ha_check = 0.0
        self.last_auto_attempt = 0.0
        self.ha_connected = None
        self.last_auto_brightness = None
        self.brightness_hold_until = 0.0
        self.last_auto_dashboard = ''
        self.queue = []
        self.c.persist()

    def discovery(self):
        c = self.c
        base = c.base
        for key, name in [('auto_brightness', 'Automatisk lysstyrke'),
                          ('motion_enabled', 'Bevægelsesstyring'),
                          ('auto_dashboard', 'Automatisk dashboard'),
                          ('recovery_enabled', 'Automatisk gendannelse')]:
            c.discovery('switch', 'smart_' + key, {
                'name': name, 'state_topic': base + '/smart/' + key,
                'command_topic': base + '/command',
                'payload_on': 'pref:' + key + ':ON',
                'payload_off': 'pref:' + key + ':OFF',
                'state_on': 'ON', 'state_off': 'OFF', 'entity_category': 'config'})
        for key, name in [('day_brightness', 'Lysstyrke dag'),
                          ('evening_brightness', 'Lysstyrke aften'),
                          ('night_brightness', 'Lysstyrke nat'),
                          ('goodnight_brightness', 'Lysstyrke Goodnight'),
                          ('motion_timeout', 'Bevægelse timeout')]:
            low, high = NUMBER_RANGES[key]
            c.discovery('number', 'smart_' + key, {
                'name': name, 'state_topic': base + '/smart/' + key,
                'command_topic': base + '/command',
                'command_template': 'pref:' + key + ':{{ value | int }}',
                'min': low, 'max': high, 'step': 5 if key != 'motion_timeout' else 30,
                'mode': 'box', 'unit_of_measurement': 's' if key == 'motion_timeout' else '%',
                'entity_category': 'config'})
        for key, name in [('day_start', 'Dag starter'), ('evening_start', 'Aften starter')]:
            c.discovery('text', 'smart_' + key, {
                'name': name, 'state_topic': base + '/smart/' + key,
                'command_topic': base + '/command',
                'command_template': 'pref:' + key + ':{{ value }}',
                'min': 5, 'max': 5, 'pattern': '[0-2][0-9]:[0-5][0-9]',
                'entity_category': 'config'})
        for key in DASH_KEYS:
            c.discovery('select', 'smart_' + key, {
                'name': key.replace('_', ' ').title(),
                'state_topic': base + '/smart/' + key,
                'command_topic': base + '/command',
                'command_template': 'pref:' + key + ':{{ value }}',
                'options': ['Disabled'] + list(c.cfg['dashboards']['urls']),
                'entity_category': 'config'})
        for key, name in [('house_mode', 'Husets tilstand'),
                          ('last_notification', 'Seneste skærmbesked'),
                          ('last_recovery', 'Seneste gendannelse'),
                          ('recovery_count', 'Gendannelser'),
                          ('cursor', 'Markørdiagnose'),
                          ('ha_reachable', 'Home Assistant forbindelse')]:
            c.discovery('sensor', 'smart_' + key, {
                'name': name, 'state_topic': base + '/smart_status',
                'value_template': '{{ value_json.' + key + ' }}',
                'entity_category': 'diagnostic'})
        c.discovery('button', 'smart_diagnose', {
            'name': 'Kør skærmdiagnose', 'command_topic': base + '/command',
            'payload_press': 'diagnose', 'entity_category': 'diagnostic'})
        c.discovery('text', 'smart_notification', {
            'name': 'Vis besked', 'command_topic': base + '/command',
            'command_template': 'notify:{{ value }}', 'max': 240,
            'mode': 'text', 'entity_category': 'config'})

    def on_connect(self):
        c = self.c
        c.mqtt.subscribe('gugzi/kiosk/house_mode', qos=1)
        c.mqtt.subscribe(c.base + '/ha/motion', qos=1)
        c.mqtt.subscribe(c.base + '/notify', qos=1)
        if c.cfg.get('fleet', {}).get('enabled', False):
            c.mqtt.subscribe('gugzi/kiosk/fleet/command', qos=1)
        self.publish_prefs()
        self.publish_status()

    def publish_prefs(self):
        for key, value in self.prefs.items():
            if key in DASH_KEYS and not value:
                rendered = 'Disabled'
            else:
                rendered = 'ON' if value is True else 'OFF' if value is False else str(value)
            self.c.publish('smart/' + key, rendered)

    def publish_status(self):
        self.c.publish('smart_status', json.dumps({
            'house_mode': self.house_mode or 'unknown',
            'last_notification': self.last_notification or 'none',
            'last_recovery': self.last_recovery or 'none',
            'recovery_count': self.recoveries,
            'cursor': 'Run: sudo gugzi-kiosk cursor status',
            'ha_reachable': 'unknown' if self.ha_connected is None else 'yes' if self.ha_connected else 'no',
        }))

    def on_message(self, msg):
        topic = msg.topic
        payload = msg.payload.decode('utf-8', 'replace').strip()
        if topic == 'gugzi/kiosk/house_mode':
            # Retained house mode is useful after a Pi restart.
            if payload in ('Morning', 'Bedtime', 'Goodnight'):
                self.house_mode = payload
            self.publish_status()
            return True
        if topic == self.c.base + '/ha/motion':
            # Only actual ON events wake the screen; never retain motion.
            self.motion_online = True
            if not msg.retain and payload.upper() == 'ON':
                self.motion_last = time.monotonic()
            return True
        if topic == self.c.base + '/notify':
            if not msg.retain:
                self.notification(payload)
            return True
        if topic == 'gugzi/kiosk/fleet/command':
            if msg.retain:
                return True
            permitted = {'check_updates': 'check_updates', 'reload': 'reload'}
            if self.c.cfg.get('fleet', {}).get('allow_install_all'):
                permitted['install_update'] = 'install_update'
            if payload in permitted:
                self.queue.append(permitted[payload])
            return True
        return False

    def on_command(self, payload):
        if payload.startswith('pref:'):
            _, key, value = payload.split(':', 2)
            self.prefs[key] = validate_pref(key, value, self.c.cfg['dashboards']['urls'])
            self.c.persist()
            self.publish_prefs()
            self.c.last_result = 'Setting changed: ' + key
            return True
        if payload.startswith('notify:'):
            self.notification(payload[7:])
            return True
        if payload == 'diagnose':
            self.c.last_result = 'Diagnostic: ' + ('PiKiosk running' if self.c.kiosk_running() else 'PiKiosk stopped')
            self.publish_status()
            return True
        return False

    def notification(self, message):
        message = message.strip()[:240]
        if not message:
            return
        self.last_notification = message
        self.notification_until = time.monotonic() + 15
        # Home Assistant automation / Browser Mod can render this event on-screen.
        # PiKiosk/Cage has no native overlay mechanism.
        self.c.publish('notification_event', json.dumps({'message': message, 'duration': 15}), retain=False)
        self.publish_status()

    def screen_tick(self):
        c = self.c
        if c.state['mode'] != 'Automatic':
            return False
        now = datetime.now().strftime('%H:%M')
        screen = c.cfg['screen']
        scheduled = time_in_window(now, screen['schedule_on'], screen['schedule_off'])
        if self.prefs['motion_enabled']:
            scheduled = scheduled and bool(self.motion_last) and (
                time.monotonic() - self.motion_last < self.prefs['motion_timeout'])
        wanted = 'ON' if scheduled else 'OFF'
        if wanted != c.state['screen_requested']:
            c.screen(wanted == 'ON')
        return True

    def tick(self):
        c = self.c
        now = datetime.now().strftime('%H:%M')
        if c.state['screen_requested'] == 'ON' and self.prefs['auto_brightness'] and c.cfg['brightness']['enabled']:
            if time.monotonic() >= self.brightness_hold_until:
                target = brightness_for(self.prefs, self.house_mode, now)
                if self.last_auto_brightness != target and time.monotonic() - self.last_auto_attempt >= 120:
                    self.last_auto_attempt = time.monotonic()
                    try:
                        c.brightness_set(target)
                        self.last_auto_brightness = target
                    except Exception as exc:
                        print('Auto brightness failed:', exc, flush=True)
        if self.prefs['auto_dashboard'] and c.state['screen_requested'] == 'ON':
            period = 'goodnight' if self.house_mode == 'Goodnight' else time_period(now, self.prefs['day_start'], self.prefs['evening_start'])
            dashboard = self.prefs.get('dashboard_' + period, '')
            if dashboard and dashboard != c.state['dashboard']:
                c.switch_dashboard(dashboard)
                self.last_auto_dashboard = dashboard
        self.check_ha_recovery()
        self.publish_status()

    def check_ha_recovery(self):
        now = time.monotonic()
        if now - self.last_ha_check < 90:
            return
        self.last_ha_check = now
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        try:
            url = self.c.get_url()
            request = Request(url, method='HEAD')
            try:
                with urlopen(request, timeout=4):
                    online = True
            except HTTPError as exc:
                online = exc.code < 500
        except Exception:
            online = False
        was_online = self.ha_connected
        self.ha_connected = online
        if (was_online is False and online and
                self.c.state['screen_requested'] == 'ON' and
                self.c.kiosk_running() and now - self.c.last_refresh > 120):
            try:
                self.c.pikiosk_reload()
                self.note_recovery('HA connection restored; kiosk refreshed')
            except Exception as exc:
                print('Reconnect recovery failed:', exc, flush=True)

    def user_brightness_changed(self):
        # Explicit user slider wins for 60 minutes, then automation resumes.
        self.brightness_hold_until = time.monotonic() + 3600
        self.last_auto_brightness = None

    def note_recovery(self, detail):
        self.recoveries += 1
        self.last_recovery = datetime.now().isoformat(timespec='seconds') + ': ' + detail
        self.publish_status()

    def take_queued(self):
        if self.queue:
            return self.queue.pop(0)
        return None
