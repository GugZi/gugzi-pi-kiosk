"""Regression checks for opt-in invisible cursor on Cage/Wayland."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HELPER = (ROOT / "scripts/cursor-invisible.sh").read_text()
CLI = (ROOT / "gugzi-kiosk").read_text()
INSTALLER = (ROOT / "install.sh").read_text()
UPDATER = (ROOT / "gugzi_kiosk/updater.py").read_text()


def test_shell_scripts_parse():
    for path in ("gugzi-kiosk", "scripts/cursor-invisible.sh"):
        subprocess.run(["bash", "-n", str(ROOT / path)], check=True)


def test_invisible_theme_is_opt_in_and_local_to_kiosk():
    assert "XCURSOR_THEME" in HELPER
    assert "/etc/profile.d/gugzi-kiosk-invisible-cursor.sh" in HELPER
    assert 'user="$(kiosk_user)"' in HELPER
    assert 'if [ "\\$(id -un)" = "$user" ]' in HELPER
    assert 'export XCURSOR_THEME="$THEME"' in HELPER
    assert "LIBINPUT_IGNORE_DEVICE" not in HELPER
    assert "udevadm" not in HELPER
    assert "cursor-invisible.sh" in CLI


def test_theme_is_transparent_and_covers_default_and_browser_shapes():
    assert "PNG" in HELPER
    assert "b'\\x00'" in HELPER
    assert "xcursorgen" in HELPER
    assert "cursors/left_ptr" in HELPER
    assert "default arrow pointer hand1 hand2" in HELPER
    assert "xterm text vertical-text crosshair" in HELPER
    assert "e-resize w-resize n-resize s-resize" in HELPER


def test_theme_can_be_removed_without_affecting_udev():
    assert "show)" in HELPER
    assert 'rm -f "$PROFILE"' in HELPER
    assert 'rm -rf "$THEME_DIR"' in HELPER
    assert '".gugzi-managed"' in HELPER or '/.gugzi-managed' in HELPER
    assert "cursor-cec.sh" in CLI  # Existing CEC workaround still available.


def test_install_and_ota_mark_helper_executable():
    assert 'chmod 755 "$DEST/scripts/cursor-invisible.sh"' in INSTALLER
    assert "invisible_helper = destination / 'scripts/cursor-invisible.sh'" in UPDATER
    assert "os.chmod(invisible_helper, 0o755)" in UPDATER
