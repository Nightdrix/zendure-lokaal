# Zendure Lokaal

Je Zendure-thuisbatterij **100% lokaal** in Home Assistant, ingesteld met een paar klikken.
Er is geen Zendure-account, geen cloud, geen YAML en geen automatisering nodig.
Werkt direct samen met de **planner van [Energienerds.nl](https://energienerds.nl/)**.

Gemaakt voor de **SolarFlow 3000 Mix AC+**. Werkt ook met andere Zendure-batterijen met lokale API (zenSDK):
SolarFlow 4000 Mix, 2400 AC / AC+ / Pro, 1600 AC+ en 800 Pro / Plus.

| | Gielz-pakket | **Zendure Lokaal** |
|---|---|---|
| Installeren | YAML-bestanden, `configuration.yaml` aanpassen, automatisering plakken | Map kopiëren, daarna alles via het scherm |
| Batterij koppelen | IP-adres in een tekstveld typen | Automatisch zoeken, of IP invullen met controle |
| Instellingen | ± 20 losse schuifjes en vinkjes | Eén instelscherm met uitleg bij elke instelling |
| Nul op de meter | Automatisering die elke 5 s draait | Ingebouwd |
| Energienerds-planner | Werkt niet | Eén knop: **Koppel aan Energienerds-planner** |

---

## Wat heb je nodig?

- Home Assistant **2025.2 of nieuwer**
- Een Zendure-batterij met lokale API (werkte het Gielz-pakket bij jou, dan is dat in orde)
- Een slimme meter in Home Assistant, bij voorkeur een **HomeWizard P1**
- In de Zendure-app: **HEMS uitgeschakeld**

---

## Stap 0 – Oude koppeling opruimen (belangrijk!)

Er mag maar **één** systeem tegelijk de batterij aansturen. Staat het Gielz-pakket er nu op, ruim het dan eerst op:

1. Ga naar **Instellingen → Automatiseringen** en zet **Zendure zenSDK (Gielz)** uit (of verwijder hem).
2. Verwijder het bestand `packages/zendure_gielz1986_nl.yaml` uit je Home Assistant-map.
3. Heb je de officiële Zendure-integratie geïnstalleerd? Verwijder die ook, want hij ondersteunt de 3000 Mix niet.
4. Herstart Home Assistant.

> Let op: kaarten op je dashboard die Gielz-entiteiten gebruikten, werken daarna niet meer. Die vervang je door de planner-kaart (stap 3).

---

## Stap 1 – Installeren

### Manier A: via HACS (aanbevolen – je krijgt ook updates)

1. Klik op deze knop (op een apparaat waarop je Home Assistant kunt openen):

   [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Nightdrix&repository=zendure-lokaal&category=integration)

   Werkt de knop niet? Open dan **HACS → ⋮ (rechtsboven) → Aangepaste repositories**, plak
   `https://github.com/Nightdrix/zendure-lokaal`, kies type **Integratie** en klik op **Toevoegen**.
2. Klik op **Downloaden** en daarna nog een keer op **Downloaden**.
3. Herstart Home Assistant (**Instellingen → Systeem → rechtsboven ⏻ → Home Assistant opnieuw opstarten**).

### Manier B: map kopiëren (zonder HACS)

1. Download `zendure_lokaal-x.x.x.zip` bij de nieuwste [release](https://github.com/Nightdrix/zendure-lokaal/releases/latest) en pak hem uit.
2. Installeer in Home Assistant de add-on **Samba share** (Instellingen → Add-ons → Add-on winkel), vul een gebruikersnaam en wachtwoord in en start hem.
3. Open op je Windows-pc de Verkenner en typ in de adresbalk: `\\homeassistant.local\config`
4. Open de map `custom_components`. Bestaat die nog niet? Maak hem dan aan.
5. Kopieer de uitgepakte map **`zendure_lokaal`** daarin.
   Je hebt dan: `config/custom_components/zendure_lokaal/manifest.json` (enz.)
6. Herstart Home Assistant.

---

## Stap 2 – Batterij koppelen

1. Ga naar **Instellingen → Apparaten & diensten → Integratie toevoegen** en zoek op **Zendure Lokaal**.
2. **IP-adres**: laat het veld leeg en klik op *Verzenden*. De batterij wordt dan automatisch gezocht.
   Wordt hij niet gevonden? Vul het IP-adres in. Dat staat in de Zendure-app onder je batterij → ⚙️ → *Apparaatinformatie*.
3. **Slimme meter**: kies de vermogenssensor van je P1-meter. Bij een HomeWizard heet die *Vermogen* of *Power*.
4. **Instellingen**: de standaardwaarden zijn goed, dus klik gewoon op *Verzenden*.

Klaar! De batterij doet nu **nul op de meter**: hij laadt met je zonne-overschot en levert stroom als je huis verbruikt.

💡 Tip: geef de batterij in je router een **vast IP-adres**. Krijgt hij toch een ander adres, ga dan naar
*Zendure Lokaal → ⋮ → Opnieuw configureren*.

---

## Stap 3 – Energienerds-planner (het dashboard)

Met de planner van Energienerds stel je per uur in wat de batterij moet doen, bijvoorbeeld *goedkoop laden*, *duur ontladen* of *nul op de meter*.

1. Installeer de planner via HACS:
   [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=zendure-schedule&category=integration&owner=Mediacj)
   Herstart daarna Home Assistant.
2. Ga naar **Instellingen → Apparaten & diensten → Zendure Lokaal** en open je batterij (het apparaat).
3. Klik onder *Configuratie* op **Koppel aan Energienerds-planner** → *Indrukken*.
   De planner wordt nu automatisch met de juiste knoppen ingesteld.
4. Open je dashboard → ✏️ (bewerken) → **Kaart toevoegen** → zoek op **schedule** → kies *Zendure Schedule*.
   Staat hij er niet tussen? Ververs de pagina met **Ctrl+F5**.

<details>
<summary>Liever handmatig koppelen? Dit vul je in bij de planner</summary>

| Veld in de planner | Kies deze entiteit van je batterij |
|---|---|
| Bedrijfsmodus | **Bedrijfsmodus** (`select.…_bedrijfsmodus`) |
| AC mode select (input/output) | **AC-modus** (`select.…_ac_modus`) |
| Laadvermogen (input_limit) | **Laadvermogen** (`number.…_laadvermogen`) |
| Ontlaadvermogen (output_limit) | **Ontlaadvermogen** (`number.…_ontlaadvermogen`) |
| Max SOC bij laden | **Maximaal laadniveau** (`number.…_maximaal_laadniveau`) |
| Min SOC bij ontladen | **Minimaal laadniveau** (`number.…_minimaal_laadniveau`) |

Alle andere velden kun je op de standaardwaarde laten staan.
</details>

---

## De bedrijfsmodi

Je kiest de modus zelf via **Bedrijfsmodus**, of de planner doet het per uur voor je.

| Modus | Wat doet de batterij? | Planner-knop |
|---|---|---|
| **Nul op de meter** | Laadt met overschot en ontlaadt bij verbruik, zodat je meter rond 0 W blijft | NOM |
| **Slim ontladen** | Alleen ontladen naar je verbruik, nooit laden | SLM-O |
| **Slim laden** | Alleen laden met overschot, nooit ontladen uit de accu | SLM-L |
| **Alleen zonne-energie opslaan** | Alleen laden met overschot en nooit stroom leveren | – |
| **Vast vermogen** | Laadt of ontlaadt met een vast vermogen (schuifje *Vast vermogen*) | – |
| **Uit** | Doet niets automatisch. Wordt door de planner gebruikt voor *Laden*, *Ontladen* en *Uit* | Laden / Ontladen / Uit |

### Veiligheid ingebouwd
- **P1-meter weg?** Na een minuut stopt de batterij en krijg je een melding. Werkt de meter weer, dan gaat hij vanzelf verder.
- **Home Assistant uit of herstart?** De batterij wordt eerst stilgezet, zodat hij niet blijft doorgaan met een oud vermogen.
- **15 minuten niets te doen?** Dan gaat de batterij in diepe stand-by. Dat bespaart ongeveer 19 W sluipverbruik.
- **HEMS per ongeluk aan?** Dan zie je een melding onder *Instellingen → Reparaties*.
- Alle snelle bijsturingen gaan naar het werkgeheugen van de batterij, dus zijn flashgeheugen slijt niet.

---

## Instellingen aanpassen

Ga naar **Instellingen → Apparaten & diensten → Zendure Lokaal → Configureren**. Daar vind je:

- je slimme meter en het maximale laad- en ontlaadvermogen;
- onder **Geavanceerd** de fijnafstelling. Elke instelling heeft uitleg en een advieswaarde:

| Instelling | Advies | Uitleg |
|---|---|---|
| Ontladen begint vanaf | 100 W | Pas ontladen als het huis minstens zoveel van het net haalt |
| Laden begint vanaf | 300 W | Pas laden als je minstens zoveel teruglevert |
| Restafname tijdens ontladen | 10 W | Voorkomt dat accu-stroom het net op gaat |
| Restteruglevering tijdens laden | 50 W | Voorkomt dat je met net-stroom laadt |
| Naar stand-by na | 15 min | 0 = nooit |
| Bijsturen elke | 5 s | Hoe vaak de batterij wordt bijgestuurd |
| Capaciteit | 0 | 0 = automatisch; alleen invullen als de sensor *Capaciteit* niet klopt |

---

## Wat zie je in Home Assistant?

Op de apparaatpagina van je batterij staan onder andere:

- **Laadniveau**, **Status** (Laden / Ontladen / Wacht / Stand-by / Vol / Leeg) en **Beschikbare energie**
- **Accuvermogen**, **Vermogen naar huis**, **Vermogen van het net**, **Zonnepanelen** (+ per ingang)
- **Doelvermogen**: wat de regeling op dit moment wil, en **Netvermogen (P1)**: wat de regeling van je meter leest
- **Energie geladen / ontladen / naar huis / van het net / zonnepanelen** voor het *Energie*-dashboard
- Per accupakket een eigen apparaat met laadniveau, temperatuur en celspanningsverschil

**Energie-dashboard** (*Instellingen → Dashboards → Energie*):
- *Thuisbatterij* → energie de batterij in: **Energie geladen**, energie de batterij uit: **Energie ontladen**
- *Zonnepanelen* → **Energie zonnepanelen** (alleen als er panelen op de batterij zitten)

<details>
<summary>Voorbeeld: eenvoudige overzichtskaart (zonder extra installaties)</summary>

Vervang `solarflow_3000_mix_ac` door de naam van jouw batterij als die anders is.

```yaml
type: entities
title: Thuisbatterij
entities:
  - entity: select.solarflow_3000_mix_ac_bedrijfsmodus
  - entity: sensor.solarflow_3000_mix_ac_status
  - entity: sensor.solarflow_3000_mix_ac_laadniveau
  - entity: sensor.solarflow_3000_mix_ac_accuvermogen_ontladen_laden
  - entity: sensor.solarflow_3000_mix_ac_netvermogen_p1
  - entity: sensor.solarflow_3000_mix_ac_beschikbare_energie
```
</details>

---

## Problemen oplossen

| Probleem | Oplossing |
|---|---|
| *Geen batterij gevonden* | Vul het IP-adres handmatig in (Zendure-app → Apparaatinformatie). Staan Home Assistant en de batterij op hetzelfde netwerk? |
| *Kan de batterij niet bereiken* | Klopt het IP-adres? Geef de batterij een vast IP-adres in je router. |
| Status **Gestopt: geen P1-meter** | Je slimme meter geeft geen waarde. Controleer de P1-meter; de batterij gaat vanzelf verder. |
| Batterij doet rare dingen | Staat HEMS uit in de Zendure-app? Staat de Gielz-automatisering echt uit (stap 0)? |
| Meer details nodig | Zendure Lokaal → ⋮ → **Diagnostische gegevens downloaden**, of zet extra logging aan (zie hieronder). |

```yaml
# configuration.yaml – extra logging
logger:
  default: warning
  logs:
    custom_components.zendure_lokaal: debug
```

---

## Voor de techneuten

- Praat via HTTP met de batterij: `GET /properties/report` en `POST /properties/write` (zenSDK).
- Bedrijfsmodi en entiteiten zijn bewust gelijk aan de officiële [Zendure-HA](https://github.com/Zendure/Zendure-HA)-integratie (`off`, `smart`, `smart_discharging`, `smart_charging`, `acMode`, `inputLimit`, `outputLimit`, `socSet`, `minSoc`), zodat de [Energienerds-planner](https://github.com/Mediacj/zendure-schedule) er zonder aanpassing mee werkt.
- De regeling: `vraag = P1 + (vermogen naar huis − vermogen van net)`. Met startdrempels en marges voorkom je pendelen.
- Testen zonder echte batterij: `tests/fake_zendure.py` simuleert een SolarFlow 3000 Mix AC+ (accu, panelen, huisverbruik, P1).

```powershell
pip install pytest-homeassistant-custom-component
pytest
```

Met dank aan het werk van [Gielz1986](https://github.com/Gielz1986/Zendure-HA-zenSDK) en de [officiële Zendure-integratie](https://github.com/Zendure/Zendure-HA), waarop de regeling en standaardwaarden zijn gebaseerd.
