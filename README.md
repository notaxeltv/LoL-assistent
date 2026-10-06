# LoL Coach — Tempo reale

Assistente vocale locale che **vede la partita in tempo reale**, non con uno screenshot singolo.

## Come “vede” la partita

| Fonte | Cosa fa |
|-------|---------|
| **Riot Live Client API** | Legge stato live da `https://127.0.0.1:2999` (gold, HP, scoreboard, eventi, spell…) mentre sei in game |
| **Feed schermo continuo** | Thread in background che cattura ~2 FPS in un ring buffer; a ogni domanda invia gli **ultimi frame**, come un breve video |

Alla domanda (microfono / testo / **Analizza ora**) il modello riceve il briefing live aggiornato + i frame recenti.

## Setup

```bash
ollama pull qwen          # testo (veloce con sola Live Client)
ollama pull qwen2.5vl     # vision (serve se feed schermo ON)
pip install -r requirements.txt
streamlit run lol_coach.py
```

## Uso in partita

1. LoL in **borderless windowed**
2. Avvia normale / ranked / **Practice Tool** (così nasce la Live Client API)
3. App sul 2° monitor → scegli il **monitor di gioco**
4. Lascia ON: **Live Client API** + **Feed schermo continuo**
5. **🎙️ Chiedi al Coach** oppure **🔴 Analizza ora (live)**

L’anteprima in pagina si aggiorna da sola ogni ~2s (stato API + ultimo frame).

## Tip velocità

- Solo **Live Client** (feed OFF) + modello `qwen` = più veloce e spesso più accurato su KDA/gold/eventi
- Feed ON = il modello “vede” anche wave/posizione/minimap (più lento, serve `qwen2.5vl`)

## File

```
lol_coach.py    # UI Streamlit
live_game.py    # Live Client API + feed continuo
requirements.txt
```
