# GugZi Pi Kiosk Controller

Home Assistant MQTT-controller til Raspberry Pi OS Lite + [PiKiosk](https://github.com/SailingGreg/pikiosk). Én kodebase, individuelle indstillinger pr. Pi, opdateringer via GitHub Releases og Home Assistants **Controller-opdatering**-knap.

## Installation (ny Pi)

Installer PiKiosk først. Derefter:

```bash
git clone https://github.com/GugZi/gugzi-pi-kiosk.git
cd gugzi-pi-kiosk
sudo bash install.sh
```

### Valg af skærmtype i samme installation

Første gang du kører `sudo bash install.sh`, vælger du profil:

```text
Choose display type / Vaelg skaermtype:
  1) Standalone display / Almindelig skaerm (no touch)
  2) Touchscreen / Touchskaerm
Display type (1/2) [1]:
```

- **1 – Almindelig skærm:** eksisterende PiKiosk-styring til en skærm uden touch. Brug denne til Hallway-Pi.
- **2 – Touchskærm:** samme PiKiosk/controller og GitHub-opdateringer, men en særskilt lokal `display_profile: touchscreen` og MQTT-identitet. Touch sker via Raspberry Pi OS/Cage/libinput, ikke via et separat program. Brug HDMI til billede og typisk USB til touch.
- Begge profiler vises i Home Assistant med diagnostiksensoren **Skærmtype** (`Standalone` eller `Touchscreen`). Eksisterende installationer uden `display_profile` fortsætter automatisk som **Standalone**.

Touchprofilen starter med den normale sikre **Manual**-skærmtilstand. Den giver **ikke** automatisk touch-to-wake, rotation, kalibrering eller fysisk lysstyrke: disse funktioner afhænger af den konkrete skærm og skal testes, før de aktiveres. Undgå HDMI auto-off, indtil touch fortsat er testet ved sluk/tænd. På Raspberry Pi 3 B+ er et let dashboard uden mange animerede grafer bedst.

Installationsguiden spørger kun om skærmprofil ved **ny** installation. Geninstallation og GitHub-opdateringer bevarer `/etc/gugzi-kiosk/config.json`, så ingen eksisterende Pi skifter profil eller MQTT-identitet. For manuelt profilswitch skal du redigere `display_profile` i den lokale konfiguration og genstarte controlleren; det ændrer ikke PiKiosks eller touch-driverens indstillinger.

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

### Automatisk recovery, når Chromium viser “Aw, Snap!”

Controlleren kontrollerer også, om Chromiums **webside-renderer** kører. Chromium kan godt være aktiv, mens en enkelt fane er crashet. Hvis kun den interne `--top-chrome-webui`-renderer findes, og ingen normal webside-renderer er aktiv ved tre målinger i træk, genstarter controlleren PiKiosk. Kontrollen starter først efter en opstartsperiode på mindst 2 minutter; der går mindst 10 minutter mellem forsøg.

Denne mekanisme bruger den eksisterende **Automatisk gendannelse**-switch. Den anvendes kun, hvis skærmen er sat til at være tændt. Ukendt processtatus udløser ingen genstart. Diagnostiksensoren **Chromium webside** viser `running`, `missing`, `unknown`, `offline` eller `inactive`. Funktionen er en konservativ procesbaseret kontrol, ikke en fuld garanti for at browserfanens indhold er korrekt.

### Skjul musemarkøren helt (valgfrit, kun lokalt)

På **standalone-skærme uden touch** kan du forsøge at skjule markøren helt ved at installere et 100 % gennemsigtigt Xcursor-tema. Dette er mere diskret end at flytte markøren til skærmkanten. Cage læser `XCURSOR_THEME` ved opstart, og PiKiosk starter Cage via kiosk-brugerens loginsession. Det kræver ingen ændring af HDMI-CEC input-enheder og påvirker derfor ikke tastatur eller touch-funktioner.

```bash
sudo gugzi-kiosk cursor hide
sudo pikiosk reload
sudo gugzi-kiosk cursor status
```

- `hide` installerer et særskilt gennemsigtigt tema under `/usr/share/icons/GugZi-Invisible`, og sætter kun `XCURSOR_THEME` for den lokalt konfigurerede kiosk-bruger via `/etc/profile.d/gugzi-kiosk-invisible-cursor.sh`. Første gang installeres Debian-pakken `x11-apps`, hvis `xcursorgen` mangler.
- `status` viser, om temaet er installeret, og om den kørende Cage-proces har modtaget `XCURSOR_THEME`.
- `show` fjerner den ekstra profil og vores eget tema, så normal markør vender tilbage efter `sudo pikiosk reload`.
- **Kun opt-in.** Opdatering og geninstallation ændrer aldrig denne lokale indstilling. Vælg det på den konkrete Pi, ikke automatisk på alle touchskærme.

**Begrænsning:** Et gennemsigtigt Xcursor-tema skjuler normalt kompositorens temabaserede markør, men Wayland-klienter kan også tegne egne cursor-surfaces, som muligvis stadig kan ses. På din Pi skal det derfor bekræftes visuelt efter en PiKiosk-reload. Vi lover ikke fuld markørfrihed på alle kombinationer af Cage/Chromium på forhånd.

### Fjerne musemarkøren fra Cage/Wayland

Cage har ikke en generel, pålidelig `hide_cursor`-indstilling. På nogle Raspberry Pi'er stammer markøren fra de virtuelle HDMI-CEC-inputs med pointerfunktioner. På Pi 3 B+ kan den hedde **`vc4-hdmi`** (EV_REL=3); på andre Pi'er hedder den `vc4-hdmi-0/1`. Projektet indeholder en **valgfri og reversibel** udev-regel, der forsøger at fjerne *museklassificeringen* af disse specifikke CEC-enheder — ikke at ignorere hele enheden, fordi CEC også kan være det eneste tastaturinput for Cage:

```bash
sudo gugzi-kiosk cursor status
sudo gugzi-kiosk cursor enable
sudo reboot
# Gendan hvis nødvendigt:
sudo gugzi-kiosk cursor disable
sudo reboot
```

Touch, USB-input og HDMI-CEC-tastaturfunktioner deaktiveres ikke bevidst af denne regel. `sudo gugzi-kiosk cursor status` viser den faktiske enheds navn, `EV_REL` og relevante udev-inputklassifikationer. Dette er en **bedre, men ikke garanteret** løsning: Cage kan stadig oprette en markør ud fra rå `EV_REL`-kapabiliteter. Kontrollér derfor effekten efter genstart. Hvis den stadig ses, skal vi undersøge libinput/Cage mere præcist og ikke deaktivere alle input-enheder. Reglen kan til enhver tid rulles tilbage via `cursor disable` og genstart.

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
