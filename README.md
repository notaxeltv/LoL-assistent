# LoL Coach — Tempo reale (senza API key Riot)

Assistente vocale locale che **vede la partita dallo schermo in continuo**.

## Serve un account / API Riot?

**No.** Non ti serve il [Developer Portal](https://developer.riotgames.com/) né una API key.

Il percorso principale è il **feed schermo continuo**: l’app cattura frame del monitor di LoL in background e, quando chiedi aiuto, manda gli ultimi frame al modello vision (Ollama).

### Extra opzionale (disattivato di default)

Esiste anche la **Live Client Data** su `https://127.0.0.1:2999`: la espone il client LoL **in automatico solo durante una partita**, sempre in locale, **senza registrazione**.  
Se non ti convince o non la vuoi usare, lasciala OFF: il coach lavora comunque col solo video.

## Setup

```bash
ollama pull qwen2.5vl     # vision per il feed schermo
pip install -r requirements.txt
streamlit run lol_coach.py
```

## Uso in partita

1. LoL in **borderless windowed**
2. App sul 2° monitor → scegli il **monitor di gioco**
3. Lascia ON **Feed schermo continuo**
4. **🎙️ Chiedi al Coach** oppure **🔴 Analizza ora (live)**

## File

```
lol_coach.py    # UI Streamlit
live_game.py    # Feed continuo (+ Live Client opzionale)
requirements.txt
```
