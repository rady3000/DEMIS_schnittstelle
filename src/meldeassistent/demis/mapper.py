"""Baut aus dem internen KIS-Modell und den Meldeangaben eine DEMIS-Erkrankungsmeldung (§ 6 IfSG).

Ergebnis ist ein FHIR-``Bundle`` (Typ ``document``) im Profil ``NotificationBundleDisease`` der Pakete
``rki.demis.common`` und ``rki.demis.disease`` 3.0.0. Aufbau und Codes stammen aus den Profilen und den
offiziellen Beispielen; was nicht belegt ist, wird nicht gesendet (Harte Regel 3).

Datenschutz (Regel 5): Es werden nur Angaben gesendet, die DEMIS vorsieht. Freitexte aus dem KIS (z. B.
Diagnosehinweise) gehen nie automatisch mit, nur was die Ärztin/der Arzt ausdrücklich schreibt. Die
Ressourcen-IDs sind frisch erzeugte UUIDs; es gelangen keine KIS-internen IDs in die Meldung.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Callable

from meldeassistent.modell import Geschlecht, KisFall

from .angaben import Laboreinrichtung, Meldeangaben, Melder, MelderKonfig, UNTERSTUETZTE_KUERZEL
from .fragebogen import baue_antworten
from .pakete import DemisPakete, standard_pakete

BASIS = "https://demis.rki.de/fhir"
PROFIL = f"{BASIS}/StructureDefinition/"
CS_NOTIFICATION_TYPE = f"{BASIS}/CodeSystem/notificationType"
CS_DISEASE_CATEGORY = f"{BASIS}/CodeSystem/notificationDiseaseCategory"
CS_ORG_TYPE = f"{BASIS}/CodeSystem/organizationType"
CS_ADDRESS_USE = f"{BASIS}/CodeSystem/addressUse"
CS_SECTION = f"{BASIS}/CodeSystem/sectionCode"
CS_SERVICE_TYPE = f"{BASIS}/CodeSystem/hospitalizationServiceType"
CS_HOSP_REASON = f"{BASIS}/CodeSystem/hospitalizationReason"
CS_BSNR = "https://fhir.kbv.de/NamingSystem/KBV_NS_Base_BSNR"
EXT_ADDRESS_USE = f"{BASIS}/StructureDefinition/AddressUse"
EXT_FACILITY_ADDRESS = f"{BASIS}/StructureDefinition/FacilityAddressNotifiedPerson"
EXT_GESCHLECHT = "http://fhir.de/StructureDefinition/gender-amtlich-de"
CS_GESCHLECHT = "http://fhir.de/CodeSystem/gender-amtlich-de"
KATEGORIE_ARZTMELDUNG = "6.1_2"  # Meldung gemäß § 6 Abs. 1, 2 IfSG


class MeldungNichtMoeglich(Exception):
    """Eine zwingend nötige Angabe fehlt, so dass keine Meldung gebaut werden kann (Text auf Deutsch)."""


def _uuid4() -> str:
    return str(uuid.uuid4())


def _coding(system: str, code: str, pakete: DemisPakete) -> dict:
    anzeige = pakete.codesystem_anzeige(system, code)
    return {"system": system, "code": code, **({"display": anzeige} if anzeige else {})}


def _adresse_fhir(a) -> dict:
    return {"line": [a.strasse], "city": a.ort, "postalCode": a.plz, "country": a.land}


def _verweis(typ: str, id_: str) -> dict:
    return {"reference": f"{typ}/{id_}"}


def _datum(wert: datetime | None) -> str | None:
    return wert.date().isoformat() if wert else None


# --- Einzelne Ressourcen -----------------------------------------------------------------------
def _patient(fall: KisFall, ids: dict, konfig: MelderKonfig) -> tuple[dict, dict]:
    """NotifiedPerson und die Betroffenen-Einrichtung (Klinik als derzeitiger Aufenthaltsort)."""
    p = fall.patient
    pat: dict = {
        "resourceType": "Patient",
        "id": ids["patient"],
        "meta": {"profile": [PROFIL + "NotifiedPerson"]},
        "name": [{"use": "official", "family": p.nachname, "given": p.vorname.split()}],
    }
    telecom = []
    if p.telefon:
        telecom.append({"system": "phone", "value": p.telefon})
    if p.email:
        telecom.append({"system": "email", "value": p.email})
    if telecom:
        pat["telecom"] = telecom

    if p.geschlecht is Geschlecht.MAENNLICH:
        pat["gender"] = "male"
    elif p.geschlecht is Geschlecht.WEIBLICH:
        pat["gender"] = "female"
    elif p.geschlecht in (Geschlecht.DIVERS, Geschlecht.UNBESTIMMT):
        pat["gender"] = "other"
        code, anzeige = ("D", "divers") if p.geschlecht is Geschlecht.DIVERS else ("X", "unbestimmt")
        pat["_gender"] = {"extension": [{"url": EXT_GESCHLECHT, "valueCoding": {"system": CS_GESCHLECHT, "code": code, "display": anzeige}}]}
    else:
        pat["gender"] = "unknown"
    if p.geburtsdatum:
        pat["birthDate"] = p.geburtsdatum.isoformat()

    adressen = []
    a = p.adresse
    if a and a.zeilen and a.plz and a.ort:
        adr: dict = {
            "extension": [{"url": EXT_ADDRESS_USE, "valueCoding": {"system": CS_ADDRESS_USE, "code": "primary"}}],
            "line": a.zeilen[:3],
            "city": a.ort,
            "postalCode": a.plz,
        }
        if a.land:
            adr["country"] = a.land
        adressen.append(adr)
    adressen.append(
        {
            "extension": [
                {"url": EXT_ADDRESS_USE, "valueCoding": {"system": CS_ADDRESS_USE, "code": "current"}},
                {"url": EXT_FACILITY_ADDRESS, "valueReference": _verweis("Organization", ids["betroffenen_einrichtung"])},
            ]
        }
    )
    pat["address"] = adressen

    e = konfig.einrichtung
    einrichtung = {
        "resourceType": "Organization",
        "id": ids["betroffenen_einrichtung"],
        "meta": {"profile": [PROFIL + "NotifiedPersonFacility"]},
        "type": [{"coding": [_coding(CS_ORG_TYPE, e.art, standard_pakete())]}],
        "name": e.name,
        "address": [_adresse_fhir(e.anschrift)],
    }
    return pat, einrichtung


def _melder_ressourcen(melder: Melder, konfig: MelderKonfig, ids: dict, pakete: DemisPakete) -> list[dict]:
    e = konfig.einrichtung
    identifier = []
    if e.bsnr:
        identifier.append({"system": CS_BSNR, "value": e.bsnr})
    if e.demis_teilnehmer_id:
        identifier.append({"system": f"{BASIS}/NamingSystem/DemisParticipantId", "value": e.demis_teilnehmer_id})
    telecom = [{"system": "phone", "value": e.telefon, "use": "work"}]
    if e.email:
        telecom.append({"system": "email", "value": e.email, "use": "work"})
    einrichtung: dict = {
        "resourceType": "Organization",
        "id": ids["melder_einrichtung"],
        "meta": {"profile": [PROFIL + "NotifierFacility"]},
        "type": [{"coding": [_coding(CS_ORG_TYPE, e.art, pakete)]}],
        "name": e.name,
        "telecom": telecom,
        "address": [_adresse_fhir(e.anschrift)],
    }
    if identifier:
        einrichtung["identifier"] = identifier
    person = {
        "resourceType": "Practitioner",
        "id": ids["melder"],
        "meta": {"profile": [PROFIL + "Notifier"]},
        "name": [{"use": "official", "family": melder.nachname, "given": [melder.vorname]}],
        "telecom": [{"system": "phone", "value": melder.telefon, "use": "work"}],
    }
    rolle = {
        "resourceType": "PractitionerRole",
        "id": ids["melder_rolle"],
        "meta": {"profile": [PROFIL + "NotifierRole"]},
        "practitioner": _verweis("Practitioner", ids["melder"]),
        "organization": _verweis("Organization", ids["melder_einrichtung"]),
    }
    return [einrichtung, person, rolle]


def _labor(labor: Laboreinrichtung, id_: str, pakete: DemisPakete) -> dict:
    org: dict = {
        "resourceType": "Organization",
        "id": id_,
        # DEMIS verlangt an jeder Ressource ein meta.profile; für das Labor gibt es kein DEMIS-Profil
        "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/Organization"]},
        "type": [{"coding": [_coding(CS_ORG_TYPE, labor.art, pakete)]}],
        "name": labor.name,
    }
    if labor.telefon:
        org["telecom"] = [{"system": "phone", "value": labor.telefon, "use": "work"}]
    if labor.anschrift:
        org["address"] = [_adresse_fhir(labor.anschrift)]
    return org


def _hospitalisierungen(fall: KisFall, angaben: Meldeangaben, ids: dict, pakete: DemisPakete) -> list[dict]:
    """Je Aufenthaltsabschnitt (Station/Fachabteilung) ein Hospitalization-Encounter."""
    a = fall.aufenthalt
    abschnitte = a.abschnitte or [None]
    erlaubte_abteilungen = {k.code for k in pakete.wertemenge(f"{BASIS}/ValueSet/hospitalizationServiceType").konzepte or []}
    ergebnis = []
    for nummer, abschnitt in enumerate(abschnitte):
        beginn = _datum(abschnitt.beginn if abschnitt else None) or _datum(a.beginn)
        if not beginn:
            raise MeldungNichtMoeglich("Das Aufnahmedatum des Krankenhausaufenthalts fehlt im KIS.")
        ende = _datum(abschnitt.ende if abschnitt else a.ende)
        enc: dict = {
            "resourceType": "Encounter",
            "id": ids["hospitalisierungen"][nummer],
            "meta": {"profile": [PROFIL + "Hospitalization"]},
            "status": "finished" if ende else "in-progress",
            "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP", "display": "inpatient encounter"},
            "subject": _verweis("Patient", ids["patient"]),
            "period": {"start": beginn, **({"end": ende} if ende else {})},
            "serviceProvider": _verweis("Organization", ids["betroffenen_einrichtung"]),
        }
        schluessel = abschnitt.fachabteilung_schluessel if abschnitt else None
        if schluessel in erlaubte_abteilungen:
            enc["serviceType"] = {"coding": [_coding(CS_SERVICE_TYPE, schluessel, pakete)]}
        if angaben.hospitalisierungsgrund:
            enc["reasonCode"] = [{"coding": [_coding(CS_HOSP_REASON, angaben.hospitalisierungsgrund, pakete)]}]
        ergebnis.append(enc)
    return ergebnis


def _condition(angaben: Meldeangaben, ids: dict, pakete: DemisPakete) -> dict:
    k = angaben.kuerzel
    cond: dict = {
        "resourceType": "Condition",
        "id": ids["condition"],
        "meta": {"profile": [PROFIL + f"Disease{k}"]},
        "verificationStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "unconfirmed" if angaben.verdacht else "confirmed"}]
        },
        "code": {"coding": [_coding(CS_DISEASE_CATEGORY, k.lower(), pakete)]},
        "subject": _verweis("Patient", ids["patient"]),
    }
    if angaben.erkrankungsbeginn:
        cond["onsetDateTime"] = angaben.erkrankungsbeginn.isoformat()
    if angaben.diagnosedatum:
        cond["recordedDate"] = angaben.diagnosedatum.isoformat()
    if angaben.diagnosehinweis:
        cond["note"] = [{"text": angaben.diagnosehinweis}]
    if k == "MSVD" and angaben.symptome:
        wm = pakete.wertemenge(f"{BASIS}/ValueSet/evidenceMSVD")
        evidenz = []
        for code in angaben.symptome:
            konzept = wm.finde(code)
            if konzept is None:
                raise MeldungNichtMoeglich(f"Das Symptom '{code}' ist für Masern nicht vorgesehen.")
            evidenz.append({"code": [{"coding": [{"system": konzept.system, "code": konzept.code, **({"display": konzept.display} if konzept.display else {})}]}]})
        cond["evidence"] = evidenz
    return cond


def _impfung(imp, ids_imp: str, kuerzel: str, ids: dict, pakete: DemisPakete) -> dict:
    wm = pakete.wertemenge(f"{BASIS}/ValueSet/vaccine{kuerzel}")
    konzept = wm.finde(imp.impfstoff_code)
    if konzept is None:
        raise MeldungNichtMoeglich(f"Der Impfstoff '{imp.impfstoff_code}' ist für diese Krankheit nicht vorgesehen.")
    res: dict = {
        "resourceType": "Immunization",
        "id": ids_imp,
        "meta": {"profile": [PROFIL + f"ImmunizationInformation{kuerzel}"]},
        "status": "completed",
        "vaccineCode": {"coding": [{"system": konzept.system, "code": konzept.code, **({"display": konzept.display} if konzept.display else {})}]},
        "patient": _verweis("Patient", ids["patient"]),
    }
    if imp.datum:
        res["occurrenceDateTime"] = imp.datum
    if imp.anmerkung:
        res["note"] = [{"text": imp.anmerkung}]
    return res


def _fragebogen_antwort(name: str, items: list[dict], ids: dict, pakete: DemisPakete) -> dict:
    profil = "DiseaseInformationCommon" if name == "Common" else f"DiseaseInformation{name}"
    return {
        "resourceType": "QuestionnaireResponse",
        "id": ids["qr_" + name],
        "meta": {"profile": [PROFIL + profil]},
        "questionnaire": pakete.fragebogen_url(name),
        "status": "completed",
        "subject": _verweis("Patient", ids["patient"]),
        "item": items,
    }


# --- Gesamtmeldung -----------------------------------------------------------------------------
def erzeuge_meldung(
    fall: KisFall,
    angaben: Meldeangaben,
    melder: Melder,
    konfig: MelderKonfig,
    *,
    jetzt: datetime,
    pakete: DemisPakete | None = None,
    neue_id: Callable[[], str] = _uuid4,
) -> dict:
    """Baut das Meldungs-Bundle. ``jetzt`` muss eine Zeitzone haben. ``neue_id`` ist für Tests austauschbar."""
    if angaben.kuerzel not in UNTERSTUETZTE_KUERZEL:
        raise MeldungNichtMoeglich(f"Für '{angaben.kuerzel}' ist die Meldung noch nicht umgesetzt.")
    if jetzt.tzinfo is None:
        raise ValueError("'jetzt' braucht eine Zeitzone")
    pakete = pakete or standard_pakete()
    k = angaben.kuerzel
    anzahl_hosp = max(len(fall.aufenthalt.abschnitte), 1)

    ids = {
        "bundle": neue_id(),
        "meldung": neue_id(),
        "composition": neue_id(),
        "patient": neue_id(),
        "betroffenen_einrichtung": neue_id(),
        "condition": neue_id(),
        "melder_einrichtung": neue_id(),
        "melder": neue_id(),
        "melder_rolle": neue_id(),
        "labor": neue_id(),
        "qr_Common": neue_id(),
        f"qr_{k}": neue_id(),
        "hospitalisierungen": [neue_id() for _ in range(anzahl_hosp)],
        "impfungen": [neue_id() for _ in angaben.impfungen],
    }

    # Verweise in den Fragebogen-Antworten ergänzen (die der Mapper selbst erzeugt)
    allgemein = dict(angaben.allgemein)
    spezifisch = dict(angaben.spezifisch)
    ressourcen_labor: list[dict] = []
    laboreinrichtung = angaben.labor or konfig.hauslabor
    if allgemein.get("labSpecimenTaken") == "yes" and laboreinrichtung:
        allgemein["labSpecimenLab"] = f"Organization/{ids['labor']}"
        ressourcen_labor.append(_labor(laboreinrichtung, ids["labor"], pakete))
    hospitalisierungen: list[dict] = []
    if allgemein.get("hospitalized") == "yes":
        hospitalisierungen = _hospitalisierungen(fall, angaben, ids, pakete)
        allgemein["hospitalizedGroup"] = [{"hospitalizedEncounter": f"Encounter/{h['id']}"} for h in hospitalisierungen]
    impfungen = [_impfung(i, ids["impfungen"][n], k, ids, pakete) for n, i in enumerate(angaben.impfungen)]
    if spezifisch.get("immunization") == "yes" and impfungen:
        spezifisch["immunizationRef"] = [f"Immunization/{i['id']}" for i in impfungen]

    qr_common = _fragebogen_antwort("Common", baue_antworten(pakete.fragebogen("Common"), allgemein, pakete), ids, pakete)
    qr_spezifisch = _fragebogen_antwort(k, baue_antworten(pakete.fragebogen(k), spezifisch, pakete), ids, pakete)

    patient, betroffenen_einrichtung = _patient(fall, ids, konfig)
    condition = _condition(angaben, ids, pakete)
    melder_ressourcen = _melder_ressourcen(melder, konfig, ids, pakete)
    zeit = jetzt.isoformat()

    composition = {
        "resourceType": "Composition",
        "id": ids["composition"],
        "meta": {"profile": [PROFIL + f"NotificationDisease{k}"]},
        "identifier": {"system": f"{BASIS}/NamingSystem/NotificationId", "value": ids["meldung"]},
        "status": "final",
        "type": {"coding": [{"system": "http://loinc.org", "code": "34782-3", "display": "Infectious disease Note"}]},
        "category": [{"coding": [_coding(CS_NOTIFICATION_TYPE, KATEGORIE_ARZTMELDUNG, pakete)]}],
        "subject": _verweis("Patient", ids["patient"]),
        "date": zeit,
        "author": [_verweis("PractitionerRole", ids["melder_rolle"])],
        "title": "Meldung gemäß §6 Absatz 1, 2 IfSG",
        "section": [
            _abschnitt("diagnosis", "Diagnose", _verweis("Condition", ids["condition"])),
            _abschnitt(
                "generalClinAndEpiInformation",
                "Meldetatbestandsübergreifende klinische und epidemiologische Angaben",
                _verweis("QuestionnaireResponse", ids["qr_Common"]),
            ),
            _abschnitt(
                "specificClinAndEpiInformation",
                "Meldetatbestandsspezifische klinische und epidemiologische Angaben",
                _verweis("QuestionnaireResponse", ids[f"qr_{k}"]),
            ),
        ],
    }

    reihenfolge = [composition, betroffenen_einrichtung, patient, condition, *impfungen, *melder_ressourcen, *ressourcen_labor, *hospitalisierungen, qr_common, qr_spezifisch]
    return {
        "resourceType": "Bundle",
        "id": ids["bundle"],
        "meta": {"profile": [PROFIL + "NotificationBundleDisease"]},
        "identifier": {"system": f"{BASIS}/NamingSystem/NotificationBundleId", "value": neue_id()},
        "type": "document",
        "timestamp": zeit,
        "entry": [{"fullUrl": f"{BASIS}/{r['resourceType']}/{r['id']}", "resource": r} for r in reihenfolge],
    }


def _abschnitt(code: str, titel: str, eintrag: dict) -> dict:
    return {
        "title": titel,
        "code": {"coding": [{"system": CS_SECTION, "code": code, "display": titel}]},
        "entry": [eintrag],
    }
