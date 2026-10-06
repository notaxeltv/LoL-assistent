# LoL Coach — Assistente vocale per League of Legends

App Streamlit locale: parli al **microfono** durante una partita di LoL, **Qwen** (Ollama) ti risponde da coach, e **pyttsx3** legge la risposta ad alta voce.

Ideale su secondo monitor / Alt-Tab: *«sono under vs Darius, cosa faccio?»*, *«vado dragon o farm?»*, *«prossima item?»*.

## Prerequisiti

1. [Ollama](https://ollama.com) in esecuzione
2. Modello:

```bash
ollama pull qwen
```

3. Python 3.10+ consigliato

## Installazione

```bash
pip install streamlit ollama SpeechRecognition pyttsx3 PyAudio
# oppure
pip install -r requirements.txt
```

### PyAudio per OS

**Windows**
```bash
pip install pipwin
pipwin install pyaudio
```

**macOS**
```bash
brew install portaudio
pip install PyAudio
```

**Linux (Debian/Ubuntu)**
```bash
sudo apt install -y portaudio19-dev python3-pyaudio espeak espeak-ng
pip install PyAudio
```

> La trascrizione (`recognize_google`) richiede Internet. Il LLM resta locale via Ollama.

## Avvio

```bash
streamlit run lol_coach.py
```

(`streamlit run jarvis_chat.py` funziona ancora: reindirizza a LoL Coach.)

## Uso in partita

1. Prima del loadout: in sidebar imposta **ruolo**, **campione**, **rank** e note sull’avversario
2. In game: clicca **🎙️ Chiedi al Coach** e parla in italiano
3. Qwen risponde in streaming; a fine risposta la TTS legge il consiglio
4. Puoi anche digitare nella barra in basso

Il system prompt forza risposte **brevi e azionabili** (stile coach in cuffia), non guide lunghe da wiki.

## File

```
lol_coach.py       # App principale (coach LoL + voce)
jarvis_chat.py     # Alias di avvio per compatibilità
requirements.txt
README.md
```
