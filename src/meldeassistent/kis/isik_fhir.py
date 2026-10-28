"""KIS-Adapter für eine ISiK-konforme FHIR-R4-Schnittstelle (NEXUS; im Test das HAPI-Schein-KIS).

Datenschutz (Harte Regel 5): Fehlermeldungen und Logzeilen enthalten nur Ressourcentyp, HTTP-Status
und Anzahlen. Niemals Namen, Diagnosen, IDs von Patienten oder Antworttexte des Servers.
"""

from __future__ import annotations

import logging
from datetime import date
from urllib.parse import quote

import httpx

from meldeassistent.modell import (
    Diagnose,
    FallUebersicht,
    KisFall,
    Laborbefund,
    Verstorben,
)

from . import isik_mapper as m
from .schnittstelle import KisAdapter, KisAntwortFehler, KisDatenFehler, KisNichtErreichbar

logger = logging.getLogger(__name__)

# Die HTTP-Bibliothek protokolliert sonst jede Anfrage-URL, und darin stehen IDs von Patienten und Fällen
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

MAX_SEITEN = 200  # Schutz vor Endlosschleifen bei fehlerhaften "next"-Links


class IsikFhirAdapter(KisAdapter):
    def __init__(
        self,
        basis_url: str,
        token: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 30,
        seitengroesse: int = 100,
    ):
        self.basis_url = basis_url.rstrip("/")
        self.seitengroesse = seitengroesse
        headers = {"Accept": "application/fhir+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # Ein von außen übergebener Client (z. B. für Tests) wird nicht von uns geschlossen
        self._eigener_client = client is None
        self._client = client or httpx.Client(timeout=timeout, headers=headers)
        if client is not None and token:
            self._client.headers["Authorization"] = f"Bearer {token}"

    def schliessen(self) -> None:
        if self._eigener_client:
            self._client.close()

    def __enter__(self) -> "IsikFhirAdapter":
        return self

    def __exit__(self, *_) -> None:
        self.schliessen()

    # --- Zugriff auf den Server ------------------------------------------------------------
    def _get(self, url: str, params: dict | None, was: str) -> dict:
        try:
            antwort = self._client.get(url, params=params)
        except httpx.TimeoutException as fehler:
            raise KisNichtErreichbar(f"Das KIS antwortet nicht rechtzeitig ({was}).") from fehler
        except httpx.HTTPError as fehler:
            raise KisNichtErreichbar(f"Das KIS ist nicht erreichbar ({was}).") from fehler
        if antwort.status_code in (401, 403):
            raise KisAntwortFehler(f"Anmeldung am KIS abgelehnt (HTTP {antwort.status_code}).", antwort.status_code)
        if antwort.status_code == 404:
            raise KisAntwortFehler(f"Im KIS nicht gefunden ({was}).", 404)
        if antwort.status_code >= 400:
            raise KisAntwortFehler(f"Das KIS meldet einen Fehler (HTTP {antwort.status_code}, {was}).", antwort.status_code)
        try:
            daten = antwort.json()
        except ValueError as fehler:
            raise KisDatenFehler(f"Das KIS hat keine gültigen FHIR-Daten geliefert ({was}).") from fehler
        if not isinstance(daten, dict):
            raise KisDatenFehler(f"Das KIS hat keine gültigen FHIR-Daten geliefert ({was}).")
        return daten

    def _lese(self, typ: str, id_: str) -> dict:
        ressource = self._get(f"{self.basis_url}/{typ}/{quote(m.pruefe_fhir_id(id_))}", None, typ)
        if ressource.get("resourceType") != typ:
            raise KisDatenFehler(f"Das KIS hat statt {typ} etwas anderes geliefert.")
        return ressource

    def _suche(self, typ: str, params: dict) -> list[dict]:
        """Gibt alle Einträge (match UND include) über alle Seiten zurück, jeweils mit ``search.mode``."""
        url: str | None = f"{self.basis_url}/{typ}"
        parameter: dict | None = {**params, "_count": self.seitengroesse}
        eintraege: list[dict] = []
        for _ in range(MAX_SEITEN):
            bundle = self._get(url, parameter, typ)
            if bundle.get("resourceType") != "Bundle":
                raise KisDatenFehler(f"Das KIS hat auf die Suche ({typ}) kein Bundle geliefert.")
            eintraege += [e for e in bundle.get("entry", []) if "resource" in e]
            weiter = next((l.get("url") for l in bundle.get("link", []) if l.get("relation") == "next"), None)
            if not weiter:
                return eintraege
            # Token nie an fremde Server schicken: Folgeseiten müssen zum selben KIS gehören
            if not weiter.startswith(self.basis_url):
                raise KisDatenFehler("Das KIS verweist auf einen fremden Server; abgebrochen.")
            url, parameter = weiter, None
        raise KisDatenFehler(f"Zu viele Ergebnisseiten ({typ}); abgebrochen.")

    @staticmethod
    def _treffer(eintraege: list[dict]) -> list[dict]:
        return [e["resource"] for e in eintraege if e.get("search", {}).get("mode", "match") == "match"]

    @staticmethod
    def _eingebunden(eintraege: list[dict], typ: str) -> list[dict]:
        return [
            e["resource"]
            for e in eintraege
            if e.get("search", {}).get("mode") == "include" and e["resource"].get("resourceType") == typ
        ]

    # --- Schnittstelle ---------------------------------------------------------------------
    def pruefe_verbindung(self) -> str:
        info = self._get(f"{self.basis_url}/metadata", None, "metadata")
        version = info.get("fhirVersion", "")
        if info.get("resourceType") != "CapabilityStatement" or not version.startswith("4.0"):
            raise KisDatenFehler(f"Das KIS spricht nicht FHIR R4 (gemeldete Version: '{version or 'unbekannt'}').")
        return f"KIS erreichbar (FHIR {version})"

    def liste_faelle(self, seit: date | None = None, nur_laufende: bool = False) -> list[FallUebersicht]:
        filter_: dict = {}
        if seit:
            filter_["date"] = f"ge{seit.isoformat()}"
        if nur_laufende:
            filter_["status"] = "in-progress"

        # Abfrage 1: Einrichtungskontakte samt Patient und Diagnosen (in einem Zug)
        e1 = self._suche(
            "Encounter",
            {
                "type": f"{m.KONTAKTEBENE}|einrichtungskontakt",
                "_include": "Encounter:patient",
                "_revinclude": "Condition:encounter",
                **filter_,
            },
        )
        # Abfrage 2: Abteilungskontakte, um die aktuelle Station zu kennen
        e2 = self._suche("Encounter", {"type": f"{m.KONTAKTEBENE}|abteilungskontakt", **filter_})

        patienten = {p["id"]: p for p in self._eingebunden(e1, "Patient")}
        diagnosen_je_fall: dict[str, list[Diagnose]] = {}
        for cond in self._eingebunden(e1, "Condition"):
            fall_id = m.id_aus_referenz((cond.get("encounter") or {}).get("reference"), "Encounter")
            if fall_id:
                diagnosen_je_fall.setdefault(fall_id, []).append(m.diagnose_aus_fhir(cond))
        abschnitte_je_fall: dict[str, list[dict]] = {}
        for abt in self._treffer(e2):
            fall_id = m.id_aus_referenz((abt.get("partOf") or {}).get("reference"), "Encounter")
            if fall_id:
                abschnitte_je_fall.setdefault(fall_id, []).append(abt)

        zeilen = []
        for enc in self._treffer(e1):
            patient_id = m.id_aus_referenz((enc.get("subject") or {}).get("reference"), "Patient")
            if patient_id not in patienten:
                logger.warning("Ein Fall ohne lesbaren Patienten wurde übersprungen.")
                continue
            patient = m.patient_aus_fhir(patienten[patient_id])
            aufenthalt = m.aufenthalt_aus_fhir(enc, abschnitte_je_fall.get(enc["id"], []))
            verstorben = patient.verstorben
            if verstorben is Verstorben.UNBEKANNT and aufenthalt.entlassen_wegen_tod:
                verstorben = Verstorben.JA
            zeilen.append(
                FallUebersicht(
                    kis_fall_id=enc["id"],
                    patient_name=patient.anzeigename,
                    geburtsdatum=patient.geburtsdatum,
                    aufnahme=aufenthalt.beginn,
                    laufend=aufenthalt.laufend,
                    station=aufenthalt.aktuelle_station,
                    verstorben=verstorben,
                    diagnosen=diagnosen_je_fall.get(enc["id"], []),
                )
            )
        # laufende Fälle zuerst, dann neueste Aufnahme zuerst
        zeilen.sort(key=lambda z: (not z.laufend, -(m.vergleichswert(z.aufnahme).timestamp() if z.aufnahme else 0)))
        logger.info("KIS: %d Fälle geladen", len(zeilen))
        return zeilen

    def lade_fall(self, kis_fall_id: str) -> KisFall:
        enc = self._lese("Encounter", kis_fall_id)
        if not m.ist_einrichtungskontakt(enc):
            raise KisDatenFehler("Die angegebene ID ist kein stationärer Fall (Einrichtungskontakt).")
        patient_id = m.id_aus_referenz((enc.get("subject") or {}).get("reference"), "Patient")
        if not patient_id:
            raise KisDatenFehler("Der Fall im KIS verweist auf keinen lesbaren Patienten.")

        patient = m.patient_aus_fhir(self._lese("Patient", patient_id))
        bezug = f"Encounter/{enc['id']}"
        abschnitte = self._treffer(self._suche("Encounter", {"part-of": bezug}))
        diagnosen = [m.diagnose_aus_fhir(c) for c in self._treffer(self._suche("Condition", {"encounter": bezug}))]
        labor_eintraege = self._suche(
            "DiagnosticReport", {"encounter": bezug, "_include": "DiagnosticReport:result"}
        )
        beobachtungen = {o["id"]: o for o in self._eingebunden(labor_eintraege, "Observation")}
        laborbefunde = [m.laborbefund_aus_fhir(r, beobachtungen) for r in self._treffer(labor_eintraege)]

        aufenthalt = m.aufenthalt_aus_fhir(enc, abschnitte)
        hinweise = _pruefe_vollstaendigkeit(patient, aufenthalt, diagnosen, laborbefunde)
        logger.info("KIS: Fall geladen (%d Diagnosen, %d Laborbefunde)", len(diagnosen), len(laborbefunde))
        return KisFall(patient=patient, aufenthalt=aufenthalt, diagnosen=diagnosen, laborbefunde=laborbefunde, hinweise=hinweise)


def _pruefe_vollstaendigkeit(patient, aufenthalt, diagnosen: list[Diagnose], labor: list[Laborbefund]) -> list[str]:
    """Verständliche Hinweise auf Lücken in den KIS-Daten (ohne Gesundheitsdaten im Text)."""
    hinweise = []
    if not patient.geburtsdatum:
        hinweise.append("Das Geburtsdatum fehlt im KIS.")
    if not patient.adresse or not (patient.adresse.zeilen and patient.adresse.plz and patient.adresse.ort):
        hinweise.append("Die Wohnanschrift ist im KIS unvollständig oder fehlt.")
    if not patient.telefon and not patient.email:
        hinweise.append("Es ist keine Telefonnummer und keine E-Mail-Adresse im KIS hinterlegt.")
    if not diagnosen:
        hinweise.append("Zu diesem Fall ist im KIS keine Diagnose hinterlegt.")
    elif any(d.icd_code is None for d in diagnosen):
        hinweise.append("Mindestens eine Diagnose hat im KIS keinen ICD-10-GM-Code (nur Freitext).")
    if not aufenthalt.abschnitte:
        hinweise.append("Zum Aufenthalt sind keine Stationen/Fachabteilungen hinterlegt.")
    if not labor:
        hinweise.append("Im KIS wurden keine Laborbefunde gefunden (Laboranbindung evtl. nicht vorhanden).")
    if aufenthalt.entlassen_wegen_tod and patient.verstorben is Verstorben.UNBEKANNT:
        hinweise.append("Der Aufenthalt endete wegen Tod, aber am Patienten fehlt die Todesangabe.")
    if patient.verstorben is Verstorben.JA and aufenthalt.laufend:
        hinweise.append("Der Patient ist als verstorben vermerkt, der Aufenthalt gilt aber als laufend.")
    return hinweise
