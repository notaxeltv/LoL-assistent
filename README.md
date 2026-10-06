# Jarvis — Assistente vocale locale (Streamlit + Ollama)

Interfaccia grafica in Python/Streamlit che parla con il modello **qwen** su **Ollama**, con input dal microfono (SpeechRecognition, `it-IT`) e output vocale (pyttsx3).

## Prerequisiti

1. [Ollama](https://ollama.com) installato e in esecuzione in background
2. Modello scaricato:

```bash
ollama pull qwen
```

3. Python 3.10+ consigliato

## Installazione librerie

### Comando base (tutte le piattaforme)

```bash
pip install streamlit ollama SpeechRecognition pyttsx3 PyAudio
```

Oppure:

```bash
pip install -r requirements.txt
```

### Accortezze PyAudio / audio per sistema operativo

**Windows**

```bash
pip install pipwin
pipwin install pyaudio
```

Se `pipwin` non è disponibile, prova direttamente:

```bash
pip install PyAudio
```

Per la sintesi vocale: abilita una **voce italiana** in *Impostazioni → Ora e lingua → Voce* (o Accessibilità). pyttsx3 userà SAPI5.

**macOS**

```bash
brew install portaudio
pip install PyAudio
```

Per TTS italiano: Impostazioni di Sistema → Accessibilità → Contenuto parlato → aggiungi una voce italiana. pyttsx3 userà NSSS.

**Linux (Debian/Ubuntu)**

```bash
sudo apt update
sudo apt install -y portaudio19-dev python3-pyaudio espeak espeak-ng ffmpeg
pip install PyAudio pyttsx3
```

`espeak` / `espeak-ng` sono necessari a pyttsx3 su Linux. Per voci migliori puoi anche installare pacchetti voci aggiuntivi disponibili nella tua distro.

> **Nota sul riconoscimento vocale:** `recognize_google` di SpeechRecognition usa le API Google e richiede connessione Internet per la sola trascrizione. Il modello LLM resta 100% locale via Ollama.

## Avvio

```bash
# Terminale 1 — se Ollama non è già attivo
ollama serve

# Terminale 2
streamlit run jarvis_chat.py
```

Apri l’URL mostrato nel terminale (di solito `http://localhost:8501`).

## Funzionalità

| Funzione | Dettaglio |
|----------|-----------|
| Chat | Cronologia User/Assistant in `st.session_state` |
| LLM | Ollama modello `qwen` con **streaming** dei token |
| Microfono | Pulsante **🎙️ Parla al Microfono** → `it-IT` → invio automatico a Qwen |
| Tastiera | `st.chat_input` sempre disponibile |
| TTS | pyttsx3 legge la risposta **solo dopo** la fine dello streaming (rate ≈ 170, voce IT se presente) |

## Struttura

```
jarvis_chat.py    # Applicazione Streamlit completa
requirements.txt  # Dipendenze Python
README.md         # Questa guida
```
