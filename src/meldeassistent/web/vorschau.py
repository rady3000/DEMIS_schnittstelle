"""Lesbare Vorschau dessen, was tatsächlich gesendet wird (gebaut aus dem fertigen Bundle, nicht aus dem Entwurf)."""

from __future__ import annotations

from dataclasses import dataclass

from meldeassistent.demis.pakete import DemisPakete

from .anzeige import datum_de, option_text

GESCHLECHT = {"male": "männlich", "female": "weiblich", "unknown": "unbekannt"}
NULLFLAVOR = "http://terminology.hl7.org/CodeSystem/v3-NullFlavor"


@dataclass(frozen=True)
class Zeile:
    bezeichnung: str
    wert: str
    tiefe: int = 0


def _ressourcen(bundle: dict, typ: str) -> list[dict]:
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == typ]


def _antwort_text(antwort: dict, pakete: DemisPakete, wertemenge_url: str | None) -> str | None:
    if "valueCoding" in antwort:
        c = antwort["valueCoding"]
        if wertemenge_url:
            konzept = pakete.wertemenge(wertemenge_url).finde(c["code"])
            if konzept:
                return option_text(konzept)
        return c.get("display") or c["code"]
    if "valueDate" in antwort:
        return datum_de(antwort["valueDate"])
    if "valueString" in antwort:
        return antwort["valueString"]
    return None  # Verweise zeigen wir nicht als Zeile, sie stehen in den eigenen Abschnitten


def _fragen_zeilen(items: list[dict], fragebogen_items: list[dict], pakete: DemisPakete, tiefe: int = 0) -> list[Zeile]:
    definiert = {f["linkId"]: f for f in fragebogen_items}
    zeilen: list[Zeile] = []
    for it in items:
        f = definiert.get(it["linkId"], {})
        if "answer" in it:
            texte = [t for a in it["answer"] if (t := _antwort_text(a, pakete, f.get("answerValueSet")))]
            if texte:
                zeilen.append(Zeile(f.get("text") or it["linkId"], "; ".join(texte), tiefe))
            for a in it["answer"]:
                zeilen += _fragen_zeilen(a.get("item", []), f.get("item", []), pakete, tiefe + 1)
        else:
            zeilen += _fragen_zeilen(it.get("item", []), f.get("item", []), pakete, tiefe)
    return zeilen


def vorschau_aus_bundle(bundle: dict, pakete: DemisPakete) -> dict[str, list[Zeile]]:
    """Abschnitte der Vorschau: Überschrift -> Zeilen."""
    abschnitte: dict[str, list[Zeile]] = {}
    pat = _ressourcen(bundle, "Patient")[0]
    name = pat["name"][0]
    zeilen = [
        Zeile("Name", f"{name['family']}, {' '.join(name['given'])}"),
        Zeile("Geburtsdatum", datum_de(pat.get("birthDate")) or "–"),
        Zeile("Geschlecht", {"other": "divers/unbestimmt"}.get(pat["gender"], GESCHLECHT.get(pat["gender"], pat["gender"]))),
    ]
    for a in pat.get("address", []):
        art = a["extension"][0]["valueCoding"]["code"]
        if art == "current":
            zeilen.append(Zeile("Derzeitiger Aufenthaltsort", "Krankenhaus (siehe unten)"))
        else:
            zeilen.append(Zeile("Wohnanschrift", f"{' '.join(a.get('line', []))}, {a.get('postalCode', '')} {a.get('city', '')}"))
    for t in pat.get("telecom", []):
        zeilen.append(Zeile("Telefon" if t["system"] == "phone" else "E-Mail", t["value"]))
    abschnitte["Betroffene Person"] = zeilen

    cond = _ressourcen(bundle, "Condition")[0]
    code = cond["code"]["coding"][0]
    zeilen = [
        Zeile("Meldetatbestand", pakete.codesystem_anzeige(code["system"], code["code"]) or code["code"]),
        Zeile("Art der Meldung", "Verdacht einer Erkrankung" if cond["verificationStatus"]["coding"][0]["code"] == "unconfirmed" else "Erkrankung"),
    ]
    if cond.get("onsetDateTime"):
        zeilen.append(Zeile("Erkrankungsbeginn", datum_de(cond["onsetDateTime"])))
    if cond.get("recordedDate"):
        zeilen.append(Zeile("Diagnosedatum", datum_de(cond["recordedDate"])))
    for e in cond.get("evidence", []):
        c = e["code"][0]["coding"][0]
        zeilen.append(Zeile("Symptom", c.get("display") or c["code"]))
    if cond.get("note"):
        zeilen.append(Zeile("Hinweis", cond["note"][0]["text"]))
    abschnitte["Erkrankung"] = zeilen

    impfungen = _ressourcen(bundle, "Immunization")
    if impfungen:
        zeilen = []
        for i in impfungen:
            c = i["vaccineCode"]["coding"][0]
            zeilen.append(Zeile("Impfstoff", c.get("display") or c["code"]))
            if i.get("occurrenceDateTime"):
                zeilen.append(Zeile("Datum der Impfung", datum_de(i["occurrenceDateTime"])))
        abschnitte["Impfung"] = zeilen

    hosp = _ressourcen(bundle, "Encounter")
    zeilen = []
    for h in hosp:
        abt = ""
        if h.get("serviceType"):
            c = h["serviceType"]["coding"][0]
            abt = pakete.codesystem_anzeige(c["system"], c["code"]) or c["code"]
        von = datum_de(h["period"]["start"])
        bis = datum_de(h["period"].get("end")) or "andauernd"
        zeilen.append(Zeile(abt or "Krankenhausaufenthalt", f"{von} bis {bis}"))
    if zeilen:
        abschnitte["Krankenhausaufenthalt"] = zeilen

    for qr in _ressourcen(bundle, "QuestionnaireResponse"):
        name_fb = qr["questionnaire"].rsplit("/", 1)[-1].removeprefix("DiseaseQuestions")
        titel = "Allgemeine klinische Angaben" if name_fb == "Common" else "Krankheitsspezifische Angaben"
        abschnitte[titel] = _fragen_zeilen(qr["item"], pakete.fragebogen(name_fb)["item"], pakete)

    melder = _ressourcen(bundle, "Practitioner")
    einrichtung = next(o for o in _ressourcen(bundle, "Organization") if o["meta"]["profile"][0].endswith("NotifierFacility"))
    zeilen = [Zeile("Einrichtung", einrichtung["name"])]
    if melder:
        zeilen.append(Zeile("Meldende Person", f"{' '.join(melder[0]['name'][0]['given'])} {melder[0]['name'][0]['family']}"))
    abschnitte["Melder"] = zeilen
    return abschnitte
