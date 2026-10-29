"""Fragebögen der DEMIS-Erkrankungsmeldung: Antworten aufbauen und prüfen.

Die Krankheitsmeldung besteht zu einem großen Teil aus Fragebogen-Antworten (FHIR
``QuestionnaireResponse``). Die Fragen, Pflichtangaben, Bedingungen und erlaubten Antworten stehen im
offiziellen Fragebogen (``Questionnaire``) des DEMIS-Pakets. Dieses Modul

- baut aus einfachen Antworten ({linkId: Wert}) die korrekt verschachtelte Antwortstruktur und
- prüft vorhandene Antworten gegen den Fragebogen und meldet Lücken verständlich auf Deutsch.

Warum eigene Prüfung? Der offizielle FHIR-Validator kann die SNOMED-Antworten ohne den deutschen
SNOMED-Katalog nicht zuverlässig prüfen (selbst die Beispiele des RKI fallen dort durch). Hier wird
direkt gegen die in den DEMIS-Wertemengen aufgezählten Antworten geprüft.

Einfaches Antwortformat ({linkId: Wert}):
- Auswahlfrage (``choice``): der Code, z. B. ``"yes"``, ``"NASK"``, ``"DE"``
- Datum: ``date`` oder Text ``"2026-10-12"`` (auch ``"2026-10"`` oder ``"2026"``)
- Freitext: ``str``
- Verweis (``reference``): ``"Encounter/<id>"``
- sich wiederholende Gruppe: Liste von Dicts, ein Dict je Wiederholung
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from .pakete import DemisPakete, Konzept

NULLFLAVOR = "http://terminology.hl7.org/CodeSystem/v3-NullFlavor"
DATUM = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
REFERENZ = re.compile(r"^[A-Za-z]+/[A-Za-z0-9\-.]{1,64}$")


class UngueltigeAntwort(ValueError):
    """Eine Antwort passt nicht zur Frage (z. B. Code nicht in der Wertemenge)."""


@dataclass(frozen=True)
class Befund:
    """Ein Prüfergebnis zu einer Frage, mit verständlichem deutschem Text."""

    schwere: str  # "fehler" | "offen" (noch nicht beantwortet) | "hinweis"
    link_id: str
    text: str


def _link_ids(frage: dict) -> list[str]:
    ergebnis = []
    for kind in frage.get("item", []):
        ergebnis.append(kind["linkId"])
        ergebnis += _link_ids(kind)
    return ergebnis


# =============================================================================================
# Aufbauen
# =============================================================================================
def _wert_zu_antwort(frage: dict, wert: Any, pakete: DemisPakete) -> dict:
    typ = frage["type"]
    if typ == "choice":
        wertemenge = pakete.wertemenge(frage["answerValueSet"])
        konzept = wertemenge.finde(str(wert))
        if konzept is not None:
            return {"valueCoding": {"system": konzept.system, "code": konzept.code, **({"display": konzept.display} if konzept.display else {})}}
        if wertemenge.konzepte is None and wertemenge.system_standard:  # nicht aufzählbar: Code vertrauen
            return {"valueCoding": {"system": wertemenge.system_standard, "code": str(wert)}}
        raise UngueltigeAntwort(f"'{wert}' ist keine zulässige Antwort auf „{frage['text']}“.")
    if typ == "date":
        text = wert.isoformat() if isinstance(wert, date) else str(wert)
        if not DATUM.match(text):
            raise UngueltigeAntwort(f"'{wert}' ist kein gültiges Datum für „{frage['text']}“ (erlaubt: JJJJ, JJJJ-MM, JJJJ-MM-TT).")
        return {"valueDate": text}
    if typ == "text":
        return {"valueString": str(wert)}
    if typ == "reference":
        if not REFERENZ.match(str(wert)):
            raise UngueltigeAntwort(f"'{wert}' ist kein gültiger Verweis für „{frage['text']}“.")
        return {"valueReference": {"reference": str(wert)}}
    raise UngueltigeAntwort(f"Fragetyp '{typ}' wird nicht unterstützt.")


def _initial(frage: dict) -> dict | None:
    if frage.get("initial"):
        return {"valueCoding": frage["initial"][0]["valueCoding"]}
    return None


def _aktiv(frage: dict, bekannt: dict[str, list[str]]) -> bool:
    """Wertet die Bedingungen (enableWhen) einer Frage anhand der bisher gegebenen Antworten aus."""
    bedingungen = frage.get("enableWhen", [])
    if not bedingungen:
        return True
    ergebnisse = []
    for b in bedingungen:
        gegeben = bekannt.get(b["question"], [])
        erwartet = (b.get("answerCoding") or {}).get("code") or b.get("answerString") or b.get("answerBoolean")
        if b["operator"] == "=":
            ergebnisse.append(erwartet in gegeben)
        elif b["operator"] == "!=":
            ergebnisse.append(bool(gegeben) and erwartet not in gegeben)  # ohne Antwort: nicht aktiv
        elif b["operator"] == "exists":
            ergebnisse.append(bool(gegeben) == bool(b.get("answerBoolean")))
        else:
            ergebnisse.append(False)
    return any(ergebnisse) if frage.get("enableBehavior") == "any" else all(ergebnisse)


def _codes(wert: Any) -> list[str]:
    if isinstance(wert, list):
        return [str(w) for w in wert]
    return [str(wert)] if wert is not None else []


def bekannte_antworten(fragebogen: dict, antworten: dict[str, Any], vorbelegen: bool = True) -> dict[str, list[str]]:
    """Alle gegebenen Antwort-Codes je Frage (für die Bedingungen). Anfangswerte zählen mit, wenn ``vorbelegen``."""
    bekannt: dict[str, list[str]] = {}

    def sammle(daten: dict) -> None:
        for k, v in daten.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                for eintrag in v:
                    sammle(eintrag)
            else:
                bekannt.setdefault(k, []).extend(_codes(v))

    def sammle_initial(items: list[dict]) -> None:
        for f in items:
            if f["linkId"] not in bekannt and vorbelegen and (i := _initial(f)):
                bekannt[f["linkId"]] = [i["valueCoding"]["code"]]
            sammle_initial(f.get("item", []))

    sammle(antworten)
    sammle_initial(fragebogen["item"])
    return bekannt


def baue_antworten(fragebogen: dict, antworten: dict[str, Any], pakete: DemisPakete, vorbelegen: bool = True) -> list[dict]:
    """Baut die ``item``-Liste einer QuestionnaireResponse.

    ``vorbelegen``: Auswahlfragen ohne Antwort erhalten den im Fragebogen festgelegten Anfangswert
    (bei Ja/Nein-Fragen "NASK" = nicht erhoben). Das schreibt DEMIS für unausgefüllte Fragebögen vor.
    """
    bekannt = bekannte_antworten(fragebogen, antworten, vorbelegen)

    def gehe(fragen: list[dict], daten: dict) -> list[dict]:
        ergebnis = []
        for f in fragen:
            lid = f["linkId"]
            if not _aktiv(f, bekannt):
                continue
            if f["type"] == "group":
                if f.get("repeats"):
                    instanzen = daten.get(lid)
                    if instanzen is None:  # flache Antworten (aus der Oberfläche): eine Wiederholung bilden
                        instanzen = [daten] if any(k in daten for k in _link_ids(f)) else []
                    for eintrag in instanzen:
                        kinder = gehe(f.get("item", []), eintrag)
                        if kinder:
                            ergebnis.append({"linkId": lid, "item": kinder})
                else:
                    kinder = gehe(f.get("item", []), daten)
                    if kinder:
                        ergebnis.append({"linkId": lid, "item": kinder})
                continue
            wert = daten.get(lid)
            if isinstance(wert, list):  # mehrere Antworten auf dieselbe Frage (z. B. mehrere Impfungen)
                antworten_liste = [_wert_zu_antwort(f, w, pakete) for w in wert]
            elif wert is not None:
                antworten_liste = [_wert_zu_antwort(f, wert, pakete)]
            else:
                vorgabe = _initial(f) if vorbelegen else None
                antworten_liste = [vorgabe] if vorgabe else []
            if not antworten_liste:
                continue
            kinder = gehe(f.get("item", []), daten)
            if kinder:  # Folgefragen hängen an der (ersten) Antwort
                antworten_liste[0] = {**antworten_liste[0], "item": kinder}
            ergebnis.append({"linkId": lid, "answer": antworten_liste})
        return ergebnis

    return gehe(fragebogen["item"], antworten)


# =============================================================================================
# Prüfen
# =============================================================================================
def _antwort_code(antwort: dict) -> str | None:
    if "valueCoding" in antwort:
        return antwort["valueCoding"].get("code")
    return antwort.get("valueDate") or antwort.get("valueString")


def pruefe_antworten(fragebogen: dict, items: list[dict], pakete: DemisPakete, streng: bool = False) -> list[Befund]:
    """Prüft QuestionnaireResponse-Einträge gegen den Fragebogen. Gibt alle Befunde zurück (leer = in Ordnung).

    DEMIS erlaubt für jede Pflichtfrage die Antwort "nicht erhoben" (NASK) und belegt sie damit vor. Im
    ``streng``-Modus melden wir solche unbeantworteten Fragen als "offen": Die Ärztin/der Arzt soll aktiv
    antworten (Ja, Nein oder bewusst "nicht ermittelbar").
    """
    befunde: list[Befund] = []

    # Alle gegebenen Antwort-Codes einsammeln (für die Bedingungen)
    bekannt: dict[str, list[str]] = {}

    def sammle(liste: list[dict]) -> None:
        for it in liste:
            for a in it.get("answer", []):
                code = _antwort_code(a)
                if code is not None:
                    bekannt.setdefault(it["linkId"], []).append(code)
                sammle(a.get("item", []))
            sammle(it.get("item", []))

    sammle(items)

    def pruefe_ebene(fragen: list[dict], gegeben: list[dict]) -> None:
        definiert = {f["linkId"]: f for f in fragen}
        nach_id: dict[str, list[dict]] = {}
        for it in gegeben:
            if it["linkId"] not in definiert:
                befunde.append(Befund("fehler", it["linkId"], f"Unbekannte Frage '{it['linkId']}' im Fragebogen."))
                continue
            nach_id.setdefault(it["linkId"], []).append(it)

        for f in fragen:
            lid, text = f["linkId"], f.get("text") or f["linkId"]
            vorhanden = nach_id.get(lid, [])
            aktiv = _aktiv(f, bekannt)
            if not aktiv:
                if vorhanden:
                    befunde.append(Befund("fehler", lid, f"„{text}“ wurde beantwortet, obwohl die Frage laut Bedingung nicht gestellt wird."))
                continue
            if f["type"] == "group":
                if f.get("required") and not vorhanden:
                    befunde.append(Befund("fehler", lid, f"Pflichtangabe fehlt: {_gruppenname(f)}"))
                if not f.get("repeats") and len(vorhanden) > 1:
                    befunde.append(Befund("fehler", lid, f"{_gruppenname(f)} darf nur einmal vorkommen."))
                for it in vorhanden:
                    pruefe_ebene(f.get("item", []), it.get("item", []))
                continue
            antworten = [a for it in vorhanden for a in it.get("answer", [])]
            if f.get("required") and not antworten:
                befunde.append(Befund("fehler", lid, f"Pflichtfrage nicht beantwortet: „{text}“"))
                continue
            if len(antworten) > 1 and not f.get("repeats"):
                befunde.append(Befund("fehler", lid, f"„{text}“ erlaubt nur eine Antwort."))
            for a in antworten:
                _pruefe_antwort(f, a, text, befunde, pakete)
                if streng and (a.get("valueCoding") or {}).get("code") == "NASK":
                    codes = {k.code for k in pakete.wertemenge(f["answerValueSet"]).konzepte or ()}
                    wahl = "Ja, Nein oder „nicht ermittelbar“" if codes == {"yes", "no", "NASK", "ASKU"} else "eine Antwort"
                    befunde.append(Befund("offen", lid, f"Noch nicht beantwortet: „{text}“ (bitte {wahl} wählen)."))
                if f.get("item"):
                    pruefe_ebene(f["item"], a.get("item", []))
            if not antworten and f.get("item"):
                pruefe_ebene(f["item"], [])

    pruefe_ebene(fragebogen["item"], items)
    return befunde


def _gruppenname(gruppe: dict) -> str:
    kinder = [k.get("text") for k in gruppe.get("item", []) if k.get("text")]
    return gruppe.get("text") or ("Angaben zu: " + ", ".join(f"„{k}“" for k in kinder[:2]) if kinder else gruppe["linkId"])


def _pruefe_antwort(frage: dict, antwort: dict, text: str, befunde: list[Befund], pakete: DemisPakete) -> None:
    lid, typ = frage["linkId"], frage["type"]
    if typ == "choice":
        coding = antwort.get("valueCoding")
        if not coding or not coding.get("code"):
            befunde.append(Befund("fehler", lid, f"„{text}“: Es fehlt eine ausgewählte Antwort."))
            return
        wertemenge = pakete.wertemenge(frage["answerValueSet"])
        if wertemenge.konzepte is None:
            befunde.append(Befund("hinweis", lid, f"„{text}“: Die Antwort konnte nicht gegen eine Liste geprüft werden."))
        elif not any(k.code == coding["code"] and k.system == coding.get("system") for k in wertemenge.konzepte):
            befunde.append(Befund("fehler", lid, f"„{text}“: Die Antwort „{coding.get('display') or coding['code']}“ (Code {coding['code']}) ist nicht zulässig."))
    elif typ == "date":
        if not DATUM.match(antwort.get("valueDate", "")):
            befunde.append(Befund("fehler", lid, f"„{text}“: Es fehlt ein gültiges Datum (JJJJ, JJJJ-MM oder JJJJ-MM-TT)."))
    elif typ == "text":
        if not antwort.get("valueString", "").strip():
            befunde.append(Befund("fehler", lid, f"„{text}“: Der Text ist leer."))
    elif typ == "reference":
        if not REFERENZ.match((antwort.get("valueReference") or {}).get("reference", "")):
            befunde.append(Befund("fehler", lid, f"„{text}“: Es fehlt der Verweis auf die zugehörige Angabe."))


# =============================================================================================
# Ansicht für die Oberfläche
# =============================================================================================
@dataclass(frozen=True)
class Frage:
    """Eine gerade sichtbare Frage des Meldebogens (unabhängig von HTML)."""

    link_id: str
    text: str
    typ: str  # choice | date | text | reference | group
    pflicht: bool
    tiefe: int  # Einrückung: 0 = oberste Ebene
    optionen: tuple[Konzept, ...] = ()
    wert: str | None = None  # aktuelle Antwort (Code, Datum oder Text)
    hat_nask: bool = False  # Frage ist mit "nicht erhoben" vorbelegt


def formular_fragen(fragebogen: dict, antworten: dict[str, Any], pakete: DemisPakete) -> list[Frage]:
    """Die Fragen, die bei den bisherigen Antworten gestellt werden (Bedingungen ausgewertet), in Reihenfolge."""
    bekannt = bekannte_antworten(fragebogen, antworten, vorbelegen=True)
    ergebnis: list[Frage] = []

    def gehe(fragen: list[dict], tiefe: int) -> None:
        for f in fragen:
            if not _aktiv(f, bekannt):
                continue
            if f["type"] == "group":
                ergebnis.append(Frage(f["linkId"], _gruppenname(f), "group", bool(f.get("required")), tiefe))
                gehe(f.get("item", []), tiefe + 1)
                continue
            optionen: tuple[Konzept, ...] = ()
            if f["type"] == "choice":
                optionen = pakete.wertemenge(f["answerValueSet"]).konzepte or ()
            wert = antworten.get(f["linkId"])
            ergebnis.append(
                Frage(
                    f["linkId"], f.get("text") or f["linkId"], f["type"], bool(f.get("required")), tiefe,
                    optionen, None if wert is None else str(wert), bool(f.get("initial")),
                )
            )
            gehe(f.get("item", []), tiefe + 1)

    gehe(fragebogen["item"], 0)
    return ergebnis
