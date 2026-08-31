# Transkribering och anonymisering

Webbapplikation som körs **lokalt** för att:

- **Transkribera** svenska ljud- och filmfiler till Word-filer med
  [KB-Whisper](https://huggingface.co/KBLab/kb-whisper-large).
- **Anonymisera** svensk text i transkriptioner och dokument (PDF, Word, Excel) med
  [KB-BERT NER](https://huggingface.co/KB/bert-base-swedish-cased-ner) kompletterad med
  regexdetektering av personnummer, telefonnummer, e-postadresser och registreringsnummer.
- **Generera kodnyckel** (valfritt): en separat Word-fil som kopplar pseudonymer
  (`[Person 1]` osv.) till de ursprungliga uppgifterna.

All bearbetning sker lokalt på den egna maskinen — inga filer eller data skickas till
externa tjänster. Det enda nätverksanropet är nedladdning av modellerna från Hugging Face
vid första start (eller via `scripts/download_models.py`).

## Krav

- Python 3.11+
- `ffmpeg` installerat och i `PATH` (krävs för ljud-/filmfiler)
- Helst en NVIDIA-GPU med CUDA (appen fungerar även på CPU, men transkribering blir långsam)
- Cirka 5 GB diskutrymme för modellcache

## Installation

```bash
git clone https://github.com/bjoottG/transkribering-och-anonymisering.git
cd transkribering-och-anonymisering
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # anpassa vid behov
```

### GPU (CUDA)

`pip install torch` ger på Linux/Windows ofta en CPU-version. För GPU, installera torch
med rätt CUDA-version enligt <https://pytorch.org/get-started/locally/>, t.ex.:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

`faster-whisper` använder CTranslate2 som kräver cuDNN/cuBLAS-bibliotek vid GPU-körning;
följ instruktionerna på <https://github.com/SYSTRAN/faster-whisper>.

### Förhämta modeller (valfritt)

```bash
python scripts/download_models.py
```

## Användning

```bash
python -m app.main
# eller: uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Öppna <http://localhost:8000>, dra in en fil och välj vilka resultat du vill ha.
Alla resultat blir Word-filer (`.docx`).

| Filtyp | Val |
|---|---|
| Ljud/film (`mp3, wav, m4a, flac, ogg, aac, wma, mp4, mov, avi, mkv, webm, wmv`) | Transkription, anonymiserad transkription, kodnyckel, tidsstämplar av/på |
| Dokument (`pdf, docx, doc, xlsx, xls`) | Anonymiserad version, oanonymiserad (konverterad) version, kodnyckel |

**⚠ Kodnyckeln innehåller de ursprungliga personuppgifterna** — hantera och lagra den
separat från den anonymiserade filen.

Uppladdningar och resultat lagras i `data/` och rensas automatiskt efter 24 timmar
(konfigurerbart via `CLEANUP_HOURS` i `.env`).

## Konfiguration

Se [.env.example](.env.example) för alla inställningar: modellval, device (cuda/cpu),
entitetstyper som anonymiseras, maxfilstorlek, rensningsintervall och port.

## Tester

```bash
pytest                          # enhetstester (ML-modeller mockas)
python scripts/smoke_test.py    # manuellt helkedjetest, kräver modellerna lokalt
ruff check .
```

## Arkitektur

Se [PLAN.md](PLAN.md) för fullständig kravspecifikation och plan.

```
app/main.py           FastAPI-routes och statiska filer
app/config.py         inställningar från .env
app/jobs.py           jobbkö (sekventiell GPU-kö), status, automatisk rensning
app/transcription.py  ffmpeg-extraktion + KB-Whisper via faster-whisper
app/anonymization.py  KB-BERT-NER + regex + pseudonymisering + kodnyckel
app/extraction.py     textextraktion ur pdf/docx/xlsx
app/docx_output.py    generering av Word-filer
app/static/           frontend (svenska)
```
