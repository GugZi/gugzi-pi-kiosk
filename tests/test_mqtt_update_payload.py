"""MQTT update payload schema regression test.

Home Assistant rejected the *entire* update status because it contained an
unsupported "error" key. The installed_version therefore appeared stuck.
This test executes the real controller's update-publish method without
requiring MQTT, Pi hardware or paho-mqtt.
"""
import ast
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_update_payload_is_valid_and_error_is_separate():
    script = (ROOT / "gugzi_kiosk/controller.py").read_text()
    parsed = ast.parse(script)
    controller = next(n for n in parsed.body if isinstance(n, ast.ClassDef) and n.name == "Controller")
    method = copy.deepcopy(next(n for n in controller.body if isinstance(n, ast.FunctionDef) and n.name == "publish_controller_update"))
    wrapper = ast.ClassDef(name="Isolated", bases=[], keywords=[], body=[method], decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))
    scope = {
        "Path": Path,
        "json": json,
        "VERSION": "1.9.0",
        "load_json": lambda path, default: {"in_progress": False, "error": "Prior updater error"},
    }
    exec(compile(module, "<isolated controller test>", "exec"), scope)
    instance = scope["Isolated"]()
    instance.latest_release = "1.9.0"
    instance.release_url = "https://github.com/GugZi/gugzi-pi-kiosk/releases/tag/v1.9.0"
    instance.release_summary = "Fixed: show correct installed version"
    messages = {}
    instance.publish = lambda topic, payload: messages.__setitem__(topic, payload)

    instance.publish_controller_update()

    assert messages["update_error"] == "Prior updater error"
    state = json.loads(messages["controller_update"])
    assert set(state) == {
        "installed_version", "latest_version", "title", "in_progress",
        "release_url", "release_summary",
    }
    assert state["installed_version"] == "1.9.0"
    assert state["latest_version"] == "1.9.0"
    assert state["in_progress"] is False
    assert len(state["release_summary"]) <= 255


def test_no_previous_error_gives_human_readable_status():
    script = (ROOT / "gugzi_kiosk/controller.py").read_text()
    assert "self.publish('update_error',str(update.get('error',''))[:220] or 'Ingen')" in script
