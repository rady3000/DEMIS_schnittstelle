"""Anbindung des offiziellen HL7-FHIR-Validators (Java) im Server-Modus.

Der Validator lädt die DEMIS-Profile einmal (ca. 20 Sekunden) und prüft danach jede Meldung in etwa
einer Sekunde. Konfiguration (begründet in PLAN.md / WARTUNG.md):

- ``-tx n/a``: kein externer Terminologieserver. Öffentliche Server kennen die deutschen
  SNOMED-Erweiterungscodes nicht; selbst die Beispiele des RKI fielen dort durch. DEMIS-eigene Codes
  (Meldetatbestände, Einrichtungsarten, Ja/Nein usw.) prüft der Validator trotzdem lokal. Die
  Fragebogen-Antworten (SNOMED, Länder) prüft ``fragebogen.py`` gegen die DEMIS-Wertemengen.
- ``-display-issues-are-warnings``: Abweichende Anzeigetexte sind nur Warnungen.
- ``hl7.terminology.r4#4.0.0``: enthält die HL7-Codesystem-Version 0.5.0, die DEMIS festlegt.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[3]
JAR = PROJEKT / "tools" / "validator_cli.jar"
PAKETE = [
    "rki.demis.common-3.0.0.tgz",
    "rki.demis.disease-3.0.0.tgz",
    "hl7.terminology.r4-4.0.0.tgz",
]
STANDARD_URL = "http://localhost:8090"


class ValidatorFehler(Exception):
    """Der Validator ist nicht erreichbar oder antwortet unbrauchbar (Text auf Deutsch)."""


class FhirValidator:
    def __init__(self, url: str | None = None, timeout: float = 120):
        self.url = (url or os.environ.get("VALIDATOR_URL") or STANDARD_URL).rstrip("/")
        self.timeout = timeout

    def ist_bereit(self) -> bool:
        try:
            urllib.request.urlopen(f"{self.url}/validator/version", timeout=3)
            return True
        except urllib.error.HTTPError:
            return True  # der Server antwortet (404 für diesen Pfad ist normal)
        except OSError:
            return False

    def pruefe(self, bundle: dict) -> dict:
        """Gibt das OperationOutcome des Validators zurück."""
        anfrage = urllib.request.Request(
            f"{self.url}/validateResource",
            data=json.dumps(bundle).encode("utf-8"),
            headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"},
        )
        try:
            with urllib.request.urlopen(anfrage, timeout=self.timeout) as antwort:
                ergebnis = json.load(antwort)
        except OSError as problem:
            raise ValidatorFehler("Der Meldungsprüfer (Validator) ist nicht erreichbar. Bitte die IT informieren.") from problem
        except ValueError as problem:
            raise ValidatorFehler("Der Meldungsprüfer hat eine unverständliche Antwort geliefert.") from problem
        if ergebnis.get("resourceType") != "OperationOutcome":
            raise ValidatorFehler("Der Meldungsprüfer hat keine Prüfergebnisse geliefert.")
        return ergebnis


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def starte_server(port: int, logdatei: Path | None = None, warte_sekunden: int = 180) -> subprocess.Popen:
    """Startet den Validator-Server als Unterprozess und wartet, bis er bereit ist."""
    if not JAR.exists():
        raise ValidatorFehler(f"{JAR} fehlt. Bitte 'python tools/einrichten.py' ausführen.")
    befehl = ["java", "-jar", str(JAR), "-server", str(port), "-version", "4.0.1"]
    for name in PAKETE:
        pfad = PROJEKT / ".fhir" / "pakete" / name
        if not pfad.exists():
            raise ValidatorFehler(f"{pfad} fehlt. Bitte 'python tools/einrichten.py' ausführen.")
        befehl += ["-ig", str(pfad)]
    befehl += ["-tx", "n/a", "-display-issues-are-warnings"]
    ziel = open(logdatei, "wb") if logdatei else subprocess.DEVNULL
    prozess = subprocess.Popen(befehl, stdout=ziel, stderr=subprocess.STDOUT)
    pruefer = FhirValidator(f"http://localhost:{port}")
    ende = time.time() + warte_sekunden
    while time.time() < ende:
        if prozess.poll() is not None:
            raise ValidatorFehler("Der Validator wurde unerwartet beendet.")
        if pruefer.ist_bereit():
            return prozess
        time.sleep(2)
    prozess.terminate()
    raise ValidatorFehler("Der Validator ist nicht rechtzeitig gestartet.")
