"""Conservative Chromium dashboard renderer health detection for PiKiosk.

An 'Aw, Snap!' Chromium tab may crash while Cage and Chromium stay alive.
Chromium's --top-chrome-webui renderer is not the Home Assistant page.
Only report 'missing' if at least one *internal* renderer exists and no
normal page renderer is seen. Other cases are uncertain ('unknown').
"""
from pathlib import Path


def browser_renderer_state(kiosk_uid, proc_root=Path('/proc')):
    """Return 'running', 'missing' or 'unknown' for kiosk user's Chromium.

    Reads /proc/<pid>/cmdline, not pgrep's abbreviated process name.
    Races or proc permissions cannot trigger a spurious restart.
    """
    web_renderers = 0
    internal_renderers = 0
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return 'unknown'

    for path in entries:
        if not path.name.isdigit():
            continue
        try:
            if path.stat().st_uid != int(kiosk_uid):
                continue
            args = (path / 'cmdline').read_bytes().split(b'\0')
        except (OSError, ValueError):
            continue
        if not args or b'chromium' not in args[0].lower():
            continue
        if b'--type=renderer' not in args:
            continue
        if b'--top-chrome-webui' in args:
            internal_renderers += 1
        else:
            web_renderers += 1

    if web_renderers:
        return 'running'
    if internal_renderers:
        return 'missing'
    return 'unknown'
