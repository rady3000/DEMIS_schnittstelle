"""Erzeugt eine lesbare HTML-Übersicht der Testfälle (für Menschen, nicht für den Server)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from .faelle import STATIONEN, WEG_DEMIS, WEG_KEIN_AUTOMATISCH, WEG_SACHSEN, alle_faelle

WEG_TEXT = {
    WEG_DEMIS: "DEMIS",
    WEG_SACHSEN: "Sachsen (Landesmeldung)",
    WEG_KEIN_AUTOMATISCH: "kein automatischer Weg",
}
WEG_KLASSE = {WEG_DEMIS: "demis", WEG_SACHSEN: "sachsen", WEG_KEIN_AUTOMATISCH: "offen"}


def erzeuge_html() -> str:
    zeilen = []
    for nummer, fall in enumerate(alle_faelle(), start=1):
        for index, (person, abschnitte, diagnose, labor) in enumerate(fall.personen):
            stationen = " → ".join(STATIONEN[a.station][0] for a in abschnitte)
            diagnose_text = f"{diagnose.icd} ({'gesichert' if diagnose.sicherheit == 'G' else 'Verdacht'})"
            status = "verstorben" if person.verstorben else "lebend"
            profil = f" ({fall.erwartetes_demis_profil})" if fall.erwartetes_demis_profil else ""
            erste = index == 0
            zeilen.append(
                "<tr>"
                + (f"<td rowspan='{len(fall.personen)}'>{nummer}</td>" if erste else "")
                + (f"<td rowspan='{len(fall.personen)}'><b>{escape(fall.titel)}</b></td>" if erste else "")
                + f"<td>{escape(person.vorname)} Testpatient</td><td>{status}</td>"
                f"<td>{escape(stationen)}</td><td>{escape(diagnose_text)}</td>"
                f"<td>{'ja' if labor else 'nein'}</td>"
                + (
                    f"<td rowspan='{len(fall.personen)}' class='{WEG_KLASSE[fall.erwarteter_weg]}'>"
                    f"<b>{WEG_TEXT[fall.erwarteter_weg]}{escape(profil)}</b><br><small>{escape(fall.begruendung)}</small></td>"
                    if erste
                    else ""
                )
                + "</tr>"
            )
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Testfälle Schein-KIS</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 16px; color: #1b1b1b; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
 th, td {{ border: 1px solid #c9c9c9; padding: 6px 8px; vertical-align: top; text-align: left; }}
 th {{ background: #eef2f6; }}
 td.demis {{ background: #e6f4ea; }} td.sachsen {{ background: #fff4d6; }} td.offen {{ background: #fde7e7; }}
 .hinweis {{ background: #eef2f6; padding: 8px 12px; margin-bottom: 12px; }}
</style></head><body>
<h1>Testfälle im Schein-KIS</h1>
<p class="hinweis">Alle Daten sind frei erfunden (synthetisch). Keine echten Patienten.</p>
<div style="overflow-x:auto"><table>
<tr><th>Nr.</th><th>Fall</th><th>Patient</th><th>Status</th><th>Station(en)</th><th>Diagnose (ICD-10-GM)</th><th>Labor</th><th>Erwarteter Meldeweg</th></tr>
{chr(10).join(zeilen)}
</table></div>
</body></html>
"""


def schreibe_html(pfad: Path) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(erzeuge_html(), encoding="utf-8")
    return pfad
