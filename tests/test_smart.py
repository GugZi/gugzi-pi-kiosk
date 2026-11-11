"""Unit tests for policy and HA command validation (no physical Pi needed)."""
import time
from types import SimpleNamespace
from gugzi_kiosk.smart import (
    SmartFeatures, DEFAULTS, brightness_for, time_in_window, time_period,
    time_valid, validate_pref,
)


def test_night_schedule_over_midnight():
    assert time_in_window('23:30', '20:00', '07:00')
    assert time_in_window('05:30', '20:00', '07:00')
    assert not time_in_window('12:00', '20:00', '07:00')
    assert time_in_window('12:00', '08:00', '08:00')


def test_goodnight_override():
    assert brightness_for(DEFAULTS, 'Goodnight', '15:00') == 5
    assert brightness_for(DEFAULTS, 'Morning', '12:00') == 80
    assert brightness_for(DEFAULTS, '', '21:00') == 35
    assert brightness_for(DEFAULTS, '', '01:00') == 10


def test_validate_values_and_dashboards():
    assert time_valid('06:30')
    assert not time_valid('25:00')
    assert validate_pref('dashboard_night', 'Disabled', {'Hallway': 'http://ha/'}) == ''
    assert validate_pref('dashboard_night', 'Hallway', {'Hallway': 'http://ha/'}) == 'Hallway'
    try:
        validate_pref('dashboard_night', 'https://evil.test/', {'Hallway': 'http://ha/'})
        assert False, 'Should have rejected arbitrary URL'
    except ValueError:
        pass
    try:
        validate_pref('motion_timeout', '0', {})
        assert False, 'Should reject too-low timeout'
    except ValueError:
        pass


class FakeController:
    def __init__(self):
        self.state = {'mode': 'Manual', 'screen_requested': 'ON', 'dashboard': 'Hallway'}
        self.cfg = {
            'dashboards': {'urls': {'Hallway': 'http://ha/'}},
            'screen': {'schedule_on': '00:00', 'schedule_off': '00:00'},
            'brightness': {'enabled': True},
        }
        self.base = 'gugzi/pi_hallway_screen'
        self.messages = []
        self.screen_changes = []
        self.last_refresh = 0
        self.last_result = ''
    def persist(self):
        pass
    def publish(self, key, val, retain=True):
        self.messages.append((key, val))
    def discovery(self, *args):
        self.messages.append(('discovery', args))
    def screen(self, on):
        self.screen_changes.append(on)
        self.state['screen_requested'] = 'ON' if on else 'OFF'
    def kiosk_running(self):
        return True
    def get_url(self):
        return 'http://ha/'


def test_settings_preserved_and_motion_opt_in():
    c = FakeController()
    c.state['smart'] = {'day_brightness': 65}
    smart = SmartFeatures(c)
    assert smart.prefs['day_brightness'] == 65
    assert smart.prefs['motion_enabled'] is False
    assert smart.on_command('pref:motion_enabled:ON') is True
    assert smart.prefs['motion_enabled'] is True
    c.state['mode'] = 'Automatic'
    smart.screen_tick()
    assert c.screen_changes[-1] is False
    smart.motion_last = time.monotonic()
    smart.screen_tick()
    assert c.screen_changes[-1] is True


def test_nonretained_notification_event():
    c = FakeController()
    smart = SmartFeatures(c)
    retained = SimpleNamespace(topic=c.base + '/notify', payload=b'Test', retain=True)
    assert smart.on_message(retained)
    assert smart.last_notification == ''
    ordinary = SimpleNamespace(topic=c.base + '/notify', payload=b'Vask ferdig', retain=False)
    assert smart.on_message(ordinary)
    assert smart.last_notification == 'Vask ferdig'
    assert any(key == 'notification_event' for key, _ in c.messages)


def test_discovery_preserves_legacy_ids_and_adds_new():
    c = FakeController()
    smart = SmartFeatures(c)
    smart.discovery()
    assert any(key == 'discovery' and args[1] == 'smart_auto_brightness' for key, args in c.messages)
    assert any(key == 'discovery' and args[1] == 'smart_notification' for key, args in c.messages)
