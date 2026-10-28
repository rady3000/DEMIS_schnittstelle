"""Tests der DEMIS-Meldung: Aufbau (Mapper), Datenschutz, offizieller Validator und deutsche Fehlertexte.

KIS-Daten stammen aus den synthetischen Testfällen (Fake-Server, ohne Docker). Die Validator-Tests
brauchen Java und die geladenen Pakete (python tools/einrichten.py); sonst werden sie übersprungen.
"""

import copy
import json
import re
import uuid

import pytest

from demis_faelle import FAELLE, JETZT, KONFIG, MELDER, lade
from meldeassistent.demis.angaben import Impfung, Meldeangaben
from meldeassistent.demis.fehlertexte import Problem, uebersetze
from meldeassistent.demis.mapper import MeldungNichtMoeglich, erzeuge_meldung
from meldeassistent.demis.meldung import pruefe_meldung
from meldeassistent.demis.vorbelegung import ergaenze, vorbelegung
from meldeassistent.modell import Geschlecht

PROFIL = "https://demis.rki.de/fhir/StructureDefinition/"


def baue(name: str, **aenderungen):
    fall, angaben = lade(name)
    if aenderungen:
        angaben = angaben.model_copy(update=aenderungen)
    return fall, erzeuge_meldung(fall, angaben, MELDER, KONFIG, jetzt=JETZT)


def ressourcen(bundle: dict, typ: str) -> list[dict]:
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == typ]


def zaehler_ids():
    """Erzeugt vorhersagbare UUIDs, damit Tests reproduzierbar sind."""
    n = iter(range(1, 1000))
    return lambda: str(uuid.UUID(int=next(n)))


# =============================================================================================
# Aufbau
# =============================================================================================
@pytest.mark.parametrize("name,kuerzel", [("cdi", "CDFD"), ("tb", "MYTD"), ("masern", "MSVD"), ("cdi_tot", "CDFD")])
def test_bundle_hat_den_erwarteten_aufbau(pakete, name, kuerzel):
    _, b = baue(name)
    assert b["resourceType"] == "Bundle" and b["type"] == "document"
    assert b["meta"]["profile"] == [PROFIL + "NotificationBundleDisease"]
    comp = b["entry"][0]["resource"]
    assert comp["resourceType"] == "Composition"  # Composition steht an erster Stelle
    assert comp["meta"]["profile"] == [PROFIL + f"NotificationDisease{kuerzel}"]
    assert comp["category"][0]["coding"][0]["code"] == "6.1_2"
    assert [s["code"]["coding"][0]["code"] for s in comp["section"]] == [
        "diagnosis", "generalClinAndEpiInformation", "specificClinAndEpiInformation",
    ]
    cond = ressourcen(b, "Condition")[0]
    assert cond["code"]["coding"][0]["code"] == kuerzel.lower()
    assert cond["meta"]["profile"] == [PROFIL + f"Disease{kuerzel}"]


def test_jede_ressource_hat_ein_profil_und_alle_verweise_zeigen_ins_bundle(pakete):
    _, b = baue("cdi")
    vorhanden = {f"{e['resource']['resourceType']}/{e['resource']['id']}" for e in b["entry"]}
    for e in b["entry"]:
        r = e["resource"]
        assert r["meta"]["profile"], f"{r['resourceType']} ohne meta.profile"
        assert e["fullUrl"] == f"https://demis.rki.de/fhir/{r['resourceType']}/{r['id']}"
    for ziel in re.findall(r'"reference": "([^"]+)"', json.dumps(b)):
        assert ziel in vorhanden, f"Verweis ins Leere: {ziel}"


def test_ids_sind_uuids_und_eindeutig(pakete):
    _, b = baue("cdi")
    ids = [e["resource"]["id"] for e in b["entry"]]
    assert len(ids) == len(set(ids))
    for i in ids + [b["id"], b["identifier"]["value"], b["entry"][0]["resource"]["identifier"]["value"]]:
        uuid.UUID(i)


def test_reproduzierbar_mit_festen_ids(pakete):
    fall, angaben = lade("cdi")
    a = erzeuge_meldung(fall, angaben, MELDER, KONFIG, jetzt=JETZT, neue_id=zaehler_ids())
    b = erzeuge_meldung(fall, angaben, MELDER, KONFIG, jetzt=JETZT, neue_id=zaehler_ids())
    assert a == b


def test_zwei_meldungen_haben_unterschiedliche_ids(pakete):
    fall, angaben = lade("cdi")
    a = erzeuge_meldung(fall, angaben, MELDER, KONFIG, jetzt=JETZT)
    b = erzeuge_meldung(fall, angaben, MELDER, KONFIG, jetzt=JETZT)
    assert a["id"] != b["id"] and a["entry"][0]["resource"]["identifier"] != b["entry"][0]["resource"]["identifier"]


def test_zeitzone_ist_pflicht(pakete):
    from datetime import datetime

    fall, angaben = lade("cdi")
    with pytest.raises(ValueError, match="Zeitzone"):
        erzeuge_meldung(fall, angaben, MELDER, KONFIG, jetzt=datetime(2026, 10, 28, 12, 0))


def test_patient_daten_stammen_aus_dem_kis(pakete):
    _, b = baue("cdi")
    p = ressourcen(b, "Patient")[0]
    assert p["name"] == [{"use": "official", "family": "Testpatient", "given": ["Anna"]}]
    assert p["gender"] == "female" and p["birthDate"] == "1948-03-14"
    primaer = next(a for a in p["address"] if a["extension"][0]["valueCoding"]["code"] == "primary")
    assert primaer["line"] == ["Musterstraße 12"] and primaer["postalCode"] == "09117" and primaer["city"] == "Chemnitz"
    aktuell = next(a for a in p["address"] if a["extension"][0]["valueCoding"]["code"] == "current")
    assert aktuell["extension"][1]["valueReference"]["reference"].startswith("Organization/")  # Klinik als Aufenthaltsort


@pytest.mark.parametrize("geschlecht,erwartet,code", [(Geschlecht.DIVERS, "other", "D"), (Geschlecht.UNBESTIMMT, "other", "X"), (Geschlecht.UNBEKANNT, "unknown", None)])
def test_geschlecht_divers_unbestimmt_unbekannt(pakete, geschlecht, erwartet, code):
    fall, angaben = lade("cdi")
    fall = fall.model_copy(update={"patient": fall.patient.model_copy(update={"geschlecht": geschlecht})})
    p = ressourcen(erzeuge_meldung(fall, angaben, MELDER, KONFIG, jetzt=JETZT), "Patient")[0]
    assert p["gender"] == erwartet
    assert (p.get("_gender", {}).get("extension", [{}])[0].get("valueCoding", {}).get("code")) == code


def test_patient_ohne_wohnanschrift_hat_nur_den_aufenthaltsort(pakete):
    fall, angaben = lade("cdi")
    fall = fall.model_copy(update={"patient": fall.patient.model_copy(update={"adresse": None})})
    p = ressourcen(erzeuge_meldung(fall, angaben, MELDER, KONFIG, jetzt=JETZT), "Patient")[0]
    assert [a["extension"][0]["valueCoding"]["code"] for a in p["address"]] == ["current"]


def test_krankenhausaufenthalt_je_abschnitt_mit_fachabteilung(pakete):
    _, b = baue("cdi")
    hosp = ressourcen(b, "Encounter")
    assert [h["serviceType"]["coding"][0]["code"] for h in hosp] == ["0100", "3600"]  # Innere, dann Intensivmedizin
    assert [h["status"] for h in hosp] == ["finished", "in-progress"]
    assert hosp[0]["period"] == {"start": "2026-10-12", "end": "2026-10-16"}
    assert hosp[1]["period"] == {"start": "2026-10-16"}  # nur Datum, keine Uhrzeit
    qr = ressourcen(b, "QuestionnaireResponse")[0]
    frage = next(i for i in qr["item"] if i["linkId"] == "hospitalized")
    gruppen = frage["answer"][0]["item"]
    assert len(gruppen) == 2  # eine Gruppe je Aufenthaltsabschnitt


def test_tod_kommt_aus_dem_kis(pakete):
    _, b = baue("cdi_tot")
    qr = ressourcen(b, "QuestionnaireResponse")[0]
    tod = next(i for i in qr["item"] if i["linkId"] == "isDead")["answer"][0]
    assert tod["valueCoding"]["code"] == "yes"
    assert tod["item"] == [{"linkId": "deathDate", "answer": [{"valueDate": "2026-10-22"}]}]


def test_melder_und_einrichtung(pakete):
    _, b = baue("cdi")
    einr = next(o for o in ressourcen(b, "Organization") if o["meta"]["profile"][0].endswith("NotifierFacility"))
    assert einr["name"] == "DRK Krankenhaus Chemnitz-Rabenstein gGmbH"
    assert einr["type"][0]["coding"][0]["code"] == "hospital"
    assert einr["address"][0]["line"] == ["Unritzstraße 23"]
    assert einr["identifier"][0]["value"] == "123456789"
    person = ressourcen(b, "Practitioner")[0]
    assert person["name"][0]["family"] == "Ärztin" and person["telecom"][0]["system"] == "phone"
    rolle = ressourcen(b, "PractitionerRole")[0]
    assert rolle["practitioner"]["reference"] == f"Practitioner/{person['id']}"
    assert b["entry"][0]["resource"]["author"][0]["reference"] == f"PractitionerRole/{rolle['id']}"


def test_verdacht_wird_aus_der_diagnosesicherheit_vorbelegt(pakete):
    _, b_masern = baue("masern")
    assert ressourcen(b_masern, "Condition")[0]["verificationStatus"]["coding"][0]["code"] == "unconfirmed"
    _, b_cdi = baue("cdi")
    assert ressourcen(b_cdi, "Condition")[0]["verificationStatus"]["coding"][0]["code"] == "confirmed"


def test_masern_symptome_und_impfung(pakete):
    fall, angaben = lade("masern")
    angaben = ergaenze(angaben, spezifisch={"immunization": "yes"}, impfungen=[Impfung(impfstoff_code="2241000221103", datum="2022-04-20")])
    b = erzeuge_meldung(fall, angaben, MELDER, KONFIG, jetzt=JETZT)
    cond = ressourcen(b, "Condition")[0]
    assert [e["code"][0]["coding"][0]["code"] for e in cond["evidence"]] == ["386661006", "64611009", "247471006:{363698007=181469002}"]
    imp = ressourcen(b, "Immunization")[0]
    assert imp["vaccineCode"]["coding"][0]["code"] == "2241000221103" and imp["occurrenceDateTime"] == "2022-04-20"
    qr = ressourcen(b, "QuestionnaireResponse")[1]
    ref = next(i for i in qr["item"] if i["linkId"] == "immunization")["answer"][0]["item"][0]["answer"][0]["valueReference"]["reference"]
    assert ref == f"Immunization/{imp['id']}"


def test_ungueltiges_symptom_und_ungueltiger_impfstoff_werden_abgelehnt(pakete):
    fall, angaben = lade("masern")
    with pytest.raises(MeldungNichtMoeglich, match="Symptom"):
        erzeuge_meldung(fall, angaben.model_copy(update={"symptome": ["12345"]}), MELDER, KONFIG, jetzt=JETZT)
    with pytest.raises(MeldungNichtMoeglich, match="Impfstoff"):
        erzeuge_meldung(fall, angaben.model_copy(update={"impfungen": [Impfung(impfstoff_code="999")]}), MELDER, KONFIG, jetzt=JETZT)


def test_nicht_umgesetzte_krankheit_wird_abgelehnt(pakete):
    from pydantic import ValidationError

    fall, angaben = lade("cdi")
    with pytest.raises(ValidationError):  # schon die Eingabe lässt nur CDFD, MYTD, MSVD zu
        Meldeangaben(kuerzel="HBVD")
    umgangen = Meldeangaben.model_construct(**{**angaben.model_dump(), "kuerzel": "HBVD"})  # Eingabeprüfung umgangen
    with pytest.raises(MeldungNichtMoeglich, match="noch nicht umgesetzt"):
        erzeuge_meldung(fall, umgangen, MELDER, KONFIG, jetzt=JETZT)


def test_ohne_aufnahmedatum_keine_meldung(pakete):
    fall, angaben = lade("cdi")
    aufenthalt = fall.aufenthalt.model_copy(update={"beginn": None, "abschnitte": []})
    with pytest.raises(MeldungNichtMoeglich, match="Aufnahmedatum"):
        erzeuge_meldung(fall.model_copy(update={"aufenthalt": aufenthalt}), angaben, MELDER, KONFIG, jetzt=JETZT)


# =============================================================================================
# Datenschutz (Harte Regel 5): Datensparsamkeit
# =============================================================================================
@pytest.mark.parametrize("name", list(FAELLE))
def test_keine_kis_interne_ids_und_keine_freitexte_im_bundle(pakete, name):
    fall, angaben = lade(name)
    text = json.dumps(erzeuge_meldung(fall, angaben, MELDER, KONFIG, jetzt=JETZT), ensure_ascii=False)
    # KIS-interne IDs (Fall-, Patienten-, Diagnose-IDs) dürfen nicht in die Meldung gelangen
    for kennung in (fall.patient.kis_patienten_id, fall.aufenthalt.kis_fall_id, fall.aufenthalt.besuchsnummer, fall.patient.patientennummer):
        assert kennung and kennung not in text
    # Freitext aus dem KIS (Diagnosehinweis) geht nie automatisch mit
    for diagnose in fall.diagnosen:
        assert diagnose.hinweis and diagnose.hinweis not in text
    # Laborbefunde und ICD-Codes gehören nicht in die Meldung
    for befund in fall.laborbefunde:
        assert befund.labornummer not in text
    assert not re.search(r"\b[A-Z]\d\d\.\d\b", text)


def test_freitext_nur_wenn_der_arzt_ihn_schreibt(pakete):
    fall, angaben = lade("cdi")
    b = erzeuge_meldung(fall, angaben.model_copy(update={"diagnosehinweis": "OP am 13.04."}), MELDER, KONFIG, jetzt=JETZT)
    assert ressourcen(b, "Condition")[0]["note"] == [{"text": "OP am 13.04."}]


# =============================================================================================
# Offizieller Validator
# =============================================================================================
@pytest.mark.parametrize("name", list(FAELLE))
def test_testfaelle_werden_vom_validator_ohne_fehler_akzeptiert(pakete, validator, name):
    """Akzeptanzkriterium Phase 3: Für alle DEMIS-Testfälle entsteht eine Meldung ohne Validator-Fehler."""
    _, b = baue(name)
    ergebnis = pruefe_meldung(b, validator)
    assert ergebnis.ok, [str(p) for p in ergebnis.fehler]
    assert ergebnis.hinweise == [], [str(p) for p in ergebnis.hinweise]


def test_vorbelegter_bogen_ist_formal_gueltig_aber_noch_nicht_vollstaendig(pakete, validator):
    fall, angaben = lade("cdi")
    vorbel = vorbelegung(fall, "CDFD", KONFIG)  # ohne Ergänzungen der Ärztin/des Arztes
    b = erzeuge_meldung(fall, vorbel, MELDER, KONFIG, jetzt=JETZT)
    ergebnis = pruefe_meldung(b, validator, streng=True)
    assert ergebnis.ok and not ergebnis.vollstaendig
    offen = " ".join(p.text for p in ergebnis.offen)
    assert "Ist die Person verstorben?" in offen and "Mit welcher Methode" in offen


def test_vollstaendige_angaben_sind_im_strengen_modus_in_ordnung(pakete, validator):
    _, b = baue("cdi")
    assert pruefe_meldung(b, validator, streng=True).vollstaendig


def aendere(bundle: dict, typ: str, funktion) -> dict:
    kopie = copy.deepcopy(bundle)
    for e in kopie["entry"]:
        if e["resource"]["resourceType"] == typ:
            funktion(e["resource"])
    return kopie


@pytest.mark.parametrize(
    "beschreibung,typ,aenderung,erwartet",
    [
        ("Vorname fehlt", "Patient", lambda r: r["name"][0].pop("given"), "Betroffene Person: Pflichtangabe fehlt: Vorname."),
        ("Nachname fehlt", "Patient", lambda r: r["name"][0].pop("family"), "Pflichtangabe fehlt: Nachname"),
        ("Geschlecht fehlt", "Patient", lambda r: r.pop("gender"), "Pflichtangabe fehlt: Geschlecht"),
        ("Geschlecht ungültig", "Patient", lambda r: r.update(gender="x"), "Ungültiges Geschlecht „x“"),
        ("Meldetatbestand falsch", "Condition", lambda r: r["code"]["coding"][0].update(code="cdfx"), "Der Wert „cdfx“ ist bei „Meldetatbestand“ nicht zulässig"),
        ("Verdacht/bestätigt fehlt", "Condition", lambda r: r.pop("verificationStatus"), "Pflichtangabe fehlt: Verdacht oder bestätigt"),
        ("Einrichtungsart falsch", "Organization", lambda r: r["type"][0]["coding"][0].update(code="xyz") if "type" in r else None, "„xyz“ ist bei „Art der Einrichtung“ nicht zulässig"),
        ("Melder ohne Telefon", "Practitioner", lambda r: r.pop("telecom"), "Pflichtangabe fehlt: Telefonnummer oder E-Mail"),
        ("Aufnahmedatum fehlt", "Encounter", lambda r: r["period"].pop("start"), "Pflichtangabe fehlt: Beginn"),
        ("Meldetyp falsch", "Composition", lambda r: r["category"][0]["coding"][0].update(code="9.9"), "Der Wert „9.9“ ist bei „Meldetyp“ nicht zulässig"),
    ],
)
def test_fehler_erscheinen_auf_deutsch(pakete, validator, beschreibung, typ, aenderung, erwartet):
    _, b = baue("cdi")
    ergebnis = pruefe_meldung(aendere(b, typ, aenderung), validator)
    assert not ergebnis.ok, f"{beschreibung}: es wurde kein Fehler erkannt"
    assert any(erwartet in str(p) for p in ergebnis.fehler), (beschreibung, [str(p) for p in ergebnis.fehler])
    assert all("minimum required" not in p.text and "Unknown code" not in p.text for p in ergebnis.fehler)  # kein Technikerdeutsch


def test_fehlende_pflichtfrage_im_bundle_wird_gemeldet(pakete, validator):
    _, b = baue("tb")

    def entferne_gruppe(qr):
        if qr["questionnaire"].endswith("MYTD"):
            qr["item"] = [i for i in qr["item"] if i["linkId"] != "nationalityGroup"]

    ergebnis = pruefe_meldung(aendere(b, "QuestionnaireResponse", entferne_gruppe), validator)
    assert any("Pflichtangabe fehlt" in p.text and p.quelle == "fragebogen" for p in ergebnis.fehler)


def test_folgefehler_werden_ausgeblendet_wenn_es_eine_ursache_gibt(pakete, validator):
    _, b = baue("cdi")
    ergebnis = pruefe_meldung(aendere(b, "Patient", lambda r: r["name"][0].pop("given")), validator)
    assert not any("entspricht nicht dem DEMIS-Profil" in p.text for p in ergebnis.probleme)


def test_validator_nicht_erreichbar_gibt_verstaendliche_meldung(pakete):
    from meldeassistent.demis.validator import FhirValidator, ValidatorFehler

    _, b = baue("cdi")
    with pytest.raises(ValidatorFehler, match="nicht erreichbar"):
        pruefe_meldung(b, FhirValidator("http://localhost:1", timeout=2))


# =============================================================================================
# Übersetzung (ohne Validator)
# =============================================================================================
def issue(text: str, ausdruck: str = "Bundle.entry[0].resource.name[0]", schwere: str = "error") -> dict:
    return {"severity": schwere, "details": {"text": text}, "expression": [ausdruck]}


KLEINES_BUNDLE = {"entry": [{"resource": {"resourceType": "Patient", "meta": {"profile": [PROFIL + "NotifiedPerson|2.4.1"]}}}]}


def test_uebersetzung_pflichtfeld():
    p = uebersetze(issue("Patient.name.given: minimum required = 1, but only found 0 (from https://x)"), KLEINES_BUNDLE)
    assert p == Problem("fehler", "Betroffene Person", "Pflichtangabe fehlt: Vorname.", technisch=p.technisch)
    assert "minimum required" in p.technisch  # Original bleibt für die IT erhalten


@pytest.mark.parametrize(
    "text,erwartet",
    [
        ("Patient.address: max allowed = 3, but found 4", "Zu viele Einträge bei „Anschrift“ (erlaubt: höchstens 3)"),
        ("Value is 'x' but is fixed to 'y' in the profile …", "Falscher Wert „x“"),
        ("Constraint failed: validBirthDate: 'bla'", "Das Geburtsdatum hat ein ungültiges Format"),
        ("Constraint failed: andereRegel: 'Eine deutsche Regel.'", "Regel verletzt: Eine deutsche Regel."),
        ("Etwas völlig Unbekanntes passierte", "Technischer Prüfhinweis: Etwas völlig Unbekanntes passierte"),
    ],
)
def test_uebersetzung_weitere_muster(text, erwartet):
    assert erwartet in uebersetze(issue(text), KLEINES_BUNDLE).text


@pytest.mark.parametrize(
    "text",
    [
        "Constraint failed: dom-6: 'A resource should have narrative' (Best Practice Recommendation)",
        "Unable to validate code 'x' in system 'y' because the validator is running without terminology services",
        "Wrong Display Name 'a' for http://snomed.info/sct#1. Valid display is 'b'",
        "The questionnaire 'x' could not be resolved, so no validation can be performed against the base questionnaire",
    ],
)
def test_rauschen_wird_ausgeblendet(text):
    assert uebersetze(issue(text, schwere="warning"), KLEINES_BUNDLE) is None


def test_informationen_werden_ausgeblendet_und_warnungen_werden_hinweise():
    assert uebersetze(issue("Irgendeine Info", schwere="information"), KLEINES_BUNDLE) is None
    assert uebersetze(issue("Irgendeine Warnung", schwere="warning"), KLEINES_BUNDLE).schwere == "hinweis"
