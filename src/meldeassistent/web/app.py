"""Die Web-Anwendung (FastAPI + Jinja2 + HTMX), serverseitig gerendert.

Sicherheit (siehe PLAN.md / DATENSCHUTZ.md):
- Anmeldung mit serverseitiger Sitzung (Cookie enthält nur eine zufällige ID, HttpOnly, SameSite=Strict).
  Zeitüberschreitung bei Inaktivität, Sperre nach mehreren Fehlversuchen. Später LDAP/AD statt Test-Anmeldung.
- CSRF-Schutz auf allen ändernden Anfragen, strikte Content-Security-Policy, keine externen Ressourcen.
- Fälle werden in Adressen nur über zufällige Kennungen angesprochen (nie KIS-IDs): Zugriffsprotokolle des
  Servers enthalten damit keine Patientenbezüge.
- Entwürfe nur im Arbeitsspeicher; nach Freigabe/Verwerfen/Zeitablauf gelöscht (Regel 5).
- Der Versand an DEMIS ist in dieser Phase NICHT angeschlossen (Regel 6): "Freigeben" speichert nur den Audit-Eintrag.
"""

from __future__ import annotations

import hmac
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from meldeassistent.audit import Audit
from meldeassistent.demis.angaben import Melder, MelderKonfig
from meldeassistent.demis.mapper import MeldungNichtMoeglich, erzeuge_meldung
from meldeassistent.demis.meldung import pruefe_meldung
from meldeassistent.demis.pakete import DemisPakete
from meldeassistent.demis.validator import FhirValidator, ValidatorFehler
from meldeassistent.kis.schnittstelle import KisAdapter, KisFehler
from meldeassistent.regelwerk import Bewertung, Meldeweg, bewerte

from . import anzeige
from .entwurf import (
    AUTOMATISCH,
    NICHT_UNTERSTUETZT_JA,
    Entwurf,
    bestaetige,
    bewerte_entwurf,
    neuer_entwurf,
    wende_formular_an,
)
from .vorschau import vorschau_aus_bundle

HIER = Path(__file__).resolve().parent
logger = logging.getLogger("meldeassistent.web")
ZEITUNG = re.compile(r"^(allgemein|spezifisch)\.[A-Za-z0-9]+$")
WEG_NAMEN = {
    Meldeweg.DEMIS: "DEMIS",
    Meldeweg.SACHSEN: "Landesmeldung Sachsen",
    Meldeweg.KLAERUNG: "Klärung nötig",
    Meldeweg.KEINER: "nicht meldepflichtig",
}


@dataclass
class Einstellungen:
    benutzer: dict[str, str]  # Anmeldename -> Passwort (NUR Testbetrieb; später LDAP/AD)
    melder: Melder
    konfig: MelderKonfig
    testbetrieb: bool = True
    cookie_sicher: bool = False  # True, sobald die Anwendung über HTTPS ausgeliefert wird
    leerlauf_s: int = 1800
    max_versuche: int = 5
    sperre_s: int = 300
    liste_tage: int = 30


@dataclass
class FallRef:
    kis_fall_id: str
    bewertung: Bewertung


@dataclass
class Sitzung:
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    benutzer: str | None = None
    faelle: dict[str, FallRef] = field(default_factory=dict)  # Kennung -> Fall
    kennung_je_fall: dict[str, str] = field(default_factory=dict)  # KIS-Fall -> Kennung (stabil während der Sitzung)
    zuletzt: float = field(default_factory=time.monotonic)


class Zustand:
    def __init__(self, kis: KisAdapter, validator: FhirValidator | None, pakete: DemisPakete, audit: Audit, einstellungen: Einstellungen, uhr: Callable[[], datetime]):
        self.kis, self.validator, self.pakete, self.audit, self.e, self.uhr = kis, validator, pakete, audit, einstellungen, uhr
        self.sitzungen: dict[str, Sitzung] = {}
        self.entwuerfe: dict[tuple[str, str], Entwurf] = {}  # (Benutzer, KIS-Fall) -> Entwurf
        self.fehlversuche: dict[str, list[float]] = {}

    def aufraeumen(self) -> None:
        jetzt = time.monotonic()
        for sid in [s for s, v in self.sitzungen.items() if jetzt - v.zuletzt > self.e.leerlauf_s]:
            del self.sitzungen[sid]
        for k in [k for k, v in self.entwuerfe.items() if jetzt - v.zuletzt > self.e.leerlauf_s]:
            del self.entwuerfe[k]


def erzeuge_app(
    kis: KisAdapter,
    validator: FhirValidator | None,
    pakete: DemisPakete,
    audit: Audit,
    einstellungen: Einstellungen,
    uhr: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> FastAPI:
    zustand = Zustand(kis, validator, pakete, audit, einstellungen, uhr)
    app = FastAPI(title="DEMIS-Meldeassistent", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.zustand = zustand
    vorlagen = Jinja2Templates(directory=str(HIER / "templates"))
    vorlagen.env.filters["datum"] = anzeige.datum_de
    vorlagen.env.globals.update(option_text=anzeige.option_text, ist_ja_nein=anzeige.ist_ja_nein, WEG_NAMEN=WEG_NAMEN, Meldeweg=Meldeweg)
    app.mount("/static", StaticFiles(directory=str(HIER / "static")), name="static")

    # ---- Sitzung -------------------------------------------------------------------------------
    def hole_sitzung(request: Request) -> tuple[str, Sitzung]:
        zustand.aufraeumen()
        sid = request.cookies.get("sid")
        if sid and sid in zustand.sitzungen:
            s = zustand.sitzungen[sid]
            s.zuletzt = time.monotonic()
            return sid, s
        sid = secrets.token_urlsafe(32)
        zustand.sitzungen[sid] = Sitzung()
        return sid, zustand.sitzungen[sid]

    def setze_cookie(antwort: Response, sid: str) -> Response:
        antwort.set_cookie("sid", sid, httponly=True, samesite="strict", secure=einstellungen.cookie_sicher, max_age=None, path="/")
        return antwort

    def csrf_pruefen(sitzung: Sitzung, request: Request, formularwert: str | None) -> bool:
        gegeben = request.headers.get("x-csrf-token") or formularwert or ""
        return hmac.compare_digest(gegeben, sitzung.csrf)

    def seite(request: Request, name: str, sitzung: Sitzung, sid: str, status: int = 200, **kontext) -> Response:
        antwort = vorlagen.TemplateResponse(
            request, name, {"csrf": sitzung.csrf, "benutzer": sitzung.benutzer, "testbetrieb": einstellungen.testbetrieb, **kontext}, status_code=status
        )
        return setze_cookie(antwort, sid)

    def weiterleitung(request: Request, ziel: str, sid: str) -> Response:
        if request.headers.get("hx-request"):  # HTMX: ganze Seite wechseln
            antwort: Response = Response(status_code=204, headers={"HX-Redirect": ziel})
        else:
            antwort = RedirectResponse(ziel, status_code=303)
        return setze_cookie(antwort, sid)

    def geschuetzt(request: Request):
        sid, sitzung = hole_sitzung(request)
        if sitzung.benutzer is None:
            return sid, sitzung, weiterleitung(request, "/anmelden", sid)
        return sid, sitzung, None

    def fall_laden(sitzung: Sitzung, token: str):
        ref = sitzung.faelle.get(token)
        if ref is None:
            return None, None, None
        fall = zustand.kis.lade_fall(ref.kis_fall_id)
        return ref, fall, zustand.entwuerfe.get((sitzung.benutzer, ref.kis_fall_id))

    def fehlerseite(request, sitzung, sid, text: str, status: int = 500):
        return seite(request, "fehler.html", sitzung, sid, status, text=text)

    # ---- Sicherheits-Header und Protokoll --------------------------------------------------------
    @app.middleware("http")
    async def sicherheit(request: Request, call_next):
        start = time.monotonic()
        antwort = await call_next(request)
        antwort.headers["Cache-Control"] = "no-store"
        antwort.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        antwort.headers["X-Content-Type-Options"] = "nosniff"
        antwort.headers["Referrer-Policy"] = "no-referrer"
        antwort.headers["X-Frame-Options"] = "DENY"
        route = request.scope.get("route")
        # Muster statt echter Adresse: keine Fall-Kennungen im Protokoll
        logger.info("%s %s -> %s (%d ms)", request.method, getattr(route, "path", "?"), antwort.status_code, (time.monotonic() - start) * 1000)
        return antwort

    # ---- Anmeldung -------------------------------------------------------------------------------
    @app.get("/anmelden", response_class=HTMLResponse)
    def anmelden_seite(request: Request):
        sid, sitzung = hole_sitzung(request)
        if sitzung.benutzer:
            return weiterleitung(request, "/", sid)
        return seite(request, "anmelden.html", sitzung, sid, fehler=None)

    @app.post("/anmelden")
    def anmelden(request: Request, benutzer: str = Form(""), passwort: str = Form(""), csrf: str = Form("")):
        sid, sitzung = hole_sitzung(request)
        if not csrf_pruefen(sitzung, request, csrf):
            return seite(request, "anmelden.html", sitzung, sid, 403, fehler="Die Sitzung ist abgelaufen. Bitte erneut versuchen.")
        jetzt = time.monotonic()
        versuche = [t for t in zustand.fehlversuche.get(benutzer, []) if jetzt - t < einstellungen.sperre_s]
        if len(versuche) >= einstellungen.max_versuche:
            return seite(request, "anmelden.html", sitzung, sid, 429, fehler="Zu viele Fehlversuche. Bitte in einigen Minuten erneut versuchen.")
        erwartet = einstellungen.benutzer.get(benutzer)
        # immer vergleichen (auch bei unbekanntem Benutzer), damit die Antwortzeit nichts verrät
        ok = hmac.compare_digest(passwort.encode(), (erwartet or secrets.token_urlsafe(8)).encode()) and erwartet is not None
        if not ok:
            zustand.fehlversuche[benutzer] = versuche + [jetzt]
            zustand.audit.schreibe("-", benutzer[:40], "-", "anmeldung_fehlgeschlagen", zustand.uhr())
            return seite(request, "anmelden.html", sitzung, sid, 401, fehler="Benutzername oder Passwort stimmt nicht.")
        zustand.fehlversuche.pop(benutzer, None)
        del zustand.sitzungen[sid]  # neue Sitzungs-ID nach der Anmeldung (verhindert Session-Fixation)
        neue_sid = secrets.token_urlsafe(32)
        zustand.sitzungen[neue_sid] = Sitzung(benutzer=benutzer)
        zustand.audit.schreibe("-", benutzer, "-", "angemeldet", zustand.uhr())
        return weiterleitung(request, "/", neue_sid)

    @app.post("/abmelden")
    def abmelden(request: Request, csrf: str = Form("")):
        sid, sitzung = hole_sitzung(request)
        if not csrf_pruefen(sitzung, request, csrf):
            return Response(status_code=403)
        zustand.sitzungen.pop(sid, None)
        return weiterleitung(request, "/anmelden", secrets.token_urlsafe(8))

    # ---- Arbeitsliste ----------------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def arbeitsliste(request: Request, alle: int = 0):
        sid, sitzung, umleitung = geschuetzt(request)
        if umleitung:
            return umleitung
        try:
            uebersicht = zustand.kis.liste_faelle(seit=zustand.uhr().date() - timedelta(days=einstellungen.liste_tage))
        except KisFehler as fehler:
            return fehlerseite(request, sitzung, sid, str(fehler), 502)
        zeilen = []
        for z in uebersicht:
            b = bewerte(z, uebersicht)
            # Zufällige, nicht aus der KIS-ID ableitbare Kennung; bleibt in der Sitzung gleich, damit offene Meldebögen
            # gültig bleiben, wenn die Liste in einem zweiten Tab neu geladen wird
            token = sitzung.kennung_je_fall.setdefault(z.kis_fall_id, secrets.token_urlsafe(9))
            sitzung.faelle[token] = FallRef(z.kis_fall_id, b)
            if b.meldepflichtig or alle:
                zeilen.append({"z": z, "b": b, "token": token, "entwurf": (sitzung.benutzer, z.kis_fall_id) in zustand.entwuerfe})
        # meldepflichtige zuerst, dann laufende, dann neueste Aufnahme
        zeilen.sort(key=lambda r: (not r["b"].meldepflichtig, not r["z"].laufend, -(r["z"].aufnahme.timestamp() if r["z"].aufnahme else 0)))
        return seite(
            request, "liste.html", sitzung, sid, zeilen=zeilen, alle=bool(alle), heute=zustand.uhr().date(),
            anzahl_nicht=sum(1 for z in uebersicht if not bewerte(z, uebersicht).meldepflichtig), alter=anzeige.alter_jahre,
        )

    # ---- Meldebogen ------------------------------------------------------------------------------
    def bogen_kontext(sitzung: Sitzung, token: str, ref: FallRef, fall, entwurf: Entwurf, nur_fragment: bool = False) -> dict:
        stand = bewerte_entwurf(entwurf, fall, einstellungen.melder, einstellungen.konfig, pakete, zustand.uhr())
        feld_status = {}
        for o in stand.fehler:
            feld_status[o.feld] = "fehler"
        for o in stand.offen:
            feld_status.setdefault(o.feld, "offen")
        a = entwurf.angaben
        impf_optionen = ()
        if a.kuerzel:
            impf_optionen = tuple(k for k in (pakete.wertemenge(f"https://demis.rki.de/fhir/ValueSet/vaccine{a.kuerzel}").konzepte or ()) if k.code not in ("NASK", "ASKU"))
        symptom_optionen = tuple(pakete.wertemenge("https://demis.rki.de/fhir/ValueSet/evidenceMSVD").konzepte or ()) if a.kuerzel == "MSVD" else ()
        return dict(
            token=token, ref=ref, fall=fall, entwurf=entwurf, a=a, stand=stand, feld_status=feld_status,
            herkunft=a.herkunft, AUTOMATISCH=AUTOMATISCH, NICHT_UNTERSTUETZT_JA=NICHT_UNTERSTUETZT_JA,
            impf_optionen=impf_optionen, symptom_optionen=symptom_optionen, alter=anzeige.alter_jahre, heute=zustand.uhr().date(),
        )

    @app.get("/fall/{token}", response_class=HTMLResponse)
    def meldebogen(request: Request, token: str):
        sid, sitzung, umleitung = geschuetzt(request)
        if umleitung:
            return umleitung
        try:
            ref, fall, entwurf = fall_laden(sitzung, token)
        except KisFehler as fehler:
            return fehlerseite(request, sitzung, sid, str(fehler), 502)
        if ref is None:
            return weiterleitung(request, "/", sid)
        if ref.bewertung.weg is not Meldeweg.DEMIS:
            return seite(request, "kein_demis.html", sitzung, sid, token=token, ref=ref, fall=fall, alter=anzeige.alter_jahre, heute=zustand.uhr().date())
        if entwurf is None:
            entwurf = neuer_entwurf(fall, ref.bewertung.kuerzel, einstellungen.konfig, ref.kis_fall_id)
            zustand.entwuerfe[(sitzung.benutzer, ref.kis_fall_id)] = entwurf
            zustand.audit.schreibe(entwurf.vorgang, sitzung.benutzer, "demis", "geoeffnet", zustand.uhr())
        return seite(request, "bogen.html", sitzung, sid, **bogen_kontext(sitzung, token, ref, fall, entwurf))

    @app.post("/fall/{token}/bogen", response_class=HTMLResponse)
    async def bogen_aktualisieren(request: Request, token: str):
        sid, sitzung, umleitung = geschuetzt(request)
        if umleitung:
            return umleitung
        formular = await request.form()
        if not csrf_pruefen(sitzung, request, formular.get("csrf")):
            return Response(status_code=403)
        try:
            ref, fall, entwurf = fall_laden(sitzung, token)
        except KisFehler as fehler:
            return fehlerseite(request, sitzung, sid, str(fehler), 502)
        if ref is None or entwurf is None:
            return weiterleitung(request, "/", sid)
        daten: dict[str, list[str]] = {}
        for schluessel in formular.keys():
            daten[schluessel] = [str(w) for w in formular.getlist(schluessel)]
        wende_formular_an(entwurf, daten, pakete)
        return seite(request, "_bogen.html", sitzung, sid, **bogen_kontext(sitzung, token, ref, fall, entwurf))

    @app.post("/fall/{token}/bestaetigen/{schluessel}", response_class=HTMLResponse)
    async def vorschlag_bestaetigen(request: Request, token: str, schluessel: str):
        sid, sitzung, umleitung = geschuetzt(request)
        if umleitung:
            return umleitung
        formular = await request.form()
        if not csrf_pruefen(sitzung, request, formular.get("csrf")) or not ZEITUNG.match(schluessel):
            return Response(status_code=403)
        try:
            ref, fall, entwurf = fall_laden(sitzung, token)
        except KisFehler as fehler:
            return fehlerseite(request, sitzung, sid, str(fehler), 502)
        if ref is None or entwurf is None:
            return weiterleitung(request, "/", sid)
        bestaetige(entwurf, schluessel)
        return seite(request, "_bogen.html", sitzung, sid, **bogen_kontext(sitzung, token, ref, fall, entwurf))

    # ---- Vorschau, Freigabe, Verwerfen -----------------------------------------------------------
    def volle_pruefung(fall, entwurf: Entwurf, sitzung: Sitzung):
        stand = bewerte_entwurf(entwurf, fall, einstellungen.melder, einstellungen.konfig, pakete, zustand.uhr())
        if not stand.bereit:
            return stand, None, None
        if zustand.validator is None:
            raise ValidatorFehler("Der Meldungsprüfer ist nicht eingerichtet. Bitte die IT informieren.")
        return stand, pruefe_meldung(stand.bundle, zustand.validator, pakete, streng=True), stand.bundle

    @app.get("/fall/{token}/vorschau", response_class=HTMLResponse)
    def vorschau(request: Request, token: str):
        sid, sitzung, umleitung = geschuetzt(request)
        if umleitung:
            return umleitung
        try:
            ref, fall, entwurf = fall_laden(sitzung, token)
            if ref is None or entwurf is None:
                return weiterleitung(request, "/", sid)
            stand, ergebnis, bundle = volle_pruefung(fall, entwurf, sitzung)
        except KisFehler as fehler:
            return fehlerseite(request, sitzung, sid, str(fehler), 502)
        except ValidatorFehler as fehler:
            return fehlerseite(request, sitzung, sid, str(fehler), 503)
        if ergebnis is None:
            return weiterleitung(request, f"/fall/{token}", sid)
        abschnitte = vorschau_aus_bundle(bundle, pakete) if ergebnis.ok else {}
        return seite(request, "vorschau.html", sitzung, sid, token=token, ref=ref, ergebnis=ergebnis, abschnitte=abschnitte, entwurf=entwurf)

    @app.post("/fall/{token}/freigeben", response_class=HTMLResponse)
    def freigeben(request: Request, token: str, csrf: str = Form("")):
        sid, sitzung, umleitung = geschuetzt(request)
        if umleitung:
            return umleitung
        if not csrf_pruefen(sitzung, request, csrf):
            return Response(status_code=403)
        try:
            ref, fall, entwurf = fall_laden(sitzung, token)
            if ref is None or entwurf is None:
                return weiterleitung(request, "/", sid)
            stand, ergebnis, _ = volle_pruefung(fall, entwurf, sitzung)
        except KisFehler as fehler:
            return fehlerseite(request, sitzung, sid, str(fehler), 502)
        except ValidatorFehler as fehler:
            return fehlerseite(request, sitzung, sid, str(fehler), 503)
        if ergebnis is None or not ergebnis.vollstaendig:
            return weiterleitung(request, f"/fall/{token}", sid)
        dauer = entwurf.dauer_s()
        # Phase 4: kein Versand. Der Versand an DEMIS folgt in Phase 5 (erst nach Rückfrage, Regel 6).
        zustand.audit.schreibe(entwurf.vorgang, sitzung.benutzer, "demis", "freigegeben_ohne_versand", zustand.uhr(), dauer)
        del zustand.entwuerfe[(sitzung.benutzer, ref.kis_fall_id)]
        return seite(request, "fertig.html", sitzung, sid, dauer=dauer, vorgang=entwurf.vorgang)

    @app.post("/fall/{token}/verwerfen")
    def verwerfen(request: Request, token: str, csrf: str = Form("")):
        sid, sitzung, umleitung = geschuetzt(request)
        if umleitung:
            return umleitung
        if not csrf_pruefen(sitzung, request, csrf):
            return Response(status_code=403)
        ref = sitzung.faelle.get(token)
        if ref:
            e = zustand.entwuerfe.pop((sitzung.benutzer, ref.kis_fall_id), None)
            if e:
                zustand.audit.schreibe(e.vorgang, sitzung.benutzer, "demis", "verworfen", zustand.uhr(), e.dauer_s())
        return weiterleitung(request, "/", sid)

    # ---- Betriebsprüfung für die IT (keine Patientendaten) ---------------------------------------
    @app.get("/gesundheit")
    def gesundheit():
        try:
            kis = zustand.kis.pruefe_verbindung()
        except KisFehler as fehler:
            kis = f"FEHLER: {fehler}"
        pruefer = "nicht eingerichtet" if zustand.validator is None else ("bereit" if zustand.validator.ist_bereit() else "FEHLER: nicht erreichbar")
        return JSONResponse({"kis": kis, "validator": pruefer, "testbetrieb": einstellungen.testbetrieb})

    return app
