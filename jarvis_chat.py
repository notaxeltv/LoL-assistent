"""
Jarvis — Assistente vocale locale con Streamlit + Ollama (modello qwen).

Funzionalità:
- Chat con cronologia in sessione
- Streaming token-by-token da Ollama
- Input vocale (SpeechRecognition, it-IT)
- Output vocale (pyttsx3, voce italiana, rate ~170)

Avvio:
    streamlit run jarvis_chat.py
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
TTS_RATE = 170
PAGE_TITLE = "Jarvis — Assistente Vocale"
PAGE_ICON = "🎙️"


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
    # Linux e altri: espeak / espeak-ng
    return "espeak"


def _pick_italian_voice(engine: "pyttsx3.Engine") -> str | None:
    """
    Cerca una voce italiana tra quelle installate.
    Confronta id, name e languages (quando disponibili).
    """
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
        # Su alcune piattaforme `languages` è una lista di bytes/str
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
        # Match espliciti: italian / italiano / it-IT / it_IT, ecc.
        if any(k in haystack for k in keywords):
            return voice.id

    # Secondo passaggio più permissivo: codice lingua 'it' nell'id
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
            # Fallback al rilevamento automatico
            engine = pyttsx3.init()

        italian_voice = _pick_italian_voice(engine)
        if italian_voice:
            engine.setProperty("voice", italian_voice)
        else:
            # Non è un errore fatale: useremo la voce di default del sistema
            st.info(
                "Nessuna voce italiana trovata nel sistema. "
                "Uso la voce predefinita. Su Linux installa `espeak` / `espeak-ng` "
                "e le voci IT; su Windows/macOS abilita una voce italiana nelle "
                "impostazioni di accessibilità."
            )

        engine.setProperty("rate", TTS_RATE)
        # Volume pieno (0.0–1.0)
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

    Ritorna:
        (testo, errore)
        - testo: stringa riconosciuta, oppure None
        - errore: messaggio utente-friendly, oppure None se ok
    """
    if sr is None:
        return None, "SpeechRecognition non è installato."

    recognizer = sr.Recognizer()
    # Soglie ragionevoli per ambienti domestici
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.8

    try:
        with sr.Microphone() as source:
            # Adatta al rumore ambientale (breve, per non bloccare troppo la UI)
            recognizer.adjust_for_ambient_noise(source, duration=0.6)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=20)
    except sr.WaitTimeoutError:
        return None, "Nessun audio rilevato entro il timeout. Riprova."
    except OSError as exc:
        # Tipico se il microfono non è disponibile / PyAudio non configurato
        return (
            None,
            f"Impossibile accedere al microfono ({exc}). "
            "Verifica che PyAudio sia installato e che il microfono sia abilitato.",
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
        return None, "Non sono riuscito a capire l'audio. Parla più chiaramente e riprova."
    except sr.RequestError as exc:
        # recognize_google usa le API Google (serve connessione internet)
        return (
            None,
            f"Servizio di riconoscimento vocale non raggiungibile: {exc}. "
            "Controlla la connessione Internet.",
        )
    except Exception as exc:
        return None, f"Errore durante il riconoscimento vocale: {exc}"


# ---------------------------------------------------------------------------
# Ollama — chat con streaming
# ---------------------------------------------------------------------------
def stream_ollama_reply(messages: list[dict]) -> Generator[str, None, None]:
    """
    Invia la conversazione a Ollama (modello qwen) e yielda i token man mano.
    """
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
            # Formato tipico: {"message": {"role": "...", "content": "..."}, ...}
            content = ""
            if isinstance(chunk, dict):
                content = (chunk.get("message") or {}).get("content") or ""
            else:
                # Oggetti risposta della lib ufficiale
                message = getattr(chunk, "message", None)
                content = getattr(message, "content", "") if message else ""
            if content:
                yield content
    except Exception as exc:
        yield (
            f"⚠️ Errore nella comunicazione con Ollama: {exc}\n\n"
            "Verifica che Ollama sia in esecuzione (`ollama serve`) "
            f"e che il modello `{MODEL_NAME}` sia disponibile (`ollama list`)."
        )


def generate_assistant_reply(messages: list[dict]) -> str:
    """
    Mostra la risposta in streaming nella chat Streamlit e restituisce il testo completo.
    """
    placeholder = st.empty()
    full_response = ""

    with placeholder.container():
        stream_area = st.empty()
        for token in stream_ollama_reply(messages):
            full_response += token
            # Aggiorna a schermo mentre i token arrivano (niente TTS qui)
            stream_area.markdown(full_response)

    return full_response


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def init_session_state() -> None:
    """Inizializza lo stato della conversazione nella sessione Streamlit."""
    if "messages" not in st.session_state:
        st.session_state.messages: list[dict] = [
            {
                "role": "assistant",
                "content": (
                    "Ciao, sono Jarvis. Puoi scrivermi qui sotto oppure "
                    "premere **🎙️ Parla al Microfono**. "
                    "Risponderò con Qwen in locale e leggerò la risposta ad alta voce."
                ),
            }
        ]
    # Evita di rilanciare la TTS sulla stessa risposta a ogni rerun
    if "last_spoken_index" not in st.session_state:
        st.session_state.last_spoken_index = -1
    if "pending_voice_prompt" not in st.session_state:
        st.session_state.pending_voice_prompt = None


# ---------------------------------------------------------------------------
# UI Streamlit
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    """Pannello laterale con info e controlli."""
    with st.sidebar:
        st.header("Impostazioni")
        st.markdown(f"**Modello Ollama:** `{MODEL_NAME}`")
        st.markdown(f"**Lingua microfono:** `{SPEECH_LANG}`")
        st.markdown(f"**Velocità TTS:** `{TTS_RATE}`")
        st.markdown(f"**Sistema:** `{platform.system()} ({sys.platform})`")

        st.divider()
        tts_enabled = st.toggle("Sintesi vocale attiva", value=True)
        st.session_state.tts_enabled = tts_enabled

        if st.button("🗑️ Nuova conversazione", use_container_width=True):
            st.session_state.messages = [
                {
                    "role": "assistant",
                    "content": "Conversazione azzerata. Dimmi pure, ti ascolto.",
                }
            ]
            st.session_state.last_spoken_index = 0
            st.session_state.pending_voice_prompt = None
            st.rerun()

        st.divider()
        st.caption(
            "Requisiti: Ollama in esecuzione con il modello `qwen`, "
            "microfono abilitato e (per TTS) una voce italiana nel sistema."
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

    # Contesto completo per Ollama (escludiamo eventuali meta-messaggi se servisse)
    ollama_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
        if m["role"] in ("user", "assistant", "system")
    ]

    with st.chat_message("assistant"):
        with st.spinner("Qwen sta pensando..."):
            full_response = generate_assistant_reply(ollama_messages)

    st.session_state.messages.append({"role": "assistant", "content": full_response})

    # TTS: solo DOPO che l'intera risposta è a schermo
    if st.session_state.get("tts_enabled", True):
        # Evita di parlare messaggi di errore "tecnici" troppo lunghi se preferisci;
        # qui leggiamo comunque l'intera risposta generata, come richiesto.
        speak_text(full_response)
        st.session_state.last_spoken_index = len(st.session_state.messages) - 1


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="centered")
    init_session_state()

    st.title("🎙️ Jarvis")
    st.caption("Assistente vocale locale — Streamlit + Ollama (`qwen`) + SpeechRecognition + pyttsx3")

    render_sidebar()
    render_chat_history()

    # --- Pulsante microfono -------------------------------------------------
    mic_col, _ = st.columns([1, 2])
    with mic_col:
        mic_clicked = st.button("🎙️ Parla al Microfono", use_container_width=True)

    if mic_clicked:
        with st.spinner("Ti ascolto... parla pure (italiano)."):
            text, error = listen_from_microphone()
        if error:
            st.warning(error)
        elif text:
            st.success(f"Trascrizione: {text}")
            # Salviamo il prompt e facciamo rerun così la chat resta coerente
            st.session_state.pending_voice_prompt = text
            st.rerun()

    # Prompt vocale in coda (da turno precedente)
    if st.session_state.pending_voice_prompt:
        voice_prompt = st.session_state.pending_voice_prompt
        st.session_state.pending_voice_prompt = None
        handle_user_prompt(voice_prompt)
        # Dopo la gestione completa, Streamlit riprenderà dal basso con chat_input

    # --- Barra di testo classica -------------------------------------------
    typed = st.chat_input("Scrivi un messaggio a Jarvis...")
    if typed:
        handle_user_prompt(typed)


if __name__ == "__main__":
    main()
