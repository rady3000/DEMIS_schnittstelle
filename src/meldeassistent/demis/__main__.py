"""Kommandozeilenwerkzeug: baut eine Demo-Meldung aus dem Schein-KIS und prüft sie.

    python -m meldeassistent.demis --fall cdi            # cdi | tb | masern | cdi_tot
    python -m meldeassistent.demis --fall cdi --streng   # unbeantwortete Fragen als "offen" melden

Es wird NICHTS gesendet (Harte Regel 6). Die Meldung wird nur gebaut, geprüft und optional als JSON
gespeichert. Alle Daten sind synthetisch.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from meldeassistent.demis.mapper import MeldungNichtMoeglich, erzeuge_meldung
from meldeassistent.demis.meldung import pruefe_meldung
from meldeassistent.demis.validator import FhirValidator, ValidatorFehler, freier_port, starte_server
from meldeassistent.konfig import KisKonfig, erzeuge_kis_adapter
from meldeassistent.testdaten.demo_meldung import FAELLE, KONFIG, MELDER, demo_angaben


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Demo-Meldung aus dem Schein-KIS bauen und prüfen (sendet nichts)")
    parser.add_argument("--fall", choices=sorted(FAELLE), required=True)
    parser.add_argument("--streng", action="store_true", help="unbeantwortete Fragen als 'offen' melden")
    parser.add_argument("--ausgabe", help="Meldung als JSON-Datei speichern")
    parser.add_argument("--validator-url", help="laufender Validator (Standard: wird bei Bedarf selbst gestartet)")
    args = parser.parse_args(argv)

    fall_id, _ = FAELLE[args.fall]
    adapter = erzeuge_kis_adapter(KisKonfig.aus_umgebung())
    fall = adapter.lade_fall(fall_id)
    angaben = demo_angaben(fall, args.fall)
    try:
        bundle = erzeuge_meldung(fall, angaben, MELDER, KONFIG, jetzt=datetime.now().astimezone())
    except MeldungNichtMoeglich as fehler:
        print(f"Meldung nicht möglich: {fehler}")
        return 2
    if args.ausgabe:
        Path(args.ausgabe).write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Meldung gespeichert: {args.ausgabe}")

    prozess = None
    try:
        pruefer = FhirValidator(args.validator_url)
        if not pruefer.ist_bereit():
            print("Starte den Meldungsprüfer (dauert etwa 20 Sekunden) ...")
            port = freier_port()
            prozess = starte_server(port)
            pruefer = FhirValidator(f"http://localhost:{port}")
        ergebnis = pruefe_meldung(bundle, pruefer, streng=args.streng)
    except ValidatorFehler as fehler:
        print(f"Prüfung nicht möglich: {fehler}")
        return 3
    finally:
        if prozess:
            prozess.terminate()

    print(f"\nMeldetatbestand: {angaben.kuerzel}  |  Fehler: {len(ergebnis.fehler)}  |  Noch offen: {len(ergebnis.offen)}  |  Hinweise: {len(ergebnis.hinweise)}")
    for p in ergebnis.probleme:
        print(f"  [{p.schwere.upper()}] {p}")
    print("\nErgebnis:", "bereit zum Senden (formal gültig)" if ergebnis.ok else "NICHT sendefähig")
    print("(Es wurde nichts gesendet.)")
    return 0 if ergebnis.ok else 1


if __name__ == "__main__":
    sys.exit(main())
