"""Demo-Angaben für die DEMIS-Testfälle (1, 2, 3, 7): so würde eine Ärztin/ein Arzt den Meldebogen ergänzen.

Alles hier ist erfunden (synthetische Testdaten). Wird von den Tests, vom Kommandozeilenwerkzeug und später
von der Oberfläche (Demo-Modus) genutzt.
"""

from datetime import datetime, timezone

from meldeassistent.demis.angaben import Anschrift, Laboreinrichtung, MeldendeEinrichtung, Melder, MelderKonfig
from meldeassistent.demis.vorbelegung import ergaenze, vorbelegung
from meldeassistent.modell import KisFall

JETZT = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)

KONFIG = MelderKonfig(
    einrichtung=MeldendeEinrichtung(
        name="DRK Krankenhaus Chemnitz-Rabenstein gGmbH",
        anschrift=Anschrift(strasse="Unritzstraße 23", plz="09117", ort="Chemnitz"),
        telefon="+49 371 0000100",
        bsnr="123456789",  # erfunden
    ),
    hauslabor=Laboreinrichtung(name="Labor Testlabor (synthetisch)"),
)
MELDER = Melder(vorname="Test", nachname="Ärztin", telefon="+49 371 0000101")

# Fall-ID im Schein-KIS -> (DEMIS-Kürzel, Ergänzungen der Ärztin/des Arztes)
ALLGEMEIN_STANDARD = dict(
    militaryAffiliation="noReferenceToBundeswehr",
    infectProtectFacility="no",
    placeExposure="no",
    organDonation="no",
)
FAELLE = {
    "cdi": ("enc-01-cdi-schwer-cdi-einr", "CDFD"),
    "tb": ("enc-02-tb-offen-tb-einr", "MYTD"),
    "masern": ("enc-03-masern-verdacht-masern-einr", "MSVD"),
    "cdi_tot": ("enc-07-cdi-schwer-verstorben-cdi-einr", "CDFD"),
}

ERGAENZUNGEN = {
    "cdi": dict(
        allgemein={**ALLGEMEIN_STANDARD, "isDead": "no"},
        spezifisch=dict(immunization="no", method="117963005:{363701004=39477002}", outbreak="no"),
    ),
    "cdi_tot": dict(
        allgemein=dict(ALLGEMEIN_STANDARD),  # isDead kommt aus dem KIS
        spezifisch=dict(immunization="no", method="117963005:{363701004=39477002}", outbreak="no"),
    ),
    "tb": dict(
        allgemein={**ALLGEMEIN_STANDARD, "isDead": "no"},
        spezifisch=dict(
            immunization="ASKU",
            infectionEnvironmentSettingKind="NASK",
            nationality="DE",
            countryOfBirth="DE",
            childrenUnder15Years="no",
            causeDiagnosis="41769001:{246090004=404684003}",
            statusDiagnosis="yes",
            treatment="yes",
            treatmentBegin="2026-10-21",
            resultOfTreatment="NASK",
            majorSite="154283005",
            minorSite="260413007",
            prevTreatment="no",
            outbreak="no",
        ),
    ),
    "masern": dict(
        allgemein={**ALLGEMEIN_STANDARD, "isDead": "no"},
        spezifisch=dict(immunization="ASKU", onsetOfExanthem="2026-10-25", pregnancy="no", outbreak="no"),
        symptome=["386661006", "64611009", "247471006:{363698007=181469002}"],
    ),
}




def demo_angaben(fall: KisFall, name: str):
    """Vorbelegung aus den KIS-Daten plus die Ergänzungen der (fiktiven) Ärztin."""
    _, kuerzel = FAELLE[name]
    erg = dict(ERGAENZUNGEN[name])
    return ergaenze(vorbelegung(fall, kuerzel, KONFIG), allgemein=erg.pop("allgemein"), spezifisch=erg.pop("spezifisch"), **erg)
