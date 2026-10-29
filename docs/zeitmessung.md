# Zeitmessung der Meldung (Ziel: unter 2 Minuten)

Gemessen am 29.10.2026 mit `tools/zeitmessung.js` im echten Browser (Chromium) gegen das Schein-KIS und die laufende Anwendung,
jeweils von der Arbeitsliste bis zur Freigabe. Alle Daten sind synthetisch.

| Fall | Eingaben | Wartezeit des Systems | Skriptzeit | Schätzung für einen Menschen* | Zeit je Eingabe, um 2:00 min zu halten |
|---|---:|---:|---:|---:|---:|
| C. difficile (Fall 1) | 12 | 6,5 s | 6,7 s | 0:55 min | 9,5 s |
| C. difficile, verstorben (Fall 7) | 11 | 2,6 s | 2,7 s | 0:47 min | 10,7 s |
| Tuberkulose (Fall 2) | 22 | 4,8 s | 5,1 s | 1:33 min | 5,2 s |
| Masern-Verdacht (Fall 3) | 15 | 2,7 s | 2,8 s | 1:03 min | 7,8 s |

\* Annahme: 4 Sekunden je Eingabe (Frage lesen, Antwort wählen). Eine „Eingabe“ ist ein Klick, eine Auswahl oder eine Texteingabe
einschließlich Link „Meldung bearbeiten“, „Weiter zur Vorschau“ und „Freigeben“.

**Einordnung (ehrlich):**
- Das **System selbst bremst nicht**: Über den ganzen Durchlauf warten Sie zusammengerechnet nur 3 bis 7 Sekunden.
- Entscheidend ist die **Zahl der Eingaben**. Die einfachen Fälle (11 bis 15 Eingaben) bleiben auch bei 8 Sekunden je Eingabe unter 2 Minuten.
  Die **Tuberkulose-Meldung (22 Eingaben)** hält die 2 Minuten nur, wenn jede Eingabe in etwa 5 Sekunden gelingt. Das ist für eine geübte Ärztin machbar, für den ersten Durchlauf eher knapp.
- Die Schätzung ersetzt **keine Messung mit einer echten Ärztin/einem echten Arzt**. Die Abnahme „Ich kann eine Meldung allein durchklicken“ steht aus.
- Die Eingaben sind bewusst gezählt, **nachdem** das KIS alles Bekannte vorausgefüllt hat (Aufnahme, Station, Tod, Labor, Verdacht, Daten, Vorschlag für den schweren Verlauf).
  Je mehr das KIS liefert, desto weniger bleibt zu tun.

Messung wiederholen:

```bash
python -m meldeassistent.web &                      # Anwendung starten (frisch, sonst sind Entwürfe vom letzten Lauf noch da)
NODE_PATH=$(npm root -g) node tools/zeitmessung.js
```
