"""
LoL Coach — Assistente vocale locale per League of Legends.

Parli al microfono mentre giochi; Qwen (Ollama) risponde in italiano
con consigli brevi e azionabili, poi pyttsx3 legge la risposta ad alta voce.

Avvio:
    streamlit run lol_coach.py
"""

from __future__ import annotations

import platform
import sys
from typing import Generator

import streamlit as st

# ---------------------------------------------------------------------------
# Dipendenze opzionali a runtime (messaggi chiari se mancano)
# ---------------------------------------------------------------------------
try:
    import ollama
except ImportError:  # pragma: no cover
    ollama = None  # type: ignore

try:
    import speech_recognition as sr
except ImportError:  # pragma: no cover
    sr = None  # type: ignore

try:
    import pyttsx3
except ImportError:  # pragma: no cover
    pyttsx3 = None  # type: ignore


# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------
MODEL_NAME = "qwen"
SPEECH_LANG = "it-IT"
TTS_RATE = 175  # leggermente più sostenuto: utile in partita
PAGE_TITLE = "LoL Coach — Assistente Vocale"
PAGE_ICON = "⚔️"

ROLES = ["Top", "Jungle", "Mid", "ADC", "Support", "Non specificato"]
RANKS = [
    "Non specificato",
    "Iron",
    "Bronze",
    "Silver",
    "Gold",
    "Platinum",
    "Emerald",
    "Diamond",
    "Master+",
]

SYSTEM_PROMPT_TEMPLATE = """Sei un coach vocale di League of Legends. L'utente ti parla al microfono DURANTE una partita e ha bisogno di aiuto immediato.

Contesto partita attuale:
- Ruolo: {role}
- Campione: {champion}
- Elo/Rank: {rank}
- Avversario / note: {enemy_notes}

Regole di risposta (obbligatorie):
1. Rispondi SEMPRE in italiano.
2. Sii BREVE e AZIONABILE: massimo 3-5 frasi corte (ideale ~20-40 secondi di lettura ad alta voce).
3. Dai priorità a: cosa fare ORA (farm, trade, roam, obiettivo, posizione, spell, item successivo).
4. Usa termini LoL comuni (CS, wave, spike, power spike, vision, invade, recall, ecc.) senza dilungarti.
5. Se mancano info critiche, fai UNA sola domanda breve, poi dai comunque il consiglio migliore possibile.
6. Non scrivere elenchi lunghi, markdown pesante o guide da wiki: parla come un coach in cuffia.
7. Non inventare patch note precise se non sei sicuro: dai principi solidi di macro/micro.
"""

WELCOME_MESSAGE = (
    "Pronto per la partita. Imposta **ruolo** e **campione** nella sidebar, "
    "poi premi **🎙️ Chiedi al Coach** e dimmi cosa sta succedendo "
    "(es. *«sono 2/4 vs Darius, pusha la wave, cosa faccio?»*)."
)


# ---------------------------------------------------------------------------
# Sintesi vocale (pyttsx3) — cross-platform
# ---------------------------------------------------------------------------
def _tts_driver_name() -> str | None:
    """Sceglie il driver pyttsx3 più adatto al sistema operativo."""
    system = platform.system()
    if system == "Windows":
        return "sapi5"
    if system == "Darwin":  # macOS
        return "nsss"
    return "espeak"


def _pick_italian_voice(engine: "pyttsx3.Engine") -> str | None:
    """Cerca una voce italiana tra quelle installate."""
    try:
        voices = engine.getProperty("voices") or []
    except Exception:
        return None

    keywords = ("italian", "italiano", "italy", "it-it", "it_it", "it_IT")

    for voice in voices:
        haystack_parts = [
            getattr(voice, "id", "") or "",
            getattr(voice, "name", "") or "",
        ]
        langs = getattr(voice, "languages", None) or []
        for lang in langs:
            if isinstance(lang, bytes):
                try:
                    haystack_parts.append(lang.decode("utf-8", errors="ignore"))
                except Exception:
                    haystack_parts.append(str(lang))
            else:
                haystack_parts.append(str(lang))

        haystack = " ".join(haystack_parts).lower()
        if any(k in haystack for k in keywords):
            return voice.id

    for voice in voices:
        vid = (getattr(voice, "id", "") or "").lower()
        vname = (getattr(voice, "name", "") or "").lower()
        if (
            "/it" in vid
            or vid.endswith("-it")
            or "it-it" in vid
            or "it_it" in vid
            or vname.startswith("it ")
            or "italian" in vname
            or "italiano" in vname
        ):
            return voice.id

    return None


def speak_text(text: str) -> None:
    """
    Legge ad alta voce `text` con pyttsx3.
    Va chiamata SOLO dopo che lo streaming della risposta è terminato.
    """
    if not text or not text.strip():
        return
    if pyttsx3 is None:
        st.warning("pyttsx3 non è installato: sintesi vocale non disponibile.")
        return

    engine = None
    try:
        driver = _tts_driver_name()
        try:
            engine = pyttsx3.init(driverName=driver) if driver else pyttsx3.init()
        except Exception:
            engine = pyttsx3.init()

        italian_voice = _pick_italian_voice(engine)
        if italian_voice:
            engine.setProperty("voice", italian_voice)
        else:
            st.info(
                "Nessuna voce italiana trovata. Uso la voce predefinita. "
                "Su Windows/macOS abilita una voce IT; su Linux installa espeak-ng."
            )

        engine.setProperty("rate", TTS_RATE)
        try:
            engine.setProperty("volume", 1.0)
        except Exception:
            pass

        engine.say(text)
        engine.runAndWait()
    except Exception as exc:  # pragma: no cover
        st.warning(f"Errore durante la sintesi vocale: {exc}")
    finally:
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Riconoscimento vocale (SpeechRecognition) — cross-platform
# ---------------------------------------------------------------------------
def listen_from_microphone() -> tuple[str | None, str | None]:
    """
    Attiva il microfono, ascolta e trascrive in italiano (it-IT).

    Ritorna (testo, errore).
    """
    if sr is None:
        return None, "SpeechRecognition non è installato."

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    # In partita si parla spesso in fretta: pause un filo più corte
    recognizer.pause_threshold = 0.7

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=18)
    except sr.WaitTimeoutError:
        return None, "Nessun audio rilevato. Riprova (tieni premuto / parla subito dopo il click)."
    except OSError as exc:
        return (
            None,
            f"Impossibile accedere al microfono ({exc}). "
            "Verifica PyAudio e che il microfono non sia esclusivo di LoL/Discord.",
        )
    except Exception as exc:
        return None, f"Errore durante l'ascolto dal microfono: {exc}"

    try:
        text = recognizer.recognize_google(audio, language=SPEECH_LANG)
        text = (text or "").strip()
        if not text:
            return None, "Audio ricevuto ma trascrizione vuota."
        return text, None
    except sr.UnknownValueError:
        return None, "Non ho capito l'audio (rumore di game/Discord?). Riprova parlando chiaro."
    except sr.RequestError as exc:
        return (
            None,
            f"Riconoscimento vocale non raggiungibile: {exc}. Serve Internet per la trascrizione.",
        )
    except Exception as exc:
        return None, f"Errore durante il riconoscimento vocale: {exc}"


# ---------------------------------------------------------------------------
# Contesto partita + Ollama
# ---------------------------------------------------------------------------
def build_system_prompt() -> str:
    """Costruisce il system prompt con i dati partita della sidebar."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        role=st.session_state.get("match_role", "Non specificato"),
        champion=(st.session_state.get("match_champion") or "Non specificato").strip()
        or "Non specificato",
        rank=st.session_state.get("match_rank", "Non specificato"),
        enemy_notes=(st.session_state.get("match_enemy_notes") or "Nessuna").strip()
        or "Nessuna",
    )


def stream_ollama_reply(messages: list[dict]) -> Generator[str, None, None]:
    """Invia la conversazione a Ollama (qwen) e yielda i token."""
    if ollama is None:
        yield "⚠️ La libreria `ollama` non è installata. Esegui: pip install ollama"
        return

    try:
        stream = ollama.chat(
            model=MODEL_NAME,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            content = ""
            if isinstance(chunk, dict):
                content = (chunk.get("message") or {}).get("content") or ""
            else:
                message = getattr(chunk, "message", None)
                content = getattr(message, "content", "") if message else ""
            if content:
                yield content
    except Exception as exc:
        yield (
            f"⚠️ Errore Ollama: {exc}\n\n"
            "Verifica che Ollama sia attivo e che il modello "
            f"`{MODEL_NAME}` sia disponibile (`ollama list`)."
        )


def generate_assistant_reply(messages: list[dict]) -> str:
    """Mostra la risposta in streaming e restituisce il testo completo."""
    placeholder = st.empty()
    full_response = ""

    with placeholder.container():
        stream_area = st.empty()
        for token in stream_ollama_reply(messages):
            full_response += token
            stream_area.markdown(full_response)

    return full_response


def messages_for_ollama() -> list[dict]:
    """
    Cronologia chat + system prompt aggiornato al contesto partita corrente.
    Il system message non viene mostrato in UI, solo inviato a Ollama.
    """
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
        if m["role"] in ("user", "assistant")
    ]
    return [{"role": "system", "content": build_system_prompt()}, *history]


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def init_session_state() -> None:
    """Inizializza stato conversazione e contesto partita."""
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": WELCOME_MESSAGE},
        ]
    if "last_spoken_index" not in st.session_state:
        st.session_state.last_spoken_index = -1
    if "pending_voice_prompt" not in st.session_state:
        st.session_state.pending_voice_prompt = None
    if "match_role" not in st.session_state:
        st.session_state.match_role = "Non specificato"
    if "match_champion" not in st.session_state:
        st.session_state.match_champion = ""
    if "match_rank" not in st.session_state:
        st.session_state.match_rank = "Non specificato"
    if "match_enemy_notes" not in st.session_state:
        st.session_state.match_enemy_notes = ""
    if "tts_enabled" not in st.session_state:
        st.session_state.tts_enabled = True


# ---------------------------------------------------------------------------
# UI Streamlit
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    """Sidebar: contesto partita + controlli audio."""
    with st.sidebar:
        st.header("Contesto partita")
        st.caption("Compila prima del loadout: il coach userà questi dati.")

        st.session_state.match_role = st.selectbox(
            "Ruolo",
            ROLES,
            index=ROLES.index(st.session_state.match_role)
            if st.session_state.match_role in ROLES
            else len(ROLES) - 1,
        )
        st.session_state.match_champion = st.text_input(
            "Il tuo campione",
            value=st.session_state.match_champion,
            placeholder="es. Jax, Lux, Jinx...",
        )
        st.session_state.match_rank = st.selectbox(
            "Elo / Rank",
            RANKS,
            index=RANKS.index(st.session_state.match_rank)
            if st.session_state.match_rank in RANKS
            else 0,
        )
        st.session_state.match_enemy_notes = st.text_area(
            "Avversario / note rapide",
            value=st.session_state.match_enemy_notes,
            placeholder="es. vs Darius, no flash, dragon spawn 1:20",
            height=80,
        )

        st.divider()
        st.subheader("Audio")
        st.session_state.tts_enabled = st.toggle(
            "Sintesi vocale attiva",
            value=st.session_state.tts_enabled,
        )
        st.caption(f"Modello: `{MODEL_NAME}` · Mic: `{SPEECH_LANG}` · TTS rate: `{TTS_RATE}`")
        st.caption(f"OS: `{platform.system()} ({sys.platform})`")

        if st.button("🗑️ Nuova conversazione", use_container_width=True):
            st.session_state.messages = [
                {
                    "role": "assistant",
                    "content": (
                        "Chat azzerata. Contesto partita invariato. "
                        "Dimmi pure cosa sta succedendo in game."
                    ),
                }
            ]
            st.session_state.last_spoken_index = 0
            st.session_state.pending_voice_prompt = None
            st.rerun()

        st.divider()
        st.markdown(
            "**Suggerimento in-game:** tieni questa finestra su un secondo "
            "monitor (o Alt-Tab), clicca il microfono e parla. "
            "Esempi: *«posso all-in?»*, *«cosa buildo contro tanks?»*, "
            "*«roto mid, vado dragon?»*."
        )


def render_chat_history() -> None:
    """Disegna la cronologia User / Assistant."""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def handle_user_prompt(prompt: str) -> None:
    """
    Aggiunge il messaggio utente, genera la risposta in streaming,
    poi (se abilitato) attiva la TTS solo a generazione completata.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Il coach sta pensando..."):
            full_response = generate_assistant_reply(messages_for_ollama())

    st.session_state.messages.append({"role": "assistant", "content": full_response})

    # TTS solo DOPO che la risposta è completa a schermo
    if st.session_state.get("tts_enabled", True):
        speak_text(full_response)
        st.session_state.last_spoken_index = len(st.session_state.messages) - 1


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="centered")
    init_session_state()

    st.title("⚔️ LoL Coach")
    st.caption(
        "Assistente vocale locale per League of Legends — "
        "chiedi al microfono cosa fare in partita (Ollama `qwen`)."
    )

    render_sidebar()
    render_chat_history()

    # --- Pulsante microfono (uso principale in-game) -----------------------
    mic_col, tip_col = st.columns([1, 2])
    with mic_col:
        mic_clicked = st.button("🎙️ Chiedi al Coach", use_container_width=True, type="primary")
    with tip_col:
        st.caption("Clic → parla in italiano → la domanda va a Qwen → risposta letta ad alta voce.")

    if mic_clicked:
        with st.spinner("Ti ascolto... descrivi la situazione in game."):
            text, error = listen_from_microphone()
        if error:
            st.warning(error)
        elif text:
            st.success(f"Hai detto: {text}")
            st.session_state.pending_voice_prompt = text
            st.rerun()

    if st.session_state.pending_voice_prompt:
        voice_prompt = st.session_state.pending_voice_prompt
        st.session_state.pending_voice_prompt = None
        handle_user_prompt(voice_prompt)

    # --- Input testuale di backup ------------------------------------------
    typed = st.chat_input("Oppure scrivi qui (es. «vs Zed 0/2, pusha, cosa faccio?»)...")
    if typed:
        handle_user_prompt(typed)


if __name__ == "__main__":
    main()
