# Synthetische Testdaten (Schein-KIS)

**Alle Daten sind frei erfunden.** Die Patienten heißen "Testpatient", jede Ressource trägt das Tag
`SYNTHETISCH`. Es sind keine echten Personen, Adressen oder Befunde enthalten.

Die JSON-Dateien werden aus `src/meldeassistent/testdaten/faelle.py` erzeugt. Nicht von Hand ändern:

```bash
.venv/bin/python -m meldeassistent.testdaten --erzeugen
```

| Datei | Inhalt | Erwarteter Meldeweg |
|---|---|---|
| `00-stammdaten.json` | Klinik, Fachabteilungen, Stationen, Testlabor | – |
| `01-cdi-schwer.json` | C. difficile, schwer, ITS | DEMIS (`CDFD`) |
| `02-tb-offen.json` | Offene Lungen-TB, Isolierstation | DEMIS (`MYTD`) |
| `03-masern-verdacht.json` | Masern-Verdacht, Kind | DEMIS (`MSVD`) |
| `04-influenza.json` | Influenza nachgewiesen | Sachsen (§ 1 Abs. 1 Nr. 9) |
| `05-norovirus-ausbruch.json` | 3 Patienten, Station 3B | kein automatischer Weg (§ 6 Abs. 3) |
| `06-mrgn-verstorben.json` | Sepsis 4MRGN, verstorben | Sachsen (§ 1 Abs. 2) |
| `07-cdi-schwer-verstorben.json` | C. difficile, schwer, verstorben | DEMIS (`CDFD`, mit Todesangabe) |
| `uebersicht.json` | Erwartungen und Begründungen je Fall | – |

Hinweise:
- Die ICD-10-GM-Codes konnten nicht gegen den BfArM-Katalog geprüft werden (siehe `OFFENE_FRAGEN.md`).
- Laborbefunde sind ein vereinfachtes Format (kein ISiK-Labor), weil offen ist, was NEXUS liefert.
- Einspielen ist wiederholbar: gleiche IDs, es entstehen keine Duplikate.
