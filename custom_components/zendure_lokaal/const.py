"""Constanten voor Zendure Lokaal."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "zendure_lokaal"
NAME: Final = "Zendure Lokaal"
MANUFACTURER: Final = "Zendure"

# --- Config entry keys -------------------------------------------------------
CONF_HOST: Final = "host"
CONF_P1_SENSOR: Final = "p1_sensor"
CONF_P1_EXPORT_SENSOR: Final = "p1_export_sensor"
CONF_P1_INVERT: Final = "p1_invert"
CONF_START_MODE: Final = "start_mode"
CONF_MAX_CHARGE: Final = "max_charge_power"
CONF_MAX_DISCHARGE: Final = "max_discharge_power"
CONF_CHARGE_START: Final = "charge_start"
CONF_DISCHARGE_START: Final = "discharge_start"
CONF_CHARGE_MARGIN: Final = "charge_margin"
CONF_DISCHARGE_MARGIN: Final = "discharge_margin"
CONF_STANDBY_MINUTES: Final = "standby_minutes"
CONF_INTERVAL: Final = "interval"
CONF_CAPACITY: Final = "capacity"

SECTION_ADVANCED: Final = "geavanceerd"

# --- Standaardwaarden (gebaseerd op beproefde community-instellingen) --------
DEFAULT_MAX_POWER: Final = 2400
DEFAULT_CHARGE_START: Final = 300
DEFAULT_DISCHARGE_START: Final = 100
DEFAULT_CHARGE_MARGIN: Final = 50
DEFAULT_DISCHARGE_MARGIN: Final = 10
DEFAULT_STANDBY_MINUTES: Final = 15
DEFAULT_INTERVAL: Final = 5
DEFAULT_CAPACITY: Final = 0.0

# Hoe lang de P1-meter weg mag zijn voordat de accu veiligheidshalve stopt.
P1_TIMEOUT_SECONDS: Final = 60
# Een P1-waarde die langer dan dit niet ververst is, vertrouwen we niet.
P1_STALE_SECONDS: Final = 180
# Een P1-meting moet minstens zo lang ná onze laatste bijsturing zijn gedaan,
# anders ziet de meter het effect nog niet en schiet de regeling door.
P1_SETTLE_SECONDS: Final = 2
# ...maar nooit langer wachten dan dit op een verse meting.
P1_MAX_WAIT_SECONDS: Final = 15
# Bij een nieuwe meterstand direct bijsturen, maar hooguit eens per zoveel seconden.
REFRESH_COOLDOWN_SECONDS: Final = 2
# Na zoveel mislukte pogingen op rij is de batterij "onbereikbaar".
MAX_FAILED_POLLS: Final = 3

# --- Bedrijfsmodi ------------------------------------------------------------
# Deze waarden zijn bewust gelijk aan die van de officiële Zendure-integratie,
# zodat de Energienerds-planner (zendure_schedule) er zonder aanpassing mee werkt.
MODE_OFF: Final = "off"
MODE_MANUAL: Final = "manual"
MODE_SMART: Final = "smart"
MODE_SMART_DISCHARGING: Final = "smart_discharging"
MODE_SMART_CHARGING: Final = "smart_charging"
MODE_STORE_SOLAR: Final = "store_solar"
OPERATION_MODES: Final = [
    MODE_OFF,
    MODE_MANUAL,
    MODE_SMART,
    MODE_SMART_DISCHARGING,
    MODE_SMART_CHARGING,
    MODE_STORE_SOLAR,
]
START_MODES: Final = [MODE_SMART, MODE_OFF]

# AC-modus zoals de batterij hem kent.
AC_MODE_INPUT: Final = "input"
AC_MODE_OUTPUT: Final = "output"
AC_MODES: Final = {1: AC_MODE_INPUT, 2: AC_MODE_OUTPUT}
AC_MODE_VALUES: Final = {v: k for k, v in AC_MODES.items()}

# Status van de accu (sensor "Status").
STATUS_CHARGING: Final = "charging"
STATUS_DISCHARGING: Final = "discharging"
STATUS_IDLE: Final = "idle"
STATUS_STANDBY: Final = "standby"
STATUS_FULL: Final = "full"
STATUS_EMPTY: Final = "empty"
STATUS_P1_MISSING: Final = "p1_missing"
STATUS_CALIBRATING: Final = "calibrating"
STATUSES: Final = [
    STATUS_CHARGING,
    STATUS_DISCHARGING,
    STATUS_IDLE,
    STATUS_STANDBY,
    STATUS_FULL,
    STATUS_EMPTY,
    STATUS_P1_MISSING,
    STATUS_CALIBRATING,
]

# Energienerds-planner
PLANNER_DOMAIN: Final = "zendure_schedule"

# Repair-meldingen
ISSUE_P1_MISSING: Final = "p1_missing"
ISSUE_HEMS_ACTIVE: Final = "hems_active"
