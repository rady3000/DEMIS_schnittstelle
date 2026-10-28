"""Vorbelegung der Meldeangaben aus den KIS-Daten.

Alles, was das KIS sicher weiß, wird vorausgefüllt (Herkunft ``kis``); fachliche Vorschläge sind
Herkunft ``auto`` und müssen von der Ärztin/vom Arzt bestätigt werden. Was fehlt, bleibt leer: Der
Fragebogen füllt Ja/Nein-Fragen dann mit "nicht erhoben" vor, Pflichtfragen ohne Vorgabe meldet die
Prüfung. Es wird nie geraten.

Hinweis: Die Zuordnung ICD-10-GM -> Meldetatbestand ist hier nur das Nötigste für die ersten drei
Krankheiten. Das vollständige, von der Hygiene pflegbare Regelwerk (YAML) folgt in Phase 6.
"""

from __future__ import annotations

from meldeassistent.modell import Diagnose, Diagnosesicherheit, KisFall, Verstorben

from .angaben import Meldeangaben, MelderKonfig

# Vorläufig (Phase 6 ersetzt das durch das YAML-Regelwerk): ICD-10-GM-Präfixe je DEMIS-Kürzel
ICD_PRAEFIXE = {
    "CDFD": ("A04.7",),
    "MYTD": ("A15", "A16", "A17", "A18", "A19"),
    "MSVD": ("B05",),
}

ITS_SCHWERER_VERLAUF_CDFD = "186431008:{288556008=305351004}"  # Aufnahme auf eine Intensivstation aufgrund der Erkrankung


def finde_diagnose(fall: KisFall, kuerzel: str) -> Diagnose | None:
    """Die erste Diagnose des Falls, die zum Meldetatbestand passt."""
    for d in fall.diagnosen:
        if d.icd_code and d.icd_code.startswith(ICD_PRAEFIXE[kuerzel]):
            return d
    return None


def vorbelegung(fall: KisFall, kuerzel: str, konfig: MelderKonfig) -> Meldeangaben:
    herkunft: dict[str, str] = {}
    allgemein: dict = {}
    spezifisch: dict = {}

    diagnose = finde_diagnose(fall, kuerzel)
    verdacht = bool(diagnose and diagnose.sicherheit is Diagnosesicherheit.VERDACHT)
    if diagnose:
        herkunft["diagnose"] = "kis"

    # Tod: nur, wenn das KIS es ausdrücklich sagt
    p, a = fall.patient, fall.aufenthalt
    if p.verstorben is Verstorben.JA or (p.verstorben is Verstorben.UNBEKANNT and a.entlassen_wegen_tod):
        allgemein["isDead"] = "yes"
        todestag = p.verstorben_am or a.ende
        if todestag:
            allgemein["deathDate"] = todestag.date().isoformat()
        herkunft["allgemein.isDead"] = "kis"
    elif p.verstorben is Verstorben.NEIN:
        allgemein["isDead"] = "no"
        herkunft["allgemein.isDead"] = "kis"

    allgemein["hospitalized"] = "yes"  # ein stationärer Fall liegt vor
    herkunft["allgemein.hospitalized"] = "kis"

    if fall.laborbefunde:
        allgemein["labSpecimenTaken"] = "yes"
        herkunft["allgemein.labSpecimenTaken"] = "kis"

    if kuerzel == "CDFD" and a.hatte_intensivstation:
        spezifisch["form"] = ITS_SCHWERER_VERLAUF_CDFD
        herkunft["spezifisch.form"] = "auto"  # Vorschlag: Arzt bestätigt, dass die ITS wegen der Erkrankung nötig war

    return Meldeangaben(
        kuerzel=kuerzel,
        verdacht=verdacht,
        allgemein=allgemein,
        spezifisch=spezifisch,
        erkrankungsbeginn=diagnose.erkrankungsbeginn if diagnose else None,
        diagnosedatum=diagnose.erfasst_am if diagnose else None,
        labor=konfig.hauslabor if fall.laborbefunde else None,
        herkunft=herkunft,
    )


def ergaenze(angaben: Meldeangaben, *, allgemein: dict | None = None, spezifisch: dict | None = None, **felder) -> Meldeangaben:
    """Fügt Angaben der Ärztin/des Arztes hinzu (Herkunft ``arzt``). Vorhandene Werte werden überschrieben."""
    herkunft = dict(angaben.herkunft)
    for gruppe, werte in (("allgemein", allgemein), ("spezifisch", spezifisch)):
        for schluessel in werte or {}:
            herkunft[f"{gruppe}.{schluessel}"] = "arzt"
    for schluessel in felder:
        herkunft[schluessel] = "arzt"
    return angaben.model_copy(
        update={
            "allgemein": {**angaben.allgemein, **(allgemein or {})},
            "spezifisch": {**angaben.spezifisch, **(spezifisch or {})},
            "herkunft": herkunft,
            **felder,
        }
    )
