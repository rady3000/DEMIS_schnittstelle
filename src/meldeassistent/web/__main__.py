"""Startet die Anwendung:  python -m meldeassistent.web

Einstellungen über Umgebungsvariablen (siehe config/app.example.env). Standard ist immer der Testbetrieb mit
dem lokalen Schein-KIS (Harte Regel 2). Geheimnisse gehören nie in den Code.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

from meldeassistent.audit import Audit
from meldeassistent.demis.pakete import PaketeFehlen, standard_pakete
from meldeassistent.demis.validator import FhirValidator, ValidatorFehler, freier_port, starte_server
from meldeassistent.konfig import KisKonfig, erzeuge_kis_adapter
from meldeassistent.testdaten.demo_meldung import KONFIG, MELDER
from meldeassistent.web.app import Einstellungen, erzeuge_app


def lies_benutzer(text: str) -> dict[str, str]:
    """'name:passwort;name2:passwort2' -> Wörterbuch. Nur für den Testbetrieb."""
    ergebnis = {}
    for teil in filter(None, (t.strip() for t in text.split(";"))):
        name, _, passwort = teil.partition(":")
        if name and passwort:
            ergebnis[name] = passwort
    return ergebnis


def main() -> int:
    testbetrieb = os.environ.get("MELDE_TESTBETRIEB", "1") != "0"
    benutzer = lies_benutzer(os.environ.get("MELDE_BENUTZER", ""))
    if not benutzer:
        if not testbetrieb:
            print("MELDE_BENUTZER ist nicht gesetzt. Im Echtbetrieb ist ohne Anmeldung kein Start möglich.", file=sys.stderr)
            return 2
        benutzer = {"testarzt": "test"}
        print("TESTBETRIEB: Anmeldung mit Benutzer 'testarzt' und Passwort 'test'.")
    try:
        pakete = standard_pakete()
    except PaketeFehlen as fehler:
        print(fehler, file=sys.stderr)
        return 2

    validator = FhirValidator(os.environ.get("VALIDATOR_URL"))
    prozess = None
    if not validator.ist_bereit():
        print("Starte den Meldungsprüfer (Validator), das dauert etwa 20 Sekunden ...")
        try:
            port = freier_port()
            prozess = starte_server(port)
            validator = FhirValidator(f"http://localhost:{port}")
        except ValidatorFehler as fehler:
            print(f"Warnung: {fehler} Die Vorschau ist nicht möglich.", file=sys.stderr)
            validator = None

    einstellungen = Einstellungen(benutzer=benutzer, melder=MELDER, konfig=KONFIG, testbetrieb=testbetrieb, cookie_sicher=os.environ.get("MELDE_COOKIE_SICHER") == "1")
    audit = Audit(Path(os.environ.get("MELDE_AUDIT_LOG", "data/audit.log")))
    app = erzeuge_app(erzeuge_kis_adapter(KisKonfig.aus_umgebung()), validator, pakete, audit, einstellungen)
    try:
        uvicorn.run(app, host=os.environ.get("MELDE_HOST", "127.0.0.1"), port=int(os.environ.get("MELDE_PORT", "8000")), access_log=False, log_level="info")
    finally:
        if prozess:
            prozess.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
