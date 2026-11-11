# GugZi Pi Kiosk Controller

A lightweight Home Assistant MQTT controller for Raspberry Pi OS Lite and [PiKiosk](https://github.com/SailingGreg/pikiosk).

## Features

- Home Assistant MQTT Discovery (CPU, RAM, temperature, disk, throttling, kiosk health)
- HDMI on/off using Wayland `wlr-randr`, with dashboard refresh on wake
- DDC/CI physical monitor brightness via `ddcutil`
- Dashboard selector and screen modes
- Per-Pi MQTT IDs, with migration option for existing `pi-hallway-screen`
- GitHub Actions release builds and an MQTT Update entity for approved upgrades

**Work in progress:** test installation and updates on one Pi before enabling them on additional units. PiKiosk and MQTT must already be configured.

## Security

Do not commit `/etc/gugzi-kiosk/config.json`, MQTT passwords, tokens, or Pi-specific secrets. Device configuration stays on the Pi; the GitHub repository holds code only.

## Installation

```bash
git clone https://github.com/GugZi/gugzi-pi-kiosk.git
cd gugzi-pi-kiosk
sudo bash install.sh
```

The installer asks for your MQTT broker settings, Wayland HDMI output and optional DDC bus. For the *existing Hallway Pi only*, choose the migration option to retain its Home Assistant unique IDs.

Useful commands after installation:

```bash
sudo gugzi-kiosk status
sudo gugzi-kiosk logs
sudo gugzi-kiosk diagnose
sudo gugzi-kiosk configure
sudo gugzi-kiosk update
```

## Updates

Push to `main` → GitHub Actions validates and publishes a numbered GitHub Release → each Pi checks the latest release → Home Assistant's **Controller-opdatering** entity offers **Install**. Updates are **not installed automatically**. Test Hallway first.

The updater stages verified release files, changes the application symlink and checks the controller service before finalizing; Pi-specific configuration remains separate. A checksum guards against accidental corruption, but is **not a substitute for a signed release or protected GitHub credentials**.

## Limitations

- CEC is not required; HDMI output can be deactivated, but Cage may exit when it is the only output.
- DDC brightness requires a compatible display; on the Eletra Nano X it was confirmed on `/dev/i2c-2`.
- Mouse cursor hiding is not yet automatic.
- PiKiosk installation is not included yet.
- GitHub Actions and release installation should be verified before relying on them in production.
