# GugZi Pi Kiosk Controller

Home Assistant MQTT-controller til Raspberry Pi OS Lite + [PiKiosk](https://github.com/SailingGreg/pikiosk). Én kodebase, individuelle indstillinger pr. Pi, opdateringer via GitHub Releases og Home Assistants **Controller-opdatering**-knap.

## Installation (ny Pi)

Installer PiKiosk først. Derefter:

```bash
git clone https://github.com/GugZi/gugzi-pi-kiosk.git
cd gugzi-pi-kiosk
sudo bash install.sh
```

Installationsguiden gemmer MQTT-login lokalt i `/etc/gugzi-kiosk/config.json` (rettigheder `0600`). **Kun på den eksisterende Hallway-Pi:** vælg Hallway-migration, så de gamle MQTT-ID'er bevares. Andre Pi'er skal have deres egne MQTT-ID'er. Brugeren og adgangskoder må ikke committes til GitHub.

```bash
sudo gugzi-kiosk status
sudo gugzi-kiosk logs
sudo gugzi-kiosk diagnose
sudo gugzi-kiosk configure
sudo gugzi-kiosk update
```

## Nye smart-funktioner

De nye funktioner er **slået fra som udgangspunkt**, så en opdatering ikke uventet slukker skærmen eller skifter dashboard. De kan aktiveres under MQTT-enheden i Home Assistant:

| Funktion | MQTT-indstilling | Funktion |
| --- | --- | --- |
| Automatisk DDC-lysstyrke | Automatisk lysstyrke | Dag/aften/nat + `Goodnight`-override. En manuel sliderændring gælder i 60 minutter. |
| Bevægelsesstyring | Bevægelsesstyring, Bevægelse timeout | Virker i skærmtilstand `Automatic` og inden for skærmens tidsplan. Motion `ON` tænder, timeout slukker. |
| Dashboard-automation | Automatisk dashboard, Dashboard Day/Evening/Night/Goodnight | Vælg mellem **allerede konfigurerede** dashboards. Ingen vilkårlige URL'er accepteres. |
| Selvreparation | Automatisk gendannelse | Process-watchdog og genindlæsning efter at Home Assistant bliver tilgængelig igen. |
| Skærmbeskeder | Vis besked | Udgiver en MQTT event til valgfri Home Assistant/Browser Mod-visning. Browser Mod er *ikke installeret automatisk*. |
| Diagnostik | Kør skærmdiagnose og status-sensorer | Registrerer kiosk, HA-forbindelse og antal gendannelser. |
| Fleet | Home Assistant update-entitet pr. Pi | Home Assistant kan installere opdateringer på flere Pi'er. MQTT-gruppekommandoer kan aktiveres særskilt. |

### Forbind til Home Assistant

Den enkelte Pi kan ikke automatisk vide, hvilke Home Assistant-entiteter der er `input_select.house_mode` eller en bevægelsessensor. Derfor skal Home Assistant udsende de relevante tilstande på MQTT. Se [eksemplerne](examples/home_assistant.yaml) og kopier automations efter behov.

- `gugzi/kiosk/house_mode` — behold seneste `Morning`, `Bedtime` eller `Goodnight` (retained).
- `gugzi/<pi-id>/ha/motion` — en **ikke-retained** `ON`-hændelse, eksempelvis `gugzi/pi_hallway_screen/ha/motion`.
- `gugzi/<pi-id>/notify` — tekstbesked, ikke-retained. Enheden publicerer `gugzi/<pi-id>/notification_event` med `{message,duration}`.

På Hallway-Pi er bevægelsessensoren `binary_sensor.hallway_motion_sensors`. Aktiver først Home Assistant-automation, der publicerer bevægelse; slå derefter **Bevægelsesstyring** til. Hvis der ikke kommer MQTT-bevægelseshændelser, vil skærmen forblive slukket i `Automatic`-tilstand.

### Fjerne musemarkøren fra Cage/Wayland

Cage har ikke en generel, pålidelig `hide_cursor`-indstilling. På nogle Raspberry Pi'er stammer markøren fra de virtuelle HDMI-CEC-pointere `vc4-hdmi-0/1` og ikke fra en rigtig mus. Projektet indeholder en **valgfri og reversibel** udev-regel, der kun ignorerer disse to pseudo-enheder for libinput:

```bash
sudo gugzi-kiosk cursor status
sudo gugzi-kiosk cursor enable
sudo reboot
# Gendan hvis nødvendigt:
sudo gugzi-kiosk cursor disable
sudo reboot
```

Touch og USB-input deaktiveres ikke af disse regler. Hvis cursoren kommer fra en anden pegeenhed, virker metoden ikke; diagnosticér input-enheden i stedet for at deaktivere input generelt.

### Flere Pi'er og central opdatering

Alle Pi'er kan installere den samme GitHub Release ved hjælp af deres egen MQTT Update-entity **Controller-opdatering**. Home Assistant kan kalde `update.install` med én eller flere update-entity IDs. Nye versioner bliver **ikke installeret automatisk**.

Valgfri fleet-MQTT-kommando til *alle* kan aktiveres på hver Pi i dens lokale konfiguration:

```json
"fleet": {"enabled": true, "allow_install_all": false}
```

Emnet `gugzi/kiosk/fleet/command` accepterer `check_updates` og `reload`, men **ikke `install_update`**, medmindre administratoren eksplicit sætter `allow_install_all` til `true`. Undlad at retain gruppekommandoer, og begræns MQTT write-rettigheder via Mosquitto ACL.

### Releases

Home Assistant viser en kort **release_summary** (op til 255 tegn) direkte under **Controller-opdatering**. Tryk på **Read release announcement** for den komplette changelog på GitHub. Controlleren henter resumeet fra den aktuelle GitHub Release og viser ikke tidligere versioners ændringer som nye.

Alle PR'er valideres i GitHub Actions. Et commit på `main` giver automatisk en ny nummereret GitHub Release med ZIP og SHA256. Opdateringsværktøjet installerer kun en release med det forventede navn og kontrolsum og genstarter tjenesten; ved registreret fejl genoprettes tidligere kodeversion. Det er ikke en kryptografisk signatur — beskyt GitHub-kontoen og `main`.

**Vigtigt:** Test på Hallway før opdatering af flere enheder. HDMI `--off` kan stoppe Cage, og skærme uden DDC/CI understøtter ikke fysisk lysstyrke. Koden kan kun levere on-screen notifikationer, hvis en frontend eller Browser Mod er sat op til at vise `notification_event`.
