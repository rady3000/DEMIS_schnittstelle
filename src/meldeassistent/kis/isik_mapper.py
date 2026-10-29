"""Übersetzt ISiK-FHIR-Ressourcen (Patient, Kontakt, Diagnose, Labor) in das interne Modell.

Reine Funktionen ohne Netzwerkzugriff: Sie sind leicht zu testen und enthalten die gesamte
Kenntnis darüber, wie ISiK Daten ablegt. Wo das KIS etwas nicht liefert, bleibt das Feld leer
(siehe modell/kis.py); es wird nie etwas erfunden.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from meldeassistent.kis.schnittstelle import KisDatenFehler
from meldeassistent.modell import (
    Adresse,
    Aufenthalt,
    Aufenthaltsabschnitt,
    Diagnose,
    Diagnosesicherheit,
    Geschlecht,
    Laborbefund,
    Patient,
    Verstorben,
)
from meldeassistent.modell.kis import vergleichswert

# --- Namensräume laut ISiK / deutschem Basisprofil ---------------------------------------------
KONTAKTEBENE = "http://fhir.de/CodeSystem/Kontaktebene"
ICD10GM_PRAEFIX = "http://fhir.de/CodeSystem/bfarm/icd-10-gm"
FACHABTEILUNG = "http://fhir.de/CodeSystem/dkgev/Fachabteilungsschluessel"
FACHABTEILUNG_ERWEITERT = "http://fhir.de/CodeSystem/dkgev/Fachabteilungsschluessel-erweitert"
EXT_GESCHLECHT_AMTLICH = "http://fhir.de/StructureDefinition/gender-amtlich-de"
EXT_DIAGNOSESICHERHEIT = "http://fhir.de/StructureDefinition/icd-10-gm-diagnosesicherheit"
EXT_ENTLASSUNGSGRUND = "http://fhir.de/StructureDefinition/Entlassungsgrund"
EXT_STRASSE = "http://hl7.org/fhir/StructureDefinition/iso21090-ADXP-streetName"
EXT_HAUSNUMMER = "http://hl7.org/fhir/StructureDefinition/iso21090-ADXP-houseNumber"

LAUFENDE_STATUS = {"in-progress", "onleave", "arrived", "triaged"}

_SICHERHEIT_NACH_KUERZEL = {
    "G": Diagnosesicherheit.GESICHERT,
    "V": Diagnosesicherheit.VERDACHT,
    "A": Diagnosesicherheit.AUSGESCHLOSSEN,
    "Z": Diagnosesicherheit.ZUSTAND_NACH,
}
_SICHERHEIT_NACH_STATUS = {
    "confirmed": Diagnosesicherheit.GESICHERT,
    "provisional": Diagnosesicherheit.VERDACHT,
    "unconfirmed": Diagnosesicherheit.VERDACHT,
    "differential": Diagnosesicherheit.VERDACHT,
    "refuted": Diagnosesicherheit.AUSGESCHLOSSEN,
}

_FHIR_ID = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")


# --- Hilfsfunktionen ---------------------------------------------------------------------------
def pruefe_fhir_id(wert: str) -> str:
    """FHIR-IDs bestehen nur aus Buchstaben, Ziffern, '-' und '.'; alles andere wird abgelehnt."""
    if not isinstance(wert, str) or not _FHIR_ID.match(wert):
        raise KisDatenFehler("Ungültige Fall-ID.")
    return wert


def id_aus_referenz(referenz: str | None, typ: str) -> str | None:
    """'Patient/abc' oder 'https://…/Patient/abc' -> 'abc'. Falscher Typ oder fehlend -> None."""
    if not referenz:
        return None
    teile = referenz.rstrip("/").split("/")
    if len(teile) >= 2 and teile[-2] == typ and _FHIR_ID.match(teile[-1]):
        return teile[-1]
    return None


def parse_datum(text: str | None) -> date | None:
    """Vollständiges Datum (auch aus einem Zeitstempel). Unvollständige Angaben ('2026-10') -> None."""
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]) if len(text) >= 10 else None
    except ValueError:
        return None


def parse_zeitpunkt(text: str | None) -> datetime | None:
    """Zeitstempel mit oder ohne Zeitzone. Nur ein Datum -> Mitternacht (ohne Zeitzone)."""
    if not text:
        return None
    try:
        return datetime.fromisoformat(text) if len(text) > 10 else datetime.fromisoformat(text + "T00:00:00")
    except ValueError:
        return None


def _erweiterungen(element: dict, url: str) -> list[dict]:
    return [e for e in element.get("extension", []) if e.get("url") == url]


def _coding_code(codeable: dict | None, system: str | None = None) -> str | None:
    for coding in (codeable or {}).get("coding", []):
        if system is None or coding.get("system") == system:
            return coding.get("code")
    return None


# --- Patient -----------------------------------------------------------------------------------
def _geschlecht(res: dict) -> Geschlecht:
    gender = res.get("gender")
    if gender == "male":
        return Geschlecht.MAENNLICH
    if gender == "female":
        return Geschlecht.WEIBLICH
    if gender == "other":
        # ISiK: "other" wird über die Erweiterung gender-amtlich-de genauer bestimmt (D = divers, X = unbestimmt)
        for ext in _erweiterungen(res.get("_gender", {}), EXT_GESCHLECHT_AMTLICH):
            code = ext.get("valueCoding", {}).get("code")
            if code == "D":
                return Geschlecht.DIVERS
            if code == "X":
                return Geschlecht.UNBESTIMMT
        return Geschlecht.UNBESTIMMT
    return Geschlecht.UNBEKANNT


def _adresse(res: dict) -> Adresse | None:
    adressen = res.get("address") or []
    if not adressen:
        return None
    # Wohnanschrift bevorzugen (ISiK: Straßenanschrift = type both/physical), Postfach nicht
    wahl = next((a for a in adressen if a.get("type") in ("both", "physical")), adressen[0])
    strasse = hausnummer = None
    for zeile in wahl.get("_line") or []:
        for e in (zeile or {}).get("extension", []):
            if e.get("url") == EXT_STRASSE:
                strasse = e.get("valueString")
            elif e.get("url") == EXT_HAUSNUMMER:
                hausnummer = e.get("valueString")
    return Adresse(
        zeilen=wahl.get("line", []),
        strasse=strasse,
        hausnummer=hausnummer,
        plz=wahl.get("postalCode"),
        ort=wahl.get("city"),
        land=wahl.get("country"),
    )


def patient_aus_fhir(res: dict) -> Patient:
    namen = res.get("name") or []
    if not namen:
        raise KisDatenFehler("Ein Patient im KIS hat keinen Namen.")
    name = next((n for n in namen if n.get("use") == "official"), namen[0])
    if not name.get("family") or not name.get("given"):
        raise KisDatenFehler("Ein Patient im KIS hat keinen vollständigen Namen (Vor- und Nachname).")

    telefon = email = None
    for t in res.get("telecom", []):
        if t.get("system") == "phone" and not telefon:
            telefon = t.get("value")
        elif t.get("system") == "email" and not email:
            email = t.get("value")

    patientennummer = next(
        (i.get("value") for i in res.get("identifier", []) if _coding_code(i.get("type")) == "MR"), None
    )

    verstorben, verstorben_am = Verstorben.UNBEKANNT, None
    if res.get("deceasedDateTime"):
        verstorben, verstorben_am = Verstorben.JA, parse_zeitpunkt(res["deceasedDateTime"])
    elif "deceasedBoolean" in res:
        verstorben = Verstorben.JA if res["deceasedBoolean"] else Verstorben.NEIN

    return Patient(
        kis_patienten_id=res["id"],
        patientennummer=patientennummer,
        vorname=" ".join(name["given"]),
        nachname=name["family"],
        geburtsdatum=parse_datum(res.get("birthDate")),
        geschlecht=_geschlecht(res),
        adresse=_adresse(res),
        telefon=telefon,
        email=email,
        verstorben=verstorben,
        verstorben_am=verstorben_am,
    )


# --- Aufenthalt --------------------------------------------------------------------------------
def abschnitt_aus_fhir(enc: dict) -> Aufenthaltsabschnitt:
    fachabteilung_schluessel = fachabteilung_name = None
    for coding in (enc.get("serviceType") or {}).get("coding", []):
        if coding.get("system") in (FACHABTEILUNG, FACHABTEILUNG_ERWEITERT):
            fachabteilung_schluessel, fachabteilung_name = coding.get("code"), coding.get("display")
            break

    orte = enc.get("location") or []
    aktiv = [o for o in orte if o.get("status") == "active"]
    ort = (aktiv or orte or [None])[-1]
    station = (ort or {}).get("location", {}).get("display") if ort else None

    periode = enc.get("period") or {}
    return Aufenthaltsabschnitt(
        station=station,
        fachabteilung_schluessel=fachabteilung_schluessel,
        fachabteilung_name=fachabteilung_name,
        beginn=parse_zeitpunkt(periode.get("start")),
        ende=parse_zeitpunkt(periode.get("end")),
    )


def ist_einrichtungskontakt(enc: dict) -> bool:
    return any(
        _coding_code(t, KONTAKTEBENE) == "einrichtungskontakt" for t in enc.get("type", [])
    )


def _entlassung_wegen_tod(enc: dict) -> bool:
    entlassung = (enc.get("hospitalization") or {}).get("dischargeDisposition") or {}
    if _coding_code(entlassung) == "exp":  # HL7: "expired"
        return True
    for ext in _erweiterungen(entlassung, EXT_ENTLASSUNGSGRUND):
        for teil in ext.get("extension", []):
            if teil.get("url") == "ErsteUndZweiteStelle" and teil.get("valueCoding", {}).get("code") == "07":
                return True  # Entlassungsgrund 07 = Tod
    return False


def aufenthalt_aus_fhir(enc: dict, abschnitte_fhir: list[dict]) -> Aufenthalt:
    periode = enc.get("period") or {}
    abschnitte = [abschnitt_aus_fhir(a) for a in abschnitte_fhir]
    # zeitlich ordnen; Abschnitte ohne Beginn ans Ende
    abschnitte.sort(key=lambda a: (a.beginn is None, vergleichswert(a.beginn) if a.beginn else datetime.max))
    besuchsnummer = next(
        (i.get("value") for i in enc.get("identifier", []) if _coding_code(i.get("type")) == "VN"), None
    )
    return Aufenthalt(
        kis_fall_id=enc["id"],
        besuchsnummer=besuchsnummer,
        laufend=enc.get("status") in LAUFENDE_STATUS,
        beginn=parse_zeitpunkt(periode.get("start")),
        ende=parse_zeitpunkt(periode.get("end")),
        entlassen_wegen_tod=_entlassung_wegen_tod(enc),
        abschnitte=abschnitte,
    )


# --- Diagnose ----------------------------------------------------------------------------------
def diagnose_aus_fhir(cond: dict) -> Diagnose:
    code = sicherheit = icd_text = None
    for coding in (cond.get("code") or {}).get("coding", []):
        if (coding.get("system") or "").startswith(ICD10GM_PRAEFIX):
            code = coding.get("code")
            icd_text = coding.get("display")
            for ext in _erweiterungen(coding, EXT_DIAGNOSESICHERHEIT):
                sicherheit = _SICHERHEIT_NACH_KUERZEL.get(ext.get("valueCoding", {}).get("code"))
            break
    if sicherheit is None:
        status = _coding_code(cond.get("verificationStatus"))
        sicherheit = _SICHERHEIT_NACH_STATUS.get(status, Diagnosesicherheit.UNBEKANNT)
    notizen = [n.get("text") for n in cond.get("note", []) if n.get("text")]
    return Diagnose(
        icd_code=code,
        icd_text=icd_text,
        freitext=(cond.get("code") or {}).get("text"),
        sicherheit=sicherheit,
        erkrankungsbeginn=parse_datum(cond.get("onsetDateTime")),
        erfasst_am=parse_datum(cond.get("recordedDate")),
        hinweis=" ".join(notizen) or None,
    )


# --- Labor (vereinfacht: DiagnosticReport + Observation) --------------------------------------
def _beobachtung_text(obs: dict) -> str | None:
    if obs.get("valueString"):
        return obs["valueString"]
    if "valueCodeableConcept" in obs:
        konzept = obs["valueCodeableConcept"]
        return konzept.get("text") or next((c.get("display") for c in konzept.get("coding", []) if c.get("display")), None)
    if "valueQuantity" in obs:
        menge = obs["valueQuantity"]
        return " ".join(str(x) for x in (menge.get("value"), menge.get("unit")) if x is not None) or None
    return None


def laborbefund_aus_fhir(report: dict, beobachtungen: dict[str, dict]) -> Laborbefund:
    """``beobachtungen``: Observation-Ressourcen, nach ID geordnet."""
    ergebnisse = []
    for ref in report.get("result", []):
        obs = beobachtungen.get(id_aus_referenz(ref.get("reference"), "Observation") or "")
        if obs and (text := _beobachtung_text(obs)):
            ergebnisse.append(text)
    code = report.get("code") or {}
    untersuchung = code.get("text") or next((c.get("display") for c in code.get("coding", []) if c.get("display")), None)
    performer = (report.get("performer") or [{}])[0].get("display")
    return Laborbefund(
        labornummer=next((i.get("value") for i in report.get("identifier", []) if i.get("value")), None),
        untersuchung=untersuchung,
        ergebnis="; ".join(ergebnisse) or None,
        datum=parse_zeitpunkt(report.get("effectiveDateTime") or report.get("issued")),
        labor=performer,
    )
