"""Coördinator: leest de batterij uit en stuurt hem bij."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ZendureClient, ZendureError
from .const import (
    CONF_CAPACITY,
    CONF_CHARGE_MARGIN,
    CONF_CHARGE_START,
    CONF_DISCHARGE_MARGIN,
    CONF_DISCHARGE_START,
    CONF_INTERVAL,
    CONF_MAX_CHARGE,
    CONF_MAX_DISCHARGE,
    CONF_P1_EXPORT_SENSOR,
    CONF_P1_INVERT,
    CONF_P1_SENSOR,
    CONF_STANDBY_MINUTES,
    CONF_START_MODE,
    DEFAULT_CAPACITY,
    DEFAULT_CHARGE_MARGIN,
    DEFAULT_CHARGE_START,
    DEFAULT_DISCHARGE_MARGIN,
    DEFAULT_DISCHARGE_START,
    DEFAULT_INTERVAL,
    DEFAULT_MAX_POWER,
    DEFAULT_STANDBY_MINUTES,
    DOMAIN,
    ISSUE_HEMS_ACTIVE,
    ISSUE_P1_MISSING,
    MAX_FAILED_POLLS,
    MODE_MANUAL,
    MODE_OFF,
    MODE_SMART,
    P1_MAX_WAIT_SECONDS,
    P1_SETTLE_SECONDS,
    P1_STALE_SECONDS,
    P1_TIMEOUT_SECONDS,
    REFRESH_COOLDOWN_SECONDS,
    SECTION_ADVANCED,
    STATUS_CALIBRATING,
    STATUS_CHARGING,
    STATUS_DISCHARGING,
    STATUS_EMPTY,
    STATUS_FULL,
    STATUS_IDLE,
    STATUS_P1_MISSING,
    STATUS_STANDBY,
)
from .models import ZendureData
from .regelaar import (
    STANDBY_OPDRACHT,
    Meting,
    RegelInstellingen,
    bereken_doel,
    huidige_opdracht,
    moet_schrijven,
    opdracht,
)

_LOGGER = logging.getLogger(__name__)

type ZendureConfigEntry = ConfigEntry[ZendureCoordinator]


def entry_settings(entry: ConfigEntry) -> dict[str, Any]:
    """Alle instellingen van een config entry, plat (zonder secties)."""
    merged: dict[str, Any] = {**entry.data, **entry.options}
    advanced = merged.pop(SECTION_ADVANCED, None)
    if isinstance(advanced, dict):
        merged.update(advanced)
    return merged


class ZendureCoordinator(DataUpdateCoordinator[ZendureData]):
    """Leest elke paar seconden de batterij uit en regelt hem bij."""

    config_entry: ZendureConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ZendureConfigEntry, client: ZendureClient) -> None:
        self.settings = entry_settings(entry)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=int(self.settings.get(CONF_INTERVAL, DEFAULT_INTERVAL))),
            always_update=True,
            request_refresh_debouncer=Debouncer(hass, _LOGGER, cooldown=REFRESH_COOLDOWN_SECONDS, immediate=True),
        )
        self.client = client
        # None = nog niet hersteld na een herstart; dan sturen we nog niets aan.
        self.operation: str | None = None
        self.start_mode: str = self.settings.get(CONF_START_MODE, MODE_SMART)
        self.manual_power: float = 0
        self.target: int = 0
        self.status: str = STATUS_IDLE
        self.p1_value: float | None = None
        self._failed = 0
        self._p1_missing_since: datetime | None = None
        self._p1_stopped = False
        self._idle_since: datetime | None = None
        self._last_control_write: datetime | None = None

    # ------------------------------------------------------------------ helpers
    @property
    def serial(self) -> str:
        return self.data.serial if self.data else (self.config_entry.unique_id or "")

    @property
    def capacity_kwh(self) -> float:
        override = float(self.settings.get(CONF_CAPACITY, DEFAULT_CAPACITY) or 0)
        if override > 0:
            return override
        return self.data.capacity_kwh if self.data else 0.0

    def regel_instellingen(self, data: ZendureData) -> RegelInstellingen:
        s = self.settings
        return RegelInstellingen(
            max_charge=min(int(s.get(CONF_MAX_CHARGE, DEFAULT_MAX_POWER)), data.max_charge_limit),
            max_discharge=min(int(s.get(CONF_MAX_DISCHARGE, DEFAULT_MAX_POWER)), data.max_discharge_limit),
            charge_start=int(s.get(CONF_CHARGE_START, DEFAULT_CHARGE_START)),
            discharge_start=int(s.get(CONF_DISCHARGE_START, DEFAULT_DISCHARGE_START)),
            charge_margin=int(s.get(CONF_CHARGE_MARGIN, DEFAULT_CHARGE_MARGIN)),
            discharge_margin=int(s.get(CONF_DISCHARGE_MARGIN, DEFAULT_DISCHARGE_MARGIN)),
        )

    def _sensor_watt(self, entity_id: str | None) -> tuple[float, datetime] | None:
        """Lees een vermogenssensor uit in watt (+ tijdstip); None als hij niet bruikbaar is."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, ""):
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        last = getattr(state, "last_reported", None) or state.last_updated
        if (dt_util.utcnow() - last).total_seconds() > P1_STALE_SECONDS:
            return None
        unit = str(state.attributes.get("unit_of_measurement") or "W").strip()
        if unit.lower() == "kw":
            value *= 1000
        return value, last

    def _read_p1_timed(self) -> tuple[float, datetime] | None:
        """Netvermogen in watt (+ = afname, - = teruglevering) en wanneer het gemeten is."""
        reading = self._sensor_watt(self.settings.get(CONF_P1_SENSOR))
        if reading is None:
            return None
        value, measured = reading
        if export_sensor := self.settings.get(CONF_P1_EXPORT_SENSOR):
            export = self._sensor_watt(export_sensor)
            if export is None:
                return None
            value -= abs(export[0])
            measured = min(measured, export[1])
        if self.settings.get(CONF_P1_INVERT):
            value = -value
        return value, measured

    def read_p1(self) -> float | None:
        """Netvermogen in watt: + = afname, - = teruglevering."""
        reading = self._read_p1_timed()
        return None if reading is None else reading[0]

    def p1_entities(self) -> list[str]:
        return [e for e in (self.settings.get(CONF_P1_SENSOR), self.settings.get(CONF_P1_EXPORT_SENSOR)) if e]

    @callback
    def async_p1_changed(self, _event: Event[EventStateChangedData]) -> None:
        """Nieuwe meterstand: meteen bijsturen (max. eens per paar seconden)."""
        if self.operation in (None, MODE_OFF, MODE_MANUAL):
            return
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_write(self, data: ZendureData | None, properties: dict[str, Any]) -> None:
        await self.client.async_write(properties)
        if data is not None:
            data.apply_write(properties)

    # ---------------------------------------------------------------- polling
    async def _async_update_data(self) -> ZendureData:
        try:
            report = await self.client.async_get_report()
        except ZendureError as err:
            self._failed += 1
            if self.data is not None and self._failed < MAX_FAILED_POLLS:
                _LOGGER.debug("Batterij antwoordde niet (%s keer): %s", self._failed, err)
                return self.data
            raise UpdateFailed(f"Kan de batterij op {self.client.host} niet bereiken: {err}") from err

        self._failed = 0
        data = ZendureData.from_report(report)
        try:
            await self._async_regel(data)
        except ZendureError as err:
            _LOGGER.warning("Bijsturen van de batterij mislukt: %s", err)
        self.status = self._bepaal_status(data)
        self._check_hems(data)
        return data

    # ---------------------------------------------------------------- regelen
    async def _async_regel(self, data: ZendureData) -> None:
        now = dt_util.utcnow()
        mode = self.operation

        if mode is None:
            # Bedrijfsmodus is nog niet hersteld (net opgestart): nog niets doen.
            return

        if mode == MODE_OFF:
            # Uit: niets automatisch. Handmatige knoppen (en de planner) sturen direct.
            self.target = huidige_opdracht(data.ac_mode, data.input_limit, data.output_limit)
            self.p1_value = self.read_p1()
            await self._async_standby(data, now)
            return

        reading = self._read_p1_timed()
        p1 = None if reading is None else reading[0]
        self.p1_value = p1
        if reading is None and mode != MODE_MANUAL:
            await self._async_p1_missing(data, now)
            return
        if self._p1_missing_since is not None:
            self._p1_missing_since = None
            self._p1_stopped = False
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(ISSUE_P1_MISSING))
            _LOGGER.info("P1-meter is weer beschikbaar, regeling hervat")

        if reading is not None and mode != MODE_MANUAL and self._p1_te_oud(reading[1], now):
            # Deze meterstand is van vóór (of vlak na) onze laatste bijsturing: dan zou
            # de regeling doorschieten. Even wachten op een verse meting.
            await self._async_standby(data, now)
            return

        meting = Meting(
            p1=p1 or 0,
            ac_flow=data.ac_flow,
            solar=data.solar_power,
            full=data.is_full,
            empty=data.is_empty,
            current=huidige_opdracht(data.ac_mode, data.input_limit, data.output_limit),
        )
        doel = bereken_doel(mode, meting, self.regel_instellingen(data), self.manual_power)
        self.target = doel

        if moet_schrijven(doel, data.ac_mode, data.input_limit, data.output_limit, data.smart_mode):
            command = opdracht(doel)
            if doel == 0 and data.smart_mode == 0:
                command = dict(STANDBY_OPDRACHT)
            _LOGGER.debug("Regelen (%s): P1 %s W, batterij %s W -> doel %s W", mode, p1, data.ac_flow, doel)
            self._last_control_write = now
            await self._async_write(data, command)

        await self._async_standby(data, now)

    def _p1_te_oud(self, measured: datetime, now: datetime) -> bool:
        """Is de P1-meting van te kort na (of vóór) onze laatste opdracht?"""
        if self._last_control_write is None:
            return False
        if (now - self._last_control_write).total_seconds() >= P1_MAX_WAIT_SECONDS:
            return False  # niet eeuwig wachten
        return (measured - self._last_control_write).total_seconds() < P1_SETTLE_SECONDS

    async def _async_p1_missing(self, data: ZendureData, now: datetime) -> None:
        """Zonder P1-meter kunnen we niet veilig regelen: na een minuut stoppen."""
        if self._p1_missing_since is None:
            self._p1_missing_since = now
            return
        if self._p1_stopped:
            return
        if (now - self._p1_missing_since).total_seconds() < P1_TIMEOUT_SECONDS:
            return
        _LOGGER.warning("P1-meter geeft al een minuut geen waarde: batterij veiligheidshalve gestopt")
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id(ISSUE_P1_MISSING),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_P1_MISSING,
            translation_placeholders={"sensor": str(self.settings.get(CONF_P1_SENSOR))},
        )
        self.target = 0
        if data.input_limit or data.output_limit:
            await self._async_write(data, opdracht(0))
        self._p1_stopped = True

    async def _async_standby(self, data: ZendureData, now: datetime) -> None:
        """Na een tijdje niets doen: diepe stand-by (scheelt ~19 W sluipverbruik)."""
        minutes = int(self.settings.get(CONF_STANDBY_MINUTES, DEFAULT_STANDBY_MINUTES))
        idle = data.input_limit == 0 and data.output_limit == 0 and data.charge_power < 10 and data.discharge_power < 10
        if not idle or data.is_calibrating:
            self._idle_since = None
            return
        if data.smart_mode == 0 or minutes <= 0:
            return
        if self._idle_since is None:
            self._idle_since = now
            return
        if now - self._idle_since >= timedelta(minutes=minutes):
            _LOGGER.info("Batterij %s minuten niets gedaan: naar stand-by", minutes)
            await self._async_write(data, dict(STANDBY_OPDRACHT))
            self._idle_since = None

    def _bepaal_status(self, data: ZendureData) -> str:
        if self._p1_stopped and self.operation not in (None, MODE_OFF):
            return STATUS_P1_MISSING
        if data.is_calibrating:
            return STATUS_CALIBRATING
        if data.charge_power >= 10:
            return STATUS_CHARGING
        if data.discharge_power >= 10:
            return STATUS_DISCHARGING
        if data.smart_mode == 0 and data.input_limit == 0 and data.output_limit == 0:
            return STATUS_STANDBY
        if data.is_full:
            return STATUS_FULL
        if data.is_empty:
            return STATUS_EMPTY
        return STATUS_IDLE

    def _check_hems(self, data: ZendureData) -> None:
        issue_id = self._issue_id(ISSUE_HEMS_ACTIVE)
        if int(data.get("hemsState")) == 1:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_HEMS_ACTIVE,
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def _issue_id(self, key: str) -> str:
        return f"{key}_{self.config_entry.entry_id}"

    # --------------------------------------------------------- vanuit entities
    async def async_set_operation(self, mode: str, *, restored: bool = False) -> None:
        """Nieuwe bedrijfsmodus (vanuit het keuzemenu of de planner)."""
        previous = self.operation
        self.operation = mode
        self._p1_missing_since = None
        self._p1_stopped = False
        self._idle_since = None
        self._last_control_write = None  # nieuwe modus: direct mogen bijsturen
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(ISSUE_P1_MISSING))
        _LOGGER.info("Bedrijfsmodus: %s -> %s", previous, mode)

        if mode == MODE_OFF and not restored and previous not in (None, MODE_OFF):
            # Automatische sturing stopt: de batterij ook.
            self.target = 0
            if self.data is not None and (self.data.input_limit or self.data.output_limit):
                await self._async_write(self.data, opdracht(0))
            self.async_update_listeners()
            return
        await self.async_refresh()

    async def async_set_manual_power(self, value: float) -> None:
        self.manual_power = value
        if self.operation == MODE_MANUAL:
            await self.async_refresh()

    async def async_write_setting(self, properties: dict[str, Any]) -> None:
        """Eén instelling direct naar de batterij schrijven (knoppen/schuifjes)."""
        # Iemand (of de planner) doet iets: de stand-by-teller begint opnieuw.
        self._idle_since = None
        await self._async_write(self.data, properties)
        self.async_update_listeners()

    async def async_stop(self) -> None:
        """Home Assistant stopt met regelen: batterij stilzetten (veilig)."""
        if self.operation in (None, MODE_OFF) or self.data is None:
            return
        if self.data.input_limit or self.data.output_limit:
            try:
                await self.client.async_write(opdracht(0))
            except ZendureError as err:
                _LOGGER.debug("Stoppen bij afsluiten mislukt: %s", err)
