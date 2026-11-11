import ast
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_python_syntax():
    for p in (ROOT/'setup.py',ROOT/'gugzi_kiosk/controller.py', ROOT/'gugzi_kiosk/updater.py'):
        ast.parse(p.read_text())

def test_migration_identity_literals():
    script=(ROOT/'setup.py').read_text()
    assert 'gugzi_pi_hallway_screen' in script
    assert 'gugzi/pi_hallway_screen' in script

def test_brightness_discovery():
    script=(ROOT/'gugzi_kiosk/controller.py').read_text()
    assert "self.discovery('number','brightness'" in script
    assert 'getvcp' in script and 'setvcp' in script

def test_mqtt_update_entity_and_button():
    script=(ROOT/'gugzi_kiosk/controller.py').read_text()
    assert "self.discovery('update','controller_update'" in script
    assert "elif payload=='install_update'" in script
    assert "systemd-run" in script

def test_update_workflow_and_checksum():
    workflow=(ROOT/'.github/workflows/release.yml').read_text()
    updater=(ROOT/'gugzi_kiosk/updater.py').read_text()
    assert 'sha256sum' in workflow
    assert 'hashlib.sha256' in updater
    assert 'VERSION' in updater

def test_no_default_credentials():
    setup=(ROOT/'setup.py').read_text()
    assert "getpass.getpass('MQTT password:" in setup
    assert 'config.json' in (ROOT/'.gitignore').read_text()
