# LoL Coach — Assistente vocale locale / Local voice coach

<p align="center">
  <strong>🇮🇹 Italiano</strong> · <a href="#-english">🇬🇧 English</a>
</p>

Coach IA **totalmente in locale** per League of Legends: parli al microfono (o digiti), l’app **vede la partita dallo schermo in tempo reale** e ti risponde a voce con consigli brevi.

> **Non serve un’API key Riot** né il Developer Portal. Il percorso principale è il feed video dello schermo + Ollama sul tuo PC.

---

# 🇮🇹 Italiano

## Indice

1. [Cosa fa](#cosa-fa)
2. [Requisiti](#requisiti)
3. [Installazione passo passo](#installazione-passo-passo)
4. [Avvio](#avvio)
5. [Guida all’uso in partita](#guida-alluso-in-partita)
6. [Impostazioni consigliate](#impostazioni-consigliate)
7. [Come “vede” la partita](#come-vede-la-partita)
8. [Struttura del progetto](#struttura-del-progetto)
9. [Risoluzione problemi](#risoluzione-problemi)
10. [Privacy e limiti](#privacy-e-limiti)

## Cosa fa

| Funzione | Descrizione |
|----------|-------------|
| Chat vocale | Pulsante **Chiedi al Coach** → microfono italiano (`it-IT`) → risposta di Qwen |
| Chat testuale | Barra in basso sempre disponibile |
| Tempo reale | **Feed schermo continuo** (~2 FPS): buffer degli ultimi frame della partita |
| Analisi immediata | Pulsante **Analizza ora (live)** senza parlare |
| Sintesi vocale | `pyttsx3` legge la risposta (anche dalla prima frase, per essere più reattivi) |
| Contesto | Ruolo, campione, rank e note in sidebar |
| Extra opzionale | Live Client locale `127.0.0.1:2999` (niente API key; OFF di default) |

## Requisiti

- Windows, macOS o Linux
- [Python](https://www.python.org/) **3.10+**
- [Ollama](https://ollama.com/) installato e in esecuzione
- Microfono funzionante
- League of Legends (consigliato in **borderless windowed**)
- Ideale: secondo monitor per l’app Streamlit

### Modelli Ollama

```bash
# Consigliato (vede i frame della partita)
ollama pull qwen2.5vl

# Opzionale: solo testo (se disattivi il feed schermo)
ollama pull qwen
```

> Se usi un altro modello vision (`llava`, `llama3.2-vision`, …) impostalo nella sidebar.

## Installazione passo passo

### 1. Clona / apri il progetto

```bash
git clone <url-del-repo>
cd LoL-assistent
```

### 2. (Consigliato) Crea un ambiente virtuale

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Installa le dipendenze Python

```bash
pip install -r requirements.txt
```

Equivalente manuale:

```bash
pip install streamlit ollama SpeechRecognition pyttsx3 PyAudio mss Pillow
```

### 4. Accortezze audio per sistema operativo

<details>
<summary><strong>Windows</strong></summary>

```bash
pip install pipwin
pipwin install pyaudio
```

Se `pipwin` non funziona, prova `pip install PyAudio`.

Per la voce italiana: *Impostazioni → Ora e lingua → Voce* (o Accessibilità) e abilita una voce IT. `pyttsx3` usa SAPI5.

</details>

<details>
<summary><strong>macOS</strong></summary>

```bash
brew install portaudio
pip install PyAudio
```

Voce italiana: *Impostazioni di Sistema → Accessibilità → Contenuto parlato*.

</details>

<details>
<summary><strong>Linux (Debian/Ubuntu)</strong></summary>

```bash
sudo apt update
sudo apt install -y portaudio19-dev python3-pyaudio espeak espeak-ng ffmpeg
pip install PyAudio
```

`espeak` / `espeak-ng` servono a `pyttsx3` su Linux.

</details>

### 5. Avvia Ollama e scarica i modelli

```bash
# Se non è già in background
ollama serve

# In un altro terminale
ollama pull qwen2.5vl
ollama list
```

## Avvio

```bash
streamlit run lol_coach.py
```

Apri l’URL mostrato (di solito `http://localhost:8501`).

> `streamlit run jarvis_chat.py` funziona ancora: è un alias verso LoL Coach.

## Guida all’uso in partita

1. **Prima della partita**
   - Avvia Ollama e Streamlit
   - In sidebar: ruolo, campione, rank (opzionale ma utile)
   - Seleziona il **monitor di gioco**
   - Lascia ON **Feed schermo continuo**
   - Lascia ON **Modalità rapida** e **TTS dalla prima frase**

2. **Imposta LoL**
   - Modalità video: **Borderless** (il fullscreen esclusivo a volte blocca la cattura)
   - Metti Streamlit sul secondo monitor (o usa Alt-Tab)

3. **Durante la partita**
   - Clicca **🎙️ Chiedi al Coach** e parla, es.  
     *«sono under vs Darius, pusha, cosa faccio?»*  
     *«vado dragon o farmo?»*  
     *«prossima item contro tanks?»*
   - Oppure **🔴 Analizza ora (live)** per un consiglio immediato sui frame recenti
   - Oppure scrivi nella barra in basso

4. **Cosa riceve il modello**
   - Gli ultimi frame dal feed continuo (non uno screenshot “a caso” dopo il click)
   - Il tuo contesto (ruolo/campione/note)
   - La domanda vocale o scritta

## Impostazioni consigliate

| Impostazione | Valore consigliato | Perché |
|--------------|--------------------|--------|
| Feed schermo continuo | ON | Vede la partita senza API Riot |
| Live Client locale | OFF | Opzionale; non necessaria |
| FPS feed | 2 | Buon compromesso CPU / freschezza |
| Frame per domanda | 3 | Mini-sequenza temporale |
| Modalità rapida | ON | Risposte corte, TTS più veloce |
| TTS dalla prima frase | ON | Inizia a parlare subito |
| Modello vision | `qwen2.5vl` | Capisce i frame |

## Come “vede” la partita

### Fonte principale (default): feed schermo continuo

Un thread in background cattura frame del monitor scelto (~2 FPS) e li tiene in un **ring buffer**.  
Quando fai una domanda, l’app invia gli **ultimi frame** al modello vision → visione “quasi video”, non uno screen isolato.

**Nessuna API key Riot. Nessuna registrazione.**

### Extra opzionale: Live Client locale

Su `https://127.0.0.1:2999` il client LoL può esporre dati di partita (gold, KDA, eventi…) **solo mentre giochi**, in locale.

- **Non** è l’API del [Developer Portal](https://developer.riotgames.com/)
- **Non** richiede API key
- È **OFF di default**: puoi ignorarla del tutto

## Struttura del progetto

```
LoL-assistent/
├── lol_coach.py       # App Streamlit (UI, microfono, TTS, Ollama)
├── live_game.py       # Feed schermo continuo + Live Client opzionale
├── jarvis_chat.py     # Alias di avvio (compatibilità)
├── requirements.txt   # Dipendenze Python
└── README.md          # Questa guida (IT + EN)
```

## Risoluzione problemi

| Problema | Cosa provare |
|------------------------|
| Ollama non risponde | `ollama serve` e `ollama list`; verifica il nome modello in sidebar |
| Il modello vision manca | `ollama pull qwen2.5vl` |
| Microfono non funziona | Controlla PyAudio; su Discord/LoL evita l’uso esclusivo del mic |
| Trascrizione fallisce | `recognize_google` richiede Internet (solo per STT) |
| Nessun frame / schermo nero | LoL in **borderless**; scegli il monitor giusto; disattiva overlay invasivi |
| TTS non parla italiano | Installa/abilita una voce IT di sistema; su Linux: `espeak-ng` |
| App lenta | Modalità rapida ON; riduci FPS/frame; oppure spegni il feed e usa solo testo |

## Privacy e limiti

- LLM e visione girano **in locale** via Ollama
- La trascrizione vocale Google (`SpeechRecognition`) usa un servizio online: serve connessione per quella sola fase
- I modelli vision possono sbagliarsi su dettagli minuti (CD esatti, fog di guerra, ecc.): trattali come coach, non come truth assoluta
- Uso personale / educativo; rispetta i Terms of Service di Riot (niente injection nel client di gioco)

---

# 🇬🇧 English

<a id="-english"></a>

## Table of contents

1. [What it does](#what-it-does)
2. [Requirements](#requirements)
3. [Step-by-step installation](#step-by-step-installation)
4. [Run the app](#run-the-app)
5. [In-game usage guide](#in-game-usage-guide)
6. [Recommended settings](#recommended-settings)
7. [How it “sees” the match](#how-it-sees-the-match)
8. [Project structure](#project-structure)
9. [Troubleshooting](#troubleshooting)
10. [Privacy & limits](#privacy--limits)

## What it does

| Feature | Description |
|---------|-------------|
| Voice chat | **Ask the Coach** → Italian microphone (`it-IT`) → Qwen reply |
| Text chat | Bottom input bar always available |
| Real-time vision | **Continuous screen feed** (~2 FPS) with a recent-frame buffer |
| Instant analysis | **Analyze now (live)** without speaking |
| Text-to-speech | `pyttsx3` reads the answer (can start from the first sentence) |
| Match context | Role, champion, rank, notes in the sidebar |
| Optional extra | Local Live Client at `127.0.0.1:2999` (no API key; OFF by default) |

## Requirements

- Windows, macOS, or Linux
- [Python](https://www.python.org/) **3.10+**
- [Ollama](https://ollama.com/) installed and running
- Working microphone
- League of Legends (preferably **borderless windowed**)
- Ideal: a second monitor for the Streamlit UI

### Ollama models

```bash
# Recommended (understands game frames)
ollama pull qwen2.5vl

# Optional: text-only (if you disable the screen feed)
ollama pull qwen
```

> Using another vision model (`llava`, `llama3.2-vision`, …)? Set it in the sidebar.

## Step-by-step installation

### 1. Clone / open the project

```bash
git clone <repo-url>
cd LoL-assistent
```

### 2. (Recommended) Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install streamlit ollama SpeechRecognition pyttsx3 PyAudio mss Pillow
```

### 4. OS-specific audio notes

<details>
<summary><strong>Windows</strong></summary>

```bash
pip install pipwin
pipwin install pyaudio
```

If that fails, try `pip install PyAudio`.

Enable an Italian system voice under *Settings → Time & language → Speech* (or Accessibility). `pyttsx3` uses SAPI5.

</details>

<details>
<summary><strong>macOS</strong></summary>

```bash
brew install portaudio
pip install PyAudio
```

Italian voice: *System Settings → Accessibility → Spoken Content*.

</details>

<details>
<summary><strong>Linux (Debian/Ubuntu)</strong></summary>

```bash
sudo apt update
sudo apt install -y portaudio19-dev python3-pyaudio espeak espeak-ng ffmpeg
pip install PyAudio
```

`espeak` / `espeak-ng` are required by `pyttsx3` on Linux.

</details>

### 5. Start Ollama and pull models

```bash
ollama serve
ollama pull qwen2.5vl
ollama list
```

## Run the app

```bash
streamlit run lol_coach.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`).

> `streamlit run jarvis_chat.py` still works as a compatibility alias.

## In-game usage guide

1. **Before the match**
   - Start Ollama and Streamlit
   - Sidebar: set role / champion / rank (optional but helpful)
   - Select your **game monitor**
   - Keep **Continuous screen feed** ON
   - Keep **Fast mode** and **TTS from first sentence** ON

2. **Configure LoL**
   - Use **Borderless** window mode (exclusive fullscreen can block capture)
   - Put Streamlit on a second monitor (or Alt-Tab)

3. **During the match**
   - Click **🎙️ Ask the Coach** and speak, e.g.  
     *“I’m under vs Darius, he’s pushing, what do I do?”*  
     *“Dragon or farm?”*  
     *“Next item vs tanks?”*
   - Or **🔴 Analyze now (live)** for an instant tip from recent frames
   - Or type in the chat box

4. **What the model receives**
   - The latest frames from the continuous feed
   - Your sidebar context
   - Your voice/text question

## Recommended settings

| Setting | Suggested value | Why |
|---------|-----------------|-----|
| Continuous screen feed | ON | Sees the match with no Riot API |
| Local Live Client | OFF | Optional; not required |
| Feed FPS | 2 | Good CPU / freshness balance |
| Frames per question | 3 | Short temporal sequence |
| Fast mode | ON | Short answers, faster TTS |
| TTS from first sentence | ON | Starts speaking sooner |
| Vision model | `qwen2.5vl` | Reads game frames |

## How it “sees” the match

### Primary source (default): continuous screen feed

A background thread captures frames from the selected monitor (~2 FPS) into a **ring buffer**.  
When you ask a question, the app sends the **most recent frames** to the vision model — near real-time vision, not a single on-demand screenshot.

**No Riot API key. No registration.**

### Optional extra: local Live Client

At `https://127.0.0.1:2999`, the LoL client can expose match data (gold, KDA, events…) **only while you are in a game**, locally.

- This is **not** the [Developer Portal](https://developer.riotgames.com/) API
- It does **not** require an API key
- It is **OFF by default** — you can ignore it completely

## Project structure

```
LoL-assistent/
├── lol_coach.py       # Streamlit app (UI, mic, TTS, Ollama)
├── live_game.py       # Continuous screen feed + optional Live Client
├── jarvis_chat.py     # Launch alias (compatibility)
├── requirements.txt   # Python dependencies
└── README.md          # This guide (IT + EN)
```

## Troubleshooting

| Issue | Try this |
|-------|----------|
| Ollama errors | Run `ollama serve` / `ollama list`; check model name in sidebar |
| Missing vision model | `ollama pull qwen2.5vl` |
| Microphone fails | Check PyAudio; avoid exclusive mic capture in Discord/LoL |
| Transcription fails | Google STT needs Internet (STT only) |
| No frames / black screen | Use **borderless** LoL; pick the correct monitor; disable heavy overlays |
| TTS not Italian | Install/enable an IT system voice; on Linux install `espeak-ng` |
| App feels slow | Fast mode ON; lower FPS/frames; or disable feed and use text-only |

## Privacy & limits

- LLM + vision run **locally** through Ollama
- Google speech transcription (`SpeechRecognition`) is online — Internet is needed for that step only
- Vision models can misread fine details (exact cooldowns, fog of war, etc.): treat advice as coaching, not ground truth
- For personal / educational use; respect Riot’s Terms of Service (no injection into the game client)

---

## License / note

Progetto personale di assistenza in-game. Usa i modelli e i servizi nel rispetto dei rispettivi termini.  
Personal in-game assistance project. Use models and services in accordance with their terms.
