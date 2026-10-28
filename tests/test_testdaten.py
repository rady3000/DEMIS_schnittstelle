"""Tests für die synthetischen Testdaten und das Einspiel-Skript (Phase 1).

Die Tests brauchen keinen Server. Ein Test gegen das echte Schein-KIS läuft nur, wenn die
Umgebungsvariable SCHEIN_KIS_TEST=1 gesetzt ist (siehe test_gegen_schein_kis).
"""

import json
import os
from pathlib import Path

import httpx
import pytest

from meldeassistent.testdaten import einspielen
from meldeassistent.testdaten.faelle import (
    TAG_SYSTEM,
    WEG_DEMIS,
    WEG_KEIN_AUTOMATISCH,
    WEG_SACHSEN,
    alle_faelle,
    stammdaten,
    transaktions_bundle,
)

PROJEKT = Path(__file__).resolve().parent.parent


def alle_ressourcen():
    ressourcen = list(stammdaten())
    for fall in alle_faelle():
        ressourcen += fall.ressourcen()
    return ressourcen


def test_sieben_faelle_mit_erwarteten_meldewegen():
    wege = {f.schluessel: f.erwarteter_weg for f in alle_faelle()}
    assert wege == {
        "01-cdi-schwer": WEG_DEMIS,
        "02-tb-offen": WEG_DEMIS,
        "03-masern-verdacht": WEG_DEMIS,
        "04-influenza": WEG_SACHSEN,
        "05-norovirus-ausbruch": WEG_KEIN_AUTOMATISCH,
        "06-mrgn-verstorben": WEG_SACHSEN,
        "07-cdi-schwer-verstorben": WEG_DEMIS,
    }


def test_demis_faelle_nennen_das_profilkuerzel():
    kuerzel = {f.schluessel: f.erwartetes_demis_profil for f in alle_faelle()}
    assert kuerzel["01-cdi-schwer"] == "CDFD"
    assert kuerzel["02-tb-offen"] == "MYTD"
    assert kuerzel["03-masern-verdacht"] == "MSVD"
    assert kuerzel["07-cdi-schwer-verstorben"] == "CDFD"
    # Nicht-DEMIS-Fälle haben kein Profil
    assert kuerzel["04-influenza"] is None and kuerzel["06-mrgn-verstorben"] is None


def test_alle_ressourcen_sind_als_synthetisch_markiert():
    # Harte Regel 1: keine echten Patientendaten, alles muss erkennbar synthetisch sein
    for r in alle_ressourcen():
        codes = [t["code"] for t in r["meta"]["tag"] if t["system"] == TAG_SYSTEM]
        assert codes == ["SYNTHETISCH"], f"{r['resourceType']}/{r['id']} ist nicht markiert"


def test_patienten_heissen_testpatient():
    patienten = [r for r in alle_ressourcen() if r["resourceType"] == "Patient"]
    assert len(patienten) == 9  # 6 Einzelfälle + 3 Patienten im Ausbruch
    assert {p["name"][0]["family"] for p in patienten} == {"Testpatient"}


def test_ids_sind_eindeutig():
    ids = [(r["resourceType"], r["id"]) for r in alle_ressourcen()]
    assert len(ids) == len(set(ids))


def _verweise(wert):
    """Sammelt alle 'reference'-Werte rekursiv."""
    if isinstance(wert, dict):
        for schluessel, inhalt in wert.items():
            if schluessel == "reference" and isinstance(inhalt, str):
                yield inhalt
            else:
                yield from _verweise(inhalt)
    elif isinstance(wert, list):
        for eintrag in wert:
            yield from _verweise(eintrag)


def test_alle_verweise_zeigen_auf_vorhandene_ressourcen():
    vorhanden = {f"{r['resourceType']}/{r['id']}" for r in alle_ressourcen()}
    for r in alle_ressourcen():
        for ziel in _verweise(r):
            assert ziel in vorhanden, f"{r['resourceType']}/{r['id']} verweist auf fehlendes {ziel}"


def _fall(schluessel):
    return next(f for f in alle_faelle() if f.schluessel == schluessel)


@pytest.mark.parametrize("schluessel", ["06-mrgn-verstorben", "07-cdi-schwer-verstorben"])
def test_verstorbene_haben_todesdatum_und_entlassungsgrund_tod(schluessel):
    ressourcen = _fall(schluessel).ressourcen()
    patient = next(r for r in ressourcen if r["resourceType"] == "Patient")
    einrichtung = next(r for r in ressourcen if r["id"].endswith("-einr"))
    assert "deceasedDateTime" in patient
    assert einrichtung["status"] == "finished"
    assert einrichtung["period"]["end"] == patient["deceasedDateTime"]
    assert einrichtung["hospitalization"]["dischargeDisposition"]["coding"][0]["code"] == "exp"


def test_lebende_haben_kein_todesdatum():
    for schluessel in ("01-cdi-schwer", "02-tb-offen", "03-masern-verdacht", "04-influenza", "05-norovirus-ausbruch"):
        for r in _fall(schluessel).ressourcen():
            assert "deceasedDateTime" not in r


@pytest.mark.parametrize("schluessel", ["01-cdi-schwer", "07-cdi-schwer-verstorben"])
def test_cdi_faelle_haben_einen_intensivabschnitt(schluessel):
    abschnitte = [r for r in _fall(schluessel).ressourcen() if r["id"].endswith(("-abt1", "-abt2"))]
    schluessel_abteilungen = [a["serviceType"]["coding"][0]["code"] for a in abschnitte]
    assert schluessel_abteilungen == ["0100", "3600"]  # Innere, dann Intensivmedizin


def test_masern_verdacht_ist_verdacht_und_ohne_labor():
    ressourcen = _fall("03-masern-verdacht").ressourcen()
    diagnose = next(r for r in ressourcen if r["resourceType"] == "Condition")
    assert diagnose["verificationStatus"]["coding"][0]["code"] == "provisional"
    assert diagnose["code"]["coding"][0]["extension"][0]["valueCoding"]["code"] == "V"
    assert not [r for r in ressourcen if r["resourceType"] == "DiagnosticReport"]


def test_norovirus_ausbruch_hat_drei_patienten_auf_derselben_station():
    ressourcen = _fall("05-norovirus-ausbruch").ressourcen()
    stationen = {
        e["location"][0]["location"]["reference"]
        for e in ressourcen
        if e["resourceType"] == "Encounter" and e["id"].endswith("-abt1")
    }
    assert stationen == {"Location/loc-3b"}
    assert len([r for r in ressourcen if r["resourceType"] == "Patient"]) == 3


def test_icd_codes_haben_den_bestaetigten_anzeigetext():
    # Codes und Texte wurden vom Auftraggeber bestätigt (28.10.2026); hier als Festschreibung
    erwartet = {
        "A04.71": "Enterokolitis durch Clostridium difficile ohne Megakolon, mit sonstigen Organkomplikationen",
        "A15.0": "Lungentuberkulose, durch mikroskopische Untersuchung des Sputums gesichert, mit oder ohne Nachweis durch Kultur oder molekularbiologische Verfahren",
        "B05.9": "Masern ohne Komplikation",
        "J10.1": "Grippe mit sonstigen Manifestationen an den Atemwegen, saisonale Influenzaviren nachgewiesen",
        "A08.1": "Akute Gastroenteritis durch Norovirus",
        "A41.58": "Sepsis durch sonstige gramnegative Erreger",
    }
    gefunden = {
        r["code"]["coding"][0]["code"]: r["code"]["coding"][0]["display"]
        for r in alle_ressourcen()
        if r["resourceType"] == "Condition"
    }
    assert gefunden == erwartet


def test_transaktions_bundle_nutzt_put_mit_fester_id():
    bundle = transaktions_bundle(stammdaten())
    assert bundle["type"] == "transaction"
    for eintrag in bundle["entry"]:
        r = eintrag["resource"]
        assert eintrag["request"] == {"method": "PUT", "url": f"{r['resourceType']}/{r['id']}"}


# --- Schutz vor falschem Ziel (Harte Regel 2) ----------------------------------------------
@pytest.mark.parametrize("url", ["http://localhost:8080/fhir", "http://127.0.0.1:8080/fhir", "http://[::1]:8080/fhir"])
def test_lokale_ziele_sind_erlaubt(url):
    einspielen.pruefe_ziel(url)


@pytest.mark.parametrize("url", ["https://kis.klinik.example/fhir", "http://10.1.2.3:8080/fhir", "https://test.demis.rki.de/fhir"])
def test_fremde_ziele_werden_abgelehnt(url):
    with pytest.raises(einspielen.FremderServerFehler):
        einspielen.pruefe_ziel(url)


def test_fremdes_ziel_nur_mit_ausdruecklicher_erlaubnis():
    einspielen.pruefe_ziel("https://kis.klinik.example/fhir", erlaube_fremden_server=True)


def test_einspielen_sendet_alle_bundles_in_reihenfolge():
    gesendet = []

    def antwort(request: httpx.Request) -> httpx.Response:
        bundle = json.loads(request.content)
        gesendet.append(bundle)
        return httpx.Response(200, json={"resourceType": "Bundle", "entry": [{}] * len(bundle["entry"])})

    client = httpx.Client(transport=httpx.MockTransport(antwort))
    ergebnis = einspielen.spiele_ein("http://localhost:8080/fhir", client=client)
    assert list(ergebnis)[0] == "00-stammdaten"  # Stammdaten zuerst, sonst fehlen Verweise
    assert len(gesendet) == 8
    assert all(b["type"] == "transaction" for b in gesendet)


def test_einspielen_meldet_serverfehler_verstaendlich():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, text="kaputt")))
    with pytest.raises(RuntimeError, match="HTTP 400"):
        einspielen.spiele_ein("http://localhost:8080/fhir", client=client)


def test_einspielen_verweigert_fremden_server_ohne_netzwerkzugriff():
    aufrufe = []
    client = httpx.Client(transport=httpx.MockTransport(lambda r: aufrufe.append(r) or httpx.Response(200, json={})))
    with pytest.raises(einspielen.FremderServerFehler):
        einspielen.spiele_ein("https://kis.klinik.example/fhir", client=client)
    assert aufrufe == []  # es wurde gar nichts gesendet


def test_eingecheckte_json_dateien_entsprechen_dem_code(tmp_path):
    """Die Dateien in testdaten/ müssen aus dem Code reproduzierbar sein (kein Auseinanderlaufen)."""
    einspielen.schreibe_dateien(tmp_path)
    for neu in tmp_path.glob("*.json"):
        alt = PROJEKT / "testdaten" / neu.name
        assert alt.exists(), f"{alt} fehlt: bitte 'python -m meldeassistent.testdaten --erzeugen' ausführen"
        assert alt.read_text(encoding="utf-8") == neu.read_text(encoding="utf-8"), f"{neu.name} ist veraltet"


def test_html_uebersicht_nennt_alle_faelle_und_wege():
    from meldeassistent.testdaten.uebersicht_html import erzeuge_html

    html = erzeuge_html()
    for fall in alle_faelle():
        assert fall.titel.split(",")[0].split(" (")[0] in html
    assert html.count("<tr>") == 1 + 9  # Kopfzeile + 9 Patienten
    assert "Sachsen (Landesmeldung)" in html and "kein automatischer Weg" in html
    assert "<script" not in html  # statische Seite, kein Skript


@pytest.mark.skipif(os.environ.get("SCHEIN_KIS_TEST") != "1", reason="braucht laufendes Schein-KIS (SCHEIN_KIS_TEST=1)")
def test_gegen_schein_kis():
    basis = os.environ.get("FHIR_BASIS_URL", einspielen.STANDARD_URL)
    einspielen.spiele_ein(basis)
    einspielen.spiele_ein(basis)  # zweites Mal: darf nichts verdoppeln
    with httpx.Client(timeout=30) as client:
        gesamt = client.get(f"{basis}/Patient", params={"_summary": "count"}).json()["total"]
        assert gesamt == 9
        assert einspielen.zaehle_fremde_ressourcen(basis, client) == 0
