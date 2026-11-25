"""Nep-Zendure: simuleert een SolarFlow 3000 Mix AC+ met lokale zenSDK-API.

Gebruikt in de tests, maar ook los te starten om de integratie zonder echte
batterij uit te proberen:

    python tests/fake_zendure.py --port 8080

Simuleert: laadniveau, laad-/ontlaadlimieten, AC-modus, zonnepanelen op de
batterij, huisverbruik en de P1-meter (GET /p1 geeft het netvermogen).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web

EFFICIENCY = 0.95


@dataclass
class FakeZendure:
    product: str = "solarFlow3000MixAC+"
    sn: str = "HOA3MIX0000TEST"
    capacity_kwh: float = 8.0
    soc: float = 50.0
    soc_set: int = 1000  # x10
    min_soc: int = 100  # x10
    ac_mode: int = 2
    input_limit: int = 0
    output_limit: int = 0
    smart_mode: int = 0
    grid_reverse: int = 1
    charge_max: int = 2400
    discharge_max: int = 2400
    solar: float = 0.0  # zonnepanelen op de batterij
    house_load: float = 400.0  # verbruik van het huis
    house_solar: float = 0.0  # losse zonnepanelen (eigen omvormer)
    hems: int = 0
    # gemeten
    grid_input: float = 0.0
    home_output: float = 0.0
    pack_in: float = 0.0  # ontladen
    pack_out: float = 0.0  # laden
    writes: list[dict[str, Any]] = field(default_factory=list)
    fail: bool = False

    # ------------------------------------------------------------ physics
    @property
    def full(self) -> bool:
        return self.soc >= self.soc_set / 10

    @property
    def empty(self) -> bool:
        return self.soc <= self.min_soc / 10

    def step(self, seconds: float = 5.0) -> None:
        """Bereken de vermogens bij de huidige instellingen en werk het laadniveau bij."""
        solar = self.solar
        self.grid_input = self.home_output = self.pack_in = self.pack_out = 0.0

        if self.ac_mode == 1 and self.input_limit > 0 and not self.full:
            self.grid_input = float(min(self.input_limit, self.charge_max))
            self.pack_out = self.grid_input * EFFICIENCY + solar
        elif self.ac_mode == 2 and self.output_limit > 0:
            want = float(min(self.output_limit, self.discharge_max))
            from_solar = min(want, solar)
            from_battery = 0.0 if self.empty else want - from_solar
            self.home_output = from_solar + from_battery
            self.pack_in = from_battery / EFFICIENCY
            rest_solar = solar - from_solar
            if rest_solar > 0 and not self.full:
                self.pack_out = rest_solar
            elif rest_solar > 0 and self.grid_reverse == 1:
                self.home_output += rest_solar
        else:
            if solar > 0 and not self.full:
                self.pack_out = solar
            elif solar > 0 and self.grid_reverse == 1:
                self.home_output = solar

        net_pack = self.pack_out - self.pack_in
        self.pack_in, self.pack_out = max(0.0, -net_pack), max(0.0, net_pack)
        delta_kwh = net_pack * seconds / 3_600_000
        self.soc = max(0.0, min(100.0, self.soc + delta_kwh / self.capacity_kwh * 100))

    @property
    def p1(self) -> float:
        """Netvermogen zoals de slimme meter het ziet (+ afname, - teruglevering)."""
        return self.house_load - self.house_solar - self.home_output + self.grid_input

    # ------------------------------------------------------------ zenSDK
    def report(self) -> dict[str, Any]:
        soc_limit = 1 if self.full else 2 if self.empty else 0
        return {
            "timestamp": 1764000000,
            "messageId": 1,
            "sn": self.sn,
            "product": self.product,
            "properties": {
                "electricLevel": round(self.soc),
                "socSet": self.soc_set,
                "minSoc": self.min_soc,
                "inputLimit": self.input_limit,
                "outputLimit": self.output_limit,
                "acMode": self.ac_mode,
                "smartMode": self.smart_mode,
                "gridInputPower": round(self.grid_input),
                "outputHomePower": round(self.home_output),
                "packInputPower": round(self.pack_in),
                "outputPackPower": round(self.pack_out),
                "solarInputPower": round(self.solar),
                "solarPower1": round(self.solar / 2),
                "solarPower2": round(self.solar / 2),
                "gridOffPower": 0,
                "gridOffMode": 2,
                "chargeMaxLimit": self.charge_max,
                "inverseMaxPower": self.discharge_max,
                "socLimit": soc_limit,
                "socStatus": 0,
                "hyperTmp": 2981,
                "pass": 0,
                "gridReverse": self.grid_reverse,
                "packNum": 2,
                "packState": 1 if self.pack_out else 2 if self.pack_in else 0,
                "BatVolt": 5120,
                "rssi": -58,
                "hemsState": self.hems,
                "heatState": 0,
                "is_error": 0,
            },
            "packData": [
                {
                    "sn": "BO4HMIXPACK0001",
                    "packType": 70,
                    "socLevel": round(self.soc),
                    "state": 0,
                    "power": round(self.pack_out - self.pack_in),
                    "maxTemp": 2991,
                    "totalVol": 5120,
                    "batcur": 0,
                    "maxVol": 334,
                    "minVol": 332,
                    "softVersion": 4100,
                },
                {
                    "sn": "FO4HAB3000PACK2",
                    "packType": 300,
                    "socLevel": round(self.soc),
                    "state": 0,
                    "power": 0,
                    "maxTemp": 2985,
                    "totalVol": 5118,
                    "batcur": 0,
                    "maxVol": 333,
                    "minVol": 331,
                    "softVersion": 4100,
                },
            ],
        }

    def write(self, body: dict[str, Any]) -> None:
        props = body.get("properties") or {}
        self.writes.append(props)
        mapping = {
            "acMode": "ac_mode",
            "inputLimit": "input_limit",
            "outputLimit": "output_limit",
            "smartMode": "smart_mode",
            "socSet": "soc_set",
            "minSoc": "min_soc",
            "gridReverse": "grid_reverse",
        }
        for key, value in props.items():
            if key in mapping:
                setattr(self, mapping[key], int(value))
        # De echte batterij reageert binnen een paar seconden; wij direct.
        self.step(0)

    # ------------------------------------------------------------ webserver
    def app(self) -> web.Application:
        async def report(_request: web.Request) -> web.Response:
            if self.fail:
                raise web.HTTPServiceUnavailable
            return web.Response(text=json.dumps(self.report()), content_type="text/plain")

        async def write(request: web.Request) -> web.Response:
            if self.fail:
                raise web.HTTPServiceUnavailable
            self.write(await request.json())
            return web.json_response({"code": 200, "success": True})

        async def p1(_request: web.Request) -> web.Response:
            return web.json_response({"active_power_w": round(self.p1)})

        async def sim(request: web.Request) -> web.Response:
            """Demo: verander verbruik/zon terwijl hij draait (load, house_solar, solar)."""
            for key, value in (await request.json()).items():
                if key in ("house_load", "house_solar", "solar", "soc"):
                    setattr(self, key, float(value))
            return web.json_response({"house_load": self.house_load, "house_solar": self.house_solar, "solar": self.solar})

        app = web.Application()
        app.router.add_get("/properties/report", report)
        app.router.add_post("/properties/write", write)
        app.router.add_get("/p1", p1)
        app.router.add_post("/sim", sim)
        return app


def main() -> None:
    import asyncio

    parser = argparse.ArgumentParser(description="Nep-Zendure-batterij voor tests")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--load", type=float, default=400, help="huisverbruik (W)")
    parser.add_argument("--house-solar", type=float, default=0, help="losse zonnepanelen (W)")
    parser.add_argument("--solar", type=float, default=0, help="zonnepanelen op de batterij (W)")
    parser.add_argument("--soc", type=float, default=50, help="start-laadniveau (%%)")
    args = parser.parse_args()
    fake = FakeZendure(house_load=args.load, house_solar=args.house_solar, solar=args.solar, soc=args.soc)

    async def tick() -> None:
        while True:
            fake.step(1)
            await asyncio.sleep(1)

    async def run() -> None:
        runner = web.AppRunner(fake.app())
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", args.port).start()
        print(f"Nep-Zendure draait op poort {args.port} (P1: http://<ip>:{args.port}/p1)")
        await tick()

    asyncio.run(run())


if __name__ == "__main__":
    main()
