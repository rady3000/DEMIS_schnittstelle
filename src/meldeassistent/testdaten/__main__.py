"""Aufruf:  python -m meldeassistent.testdaten [--erzeugen | --einspielen | --pruefen]"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .einspielen import STANDARD_URL, FremderServerFehler, schreibe_dateien, spiele_ein, zaehle_fremde_ressourcen
from .uebersicht_html import schreibe_html


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetische Testfälle für das Schein-KIS")
    gruppe = parser.add_mutually_exclusive_group(required=True)
    gruppe.add_argument("--erzeugen", action="store_true", help="JSON-Dateien in testdaten/ schreiben")
    gruppe.add_argument("--einspielen", action="store_true", help="Testfälle in das Schein-KIS laden")
    gruppe.add_argument("--pruefen", action="store_true", help="prüfen, dass im Server nur synthetische Patienten liegen")
    gruppe.add_argument("--uebersicht", action="store_true", help="lesbare HTML-Übersicht docs/testfaelle.html schreiben")
    parser.add_argument("--server", default=os.environ.get("FHIR_BASIS_URL", STANDARD_URL), help=f"FHIR-Basis-URL (Standard: {STANDARD_URL})")
    parser.add_argument("--ordner", default="testdaten", help="Zielordner für --erzeugen")
    parser.add_argument("--erlaube-fremden-server", action="store_true", help="auch Nicht-Localhost-Ziele zulassen (Vorsicht!)")
    args = parser.parse_args()

    try:
        if args.erzeugen:
            for pfad in schreibe_dateien(Path(args.ordner)):
                print("geschrieben:", pfad)
        elif args.uebersicht:
            print("geschrieben:", schreibe_html(Path("docs") / "testfaelle.html"))
        elif args.einspielen:
            for name, anzahl in spiele_ein(args.server, args.erlaube_fremden_server).items():
                print(f"{name}: {anzahl} Ressourcen")
        else:
            fremd = zaehle_fremde_ressourcen(args.server)
            print(f"Patienten ohne Tag SYNTHETISCH: {fremd}")
            return 0 if fremd == 0 else 1
    except FremderServerFehler as fehler:
        print("ABGEBROCHEN:", fehler, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
