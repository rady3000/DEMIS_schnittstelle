"""Übersetzt technische Prüfmeldungen des FHIR-Validators in verständliches Deutsch.

Ärztinnen und Ärzte sollen "Pflichtangabe fehlt: Vorname der betroffenen Person" lesen, nicht
"Patient.name.given: minimum required = 1, but only found 0". Das Original bleibt als
``technisch`` erhalten (für die IT), wird in der Oberfläche aber nicht in den Vordergrund gestellt.

Unbekannte Meldungen werden nicht verschluckt: Sie erscheinen als "Technischer Prüfhinweis" mit dem
Originaltext. Harmloses Rauschen (reine Best-Practice-Hinweise, nicht prüfbare externe Codes) wird
bewusst ausgeblendet; die Liste steht in ``RAUSCHEN`` und ist in WARTUNG.md erklärt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Meldungen, die nichts mit der Qualität einer Meldung zu tun haben
RAUSCHEN = (
    "dom-6",  # Empfehlung, Texte zu ergänzen
    "could not be resolved, so no validation can be performed against the base questionnaire",  # prüfen wir selbst
    "because the validator is running without terminology services",  # SNOMED/ISO/LOINC: prüfen wir selbst
    "Reference to draft CodeSystem",
    "does not match any known slice",
    "A definition could not be found for Canonical URL",
    "Wrong Display Name",  # deutsche Anzeigetexte gegen englische Standardtexte
    "Unable to validate code without using server",
    "so the code cannot be validated",  # externe Terminologie (SNOMED-Version) nicht vorhanden: prüfen wir selbst
    "out of bounds for length",  # bekannter Fehler im Validator bei SNOMED-Codes
    "The code provided (http://snomed.info/sct#",  # SNOMED-Wertemenge nicht auflösbar: prüft der Mapper selbst
)

PROFIL_NAMEN = {
    "NotifiedPerson": "Betroffene Person",
    "NotifiedPersonFacility": "Aufenthaltsort der betroffenen Person",
    "NotifierFacility": "Meldende Einrichtung",
    "Notifier": "Meldende Person",
    "NotifierRole": "Meldende Person und Einrichtung",
    "Hospitalization": "Krankenhausaufenthalt",
    "DiseaseInformationCommon": "Allgemeine klinische Angaben",
    "Organization": "Labor",
    "NotificationBundleDisease": "Meldung",
}
TYP_NAMEN = {
    "Composition": "Meldung (Kopfdaten)",
    "Patient": "Betroffene Person",
    "Condition": "Erkrankung",
    "Encounter": "Krankenhausaufenthalt",
    "Immunization": "Impfung",
    "QuestionnaireResponse": "Klinische Angaben",
    "Organization": "Einrichtung",
    "Practitioner": "Meldende Person",
    "PractitionerRole": "Meldende Person und Einrichtung",
    "Bundle": "Meldung",
}

# Verständliche Bezeichnungen für Elemente (Pfad ohne Ressourcentyp und ohne Indizes)
ELEMENT_NAMEN = {
    "name.given": "Vorname",
    "name.family": "Nachname",
    "name": "Name",
    "gender": "Geschlecht",
    "birthDate": "Geburtsdatum",
    "address": "Anschrift",
    "address.line": "Straße und Hausnummer",
    "address.city": "Ort",
    "address.postalCode": "Postleitzahl",
    "address.country": "Land",
    "address.extension": "Art der Anschrift",
    "telecom": "Telefonnummer oder E-Mail",
    "telecom.value": "Telefonnummer oder E-Mail",
    "telecom.system": "Art des Kontakts",
    "type": "Art der Einrichtung",
    "period": "Zeitraum",
    "period.start": "Beginn",
    "period.end": "Ende",
    "serviceType": "Fachabteilung",
    "verificationStatus": "Verdacht oder bestätigt",
    "code": "Meldetatbestand",
    "onsetDateTime": "Erkrankungsbeginn",
    "recordedDate": "Diagnosedatum",
    "practitioner": "Meldende Person",
    "organization": "Meldende Einrichtung",
    "subject": "Verweis auf die betroffene Person",
    "category": "Meldetyp",
    "category.coding.code": "Meldetyp",
    "author": "Verweis auf die meldende Person",
    "identifier": "Kennung",
    "item": "Antworten",
    "vaccineCode": "Impfstoff",
    "occurrenceDateTime": "Impfdatum",
    "evidence.code": "Symptom",
}

CONSTRAINTS = {
    "validBirthDate": "Das Geburtsdatum hat ein ungültiges Format oder liegt in der Zukunft.",
    "atLeastOneMetaProfile": "Technischer Fehler: Bei einer Angabe fehlt die Profilzuordnung. Bitte die IT informieren.",
}


@dataclass(frozen=True)
class Problem:
    schwere: str  # "fehler" | "hinweis"
    wo: str  # lesbarer Ort, z. B. "Betroffene Person"
    text: str  # verständlicher deutscher Satz
    quelle: str = "validator"  # validator | fragebogen | mapper
    technisch: str | None = None  # Originalmeldung, nur für die IT
    folgefehler: bool = False  # True: nur die Folge eines anderen Fehlers

    def __str__(self) -> str:
        return f"{self.wo}: {self.text}"


def _eintrag_und_pfad(issue: dict, bundle: dict) -> tuple[dict | None, str]:
    """Findet die betroffene Ressource im Bundle und den Elementpfad (ohne Indizes)."""
    ausdruck = (issue.get("expression") or [""])[0]
    treffer = re.match(r"Bundle\.entry\[(\d+)\]\.resource(?:/\*[^*]*\*/)?\.?(.*)", ausdruck)
    if not treffer:
        return None, ""
    index, rest = int(treffer.group(1)), treffer.group(2)
    eintraege = bundle.get("entry", [])
    ressource = eintraege[index]["resource"] if index < len(eintraege) else None
    pfad = re.sub(r"\[\d+\]", "", rest)
    pfad = re.sub(r"\.value\.ofType\(\w+\)", "", pfad)
    return ressource, pfad


def _profilname(ressource: dict | None) -> str:
    if not ressource:
        return "Meldung"
    profile = (ressource.get("meta") or {}).get("profile") or []
    kurz = profile[0].rsplit("/", 1)[-1].split("|")[0] if profile else ""
    if kurz in PROFIL_NAMEN:
        return PROFIL_NAMEN[kurz]
    if kurz.startswith("NotificationDisease"):
        return "Meldung (Kopfdaten)"
    if kurz.startswith("DiseaseInformation"):
        return "Krankheitsspezifische Angaben"
    if kurz.startswith("Disease"):
        return "Erkrankung"
    if kurz.startswith("ImmunizationInformation"):
        return "Impfung"
    return TYP_NAMEN.get(ressource.get("resourceType", ""), "Meldung")


def _element_name(pfad: str) -> str:
    if not pfad:
        return ""
    if pfad == "item" or pfad.startswith("item."):
        return "Antwort im Fragebogen"
    # Codes liegen in coding/code: für die Bezeichnung zählt das Feld darüber ("type.coding.code" -> "type")
    pfad = re.sub(r"(\.coding)?(\.code|\.system|\.display)?$", "", pfad) or pfad
    # längsten passenden Pfad-Endabschnitt suchen
    teile = pfad.split(".")
    for start in range(len(teile)):
        schluessel = ".".join(teile[start:])
        if schluessel in ELEMENT_NAMEN:
            return ELEMENT_NAMEN[schluessel]
    return pfad


def uebersetze(issue: dict, bundle: dict) -> Problem | None:
    """Gibt ein deutsches Problem zurück oder None, wenn die Meldung ignoriert werden soll."""
    original = issue["details"]["text"]
    schwere_original = issue["severity"]
    if schwere_original == "information" or any(r in original for r in RAUSCHEN):
        return None
    schwere = "fehler" if schwere_original in ("error", "fatal") else "hinweis"

    ressource, pfad = _eintrag_und_pfad(issue, bundle)
    wo = _profilname(ressource)

    # vollständigen Elementpfad aus dem Text bevorzugen ("Patient.name.given: minimum required …")
    aus_text = re.match(r"^([A-Z][A-Za-z]+)\.([\w.\[\]]+): (?:minimum|max)", original)
    if aus_text:
        pfad = aus_text.group(2)
    feld = _element_name(pfad)
    ort = f"{wo} – {feld}" if feld else wo

    if m := re.search(r"minimum required = (\d+), but only found (\d+)", original):
        return Problem(schwere, wo, f"Pflichtangabe fehlt: {feld or 'unbekanntes Feld'}.", technisch=original)
    if m := re.search(r"max allowed = (\d+), but found (\d+)", original):
        return Problem(schwere, wo, f"Zu viele Einträge bei „{feld}“ (erlaubt: höchstens {m.group(1)}).", technisch=original)
    if m := re.search(r"Value is '([^']*)' but is fixed to '([^']*)'", original):
        return Problem(schwere, wo, f"Falscher Wert „{m.group(1)}“ bei „{feld}“. Erwartet wird „{m.group(2)}“.", technisch=original)
    if m := re.search(r"The value provided \('([^']*)'\) was not found in the value set 'AdministrativeGender'", original):
        return Problem(schwere, wo, f"Ungültiges Geschlecht „{m.group(1)}“. Erlaubt sind männlich, weiblich, divers, unbestimmt.", technisch=original)
    if re.search(r"The System URI could not be determined for the code", original):
        return None  # Doppelmeldung zum Geschlecht
    if m := re.search(r"Unknown code '([^']*)' in the CodeSystem", original):
        return Problem(schwere, wo, f"Der Wert „{m.group(1)}“ ist bei „{feld}“ nicht zulässig.", technisch=original)
    if m := re.search(r"The Coding provided \([^)#]*#([^)]*)\) was not found in the value set", original):
        return Problem(schwere, wo, f"Der Wert „{m.group(1)}“ ist bei „{feld}“ nicht zulässig.", technisch=original)
    if m := re.search(r"Unable to find a profile match for (\w+)/", original):
        return Problem(
            schwere,
            TYP_NAMEN.get(m.group(1), wo),
            "Diese Angabe entspricht nicht dem DEMIS-Profil. Das ist meist die Folge eines anderen Fehlers; bitte zuerst die übrigen Fehler beheben.",
            technisch=original,
            folgefehler=True,
        )
    if m := re.search(r"Constraint failed: (\w+): '(.*)'", original):
        text = CONSTRAINTS.get(m.group(1), f"Regel verletzt: {m.group(2)}")
        return Problem(schwere, wo, text, technisch=original)
    return Problem(schwere, ort, f"Technischer Prüfhinweis: {original}", technisch=original)
