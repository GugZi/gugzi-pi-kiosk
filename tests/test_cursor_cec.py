"""CEC cursor fix must not disable the only keyboard/touch input device."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/cursor-cec.sh'


def test_script_syntax_and_status():
    subprocess.run(['bash', '-n', str(SCRIPT)], check=True)
    # Read-only diagnostic must be safe without privileged input access.
    subprocess.run(['bash', str(SCRIPT), 'status'], check=True, capture_output=True, text=True)


def test_pi3_exact_cec_name_is_included():
    code = SCRIPT.read_text()
    assert 'ATTRS{name}=="vc4-hdmi"' in code
    assert 'ATTRS{name}=="vc4-hdmi-0"' in code
    assert 'ATTRS{name}=="vc4-hdmi-1"' in code


def test_keyboard_and_touch_are_preserved():
    code = SCRIPT.read_text()
    # Do not ignore the entire CEC keyboard/pointer node, which may be the
    # only usable input device for Cage on a headless Raspberry Pi.
    assert 'ENV{LIBINPUT_IGNORE_DEVICE}="1"' not in code
    assert 'ENV{ID_INPUT_MOUSE}=""' in code
    assert 'ENV{ID_INPUT_POINTINGSTICK}=""' in code
    assert 'ENV{ID_INPUT_KEYBOARD}=""' not in code
    assert 'ENV{ID_INPUT_TOUCHSCREEN}=""' not in code


def test_existing_rule_is_replaceable_and_reversible():
    code = SCRIPT.read_text()
    assert 'cat > "$RULE"' in code
    assert 'rm -f "$RULE"' in code
    assert 'udevadm control --reload-rules' in code
    assert 'Reboot Pi' in code
