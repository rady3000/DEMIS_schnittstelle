"""Anzeigeformate für die Oberfläche: deutsche Datumsangaben, Texte der Antwortmöglichkeiten, Alter."""

from __future__ import annotations

import gettext
import re
from datetime import date, datetime

import pycountry

from meldeassistent.demis.pakete import Konzept

NULLFLAVOR = "http://terminology.hl7.org/CodeSystem/v3-NullFlavor"
ISO_LAENDER = "urn:iso:std:iso:3166"

try:
    _LAENDER = gettext.translation("iso3166-1", pycountry.LOCALES_DIR, languages=["de"])
except OSError:  # Übersetzungen fehlen: englische Namen genügen
    _LAENDER = None


def datum_de(iso: str | date | datetime | None) -> str:
    """'2026-10-12' -> '12.10.2026', '2026-10' -> '10.2026', '2026' -> '2026'. Leer bleibt leer."""
    if iso is None or iso == "":
        return ""
    if isinstance(iso, (date, datetime)):
        return iso.strftime("%d.%m.%Y")
    teile = str(iso)[:10].split("-")
    return ".".join(reversed(teile))


_EINGABE = re.compile(r"^\s*(?:(?:(\d{1,2})\.)?(\d{1,2})\.)?(\d{4})\s*$")
_ISO = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")


def datum_aus_eingabe(text: str) -> str | None:
    """'22.10.2026' | '10.2026' | '2026' | '2026-10-22' -> ISO-Datum (gleiche Genauigkeit). Ungültig -> None."""
    text = (text or "").strip()
    if m := _ISO.match(text):
        jahr, monat, tag = m.groups()
    elif m := _EINGABE.match(text):
        tag, monat, jahr = m.groups()
    else:
        return None
    if not 1900 <= int(jahr) <= 2100:  # Tippfehler wie 0026 oder 20266 abfangen
        return None
    try:
        if tag:
            date(int(jahr), int(monat), int(tag))
        elif monat:
            date(int(jahr), int(monat), 1)
    except ValueError:
        return None
    return "-".join(x if len(x) == 4 else x.zfill(2) for x in (jahr, monat, tag) if x)


def option_text(k: Konzept) -> str:
    """Verständlicher deutscher Text einer Antwortmöglichkeit."""
    if k.system == NULLFLAVOR:
        return {"ASKU": "nicht ermittelbar", "NASK": "noch nicht beantwortet"}.get(k.code, k.display or k.code)
    if k.system == ISO_LAENDER and _LAENDER:
        land = pycountry.countries.get(alpha_2=k.code)  # über den Code, denn die englischen Texte weichen ab
        if land:
            return _LAENDER.gettext(land.name)
    return k.display or k.code


def ist_ja_nein(optionen: tuple[Konzept, ...]) -> bool:
    return {k.code for k in optionen} == {"yes", "no", "NASK", "ASKU"}


def alter_jahre(geburtsdatum: date | None, stichtag: date) -> int | None:
    if not geburtsdatum:
        return None
    return stichtag.year - geburtsdatum.year - ((stichtag.month, stichtag.day) < (geburtsdatum.month, geburtsdatum.day))
