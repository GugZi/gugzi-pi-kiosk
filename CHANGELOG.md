# Changelog

## Next release – Standalone and touchscreen setup profiles

### Added
- One installer now offers **1) Standalone display** and **2) Touchscreen**, with standalone selected by default.
- Store per-Pi `display_profile` locally and publish **Skærmtype** in Home Assistant.
- New touchscreen installations always use unique MQTT IDs instead of reusing Hallway's MQTT identity.
- Automated tests for both profile choices, old Hallway migration, setup defaults and existing config preservation.

### Compatibility
- Existing Raspberry Pi installations without a display profile remain **Standalone** and keep their existing dashboards, Home Assistant entities, update process, credentials and IDs.
- Touch support uses the installed Raspberry Pi OS/Cage input stack; rotation, calibration, touch-to-wake and backlight control are **not** configured or promised until the physical touch panel has been tested.
- Installer does not overwrite local configuration during future updates.

## Next release – Chromium dashboard crash recovery

### Added
- New Home Assistant diagnostic sensor **Chromium webside** showing `running`, `missing`, `unknown`, `offline` or `inactive`.
- Detect Chromium's “Aw, Snap!” state when only the internal `--top-chrome-webui` renderer survives and the Home Assistant page renderer is missing.
- Automatic PiKiosk reload after three consecutive missing-renderer checks, with startup grace and a ten-minute recovery cooldown.
- Regression tests for renderer recognition, false positives, startup/cooldown behavior and a screen intentionally switched off.

### Fixed
- Existing watchdog did not recover a crashed Chromium tab while Cage and Chromium processes remained alive.
- A temporary Wayland/HDMI scheduling error no longer prevents the browser health checks and MQTT monitoring from running in the same cycle.

### Notes
- Recovery requires both existing **Automatisk gendannelse** and the local recovery setting enabled, with the screen requested on. It does not change motion, brightness, dashboard or MQTT identities.
- This is a process-based health heuristic, not a Chromium DevTools/tab-state API. It avoids reloading when the renderer state is uncertain.

## Next release – MQTT Update version synchronization

### Fixed
- Fixed stale installed-version in Home Assistant's **Controller-opdatering** entity: MQTT Update rejects the unsupported `error` JSON field and had retained an old version (for example 1.7.0 instead of installed 1.9.0).
- Publish the update error separately on `gugzi/<device>/update_error` while keeping the existing diagnostic entity and MQTT unique ID.
- Preserve release summaries, release links, update button and Pi-specific configuration.

### Tests
- Added a runtime regression test for the actual MQTT Update JSON payload and validated that unsupported keys cannot be reintroduced.

## Next release – Home Assistant changelog preview

### Added
- Show a concise, current-release changelog in Home Assistant's Controller-opdatering dialog using MQTT `release_summary` (maximum 255 characters).
- Keep the full GitHub release announcement accessible through the existing release link.

### Fixed
- Prevent older changelog sections from being used as the summary for a new update.
- Preserve the existing MQTT update entity ID, update command and local settings.

## Next release – updater and MQTT reliability

### Fixed
- Corrected Home Assistant update button failing with `systemd status=203/EXEC` because ZIP installation lost executable permissions on `gugzi-kiosk`.
- Start the updater directly with the installed Python interpreter to avoid requiring CLI executable permissions.
- Restore executable permissions for the kiosk CLI and cursor helper after installation and every GitHub update.
- Queue MQTT commands instead of silently dropping them during monitoring or a slow operation (`Busy; command skipped`).
- Ignore repeated update requests for 90 seconds while a prior attempt starts.

### Added
- A Home Assistant diagnostic sensor for the most recent controller update error.
- Regression tests for update launching, script permissions and MQTT command queue.

## Previous smart-kiosk feature update
- Added non-disruptive opt-in auto brightness, house-mode override, and temporary manual brightness hold.
- Added opt-in motion wake and auto-off using per-device HA MQTT events.
- Added opt-in automatic dashboard selection for day, evening, night and Goodnight.
- Added MQTT settings and diagnostic entities, HA health checks and reconnect recovery.
- Added notification event bridge for HA/Browser Mod (no native Cage overlay).
- Added opt-in fleet MQTT commands and documented multi-device HA update actions.
- Added reversible HDMI-CEC pseudo-pointer cursor suppression helper.
- Preserved existing MQTT entity IDs, local device config and GitHub update workflow.
