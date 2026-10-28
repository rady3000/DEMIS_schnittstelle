# Changelog

## [Unveröffentlicht]

### Phase 2 – KIS-Adapter (abgeschlossen, 28.10.2026)
- Internes Datenmodell `meldeassistent.modell` (pydantic, unveränderlich): Patient, Aufenthalt mit Abschnitten, Diagnose, Laborbefund, KisFall, FallUebersicht.
  Grundsatz: Was das KIS nicht liefert, bleibt leer bzw. „unbekannt“ (z. B. fehlende Todesangabe ist nicht „nein“).
- Schnittstelle `KisAdapter` (`liste_faelle`, `lade_fall`, `pruefe_verbindung`) mit verständlichen Fehlerklassen ohne Gesundheitsdaten.
- `IsikFhirAdapter` (ISiK/FHIR R4) und `isik_mapper` (reine Übersetzungsfunktionen). Seitenweises Lesen, Schutz vor Folgelinks auf fremde Server,
  Prüfung der FHIR-IDs, Hinweise auf Lücken in den KIS-Daten (`KisFall.hinweise`).
- `konfig.py`: Einstellung über Umgebungsvariablen `KIS_FHIR_BASIS_URL` (Standard: lokales Schein-KIS), `KIS_FHIR_TOKEN`, `KIS_FHIR_TIMEOUT`.
- Datenschutz: HTTP-Bibliothek protokolliert keine URLs mehr; Test stellt sicher, dass Logs weder Namen, Diagnosen noch IDs enthalten.
- Tests: 119 grün. Dieselben Prüfungen laufen gegen einen eingebauten Fake-Server und gegen das echte Schein-KIS (HAPI);
  zusätzlich Mapper-Sonderfälle, Fehlerverhalten, Datenschutz und Architekturgrenze. Mutationsprüfung: absichtliche Fehler werden erkannt.

### Phase 1 – Schein-KIS (abgeschlossen, 28.10.2026)
- `docker-compose.yml`: HAPI-FHIR `v8.12.0-2` (FHIR R4) als Schein-KIS, nur an `127.0.0.1:8080` gebunden, Datenhaltung im Arbeitsspeicher.
- `docker-compose.sandbox.yml`: nur für die Cloud-Entwicklungsumgebung (Docker ohne Netzwerkbrücke).
- Synthetische Testdaten (`src/meldeassistent/testdaten/`): 7 Testfälle, 9 Patienten, ISiK-Basismodul (Patient, Kontakt, Diagnose, Organisation, Standort), vereinfachte Laborbefunde.
- Einspiel-Skript `python -m meldeassistent.testdaten`: `--erzeugen`, `--einspielen`, `--pruefen`, `--uebersicht`. Wiederholbar (feste IDs, keine Duplikate).
  Schutz: nur lokale Ziele, alles Tag `SYNTHETISCH`, Prüfung auf fremde Patienten.
- 28 Tests grün (davon 1 gegen das laufende Schein-KIS), `docs/testfaelle.html` als lesbare Übersicht.
- Entscheidungen/Funde: Docker Hub lieferte dauerhaft HTTP 429, Image über `mirror.gcr.io` geladen; das Image hat keine Shell (kein healthcheck);
  H2-Datei im Volume scheiterte an Dateirechten, deshalb Arbeitsspeicher-Datenbank.
- Offen: ICD-10-GM-Codes der Testdaten nicht gegen BfArM geprüft (Server gesperrt).

### Phase 0 – Recherche und Plan (abgeschlossen, 28.10.2026)
- Projektgerüst und `.gitignore` angelegt (Zertifikate, Schlüssel, Meldeinhalte ausgeschlossen).
- Offizielle Quellen gelesen: RKI-Profile (`rki.demis.common` 3.0.0, `rki.demis.disease` 3.0.0),
  ISiK-Basismodul 4.0.3, gematik DEMIS-Wissensdatenbank (Endpunkte, Testumgebung, Zertifikate).
- `PLAN.md`: Architektur, Aufbau der DEMIS-Arztmeldung, Einordnung der sechs Testfälle, Quellenverzeichnis.
- `FELDMAPPING.md`: Formularfeld → ISiK → DEMIS-Profil/Fragebogen, inklusive Feldern ohne DEMIS-Ziel.
- `OFFENE_FRAGEN.md`: Fragen an DEMIS-Support, NEXUS, IT, Gesundheitsamt, Projektleitung.
- SächsIfSMeldeVO (19.07.2024, Stand 28.10.2026) im Original gelesen; Sachsen-Angaben in `PLAN.md` und `FELDMAPPING.md` belegt.
- Testfälle festgelegt: 7 Fälle (3× DEMIS, 1× DEMIS mit Todesfolge, Influenza und MRGN über Sachsen, Norovirus als Rückfallzweig).
- Korrektur: Norovirus fällt nicht unter die sächsische Verordnung.
- Landesformular vom Auftraggeber bereitgestellt (`vorlagen/LUA-HM-Arzt-Meldebogen.pdf`) und ins Feldmapping eingearbeitet (V/E/T-Matrix, § 6 Abs. 3 im Formular).
