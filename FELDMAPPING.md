# FELDMAPPING – Papierformular → KIS (ISiK) → DEMIS

Stand: 28.10.2026 · Basis: `rki.demis.common` 3.0.0, `rki.demis.disease` 3.0.0, ISiK-Basismodul 4.0.3.
Alle DEMIS-Angaben sind den Profilen und Fragebögen des Pakets entnommen (Beispiel-Bundles für CDFD, MYTD, MSVD geprüft).
Was nicht geprüft werden konnte, ist mit **[UNGEPRÜFT]** markiert.

**Legende**
- *Wer füllt:* **KIS** = automatisch aus dem KIS · **Auto** = Konfiguration/berechnet · **Arzt** = Eingabe/Auswahl · **–** = kein Ziel in DEMIS
- *Pflicht:* DEMIS-Pflicht laut Profil. „bed.“ = nur wenn eine andere Angabe es auslöst. „Frage Pflicht“ = die Frage muss beantwortet werden, zulässig sind auch „Nicht erhoben“ (`NASK`) / „Nicht ermittelbar“ (`ASKU`).
- Kürzel `QR:` = Antwort (`linkId`) im Fragebogen `DiseaseInformationCommon` bzw. krankheitsspezifisch.

## A. Patient

| Formularfeld | KIS-Quelle (ISiK 4.0.3) | DEMIS-Ziel | Pflicht | Wer füllt |
|---|---|---|---|---|
| Name, Vorname | `ISiKPatient.name:Name` (`use=official`) `.family`, `.given` | `NotifiedPerson.name` (genau 1) `.family`, `.given` | **Pflicht** (beide) | KIS |
| Geburtsdatum | `Patient.birthDate` | `NotifiedPerson.birthDate` (Prüfregel `validBirthDate`) | optional im Profil, in der Praxis immer senden | KIS |
| Geschlecht | `Patient.gender` + Erweiterung `gender-amtlich-de` | `NotifiedPerson.gender` + gleiche Erweiterung | **Pflicht** | KIS |
| Wohnsitz | `Patient.address:Strassenanschrift` (Straße/Nr., PLZ, Ort) | `NotifiedPerson.address` (bis 3 Adressen, `line` bis 3, `postalCode`, `city`, `country`) mit Pflicht-Erweiterung `AddressUse` = `primary` (Hauptwohnsitz) / `ordinary` (gewöhnlicher Aufenthalt) | Adresse optional; wenn vorhanden `AddressUse` **Pflicht** | KIS + Auto (`AddressUse`), Arzt bestätigt |
| Aufenthaltsort (hier: Klinik) | Klinik: Konfiguration; Station/Zimmer: `ISiKKontaktGesundheitseinrichtung.location` | zusätzliche `NotifiedPerson.address` mit `AddressUse` = `current` und Erweiterung `FacilityAddressNotifiedPerson` → Ressource `NotifiedPersonFacility` (Name, Typ `medFacility`, Adresse) | optional | Auto |
| Kontakt (Telefon, E-Mail) | `Patient.telecom` (`system`, `value`) | `NotifiedPerson.telecom` (Slices `Email`, `Phone`, mit Kommentar-Erweiterung) | optional | KIS, Arzt ergänzt |
| Gestorben am / Verstorben | `Patient.deceased[x]` (Basis-FHIR, in ISiK nicht eigens profiliert) **[UNGEPRÜFT: ob NEXUS es füllt]** | `QR(Common): isDead` (Frage Pflicht, Vorbelegung `NASK`) und `deathDate` (optional, nur bei `isDead = yes`) | `isDead` **Pflicht** | KIS + Arzt bestätigt |
| Geburtsland, Staatsangehörigkeit, Einreisejahr | nicht im ISiK-Basismodul | `QR(MYTD/HBVD/HCVD): countryOfBirth`, `nationality` (beide Pflicht), `yearOfEntry` (bed.: Geburtsland ≠ DE) | nur bei TB, Hepatitis B, Hepatitis C **Pflicht**; sonst **kein Ziel** | Arzt |
| Tätigkeit / Arbeitsstelle (§§ 23, 35, 36, 42 IfSG; Betreuung in Gemeinschaftseinrichtung) | nicht im KIS | `QR(Common): infectProtectFacility` (Frage Pflicht) mit Gruppe: Art, Beginn, Ende, **Beziehung** (`organizationAssociation`, Pflicht wenn ja), **Einrichtung** (Pflicht wenn ja, eigene Organization) | Frage **Pflicht** | Arzt |
| Berufliche Exposition (Hepatitis E, Hantavirus) | nicht im KIS | `QR(HEVD/HTVD): infectionRiskKindJob` | krankheitsabhängig | Arzt |

## B. Erkrankung

| Formularfeld | KIS-Quelle (ISiK 4.0.3) | DEMIS-Ziel | Pflicht | Wer füllt |
|---|---|---|---|---|
| Krankheit/Erreger | `ISiKDiagnose.code` (ICD-10-GM, Slice `ICD-10-GM`) → Zuordnung über Regelwerk-YAML | Auswahl des **Profils** `NotificationDisease<Kürzel>` und `Disease<Kürzel>.code` (fester Code aus `notificationDiseaseCategory`, z. B. `cdfd`, `mytd`, `msvd`) | **Pflicht** | Auto (Regelwerk), Arzt bestätigt |
| Erkrankung / Verdacht | `ISiKDiagnose` (Diagnosesicherheit-Erweiterung am Coding) | `Disease.verificationStatus` (Wertemenge `verificationStatus`: `confirmed` = bestätigt, `unconfirmed` = Verdacht; zusätzlich `refuted`, `entered-in-error`) | **Pflicht** | KIS + Arzt bestätigt |
| Tod | siehe „Gestorben am“ oben | `QR(Common): isDead`, `deathDate` | **Pflicht** (`isDead`) | KIS + Arzt |
| erkrankt am | `ISiKDiagnose.onset[x]` | `Disease.onsetDateTime` | optional | KIS, Arzt ergänzt |
| Diagnosedatum | `ISiKDiagnose.recordedDate` (Pflicht in ISiK) | `Disease.recordedDate` | optional | KIS |
| Diagnosehinweise | `ISiKDiagnose.note` | `Disease.note` | optional | KIS/Arzt |
| Symptome | Nebendiagnosen / Freitext | **kein Ziel** im allgemeinen Teil (nur krankheitsspezifisch, z. B. `skinSymptomBegin` bei Mpox, `onsetOfExanthem` bei Masern) | – | Arzt (nur für Landesmeldung/PDF) |
| erste Arztkonsultation | nicht im KIS | **kein Ziel** in DEMIS | – | Arzt (nur Landesmeldung/PDF) |
| Ausbruch zugeordnet | – | `QR(krankheitsspezifisch): outbreak` (Frage Pflicht), `outbreakNote`, `outbreakNotificationId` | Frage **Pflicht** (CDFD, MYTD, MSVD) | Arzt |

## C. Krankenhaus / Verlauf

| Formularfeld | KIS-Quelle (ISiK 4.0.3) | DEMIS-Ziel | Pflicht | Wer füllt |
|---|---|---|---|---|
| Krankenhauseinweisung ja/nein | Existenz eines `ISiKKontaktGesundheitseinrichtung` (`class` stationär) | `QR(Common): hospitalized` (Frage Pflicht) | **Pflicht** | KIS |
| Einweisungsdatum | `Encounter.period.start` | `Hospitalization.period.start` (Pflicht), verlinkt über `QR(Common): hospitalizedEncounter` | **Pflicht** (wenn hospitalisiert) | KIS |
| Entlassung | `Encounter.period.end`, `hospitalization.dischargeDisposition` | `Hospitalization.period.end` | optional | KIS |
| Intensivstation (ITS) | `Encounter.serviceType` (Fachabteilungsschlüssel, z. B. `3600` = Intensivmedizin) | `Hospitalization.serviceType` (Codesystem `hospitalizationServiceType`, enthält `3600 Intensivmedizin`). Es gibt kein eigenes ITS-Feld; die Information liegt nur in der Fachabteilung. **Offen:** ob mehrere Abschnitte (Normalstation → ITS) als mehrere `Hospitalization`-Ressourcen zu senden sind (siehe `OFFENE_FRAGEN.md`) | optional (wenn vorhanden: Code Pflicht) | KIS |
| Fachabteilung / Station | `Encounter.serviceType` (Fachabteilungsschlüssel) / Standort | `Hospitalization.serviceType` (Beispiel im Paket: `3700 Sonstige Fachabteilung`; Aufnahme als `class = IMP`) | optional | KIS |
| Hospitalisierungsgrund | – | `Hospitalization.reasonCode`: `becauseOfDisease`, `becauseOfOtherReason`, `forIsolation` | optional | Arzt |
| abgesondert (Isolierung) | nicht im KIS | nur indirekt über `reasonCode = forIsolation` | optional | Arzt |
| Beatmungspflicht | nicht im KIS-Basismodul | **kein Ziel** in `DiseaseInformationCommon` und in CDFD/MYTD/MSVD | – | Arzt (nur Landesmeldung/PDF) |
| Krankenhaus (Aufnahme-Einrichtung) | Konfiguration | `Hospitalization.serviceProvider` (Referenz auf eine Organization; im Paketbeispiel vorhanden) | optional | Auto |

## D. Labor

| Formularfeld | KIS-Quelle | DEMIS-Ziel | Pflicht | Wer füllt |
|---|---|---|---|---|
| Labor beauftragt ja/nein | Laborauftrag (HL7 v2 / FHIR `ServiceRequest`) **[UNGEPRÜFT: NEXUS]** | `QR(Common): labSpecimenTaken` (Frage Pflicht) | **Pflicht** | KIS (sonst Arzt) |
| Labor (Name, Adresse) | Konfiguration/Laborstamm | `QR(Common): labSpecimenLab` → `Organization` (Pflicht wenn ja) | bed. | Auto/Arzt |
| Labordatum, Labornummer | Laborbefund (`DiagnosticReport`/ORU) | **kein Ziel** in der Arztmeldung (der Erregernachweis wird vom Labor selbst nach § 7 gemeldet) | – | KIS (nur Landesmeldung/PDF) |
| Nachweismethode | – | `QR(CDFD): method` (Pflicht, SNOMED-Antwort) | CDFD **Pflicht** | Arzt |
| Erfüllung schwere Verlaufsform | – | `QR(CDFD): form` (Pflicht, SNOMED-Antwort) | CDFD **Pflicht** | Arzt |

## E. Epidemiologie / Zusatz

| Formularfeld | KIS-Quelle | DEMIS-Ziel | Pflicht | Wer füllt |
|---|---|---|---|---|
| Impfstatus (nur impfpräventable Krankheiten) | `Immunization` falls im KIS **[UNGEPRÜFT]** | `QR(krankheitsspezifisch): immunization` (Frage Pflicht) + `immunizationRef` → Ressource `ImmunizationInformation<Kürzel>` (Impfstoff, Datum, Indikation `S/A/I/B/R`) | Frage **Pflicht** (CDFD, MYTD, MSVD u. a.) | KIS/Arzt |
| Blut-/Organspende in den letzten 6 Monaten | nicht im KIS | `QR(Common): organDonation` | Frage **Pflicht** | Arzt |
| Zugehörigkeit zur Bundeswehr | nicht im KIS | `QR(Common): militaryAffiliation` | Frage **Pflicht** | Arzt (nicht im Papierformular) |
| Wahrscheinlicher Expositionsort / Auslandsaufenthalt | – | `QR(Common): placeExposure` (Frage Pflicht) mit Beginn, Ende, Region (Pflicht wenn ja), Anmerkung | Frage **Pflicht** | Arzt |
| Schwangerschaft (Masern, Röteln, zoonot. Influenza) | `ISiKSchwangerschaftsstatus` | `QR(MSVD): pregnancy` (Pflicht), `pregnancyWeek` (Pflicht wenn ja) | MSVD **Pflicht** | KIS + Arzt |
| Exanthembeginn (Masern) | – | `QR(MSVD): onsetOfExanthem` | optional | Arzt |
| TB-Zusatzangaben (Therapie, betroffene Organe, Vorerkrankung, Einreise, Alter < 15) | – | `QR(MYTD)`: `statusDiagnosis`, `treatment`, `majorSite`, `minorSite`, `prevTreatment`, `causeDiagnosis`, `infectionEnvironmentSettingKind`, … | MYTD: viele **Pflicht** | Arzt (nur bei TB sichtbar) |
| Hepatitis-B/C-Zusatzangaben | – | `QR(HBVD/HCVD)` inkl. Infektionsweg (`answerSetInfectionPath…`, `answerSetTransmissionKind…`) **[UNGEPRÜFT: Detail nicht ausgewertet]** | krankheitsabhängig | Arzt (nur bei HBV/HCV) |
| Kontaktpersonen / Infektionsquelle | – | **kein Ziel** (Infektionsquelle nur bei HIV vorgesehen) | – | Arzt (nur Landesmeldung/PDF) |
| Sofortmaßnahmen | – | **kein Ziel** | – | Arzt (nur Landesmeldung/PDF) |
| Wichtige Zusatzinformationen | – | `QR(Common): additionalInformation` (Freitext) | optional | Arzt |

## F. Meldende Person und Einrichtung

| Formularfeld | KIS-Quelle | DEMIS-Ziel | Pflicht | Wer füllt |
|---|---|---|---|---|
| Einrichtung (Name, Anschrift, Telefon) | Konfiguration (DRK Krankenhaus Chemnitz-Rabenstein) | `NotifierFacility`: `name`, `type`, `telecom`, `address` (`line`, `city`, `postalCode`, `country`), Kennung `bsnr` (Betriebsstättennummer) und/oder `demisParticipantId` | **Pflicht** (Name, Art, Kontakt, Adresse) | Auto |
| Ärztin/Arzt (Name, Telefon) | Anmeldung (später LDAP/AD); Name aus `ISiKPersonImGesundheitsberuf` möglich | `Notifier`: `name.family`, `name.given`, `telecom` (Telefon Pflicht, 1), `address` optional | **Pflicht** | Auto (Benutzerprofil), Arzt bestätigt |
| Verbindung Person ↔ Einrichtung | – | `NotifierRole` (verweist auf `Notifier` und `NotifierFacility`); `Composition.author` zeigt auf `NotifierRole` | Pflicht | Auto |
| Zuständiges Gesundheitsamt | – | wird von DEMIS **automatisch berechnet** (Wiki, „DEMIS-APIs“); wir senden es nicht mit | – | – |

## G. Sachsen-Zusatz (SächsIfSMeldeVO vom 19.07.2024, im Original gelesen)

| Angabe | Quelle | Ziel | Wer |
|---|---|---|---|
| Namentliche Meldung von **Erkrankung und Tod** bei 23 Krankheiten (§ 1 Abs. 1; u. a. Influenza, CDI mit toxinbildenden Stämmen, Legionellose, Borreliose, Herpes zoster, Malaria, Tetanus, Skabies, Shigellose, Listeriose, Brucellose, Q-Fieber, Tularämie) | ICD-10-GM aus `ISiKDiagnose` → Regelwerk-YAML | Landesmeldung (PDF + maschinenlesbarer Datensatz) | Auto, Arzt bestätigt |
| **Tod infolge jeder sonstigen Infektionskrankheit** außer AIDS (§ 1 Abs. 2) | `Patient.deceased[x]` + Infektionsdiagnose | Landesmeldung | KIS + Arzt |
| Alle Papierformular-Felder ohne DEMIS-Ziel (Symptome, erste Konsultation, Beatmung, Isolierung, Kontaktpersonen, Infektionsquelle, Sofortmaßnahmen, Labordaten) | siehe Abschnitte B–E | Landesmeldung (PDF + Datensatz) | Arzt/KIS |
| Erregernachweise nach § 2 und § 3 (Adenovirus, Astrovirus, Parvovirus B19 usw.) | – | **nicht unsere Aufgabe**: Labor meldet. DEMIS führt diese als landesspezifische Laborkategorien (`DE-SN`) | – |

**Das Landesformular liegt vor** (`vorlagen/LUA-HM-Arzt-Meldebogen.pdf`, Stand 08/2024, 2 Seiten) und bestätigt das Mapping oben. Zusätzliche Erkenntnisse:
- Seite 2 enthält die **Krankheitsliste mit Spalten V (Verdacht), E (Erkrankung), T (Tod)**. Daraus wird das Regelwerk-YAML (Phase 6) abgeleitet:
  je Krankheit steht fest, welche der drei Angaben meldepflichtig sind (z. B. Influenza und C. difficile nur E und T, Masern V, E und T).
- Das **Landesformular ist auch der Weg für § 6 Abs. 3 IfSG:** Die Zeile „zwei oder mehr nosokomiale Infektionen mit wahrscheinlichem oder vermutetem
  epidemischem Zusammenhang (nichtnamentliche Meldepflicht)“ steht dort mit V, E und T. Für den Norovirus-Fall (Testfall 5) ist das Formular also der vorgesehene Weg, nicht DEMIS.
- Die Zeile „übrige Infektionskrankheiten, ausgenommen AIDS“ hat nur die Spalte T. Das entspricht § 1 Abs. 2 der Verordnung (Testfall 6).
- Fußnote: Gastroenteritis ist nur meldepflichtig bei Beschäftigten im Lebensmittelbereich (§ 42) **oder** bei zwei oder mehr gleichartigen Erkrankungen mit epidemischem Zusammenhang.
- Zusätzliche Formularfelder: Geschlecht hat die Auswahl *divers*; **Impfstatus** (unbekannt, ungeimpft, unvollständig, vollständig, Anzahl der Impfungen, Datum der letzten Impfung);
  drei Ankreuzfelder „Epidemiologische Hinweise“ mit Name/Anschrift der Einrichtung; **Sofortmaßnahmen a–e** (a Untersuchungsmaterial, b Beobachtung/Absonderung/Verbot, c Belehrung, d Material von Infektionsquelle, e Maßnahmen für Umgebung).
  Sofortmaßnahmen und „Meldung im Gesundheitsamt angenommen durch“ (nur vom Amt auszufüllen) haben kein DEMIS-Ziel.
- Die Verordnung nennt keine Fristen; als Rahmen gilt § 6 IfSG und ist zu bestätigen.

Hinweis zu Herpes zoster: In DEMIS ist `vzzd` als landesspezifisch für Sachsen-Anhalt (`DE-ST`) gekennzeichnet, nicht für Sachsen.
Ob Herpes-zoster-Meldungen aus Sachsen über DEMIS angenommen werden, ist offen.

## H. Zusammenfassung: Welche Formularfelder gibt es in DEMIS nicht?
Symptome (allgemein), erste Arztkonsultation, Beatmungspflicht, Absonderung (nur indirekt), Labordatum/Labornummer,
Kontaktpersonen, Infektionsquelle (außer HIV), Sofortmaßnahmen. Diese Felder bleiben im Assistenten
sichtbar, gehen aber **nur in die sächsische Landesmeldung bzw. das PDF**, nicht in die DEMIS-Meldung.
Umgekehrt verlangt DEMIS Angaben, die das Papierformular nicht kennt (Bundeswehr, Ausbruchszuordnung,
Hospitalisierung je Fachabteilung, Impfinformationen als eigene Ressource).
