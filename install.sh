#!/usr/bin/env bash
set -Eeuo pipefail
if [[ $EUID -ne 0 ]]; then echo 'Run: sudo bash install.sh'; exit 1; fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo 'GugZi Kiosk installer 1.0.0'
apt-get update
apt-get install -y python3 python3-venv python3-pip python3-yaml git wlr-randr ddcutil
if ! command -v pikiosk >/dev/null; then
  echo 'PiKiosk is not installed. Install and configure PiKiosk first: https://github.com/SailingGreg/pikiosk'
  exit 2
fi
if [[ ! -f /etc/pikiosk/config.yaml ]]; then echo 'Missing /etc/pikiosk/config.yaml'; exit 2; fi
install -d -m 700 /etc/gugzi-kiosk /var/lib/gugzi-kiosk
install -d -m 755 /opt/gugzi-kiosk/releases
if [[ ! -f /etc/gugzi-kiosk/config.json ]]; then
  GUGZI_SOURCE="$ROOT" python3 "$ROOT/setup.py"
fi
if [[ ! -f /opt/gugzi-kiosk/venv/bin/python ]]; then python3 -m venv /opt/gugzi-kiosk/venv; fi
/opt/gugzi-kiosk/venv/bin/pip install -r "$ROOT/requirements.txt"
VERSION="$(cat "$ROOT/VERSION")"
DEST="/opt/gugzi-kiosk/releases/${VERSION}"
mkdir -p "$DEST"
cp -a "$ROOT/gugzi_kiosk" "$ROOT/scripts" "$ROOT/systemd" "$ROOT/gugzi-kiosk" "$ROOT/install.sh" "$ROOT/requirements.txt" "$ROOT/README.md" "$ROOT/VERSION" "$DEST/"
ln -sfn "$DEST" /opt/gugzi-kiosk/current.new
mv -Tf /opt/gugzi-kiosk/current.new /opt/gugzi-kiosk/current
install -m 644 "$ROOT/systemd/gugzi-kiosk.service" /etc/systemd/system/gugzi-kiosk.service
ln -sfn /opt/gugzi-kiosk/current/gugzi-kiosk /usr/local/bin/gugzi-kiosk
chmod 755 "$DEST/gugzi-kiosk"
if [[ -f "$DEST/scripts/cursor-cec.sh" ]]; then
  chmod 755 "$DEST/scripts/cursor-cec.sh"
fi
# Only stop the old controller when explicitly migrating the Hallway device.
if python3 - <<'PY'
import json
c=json.load(open('/etc/gugzi-kiosk/config.json'))
raise SystemExit(0 if c.get('migration')=='hallway-v2' else 1)
PY
then
  systemctl disable --now pi-ha-controller.service 2>/dev/null || true
fi
systemctl daemon-reload
systemctl enable --now gugzi-kiosk.service
systemctl restart gugzi-kiosk.service
sleep 2
systemctl --no-pager --full status gugzi-kiosk.service || true
echo 'Done. Run: sudo gugzi-kiosk status'
