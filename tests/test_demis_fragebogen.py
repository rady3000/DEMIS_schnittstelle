"""Tests für Paket-Katalog sowie Aufbau und Prüfung der Fragebogen-Antworten.

Wahrheit sind die offiziellen Beispiele des RKI (im Paket mitgeliefert) und die Wertemengen des Pakets 3.0.0.
"""

import json
import tarfile
from datetime import date

import pytest

from meldeassistent.demis.fragebogen import UngueltigeAntwort, baue_antworten, pruefe_antworten
from meldeassistent.demis.pakete import PAKETORDNER

BASIS = "https://demis.rki.de/fhir"


def beispiel_bundle(kuerzel: str) -> dict:
    with tarfile.open(PAKETORDNER / "rki.demis.disease-3.0.0.tgz") as t:
        return json.load(t.extractfile(f"package/examples/example-bundle-notificationbundledisease-{kuerzel}-01.json"))


def beispiel_antworten(kuerzel: str) -> list[tuple[str, dict]]:
    """(Fragebogenname, QuestionnaireResponse) aller Fragebogen-Antworten eines offiziellen Beispiels."""
    ergebnis = []
    for e in beispiel_bundle(kuerzel)["entry"]:
        r = e["resource"]
        if r["resourceType"] == "QuestionnaireResponse":
            ergebnis.append((r["questionnaire"].rsplit("/", 1)[-1].removeprefix("DiseaseQuestions"), r))
    return ergebnis


# --- Paket-Katalog ---------------------------------------------------------------------------
def test_fragebogen_gibt_es_fuer_alle_krankheiten(pakete):
    assert len(pakete.fragebogen_nach_name) == 49
    for name in ("Common", "CDFD", "MYTD", "MSVD"):
        assert pakete.fragebogen_url(name) == f"{BASIS}/Questionnaire/DiseaseQuestions{name}"


def test_wertemenge_ja_nein_hat_vier_antworten(pakete):
    w = pakete.wertemenge(f"{BASIS}/ValueSet/yesOrNoOrNoInformation")
    assert {k.code for k in w.konzepte} == {"yes", "no", "NASK", "ASKU"}


def test_wertemenge_kennt_verschachtelte_einrichtungsarten(pakete):
    # 'hospital' liegt im Codesystem eine Ebene unter 'medFacility'
    w = pakete.wertemenge(f"{BASIS}/ValueSet/organizationType")
    assert w.finde("hospital").display == "Krankenhaus"
    assert w.finde("hospitalLab").display == "Krankenhauslabor"
    assert w.finde("xyz") is None


def test_wertemenge_laender_und_regionen_sind_aufzaehlbar(pakete):
    assert len(pakete.wertemenge(f"{BASIS}/ValueSet/answerSetCountry").konzepte) == 253
    assert pakete.wertemenge(f"{BASIS}/ValueSet/answerSetCountry").finde("DE").display == "Germany"
    assert len(pakete.wertemenge(f"{BASIS}/ValueSet/answerSetGeographicRegion").konzepte) > 3000


def test_unbekannte_wertemenge_ist_nicht_aufzaehlbar(pakete):
    w = pakete.wertemenge(f"{BASIS}/ValueSet/gibt-es-nicht")
    assert w.konzepte is None and w.finde("x") is None


# --- Prüfer an den offiziellen Beispielen ------------------------------------------------------
# Zwei Antworten der offiziellen Beispiele weichen von den Wertemengen des Pakets 3.0.0 ab (die Beispiele sind
# älter). Wir folgen den Wertemengen; das ist in OFFENE_FRAGEN.md vermerkt und wird in Phase 5 gegen DEMIS geprüft.
BEKANNT_VERALTET = {("cdfd", "CDFD", "method"), ("mytd", "Common", "placeExposureRegion")}


@pytest.mark.parametrize("kuerzel", ["cdfd", "mytd", "msvd"])
def test_pruefer_akzeptiert_offizielle_beispiele_bis_auf_bekannt_veraltete(pakete, kuerzel):
    gefunden = set()
    for name, qr in beispiel_antworten(kuerzel):
        for befund in pruefe_antworten(pakete.fragebogen(name), qr["item"], pakete):
            assert befund.schwere == "fehler"
            gefunden.add((kuerzel, name, befund.link_id))
    assert gefunden <= BEKANNT_VERALTET


def test_pruefer_findet_genau_die_zwei_veralteten_antworten(pakete):
    gefunden = set()
    for kuerzel in ("cdfd", "mytd", "msvd"):
        for name, qr in beispiel_antworten(kuerzel):
            gefunden |= {(kuerzel, name, b.link_id) for b in pruefe_antworten(pakete.fragebogen(name), qr["item"], pakete)}
    assert gefunden == BEKANNT_VERALTET


def als_antworten(items: list[dict]) -> dict:
    """Wandelt QuestionnaireResponse-Einträge in das einfache {linkId: Wert}-Format um (nur für Tests)."""
    ergebnis: dict = {}

    def wert(a: dict):
        if "valueCoding" in a:
            return a["valueCoding"]["code"]
        if "valueReference" in a:
            return a["valueReference"]["reference"]
        return a.get("valueDate") or a.get("valueString")

    def gehe(liste: list[dict], ziel: dict):
        for it in liste:
            if "answer" in it:
                werte = [wert(a) for a in it["answer"]]
                ziel[it["linkId"]] = werte if len(werte) > 1 else werte[0]
                for a in it["answer"]:
                    gehe(a.get("item", []), ziel)
            elif "item" in it:
                if it["linkId"] in WIEDERHOLT:
                    ziel.setdefault(it["linkId"], []).append(_kind(it))
                else:
                    gehe(it["item"], ziel)

    def _kind(gruppe: dict) -> dict:
        kind: dict = {}
        gehe(gruppe["item"], kind)
        return kind

    gehe(items, ergebnis)
    return ergebnis


WIEDERHOLT = {"hospitalizedGroup", "infectProtectFacilityGroup", "placeExposureGroup"}


def ohne_anzeige(wert):
    """Vergleichsform ohne Anzeigetexte (die in den Beispielen leicht von den Wertemengen abweichen)."""
    if isinstance(wert, dict):
        return {k: ohne_anzeige(v) for k, v in wert.items() if k != "display"}
    if isinstance(wert, list):
        return [ohne_anzeige(v) for v in wert]
    return wert


@pytest.mark.parametrize(
    "kuerzel,name",
    [("cdfd", "Common"), ("mytd", "MYTD"), ("msvd", "Common"), ("msvd", "MSVD")],
)
def test_aufbau_reproduziert_offizielle_beispiele(pakete, kuerzel, name):
    """Aus den Antworten eines offiziellen Beispiels baut unser Builder wieder dieselbe Struktur."""
    original = dict(beispiel_antworten(kuerzel))[name]
    nachgebaut = baue_antworten(pakete.fragebogen(name), als_antworten(original["item"]), pakete)
    assert ohne_anzeige(nachgebaut) == ohne_anzeige(original["item"])


# --- Aufbau ----------------------------------------------------------------------------------
def test_unbeantwortete_jaNein_fragen_werden_mit_nask_vorbelegt(pakete):
    items = baue_antworten(pakete.fragebogen("Common"), {}, pakete)
    by = {i["linkId"]: i for i in items}
    assert by["isDead"]["answer"][0]["valueCoding"]["code"] == "NASK"
    assert by["organDonation"]["answer"][0]["valueCoding"]["code"] == "NASK"


def test_ohne_vorbelegung_bleiben_fragen_leer(pakete):
    assert baue_antworten(pakete.fragebogen("Common"), {}, pakete, vorbelegen=False) == []


def test_folgefragen_erscheinen_nur_bei_ausloeser(pakete):
    fb = pakete.fragebogen("Common")
    ohne = {i["linkId"] for i in baue_antworten(fb, {"isDead": "no", "deathDate": "2026-10-22"}, pakete)}
    assert "deathDate" not in ohne
    mit = baue_antworten(fb, {"isDead": "yes", "deathDate": "2026-10-22"}, pakete)
    tod = next(i for i in mit if i["linkId"] == "isDead")
    assert tod["answer"][0]["item"] == [{"linkId": "deathDate", "answer": [{"valueDate": "2026-10-22"}]}]


def test_wiederholte_gruppe_wird_mehrfach_gebaut(pakete):
    antworten = {"hospitalized": "yes", "hospitalizedGroup": [{"hospitalizedEncounter": "Encounter/a"}, {"hospitalizedEncounter": "Encounter/b"}]}
    items = baue_antworten(pakete.fragebogen("Common"), antworten, pakete)
    frage = next(i for i in items if i["linkId"] == "hospitalized")
    gruppen = frage["answer"][0]["item"]
    assert [g["linkId"] for g in gruppen] == ["hospitalizedGroup", "hospitalizedGroup"]
    assert [g["item"][0]["answer"][0]["valueReference"]["reference"] for g in gruppen] == ["Encounter/a", "Encounter/b"]


def test_mehrere_antworten_auf_eine_frage(pakete):
    antworten = {"immunization": "yes", "immunizationRef": ["Immunization/a", "Immunization/b"]}
    items = baue_antworten(pakete.fragebogen("CDFD"), antworten, pakete)
    frage = next(i for i in items if i["linkId"] == "immunization")
    refs = frage["answer"][0]["item"][0]["answer"]
    assert [r["valueReference"]["reference"] for r in refs] == ["Immunization/a", "Immunization/b"]


def test_antwort_bekommt_system_und_anzeigetext_aus_der_wertemenge(pakete):
    items = baue_antworten(pakete.fragebogen("CDFD"), {"form": "186431008:{288556008=305351004}"}, pakete)
    coding = next(i for i in items if i["linkId"] == "form")["answer"][0]["valueCoding"]
    assert coding["system"] == "http://snomed.info/sct"
    assert coding["code"] == "186431008:{288556008=305351004}"
    assert "Intensivstation" in coding["display"]


@pytest.mark.parametrize("frage,wert", [("isDead", "vielleicht"), ("hospitalized", True), ("form", "123")])
def test_ungueltige_auswahl_wird_abgelehnt(pakete, frage, wert):
    fb = pakete.fragebogen("Common" if frage != "form" else "CDFD")
    with pytest.raises(UngueltigeAntwort, match="keine zulässige Antwort"):
        baue_antworten(fb, {frage: wert}, pakete)


@pytest.mark.parametrize("datum,ok", [("2026-10-22", True), ("2026-10", True), ("2026", True), (date(2026, 10, 22), True), ("22.10.2026", False), ("2026-13-01x", False)])
def test_datumsformate(pakete, datum, ok):
    fb = pakete.fragebogen("Common")
    antworten = {"isDead": "yes", "deathDate": datum}
    if ok:
        baue_antworten(fb, antworten, pakete)
    else:
        with pytest.raises(UngueltigeAntwort, match="Datum"):
            baue_antworten(fb, antworten, pakete)


# --- Prüfen: Fehler in Antworten werden verständlich gemeldet ----------------------------------
def pruefe(pakete, name, items):
    return pruefe_antworten(pakete.fragebogen(name), items, pakete)


def test_vollstaendige_antworten_haben_keine_befunde(pakete):
    items = baue_antworten(pakete.fragebogen("Common"), {"isDead": "no", "militaryAffiliation": "noReferenceToBundeswehr"}, pakete)
    assert pruefe(pakete, "Common", items) == []  # alles übrige ist mit NASK vorbelegt


def test_leerer_bogen_ist_fuer_demis_formal_gueltig_aber_im_strengen_modus_offen(pakete):
    # DEMIS belegt jede Pflichtfrage mit "nicht erhoben" vor; ein leerer Bogen ist deshalb formal in Ordnung
    for name in ("CDFD", "MYTD", "MSVD", "Common"):
        items = baue_antworten(pakete.fragebogen(name), {}, pakete)
        assert pruefe(pakete, name, items) == []
    items = baue_antworten(pakete.fragebogen("CDFD"), {}, pakete)
    offen = pruefe_antworten(pakete.fragebogen("CDFD"), items, pakete, streng=True)
    assert {b.link_id for b in offen} == {"form", "immunization", "method", "outbreak"}
    assert all(b.schwere == "offen" and b.text.startswith("Noch nicht beantwortet: „") for b in offen)


def test_streng_meldet_nur_unbeantwortetes_nicht_echte_antworten(pakete):
    antworten = {"form": "186431008:{288556008=305351004}", "immunization": "no", "method": "117963005:{363701004=39477002}", "outbreak": "ASKU"}
    items = baue_antworten(pakete.fragebogen("CDFD"), antworten, pakete)
    assert pruefe_antworten(pakete.fragebogen("CDFD"), items, pakete, streng=True) == []  # bewusstes "nicht ermittelbar" zählt als Antwort


def test_fehlende_pflichtgruppe_wird_gemeldet(pakete):
    fb = pakete.fragebogen("Common")
    items = [{"linkId": "hospitalized", "answer": [{"valueCoding": {"system": f"{BASIS}/CodeSystem/yesOrNoAnswer", "code": "yes"}}]}]
    befunde = pruefe(pakete, "Common", items)
    assert any(b.link_id == "hospitalizedGroup" and "Pflichtangabe fehlt" in b.text for b in befunde)


def test_antwort_ohne_ausloeser_wird_gemeldet(pakete):
    items = baue_antworten(pakete.fragebogen("Common"), {"isDead": "no"}, pakete, vorbelegen=True)
    items[0]["answer"][0]["item"] = [{"linkId": "deathDate", "answer": [{"valueDate": "2026-10-22"}]}]
    befunde = pruefe(pakete, "Common", items)
    assert any(b.link_id == "deathDate" and "nicht gestellt" in b.text for b in befunde)


def test_unbekannte_frage_wird_gemeldet(pakete):
    befunde = pruefe(pakete, "Common", [{"linkId": "gibtEsNicht", "answer": []}])
    assert any("Unbekannte Frage" in b.text for b in befunde)


def test_zwei_antworten_bei_einfachfrage(pakete):
    coding = {"valueCoding": {"system": f"{BASIS}/CodeSystem/yesOrNoAnswer", "code": "no"}}
    befunde = pruefe(pakete, "Common", [{"linkId": "isDead", "answer": [coding, coding]}])
    assert any("nur eine Antwort" in b.text for b in befunde)


def test_falscher_code_ungueltiges_datum_leerer_text_kaputter_verweis(pakete):
    ja = {"valueCoding": {"system": f"{BASIS}/CodeSystem/yesOrNoAnswer", "code": "yes"}}
    items = [
        {"linkId": "isDead", "answer": [{**ja, "item": [{"linkId": "deathDate", "answer": [{"valueDate": "gestern"}]}]}]},
        {"linkId": "additionalInformation", "answer": [{"valueString": "  "}]},
        {"linkId": "labSpecimenTaken", "answer": [{**ja, "item": [{"linkId": "labSpecimenLab", "answer": [{"valueReference": {"reference": "kaputt"}}]}]}]},
        {"linkId": "militaryAffiliation", "answer": [{"valueCoding": {"system": "x", "code": "falsch"}}]},
    ]
    texte = " | ".join(b.text for b in pruefe(pakete, "Common", items))
    assert "Es fehlt ein gültiges Datum" in texte
    assert "Der Text ist leer" in texte
    assert "Es fehlt der Verweis" in texte
    assert "nicht zulässig" in texte
