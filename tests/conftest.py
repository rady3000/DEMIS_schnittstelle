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


# --- DEMIS (Phase 3) -------------------------------------------------------------------------
import os
import subprocess
from pathlib import Path

from meldeassistent.demis import validator as validator_modul
from meldeassistent.demis.pakete import PaketeFehlen, standard_pakete


@pytest.fixture(scope="session")
def pakete():
    try:
        return standard_pakete()
    except PaketeFehlen as fehler:
        pytest.skip(str(fehler))


@pytest.fixture(scope="session")
def validator(tmp_path_factory):
    """Der FHIR-Validator: ein schon laufender (VALIDATOR_URL / Port 8090) oder ein eigener Unterprozess."""
    vorhanden = validator_modul.FhirValidator()
    if vorhanden.ist_bereit():
        yield vorhanden
        return
    if not validator_modul.JAR.exists():
        pytest.skip("Validator fehlt: python tools/einrichten.py")
    port = validator_modul.freier_port()
    log = tmp_path_factory.mktemp("validator") / "validator.log"
    try:
        prozess = validator_modul.starte_server(port, log)
    except validator_modul.ValidatorFehler as fehler:
        pytest.skip(str(fehler))
    try:
        yield validator_modul.FhirValidator(f"http://localhost:{port}")
    finally:
        prozess.terminate()
