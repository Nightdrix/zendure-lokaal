"""Gedeelde test-fixtures."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from aiohttp.test_utils import TestServer

from .fake_zendure import FakeZendure

# Optioneel: de échte Energienerds-planner meetesten. Zet ZENDURE_SCHEDULE_SRC op de map
# custom_components/zendure_schedule uit github.com/Mediacj/zendure-schedule.
# We gebruiken een kopie zonder frontend-afhankelijkheden (de kaart zelf testen we niet).
PLANNER_AVAILABLE = False
if (_src := os.environ.get("ZENDURE_SCHEDULE_SRC")) and Path(_src, "manifest.json").is_file():
    _root = Path(tempfile.mkdtemp(prefix="planner_"))
    _dest = _root / "custom_components" / "zendure_schedule"
    shutil.copytree(_src, _dest)
    _manifest = json.loads((_dest / "manifest.json").read_text(encoding="utf-8"))
    _manifest["dependencies"] = []
    _manifest["after_dependencies"] = []
    (_dest / "manifest.json").write_text(json.dumps(_manifest), encoding="utf-8")
    sys.path.append(str(_root))
    PLANNER_AVAILABLE = True

if sys.platform == "win32":
    # Home Assistant test-tools blokkeren sockets, maar de asyncio-loop op Windows
    # heeft een lokale socket nodig. Alleen voor het draaien van tests op Windows;
    # verbindingen blijven beperkt tot 127.0.0.1.
    import pytest_socket

    pytest_socket.disable_socket = lambda *args, **kwargs: None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Laat Home Assistant onze custom integratie laden."""


@pytest.fixture
def fake() -> FakeZendure:
    return FakeZendure()


@pytest.fixture
async def fake_server(fake: FakeZendure) -> AsyncGenerator[str]:
    """Start de nep-batterij op 127.0.0.1 en geef 'ip:poort' terug."""
    server = TestServer(fake.app(), host="127.0.0.1")
    await server.start_server()
    yield f"127.0.0.1:{server.port}"
    await server.close()
