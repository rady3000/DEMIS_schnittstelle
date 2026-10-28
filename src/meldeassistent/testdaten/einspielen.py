"""Spielt die synthetischen Testfälle in das Schein-KIS (HAPI-FHIR) ein.

Sicherheitsgurte (Harte Regeln 1 und 2):
- Standardziel ist ein lokaler Server. Ein anderer Rechner wird nur mit ``erlaube_fremden_server=True``
  angesprochen, damit die Testdaten nie versehentlich in ein echtes KIS gelangen.
- Alle Ressourcen tragen das Tag SYNTHETISCH (siehe faelle.py).
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .faelle import TAG_SYSTEM, alle_faelle, stammdaten, transaktions_bundle

STANDARD_URL = "http://localhost:8080/fhir"
LOKALE_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


class FremderServerFehler(RuntimeError):
    """Das Ziel ist kein lokaler Server und wurde nicht ausdrücklich erlaubt."""


def pruefe_ziel(basis_url: str, erlaube_fremden_server: bool = False) -> None:
    host = urlparse(basis_url).hostname or ""
    if host not in LOKALE_HOSTS and not erlaube_fremden_server:
        raise FremderServerFehler(
            f"'{host}' ist kein lokaler Server. Testdaten werden nur lokal eingespielt, "
            "damit sie nie in ein echtes KIS gelangen. Nur wenn Sie sicher sind: --erlaube-fremden-server."
        )


def bundles() -> list[tuple[str, dict]]:
    """Alle Transaktions-Bundles in Einspiel-Reihenfolge: zuerst Stammdaten, dann die Fälle."""
    ergebnis = [("00-stammdaten", transaktions_bundle(stammdaten()))]
    for fall in alle_faelle():
        ergebnis.append((fall.schluessel, transaktions_bundle(fall.ressourcen())))
    return ergebnis


def uebersicht() -> list[dict]:
    """Erwartungen je Fall (für Tests und zur Ansicht). Kein Teil der FHIR-Daten."""
    return [
        {
            "fall": f.schluessel,
            "titel": f.titel,
            "erwarteter_meldeweg": f.erwarteter_weg,
            "erwartetes_demis_profil": f.erwartetes_demis_profil,
            "begruendung": f.begruendung,
            "anzahl_patienten": len(f.personen),
        }
        for f in alle_faelle()
    ]


def schreibe_dateien(zielordner: Path) -> list[Path]:
    """Schreibt die Bundles als JSON-Dateien (zum Ansehen und für die Versionsverwaltung)."""
    zielordner.mkdir(parents=True, exist_ok=True)
    geschrieben = []
    for name, bundle in bundles():
        pfad = zielordner / f"{name}.json"
        pfad.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        geschrieben.append(pfad)
    pfad = zielordner / "uebersicht.json"
    pfad.write_text(json.dumps(uebersicht(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    geschrieben.append(pfad)
    return geschrieben


def spiele_ein(basis_url: str = STANDARD_URL, erlaube_fremden_server: bool = False, client: httpx.Client | None = None) -> dict[str, int]:
    """Sendet alle Bundles an den Server. Gibt je Bundle die Anzahl angelegter/aktualisierter Ressourcen zurück."""
    pruefe_ziel(basis_url, erlaube_fremden_server)
    eigener_client = client is None
    client = client or httpx.Client(timeout=60)
    try:
        ergebnis: dict[str, int] = {}
        for name, bundle in bundles():
            antwort = client.post(basis_url, json=bundle, headers={"Content-Type": "application/fhir+json"})
            if antwort.status_code >= 300:
                raise RuntimeError(f"Bundle {name}: HTTP {antwort.status_code}: {antwort.text[:500]}")
            ergebnis[name] = len(antwort.json().get("entry", []))
        return ergebnis
    finally:
        if eigener_client:
            client.close()


def zaehle_fremde_ressourcen(basis_url: str = STANDARD_URL, client: httpx.Client | None = None) -> int:
    """Prüft, ob Patienten OHNE das Tag SYNTHETISCH im Server liegen (sollte 0 sein)."""
    pruefe_ziel(basis_url, True)  # nur lesen
    eigener_client = client is None
    client = client or httpx.Client(timeout=60)
    try:
        alle = client.get(f"{basis_url}/Patient", params={"_summary": "count"}).json()["total"]
        markiert = client.get(
            f"{basis_url}/Patient", params={"_tag": f"{TAG_SYSTEM}|SYNTHETISCH", "_summary": "count"}
        ).json()["total"]
        return alle - markiert
    finally:
        if eigener_client:
            client.close()
