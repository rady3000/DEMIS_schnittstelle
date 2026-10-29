"""Tests der reinen Logik hinter der Oberfläche: Regelwerk (vorläufig), Datumseingabe, Entwurf, Audit-Log."""

import json
from datetime import date, datetime, timezone

import pytest

from demis_faelle import FAELLE, KONFIG, MELDER, kis_adapter
from meldeassistent.audit import Audit
from meldeassistent.demis.pakete import Konzept
from meldeassistent.modell import Diagnose, Diagnosesicherheit, FallUebersicht, Verstorben
from meldeassistent.regelwerk import Meldeweg, bewerte
from meldeassistent.web import anzeige
from meldeassistent.web.entwurf import bestaetige, bewerte_entwurf, neuer_entwurf, wende_formular_an

JETZT = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


# --- Regelwerk -------------------------------------------------------------------------------
def zeile(icd, station="3A", laufend=True, verstorben=Verstorben.UNBEKANNT, sicherheit=Diagnosesicherheit.GESICHERT, fall_id="x"):
    return FallUebersicht(
        kis_fall_id=fall_id, patient_name="Test, Test", laufend=laufend, station=station, verstorben=verstorben,
        diagnosen=[Diagnose(icd_code=icd, sicherheit=sicherheit)] if icd else [],
    )


@pytest.mark.parametrize(
    "icd,weg,kuerzel",
    [
        ("A04.71", Meldeweg.DEMIS, "CDFD"), ("A04.70", Meldeweg.DEMIS, "CDFD"), ("A15.0", Meldeweg.DEMIS, "MYTD"), ("A16.2", Meldeweg.DEMIS, "MYTD"),
        ("B05.9", Meldeweg.DEMIS, "MSVD"), ("J10.1", Meldeweg.SACHSEN, None), ("J09", Meldeweg.SACHSEN, None), ("J11.1", Meldeweg.SACHSEN, None),
        ("I10", Meldeweg.KEINER, None), ("J18.9", Meldeweg.KEINER, None), (None, Meldeweg.KEINER, None),
    ],
)
def test_regelwerk_nach_diagnose(icd, weg, kuerzel):
    z = zeile(icd)
    b = bewerte(z, [z])
    assert (b.weg, b.kuerzel) == (weg, kuerzel)


def test_ausgeschlossene_diagnose_loest_keine_meldung_aus():
    z = zeile("B05.9", sicherheit=Diagnosesicherheit.AUSGESCHLOSSEN)
    assert bewerte(z, [z]).weg is Meldeweg.KEINER


def test_tod_bei_infektionskrankheit_ist_landesmeldung_ausser_aids():
    def weg(icd, verstorben):
        z = zeile(icd, verstorben=verstorben, laufend=verstorben is not Verstorben.JA)
        return bewerte(z, [z]).weg

    assert weg("A41.58", Verstorben.JA) is Meldeweg.SACHSEN
    assert weg("B20", Verstorben.JA) is Meldeweg.KEINER  # AIDS ist ausgenommen
    assert weg("I21.0", Verstorben.JA) is Meldeweg.KEINER  # keine Infektionskrankheit
    assert weg("A41.58", Verstorben.NEIN) is Meldeweg.KEINER  # lebt: keine Meldung nach § 1 Abs. 2
    assert weg("A41.58", Verstorben.UNBEKANNT) is Meldeweg.KEINER  # ohne Todesangabe wird nichts unterstellt


def test_demis_hat_vorrang_vor_todesmeldung():
    z = zeile("A04.71", verstorben=Verstorben.JA, laufend=False)
    assert bewerte(z, [z]).weg is Meldeweg.DEMIS


def test_gastroenteritis_nur_bei_haeufung_auf_derselben_station():
    a, b, c = zeile("A08.1", "3B", fall_id="1"), zeile("A08.1", "3B", fall_id="2"), zeile("A08.1", "4C", fall_id="3")
    assert bewerte(a, [a]).weg is Meldeweg.KEINER  # Einzelfall
    assert bewerte(a, [a, b]).weg is Meldeweg.KLAERUNG and "2 Fälle" in bewerte(a, [a, b]).grund
    assert bewerte(c, [a, b, c]).weg is Meldeweg.KEINER  # andere Station
    beendet = zeile("A08.1", "3B", laufend=False, fall_id="4")
    assert bewerte(a, [a, beendet]).weg is Meldeweg.KEINER  # beendete Fälle zählen nicht mit


# --- Datumseingabe und Anzeige -----------------------------------------------------------------
@pytest.mark.parametrize(
    "text,iso",
    [("22.10.2026", "2026-10-22"), (" 2.10.2026 ", "2026-10-02"), ("10.2026", "2026-10"), ("2026", "2026"), ("2026-10-22", "2026-10-22"), ("2026-10", "2026-10"),
     ("31.02.2026", None), ("32.01.2026", None), ("13.2026", None), ("1.1.1800", None), ("", None), ("morgen", None), ("22/10/2026", None), ("2026-10-22T10:00", None)],
)
def test_datum_aus_eingabe(text, iso):
    assert anzeige.datum_aus_eingabe(text) == iso


@pytest.mark.parametrize("iso,de", [("2026-10-22", "22.10.2026"), ("2026-10", "10.2026"), ("2026", "2026"), (None, ""), ("", ""), (date(2026, 1, 5), "05.01.2026"), ("2026-10-22T10:00:00+02:00", "22.10.2026")])
def test_datum_de(iso, de):
    assert anzeige.datum_de(iso) == de


def test_optionstexte():
    assert anzeige.option_text(Konzept(anzeige.NULLFLAVOR, "ASKU", "asked but unknown")) == "nicht ermittelbar"
    assert anzeige.option_text(Konzept(anzeige.ISO_LAENDER, "DE", "Germany")) == "Deutschland"
    assert anzeige.option_text(Konzept(anzeige.ISO_LAENDER, "TR", "Turkey")) == "Türkei"
    assert anzeige.option_text(Konzept("http://snomed.info/sct", "1", "Lunge")) == "Lunge"
    assert anzeige.option_text(Konzept("x", "abc", None)) == "abc"


def test_alter():
    assert anzeige.alter_jahre(date(2000, 10, 29), date(2026, 10, 28)) == 25  # Geburtstag noch nicht erreicht
    assert anzeige.alter_jahre(date(2000, 10, 28), date(2026, 10, 28)) == 26
    assert anzeige.alter_jahre(None, date(2026, 10, 28)) is None


# --- Entwurf -----------------------------------------------------------------------------------
@pytest.fixture
def cdi(pakete):
    fall = kis_adapter().lade_fall(FAELLE["cdi"][0])
    return fall, neuer_entwurf(fall, "CDFD", KONFIG, "x")


def stand(pakete, fall, e):
    return bewerte_entwurf(e, fall, MELDER, KONFIG, pakete, JETZT)


def test_neuer_entwurf_ist_aus_dem_kis_vorbelegt(pakete, cdi):
    fall, e = cdi
    assert e.angaben.allgemein["hospitalized"] == "yes" and e.angaben.herkunft["allgemein.hospitalized"] == "kis"
    assert e.angaben.spezifisch["form"].startswith("186431008") and e.angaben.herkunft["spezifisch.form"] == "auto"
    s = stand(pakete, fall, e)
    assert not s.bereit and not s.fehler and len(s.offen) == 9


def test_nicht_gesendete_felder_bleiben_unveraendert(pakete, cdi):
    fall, e = cdi
    wende_formular_an(e, {"a.isDead": ["no"]}, pakete)
    assert e.angaben.spezifisch["form"].startswith("186431008")  # nicht im Formular gewesen -> unberührt
    assert e.angaben.herkunft["spezifisch.form"] == "auto"


def test_gesehenes_feld_ohne_auswahl_wird_geleert(pakete, cdi):
    fall, e = cdi
    wende_formular_an(e, {"a.isDead": ["no"]}, pakete)
    wende_formular_an(e, {"_f": ["a.isDead"]}, pakete)  # Feld war im Formular, aber nichts gewählt
    assert "isDead" not in e.angaben.allgemein and "allgemein.isDead" not in e.angaben.herkunft


def test_aenderung_wird_zu_arzt_unveraenderter_wert_bleibt_kis(pakete, cdi):
    fall, e = cdi
    wende_formular_an(e, {"a.hospitalized": ["yes"], "a.isDead": ["no"]}, pakete)
    assert e.angaben.herkunft["allgemein.hospitalized"] == "kis" and e.angaben.herkunft["allgemein.isDead"] == "arzt"
    wende_formular_an(e, {"a.hospitalized": ["no"]}, pakete)
    assert e.angaben.herkunft["allgemein.hospitalized"] == "arzt"


def test_vorschlag_bestaetigen_nur_fuer_auto(pakete, cdi):
    fall, e = cdi
    bestaetige(e, "allgemein.hospitalized")  # ist 'kis': bleibt
    assert e.angaben.herkunft["allgemein.hospitalized"] == "kis"
    bestaetige(e, "spezifisch.form")
    assert e.angaben.herkunft["spezifisch.form"] == "arzt"


def test_folgefragen_in_einem_zug(pakete, cdi):
    fall, e = cdi
    wende_formular_an(e, {"a.isDead": ["yes"], "a.deathDate": ["22.10.2026"]}, pakete)  # deathDate wird erst durch isDead sichtbar
    assert e.angaben.allgemein["deathDate"] == "2026-10-22"


def test_antworten_auf_nicht_mehr_gestellte_fragen_werden_entfernt(pakete, cdi):
    fall, e = cdi
    wende_formular_an(e, {"a.isDead": ["yes"], "a.deathDate": ["22.10.2026"]}, pakete)
    wende_formular_an(e, {"a.isDead": ["no"]}, pakete)
    assert "deathDate" not in e.angaben.allgemein and "allgemein.deathDate" not in e.angaben.herkunft


def test_ungueltige_eingaben_werden_gemerkt_und_gemeldet(pakete, cdi):
    fall, e = cdi
    wende_formular_an(e, {"a.isDead": ["yes"], "a.deathDate": ["gestern"], "erkrankungsbeginn": ["10.2026"]}, pakete)
    assert e.ungueltig == {"a.deathDate": "gestern", "erkrankungsbeginn": "10.2026"}  # Erkrankungsbeginn braucht ein volles Datum
    texte = [o.text for o in stand(pakete, fall, e).fehler]
    assert sum("kein gültiges Datum" in t for t in texte) == 2
    wende_formular_an(e, {"a.deathDate": ["22.10.2026"], "erkrankungsbeginn": ["10.10.2026"]}, pakete)
    assert e.ungueltig == {}


def test_impfungen_nur_bei_ja_und_mit_stoff(pakete):
    fall = kis_adapter().lade_fall(FAELLE["masern"][0])
    e = neuer_entwurf(fall, "MSVD", KONFIG, "x")
    wende_formular_an(e, {"s.immunization": ["yes"], "impfung_gesendet": ["1"], "impfstoff": ["2241000221103"], "impfdatum": ["04.2022"]}, pakete)
    assert [(i.impfstoff_code, i.datum) for i in e.angaben.impfungen] == [("2241000221103", "2022-04")]
    wende_formular_an(e, {"s.immunization": ["no"]}, pakete)
    assert e.angaben.impfungen == []  # ohne "Ja" keine Impfung in der Meldung


def test_ja_bei_nicht_unterstuetzter_taetigkeit_bleibt_im_formular_moeglich_aber_wird_gemeldet(pakete, cdi):
    # Die Oberfläche sperrt "Ja", doch auch ein direkt gesendetes "Ja" darf keine ungültige Meldung ergeben
    fall, e = cdi
    wende_formular_an(e, {"a.infectProtectFacility": ["yes"]}, pakete)
    s = stand(pakete, fall, e)
    assert not s.bereit and any("Pflichtangabe fehlt" in o.text for o in s.fehler)


# --- Audit-Log -----------------------------------------------------------------------------------
def test_audit_schreibt_nur_erlaubte_felder(tmp_path):
    audit = Audit(tmp_path / "unterordner" / "audit.log")
    audit.schreibe("v1", "testarzt", "demis", "geoeffnet", JETZT)
    audit.schreibe("v1", "testarzt", "demis", "freigegeben_ohne_versand", JETZT, 75)
    zeilen = [json.loads(z) for z in (tmp_path / "unterordner" / "audit.log").read_text(encoding="utf-8").splitlines()]
    assert [set(z) for z in zeilen] == [{"zeit", "vorgang", "benutzer", "meldeweg", "status"}, {"zeit", "vorgang", "benutzer", "meldeweg", "status", "dauer_s"}]
    assert audit.lies() == zeilen


def test_audit_ohne_pfad_schreibt_nichts():
    assert Audit(None).schreibe("v", "u", "demis", "x", JETZT)["status"] == "x"
    assert Audit(None).lies() == []
