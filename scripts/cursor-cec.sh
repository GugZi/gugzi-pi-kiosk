#!/usr/bin/env bash
# Reclassify only Raspberry Pi's HDMI-CEC phantom pointer, without disabling
# its keyboard events. This is an opt-in, reversible workaround for Cage.
# It does not touch USB devices, genuine mice or touchscreens.
set -Eeuo pipefail
RULE=/etc/udev/rules.d/90-gugzi-kiosk-cec-cursor.rules

status() {
  echo 'HDMI-CEC input capabilities:'
  local path event name rel props
  for path in /sys/class/input/event*/device; do
    [[ -r "$path/name" ]] || continue
    name="$(cat "$path/name")"
    [[ "$name" == vc4-hdmi* ]] || continue
    event="$(basename "$(dirname "$path")")"
    rel="$(cat "$path/capabilities/rel" 2>/dev/null || echo unknown)"
    printf '  %s: %s (EV_REL=%s)\n' "$event" "$name" "$rel"
    props="$(udevadm info --query=property --name="/dev/input/$event" 2>/dev/null || true)"
    printf '%s\n' "$props" | grep -E '^ID_INPUT_(MOUSE|POINTINGSTICK|KEYBOARD|TOUCHSCREEN)=' || true
  done
  if [[ -f "$RULE" ]]; then
    echo 'CEC pointer classification rule is installed:'
    cat "$RULE"
  else
    echo 'CEC pointer classification rule is absent'
  fi
  echo 'Cage can still show a cursor if another device advertises pointer capability.'
}

require_root() {
  [[ $EUID -eq 0 ]] || { echo 'Run: sudo gugzi-kiosk cursor enable|disable'; exit 1; }
}

case "${1:-status}" in
  status)
    status
    ;;
  enable)
    require_root
    install -d /etc/udev/rules.d
    # On Pi 3B+ the CEC event device is named exactly "vc4-hdmi".
    # On newer models it can be "vc4-hdmi-0" or "vc4-hdmi-1".
    # Only remove pointer *classification*: do NOT ignore the entire device.
    # Ignoring the only HDMI-CEC keyboard/pointer device can crash Cage.
    cat > "$RULE" <<'EOF'
# Keep HDMI-CEC keyboard events, remove its phantom mouse classification.
# Deliberately do not use LIBINPUT_IGNORE_DEVICE or touch USB input devices.
SUBSYSTEM=="input", KERNEL=="event[0-9]*", ATTRS{name}=="vc4-hdmi", ENV{ID_INPUT_MOUSE}="", ENV{ID_INPUT_POINTINGSTICK}=""
SUBSYSTEM=="input", KERNEL=="event[0-9]*", ATTRS{name}=="vc4-hdmi-0", ENV{ID_INPUT_MOUSE}="", ENV{ID_INPUT_POINTINGSTICK}=""
SUBSYSTEM=="input", KERNEL=="event[0-9]*", ATTRS{name}=="vc4-hdmi-1", ENV{ID_INPUT_MOUSE}="", ENV{ID_INPUT_POINTINGSTICK}=""
EOF
    chmod 644 "$RULE"
    udevadm control --reload-rules
    echo 'Installed narrow CEC pointer-classification rule (does not disable keyboard or touch).'
    echo 'Reboot Pi to apply; then check the screen and run: sudo gugzi-kiosk cursor status'
    echo 'If the cursor remains, the compositor may still use EV_REL capabilities; do not disable all input.'
    ;;
  disable)
    require_root
    rm -f "$RULE"
    udevadm control --reload-rules
    echo 'Removed rule. Reboot Pi to restore HDMI-CEC input classification.'
    ;;
  *)
    echo 'Usage: sudo gugzi-kiosk cursor {status|enable|disable}'
    exit 2
    ;;
esac
