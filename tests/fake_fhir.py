"""Ein kleiner FHIR-Testserver im Arbeitsspeicher (für Tests ohne Docker).

Er beherrscht genau die Abfragen, die der KIS-Adapter braucht, und liefert die synthetischen
Testdaten aus ``meldeassistent.testdaten``. Damit laufen dieselben Tests gegen ihn und gegen das
echte Schein-KIS (HAPI); weichen die Ergebnisse ab, ist einer der beiden falsch.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from meldeassistent.testdaten.faelle import alle_faelle, stammdaten

BASIS = "http://fake-kis.test/fhir"


def alle_testressourcen() -> list[dict]:
    ressourcen = list(stammdaten())
    for fall in alle_faelle():
        ressourcen += fall.ressourcen()
    return ressourcen


class FakeFhirServer:
    def __init__(self, ressourcen: list[dict] | None = None, fremder_next_link: bool = False):
        self.ressourcen = ressourcen if ressourcen is not None else alle_testressourcen()
        self.fremder_next_link = fremder_next_link
        self.anfragen: list[httpx.Request] = []

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.antworte), base_url=BASIS)

    # --- Hilfen ----------------------------------------------------------------------------
    def _typ(self, typ: str) -> list[dict]:
        return [r for r in self.ressourcen if r["resourceType"] == typ]

    def _lies(self, typ: str, id_: str) -> dict | None:
        return next((r for r in self._typ(typ) if r["id"] == id_), None)

    @staticmethod
    def _bundle(eintraege: list[dict], gesamt: int, naechste: str | None = None) -> httpx.Response:
        bundle = {"resourceType": "Bundle", "type": "searchset", "total": gesamt, "entry": eintraege}
        if naechste:
            bundle["link"] = [{"relation": "next", "url": naechste}]
        return httpx.Response(200, json=bundle)

    # --- Suche -----------------------------------------------------------------------------
    def _encounter_treffer(self, p: httpx.QueryParams) -> list[dict]:
        treffer = self._typ("Encounter")
        if "type" in p:
            system, _, code = p["type"].partition("|")
            treffer = [
                e for e in treffer
                if any(c.get("system") == system and c.get("code") == code for t in e.get("type", []) for c in t["coding"])
            ]
        if "status" in p:
            treffer = [e for e in treffer if e["status"] == p["status"]]
        if "date" in p:
            ab = p["date"].removeprefix("ge")
            treffer = [e for e in treffer if "end" not in e["period"] or e["period"]["end"][:10] >= ab]
        if "part-of" in p:
            treffer = [e for e in treffer if e.get("partOf", {}).get("reference") == p["part-of"]]
        return sorted(treffer, key=lambda e: e["id"])

    def _suche(self, typ: str, request: httpx.Request) -> httpx.Response:
        p = request.url.params
        if typ == "Encounter":
            treffer = self._encounter_treffer(p)
        elif typ == "Condition":
            treffer = [c for c in self._typ("Condition") if c["encounter"]["reference"] == p["encounter"]]
        elif typ == "DiagnosticReport":
            treffer = [r for r in self._typ("DiagnosticReport") if r["encounter"]["reference"] == p["encounter"]]
        else:
            return httpx.Response(400, json={"resourceType": "OperationOutcome"})

        seite = int(p.get("_count", 100))
        start = int(p.get("_offset", 0))
        auszug = treffer[start : start + seite]
        eintraege = [{"resource": r, "search": {"mode": "match"}} for r in auszug]
        # _include / _revinclude für die Treffer dieser Seite
        zusatz: list[dict] = []
        if p.get("_include") == "Encounter:patient":
            ids = {e["subject"]["reference"].split("/")[1] for e in auszug}
            zusatz += [self._lies("Patient", i) for i in sorted(ids)]
        if p.get("_revinclude") == "Condition:encounter":
            refs = {f"Encounter/{e['id']}" for e in auszug}
            zusatz += [c for c in self._typ("Condition") if c["encounter"]["reference"] in refs]
        if p.get("_include") == "DiagnosticReport:result":
            for r in auszug:
                zusatz += [self._lies("Observation", x["reference"].split("/")[1]) for x in r.get("result", [])]
        eintraege += [{"resource": z, "search": {"mode": "include"}} for z in zusatz]

        naechste = None
        if start + seite < len(treffer):
            neue = [(k, v) for k, v in p.multi_items() if k != "_offset"] + [("_offset", str(start + seite))]
            host = "http://anderer-server.test/fhir" if self.fremder_next_link else BASIS
            naechste = f"{host}/{typ}?{urlencode(neue)}"
        return self._bundle(eintraege, len(treffer), naechste)

    # --- Verteiler -------------------------------------------------------------------------
    def antworte(self, request: httpx.Request) -> httpx.Response:
        self.anfragen.append(request)
        pfad = request.url.path.removeprefix("/fhir/").strip("/")
        if pfad == "metadata":
            return httpx.Response(200, json={"resourceType": "CapabilityStatement", "fhirVersion": "4.0.1"})
        teile = pfad.split("/")
        if len(teile) == 1:
            return self._suche(teile[0], request)
        if len(teile) == 2:
            ressource = self._lies(*teile)
            return httpx.Response(200, json=ressource) if ressource else httpx.Response(404, json={})
        return httpx.Response(404, json={})
