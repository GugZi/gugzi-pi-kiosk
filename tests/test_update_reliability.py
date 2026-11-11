"""Regression checks for Home Assistant update button and MQTT command queue."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (ROOT / "gugzi_kiosk/controller.py").read_text()
UPDATER = (ROOT / "gugzi_kiosk/updater.py").read_text()
INSTALLER = (ROOT / "install.sh").read_text()


def test_modified_sources_parse():
    ast.parse(CONTROLLER)
    ast.parse(UPDATER)


def test_updater_does_not_exec_cli_from_zip():
    # Execute the trusted updater via the Python binary so missing ZIP +x
    # cannot produce systemd status 203/EXEC.
    assert "'/opt/gugzi-kiosk/venv/bin/python'" in CONTROLLER
    assert "'/opt/gugzi-kiosk/current/gugzi_kiosk/updater.py'" in CONTROLLER
    assert "systemd-run" in CONTROLLER
    assert "'/usr/local/bin/gugzi-kiosk','update'" not in CONTROLLER


def test_new_release_restores_cli_and_cursor_permissions():
    assert "os.chmod(destination / 'gugzi-kiosk', 0o755)" in UPDATER
    assert "os.chmod(cursor_helper, 0o755)" in UPDATER
    assert 'chmod 755 "$DEST/gugzi-kiosk"' in INSTALLER
    assert 'chmod 755 "$DEST/scripts/cursor-cec.sh"' in INSTALLER


def test_mqtt_actions_are_queued_instead_of_discarded_when_busy():
    assert "queue.Queue(maxsize=64)" in CONTROLLER
    assert "self.command_queue.put_nowait(payload)" in CONTROLLER
    assert "def command_worker(self):" in CONTROLLER
    assert "Busy; command skipped" not in CONTROLLER
    assert "self.lock.acquire()" in CONTROLLER


def test_update_error_is_exposed_to_home_assistant():
    assert "'update_error'" in CONTROLLER
    assert "'error':str(update.get('error',''))[:220]" in CONTROLLER
    assert "last_update_start" in CONTROLLER
