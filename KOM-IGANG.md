# Kom igång — steg för steg

Den här guiden visar hur du laddar ner **Transkribering och anonymisering** från GitHub
och kör den lokalt på din egen dator. Allt körs lokalt — inga filer eller data lämnar
din dator (modellerna laddas ner en gång från Hugging Face vid installationen).

## 1. Förberedelser

Du behöver ha följande installerat:

| Verktyg | Kontrollera med | Om det saknas |
|---|---|---|
| **Git** | `git --version` | <https://git-scm.com/downloads> |
| **Python 3.11+** | `python3 --version` (Windows: `python --version`) | <https://www.python.org/downloads/> — bocka i "Add Python to PATH" på Windows |
| **ffmpeg** | `ffmpeg -version` | macOS: `brew install ffmpeg` · Windows: `winget install ffmpeg` (starta om terminalen efteråt) |

ffmpeg behövs bara för ljud- och filmfiler — dokumentanonymisering fungerar utan.

Du behöver också cirka **5 GB ledigt diskutrymme** för AI-modellerna.

## 2. Ladda ner repot

Öppna en terminal (macOS: Terminal, Windows: PowerShell) och kör:

```bash
git clone https://github.com/bjoottG/transkribering-och-anonymisering.git
cd transkribering-och-anonymisering
```

## 3. Installera

Skapa en isolerad Python-miljö och installera paketen:

**macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Nedladdningen är ett par GB och tar en stund.

> Får du ett fel om körningspolicy på Windows: kör
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` och försök igen.

## 4. Välj modellstorlek (rekommenderas på vanliga datorer)

Standardmodellen `kb-whisper-large` är byggd för datorer med NVIDIA-GPU.
På en vanlig kontorsdator (utan sådan GPU) — skapa en fil som heter `.env`
i projektmappen med det här innehållet:

```
WHISPER_MODEL=KBLab/kb-whisper-small
DEVICE=cpu
```

Det ger snabb transkribering med bra svensk kvalitet. Vill du ha högre kvalitet
och kan vänta längre: byt `small` mot `medium`.

## 5. Hämta AI-modellerna (engångssteg)

```bash
python scripts/download_models.py
```

Detta laddar ner den svenska Whisper-modellen (transkribering) och KB-BERT
(anonymisering) till en lokal cache, cirka 1 GB med `small`-modellen.
Hoppar du över steget laddas modellerna ner automatiskt vid första jobbet i stället.

## 6. Starta servern

```bash
python -m app.main
```

Öppna sedan **<http://localhost:8000>** i webbläsaren.

Servern kör tills du stänger terminalfönstret eller trycker `Ctrl+C`.
Nästa gång du ska använda appen räcker det med steg 6 (aktivera `.venv` först
enligt steg 3 om du öppnat en ny terminal).

## 7. Använda appen

1. Dra in en fil i rutan (eller klicka och välj):
   - **Ljud/film** (`mp3, wav, m4a, flac, ogg, aac, wma, mp4, mov, avi, mkv, webm, wmv`) → transkriberas
   - **Dokument** (`pdf, docx, xlsx`) → konverteras/anonymiseras
2. Kryssa i vilka resultat du vill ha och tryck **Starta**.
3. Följ förloppet och ladda ner Word-filerna när jobbet är klart.

**⚠ Viktigt om kodnyckeln:** den innehåller de ursprungliga personuppgifterna
(vem `[Person 1]` är osv.). Hantera och lagra den separat från den anonymiserade filen.

**Valfritt — beskriv skärminnehåll i filmer:** för skärminspelningar kan appen även
beskriva vad som syns på skärmen (menyer, fältnamn, knappar) och bygga en tidslinje
med tal + skärm. Det kräver en API-nyckel från <https://console.anthropic.com> i `.env`
(`ANTHROPIC_API_KEY=sk-ant-...`) och skickar bildrutorna till Claude API — använd bara
för material utan känsliga uppgifter. Utan nyckel är kryssrutan avstängd.

Uppladdningar och resultat sparas i mappen `data/` och rensas automatiskt efter 24 timmar.

## Vanliga problem

| Problem | Lösning |
|---|---|
| "ffmpeg hittades inte på servern" | Installera ffmpeg (se steg 1) och starta om servern. Öppnade du terminalen innan ffmpeg installerades — öppna en ny. |
| Sidan svarar inte / "refused to connect" | Servern är inte igång — kör steg 6. |
| Porten är upptagen (`address already in use`) | Lägg till `PORT=8001` i `.env` och öppna <http://localhost:8001>. |
| "Dokumentet saknar textlager" | PDF:en är skannad utan text — OCR stöds inte i denna version. |
| Gamla format `.doc`/`.xls` | Öppna filen och spara om som `.docx`/`.xlsx`. |
| Transkriberingen är mycket långsam | Kontrollera att `.env` pekar på `kb-whisper-small` (steg 4). Första jobbet är alltid långsammare eftersom modellen laddas. |

Fler inställningar (maxfilstorlek, rensningsintervall m.m.) finns beskrivna i
[.env.example](.env.example). Fullständig dokumentation finns i [README.md](README.md).
