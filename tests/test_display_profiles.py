"""Profile selection tests: one controller, separate kiosk identities."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gugzi_setup', ROOT / 'setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


@pytest.mark.parametrize(('responses', 'expected'), [
    ([''], 'standalone'),
    (['1'], 'standalone'),
    (['2'], 'touchscreen'),
    (['touch'], 'touchscreen'),
    (['x', '2'], 'touchscreen'),
])
def test_choose_screen_profile(monkeypatch, responses, expected):
    responses = iter(responses)
    monkeypatch.setattr('builtins.input', lambda prompt: next(responses))
    assert setup.choose_display_profile() == expected


def configure(monkeypatch, tmp_path, answers, hostname):
    path = tmp_path / 'config.json'
    monkeypatch.setattr(setup, 'CONFIG', path)
    monkeypatch.setattr(setup.socket, 'gethostname', lambda: hostname)
    monkeypatch.setattr('builtins.input', lambda prompt: next(answers))
    monkeypatch.setattr(setup.getpass, 'getpass', lambda prompt: 'password-not-in-git')
    import pwd
    monkeypatch.setattr(pwd, 'getpwnam', lambda user: SimpleNamespace(pw_uid=1001))
    setup.main()
    return json.loads(path.read_text()), path


def test_new_touchscreen_gets_own_identity_and_no_hallway_migration(monkeypatch, tmp_path):
    # A touchscreen never receives a prompt to adopt the existing Hallway IDs.
    answers = iter(['2', 'Kitchen Touch', '10.5.1.100', '', 'kiosk_mqtt',
                    '', '', '', ''])
    config, path = configure(monkeypatch, tmp_path, answers, 'pi-kitchen-touch')
    assert config['display_profile'] == 'touchscreen'
    assert config['migration'] is None
    assert config['mqtt']['unique_id'] == 'gugzi_pi_kitchen_touch'
    assert config['mqtt']['base'] == 'gugzi/pi_kitchen_touch'
    assert config['identity']['name'] == 'Kitchen Touch'
    assert config['brightness'] == {'enabled': False, 'bus': None}
    assert config['screen']['schedule_off'] == '23:00'
    assert path.stat().st_mode & 0o777 == 0o600


def test_standalone_hallway_migration_keeps_ids(monkeypatch, tmp_path):
    answers = iter(['1', 'My Hallway Display', 'yes', 'HALLWAY',
                    '10.5.1.100', '', 'kiosk_mqtt', '', '', '', ''])
    config, _ = configure(monkeypatch, tmp_path, answers, 'pi-hallway-screen')
    assert config['display_profile'] == 'standalone'
    assert config['migration'] == 'hallway-v2'
    assert config['mqtt']['unique_id'] == 'gugzi_pi_hallway_screen'
    assert config['mqtt']['base'] == 'gugzi/pi_hallway_screen'


def test_existing_local_configuration_is_never_overwritten(monkeypatch, tmp_path):
    path = tmp_path / 'config.json'
    old = {'mqtt': {'unique_id': 'gugzi_pi_hallway_screen'}, 'secret': 'unchanged'}
    path.write_text(json.dumps(old))
    monkeypatch.setattr(setup, 'CONFIG', path)
    monkeypatch.setattr('builtins.input',
                        lambda prompt: pytest.fail('No wizard for existing configuration'))
    setup.main()
    assert json.loads(path.read_text()) == old


def test_controller_profile_fallback_and_mqtt_diagnostic():
    code = (ROOT / 'gugzi_kiosk/controller.py').read_text()
    assert "cfg.get('display_profile', 'standalone')" in code
    assert "'display_profile':'Touchscreen' if self.display_profile=='touchscreen' else 'Standalone'" in code
    assert "'display_profile','Skærmtype'" in code
    assert "sensor(key,label,unit,icon,klass)" in code
