"""Der Entwurf einer Meldung: Eingaben der Ärztin/des Arztes, Herkunft jeder Angabe und was noch offen ist.

Reine Logik ohne HTML und ohne HTTP, damit sie sich einfach testen lässt.

Datenschutz (Regel 5): Entwürfe liegen nur im Arbeitsspeicher des Servers und werden nach Freigabe,
Verwerfen oder Zeitablauf gelöscht. Es wird nichts auf die Festplatte geschrieben.

Feldnamen im Formular:
- ``a.<linkId>``  Antwort im allgemeinen Fragebogen,  ``s.<linkId>``  im krankheitsspezifischen Fragebogen
- ``verdacht`` (``ja``/``nein``), ``erkrankungsbeginn``, ``diagnosedatum``, ``diagnosehinweis``
- ``symptom`` (mehrfach, nur Masern), ``impfstoff``, ``impfdatum``
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from meldeassistent.demis.angaben import Impfung, Meldeangaben, Melder, MelderKonfig
from meldeassistent.demis.fragebogen import Frage, formular_fragen
from meldeassistent.demis.mapper import MeldungNichtMoeglich, erzeuge_meldung
from meldeassistent.demis.meldung import pruefe_fragebogen_antworten
from meldeassistent.demis.pakete import DemisPakete
from meldeassistent.demis.vorbelegung import vorbelegung
from meldeassistent.modell import KisFall

from .anzeige import datum_aus_eingabe

# Fragen, die der Mapper selbst beantwortet (Verweise): nie im Formular
AUTOMATISCH = {"labSpecimenLab", "hospitalizedGroup", "hospitalizedEncounter", "immunizationRef", "outbreakNotificationId"}
# Noch nicht unterstützt: Die Antwort "Ja" kann nicht gewählt werden (siehe OFFENE_FRAGEN.md)
NICHT_UNTERSTUETZT_JA = {"infectProtectFacility"}


def herkunft_schluessel(praefix: str, link_id: str) -> str:
    return f"{'allgemein' if praefix == 'a' else 'spezifisch'}.{link_id}"


@dataclass
class Entwurf:
    kis_fall_id: str
    angaben: Meldeangaben
    vorgang: str = field(default_factory=lambda: str(uuid.uuid4()))
    ungueltig: dict[str, str] = field(default_factory=dict)  # Feldname -> Roheingabe, die nicht verstanden wurde
    geoeffnet: float = field(default_factory=time.monotonic)
    zuletzt: float = field(default_factory=time.monotonic)

    def dauer_s(self) -> int:
        return int(time.monotonic() - self.geoeffnet)


def neuer_entwurf(fall: KisFall, kuerzel: str, konfig: MelderKonfig, kis_fall_id: str) -> Entwurf:
    return Entwurf(kis_fall_id=kis_fall_id, angaben=vorbelegung(fall, kuerzel, konfig))


@dataclass(frozen=True)
class Offen:
    """Ein Punkt, der noch zu erledigen ist, mit Sprungziel (Feld-ID) im Formular."""

    feld: str
    text: str
    art: str  # "offen" | "bestaetigen" | "fehler"


@dataclass(frozen=True)
class Stand:
    """Auswertung eines Entwurfs für die Anzeige."""

    fragen_allgemein: list[Frage]
    fragen_spezifisch: list[Frage]
    offen: list[Offen]
    fehler: list[Offen]
    hinweise: list[str]
    bundle: dict | None

    @property
    def bereit(self) -> bool:
        """Alles beantwortet, nichts zu bestätigen, keine Fehler: erst dann geht es zur Vorschau."""
        return not self.offen and not self.fehler and self.bundle is not None


# =============================================================================================
# Formular -> Entwurf
# =============================================================================================
def _erste(daten: dict[str, list[str]], name: str) -> str | None:
    werte = [w for w in daten.get(name, []) if w != ""]
    return werte[0] if werte else None


def wende_formular_an(entwurf: Entwurf, daten: dict[str, list[str]], pakete: DemisPakete) -> None:
    """Übernimmt die abgeschickten Formularwerte. Geändertes wird als 'von Ihnen' (arzt) gekennzeichnet."""
    a = entwurf.angaben
    kuerzel = a.kuerzel
    herkunft = dict(a.herkunft)
    neu_ungueltig: dict[str, str] = {}
    gruppen = {"a": dict(a.allgemein), "s": dict(a.spezifisch)}
    fragebogen = {"a": pakete.fragebogen("Common"), "s": pakete.fragebogen(kuerzel)}

    gesehen = set(daten.get("_f", []))  # Felder, die im Formular angezeigt wurden (auch wenn nichts gewählt ist)
    for praefix in ("a", "s"):
        antworten = gruppen[praefix]
        for _ in range(6):  # Folgefragen können erst durch eine Antwort sichtbar werden: wiederholen, bis nichts mehr ändert
            geaendert = False
            sichtbar = [f for f in formular_fragen(fragebogen[praefix], antworten, pakete) if f.typ != "group" and f.link_id not in AUTOMATISCH]
            for f in sichtbar:
                name = f"{praefix}.{f.link_id}"
                if name not in daten and name not in gesehen:
                    continue  # nicht abgeschickt: unverändert lassen
                roh = _erste(daten, name)
                alt = antworten.get(f.link_id)
                if f.typ == "date" and roh is not None:
                    iso = datum_aus_eingabe(roh)
                    if iso is None:
                        neu_ungueltig[name] = roh
                    roh = iso
                if roh is None:
                    antworten.pop(f.link_id, None)
                else:
                    antworten[f.link_id] = roh
                if roh != alt:
                    geaendert = True
                    schluessel = herkunft_schluessel(praefix, f.link_id)
                    if roh is None:
                        herkunft.pop(schluessel, None)
                    else:
                        herkunft[schluessel] = "arzt"
            if not geaendert:
                break
        # Antworten auf Fragen, die jetzt nicht mehr gestellt werden, entfernen
        sichtbare_ids = {f.link_id for f in formular_fragen(fragebogen[praefix], antworten, pakete)}
        for lid in [k for k in antworten if k not in sichtbare_ids and k not in AUTOMATISCH]:
            antworten.pop(lid)
            herkunft.pop(herkunft_schluessel(praefix, lid), None)

    felder: dict = {"allgemein": gruppen["a"], "spezifisch": gruppen["s"]}
    if "verdacht" in daten:
        felder["verdacht"] = _erste(daten, "verdacht") == "ja"
    for name in ("erkrankungsbeginn", "diagnosedatum"):
        if name in daten:
            roh = _erste(daten, name)
            iso = datum_aus_eingabe(roh) if roh else None
            if roh and not iso or (iso and len(iso) != 10):
                neu_ungueltig[name] = roh or ""
                iso = None
            felder[name] = datum_iso(iso)
            if felder[name] != getattr(a, name):
                herkunft[name] = "arzt"
    if "diagnosehinweis" in daten:
        felder["diagnosehinweis"] = (_erste(daten, "diagnosehinweis") or "").strip() or None
    if kuerzel == "MSVD" and "symptom_gesendet" in daten:
        felder["symptome"] = [s for s in daten.get("symptom", []) if s]
    if "impfung_gesendet" in daten:
        code = _erste(daten, "impfstoff")
        datum = datum_aus_eingabe(_erste(daten, "impfdatum") or "") if _erste(daten, "impfdatum") else None
        if _erste(daten, "impfdatum") and datum is None:
            neu_ungueltig["impfdatum"] = _erste(daten, "impfdatum") or ""
        wird_geimpft = gruppen["s"].get("immunization") == "yes"
        felder["impfungen"] = [Impfung(impfstoff_code=code, datum=datum)] if (code and wird_geimpft) else []
    if "verdacht" in felder and felder["verdacht"] != a.verdacht:
        herkunft["verdacht"] = "arzt"
    if gruppen["s"].get("immunization") != "yes":
        felder["impfungen"] = []  # ohne "Ja" gibt es keine Impfung in der Meldung

    entwurf.angaben = a.model_copy(update={**felder, "herkunft": herkunft})
    entwurf.ungueltig = neu_ungueltig
    entwurf.zuletzt = time.monotonic()


def datum_iso(iso: str | None):
    from datetime import date

    return date.fromisoformat(iso) if iso else None


def bestaetige(entwurf: Entwurf, schluessel: str) -> None:
    """Ein Vorschlag (Herkunft 'auto') wird von der Ärztin/vom Arzt bestätigt."""
    if entwurf.angaben.herkunft.get(schluessel) == "auto":
        entwurf.angaben = entwurf.angaben.model_copy(update={"herkunft": {**entwurf.angaben.herkunft, schluessel: "arzt"}})


# =============================================================================================
# Auswertung
# =============================================================================================
def bewerte_entwurf(entwurf: Entwurf, fall: KisFall, melder: Melder, konfig: MelderKonfig, pakete: DemisPakete, jetzt: datetime) -> Stand:
    """Was ist noch offen? Schnell (ohne Validator), für die Live-Anzeige nach jeder Eingabe."""
    a = entwurf.angaben
    fragen_a = formular_fragen(pakete.fragebogen("Common"), a.allgemein, pakete)
    fragen_s = formular_fragen(pakete.fragebogen(a.kuerzel), a.spezifisch, pakete)
    offen: list[Offen] = []
    fehler: list[Offen] = []
    hinweise = list(fall.hinweise)

    bundle = None
    try:
        bundle = erzeuge_meldung(fall, a, melder, konfig, jetzt=jetzt)
    except MeldungNichtMoeglich as problem:
        fehler.append(Offen("kopf", str(problem), "fehler"))

    if bundle:
        text_nach_id = {f.link_id: (praefix, f.text) for praefix, fragen in (("a", fragen_a), ("s", fragen_s)) for f in fragen}
        for p in pruefe_fragebogen_antworten(bundle, pakete, streng=True):
            if p.schwere == "hinweis":
                hinweise.append(p.text)
                continue
            praefix, frage_text = text_nach_id.get(p.link_id or "", ("a", ""))
            ziel = f"{praefix}.{p.link_id}" if p.link_id else "kopf"
            if p.schwere == "offen":  # in der Liste genügt die Frage selbst
                offen.append(Offen(f"feld-{ziel}", f"„{frage_text}“" if frage_text else p.text, "offen"))
            else:
                fehler.append(Offen(f"feld-{ziel}", p.text, "fehler"))

    # Vorschläge, die noch bestätigt werden müssen
    for schluessel, quelle in a.herkunft.items():
        if quelle == "auto":
            gruppe, _, lid = schluessel.partition(".")
            praefix = "a" if gruppe == "allgemein" else "s"
            frage = next((f for f in (fragen_a if praefix == "a" else fragen_s) if f.link_id == lid), None)
            if frage:
                offen.append(Offen(f"feld-{praefix}.{lid}", f"Vorschlag bitte bestätigen: „{frage.text}“", "bestaetigen"))

    if a.spezifisch.get("immunization") == "yes" and not a.impfungen:
        offen.append(Offen("feld-impfstoff", "Bitte den Impfstoff angeben (Impfung wurde mit „Ja“ beantwortet).", "offen"))
    for name, roh in entwurf.ungueltig.items():
        fehler.append(Offen(f"feld-{name}", f"„{roh}“ ist kein gültiges Datum. Bitte TT.MM.JJJJ, MM.JJJJ oder JJJJ eingeben.", "fehler"))
    return Stand(fragen_a, fragen_s, offen, fehler, hinweise, bundle)
