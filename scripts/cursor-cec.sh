#!/usr/bin/env bash
# Hide phantom Cage cursor from Raspberry Pi HDMI-CEC input devices ONLY.
# Real mice and touchscreens are not changed. Reversible.
set -Eeuo pipefail
RULE=/etc/udev/rules.d/90-gugzi-kiosk-cec-cursor.rules
case "${1:-status}" in
 status)
   echo 'Possible HDMI-CEC pseudo pointers:'
   grep -E 'Name|Handlers' /proc/bus/input/devices | grep -E 'vc4-hdmi|Handlers' || true
   [[ -f "$RULE" ]] && echo 'CEC pointer-ignore rule is installed' || echo 'CEC pointer-ignore rule is absent'
   echo 'Cage may still show a cursor if other physical pointer devices exist.'
   ;;
 enable)
   [[ $EUID -eq 0 ]] || { echo 'Use sudo gugzi-kiosk cursor enable'; exit 1; }
   install -d /etc/udev/rules.d
   cat > "$RULE" <<'EOF'
# Ignore *only* Raspberry Pi HDMI-CEC virtual mouse devices in libinput.
# Leave USB, touch and real input devices alone.
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="vc4-hdmi-0", ENV{LIBINPUT_IGNORE_DEVICE}="1"
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="vc4-hdmi-1", ENV{LIBINPUT_IGNORE_DEVICE}="1"
EOF
   chmod 644 "$RULE"
   udevadm control --reload-rules
   echo 'Installed CEC-only rule. Reboot Pi to apply; touch devices remain enabled.'
   ;;
 disable)
   [[ $EUID -eq 0 ]] || { echo 'Use sudo gugzi-kiosk cursor disable'; exit 1; }
   rm -f "$RULE"
   udevadm control --reload-rules
   echo 'Removed rule. Reboot Pi to restore HDMI-CEC pointer handling.'
   ;;
 *) echo 'Usage: sudo gugzi-kiosk cursor {status|enable|disable}'; exit 2 ;;
esac
