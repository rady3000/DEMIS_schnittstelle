"""Tests des KIS-Adapters (Phase 2).

Die Tests mit dem Fixture ``adapter`` laufen zweimal: gegen den Fake-Server und gegen das echte
Schein-KIS (HAPI). Erwartet werden die Werte der sieben synthetischen Testfälle.
"""

from datetime import date

import httpx
import pytest

from fake_fhir import BASIS, FakeFhirServer
from meldeassistent.kis import KisAntwortFehler, KisDatenFehler, KisNichtErreichbar
from meldeassistent.kis.isik_fhir import IsikFhirAdapter
from meldeassistent.modell import Diagnosesicherheit, Geschlecht, Verstorben


def fall_id(schluessel: str, kennung: str) -> str:
    return f"enc-{schluessel}-{kennung}-einr"


# --- Arbeitsliste ----------------------------------------------------------------------------
def test_verbindung_wird_geprueft(adapter):
    assert "FHIR 4.0" in adapter.pruefe_verbindung()


def test_arbeitsliste_enthaelt_alle_neun_faelle(adapter):
    liste = adapter.liste_faelle()
    assert len(liste) == 9
    assert {z.patient_name.split(", ")[0] for z in liste} == {"Testpatient"}


def test_arbeitsliste_laufende_zuerst_und_neueste_zuerst(adapter):
    liste = adapter.liste_faelle()
    laufend = [z.laufend for z in liste]
    assert laufend == sorted(laufend, reverse=True)  # erst True, dann False
    assert sum(laufend) == 7  # 4 Einzelfälle + 3 im Ausbruch; zwei Verstorbene sind beendet
    aufnahmen = [z.aufnahme for z in liste if z.laufend]
    assert aufnahmen == sorted(aufnahmen, reverse=True)


def test_arbeitsliste_nur_laufende_filtert(adapter):
    assert len(adapter.liste_faelle(nur_laufende=True)) == 7


def test_arbeitsliste_seit_datum_filtert_beendete_faelle(adapter):
    # Fall 6 endete am 21.10., Fall 7 am 22.10.: ab 22.10. bleibt nur Fall 7 von den Beendeten
    liste = adapter.liste_faelle(seit=date(2026, 10, 22))
    beendet = [z for z in liste if not z.laufend]
    assert [z.patient_name for z in beendet] == ["Testpatient, Ingrid"]


def test_arbeitsliste_zeigt_aktuelle_station_und_diagnose(adapter):
    zeilen = {z.kis_fall_id: z for z in adapter.liste_faelle()}
    cdi = zeilen[fall_id("01-cdi-schwer", "cdi")]
    assert cdi.station == "Intensivstation 1"  # zuletzt begonnener Abschnitt
    assert [d.icd_code for d in cdi.diagnosen] == ["A04.71"]
    assert cdi.diagnosen[0].sicherheit is Diagnosesicherheit.GESICHERT
    masern = zeilen[fall_id("03-masern-verdacht", "masern")]
    assert masern.diagnosen[0].sicherheit is Diagnosesicherheit.VERDACHT


def test_arbeitsliste_markiert_verstorbene(adapter):
    verstorben = {z.patient_name: z.verstorben for z in adapter.liste_faelle()}
    assert verstorben["Testpatient, Hans"] is Verstorben.JA
    assert verstorben["Testpatient, Ingrid"] is Verstorben.JA
    # Lebende: das KIS sagt nichts -> unbekannt (nicht "nein")
    assert verstorben["Testpatient, Anna"] is Verstorben.UNBEKANNT


# --- Einzelner Fall --------------------------------------------------------------------------
def test_fall_cdi_schwer_mit_intensivabschnitt_und_labor(adapter):
    fall = adapter.lade_fall(fall_id("01-cdi-schwer", "cdi"))
    p = fall.patient
    assert (p.vorname, p.nachname, p.geschlecht) == ("Anna", "Testpatient", Geschlecht.WEIBLICH)
    assert p.geburtsdatum == date(1948, 3, 14)
    assert p.adresse.strasse == "Musterstraße" and p.adresse.hausnummer == "12"
    assert (p.adresse.plz, p.adresse.ort) == ("09117", "Chemnitz")
    assert p.telefon == "+49 371 0000001"
    assert p.patientennummer == "TEST-01-cdi"

    a = fall.aufenthalt
    assert a.laufend and not a.entlassen_wegen_tod
    assert [x.fachabteilung_schluessel for x in a.abschnitte] == ["0100", "3600"]
    assert [x.station for x in a.abschnitte] == ["Station 3A (Innere)", "Intensivstation 1"]
    assert a.hatte_intensivstation and a.aktuelle_station == "Intensivstation 1"
    assert a.besuchsnummer == "TEST-01-cdi"

    assert [(d.icd_code, d.sicherheit) for d in fall.diagnosen] == [("A04.71", Diagnosesicherheit.GESICHERT)]
    assert fall.diagnosen[0].erkrankungsbeginn == date(2026, 10, 10)
    assert fall.diagnosen[0].erfasst_am == date(2026, 10, 18)

    assert len(fall.laborbefunde) == 1
    labor = fall.laborbefunde[0]
    assert labor.labornummer == "L-2026-100001"
    assert labor.ergebnis == "positiv" and "Toxin" in labor.untersuchung
    assert labor.labor == "Labor Testlabor (synthetisch)" or labor.labor is None


def test_fall_masern_verdacht_ohne_labor_gibt_hinweis(adapter):
    fall = adapter.lade_fall(fall_id("03-masern-verdacht", "masern"))
    assert fall.patient.geschlecht is Geschlecht.WEIBLICH
    assert fall.diagnosen[0].sicherheit is Diagnosesicherheit.VERDACHT
    assert fall.laborbefunde == []
    assert any("Laborbefunde" in h for h in fall.hinweise)


def test_fall_verstorben_hat_todesdatum_und_entlassung_wegen_tod(adapter):
    fall = adapter.lade_fall(fall_id("06-mrgn-verstorben", "mrgn"))
    assert fall.patient.verstorben is Verstorben.JA
    assert fall.patient.verstorben_am is not None
    assert fall.aufenthalt.entlassen_wegen_tod and not fall.aufenthalt.laufend
    assert fall.aufenthalt.ende == fall.patient.verstorben_am
    assert fall.diagnosen[0].icd_code == "A41.58"
    assert not any("Tod" in h for h in fall.hinweise)  # Daten sind konsistent -> kein Widerspruchshinweis


def test_fall_cdi_verstorben_hat_beide_abschnitte_beendet(adapter):
    fall = adapter.lade_fall(fall_id("07-cdi-schwer-verstorben", "cdi"))
    assert fall.patient.verstorben is Verstorben.JA
    assert all(x.ende is not None for x in fall.aufenthalt.abschnitte)
    assert fall.aufenthalt.hatte_intensivstation


def test_fall_im_ausbruch_hat_nur_station_3b(adapter):
    fall = adapter.lade_fall(fall_id("05-norovirus-ausbruch", "noro2"))
    assert fall.patient.vorname == "Frieda"
    assert fall.aufenthalt.aktuelle_station == "Station 3B (Innere)"
    assert fall.diagnosen[0].icd_code == "A08.1"


def test_lebender_patient_ohne_todesangabe_ist_unbekannt_nicht_nein(adapter):
    fall = adapter.lade_fall(fall_id("02-tb-offen", "tb"))
    assert fall.patient.verstorben is Verstorben.UNBEKANNT and fall.patient.verstorben_am is None


def test_unbekannte_fall_id_gibt_verstaendlichen_fehler(adapter):
    with pytest.raises(KisAntwortFehler) as fehler:
        adapter.lade_fall("gibt-es-nicht")
    assert fehler.value.status == 404


@pytest.mark.parametrize("boese_id", ["../Patient", "a/b", "x?y=1", "", "a" * 65, "id mit leerzeichen"])
def test_ungueltige_fall_ids_werden_abgelehnt_ohne_anfrage(boese_id):
    server = FakeFhirServer()
    a = IsikFhirAdapter(BASIS, client=server.client())
    with pytest.raises(KisDatenFehler):
        a.lade_fall(boese_id)
    assert server.anfragen == []  # es ging gar nichts an den Server


def test_abteilungskontakt_ist_kein_fall():
    server = FakeFhirServer()
    a = IsikFhirAdapter(BASIS, client=server.client())
    with pytest.raises(KisDatenFehler, match="kein stationärer Fall"):
        a.lade_fall("enc-01-cdi-schwer-cdi-abt1")


# --- Seitenweise Abfrage ----------------------------------------------------------------------
def test_arbeitsliste_ueber_mehrere_seiten():
    server = FakeFhirServer()
    a = IsikFhirAdapter(BASIS, client=server.client(), seitengroesse=2)
    assert len(a.liste_faelle()) == 9
    suchen = [r for r in server.anfragen if r.url.path.endswith("/Encounter")]
    assert len(suchen) > 2  # mehrere Seiten wurden abgeholt


def test_next_link_auf_fremden_server_wird_nicht_gefolgt():
    # Sonst würde das Zugangs-Token an einen fremden Server geschickt
    server = FakeFhirServer(fremder_next_link=True)
    a = IsikFhirAdapter(BASIS, token="geheim", client=server.client(), seitengroesse=2)
    with pytest.raises(KisDatenFehler, match="fremden Server"):
        a.liste_faelle()
    assert all("anderer-server" not in str(r.url) for r in server.anfragen)


# --- Fehlerverhalten ---------------------------------------------------------------------------
def adapter_mit(antwort) -> IsikFhirAdapter:
    return IsikFhirAdapter(BASIS, client=httpx.Client(transport=httpx.MockTransport(antwort)))


def test_server_nicht_erreichbar():
    def antwort(request):
        raise httpx.ConnectError("verbindung abgelehnt")

    with pytest.raises(KisNichtErreichbar, match="nicht erreichbar"):
        adapter_mit(antwort).pruefe_verbindung()


def test_zeitueberschreitung():
    def antwort(request):
        raise httpx.ReadTimeout("zu langsam")

    with pytest.raises(KisNichtErreichbar, match="nicht rechtzeitig"):
        adapter_mit(antwort).liste_faelle()


@pytest.mark.parametrize("status,text", [(401, "Anmeldung am KIS abgelehnt"), (403, "Anmeldung am KIS abgelehnt"), (500, "HTTP 500")])
def test_fehlerstatus_werden_verstaendlich_gemeldet(status, text):
    with pytest.raises(KisAntwortFehler, match=text) as fehler:
        adapter_mit(lambda r: httpx.Response(status, text="intern")).liste_faelle()
    assert fehler.value.status == status


def test_fehlermeldungen_enthalten_keine_gesundheitsdaten_des_servers():
    geheim = "Anna Testpatient Clostridioides Diagnose"
    for antwort in (httpx.Response(500, text=geheim), httpx.Response(200, text=geheim)):
        with pytest.raises((KisAntwortFehler, KisDatenFehler)) as fehler:
            adapter_mit(lambda r, a=antwort: a).liste_faelle()
        assert "Anna" not in str(fehler.value) and "Clostridioides" not in str(fehler.value)


def test_kein_json_ist_ein_datenfehler():
    with pytest.raises(KisDatenFehler, match="keine gültigen FHIR-Daten"):
        adapter_mit(lambda r: httpx.Response(200, text="<html>Login</html>")).liste_faelle()


def test_falsche_fhir_version_wird_erkannt():
    antwort = httpx.Response(200, json={"resourceType": "CapabilityStatement", "fhirVersion": "3.0.2"})
    with pytest.raises(KisDatenFehler, match="nicht FHIR R4"):
        adapter_mit(lambda r: antwort).pruefe_verbindung()


def test_suche_ohne_bundle_ist_ein_datenfehler():
    with pytest.raises(KisDatenFehler, match="kein Bundle"):
        adapter_mit(lambda r: httpx.Response(200, json={"resourceType": "OperationOutcome"})).liste_faelle()


def test_token_wird_als_bearer_gesendet():
    server = FakeFhirServer()
    a = IsikFhirAdapter(BASIS, token="abc123", client=server.client())
    a.pruefe_verbindung()
    assert server.anfragen[0].headers["Authorization"] == "Bearer abc123"


# --- Datenschutz in Logs (Harte Regel 5) ---------------------------------------------------------
def test_logs_enthalten_keine_patientendaten(caplog):
    caplog.set_level("DEBUG")
    server = FakeFhirServer()
    a = IsikFhirAdapter(BASIS, client=server.client())
    a.liste_faelle()
    a.lade_fall(fall_id("01-cdi-schwer", "cdi"))
    text = caplog.text
    for verboten in ("Testpatient", "Anna", "A04.71", "Musterstraße", "Clostridioides", "09117"):
        assert verboten not in text
    assert "enc-0" not in text and "pat-0" not in text  # auch keine IDs aus den Anfrage-URLs
    assert "Fälle geladen" in text  # es wird aber protokolliert, dass etwas passiert ist
