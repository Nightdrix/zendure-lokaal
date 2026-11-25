"""Lokale zenSDK-client voor Zendure-batterijen.

Praat rechtstreeks via HTTP met de batterij op het thuisnetwerk:
  GET  http://<ip>/properties/report  -> alle actuele waarden
  POST http://<ip>/properties/write   -> instellingen wijzigen

Dit bestand gebruikt bewust geen Home Assistant-code, zodat het los te testen is.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
from collections.abc import Iterable
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

HEADERS = {"Content-Type": "application/json; charset=UTF-8"}
REPORT_PATH = "properties/report"
WRITE_PATH = "properties/write"


class ZendureError(Exception):
    """Algemene fout bij het praten met de batterij."""


class ZendureConnectionError(ZendureError):
    """De batterij is niet bereikbaar."""


class ZendureResponseError(ZendureError):
    """Er antwoordt iets, maar het is geen (bruikbare) Zendure zenSDK-batterij."""


def _validate_report(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("properties"), dict):
        raise ZendureResponseError("Antwoord bevat geen 'properties'")
    return payload


class ZendureClient:
    """Eenvoudige HTTP-client voor één batterij."""

    def __init__(self, session: aiohttp.ClientSession, host: str, timeout: float = 5) -> None:
        self._session = session
        self.host = host.strip()
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._write_lock = asyncio.Lock()
        self._message_id = 0
        self.serial: str | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}"

    async def async_get_report(self) -> dict[str, Any]:
        """Haal alle actuele waarden op."""
        url = f"{self.base_url}/{REPORT_PATH}"
        try:
            async with self._session.get(url, headers=HEADERS, timeout=self._timeout) as resp:
                if resp.status >= 400:
                    raise ZendureResponseError(f"HTTP {resp.status}")
                text = await resp.text()
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise ZendureConnectionError(str(err) or type(err).__name__) from err

        try:
            payload = json.loads(text)
        except ValueError as err:
            raise ZendureResponseError("Geen geldige JSON") from err

        report = _validate_report(payload)
        if sn := report.get("sn"):
            self.serial = str(sn)
        return report

    async def async_write(self, properties: dict[str, Any]) -> None:
        """Schrijf één of meer instellingen naar de batterij."""
        if not properties:
            return
        async with self._write_lock:
            self._message_id += 1
            body: dict[str, Any] = {"id": self._message_id, "properties": properties}
            if self.serial:
                body["sn"] = self.serial
            url = f"{self.base_url}/{WRITE_PATH}"
            _LOGGER.debug("Schrijven naar %s: %s", self.host, properties)
            try:
                async with self._session.post(url, json=body, headers=HEADERS, timeout=self._timeout) as resp:
                    if resp.status >= 400:
                        raise ZendureResponseError(f"HTTP {resp.status}")
                    await resp.read()
            except (aiohttp.ClientError, TimeoutError, OSError) as err:
                raise ZendureConnectionError(str(err) or type(err).__name__) from err


async def async_probe(session: aiohttp.ClientSession, host: str, timeout: float = 2) -> dict[str, Any] | None:
    """Kijk of er op dit adres een Zendure-batterij met lokale API zit."""
    client = ZendureClient(session, host, timeout=timeout)
    try:
        return await client.async_get_report()
    except ZendureError:
        return None


def hosts_in_networks(networks: Iterable[str], max_hosts: int = 1024) -> list[str]:
    """Alle te scannen adressen in de opgegeven netwerken (bijv. '192.168.1.0/24')."""
    hosts: list[str] = []
    for net in networks:
        try:
            network = ipaddress.ip_network(net, strict=False)
        except ValueError:
            continue
        if network.version != 4 or network.num_addresses > max_hosts:
            continue
        hosts.extend(str(ip) for ip in network.hosts())
    # dubbele adressen eruit, volgorde behouden
    return list(dict.fromkeys(hosts))


async def async_scan(
    session: aiohttp.ClientSession,
    hosts: Iterable[str],
    timeout: float = 1.5,
    concurrency: int = 64,
) -> dict[str, dict[str, Any]]:
    """Zoek op het netwerk naar Zendure-batterijen. Geeft {ip: report} terug."""
    semaphore = asyncio.Semaphore(concurrency)
    found: dict[str, dict[str, Any]] = {}

    async def _probe(host: str) -> None:
        async with semaphore:
            report = await async_probe(session, host, timeout)
            if report is not None:
                found[host] = report

    await asyncio.gather(*(_probe(h) for h in hosts))
    return found
