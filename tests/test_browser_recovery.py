"""Tests for Raspberry Pi Chromium renderer crash recovery."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace

from gugzi_kiosk.browser_health import browser_renderer_state

ROOT = Path(__file__).resolve().parents[1]


def make_process(proc_root, pid, *args):
    proc = proc_root / str(pid)
    proc.mkdir()
    (proc / 'cmdline').write_bytes(b'\0'.join(a.encode() for a in args) + b'\0')


def test_crashed_tab_only_internal_chromium_renderer(tmp_path):
    make_process(tmp_path, 110, '/usr/lib/chromium/chromium',
                 '--type=renderer', '--top-chrome-webui')
    assert browser_renderer_state(os.getuid(), tmp_path) == 'missing'


def test_healthy_home_assistant_renderer(tmp_path):
    make_process(tmp_path, 111, '/usr/lib/chromium/chromium',
                 '--type=renderer', '--top-chrome-webui')
    make_process(tmp_path, 112, '/usr/lib/chromium/chromium',
                 '--type=renderer', '--renderer-client-id=7')
    assert browser_renderer_state(os.getuid(), tmp_path) == 'running'


def test_no_chromium_renderer_is_unknown_not_crashed(tmp_path):
    make_process(tmp_path, 113, '/usr/lib/chromium/chromium', '--kiosk')
    assert browser_renderer_state(os.getuid(), tmp_path) == 'unknown'
    assert browser_renderer_state(os.getuid()+1, tmp_path) == 'unknown'


def test_non_chromium_process_ignored(tmp_path):
    make_process(tmp_path, 114, 'another-program', '--type=renderer')
    assert browser_renderer_state(os.getuid(), tmp_path) == 'unknown'


def isolated_recover(monkeypatch, browser_status, now=1000):
    """Compile the real recovery method without MQTT or Pi runtime imports."""
    source = (ROOT / 'gugzi_kiosk/controller.py').read_text()
    program = ast.parse(source)
    controller = next(n for n in program.body
                      if isinstance(n, ast.ClassDef) and n.name == 'Controller')
    recover = next(n for n in controller.body
                   if isinstance(n, ast.FunctionDef) and n.name == 'recover')
    snippet = ast.fix_missing_locations(ast.Module(
        body=[ast.ClassDef(name='Dummy', bases=[], keywords=[],
                           body=[recover], decorator_list=[])],
        type_ignores=[]))
    clock = SimpleNamespace(value=now)
    namespace = {
        'time': SimpleNamespace(monotonic=lambda: clock.value),
        'browser_renderer_state': lambda uid: browser_status.value,
    }
    exec(compile(snippet, '<isolated recovery>', 'exec'), namespace)
    target = namespace['Dummy']()
    target.cfg = {'recovery': {'enabled': True}, 'kiosk': {'uid': 1001}}
    target.smart = SimpleNamespace(prefs={'recovery_enabled': True},
                                  ha_connected=True, recoveries=0,
                                  note_recovery=lambda reason: events.append(reason))
    target.state = {'screen_requested': 'ON'}
    target.failures = 0
    target.renderer_missing_checks = 0
    target.browser_renderer_status = 'unknown'
    target.last_refresh = 800
    target.last_kiosk_recovery = 0
    target.last_result = ''
    target.kiosk_running = lambda: True
    events = []
    reloads = []
    target.pikiosk_reload = lambda: reloads.append(clock.value)
    return target, clock, browser_status, reloads, events


def test_renderer_missing_reloads_only_after_repeated_checks(monkeypatch):
    target, clock, _, reloads, events = isolated_recover(
        monkeypatch, SimpleNamespace(value='missing'))
    target.recover()
    assert reloads == []
    clock.value += 30
    target.recover()
    assert reloads == []
    clock.value += 30
    target.recover()
    assert len(reloads) == 1
    assert events == ['Chromium page renderer crash']
    for _ in range(4):
        clock.value += 30
        target.recover()
    assert len(reloads) == 1  # 10-minute recovery cooldown


def test_renderer_recovers_before_threshold_no_reload(monkeypatch):
    state = SimpleNamespace(value='missing')
    target, clock, _, reloads, events = isolated_recover(monkeypatch, state)
    target.recover()
    state.value = 'running'
    clock.value += 30
    target.recover()
    assert target.renderer_missing_checks == 0
    assert target.browser_renderer_status == 'running'
    assert reloads == []


def test_unknown_renderer_or_inactive_screen_never_reloads(monkeypatch):
    state = SimpleNamespace(value='unknown')
    target, clock, _, reloads, events = isolated_recover(monkeypatch, state)
    for _ in range(5):
        target.recover()
        clock.value += 30
    assert reloads == []
    state.value = 'missing'
    target.state['screen_requested'] = 'OFF'
    for _ in range(5):
        target.recover()
        clock.value += 30
    assert reloads == []
    assert target.browser_renderer_status == 'inactive'


def test_recovery_does_not_rely_on_schedule_success():
    src = (ROOT / 'gugzi_kiosk/controller.py').read_text()
    assert "print('Schedule error:',exc,flush=True)" in src
    assert "self.recover()" in src
    assert "'browser_renderer':self.browser_renderer_status" in src
