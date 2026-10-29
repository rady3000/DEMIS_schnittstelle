// Misst einen vollständigen Durchlauf (Arbeitsliste -> Meldebogen -> Vorschau -> Freigabe) im echten Browser.
//
// Aufruf:  NODE_PATH=$(npm root -g) node tools/zeitmessung.js [http://localhost:8000]
// Voraussetzung: Anwendung und Schein-KIS laufen (siehe docker-compose.yml, python -m meldeassistent.web).
//
// Ausgewiesen werden je Fall (a) die Anzahl der Eingaben (Klicks/Auswahlen/Texteingaben), (b) die reine
// Wartezeit des Systems (Antwortzeiten nach jeder Eingabe, Seitenwechsel), (c) die Maschinenzeit des
// Skripts und (d) eine Schätzung der Bearbeitungszeit für einen Menschen. Die Schätzung nimmt SEKUNDEN_JE_EINGABE
// für Lesen, Zielen und Klicken an; sie ersetzt keine Messung mit einer echten Ärztin/einem echten Arzt.
const { chromium } = require('playwright');
const BASIS = process.argv[2] || 'http://localhost:8000';
const SEKUNDEN_JE_EINGABE = 4;

const STANDARD = { 'a.isDead': 'no', 'a.militaryAffiliation': 'noReferenceToBundeswehr', 'a.infectProtectFacility': 'no', 'a.placeExposure': 'no', 'a.organDonation': 'no' };
const FAELLE = [
  { name: 'Testpatient, Anna', titel: 'C. difficile (Fall 1)', felder: { ...STANDARD, 's.immunization': 'no', 's.method': '117963005:{363701004=39477002}', 's.outbreak': 'no' }, bestaetigen: ['spezifisch.form'] },
  { name: 'Testpatient, Ingrid', titel: 'C. difficile verstorben (Fall 7)', felder: { ...STANDARD, 'a.isDead': undefined, 's.immunization': 'no', 's.method': '117963005:{363701004=39477002}', 's.outbreak': 'no' }, bestaetigen: ['spezifisch.form'] },
  { name: 'Testpatient, Boris', titel: 'Tuberkulose (Fall 2)', felder: { ...STANDARD, 's.immunization': 'ASKU', 's.infectionEnvironmentSettingKind': 'ASKU', 's.nationality': 'DE', 's.countryOfBirth': 'DE', 's.childrenUnder15Years': 'no', 's.causeDiagnosis': '41769001:{246090004=404684003}', 's.statusDiagnosis': 'yes', 's.treatment': 'yes', 's.treatmentBegin': '21.10.2026', 's.resultOfTreatment': 'ASKU', 's.majorSite': '154283005', 's.minorSite': '260413007', 's.prevTreatment': 'no', 's.outbreak': 'no', 'a.labSpecimenTaken': 'yes' }, bestaetigen: [] },
  { name: 'Testpatient, Clara', titel: 'Masern-Verdacht (Fall 3)', felder: { ...STANDARD, 'a.labSpecimenTaken': 'no', 's.immunization': 'ASKU', 's.pregnancy': 'no', 's.outbreak': 'no', 's.onsetOfExanthem': '25.10.2026' }, symptome: ['386661006', '49727002'], bestaetigen: [] },
];

(async () => {
  const browser = await chromium.launch();
  const ergebnisse = [];
  for (const fall of FAELLE) {
    const seite = await (await browser.newContext({ viewport: { width: 1400, height: 1000 } })).newPage();
    await seite.goto(BASIS + '/anmelden');
    await seite.fill('#benutzer', 'testarzt'); await seite.fill('#passwort', 'test');
    await Promise.all([seite.waitForURL(BASIS + '/'), seite.click('button[type=submit]')]);

    let eingaben = 0, systemMs = 0;
    const warte = async (aktion) => { const t = Date.now(); await aktion(); systemMs += Date.now() - t; };
    const nachHtmx = async (aktion, was = '') => {  eingaben++; const t = Date.now(); await Promise.all([seite.waitForResponse(r => r.url().includes('/fall/') && r.request().method() === 'POST'), aktion()]); await seite.waitForFunction(() => !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')); await seite.waitForTimeout(60); systemMs += Date.now() - t; };
    const start = Date.now();

    const zeile = seite.locator('tr', { hasText: fall.name });
    eingaben++; await warte(async () => { await Promise.all([seite.waitForURL(/\/fall\//), zeile.getByRole("link", { name: /(Meldung|Weiter) bearbeiten/ }).click()]); });
    await seite.waitForSelector('#bogenform');

    for (const [name, wert] of Object.entries(fall.felder)) {
      if (wert === undefined) continue;
      const radio = seite.locator(`input[type=radio][name="${name}"][value="${wert}"]`);
      if (await radio.count()) { if (await radio.isChecked()) continue; /* schon aus dem KIS richtig vorbelegt: keine Eingabe nötig */ await nachHtmx(() => radio.check(), name); continue; }
      const auswahl = seite.locator(`select[name="${name}"]`);
      if (await auswahl.count()) { await nachHtmx(() => auswahl.selectOption(wert), name); continue; }
      const text = seite.locator(`input[name="${name}"]`);
      if (await text.count()) { await text.fill(wert); await nachHtmx(() => text.press('Tab'), name); continue; }
      throw new Error(`Feld ${name} nicht gefunden (${fall.titel})`);
    }
    for (const code of fall.symptome || []) await nachHtmx(() => seite.locator(`input[name="symptom"][value="${code}"]`).check());
    for (const schluessel of fall.bestaetigen) await nachHtmx(() => seite.locator(`button[hx-post$="/bestaetigen/${schluessel}"]`).click());

    const offen = await seite.locator('.liste-offen li').allInnerTexts();
    if (offen.length) throw new Error(`${fall.titel}: noch offen: ${offen.join(' | ')}`);
    eingaben++; await warte(async () => { await Promise.all([seite.waitForURL(/vorschau/), seite.getByRole('link', { name: 'Weiter zur Vorschau' }).click()]); });
    await seite.waitForSelector('text=ohne Fehler akzeptiert');
    eingaben++; await warte(async () => { await Promise.all([seite.waitForSelector('text=Meldung freigegeben'), seite.getByRole('button', { name: 'Freigeben' }).click()]); });
    const maschinenSek = (Date.now() - start) / 1000;
    ergebnisse.push({ fall: fall.titel, eingaben, systemSek: +(systemMs / 1000).toFixed(1), maschinenSek: +maschinenSek.toFixed(1), schaetzungSek: Math.round(eingaben * SEKUNDEN_JE_EINGABE + systemMs / 1000), spielraum: +((120 - systemMs / 1000) / eingaben).toFixed(1) });
    await seite.context().close();
  }
  await browser.close();
  console.log('\nFall                                 Eingaben  Systemwartezeit  Skriptzeit  Schätzung Mensch  Zeit je Eingabe für 2:00 min');
  for (const e of ergebnisse) console.log(`${e.fall.padEnd(36)} ${String(e.eingaben).padStart(8)}  ${String(e.systemSek + ' s').padStart(15)}  ${String(e.maschinenSek + ' s').padStart(10)}  ${String(Math.floor(e.schaetzungSek / 60) + ':' + String(e.schaetzungSek % 60).padStart(2, '0') + ' min').padStart(16)}  ${String(e.spielraum + ' s').padStart(12)}`);
  console.log(`\nAnnahme: ${SEKUNDEN_JE_EINGABE} s je Eingabe (Lesen, Zielen, Klicken). Ziel: unter 2:00 min.`);
})().catch(e => { console.error('FEHLER:', e.message); process.exit(1); });
