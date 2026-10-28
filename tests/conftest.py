"""Gemeinsame Test-Bausteine.

Der Fixture ``adapter`` läuft gegen ZWEI Quellen: den eingebauten Fake-Server (immer) und das
echte Schein-KIS (nur wenn es unter http://localhost:8080/fhir erreichbar ist, sonst übersprungen).
"""

import httpx
import pytest

from fake_fhir import BASIS, FakeFhirServer
from meldeassistent.kis.isik_fhir import IsikFhirAdapter
from meldeassistent.testdaten import einspielen

LIVE_URL = einspielen.STANDARD_URL


def schein_kis_erreichbar() -> bool:
    try:
        return httpx.get(f"{LIVE_URL}/metadata", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="session")
def live_bereit():
    if not schein_kis_erreichbar():
        pytest.skip("Schein-KIS läuft nicht (docker compose up -d)")
    einspielen.spiele_ein(LIVE_URL)  # wiederholbar, keine Duplikate
    return LIVE_URL


@pytest.fixture(params=["fake", "live"])
def adapter(request):
    if request.param == "fake":
        server = FakeFhirServer()
        yield IsikFhirAdapter(BASIS, client=server.client())
    else:
        url = request.getfixturevalue("live_bereit")
        with IsikFhirAdapter(url) as a:
            yield a
