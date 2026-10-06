# LoL Coach — Assistente vocale + visione schermo

Coach locale per League of Legends: parli al **microfono**, l’app può **vedere lo schermo** (screenshot → modello vision Ollama) e risponderti a voce in modo **rapido**.

## Funzionalità

| Feature | Dettaglio |
|---------|-----------|
| Microfono | SpeechRecognition `it-IT` → prompt automatico |
| Visione schermo | Screenshot con `mss` + modello vision (`qwen2.5vl` / `llava`…) |
| Solo schermo | Pulsante **📸 Solo schermo** = «cosa faccio ora?» sullo screenshot |
| Modalità rapida | Meno token, mic più reattivo, TTS più veloce |
| TTS anticipata | Inizia a parlare dalla **prima frase**, senza aspettare tutta la risposta |
| Contesto | Ruolo, campione, rank, note avversario in sidebar |

## Prerequisiti

```bash
# Modello testo (già in uso)
ollama pull qwen

# Modello vision (necessario per "Vedi lo schermo")
ollama pull qwen2.5vl
# alternative: ollama pull llava   oppure   ollama pull llama3.2-vision
```

## Installazione

```bash
pip install -r requirements.txt
```

Dipendenze extra per la visione: `mss`, `Pillow`.

### PyAudio per OS

**Windows:** `pip install pipwin && pipwin install pyaudio`  
**macOS:** `brew install portaudio && pip install PyAudio`  
**Linux:** `sudo apt install portaudio19-dev espeak espeak-ng && pip install PyAudio`

## Avvio

```bash
streamlit run lol_coach.py
```

## Uso in partita

1. LoL in **borderless windowed** (il fullscreen esclusivo a volte blocca lo screenshot)
2. App su secondo monitor; in sidebar scegli il **monitor** dove gira LoL
3. Attiva **Vedi lo schermo** + **Modalità rapida**
4. **🎙️ Chiedi al Coach** → screenshot immediato + ascolto microfono
5. Oppure **📸 Solo schermo** se non vuoi parlare

> La trascrizione Google richiede Internet. LLM e visione restano locali via Ollama.
