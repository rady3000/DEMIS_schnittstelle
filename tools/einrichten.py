#!/usr/bin/env python3
"""Lädt den FHIR-Validator und die DEMIS-Pakete (mit festen Prüfsummen) in den Projektordner.

Aufruf:  python tools/einrichten.py

Was geladen wird (alles öffentlich und kostenlos):
- tools/validator_cli.jar        Offizieller HL7-FHIR-Validator (Version 7.0.3)
- .fhir/pakete/*.tgz             DEMIS-Profile (RKI) und die Pakete, von denen sie abhängen

Die Dateien werden NICHT in das Repository eingecheckt (siehe .gitignore). Jede Datei wird gegen
eine feste SHA-256-Prüfsumme geprüft: Stimmt sie nicht, wird sie verworfen. So kann niemand
unbemerkt andere Profile oder einen manipulierten Validator unterschieben.

Neue Profilversionen einspielen: siehe WARTUNG.md (Version und Prüfsumme hier anpassen).
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent

# (Zieldatei, Quelle, SHA-256)
DATEIEN = [
    (
        "tools/validator_cli.jar",
        "https://github.com/hapifhir/org.hl7.fhir.core/releases/download/7.0.3/validator_cli.jar",
        "57aa43fb40cec5de41def81c927725fd85908eeb71509b7f9313e04d9b8ec79b",
    ),
    (
        ".fhir/pakete/rki.demis.common-3.0.0.tgz",
        "https://packages2.fhir.org/packages/rki.demis.common/3.0.0",
        "5fe20da7a5aeef8f849a460d7948e28d52eabf4819065f582300b15c157066f2",
    ),
    (
        ".fhir/pakete/rki.demis.disease-3.0.0.tgz",
        "https://packages2.fhir.org/packages/rki.demis.disease/3.0.0",
        "de69cc67e78ab1220ef581128ec5f2295d1e3dacfe11dbed8cd1fc2c01cc69eb",
    ),
    (
        ".fhir/pakete/de.basisprofil.r4-1.5.4.tgz",
        "https://packages2.fhir.org/packages/de.basisprofil.r4/1.5.4",
        "9dc5392b5471060db07cf8ace2e8c81e99e3cee1e89f0b5febad362561fb739f",
    ),
    (
        # Enthält die HL7-Codesystem-Version 0.5.0, die DEMIS in seinen Wertemengen festlegt
        ".fhir/pakete/hl7.terminology.r4-4.0.0.tgz",
        "https://packages2.fhir.org/packages/hl7.terminology.r4/4.0.0",
        "5f74165a412cf4bd2c9b742efc9553c54749306921e832b12da6043012768c8b",
    ),
]


def sha256(pfad: Path) -> str:
    h = hashlib.sha256()
    with pfad.open("rb") as datei:
        for block in iter(lambda: datei.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    fehler = 0
    for ziel_name, quelle, erwartet in DATEIEN:
        ziel = PROJEKT / ziel_name
        if ziel.exists() and sha256(ziel) == erwartet:
            print(f"vorhanden und geprüft: {ziel_name}")
            continue
        print(f"lade {ziel_name} ...")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        temporaer = ziel.with_suffix(ziel.suffix + ".teil")
        try:
            with urllib.request.urlopen(quelle, timeout=300) as antwort, temporaer.open("wb") as datei:
                while block := antwort.read(1 << 20):
                    datei.write(block)
        except OSError as problem:
            print(f"  FEHLER beim Laden: {problem}")
            temporaer.unlink(missing_ok=True)
            fehler += 1
            continue
        if sha256(temporaer) != erwartet:
            print("  FEHLER: Prüfsumme stimmt nicht, Datei verworfen.")
            temporaer.unlink(missing_ok=True)
            fehler += 1
            continue
        temporaer.replace(ziel)
        print("  ok")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
