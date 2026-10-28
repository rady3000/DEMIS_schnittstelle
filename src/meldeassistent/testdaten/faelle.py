"""Synthetische Testfälle für das Schein-KIS.

ALLE Daten hier sind frei erfunden (Harte Regel 1): Die Patienten heißen "Testpatient", die
Adressen sind Fantasieadressen, die Laborwerte erfunden. Jede Ressource trägt das Tag
``SYNTHETISCH``; damit lässt sich später jederzeit prüfen, dass nichts anderes im Schein-KIS liegt.

Die Ressourcen folgen dem ISiK-Basismodul (Patient, Kontakt, Diagnose, Organisation, Standort).
Laborbefunde sind bewusst ein *vereinfachtes* Format (DiagnosticReport + Observation), weil noch
offen ist, ob und wie NEXUS Laborbefunde per FHIR liefert (siehe OFFENE_FRAGEN.md).

Die ICD-10-GM-Codes samt Texten wurden am 28.10.2026 vom Auftraggeber (Chefarzt) bestätigt
(siehe ICD_TEXTE). Das Regelwerk soll trotzdem nach Code-Präfix (z. B. "A04.7") zuordnen, nicht nach
dem exakten Code, weil das KIS je nach ICD-Version feinere oder andere Unterschlüssel liefern kann.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")

# --- Namensräume ---------------------------------------------------------------------------
TAG_SYSTEM = "https://meldeassistent.test/tags"
TESTFALL_SYSTEM = "https://meldeassistent.test/testfall"
SID_PATIENT = "https://meldeassistent.test/sid/patientennummer"
SID_BESUCH = "https://meldeassistent.test/sid/besuchsnummer"
SID_LABORNUMMER = "https://meldeassistent.test/sid/labornummer"
SID_STANDORT = "https://meldeassistent.test/sid/standort"

ISIK = "https://gematik.de/fhir/isik/StructureDefinition/"
ICD10GM = "http://fhir.de/CodeSystem/bfarm/icd-10-gm"
FACHABTEILUNG = "http://fhir.de/CodeSystem/dkgev/Fachabteilungsschluessel"
KONTAKTEBENE = "http://fhir.de/CodeSystem/Kontaktebene"
DIAGNOSESICHERHEIT_EXT = "http://fhir.de/StructureDefinition/icd-10-gm-diagnosesicherheit"
DIAGNOSESICHERHEIT_CS = "https://fhir.kbv.de/CodeSystem/KBV_CS_SFHIR_ICD_DIAGNOSESICHERHEIT"

# ICD-10-GM-Texte der in den Testfällen verwendeten Codes (vom Auftraggeber bestätigt)
ICD_TEXTE = {
    "A04.71": "Enterokolitis durch Clostridium difficile ohne Megakolon, mit sonstigen Organkomplikationen",
    "A15.0": "Lungentuberkulose, durch mikroskopische Untersuchung des Sputums gesichert, mit oder ohne Nachweis durch Kultur oder molekularbiologische Verfahren",
    "B05.9": "Masern ohne Komplikation",
    "J10.1": "Grippe mit sonstigen Manifestationen an den Atemwegen, saisonale Influenzaviren nachgewiesen",
    "A08.1": "Akute Gastroenteritis durch Norovirus",
    "A41.58": "Sepsis durch sonstige gramnegative Erreger",
}

# Meldewege, wie sie das Regelwerk später als Erwartung prüfen soll (siehe PLAN.md, Abschnitt 3)
WEG_DEMIS = "DEMIS"
WEG_SACHSEN = "SACHSEN"
WEG_KEIN_AUTOMATISCH = "KEIN_AUTOMATISCHER_WEG"

# --- Stammdaten ------------------------------------------------------------------------------
ID_EINRICHTUNG = "org-einrichtung"
ID_LABOR = "org-labor-test"

# Fachabteilungen: Schlüssel und Namen entsprechen der DEMIS-Wertemenge hospitalizationServiceType
ABTEILUNGEN = {
    "0100": "Innere Medizin",
    "1000": "Pädiatrie",
    "1400": "Lungen- und Bronchialheilkunde",
    "3600": "Intensivmedizin",
}

# Stationen: Schlüssel -> (Name, Fachabteilung)
STATIONEN = {
    "3a": ("Station 3A (Innere)", "0100"),
    "3b": ("Station 3B (Innere)", "0100"),
    "its": ("Intensivstation 1", "3600"),
    "iso": ("Isolierstation 2 (Pneumologie)", "1400"),
    "kind": ("Kinderstation 1", "1000"),
}


def _tags(testfall: str | None = None) -> list[dict]:
    tags = [{"system": TAG_SYSTEM, "code": "SYNTHETISCH", "display": "Synthetischer Testdatensatz"}]
    if testfall:
        tags.append({"system": TESTFALL_SYSTEM, "code": testfall})
    return tags


def _meta(profil: str | None, testfall: str | None = None) -> dict:
    meta: dict = {"tag": _tags(testfall)}
    if profil:
        meta["profile"] = [ISIK + profil]
    return meta


def _zeit(jahr: int, monat: int, tag: int, stunde: int = 0, minute: int = 0) -> str:
    """Zeitstempel in deutscher Ortszeit (berücksichtigt Sommer-/Winterzeit)."""
    return datetime(jahr, monat, tag, stunde, minute, tzinfo=BERLIN).isoformat()


def stammdaten() -> list[dict]:
    """Einrichtung, Fachabteilungen, Stationen und das (fiktive) Labor."""
    ressourcen: list[dict] = [
        {
            "resourceType": "Organization",
            "id": ID_EINRICHTUNG,
            "meta": _meta("ISiKOrganisation"),
            "name": "DRK Krankenhaus Chemnitz-Rabenstein gGmbH (Schein-KIS)",
            "address": [{"line": ["Unritzstraße 23"], "postalCode": "09117", "city": "Chemnitz", "country": "DE"}],
        },
        {
            "resourceType": "Organization",
            "id": ID_LABOR,
            "meta": _meta(None),
            "name": "Labor Testlabor (synthetisch)",
        },
    ]
    for schluessel, name in ABTEILUNGEN.items():
        ressourcen.append(
            {
                "resourceType": "Organization",
                "id": f"org-abt-{schluessel}",
                "meta": _meta("ISiKOrganisationFachabteilung"),
                "type": [
                    {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/organization-type", "code": "dept"}]},
                    {"coding": [{"system": FACHABTEILUNG, "code": schluessel, "display": name}]},
                ],
                "name": name,
                "partOf": {"reference": f"Organization/{ID_EINRICHTUNG}"},
            }
        )
    for schluessel, (name, abteilung) in STATIONEN.items():
        ressourcen.append(
            {
                "resourceType": "Location",
                "id": f"loc-{schluessel}",
                "meta": _meta("ISiKStandort"),
                "identifier": [{"system": SID_STANDORT, "value": f"TEST-{schluessel.upper()}"}],
                "status": "active",
                "mode": "instance",
                "name": name,
                "physicalType": {
                    "coding": [
                        {"system": "http://terminology.hl7.org/CodeSystem/location-physical-type", "code": "wa", "display": "Ward"}
                    ]
                },
                "managingOrganization": {"reference": f"Organization/org-abt-{abteilung}"},
            }
        )
    return ressourcen


# --- Bausteine für Fälle ---------------------------------------------------------------------
@dataclass
class Person:
    """Eine erfundene Patientin / ein erfundener Patient."""

    kennung: str  # kurze ID-Endung, z. B. "cdi"
    vorname: str
    geschlecht: str  # male | female
    geburtsdatum: str
    strasse: str
    hausnummer: str
    plz: str
    telefon: str
    verstorben: str | None = None  # Zeitstempel, falls verstorben


@dataclass
class Abschnitt:
    """Ein Aufenthaltsabschnitt auf einer Station (= ein Abteilungskontakt im KIS)."""

    station: str  # Schlüssel aus STATIONEN
    beginn: str
    ende: str | None = None


@dataclass
class Diagnose:
    icd: str
    sicherheit: str  # G = gesichert, V = Verdacht
    beginn: str  # Erkrankungsbeginn (Datum)
    erfasst: str  # Dokumentationsdatum
    hinweis: str


@dataclass
class Labor:
    nummer: str
    untersuchung: str
    ergebnis: str
    datum: str


@dataclass
class Fall:
    """Ein Testfall: eine oder mehrere Personen mit Aufenthalt, Diagnose und optional Labor."""

    schluessel: str
    titel: str
    erwarteter_weg: str
    erwartetes_demis_profil: str | None
    begruendung: str
    personen: list[tuple[Person, list[Abschnitt], Diagnose, Labor | None]] = field(default_factory=list)

    def ressourcen(self) -> list[dict]:
        ergebnis: list[dict] = []
        for person, abschnitte, diagnose, labor in self.personen:
            ergebnis += _patient_ressourcen(self.schluessel, person, abschnitte, diagnose, labor)
        return ergebnis


def _patient(fall: str, p: Person) -> dict:
    ressource: dict = {
        "resourceType": "Patient",
        "id": f"pat-{fall}-{p.kennung}",
        "meta": _meta("ISiKPatient", fall),
        "identifier": [
            {
                "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]},
                "system": SID_PATIENT,
                "value": f"TEST-{fall[:2]}-{p.kennung}",
            }
        ],
        "active": True,
        "name": [{"use": "official", "family": "Testpatient", "given": [p.vorname]}],
        "telecom": [{"system": "phone", "value": p.telefon, "use": "home"}],
        "gender": p.geschlecht,
        "birthDate": p.geburtsdatum,
        "address": [
            {
                "type": "both",
                "line": [f"{p.strasse} {p.hausnummer}"],
                "_line": [
                    {
                        "extension": [
                            {"url": "http://hl7.org/fhir/StructureDefinition/iso21090-ADXP-streetName", "valueString": p.strasse},
                            {"url": "http://hl7.org/fhir/StructureDefinition/iso21090-ADXP-houseNumber", "valueString": p.hausnummer},
                        ]
                    }
                ],
                "city": "Chemnitz",
                "postalCode": p.plz,
                "country": "DE",
            }
        ],
    }
    if p.verstorben:
        ressource["deceasedDateTime"] = p.verstorben
    return ressource


def _encounter_ressourcen(fall: str, p: Person, abschnitte: list[Abschnitt], diagnose_id: str) -> list[dict]:
    """Ein Einrichtungskontakt (ganzer Aufenthalt) plus je Station ein Abteilungskontakt."""
    pat = f"Patient/pat-{fall}-{p.kennung}"
    einr_id = f"enc-{fall}-{p.kennung}-einr"
    beginn = abschnitte[0].beginn
    ende = abschnitte[-1].ende
    einrichtungskontakt: dict = {
        "resourceType": "Encounter",
        "id": einr_id,
        "meta": _meta("ISiKKontaktGesundheitseinrichtung", fall),
        "extension": [
            {
                "url": "http://fhir.de/StructureDefinition/Aufnahmegrund",
                "extension": [
                    {
                        "url": "ErsteUndZweiteStelle",
                        "valueCoding": {
                            "system": "http://fhir.de/CodeSystem/dkgev/AufnahmegrundErsteUndZweiteStelle",
                            "code": "01",
                            "display": "Krankenhausbehandlung, vollstationär",
                        },
                    }
                ],
            }
        ],
        "identifier": [
            {
                "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "VN"}]},
                "system": SID_BESUCH,
                "value": f"TEST-{fall[:2]}-{p.kennung}",
            }
        ],
        "status": "finished" if ende else "in-progress",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP"},
        "type": [{"coding": [{"system": KONTAKTEBENE, "code": "einrichtungskontakt"}]}],
        "subject": {"reference": pat},
        "period": {"start": beginn, **({"end": ende} if ende else {})},
        "diagnosis": [
            {
                "condition": {"reference": f"Condition/{diagnose_id}"},
                "use": {"coding": [{"system": "http://fhir.de/CodeSystem/KontaktDiagnoseProzedur", "code": "treatment-diagnosis"}]},
                "rank": 1,
            }
        ],
    }
    if p.verstorben:
        # Entlassung wegen Tod (HL7 "exp" = verstorben; 07 = Tod nach dem Entlassungsgrund-Schlüssel)
        einrichtungskontakt["hospitalization"] = {
            "dischargeDisposition": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/discharge-disposition", "code": "exp"}],
                "extension": [
                    {
                        "url": "http://fhir.de/StructureDefinition/Entlassungsgrund",
                        "extension": [
                            {
                                "url": "ErsteUndZweiteStelle",
                                "valueCoding": {
                                    "system": "http://fhir.de/CodeSystem/dkgev/EntlassungsgrundErsteUndZweiteStelle",
                                    "code": "07",
                                    "display": "Tod",
                                },
                            }
                        ],
                    }
                ],
            }
        }
    ergebnis = [einrichtungskontakt]
    for nummer, a in enumerate(abschnitte, start=1):
        station_name, abteilung = STATIONEN[a.station]
        ergebnis.append(
            {
                "resourceType": "Encounter",
                "id": f"enc-{fall}-{p.kennung}-abt{nummer}",
                "meta": _meta("ISiKKontaktGesundheitseinrichtung", fall),
                "identifier": [
                    {
                        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "VN"}]},
                        "system": SID_BESUCH,
                        "value": f"TEST-{fall[:2]}-{p.kennung}-{nummer}",
                    }
                ],
                "status": "finished" if a.ende else "in-progress",
                "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP"},
                "type": [{"coding": [{"system": KONTAKTEBENE, "code": "abteilungskontakt"}]}],
                "serviceType": {
                    "coding": [{"system": FACHABTEILUNG, "code": abteilung, "display": ABTEILUNGEN[abteilung]}]
                },
                "subject": {"reference": pat},
                "period": {"start": a.beginn, **({"end": a.ende} if a.ende else {})},
                "location": [
                    {
                        "location": {"reference": f"Location/loc-{a.station}", "display": station_name},
                        "status": "active" if not a.ende else "completed",
                        "physicalType": {
                            "coding": [
                                {"system": "http://terminology.hl7.org/CodeSystem/location-physical-type", "code": "wa"}
                            ]
                        },
                    }
                ],
                "partOf": {"reference": f"Encounter/{einr_id}"},
            }
        )
    return ergebnis


def _condition(fall: str, p: Person, d: Diagnose, diagnose_id: str) -> dict:
    gesichert = d.sicherheit == "G"
    return {
        "resourceType": "Condition",
        "id": diagnose_id,
        "meta": _meta("ISiKDiagnose", fall),
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        "verificationStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                    "code": "confirmed" if gesichert else "provisional",
                }
            ]
        },
        "code": {
            "coding": [
                {
                    "system": ICD10GM,
                    "version": "2026",
                    "code": d.icd,
                    "display": ICD_TEXTE[d.icd],
                    "extension": [
                        {
                            "url": DIAGNOSESICHERHEIT_EXT,
                            "valueCoding": {
                                "system": DIAGNOSESICHERHEIT_CS,
                                "code": d.sicherheit,
                                "display": "gesicherte Diagnose" if gesichert else "Verdachtsdiagnose",
                            },
                        }
                    ],
                }
            ]
        },
        "subject": {"reference": f"Patient/pat-{fall}-{p.kennung}"},
        "encounter": {"reference": f"Encounter/enc-{fall}-{p.kennung}-einr"},
        "onsetDateTime": d.beginn,
        "recordedDate": d.erfasst,
        "note": [{"text": d.hinweis}],
    }


def _labor(fall: str, p: Person, l: Labor) -> list[dict]:
    pat = f"Patient/pat-{fall}-{p.kennung}"
    obs_id = f"obs-{fall}-{p.kennung}"
    return [
        {
            "resourceType": "Observation",
            "id": obs_id,
            "meta": _meta(None, fall),
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
            "code": {"text": l.untersuchung},
            "subject": {"reference": pat},
            "encounter": {"reference": f"Encounter/enc-{fall}-{p.kennung}-einr"},
            "effectiveDateTime": l.datum,
            "valueString": l.ergebnis,
        },
        {
            "resourceType": "DiagnosticReport",
            "id": f"lab-{fall}-{p.kennung}",
            "meta": _meta(None, fall),
            "identifier": [{"system": SID_LABORNUMMER, "value": l.nummer}],
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": "LAB"}]}],
            "code": {"text": l.untersuchung},
            "subject": {"reference": pat},
            "encounter": {"reference": f"Encounter/enc-{fall}-{p.kennung}-einr"},
            "effectiveDateTime": l.datum,
            "issued": l.datum,
            "performer": [{"reference": f"Organization/{ID_LABOR}"}],
            "result": [{"reference": f"Observation/{obs_id}"}],
        },
    ]


def _patient_ressourcen(fall: str, p: Person, abschnitte: list[Abschnitt], d: Diagnose, labor: Labor | None) -> list[dict]:
    diagnose_id = f"cond-{fall}-{p.kennung}"
    ressourcen = [_patient(fall, p)]
    ressourcen += _encounter_ressourcen(fall, p, abschnitte, diagnose_id)
    ressourcen.append(_condition(fall, p, d, diagnose_id))
    if labor:
        ressourcen += _labor(fall, p, labor)
    return ressourcen


# --- Die sieben Testfälle (PLAN.md, Abschnitt 3) ---------------------------------------------
def alle_faelle() -> list[Fall]:
    z = _zeit
    return [
        Fall(
            schluessel="01-cdi-schwer",
            titel="C. difficile, schwere Verlaufsform, Verlegung auf ITS",
            erwarteter_weg=WEG_DEMIS,
            erwartetes_demis_profil="CDFD",
            begruendung="§ 6 Abs. 1 IfSG: C. difficile schwere Verlaufsform (NotificationDiseaseCDFD)",
            personen=[
                (
                    Person("cdi", "Anna", "female", "1948-03-14", "Musterstraße", "12", "09117", "+49 371 0000001"),
                    [
                        Abschnitt("3a", z(2026, 10, 12, 8, 15), z(2026, 10, 16, 14, 0)),
                        Abschnitt("its", z(2026, 10, 16, 14, 0)),
                    ],
                    Diagnose("A04.71", "G", "2026-10-10", "2026-10-18", "Synthetischer Testfall: schwere Verlaufsform, Verlegung auf die Intensivstation."),
                    Labor("L-2026-100001", "Clostridioides difficile Toxin A/B (Stuhl)", "positiv", z(2026, 10, 17, 9, 30)),
                )
            ],
        ),
        Fall(
            schluessel="02-tb-offen",
            titel="Offene Lungentuberkulose (mikroskopisch positiv)",
            erwarteter_weg=WEG_DEMIS,
            erwartetes_demis_profil="MYTD",
            begruendung="§ 6 Abs. 1 IfSG: Tuberkulose (NotificationDiseaseMYTD)",
            personen=[
                (
                    Person("tb", "Boris", "male", "1979-07-02", "Beispielweg", "4", "09130", "+49 371 0000002"),
                    [Abschnitt("iso", z(2026, 10, 20, 10, 0))],
                    Diagnose("A15.0", "G", "2026-09-28", "2026-10-21", "Synthetischer Testfall: offene Lungentuberkulose, Isolierung."),
                    Labor("L-2026-100002", "Sputum, Mikroskopie auf säurefeste Stäbchen", "nachgewiesen", z(2026, 10, 21, 11, 0)),
                )
            ],
        ),
        Fall(
            schluessel="03-masern-verdacht",
            titel="Masern, Verdachtsfall bei Kind",
            erwarteter_weg=WEG_DEMIS,
            erwartetes_demis_profil="MSVD",
            begruendung="§ 6 Abs. 1 IfSG: Masern, Verdacht (NotificationDiseaseMSVD). Kein Laborbefund vorhanden",
            personen=[
                (
                    Person("masern", "Clara", "female", "2019-05-09", "Probestraße", "7", "09112", "+49 371 0000003"),
                    [Abschnitt("kind", z(2026, 10, 26, 16, 40))],
                    Diagnose("B05.9", "V", "2026-10-24", "2026-10-26", "Synthetischer Testfall: Exanthem und Fieber, Masern-Verdacht, Labor ausstehend."),
                    None,
                )
            ],
        ),
        Fall(
            schluessel="04-influenza",
            titel="Saisonale Influenza (nachgewiesen)",
            erwarteter_weg=WEG_SACHSEN,
            erwartetes_demis_profil=None,
            begruendung="SächsIfSMeldeVO § 1 Abs. 1 Nr. 9 (Influenza). In DEMIS nur zoonotische Influenza (IZVD) als Arztmeldung",
            personen=[
                (
                    Person("grippe", "Dieter", "male", "1952-11-30", "Teststraße", "3", "09126", "+49 371 0000004"),
                    [Abschnitt("3a", z(2026, 10, 25, 20, 10))],
                    Diagnose("J10.1", "G", "2026-10-23", "2026-10-26", "Synthetischer Testfall: Influenza, PCR positiv."),
                    Labor("L-2026-100004", "Influenza-A-Virus, PCR (Rachenabstrich)", "nachgewiesen", z(2026, 10, 26, 8, 45)),
                )
            ],
        ),
        Fall(
            schluessel="05-norovirus-ausbruch",
            titel="Norovirus-Ausbruchsverdacht auf Station 3B (3 Patienten)",
            erwarteter_weg=WEG_KEIN_AUTOMATISCH,
            erwartetes_demis_profil=None,
            begruendung=(
                "§ 6 Abs. 3 IfSG (Häufung nosokomialer Infektionen, nichtnamentlich). DEMIS kennt den Typ 6.3, "
                "aber kein Profil; Norovirus steht nicht in der SächsIfSMeldeVO. Das Landesformular enthält die Zeile "
                "'zwei oder mehr nosokomiale Infektionen'. Rückfallzweig: manuelle Klärung"
            ),
            personen=[
                (
                    Person("noro1", "Erwin", "male", "1944-01-19", "Fantasieallee", "21", "09119", "+49 371 0000005", None),
                    [Abschnitt("3b", z(2026, 10, 19, 9, 0))],
                    Diagnose("A08.1", "V", "2026-10-26", "2026-10-27", "Synthetischer Testfall: akute Gastroenteritis, Norovirus-Verdacht, stationär erworben."),
                    None,
                ),
                (
                    Person("noro2", "Frieda", "female", "1951-06-03", "Fantasieallee", "23", "09119", "+49 371 0000006"),
                    [Abschnitt("3b", z(2026, 10, 20, 9, 30))],
                    Diagnose("A08.1", "V", "2026-10-26", "2026-10-27", "Synthetischer Testfall: akute Gastroenteritis, Norovirus-Verdacht, stationär erworben."),
                    None,
                ),
                (
                    Person("noro3", "Gustav", "male", "1960-12-12", "Fantasieallee", "25", "09119", "+49 371 0000007"),
                    [Abschnitt("3b", z(2026, 10, 21, 14, 15))],
                    Diagnose("A08.1", "V", "2026-10-27", "2026-10-27", "Synthetischer Testfall: akute Gastroenteritis, Norovirus-Verdacht, stationär erworben."),
                    None,
                ),
            ],
        ),
        Fall(
            schluessel="06-mrgn-verstorben",
            titel="Sepsis mit 4MRGN Klebsiella pneumoniae, Patient verstorben",
            erwarteter_weg=WEG_SACHSEN,
            erwartetes_demis_profil=None,
            begruendung=(
                "SächsIfSMeldeVO § 1 Abs. 2: Tod infolge einer sonstigen Infektionskrankheit. "
                "Der Erregernachweis selbst ist Laborsache (§ 7 IfSG)"
            ),
            personen=[
                (
                    Person(
                        "mrgn", "Hans", "male", "1941-02-21", "Zufallsring", "5", "09113", "+49 371 0000008",
                        verstorben=z(2026, 10, 21, 6, 40),
                    ),
                    [Abschnitt("3a", z(2026, 10, 5, 11, 20), z(2026, 10, 21, 6, 40))],
                    Diagnose("A41.58", "G", "2026-10-18", "2026-10-21", "Synthetischer Testfall: Sepsis durch 4MRGN Klebsiella pneumoniae (Blutkultur), Tod am 21.10.2026."),
                    Labor("L-2026-100006", "Blutkultur: Klebsiella pneumoniae, 4MRGN", "nachgewiesen", z(2026, 10, 19, 15, 0)),
                )
            ],
        ),
        Fall(
            schluessel="07-cdi-schwer-verstorben",
            titel="C. difficile, schwere Verlaufsform, Patientin verstorben",
            erwarteter_weg=WEG_DEMIS,
            erwartetes_demis_profil="CDFD",
            begruendung="Wie Fall 1; zusätzlich Todesangabe in DEMIS (Fragebogen isDead = yes, deathDate)",
            personen=[
                (
                    Person(
                        "cdi", "Ingrid", "female", "1939-09-05", "Phantasiegasse", "9", "09111", "+49 371 0000009",
                        verstorben=z(2026, 10, 22, 3, 20),
                    ),
                    [
                        Abschnitt("3a", z(2026, 10, 8, 13, 0), z(2026, 10, 13, 10, 0)),
                        Abschnitt("its", z(2026, 10, 13, 10, 0), z(2026, 10, 22, 3, 20)),
                    ],
                    Diagnose("A04.71", "G", "2026-10-09", "2026-10-14", "Synthetischer Testfall: schwere Verlaufsform, ITS, Tod am 22.10.2026."),
                    Labor("L-2026-100007", "Clostridioides difficile Toxin A/B (Stuhl)", "positiv", z(2026, 10, 14, 9, 0)),
                )
            ],
        ),
    ]


def transaktions_bundle(ressourcen: list[dict]) -> dict:
    """Verpackt Ressourcen als FHIR-Transaktion mit PUT (wiederholbar: gleiche IDs, keine Duplikate)."""
    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {"resource": r, "request": {"method": "PUT", "url": f"{r['resourceType']}/{r['id']}"}}
            for r in ressourcen
        ],
    }
