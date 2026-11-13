#!/usr/bin/env bash
# Optional, reversible invisible Xcursor theme for Cage kiosk sessions.
# Only changes the kiosk user's *visual cursor theme*; never disables input.
set -Eeuo pipefail

THEME=GugZi-Invisible
THEME_DIR="/usr/share/icons/${THEME}"
PROFILE="/etc/profile.d/gugzi-kiosk-invisible-cursor.sh"
CONFIG="/etc/gugzi-kiosk/config.json"

require_root() {
  if [[ ${EUID} -ne 0 ]]; then
    echo 'Run: sudo gugzi-kiosk cursor hide|show' >&2
    exit 1
  fi
}

kiosk_user() {
  python3 - "$CONFIG" <<'PY'
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
cfg = json.loads(path.read_text())
user = cfg['kiosk']['user']
# The name is interpolated into the sourced /etc/profile.d file.
if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', user):
    raise SystemExit('Invalid kiosk Linux username')
print(user)
PY
}

create_theme() {
  if ! command -v xcursorgen >/dev/null 2>&1; then
    echo 'Installing Debian xcursorgen (x11-apps) to build a transparent theme ...'
    apt-get install -y x11-apps
  fi

  local tmp
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  python3 - "$tmp/transparent.png" <<'PY'
"""Generate a valid, completely transparent 24x24 PNG with Python stdlib."""
import struct
import sys
import zlib
from pathlib import Path

def chunk(name, data):
    return (struct.pack('>I', len(data)) + name + data
            + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff))

width = height = 24
raw = (b'\x00' + b'\x00' * (width * 4)) * height
png = (b'\x89PNG\r\n\x1a\n'
       + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
       + chunk(b'IDAT', zlib.compress(raw, 9))
       + chunk(b'IEND', b''))
Path(sys.argv[1]).write_bytes(png)
PY

  printf '24 0 0 %s\n' "$tmp/transparent.png" > "$tmp/cursor.config"
  mkdir -p "$tmp/cursors"
  xcursorgen "$tmp/cursor.config" "$tmp/cursors/left_ptr"

  # Cage's default xcursor and common Chromium pointer shape names.
  # Alias every supported shape to the same fully transparent image.
  local name
  for name in \
    default arrow pointer hand1 hand2 pointing_hand \
    left_ptr_watch watch progress wait help question_arrow \
    xterm text vertical-text crosshair cross \
    fleur move all-scroll copy alias link \
    not-allowed no-drop forbidden circle \
    grab grabbing openhand closedhand \
    cell plus context-menu \
    e-resize w-resize n-resize s-resize \
    ne-resize nw-resize se-resize sw-resize \
    ew-resize ns-resize nesw-resize nwse-resize \
    col-resize row-resize sb_h_double_arrow sb_v_double_arrow \
    top_side bottom_side left_side right_side \
    top_left_corner top_right_corner bottom_left_corner bottom_right_corner \
    dnd-copy dnd-link dnd-move dnd-none; do
    ln -s left_ptr "$tmp/cursors/$name"
  done

  # Never replace an unowned theme directory.
  if [[ -e "$THEME_DIR" && ! -f "$THEME_DIR/.gugzi-managed" ]]; then
    echo "Refusing to replace unmanaged theme: $THEME_DIR" >&2
    exit 1
  fi
  mkdir -p "$THEME_DIR"
  rm -rf "$THEME_DIR/cursors"
  cp -a "$tmp/cursors" "$THEME_DIR/cursors"
  cat > "$THEME_DIR/index.theme" <<'EOF'
[Icon Theme]
Name=GugZi Invisible
Comment=Transparent Xcursor images for Raspberry Pi Cage kiosk
EOF
  printf 'Managed by GugZi Pi Kiosk\n' > "$THEME_DIR/.gugzi-managed"
  chmod -R a+rX "$THEME_DIR"
}

case "${1:-status}" in
  hide)
    require_root
    user="$(kiosk_user)"
    create_theme
    cat > "$PROFILE" <<EOF
# GugZi Pi Kiosk: transparent cursor theme for the named kiosk user ONLY.
# Read on login by /etc/profile; does not disable the mouse or touchscreen.
if [ "\$(id -un)" = "$user" ]; then
  export XCURSOR_THEME="$THEME"
fi
EOF
    chmod 644 "$PROFILE"
    echo "Installed transparent cursor theme for user: $user"
    echo 'No input devices were disabled.'
    echo 'Run: sudo pikiosk reload  (or sudo reboot) to apply to Cage.'
    ;;
  show)
    require_root
    rm -f "$PROFILE"
    if [[ -f "$THEME_DIR/.gugzi-managed" ]]; then
      rm -rf "$THEME_DIR"
    fi
    echo 'Removed transparent cursor theme from kiosk login session.'
    echo 'Run: sudo pikiosk reload  (or sudo reboot) to restore normal cursor.'
    ;;
  status)
    echo "Transparent Xcursor theme: $([[ -f "$THEME_DIR/.gugzi-managed" ]] && echo installed || echo absent)"
    echo "Kiosk login setting: $([[ -f "$PROFILE" ]] && echo enabled || echo absent)"
    if [[ -f "$CONFIG" ]]; then
      user="$(kiosk_user)"
      pid="$(pgrep -u "$user" -x cage | head -n 1 || true)"
      if [[ -n "$pid" && -r "/proc/$pid/environ" ]]; then
        active="$(tr '\0' '\n' < "/proc/$pid/environ" | sed -n 's/^XCURSOR_THEME=//p' | head -n 1)"
        echo "Running Cage XCURSOR_THEME: ${active:-not set}"
      else
        echo 'Running Cage XCURSOR_THEME: unavailable (check as root if needed)'
      fi
    fi
    ;;
  *)
    echo 'Usage: sudo gugzi-kiosk cursor {hide|show|status}' >&2
    exit 2
    ;;
esac
