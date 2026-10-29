# PLAN – DEMIS-Meldeassistent

Stand: 28.10.2026 · Phase 0 (Recherche und Plan) · Kein Code, keine echten Patientendaten.

**Verlässlichkeit der Angaben.** Alles in diesem Dokument stammt aus den unten genannten
offiziellen Quellen, die am 28.10.2026 direkt gelesen wurden, **außer** was mit
**[UNGEPRÜFT]** markiert ist. Dort fehlte der Zugriff auf die Primärquelle (siehe
`OFFENE_FRAGEN.md`, Abschnitt 0).

## 1. Ziel
Ärztin/Arzt wählt Patient mit meldepflichtigem Befund → KIS-Daten werden automatisch übernommen →
Arzt ergänzt nur fehlende klinische Angaben (Ziel < 2 min) → Meldung wird validiert und
verschlüsselt an DEMIS (§ 6 IfSG) gesendet. Landesmeldungen nach SächsIfSMeldeVO laufen über
einen zweiten, konfigurierbaren Weg.

## 2. Wichtigste Erkenntnisse der Recherche (die den Plan prägen)

1. **Die Arztmeldung ist je Krankheit ein eigenes Profil.** Das Paket `rki.demis.disease` 3.0.0
   enthält für jede meldepflichtige Krankheit ein eigenes Meldeprofil mit festem Kürzel
   (z. B. `CDFD` = C. difficile schwere Verlaufsform, `MYTD` = Tuberkulose, `MSVD` = Masern).
   Es gibt keinen Freitext-Meldetatbestand.
2. **Nicht jeder klinische Fall ist über DEMIS meldbar.** Für saisonale Influenza, Norovirus und
   MRGN gibt es *keine* ärztliche DEMIS-Meldung (nur Laborprofile nach § 7, siehe Abschnitt 3).
   Häufungen nach § 6 Abs. 3 kennt DEMIS als Typ-Code (`6.3`), aber das Paket enthält dafür
   kein Profil. Influenza und der Tod bei MRGN fallen unter die sächsische Verordnung (Abschnitt 3);
   die Häufungsmeldung bleibt offen.
3. **Strikte Profilierung ist aktiv.** Seit 03.03.2026 gilt in Test und Produktion die strikte
   Profilierung (RKI-Hinweis auf der Vorabveröffentlichungs-Seite). Aktuell veröffentlicht:
   `rki.demis.common` 3.0.0 und `rki.demis.disease` 3.0.0 (FHIR 4.0.1, Abhängigkeit
   `de.basisprofil.r4` 1.5.4).
4. **Zertifikat für Krankenhäuser:** pro Einrichtung (IK-Nummer) eines; für Erkrankungsmeldungen
   (§ 6) ein **anderes** als für Laborbefunde (§ 7). Beantragung über die DEMIS-Geschäftsstelle
   (`demis-support@rki.de`, nicht `demis@rki.de`), Ausstellung über das CSM-Portal der
   Bundesdruckerei/D-Trust, Laufzeit 3 Jahre. Zusätzlich bekommt jedes Softwareprodukt eine eigene
   Client-ID/Passwort für den Token.
5. **Testumgebung:** Es gibt eine zentrale Live-Testumgebung (`test.demis.rki.de`); die frühere
   Docker-Testumgebung ist abgekündigt. Dort ist „Sender = Empfänger“ aktiv: gesendete Meldungen
   kann der Sender selbst wieder herunterladen. Nur Testdaten, keine personenbezogenen Daten.

## 3. Testfälle (Entscheidung des Chefarztes vom 28.10.2026) und ihr Meldeweg

Die sächsische Verordnung (SächsIfSMeldeVO vom 19.07.2024, Stand 28.10.2026, im Original gelesen) regelt:
- **§ 1 Abs. 1:** Über § 6 IfSG hinaus sind **Erkrankung und Tod** an 23 Krankheiten namentlich zu melden, u. a.
  **Influenza** (Nr. 9), **Clostridioides-difficile-Infektion mit toxinbildenden Stämmen** (Nr. 5, also nicht nur die schwere Verlaufsform), Legionellose,
  Borreliose, Herpes zoster, Malaria, Tetanus, Skabies, Shigellose, Listeriose.
- **§ 1 Abs. 2:** Meldepflichtig ist auch der **Tod infolge jeder anderen Infektionskrankheit** (außer AIDS), die weder in § 6 IfSG noch in § 1 Abs. 1 genannt ist.
- **§ 2 und § 3:** zusätzliche Erregernachweise für Labore (z. B. Pseudomonas aeruginosa mit Carbapenemasen). Das ist nicht unsere Aufgabe.

| # | Testfall | Meldeweg | Begründung (belegt) |
|---|---|---|---|
| 1 | C. difficile, schwerer Verlauf | **DEMIS** | `NotificationDiseaseCDFD` |
| 2 | Offene Lungen-TB | **DEMIS** | `NotificationDiseaseMYTD` (bei Therapieabbruch `MYBD`) |
| 3 | Masern-Verdacht | **DEMIS** | `NotificationDiseaseMSVD` |
| 4 | Influenza (saisonal) | **Sachsen** | DEMIS kennt nur zoonotische Influenza (`IZVD`); Sachsen § 1 Abs. 1 Nr. 9 |
| 5 | Norovirus-Ausbruchsverdacht (3 Patienten) | **Weder DEMIS-Profil noch Sachsen-Verordnung** | Häufung = § 6 Abs. 3 IfSG (Bundesrecht). DEMIS hat den Code `6.3`, aber kein Profil. Norovirus steht **nicht** in der SächsIfSMeldeVO. Das Landesformular hat jedoch die Zeile „zwei oder mehr nosokomiale Infektionen … (nichtnamentlich)“. Der Fall prüft den Zweig „kein automatischer Meldeweg“; vorgesehener Weg laut Formular: Landesformular (zu bestätigen) |
| 6 | MRGN-Nachweis, Patient verstorben | **Sachsen** | Tod infolge sonstiger Infektionskrankheit: § 1 Abs. 2. Der Erregernachweis selbst ist Laborsache (§ 7, `EBCP`/`ACBP`) |
| 7 | C. difficile, schwer, **verstorben** (neu) | **DEMIS** | wie Fall 1, zusätzlich `isDead = yes` und `deathDate` |

Regelwerk-Beispiel für Hygiene (zu bestätigen, siehe `OFFENE_FRAGEN.md`): C. difficile *schwer* → DEMIS;
toxinbildende CDI *ohne* schwere Verlaufsform → nur Sachsen (§ 1 Abs. 1 Nr. 5).

**Wichtig:** Die Annahme „Norovirus läuft über den Sachsen-Weg“ ist falsch. Fall 5 bleibt als Test der Rückfall-Logik und
als offene Frage an RKI/Gesundheitsamt.

## 4. Architektur

```
 ┌────────────┐  FHIR R4 (ISiK)   ┌───────────────┐
 │  NEXUS KIS │◄──────────────────│  KIS-Adapter  │  Schnittstelle `KisAdapter`
 │ (Test: HAPI)│  (später HL7 v2) │ (austauschbar)│  liefert NUR internes Modell
 └────────────┘                    └──────┬────────┘
                                          │ internes Datenmodell (pydantic)
                  ┌───────────────────────▼────────────────────────┐
                  │ Kern: Meldefall                                │
                  │  - Regelwerk (YAML): ICD-10-GM → Meldeweg(e)   │
                  │  - Pflichtfeld-/Bedingte-Felder-Logik          │
                  └───────┬───────────────────────────┬────────────┘
                          │                           │
              ┌───────────▼──────────┐     ┌──────────▼────────────┐
              │ DEMIS-Mapper         │     │ Sachsen-Mapper        │
              │ intern → FHIR-Bundle │     │ intern → PDF + JSON   │
              └───────────┬──────────┘     └──────────┬────────────┘
                          │                           │
              ┌───────────▼──────────┐     ┌──────────▼────────────┐
              │ FHIR-Validator (Java)│     │ Ablage (später KIM)   │
              │ + dt. Fehlertexte    │     │ Modul `Uebermittler`  │
              └───────────┬──────────┘     └───────────────────────┘
                          │ erst nach ärztlicher Freigabe UND Rückfrage an Projektleitung
              ┌───────────▼──────────┐
              │ DEMIS-Client         │  1. Token (mTLS, Realm HOSPITAL)
              │ (mTLS + Bearer-Token)│  2. POST …/$process-notification
              └──────────────────────┘     → Standard: Testumgebung
        Web-UI (FastAPI + Jinja2 + HTMX) bedient alle Schritte.
        Audit-Log: nur Vorgangs-ID, Zeit, Benutzer, Meldeweg, Status.
```

Kernprinzipien: (1) Rest der App kennt nur das interne Modell, nicht NEXUS. (2) Testumgebung ist
Default, Produktiv nur per ausdrücklicher Konfiguration. (3) Keine Gesundheitsdaten in Logs.
(4) Geheimnisse nur über Umgebungsvariablen/Secret-Datei außerhalb des Repos.

## 5. Aufbau einer DEMIS-Arztmeldung (belegt aus Paket 3.0.0 und Beispiel-Bundle)

Ein Meldevorgang ist ein FHIR-`Bundle` (Typ `document`, Profil `NotificationBundleDisease`) mit:

| Ressource | DEMIS-Profil | Zweck |
|---|---|---|
| Composition | `NotificationDisease<Kürzel>` | Meldung; Kategorie `6.1_2`; verweist auf alle Teile |
| Patient | `NotifiedPerson` | betroffene Person (Name, Geburtsdatum, Geschlecht, Adressen) |
| Organization | `NotifiedPersonFacility` | Einrichtung als Aufenthaltsort (hier: Klinik) |
| Condition | `Disease<Kürzel>` | Meldetatbestand, Verdacht/bestätigt, Beginn, Diagnosedatum |
| QuestionnaireResponse | `DiseaseInformationCommon` | übergreifende Angaben (Tod, Krankenhaus, Labor, Spende …) |
| QuestionnaireResponse | `DiseaseInformation<Kürzel>` | krankheitsspezifische Angaben |
| Encounter | `Hospitalization` | Krankenhausaufenthalt (Pflicht: Zeitraum; optional Fachabteilung, z. B. `3600` Intensivmedizin) |
| Immunization | `ImmunizationInformation<Kürzel>` | Impfung, falls vorhanden |
| PractitionerRole / Practitioner / Organization | `NotifierRole` / `Notifier` / `NotifierFacility` | meldende Person und Einrichtung |
| Organization | (Labor) | beauftragtes Labor |

Versand: `POST <Basis>/$process-notification` mit Bearer-Token; Antwort `200` mit
`OperationOutcome` und (bei Erfolg) Meldungsquittung als PDF; `422` = Validierungsfehler,
`403` = Token/Zertifikat ungültig, `503` = Wartung (Versand pausieren und später wiederholen).
Der Client soll einen `User-Agent` der Form `<Produkt>/<Version>` senden.

## 6. Datenfluss (Normalfall)
1. Arbeitsliste: Adapter liest Fälle/Diagnosen (ICD-10-GM) → Regelwerk markiert meldepflichtige.
2. Arzt öffnet Fall → Adapter liefert Patient, Fall, Station, Diagnosen, ggf. Labor.
3. Meldebogen wird vorbelegt; Felder farbig: *aus KIS* / *automatisch* / *Arzt ergänzt*.
4. Pflichtfeldprüfung → Vorschau → Erzeugung FHIR-Bundle → Validator → verständliche Fehler.
5. Freigabe → Versand (in der Entwicklung nur nach Rückfrage) → Quittung ablegen → Audit-Eintrag.

## 7. Ordnerstruktur (geplant)
```
demis-meldeassistent/
  PLAN.md  FELDMAPPING.md  OFFENE_FRAGEN.md  CHANGELOG.md  README.md (Phase 7)
  docker-compose.yml            # Schein-KIS (HAPI) + App
  config/  regelwerk.yaml  app.example.env
  src/meldeassistent/
    modell/        # internes Datenmodell
    kis/           # KisAdapter, isik_fhir.py, (hl7v2.py später)
    demis/         # mapper, validator, client
    sachsen/       # mapper, pdf, uebermittler
    web/           # FastAPI, Templates, HTMX
    audit.py  konfig.py
  testdaten/       # synthetische Patienten (FHIR-JSON)
  tests/
  tools/           # Download-Skripte für Validator und FHIR-Pakete
```

## 8. Technische Entscheidungen
| Thema | Entscheidung | Begründung / Prüfstand |
|---|---|---|
| Sprache | Python 3.12 (Docker-Image), FastAPI, httpx, pydantic | wie vorgeschlagen |
| FHIR-Modelle | **Bundle als JSON selbst bauen** (Python-Dicts/eigene pydantic-Modelle), Validierung ausschließlich durch den offiziellen Validator | `fhir.resources` 8.x liefert R4B/R5, DEMIS ist R4 (4.0.1). Abweichungen sind möglich; der Validator ist die Instanz, nicht die Bibliothek. Entscheidung in Phase 3 mit Test bestätigen |
| Validator | HL7-Validator (`validator_cli.jar`, aktuell 7.0.3, Download erreichbar) mit Paketen `rki.demis.common` 3.0.0, `rki.demis.disease` 3.0.0 | Terminologie (SNOMED für CDFD-Antworten): Erreichbarkeit eines Terminologieservers klären |
| KIS-Quelle | ISiK-Basismodul (4.0.3 und 3.1.1 verfügbar): `ISiKPatient`, `ISiKKontaktGesundheitseinrichtung`, `ISiKDiagnose` | welche ISiK-Stufe NEXUS im Haus liefert, ist offen |
| Frontend | Jinja2 + HTMX | schlicht, wartbar, keine Build-Kette |
| Schein-KIS | HAPI-FHIR im Docker (Docker 29.x, Docker Hub erreichbar) | |
| Labor | Zuerst manuell/FHIR-optional; Adapter erlaubt HL7-v2-ORU. Für ISiK gibt es ein eigenes Labormodul (`de.gematik.isik-labor`) | NEXUS-Labor-Schnittstelle offen |
| Konfiguration | Endpunkt-Basis und Profil-Version als Einstellung; Standard = Testumgebung | Endpunkte ändern sich (neue versionierte Pfade `v6/v7`) |

### Prüfung der Meldung in zwei Schichten (Stand Phase 3)

Jede Meldung wird vor dem Versand zweifach geprüft; beide Ergebnisse erscheinen gemeinsam auf Deutsch (`meldung.py`, `fehlertexte.py`):

1. **Offizieller HL7-Validator** (Java, Server-Modus, ca. 1 s je Meldung): Aufbau, Profile, Pflichtfelder, DEMIS-eigene Codes (Meldetatbestand, Einrichtungsart, Ja/Nein, Meldetyp), Geschlecht, Zeitangaben.
   Start ohne externen Terminologieserver (`-tx n/a`): Der öffentliche Server kennt die deutschen SNOMED-Erweiterungscodes nicht, und selbst die offiziellen RKI-Beispiele fielen dort durch.
2. **Eigener Fragebogen-Prüfer** (`fragebogen.py`): Pflichtfragen, Bedingungen (`enableWhen`), Antworttyp und Zugehörigkeit der Antwort zu den in den DEMIS-Wertemengen aufgezählten Antworten (SNOMED, Länder, Regionen). Er wurde gegen die offiziellen Beispiele geprüft.
   Im **strengen Modus** meldet er zusätzlich Fragen, die noch auf „nicht erhoben“ (NASK) stehen: DEMIS erlaubt das formal, der Meldeassistent verlangt aber eine aktive Antwort.

Das Ergebnis trennt `fehler` (DEMIS würde ablehnen), `offen` (noch nicht beantwortet) und `hinweis`.

### Oberfläche (Stand Phase 4)

Serverseitig gerendert (FastAPI + Jinja2 + HTMX, HTMX lokal ausgeliefert, keine externen Ressourcen). Ablauf:

1. **Anmeldung** (Testbetrieb: einfache Test-Anmeldung; Echtbetrieb: LDAP/AD in Phase 7), serverseitige Sitzung, Sperre nach 5 Fehlversuchen, Zeitüberschreitung.
2. **Arbeitsliste** der meldepflichtigen Befunde mit Meldeweg je Fall (DEMIS / Landesmeldung Sachsen / Klärung nötig), nach vorläufigem Regelwerk (`regelwerk.py`, Phase 6: YAML).
3. **Meldebogen** (nur für DEMIS-Fälle): KIS-Daten oben, darunter die Fragen des offiziellen DEMIS-Fragebogens. Farbliche **und** textliche Kennzeichnung je Angabe
   (*aus KIS* / *Vorschlag – bitte bestätigen* / *von Ihnen* / *offen*). Folgefragen erscheinen und verschwinden nach den Bedingungen des Fragebogens (HTMX, ohne Seitenwechsel).
   Rechts der **Stand**: was noch offen ist (mit Sprungmarken), erst bei „alles beantwortet“ geht es zur Vorschau.
4. **Vorschau**: Zeigt, was tatsächlich gesendet wird (aus dem fertigen Bundle gebaut). Hier läuft die volle Prüfung mit dem Validator.
5. **Freigabe**: In Phase 4 **ohne Versand** (Audit-Eintrag `freigegeben_ohne_versand`). Der Versand folgt in Phase 5 nach Rückfrage und mit Testzertifikat.

Datenschutz in der Oberfläche: Entwürfe nur im Arbeitsspeicher (nach Freigabe, Verwerfen oder Zeitablauf gelöscht); Fälle in Adressen nur über zufällige Kennungen (nie KIS-IDs);
Serverprotokoll enthält nur Adressmuster, keine Kennungen oder Inhalte; Audit-Log nur Vorgangs-ID, Zeit, Benutzer, Meldeweg, Status, Dauer; `Cache-Control: no-store`,
strikte Content-Security-Policy, CSRF-Schutz, Cookie `HttpOnly` und `SameSite=Strict`.

## 9. Quellen (am 28.10.2026 gelesen)
- RKI-Vorabveröffentlichung: `https://robert-koch-institut.github.io/DEMIS_FHIR-Profile_Vorabveroeffentlichung/` (Repository per `git clone` gelesen, Stand 20.04.2026)
- FHIR-Pakete: `https://packages2.fhir.org/packages/rki.demis.disease` und `…/rki.demis.common` (Version 3.0.0)
- ISiK: Paket `de.gematik.isik-basismodul` 4.0.3 und 3.1.1 vom selben Paketserver
- gematik DEMIS-Wissensdatenbank (`wiki.gematik.de/spaces/DSKB`): Seiten „Endpunkte, Zertifikate, User und Passwort“,
  „Informationen zur DEMIS-Testumgebung“, „Beantragung eines DEMIS-Zertifikats zur Authentisierung“,
  „Nutzung der FHIR-Schnittstelle als Sender“, „Anbindungsoptionen für Krankenhäuser“, „Testmöglichkeiten“
- Sachsen: SächsIfSMeldeVO vom 19.07.2024, Stand 28.10.2026, `https://revosax.sachsen.de/vorschrift_gesamt/20989/47393.html`
- Landesformular „Arzt-Meldeformular“ (Stand 08/2024): vom Auftraggeber bereitgestellt, abgelegt in `vorlagen/LUA-HM-Arzt-Meldebogen.pdf`
- **Nicht lesbar (gesperrt):** ISiK-Spezifikationsseite `gemspec.gematik.de`. `tx.fhir.org` und `www.bfarm.de` sind inzwischen freigegeben

## 10. Phasenplan
Phase 0 Recherche/Plan → 1 Schein-KIS → 2 KIS-Adapter → 3 Mapping+Validator → 4 Oberfläche →
5 DEMIS-Test (Stopp: Zertifikat) → 6 Sachsen-Weg → 7 Übergabe.

## 11. Risiken
- DEMIS-Profile und Endpunkte ändern sich (strikte Profilierung, neue API-Pfade) → Version als Konfiguration, `WARTUNG.md`.
- Der Anteil der ärztlich über DEMIS meldbaren Fälle ist kleiner als im Papierformular. Der Assistent muss
  „nicht über DEMIS meldbar“ klar anzeigen und den Alternativweg anbieten.
- Mehrere Felder des Papierformulars haben in DEMIS keine Entsprechung (siehe `FELDMAPPING.md`).
- NEXUS-FHIR evtl. nur eingeschränkt (Labor) → Adapter-Abstraktion.
- Haftung/Regulatorik: Vorschau und ärztliche Freigabe sind Pflicht, kein Auto-Versand.
