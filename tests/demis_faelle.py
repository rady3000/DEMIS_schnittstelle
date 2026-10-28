"""Hilfen für die DEMIS-Tests: KIS-Daten über den Fake-Server (ohne Docker) plus Demo-Angaben."""

from fake_fhir import BASIS, FakeFhirServer
from meldeassistent.kis.isik_fhir import IsikFhirAdapter
from meldeassistent.testdaten.demo_meldung import ERGAENZUNGEN, FAELLE, JETZT, KONFIG, MELDER, demo_angaben  # noqa: F401


def kis_adapter() -> IsikFhirAdapter:
    return IsikFhirAdapter(BASIS, client=FakeFhirServer().client())


def lade(name: str):
    """Gibt (KisFall, Meldeangaben) für einen DEMIS-Testfall zurück."""
    fall = kis_adapter().lade_fall(FAELLE[name][0])
    return fall, demo_angaben(fall, name)
