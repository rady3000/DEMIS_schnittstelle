"""Tests der Übersetzung ISiK-FHIR -> internes Modell, auch für Sonderfälle, die das Schein-KIS nicht erzeugt.

NEXUS liefert vermutlich nicht alles so vollständig wie unsere Testdaten. Diese Tests stellen
sicher, dass fehlende oder ungewöhnliche Angaben zu 'unbekannt' führen und nicht zu Fehlern oder
erfundenen Werten.
"""

import copy
from datetime import date, datetime, timedelta, timezone

import pytest

from meldeassistent.kis import KisDatenFehler
from meldeassistent.kis import isik_mapper as m
from meldeassistent.modell import (
    Aufenthalt,
    Aufenthaltsabschnitt,
    Diagnosesicherheit,
    Geschlecht,
    Verstorben,
)
from meldeassistent.testdaten.faelle import alle_faelle


def beispiel_ressource(typ: str, id_: str) -> dict:
    for fall in alle_faelle():
        for r in fall.ressourcen():
            if r["resourceType"] == typ and r["id"] == id_:
                return copy.deepcopy(r)
    raise KeyError(id_)


def patient_res() -> dict:
    return beispiel_ressource("Patient", "pat-01-cdi-schwer-cdi")


# --- Hilfsfunktionen ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,erwartet",
    [("2026-10-12", date(2026, 10, 12)), ("2026-10-12T08:15:00+02:00", date(2026, 10, 12)), ("2026-10", None), ("2026", None), ("", None), (None, None), ("kein datum!", None)],
)
def test_parse_datum_unvollstaendig_ist_none(text, erwartet):
    assert m.parse_datum(text) == erwartet


def test_parse_zeitpunkt_mit_und_ohne_zone():
    assert m.parse_zeitpunkt("2026-10-12T08:15:00+02:00").utcoffset() == timedelta(hours=2)
    assert m.parse_zeitpunkt("2026-10-12") == datetime(2026, 10, 12)
    assert m.parse_zeitpunkt("Unsinn!!") is None


@pytest.mark.parametrize(
    "ref,typ,erwartet",
    [("Patient/abc-1", "Patient", "abc-1"), ("https://kis.test/fhir/Patient/abc-1", "Patient", "abc-1"), ("Encounter/abc", "Patient", None), ("Patient/../x", "Patient", None), (None, "Patient", None), ("Patient", "Patient", None)],
)
def test_id_aus_referenz(ref, typ, erwartet):
    assert m.id_aus_referenz(ref, typ) == erwartet


# --- Patient -----------------------------------------------------------------------------------
def test_geschlecht_other_mit_erweiterung():
    for code, erwartet in (("D", Geschlecht.DIVERS), ("X", Geschlecht.UNBESTIMMT)):
        res = patient_res()
        res["gender"] = "other"
        res["_gender"] = {"extension": [{"url": m.EXT_GESCHLECHT_AMTLICH, "valueCoding": {"code": code}}]}
        assert m.patient_aus_fhir(res).geschlecht is erwartet


def test_geschlecht_other_ohne_erweiterung_und_unknown():
    res = patient_res()
    res["gender"] = "other"
    assert m.patient_aus_fhir(res).geschlecht is Geschlecht.UNBESTIMMT
    res["gender"] = "unknown"
    assert m.patient_aus_fhir(res).geschlecht is Geschlecht.UNBEKANNT
    del res["gender"]
    assert m.patient_aus_fhir(res).geschlecht is Geschlecht.UNBEKANNT


def test_verstorben_varianten():
    res = patient_res()
    assert m.patient_aus_fhir(res).verstorben is Verstorben.UNBEKANNT
    res["deceasedBoolean"] = False
    assert m.patient_aus_fhir(res).verstorben is Verstorben.NEIN
    res["deceasedBoolean"] = True
    p = m.patient_aus_fhir(res)
    assert p.verstorben is Verstorben.JA and p.verstorben_am is None
    del res["deceasedBoolean"]
    res["deceasedDateTime"] = "2026-10-21T06:40:00+02:00"
    p = m.patient_aus_fhir(res)
    assert p.verstorben is Verstorben.JA and p.verstorben_am.hour == 6


def test_wohnanschrift_wird_dem_postfach_vorgezogen():
    res = patient_res()
    res["address"] = [
        {"type": "postal", "line": ["Postfach 815"], "city": "Anderswo", "postalCode": "98764"},
        {"type": "physical", "line": ["Musterweg 2"], "city": "Chemnitz", "postalCode": "09111"},
    ]
    adresse = m.patient_aus_fhir(res).adresse
    assert adresse.zeilen == ["Musterweg 2"] and adresse.ort == "Chemnitz"
    assert adresse.strasse is None  # keine Zerlegungs-Erweiterung vorhanden -> nichts erfunden


def test_ohne_adresse_telefon_geburtsdatum():
    res = patient_res()
    for feld in ("address", "telecom", "birthDate"):
        del res[feld]
    p = m.patient_aus_fhir(res)
    assert p.adresse is None and p.telefon is None and p.email is None and p.geburtsdatum is None


def test_offizieller_name_wird_bevorzugt_und_mehrere_vornamen_zusammengefuehrt():
    res = patient_res()
    res["name"] = [
        {"use": "maiden", "family": "Alt", "given": ["Eva"]},
        {"use": "official", "family": "Neu", "given": ["Anna", "Maria"]},
    ]
    p = m.patient_aus_fhir(res)
    assert (p.vorname, p.nachname) == ("Anna Maria", "Neu")
    assert p.anzeigename == "Neu, Anna Maria"


@pytest.mark.parametrize("name", [None, [], [{"use": "official", "family": "Nur"}], [{"use": "official", "given": ["Nur"]}]])
def test_patient_ohne_vollstaendigen_namen_ist_datenfehler(name):
    res = patient_res()
    if name is None:
        del res["name"]
    else:
        res["name"] = name
    with pytest.raises(KisDatenFehler):
        m.patient_aus_fhir(res)


# --- Aufenthalt --------------------------------------------------------------------------------
def test_entlassung_wegen_tod_auch_nur_ueber_entlassungsgrund_07():
    enc = beispiel_ressource("Encounter", "enc-06-mrgn-verstorben-mrgn-einr")
    enc["hospitalization"]["dischargeDisposition"]["coding"] = [{"code": "home"}]
    assert m.aufenthalt_aus_fhir(enc, []).entlassen_wegen_tod is True  # Erweiterung 07 = Tod
    enc["hospitalization"]["dischargeDisposition"]["extension"] = []
    assert m.aufenthalt_aus_fhir(enc, []).entlassen_wegen_tod is False


@pytest.mark.parametrize("status,laufend", [("in-progress", True), ("onleave", True), ("finished", False), ("planned", False), ("cancelled", False)])
def test_laufend_nach_status(status, laufend):
    enc = beispiel_ressource("Encounter", "enc-01-cdi-schwer-cdi-einr")
    enc["status"] = status
    assert m.aufenthalt_aus_fhir(enc, []).laufend is laufend


def test_abschnitte_werden_zeitlich_geordnet_auch_bei_gemischten_zeitzonen():
    enc = beispiel_ressource("Encounter", "enc-01-cdi-schwer-cdi-einr")
    spaet = beispiel_ressource("Encounter", "enc-01-cdi-schwer-cdi-abt2")
    frueh = beispiel_ressource("Encounter", "enc-01-cdi-schwer-cdi-abt1")
    frueh["period"]["start"] = "2026-10-12T08:15:00"  # ohne Zeitzone
    a = m.aufenthalt_aus_fhir(enc, [spaet, frueh])
    assert [x.station for x in a.abschnitte] == ["Station 3A (Innere)", "Intensivstation 1"]


def test_abschnitt_ohne_fachabteilung_und_station():
    abt = beispiel_ressource("Encounter", "enc-01-cdi-schwer-cdi-abt1")
    del abt["serviceType"], abt["location"]
    a = m.abschnitt_aus_fhir(abt)
    assert a.fachabteilung_schluessel is None and a.station is None and not a.ist_intensivstation


def test_aktuelle_station_bei_gemischten_zeitzonen_stuerzt_nicht_ab():
    mit_zone = Aufenthaltsabschnitt(station="A", beginn=datetime(2026, 10, 1, 8, tzinfo=timezone(timedelta(hours=2))))
    ohne_zone = Aufenthaltsabschnitt(station="B", beginn=datetime(2026, 10, 2, 8))
    a = Aufenthalt(kis_fall_id="x", laufend=True, abschnitte=[mit_zone, ohne_zone])
    assert a.aktuelle_station == "B"


# --- Diagnose ----------------------------------------------------------------------------------
def test_diagnose_sicherheit_aus_erweiterung_hat_vorrang_vor_status():
    cond = beispiel_ressource("Condition", "cond-03-masern-verdacht-masern")
    assert m.diagnose_aus_fhir(cond).sicherheit is Diagnosesicherheit.VERDACHT
    cond["verificationStatus"]["coding"][0]["code"] = "confirmed"  # widerspricht der Erweiterung V
    assert m.diagnose_aus_fhir(cond).sicherheit is Diagnosesicherheit.VERDACHT


@pytest.mark.parametrize("status,erwartet", [("confirmed", Diagnosesicherheit.GESICHERT), ("provisional", Diagnosesicherheit.VERDACHT), ("refuted", Diagnosesicherheit.AUSGESCHLOSSEN), ("entered-in-error", Diagnosesicherheit.UNBEKANNT)])
def test_diagnose_sicherheit_faellt_auf_verificationstatus_zurueck(status, erwartet):
    cond = beispiel_ressource("Condition", "cond-01-cdi-schwer-cdi")
    del cond["code"]["coding"][0]["extension"]
    cond["verificationStatus"]["coding"][0]["code"] = status
    assert m.diagnose_aus_fhir(cond).sicherheit is erwartet


def test_diagnose_nur_freitext_hat_keinen_icd_code():
    cond = beispiel_ressource("Condition", "cond-01-cdi-schwer-cdi")
    cond["code"] = {"text": "Durchfall nach Antibiotika"}
    d = m.diagnose_aus_fhir(cond)
    assert d.icd_code is None and d.freitext == "Durchfall nach Antibiotika"


def test_diagnose_waehlt_icd_coding_unter_mehreren():
    cond = beispiel_ressource("Condition", "cond-01-cdi-schwer-cdi")
    icd = cond["code"]["coding"][0]
    cond["code"]["coding"] = [{"system": "http://snomed.info/sct", "code": "123"}, icd]
    assert m.diagnose_aus_fhir(cond).icd_code == "A04.71"


def test_diagnose_mit_unvollstaendigem_datum_hat_kein_datum():
    cond = beispiel_ressource("Condition", "cond-01-cdi-schwer-cdi")
    cond["onsetDateTime"] = "2026-10"
    assert m.diagnose_aus_fhir(cond).erkrankungsbeginn is None


# --- Labor -------------------------------------------------------------------------------------
def test_labor_mit_mengenangabe_und_codiertem_ergebnis():
    report = beispiel_ressource("DiagnosticReport", "lab-01-cdi-schwer-cdi")
    report["result"] = [{"reference": "Observation/o1"}, {"reference": "Observation/o2"}, {"reference": "Observation/fehlt"}]
    obs = {
        "o1": {"id": "o1", "valueQuantity": {"value": 12.5, "unit": "mg/l"}},
        "o2": {"id": "o2", "valueCodeableConcept": {"coding": [{"display": "positiv"}]}},
    }
    labor = m.laborbefund_aus_fhir(report, obs)
    assert labor.ergebnis == "12.5 mg/l; positiv"  # fehlende Beobachtung wird übersprungen, nichts erfunden


def test_labor_ohne_ergebnis_und_ohne_nummer():
    report = {"resourceType": "DiagnosticReport", "id": "x", "status": "final"}
    labor = m.laborbefund_aus_fhir(report, {})
    assert labor.labornummer is None and labor.ergebnis is None and labor.datum is None


# --- Architekturgrenze ---------------------------------------------------------------------------
def test_internes_modell_kennt_weder_fhir_noch_http_noch_kis_adapter():
    """Der Rest der Anwendung darf nur das interne Modell kennen (PLAN.md, Kernprinzip 1)."""
    from pathlib import Path

    quellen = (Path(__file__).resolve().parent.parent / "src" / "meldeassistent" / "modell").glob("*.py")
    for datei in quellen:
        text = datei.read_text(encoding="utf-8")
        assert "import httpx" not in text and "meldeassistent.kis" not in text, datei.name
