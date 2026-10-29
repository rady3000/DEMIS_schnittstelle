"""Baut die Klick-Demo: EINE HTML-Datei, die ohne Installation per Doppelklick im Browser läuft.

Die Fragebögen, Antwortlisten, Texte und die Vorbelegung kommen aus dem echten Programm (Fragebögen des RKI,
Schein-KIS mit erfundenen Patienten, Regelwerk). Nur die Formularlogik ist in JavaScript nachgebaut. Die Demo
sendet nichts, prüft nichts gegen den Validator und speichert nichts.

Aufruf (im Projektordner):   .venv/bin/python tools/klickdemo_bauen.py
Ergebnis:                    demo/DEMIS-Meldeassistent-Klickdemo.html
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "tests"))  # Fake-KIS der Tests

from demis_faelle import KONFIG, MELDER, kis_adapter  # noqa: E402

from meldeassistent.demis.mapper import erzeuge_meldung  # noqa: E402
from meldeassistent.demis.pakete import standard_pakete  # noqa: E402
from meldeassistent.demis.vorbelegung import vorbelegung  # noqa: E402
from meldeassistent.regelwerk import Meldeweg, bewerte  # noqa: E402
from meldeassistent.testdaten.demo_meldung import FAELLE as DEMO_FAELLE, demo_angaben  # noqa: E402
from meldeassistent.web.anzeige import alter_jahre, datum_de, option_text  # noqa: E402
from meldeassistent.web.app import AUTOMATISCH, NICHT_UNTERSTUETZT_JA, WEG_NAMEN  # noqa: E402
from meldeassistent.web.vorschau import vorschau_aus_bundle  # noqa: E402

HEUTE = date(2026, 10, 28)
JETZT = datetime(2026, 10, 28, 12, 0, tzinfo=timezone(timedelta(hours=1)))
KUERZEL = ("CDFD", "MYTD", "MSVD")
KRANKHEIT = {"CDFD": "C. difficile, schwere Verlaufsform", "MYTD": "Tuberkulose", "MSVD": "Masern"}
GESCHLECHT = {"maennlich": "männlich", "weiblich": "weiblich", "divers": "divers", "unbestimmt": "unbestimmt"}


def schlank(item: dict, pakete) -> dict:
    """Ein Fragebogen-Eintrag mit allem, was die Oberfläche braucht (Antwortlisten sind schon aufgelöst)."""
    aus = {
        "id": item["linkId"], "text": item.get("text"), "typ": item["type"], "pflicht": bool(item.get("required")),
    }
    if item.get("enableWhen"):
        aus["wenn"] = [
            {"frage": b["question"], "op": b["operator"],
             "wert": (b.get("answerCoding") or {}).get("code") or b.get("answerString") or b.get("answerBoolean")}
            for b in item["enableWhen"]
        ]
        aus["verhalten"] = item.get("enableBehavior", "all")
    if item.get("initial"):
        aus["anfang"] = item["initial"][0]["valueCoding"]["code"]
    if item["type"] == "choice":
        konzepte = pakete.wertemenge(item["answerValueSet"]).konzepte or ()
        aus["optionen"] = [{"code": k.code, "text": option_text(k)} for k in konzepte]
    if item.get("item"):
        aus["kinder"] = [schlank(k, pakete) for k in item["item"]]
    if item["type"] == "group":
        kinder = [k.get("text") for k in item.get("item", []) if k.get("text")]
        aus["text"] = item.get("text") or ("Angaben zu: " + ", ".join(f"„{k}“" for k in kinder[:2]) if kinder else item["linkId"])
    return aus


def fall_daten(fall, uebersicht_alle, uebersicht, pakete) -> dict:
    z = uebersicht
    b = bewerte(z, uebersicht_alle)
    p = fall.patient
    a = fall.aufenthalt
    d = {
        "id": z.kis_fall_id,
        "weg": b.weg.value, "wegName": WEG_NAMEN[b.weg], "kuerzel": b.kuerzel, "grund": b.grund,
        "name": z.patient_name, "geburt": datum_de(z.geburtsdatum), "alter": alter_jahre(z.geburtsdatum, HEUTE),
        "verstorben": z.verstorben.value == "ja", "station": z.station, "laufend": z.laufend,
        "sortierung": [not b.meldepflichtig, not z.laufend, -(z.aufnahme.timestamp() if z.aufnahme else 0)],
        "diagnosen": [
            {"code": x.icd_code, "text": x.icd_text or x.freitext or "", "verdacht": x.sicherheit.value == "verdacht"}
            for x in z.diagnosen
        ],
        "patient": {
            "name": f"{p.nachname}, {p.vorname}", "anzeigename": p.anzeigename, "geschlecht": GESCHLECHT.get(p.geschlecht.value, "unbekannt"),
            "adresse": (", ".join(p.adresse.zeilen) + f", {p.adresse.plz} {p.adresse.ort}") if p.adresse else "–",
            "telefon": p.telefon or "–",
        },
        "aufnahme": datum_de(a.beginn) or "–",
        "ende": None if a.laufend else datum_de(a.ende),
        "stationen": [
            {"name": ab.station or ab.fachabteilung_name or "–", "intensiv": ab.ist_intensivstation,
             "von": datum_de(ab.beginn), "bis": datum_de(ab.ende) or "andauernd"}
            for ab in a.abschnitte
        ],
        "labor": [{"text": f"{l.untersuchung}: {l.ergebnis}" + (f" ({datum_de(l.datum)})" if l.datum else "")} for l in fall.laborbefunde],
        "hinweise": list(fall.hinweise),
    }
    if b.weg is Meldeweg.DEMIS:
        angaben = vorbelegung(fall, b.kuerzel, KONFIG)
        d["start"] = {
            "allgemein": angaben.allgemein, "spezifisch": angaben.spezifisch, "herkunft": angaben.herkunft,
            "verdacht": angaben.verdacht, "beginn": datum_de(angaben.erkrankungsbeginn), "diagnosedatum": datum_de(angaben.diagnosedatum),
            "diagnoseKis": bool(angaben.herkunft.get("diagnose")),
        }
    return d


def main() -> None:
    pakete = standard_pakete()
    kis = kis_adapter()
    uebersicht = kis.liste_faelle(seit=HEUTE - timedelta(days=30))
    faelle = []
    for z in uebersicht:
        faelle.append(fall_daten(kis.lade_fall(z.kis_fall_id), uebersicht, z, pakete))
    faelle.sort(key=lambda f: f["sortierung"])

    # Bezeichnung des Meldetatbestands aus einer echten, erzeugten Meldung (nicht von Hand getippt)
    tatbestand = {}
    for name, (fall_id, kuerzel) in DEMO_FAELLE.items():
        fall = kis.lade_fall(fall_id)
        bundle = erzeuge_meldung(fall, demo_angaben(fall, name), MELDER, KONFIG, jetzt=JETZT)
        tatbestand[kuerzel] = vorschau_aus_bundle(bundle, pakete)["Erkrankung"][0].wert

    fragebogen = {"allgemein": [schlank(i, pakete) for i in pakete.fragebogen("Common")["item"]]}
    for k in KUERZEL:
        fragebogen[k] = [schlank(i, pakete) for i in pakete.fragebogen(k)["item"]]

    def liste(url: str) -> list[dict]:
        return [{"code": k.code, "text": k.display or k.code} for k in (pakete.wertemenge(url).konzepte or ()) if k.code not in ("NASK", "ASKU")]

    daten = {
        "heute": datum_de(HEUTE),
        "faelle": faelle,
        "fragebogen": fragebogen,
        "tatbestand": tatbestand,
        "krankheit": KRANKHEIT,
        "impfstoffe": {k: liste(f"https://demis.rki.de/fhir/ValueSet/vaccine{k}") for k in KUERZEL},
        "symptome": liste("https://demis.rki.de/fhir/ValueSet/evidenceMSVD"),
        "automatisch": sorted(AUTOMATISCH),
        "nichtUnterstuetztJa": sorted(NICHT_UNTERSTUETZT_JA),
        "melder": {"einrichtung": KONFIG.einrichtung.name, "person": f"{MELDER.vorname} {MELDER.nachname}"},
    }

    css = (WURZEL / "src/meldeassistent/web/static/app.css").read_text(encoding="utf-8")
    vorlage = (WURZEL / "tools/klickdemo/vorlage.html").read_text(encoding="utf-8")
    html = vorlage.replace("/*APP_CSS*/", css).replace("/*DATEN*/null", json.dumps(daten, ensure_ascii=False).replace("</", "<\\/"))
    ziel = WURZEL / "demo" / "DEMIS-Meldeassistent-Klickdemo.html"
    ziel.parent.mkdir(exist_ok=True)
    ziel.write_text(html, encoding="utf-8")
    print(f"{ziel} ({ziel.stat().st_size / 1024:.0f} KB, {len(faelle)} Fälle)")


if __name__ == "__main__":
    main()
