# OFFENE FRAGEN

Stand: 28.10.2026 · Erledigt = ☑, offen = ☐.

## 0. Blocker der Entwicklungssitzung (Projektleitung/IT)
- ☑ Freigegeben und genutzt: GitHub-Clone (RKI), `packages2.fhir.org`, `wiki.gematik.de`, `simplifier.net`, PyPI, Docker Hub.
- ☑ Sachsen freigegeben: Verordnungstext SächsIfSMeldeVO (Stand 28.10.2026) gelesen.
- ☑ Landesformular (Stand 08/2024) wurde bereitgestellt: `vorlagen/LUA-HM-Arzt-Meldebogen.pdf`.
- ☑ `tx.fhir.org` und `www.bfarm.de` freigegeben (erreichbar). **Aber:** `tx.fhir.org` führt ICD-10-GM nicht (Lizenz). Für DEMIS unkritisch (DEMIS-Meldung enthält keine ICD-Codes);
  ob SNOMED-Antworten (z. B. im CDFD-Fragebogen) dort geprüft werden können, wird in Phase 3 getestet.
- ☐ **Docker Hub:** In der Entwicklungssitzung liefert Docker Hub dauerhaft HTTP 429 (Abruflimit). Das HAPI-Image kam über den Spiegel `mirror.gcr.io`.
  Für die Klinik-VM ist das unkritisch (eigene IP), sollte aber beim Betrieb bedacht werden (ggf. Klinik-eigene Registry).
- ☐ **Noch gesperrt, nützlich für Phase 2:** `gemspec.gematik.de` (ISiK-Spezifikationstext; die Profile selbst sind über den Paketserver lesbar).
- Hinweis: WebFetch erreicht neu freigegebene Hosts nicht, `curl` in der Shell schon. Das ist ein Werkzeug-, kein Sicherheitsproblem.

## 1. Fachliche Klärung mit dem DEMIS-Support / RKI (`demis-support@rki.de`)
- ☐ **Häufung nach § 6 Abs. 3 IfSG (z. B. Norovirus-Ausbruch):** Der Code `6.3` existiert, im Paket 3.0.0 fehlt ein Profil.
  Wie meldet ein Krankenhaus das über die FHIR-Schnittstelle? Nur über das Meldeportal?
- ☐ **Endpunktversion:** Das Wiki nennt für Erkrankungsmeldungen `…/notifications/disease/v6/…` und
  „striktere Profilierung“ `…/disease/v7/…` (Test: `prod-test` zeigt `v6`). Welche Version gehört zu `rki.demis.disease` 3.0.0
  und welche Version ist heute für neue Anbindungen zu verwenden?
- ☐ **Altpfade:** Die alten Pfade `/notification-api/…` und `/hospitalization/…` sind laut Wiki „DEPRECATED“. Bestätigen, dass wir nur die neuen nutzen.
- ☐ **Zertifikate:** Zwei getrennte (§ 6 und ggf. § 7) oder nur § 6? Wir bräuchten nur § 6 (ärztliche Meldung). Pro IK-Nummer, 3 Jahre Laufzeit.
- ☐ **Client-ID/Passwort pro Softwareprodukt** (Realm `HOSPITAL`): Produktname für den Antrag festlegen (Vorschlag: „DEMIS-Meldeassistent DRK Chemnitz-Rabenstein“).
- ☐ **Terminologie:** Die Antworten im CDFD-Fragebogen sind SNOMED-Ausdrücke (z. B. `186431008:{288556008=305351004}`).
  Welchen Terminologieserver nutzt der Validator, und ist SNOMED-Lizenzierung für uns relevant?
- ☐ **Mehrere Krankenhausabschnitte:** Wird ein Aufenthalt Normalstation → ITS als eine oder als mehrere `Hospitalization`-Ressourcen gemeldet?
  (Die Beispiele im Paket zeigen je eine Ressource mit einer Fachabteilung.)
- ☐ Fehlende Felder des Papierformulars (Beatmung, Symptome, Isolierung …): Bestätigen, dass DEMIS sie in der Arztmeldung nicht vorsieht.

## 2. An NEXUS
- ☐ Ist die ISiK-FHIR-R4-Schnittstelle im Haus lizenziert/aktiviert? Welche ISiK-Stufe/Version (verfügbar: Basismodul 3.1.1 und 4.0.3)?
- ☐ Laborbefunde (`Observation`/`DiagnosticReport`) per FHIR (ISiK-Labormodul)? Sonst: HL7-v2-ORU-Schnittstelle, Format, Ansprechpartner.
- ☐ Authentifizierung der FHIR-Schnittstelle (OAuth2/SMART, technischer Benutzer).
- ☐ Wird `Patient.deceased[x]` befüllt? Sind Diagnosen mit ICD-10-GM und Diagnosesicherheit (Verdacht/gesichert) verfügbar?
- ☐ Sind Fachabteilungsschlüssel (z. B. `3600` Intensivmedizin) je Aufenthaltsabschnitt (Abteilungs-/Versorgungsstellenkontakt) verfügbar?
- ☐ Gibt es Impfdaten (`Immunization`) und Schwangerschaftsstatus im FHIR-Export?
- ☐ NEXUS-Testsystem mit synthetischen Daten?
- ☐ **Suchfunktionen, auf die der KIS-Adapter angewiesen ist** (im Schein-KIS vorhanden, bei NEXUS zu bestätigen):
  `Encounter` suchen nach `type` (Kontaktebene), `status`, `date`, `part-of` sowie `_include=Encounter:patient` und `_revinclude=Condition:encounter`;
  `Condition?encounter=…`; `DiagnosticReport?encounter=…&_include=DiagnosticReport:result`. Ohne `_revinclude` muss der Adapter je Fall einzeln nachladen (langsamer).
- ☐ **Aufbau der Kontakte:** Verweist jeder Abteilungs-/Versorgungsstellenkontakt über `Encounter.partOf` auf den Einrichtungskontakt? (Der Adapter nutzt das für Stationen und ITS.)
- ☐ **Seitengröße und Anmeldung:** Maximale `_count`-Größe, Format des Zugangs-Tokens (Bearer?), Gültigkeitsdauer.

## 3. An die Klinik-IT
- ☐ VM im Kliniknetz; ausgehende Verbindung zu `demis.rki.de` und `test.demis.rki.de` (Port 443) freigeben.
- ☐ Zertifikatsablage (außerhalb des Repositories), technische Ansprechperson für das CSM-Portal der Bundesdruckerei.
- ☐ Hauptinstitutionskennzeichen (IK) der Klinik und Betriebsstättennummer (BSNR) für den Antrag und für `NotifierFacility`.
- ☐ LDAP/AD: Gruppen/Rollen für meldeberechtigte Ärzte.

## 4. An das Gesundheitsamt / Hygiene
- ☐ **Norovirus-Häufung (§ 6 Abs. 3):** Ist sie in Sachsen vom Gesundheitsamt anders geregelt (Formular, Telefon, Portal)? Die Landesverordnung enthält Norovirus nicht.
- ☐ **C. difficile:** Sachsen verlangt Meldung jeder toxinbildenden CDI (§ 1 Abs. 1 Nr. 5), DEMIS nur die schwere Verlaufsform.
  Bestätigen: schwer → nur DEMIS; nicht schwer → nur Sachsen? Oder zusätzlich Landesmeldung bei schwerem Verlauf?
- ☐ **Tod bei Infektionskrankheit** (§ 1 Abs. 2): Gilt dies auch bei MRGN-Kolonisation, an der der Patient nicht verstarb? (Wortlaut: „Tod *infolge*“.) Fachliche Auslegung durch Hygiene.
- ☐ **Herpes zoster, Influenza u. a.:** Werden Sachsen-Fälle mit DEMIS-Kategorie `vzzd` angenommen (DEMIS flaggt `vzzd` nur für `DE-ST`)?
- ☐ **Frist** der Landesmeldung (Verordnung nennt keine; § 6 IfSG gilt als Rahmen): bestätigen.
- ☐ Gewünschtes Format/Weg der Landesmeldung (KIM-Adresse? Fax? Portal?).
- ☑ **ICD-10-GM-Codes der Testdaten** wurden vom Auftraggeber am 28.10.2026 bestätigt (A04.71, A15.0, B05.9, J10.1, A08.1, A41.58) und mit Anzeigetext in `faelle.py` eingetragen.
- ☐ Bleibt das Papierformular für die Landesmeldung verbindlich? Darf ein PDF + Datensatz an seine Stelle treten?
- ☐ Wer pflegt das YAML-Regelwerk fachlich (Hygiene)?

## 5. Fachliche Entscheidungen für den Chefarzt
- ☑ **Testfälle entschieden (28.10.2026):** Influenza und MRGN testen den Sachsen-Weg; ein DEMIS-Fall mit Todesfolge (C. difficile) wird ergänzt.
  Der Norovirus-Fall testet nicht den Sachsen-Weg (Norovirus steht nicht in der Verordnung), sondern den Rückfallzweig „kein automatischer Meldeweg“.
- ☐ Soll der Assistent bei „nicht über DEMIS meldbar“ (z. B. saisonale Influenza) trotzdem die Landesmeldung vorbereiten?
- ☐ Soll das Meldeportal (SMC-B) als dokumentierter Rückfallweg im Handbuch genannt werden, falls die FHIR-Anbindung ausfällt?

## 6. Datenschutz / Entscheidungen der Projektleitung
- ☐ Darf die DEMIS-Quittung (PDF mit Meldungsdaten) gespeichert werden (Regel 5)? Aufbewahrungsdauer? Zugriffsrechte?
- ☐ Datenschutzbeauftragten früh einbinden (Zuarbeit in Phase 7).
- ☐ Besonderheit der Testumgebung: Das Wiki verlangt dort ausschließlich Testdaten. Das ist mit unserer Regel 1 identisch, Verstöße wären aber nicht rückholbar.

## 7. Aus der Recherche notiert (zur Kenntnis)
- Ihr Auftrag nennt `demis@rki.de`. Das Wiki nennt durchgängig `demis-support@rki.de` für Zertifikate, Testzugang und Client-ID. Bitte diese Adresse verwenden.
- Test-Zugangsdaten stehen öffentlich im Wiki (Seite „Informationen zur DEMIS-Testumgebung“; die Werte stehen bewusst nicht in diesem Repository). Sie gehören trotzdem **nur** in die Konfiguration, nicht in Code oder Repository.
- Das Testzertifikat ist an eine Test-IK (987654321, „Testkrankenhaus – gematik GmbH“) gebunden. Unsere `NotifierFacility` muss in der Testumgebung zu diesem Zertifikat passen.
