# Transkribering och anonymisering

> **Instruktion till Claude Code:** Detta dokument är en komplett plan och kravspecifikation.
> Sätt upp ett nytt repo med namnet `transkribering-och-anonymisering` och bygg
> webbapplikationen enligt planen nedan, etapp för etapp (se avsnitt 9).
> Applikationens visningsnamn är **"Transkribering och anonymisering"**.

---

## 1. Syfte och översikt

En webbapplikation som körs lokalt (på en server/dator med GPU) där användare kan:

1. **Ladda upp ljudfiler eller filmfiler** med svenskt tal och få dem transkriberade
   till Word-filer. Användaren väljer per uppladdning om resultatet ska vara:
   - transkriberad text **utan** anonymisering,
   - transkriberad text **med** anonymisering,
   - eller **både och** (två separata Word-filer).
2. **Ladda upp dokument** (PDF, Word, Excel) med svensk text och få dem anonymiserade.
   Även här väljer användaren: anonymiserad version, oanonymiserad (konverterad) version,
   eller både och.
3. **Valfritt få en kodnyckel** (per uppladdning): en separat fil som kopplar ihop
   pseudonymerna i den anonymiserade texten med de ursprungliga uppgifterna,
   t.ex. `[Person 1] = Anna Andersson`.

Allt tal och all text är på **svenska**. All bearbetning sker **lokalt** — inga filer
eller data skickas till externa tjänster (viktigt ur GDPR-/sekretessynpunkt, då
materialet kan innehålla personuppgifter).

## 2. AI-modeller (obligatoriska val)

| Uppgift | Modell | Kommentar |
|---|---|---|
| Transkribering (svenska) | [`KBLab/kb-whisper-large`](https://huggingface.co/KBLab/kb-whisper-large) | KB:s svenska Whisper-modell. Kör via `faster-whisper` (CTranslate2) för bäst prestanda på GPU; modellen finns i faster-whisper-format i samma repo. Fallback: `transformers`-pipeline. |
| Anonymisering (NER, svenska) | [`KB/bert-base-swedish-cased`](https://huggingface.co/KB/bert-base-swedish-cased) som grund, i praktiken den NER-finetunade varianten [`KB/bert-base-swedish-cased-ner`](https://huggingface.co/KB/bert-base-swedish-cased-ner) | Basmodellen KB-BERT kan inte identifiera entiteter utan finetuning. Använd därför den officiella NER-varianten (samma KB-BERT i botten) via `transformers`-pipeline `token-classification` med `aggregation_strategy="first"`. |

Modellerna laddas ner en gång och cachas lokalt (`HF_HOME` konfigurerbar via `.env`).
Applikationen ska automatiskt använda GPU (`cuda`) om tillgänglig, annars CPU.
Gör Whisper-modellstorleken konfigurerbar via `.env` (`WHISPER_MODEL=KBLab/kb-whisper-large`
som standard) så att mindre varianter kan användas på svagare maskiner.

## 3. Anonymiseringslogik

1. Kör KB-BERT-NER över texten och fånga entiteter: **PER** (person), **LOC** (plats),
   **ORG** (organisation), samt **TME/EVN/WRK/OBJ/MSR/PRC** om modellen returnerar dem
   (gör konfigurerbart vilka typer som ersätts; standard: PER, LOC, ORG).
2. Komplettera med **regex-baserad detektering** av strukturerade personuppgifter som
   NER-modellen missar: personnummer (ÅÅÅÅMMDD-XXXX och ÅÅMMDD-XXXX), telefonnummer,
   e-postadresser, registreringsnummer.
3. Ersätt varje unik entitet med en **konsekvent pseudonym**: `[Person 1]`, `[Person 2]`,
   `[Plats 1]`, `[Organisation 1]`, `[Personnummer 1]`, `[Telefon 1]`, `[E-post 1]` osv.
   Samma ursprungssträng ska alltid få samma pseudonym inom en och samma körning.
   Matcha även case-insensitivt och hantera svenska böjningsformer enkelt
   (t.ex. genitiv-s: "Annas" → "[Person 1]s").
4. Bygg samtidigt upp **kodnyckeln**: tabell med kolumnerna *Pseudonym*, *Ursprunglig
   uppgift*, *Typ*, *Antal förekomster*.

**Viktigt:** Kodnyckeln innehåller själva personuppgifterna. Den ska genereras som en
separat Word-fil, aldrig bäddas in i den anonymiserade filen, och gränssnittet ska
tydligt markera den (t.ex. "⚠ Innehåller ursprungliga personuppgifter — hantera separat").

## 4. Filflöden

### 4.1 Ljud/film → transkribering
- Tillåtna format: ljud `mp3, wav, m4a, flac, ogg, aac, wma`; film `mp4, mov, avi, mkv, webm, wmv`.
- Film: extrahera ljudspår med **ffmpeg** (16 kHz mono WAV) innan transkribering.
- Transkribering med KB-Whisper (`language="sv"`), med tidsstämplar per segment.
- Word-utdata: rubrik med källfilens namn och datum, därefter transkriptionen
  segmentvis med tidsstämpel `[hh:mm:ss]` (gör tidsstämplar av/på-valbart i UI, standard på).
- Val i UI per uppladdning: ☐ Transkription (oanonymiserad) ☐ Anonymiserad transkription ☐ Kodnyckel.
  Minst ett av de två första måste väljas; kodnyckel kräver att anonymisering är vald.

### 4.2 Dokument → anonymisering
- Tillåtna format: `pdf`, `docx`/`doc`, `xlsx`/`xls`.
- Textextraktion: PDF med **PyMuPDF (fitz)**; Word med **python-docx** (styckevis, inkl.
  tabeller); Excel med **openpyxl** (cell för cell, per blad).
- Anonymisering enligt avsnitt 3. För Word bevaras styckesstruktur och tabeller så långt
  det går; för Excel skrivs resultatet som tabeller i Word-filen (ett avsnitt per blad);
  för PDF skrivs extraherad text styckevis.
- Val i UI per uppladdning: ☐ Anonymiserad version ☐ Oanonymiserad (konverterad) version ☐ Kodnyckel.
- Skannade PDF:er utan textlager: visa tydligt felmeddelande ("Dokumentet saknar textlager") —
  OCR ingår **inte** i första versionen (kan bli senare tillägg).

### 4.3 Utdata
- **Alla genererade filer är Word-filer (`.docx`)**, skapade med `python-docx`.
- Namngivning: `<källfilnamn>_transkription.docx`, `<källfilnamn>_anonymiserad.docx`,
  `<källfilnamn>_kodnyckel.docx`.
- Resultat laddas ner per fil samt som "Ladda ner alla" (zip).

## 5. Teknisk stack

- **Backend:** Python 3.11+, **FastAPI** + Uvicorn.
- **Frontend:** En enkel, ren HTML/CSS/JS-sida (ingen ramverksbuild) som serveras av FastAPI.
  Drag-och-släpp-uppladdning, kryssrutor för valen, jobbstatus, nedladdningslänkar.
  Gränssnittsspråk: **svenska**. Titel: "Transkribering och anonymisering".
- **ML:** `faster-whisper`, `transformers`, `torch` (CUDA-version), `ffmpeg` (systemberoende).
- **Dokument:** `python-docx`, `PyMuPDF`, `openpyxl`.
- **Jobbhantering:** Uppladdning skapar ett **jobb** som körs asynkront (in-process-kö,
  t.ex. `asyncio`/bakgrundstråd med sekventiell GPU-kö — kör ett transkriberings­jobb åt
  gången). Frontend pollar `GET /api/jobs/{id}` för status/progress. Ingen extern
  kö-infrastruktur (Redis/Celery) i v1.
- **Lagring:** Lokala kataloger `data/uploads/` och `data/results/` (gitignoreade),
  per jobb-ID. Konfigurerbar automatisk rensning av gamla jobb (standard: 24 h).
- **Konfiguration:** `.env` + `.env.example` (modellnamn, device, maxfilstorlek
  (standard 2 GB), rensningsintervall, port).
- **Ingen inloggning/fleranvändarhantering i v1** (appen körs internt).

## 6. API-skiss

```
POST /api/jobs                      # multipart: fil + val (transcribe, anonymize, keyfile, timestamps)
GET  /api/jobs/{id}                 # status: queued|processing|done|error, progress, fellista
GET  /api/jobs/{id}/files           # lista över genererade filer
GET  /api/jobs/{id}/files/{name}    # ladda ner en fil
GET  /api/jobs/{id}/download-all    # zip
GET  /api/health                    # inkl. device (cuda/cpu) och laddade modeller
```

## 7. Repostruktur

```
transkribering-och-anonymisering/
├── README.md                # på svenska: syfte, installation, användning, GPU-krav
├── PLAN.md                  # denna fil
├── .env.example
├── .gitignore               # data/, .env, modellcache, __pycache__ m.m.
├── requirements.txt
├── app/
│   ├── main.py              # FastAPI-app, routes, statiska filer
│   ├── config.py            # inställningar från .env
│   ├── jobs.py              # jobbkö, status, rensning
│   ├── transcription.py     # KB-Whisper (faster-whisper), ffmpeg-extraktion
│   ├── anonymization.py     # KB-BERT-NER + regex + pseudonymisering + kodnyckel
│   ├── extraction.py        # textextraktion pdf/docx/xlsx
│   ├── docx_output.py       # generering av Word-filer
│   └── static/              # index.html, style.css, app.js (svenska)
├── tests/
│   ├── test_anonymization.py
│   ├── test_extraction.py
│   ├── test_docx_output.py
│   └── fixtures/            # små svenska testfiler (ljud, pdf, docx, xlsx)
└── scripts/
    └── download_models.py   # förhämtar modellerna till cache
```

## 8. Kvalitet och tester

- Enhetstester (pytest) för: regexdetektering (personnummer, telefon, e-post),
  konsekvent pseudonymisering, genitivhantering, kodnyckelgenerering,
  textextraktion ur alla tre dokumentformat, docx-generering.
- NER- och Whisper-anrop mockas i tester (modellerna är för tunga för CI);
  lägg dessutom ett manuellt smoke-test-skript `scripts/smoke_test.py` som kör
  hela kedjan på fixtures när modellerna finns lokalt.
- Felhantering: ogiltigt filformat, för stor fil, korrupt fil, PDF utan textlager,
  ffmpeg-fel — alla ska ge begripliga svenska felmeddelanden i UI.
- Kodstil: `ruff` + typannoteringar.

## 9. Byggetapper (arbeta i denna ordning, committa per etapp)

1. **Skelett:** repo, struktur enligt avsnitt 7, FastAPI med `/api/health`,
   statisk startsida, config, README, `.gitignore`, requirements.
2. **Jobbmotor:** uppladdning, validering av filtyp/storlek, jobbkö, statuspolling,
   fillagring, nedladdnings-endpoints, zip.
3. **Anonymisering:** extraction.py (pdf/docx/xlsx) + anonymization.py
   (NER + regex + pseudonymer + kodnyckel) + docx_output.py, med tester.
   Verifiera hela dokumentflödet i UI.
4. **Transkribering:** ffmpeg-extraktion, KB-Whisper via faster-whisper,
   tidsstämplade segment, koppling till anonymiseringen ("både och"-fallet),
   progressrapportering till UI.
5. **Frontend-finish:** komplett svensk UI enligt avsnitt 4 (val per filtyp,
   varningsmarkering för kodnyckel, felmeddelanden, "Ladda ner alla").
6. **Härdning:** automatisk rensning, maxstorlekar, `download_models.py`,
   smoke-test, README med installations- och GPU-instruktioner
   (inkl. CUDA-versionsnot för torch), slutgenomgång mot kraven i detta dokument.

## 10. Acceptanskriterier (checklista)

- [ ] Ljud- och filmfil på svenska ger korrekt transkriberad Word-fil, med valbara tidsstämplar.
- [ ] Valet oanonymiserad/anonymiserad/både och fungerar för ljud/film, och ger 1–2 Word-filer.
- [ ] PDF-, Word- och Excel-filer kan laddas upp och anonymiseras till Word-fil;
      oanonymiserad konverterad version kan också väljas.
- [ ] Kodnyckel kan väljas till och blir en separat Word-fil med korrekt mappning,
      och samma entitet får samma pseudonym genom hela dokumentet.
- [ ] Personnummer, telefonnummer och e-post fångas även när NER missar dem.
- [ ] All bearbetning sker lokalt; inga anrop till externa API:er vid körning
      (endast modellnedladdning från Hugging Face vid första start/`download_models.py`).
- [ ] GPU används när den finns; appen startar och fungerar även på CPU.
- [ ] Alla tester gröna; smoke-testet går igenom hela kedjan.
