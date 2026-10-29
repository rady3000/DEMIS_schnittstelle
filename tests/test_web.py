"""Tests der Oberfläche (Phase 4). KIS-Daten über den Fake-Server, Prüfung durch den echten Validator.

Alle Anfragen laufen über den eingebauten Testclient, ohne Netzwerk und ohne Browser.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from demis_faelle import KONFIG, MELDER, kis_adapter
from fake_fhir import BASIS, FakeFhirServer
from meldeassistent.audit import Audit
from meldeassistent.kis.isik_fhir import IsikFhirAdapter
from meldeassistent.web.app import Einstellungen, erzeuge_app

JETZT = datetime(2026, 10, 28, 12, 0, tzinfo=timezone(timedelta(hours=1)))
BENUTZER = {"testarzt": "test", "zweite": "anders"}


@pytest.fixture
def audit_pfad(tmp_path):
    return tmp_path / "audit.log"


def baue_app(pakete, validator, audit_pfad, kis=None, **einstellungen):
    e = Einstellungen(benutzer=BENUTZER, melder=MELDER, konfig=KONFIG, **einstellungen)
    return erzeuge_app(kis or kis_adapter(), validator, pakete, Audit(audit_pfad), e, uhr=lambda: JETZT)


@pytest.fixture
def app(pakete, validator, audit_pfad):
    return baue_app(pakete, validator, audit_pfad)


@pytest.fixture
def client(app):
    with TestClient(app, base_url="http://testserver") as c:
        yield c


def csrf_aus(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def anmelden(client: TestClient, benutzer="testarzt", passwort="test"):
    seite = client.get("/anmelden")
    return client.post("/anmelden", data={"benutzer": benutzer, "passwort": passwort, "csrf": csrf_aus(seite.text)})


def zeile_fuer(html: str, name: str) -> str:
    """Die Tabellenzeile der Arbeitsliste zu einem Patienten."""
    for zeile in re.findall(r"<tr class=.*?</tr>", html, re.S):
        if name in zeile:
            return zeile
    raise AssertionError(f"{name} nicht in der Arbeitsliste")


def token_fuer(client: TestClient, name: str) -> str:
    html = client.get("/").text
    return re.search(r'href="/fall/([^"]+)"', zeile_fuer(html, name)).group(1)


def sitzung_csrf(client: TestClient) -> str:
    return csrf_aus(client.get("/").text)


# Antworten, mit denen die Ärztin den Bogen für C. difficile (Fall 1) vollständig ausfüllt
CDI_ANTWORTEN = {
    "a.isDead": "no", "a.militaryAffiliation": "noReferenceToBundeswehr", "a.labSpecimenTaken": "yes", "a.hospitalized": "yes",
    "a.infectProtectFacility": "no", "a.placeExposure": "no", "a.organDonation": "no",
    "s.form": "186431008:{288556008=305351004}", "s.immunization": "no", "s.method": "117963005:{363701004=39477002}", "s.outbreak": "no",
    "verdacht": "nein", "erkrankungsbeginn": "10.10.2026", "diagnosedatum": "18.10.2026",
}


def sende_bogen(client, token, felder: dict, csrf: str | None = None):
    csrf = csrf or sitzung_csrf(client)
    return client.post(f"/fall/{token}/bogen", data={**felder, "csrf": csrf}, headers={"HX-Request": "true"})


def fuelle_cdi(client) -> str:
    """Öffnet Fall 1, füllt alles aus und bestätigt den Vorschlag. Gibt das Token zurück."""
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    sende_bogen(client, token, CDI_ANTWORTEN)
    csrf = sitzung_csrf(client)
    r = client.post(f"/fall/{token}/bestaetigen/spezifisch.form", data={"csrf": csrf}, headers={"HX-Request": "true"})
    assert "Alles beantwortet" in r.text, r.text[-3000:]
    return token


# =============================================================================================
# Anmeldung und Sitzung
# =============================================================================================
def test_ohne_anmeldung_geht_es_zur_anmeldeseite(client):
    r = client.get("/")
    assert r.status_code == 200 and "Benutzername" in r.text and "Meldepflichtige Befunde" not in r.text


def test_geschuetzte_seiten_brauchen_anmeldung(client):
    for pfad in ("/fall/irgendwas", "/fall/irgendwas/vorschau"):
        assert "Benutzername" in client.get(pfad).text
    for pfad in ("/fall/x/bogen", "/fall/x/freigeben", "/fall/x/verwerfen"):
        r = client.post(pfad, data={"csrf": "x"})
        assert "Benutzername" in r.text, pfad


def test_anmeldung_ok_und_falsches_passwort(client):
    schlecht = anmelden(client, passwort="falsch")
    assert schlecht.status_code == 401 and "stimmt nicht" in schlecht.text
    gut = anmelden(client)
    assert gut.status_code == 200 and "Meldepflichtige Befunde" in gut.text and "testarzt" in gut.text


def test_unbekannter_benutzer_bekommt_dieselbe_meldung(client):
    assert "Benutzername oder Passwort stimmt nicht" in anmelden(client, benutzer="gibtsnicht", passwort="x").text


def test_nach_fuenf_fehlversuchen_wird_gesperrt(client):
    for _ in range(5):
        assert anmelden(client, passwort="falsch").status_code == 401
    gesperrt = anmelden(client, passwort="test")  # selbst das richtige Passwort geht jetzt nicht
    assert gesperrt.status_code == 429 and "Zu viele Fehlversuche" in gesperrt.text


def test_anmeldung_ohne_csrf_wird_abgelehnt(client):
    client.get("/anmelden")
    assert client.post("/anmelden", data={"benutzer": "testarzt", "passwort": "test"}).status_code == 403


def test_sitzungs_id_wechselt_bei_der_anmeldung(client):
    client.get("/anmelden")
    vorher = client.cookies.get("sid")
    anmelden(client)
    assert client.cookies.get("sid") and client.cookies.get("sid") != vorher


def test_cookie_ist_httponly_und_strict(client):
    r = client.get("/anmelden")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_abmelden(client):
    anmelden(client)
    client.post("/abmelden", data={"csrf": sitzung_csrf(client)})
    assert "Benutzername" in client.get("/").text


def test_abmelden_braucht_csrf(client):
    anmelden(client)
    assert client.post("/abmelden", data={"csrf": "falsch"}).status_code == 403
    assert "Meldepflichtige Befunde" in client.get("/").text  # noch angemeldet


def test_sitzung_laeuft_bei_inaktivitaet_ab(pakete, validator, audit_pfad):
    app = baue_app(pakete, validator, audit_pfad, leerlauf_s=0)
    with TestClient(app, base_url="http://testserver") as c:
        anmelden(c)
        assert "Benutzername" in c.get("/").text


# =============================================================================================
# Sicherheit
# =============================================================================================
def test_sicherheits_header(client):
    r = client.get("/anmelden")
    assert r.headers["cache-control"] == "no-store"
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"


def test_keine_externen_ressourcen_in_den_seiten(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    for seite in (client.get("/").text, client.get(f"/fall/{token}").text):
        for url in re.findall(r'(?:src|href)="([^"]+)"', seite):
            assert not url.startswith(("http://", "https://", "//")), url


@pytest.mark.parametrize("methode,pfad_vorlage", [("post", "/fall/{t}/bogen"), ("post", "/fall/{t}/freigeben"), ("post", "/fall/{t}/verwerfen"), ("post", "/fall/{t}/bestaetigen/spezifisch.form")])
def test_aendernde_anfragen_brauchen_csrf(client, methode, pfad_vorlage):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    r = client.post(pfad_vorlage.format(t=token), data={"csrf": "falsch"})
    assert r.status_code == 403


def test_csrf_token_im_header_wird_akzeptiert(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    r = client.post(f"/fall/{token}/bogen", data={"a.isDead": "no"}, headers={"X-CSRF-Token": sitzung_csrf(client), "HX-Request": "true"})
    assert r.status_code == 200


def test_ungueltiger_schluessel_beim_bestaetigen(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    r = client.post(f"/fall/{token}/bestaetigen/..%2Fetc", data={"csrf": sitzung_csrf(client)})
    assert r.status_code in (403, 404)


def test_html_wird_maskiert(pakete, validator, audit_pfad):
    server = FakeFhirServer()
    for r in server.ressourcen:
        if r["resourceType"] == "Patient" and r["id"].startswith("pat-01"):
            r["name"][0]["given"] = ['<img src=x onerror="alert(1)">']
    app = baue_app(pakete, validator, audit_pfad, kis=IsikFhirAdapter(BASIS, client=server.client()))
    with TestClient(app, base_url="http://testserver") as c:
        anmelden(c)
        liste = c.get("/").text
        assert "<img src=x" not in liste and "&lt;img src=x" in liste
        token = re.search(r'href="/fall/([^"]+)"', zeile_fuer(liste, "&lt;img")).group(1)
        assert "<img src=x" not in c.get(f"/fall/{token}").text


def test_fall_kennungen_sind_zufaellig_nicht_kis_ids_und_je_sitzung_verschieden(client):
    anmelden(client)
    html = client.get("/").text
    tokens = re.findall(r'href="/fall/([^"]+)"', html)
    assert len(tokens) == 9 and len(set(tokens)) == 9
    assert not any("enc-" in t or "pat-" in t for t in tokens)
    assert re.findall(r'href="/fall/([^"]+)"', client.get("/").text) == tokens  # stabil während der Sitzung (offene Bögen bleiben gültig)
    with TestClient(client.app, base_url="http://testserver") as anderer:
        anmelden(anderer)
        assert set(re.findall(r'href="/fall/([^"]+)"', anderer.get("/").text)).isdisjoint(tokens)  # je Sitzung andere Kennungen


def test_fremder_oder_unbekannter_token_fuehrt_zur_liste(client):
    anmelden(client)
    assert "Meldepflichtige Befunde" in client.get("/fall/nichtvorhanden").text


def test_gesundheit_ohne_patientendaten(client):
    daten = client.get("/gesundheit").json()
    assert set(daten) == {"kis", "validator", "testbetrieb"} and "FHIR 4.0" in daten["kis"]


# =============================================================================================
# Arbeitsliste
# =============================================================================================
def test_arbeitsliste_zeigt_faelle_mit_meldeweg(client):
    anmelden(client)
    html = client.get("/").text
    erwartet = {
        "Testpatient, Anna": "DEMIS (CDFD)", "Testpatient, Boris": "DEMIS (MYTD)", "Testpatient, Clara": "DEMIS (MSVD)", "Testpatient, Ingrid": "DEMIS (CDFD)",
        "Testpatient, Dieter": "Landesmeldung Sachsen", "Testpatient, Hans": "Landesmeldung Sachsen",
        "Testpatient, Erwin": "Klärung nötig", "Testpatient, Frieda": "Klärung nötig", "Testpatient, Gustav": "Klärung nötig",
    }
    for name, weg in erwartet.items():
        assert weg in zeile_fuer(html, name), name
    assert "verstorben" in zeile_fuer(html, "Testpatient, Hans")
    assert "A04.71" in zeile_fuer(html, "Testpatient, Anna") and "Intensivstation 1" in zeile_fuer(html, "Testpatient, Anna")


def test_demis_faelle_haben_bearbeiten_und_andere_nur_ansehen(client):
    anmelden(client)
    html = client.get("/").text
    assert "Meldung bearbeiten" in zeile_fuer(html, "Testpatient, Anna")
    assert "Ansehen" in zeile_fuer(html, "Testpatient, Dieter") and "Meldung bearbeiten" not in zeile_fuer(html, "Testpatient, Dieter")


def test_kis_ausfall_gibt_verstaendliche_meldung(pakete, validator, audit_pfad):
    import httpx

    kaputt = IsikFhirAdapter(BASIS, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500, text="Anna Testpatient"))))
    app = baue_app(pakete, validator, audit_pfad, kis=kaputt)
    with TestClient(app, base_url="http://testserver") as c:
        anmelden(c)
        r = c.get("/")
        assert r.status_code == 502 and "Das KIS meldet einen Fehler" in r.text and "Anna" not in r.text


# =============================================================================================
# Meldebogen
# =============================================================================================
def test_meldebogen_zeigt_kis_daten_vorschlaege_und_offene_punkte(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    html = client.get(f"/fall/{token}").text
    assert "Aus dem KIS übernommen" in html and "Testpatient, Anna" in html and "Musterstraße 12" in html and "Intensivstation 1" in html
    assert "Vorschlag – bitte bestätigen" in html and "Vorschlag bestätigen" in html  # CDFD: Intensivstation als Vorschlag
    assert "Noch 9 Punkte offen" in html
    assert 'class="knopf gross gesperrt"' in html  # Vorschau noch gesperrt


def test_bedingte_felder_erscheinen_und_verschwinden(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    mit_tod = sende_bogen(client, token, {"a.isDead": "yes"}).text
    assert "Sterbedatum" in mit_tod
    ohne_tod = sende_bogen(client, token, {"a.isDead": "no"}).text
    assert "Sterbedatum" not in ohne_tod


def test_tb_zusatzangaben_nur_bei_tb_und_impfstatus_nur_bei_ja(client):
    anmelden(client)
    tb = token_fuer(client, "Testpatient, Boris")
    html = client.get(f"/fall/{tb}").text
    assert "Welches Organ war hauptsächlich betroffen?" in html and "Staatsangehörigkeit" in html
    cdi = token_fuer(client, "Testpatient, Anna")
    html = client.get(f"/fall/{cdi}").text
    assert "Welches Organ war hauptsächlich betroffen?" not in html and "Staatsangehörigkeit" not in html and "Exanthem" not in html
    assert "Impfstoff" not in html
    assert "Impfstoff" in sende_bogen(client, cdi, {"s.immunization": "yes"}).text
    assert "Impfstoff" not in sende_bogen(client, cdi, {"s.immunization": "no"}).text


def test_herkunft_wird_markiert_und_aenderung_wird_von_ihnen(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    html = sende_bogen(client, token, {"a.isDead": "no", "a.hospitalized": "yes", "a.labSpecimenTaken": "yes"}).text
    feld = lambda f: re.search(rf'<div id="feld-{re.escape(f)}" class="frage ([^"]+)"', html).group(1)
    assert "quelle-arzt" in feld("a.isDead")  # von der Ärztin gesetzt
    assert "quelle-kis" in feld("a.hospitalized")  # unverändert aus dem KIS
    assert "ist-offen" in feld("a.militaryAffiliation")  # noch nicht beantwortet
    assert "quelle-auto" in feld("s.form")  # Vorschlag


def test_ungueltiges_datum_wird_gemeldet_und_gueltiges_uebernommen(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    schlecht = sende_bogen(client, token, {"erkrankungsbeginn": "31.02.2026"}).text
    assert "kein gültiges Datum" in schlecht and 'value="31.02.2026"' in schlecht
    gut = sende_bogen(client, token, {"erkrankungsbeginn": "5.10.2026"}).text
    assert 'value="05.10.2026"' in gut and "kein gültiges Datum" not in gut


def test_fuer_demis_nicht_meldbare_faelle_gibt_es_keinen_bogen(client):
    anmelden(client)
    sachsen = client.get(f"/fall/{token_fuer(client, 'Testpatient, Dieter')}").text
    assert "Landesmeldung Sachsen" in sachsen and "bogenform" not in sachsen
    klaerung = client.get(f"/fall/{token_fuer(client, 'Testpatient, Gustav')}").text
    assert "Klärung nötig" in klaerung and "Häufung" in klaerung and "bogenform" not in klaerung


# =============================================================================================
# Vorschau, Freigabe, Audit
# =============================================================================================
def test_vorschau_ohne_vollstaendigen_bogen_fuehrt_zurueck(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    r = client.get(f"/fall/{token}/vorschau")
    assert "Meldebogen: Testpatient, Anna" in r.text and "Vorschau der Meldung" not in r.text


def test_vorschau_zeigt_was_gesendet_wird(client):
    anmelden(client)
    token = fuelle_cdi(client)
    html = client.get(f"/fall/{token}/vorschau").text
    assert "Vorschau der Meldung" in html and "ohne Fehler akzeptiert" in html
    for erwartet in ("Testpatient, Anna", "14.03.1948", "weiblich", "Musterstraße 12", "Clostridioides-difficile-Erkrankung", "10.10.2026", "Intensivmedizin", "12.10.2026 bis 16.10.2026", "Ist die Person verstorben?", "Nein", "DRK Krankenhaus Chemnitz-Rabenstein gGmbH"):
        assert erwartet in html, erwartet
    assert "Freigeben" in html and "sendet nichts" in html
    assert "A04.71" not in html and "L-2026" not in html  # ICD-Code und Labornummer gehen nicht mit


def test_freigabe_schreibt_audit_ohne_gesundheitsdaten_und_loescht_den_entwurf(client, audit_pfad):
    anmelden(client)
    token = fuelle_cdi(client)
    client.get(f"/fall/{token}/vorschau")
    r = client.post(f"/fall/{token}/freigeben", data={"csrf": sitzung_csrf(client)})
    assert "Meldung freigegeben" in r.text and "nichts gesendet" in r.text and "Bearbeitungszeit" in r.text
    eintraege = [json.loads(z) for z in audit_pfad.read_text(encoding="utf-8").splitlines()]
    status = [e["status"] for e in eintraege]
    assert status == ["angemeldet", "geoeffnet", "freigegeben_ohne_versand"]
    assert set().union(*[set(e) for e in eintraege]) <= {"zeit", "vorgang", "benutzer", "meldeweg", "status", "dauer_s"}
    frei = eintraege[-1]
    assert frei["benutzer"] == "testarzt" and frei["meldeweg"] == "demis" and isinstance(frei["dauer_s"], int)
    text = audit_pfad.read_text(encoding="utf-8")
    for verboten in ("Anna", "Testpatient", "A04.71", "Musterstraße", "enc-", "pat-", "cdfd"):
        assert verboten not in text
    # Entwurf ist weg: erneutes Öffnen beginnt von vorn
    token2 = token_fuer(client, "Testpatient, Anna")
    assert "Noch 9 Punkte offen" in client.get(f"/fall/{token2}").text


def test_freigabe_ohne_vollstaendigen_bogen_ist_nicht_moeglich(client, audit_pfad):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    r = client.post(f"/fall/{token}/freigeben", data={"csrf": sitzung_csrf(client)})
    assert "Meldung freigegeben" not in r.text
    assert "freigegeben_ohne_versand" not in audit_pfad.read_text(encoding="utf-8")


def test_unbestaetigter_vorschlag_blockiert_die_freigabe(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    html = sende_bogen(client, token, CDI_ANTWORTEN).text  # Vorschlag "form" bleibt unbestätigt
    assert "Vorschlag bitte bestätigen" in html and "Alles beantwortet" not in html


def test_verwerfen_loescht_entwurf_und_schreibt_audit(client, audit_pfad):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    sende_bogen(client, token, {"a.isDead": "no"})
    client.post(f"/fall/{token}/verwerfen", data={"csrf": sitzung_csrf(client)})
    assert [json.loads(z)["status"] for z in audit_pfad.read_text(encoding="utf-8").splitlines()][-1] == "verworfen"
    assert "Noch 9 Punkte offen" in client.get(f"/fall/{token_fuer(client, 'Testpatient, Anna')}").text


def test_entwurf_bleibt_beim_zurueckkehren_erhalten(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Anna")
    client.get(f"/fall/{token}")
    sende_bogen(client, token, {"a.isDead": "no"})
    neu = token_fuer(client, "Testpatient, Anna")
    assert neu == token
    assert "Weiter bearbeiten" in zeile_fuer(client.get("/").text, "Testpatient, Anna")
    assert "Noch 8 Punkte offen" in client.get(f"/fall/{neu}").text


def test_entwuerfe_verschiedener_benutzer_sind_getrennt(pakete, validator, audit_pfad):
    app = baue_app(pakete, validator, audit_pfad)
    with TestClient(app, base_url="http://testserver") as a, TestClient(app, base_url="http://testserver") as b:
        anmelden(a)
        anmelden(b, "zweite", "anders")
        ta = token_fuer(a, "Testpatient, Anna")
        a.get(f"/fall/{ta}")
        sende_bogen(a, ta, {"a.isDead": "no"})
        tb = token_fuer(b, "Testpatient, Anna")
        assert "Noch 9 Punkte offen" in b.get(f"/fall/{tb}").text  # B sieht As Eingaben nicht


def test_vollstaendiger_ablauf_tuberkulose(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Boris")
    client.get(f"/fall/{token}")
    antworten = {
        "a.isDead": "no", "a.militaryAffiliation": "noReferenceToBundeswehr", "a.labSpecimenTaken": "yes", "a.hospitalized": "yes",
        "a.infectProtectFacility": "no", "a.placeExposure": "no", "a.organDonation": "no",
        "s.immunization": "ASKU", "s.infectionEnvironmentSettingKind": "ASKU", "s.nationality": "DE", "s.countryOfBirth": "DE", "s.childrenUnder15Years": "no",
        "s.causeDiagnosis": "41769001:{246090004=404684003}", "s.statusDiagnosis": "yes", "s.treatment": "yes", "s.treatmentBegin": "21.10.2026", "s.resultOfTreatment": "ASKU",
        "s.majorSite": "154283005", "s.minorSite": "260413007", "s.prevTreatment": "no", "s.outbreak": "no",
    }
    html = sende_bogen(client, token, antworten).text
    assert "Alles beantwortet" in html, re.findall(r'<li><a href="#[^"]+">([^<]+)', html)
    assert "Meldung freigegeben" in client.post(f"/fall/{token}/freigeben", data={"csrf": sitzung_csrf(client)}).text


def test_vollstaendiger_ablauf_masern_mit_impfung_und_symptomen(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Clara")
    client.get(f"/fall/{token}")
    antworten = {
        "a.isDead": "no", "a.militaryAffiliation": "noReferenceToBundeswehr", "a.labSpecimenTaken": "no", "a.hospitalized": "yes",
        "a.infectProtectFacility": "no", "a.placeExposure": "no", "a.organDonation": "no",
        "s.immunization": "yes", "s.pregnancy": "no", "s.outbreak": "no", "s.onsetOfExanthem": "25.10.2026",
        "impfung_gesendet": "1", "impfstoff": "2241000221103", "impfdatum": "04.2022", "symptom_gesendet": "1",
    }
    html = client.post(f"/fall/{token}/bogen", data={**antworten, "symptom": ["386661006", "49727002"], "csrf": sitzung_csrf(client)}, headers={"HX-Request": "true"}).text
    assert "Alles beantwortet" in html, re.findall(r'<li><a href="#[^"]+">([^<]+)', html)
    vorschau = client.get(f"/fall/{token}/vorschau").text
    for erwartet in ("Fieber", "Husten", "Verdacht einer Erkrankung", "Masern-Mumps-Röteln"):
        assert erwartet in vorschau, erwartet


def test_impfung_ja_ohne_impfstoff_bleibt_offen(client):
    anmelden(client)
    token = token_fuer(client, "Testpatient, Clara")
    client.get(f"/fall/{token}")
    html = sende_bogen(client, token, {"s.immunization": "yes"}).text
    assert "Bitte den Impfstoff angeben" in html


# =============================================================================================
# Datenschutz im Protokoll (Harte Regel 5)
# =============================================================================================
def test_serverprotokoll_enthaelt_keine_patientendaten_und_keine_fall_kennungen(client, caplog):
    caplog.set_level(logging.DEBUG)
    anmelden(client)
    token = fuelle_cdi(client)
    client.get(f"/fall/{token}/vorschau")
    text = caplog.text
    assert "/fall/{token}" in text  # nur das Muster der Adresse
    for verboten in (token, "Testpatient", "Anna", "A04.71", "enc-", "pat-", "Musterstraße", "geheim"):
        assert verboten not in text, verboten
