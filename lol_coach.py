"""
LoL Coach — Assistente vocale (+ visione schermo) per League of Legends.

- Microfono → domanda in italiano
- Screenshot dello schermo → modello vision Ollama (opzionale)
- Risposte brevi in streaming, TTS che parte già dalla prima frase

Avvio:
    streamlit run lol_coach.py
"""

from __future__ import annotations

import io
import platform
import re
import sys
from typing import Generator

import streamlit as st

# ---------------------------------------------------------------------------
# Dipendenze opzionali a runtime
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

try:
    import mss
    from PIL import Image
except ImportError:  # pragma: no cover
    mss = None  # type: ignore
    Image = None  # type: ignore


# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------
DEFAULT_TEXT_MODEL = "qwen"
DEFAULT_VISION_MODEL = "qwen2.5vl"  # richiede: ollama pull qwen2.5vl
SPEECH_LANG = "it-IT"
TTS_RATE_NORMAL = 175
TTS_RATE_FAST = 200
PAGE_TITLE = "LoL Coach — Assistente Vocale"
PAGE_ICON = "⚔️"

# Limiti generazione: meno token = risposta più veloce in partita
NUM_PREDICT_NORMAL = 160
NUM_PREDICT_FAST = 80

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

SYSTEM_PROMPT_TEMPLATE = """Sei un coach vocale di League of Legends. L'utente ti parla DURANTE una partita.

Contesto:
- Ruolo: {role}
- Campione: {champion}
- Elo/Rank: {rank}
- Avversario / note: {enemy_notes}
- Visione schermo: {vision_mode}
- Modalità: {speed_mode}

Regole:
1. Rispondi SEMPRE in italiano, come un coach in cuffia.
2. {brevity_rule}
3. Priorità: cosa fare ORA (trade, farm, obiettivo, posizione, summoner, item).
4. Se c'è uno screenshot, usalo: mini-map, HP/mana, wave, ultimates, obiettivi, gold/items visibili. Non descrivere lo schermo: dai il consiglio.
5. Niente markdown pesante, niente guide lunghe. Massimo UNA domanda breve se serve.
"""

WELCOME_MESSAGE = (
    "Pronto. Imposta **ruolo/campione** nella sidebar. "
    "Attiva **Vedi lo schermo** se hai un modello vision (`qwen2.5vl` / `llava`), "
    "poi **🎙️ Chiedi al Coach**: ascolto + (opzionale) screenshot → consiglio vocale rapido."
)


# ---------------------------------------------------------------------------
# Helper velocità / modelli
# ---------------------------------------------------------------------------
def is_fast_mode() -> bool:
    return bool(st.session_state.get("fast_mode", True))


def active_tts_rate() -> int:
    return TTS_RATE_FAST if is_fast_mode() else TTS_RATE_NORMAL


def active_num_predict() -> int:
    return NUM_PREDICT_FAST if is_fast_mode() else NUM_PREDICT_NORMAL


def active_model_name() -> str:
    if st.session_state.get("screen_vision", True):
        return (st.session_state.get("vision_model") or DEFAULT_VISION_MODEL).strip()
    return (st.session_state.get("text_model") or DEFAULT_TEXT_MODEL).strip()


# ---------------------------------------------------------------------------
# Sintesi vocale (pyttsx3)
# ---------------------------------------------------------------------------
def _tts_driver_name() -> str | None:
    system = platform.system()
    if system == "Windows":
        return "sapi5"
    if system == "Darwin":
        return "nsss"
    return "espeak"


def _pick_italian_voice(engine: "pyttsx3.Engine") -> str | None:
    try:
        voices = engine.getProperty("voices") or []
    except Exception:
        return None

    keywords = ("italian", "italiano", "italy", "it-it", "it_it", "it_IT")
    for voice in voices:
        parts = [getattr(voice, "id", "") or "", getattr(voice, "name", "") or ""]
        for lang in getattr(voice, "languages", None) or []:
            if isinstance(lang, bytes):
                try:
                    parts.append(lang.decode("utf-8", errors="ignore"))
                except Exception:
                    parts.append(str(lang))
            else:
                parts.append(str(lang))
        haystack = " ".join(parts).lower()
        if any(k in haystack for k in keywords):
            return voice.id

    for voice in voices:
        vid = (getattr(voice, "id", "") or "").lower()
        vname = (getattr(voice, "name", "") or "").lower()
        if (
            "/it" in vid
            or "it-it" in vid
            or "it_it" in vid
            or "italian" in vname
            or "italiano" in vname
        ):
            return voice.id
    return None


def speak_text(text: str, *, show_missing_voice_info: bool = False) -> None:
    """Legge `text` ad alta voce. Preferire frasi corte per bassissima latenza percepita."""
    if not text or not text.strip():
        return
    if pyttsx3 is None:
        st.warning("pyttsx3 non installato: TTS non disponibile.")
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
        elif show_missing_voice_info:
            st.info("Nessuna voce italiana trovata: uso quella predefinita.")

        engine.setProperty("rate", active_tts_rate())
        try:
            engine.setProperty("volume", 1.0)
        except Exception:
            pass

        engine.say(text.strip())
        engine.runAndWait()
    except Exception as exc:  # pragma: no cover
        st.warning(f"Errore TTS: {exc}")
    finally:
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Microfono
# ---------------------------------------------------------------------------
def listen_from_microphone() -> tuple[str | None, str | None]:
    """Ascolta e trascrive in it-IT. In modalità rapida riduce i tempi di calibrazione."""
    if sr is None:
        return None, "SpeechRecognition non è installato."

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    fast = is_fast_mode()
    recognizer.pause_threshold = 0.55 if fast else 0.7
    ambient = 0.25 if fast else 0.45
    phrase_limit = 12 if fast else 18

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=ambient)
            audio = recognizer.listen(source, timeout=4, phrase_time_limit=phrase_limit)
    except sr.WaitTimeoutError:
        return None, "Nessun audio rilevato. Riprova parlando subito dopo il click."
    except OSError as exc:
        return (
            None,
            f"Microfono non accessibile ({exc}). Controlla PyAudio / esclusive LoL-Discord.",
        )
    except Exception as exc:
        return None, f"Errore microfono: {exc}"

    try:
        text = (recognizer.recognize_google(audio, language=SPEECH_LANG) or "").strip()
        if not text:
            return None, "Trascrizione vuota."
        return text, None
    except sr.UnknownValueError:
        return None, "Audio non chiaro (game/Discord?). Riprova."
    except sr.RequestError as exc:
        return None, f"Riconoscimento non raggiungibile (serve Internet): {exc}"
    except Exception as exc:
        return None, f"Errore riconoscimento: {exc}"


# ---------------------------------------------------------------------------
# Screenshot (visione schermo)
# ---------------------------------------------------------------------------
def list_monitors() -> list[tuple[int, str]]:
    """Elenco monitor mss: indice -> etichetta leggibile."""
    if mss is None:
        return [(1, "Monitor 1 (installa mss + Pillow)")]
    try:
        labels: list[tuple[int, str]] = []
        with mss.mss() as sct:
            # monitors[0] = virtual desktop completo; 1..n = singoli display
            for idx, mon in enumerate(sct.monitors):
                if idx == 0:
                    labels.append((0, f"Tutti i monitor ({mon['width']}x{mon['height']})"))
                else:
                    labels.append(
                        (
                            idx,
                            f"Monitor {idx} ({mon['width']}x{mon['height']} "
                            f"@ {mon['left']},{mon['top']})",
                        )
                    )
        return labels or [(1, "Monitor 1")]
    except Exception as exc:
        # Tipico in ambienti headless/CI; sul PC di gioco mss funziona di solito
        return [(1, f"Monitor 1 (rilevamento fallito: {exc})")]


def _resize_for_vision(img: "Image.Image", max_width: int) -> "Image.Image":
    """Ridimensiona lo screenshot per ridurre latenza verso Ollama."""
    if img.width > max_width:
        ratio = max_width / float(img.width)
        img = img.resize((max_width, max(1, int(img.height * ratio))), Image.Resampling.BILINEAR)
    return img


def _image_to_png_bytes(img: "Image.Image") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def capture_screen_png(
    monitor_index: int = 1,
    max_width: int = 1280,
) -> tuple[bytes | None, str | None]:
    """
    Cattura uno screenshot PNG (ridimensionato per velocità verso Ollama).

    Prova prima `mss` (multi-monitor), poi fallback `PIL.ImageGrab` (Win/macOS).
    Ritorna (png_bytes, errore).
    """
    if Image is None:
        return None, "Installa le dipendenze visione: pip install mss Pillow"

    errors: list[str] = []

    # 1) mss — migliore per scegliere il monitor del gioco
    if mss is not None:
        try:
            with mss.mss() as sct:
                monitors = sct.monitors
                if monitor_index < 0 or monitor_index >= len(monitors):
                    monitor_index = 1 if len(monitors) > 1 else 0
                raw = sct.grab(monitors[monitor_index])
                img = Image.frombytes("RGB", raw.size, raw.rgb)
            img = _resize_for_vision(img, max_width)
            return _image_to_png_bytes(img), None
        except Exception as exc:
            errors.append(f"mss: {exc}")

    # 2) ImageGrab — fallback tipico su Windows/macOS
    try:
        from PIL import ImageGrab

        grabbed = ImageGrab.grab(all_screens=(monitor_index == 0))
        if grabbed.mode != "RGB":
            grabbed = grabbed.convert("RGB")
        grabbed = _resize_for_vision(grabbed, max_width)
        return _image_to_png_bytes(grabbed), None
    except Exception as exc:
        errors.append(f"ImageGrab: {exc}")

    detail = " | ".join(errors) if errors else "nessun backend disponibile"
    return (
        None,
        f"Screenshot fallito ({detail}). Su LoL usa *borderless windowed* "
        "se il fullscreen esclusivo blocca la cattura. Dipendenze: pip install mss Pillow",
    )


# ---------------------------------------------------------------------------
# Prompt + Ollama
# ---------------------------------------------------------------------------
def build_system_prompt() -> str:
    vision_on = bool(st.session_state.get("screen_vision", True))
    fast = is_fast_mode()
    brevity = (
        "Massimo 2 frasi corte (~10-20 secondi di voce)."
        if fast
        else "Massimo 3-5 frasi corte (~20-40 secondi di voce)."
    )
    return SYSTEM_PROMPT_TEMPLATE.format(
        role=st.session_state.get("match_role", "Non specificato"),
        champion=(st.session_state.get("match_champion") or "Non specificato").strip()
        or "Non specificato",
        rank=st.session_state.get("match_rank", "Non specificato"),
        enemy_notes=(st.session_state.get("match_enemy_notes") or "Nessuna").strip()
        or "Nessuna",
        vision_mode="ATTIVA (analizza lo screenshot allegato)" if vision_on else "spenta",
        speed_mode="RAPIDA" if fast else "normale",
        brevity_rule=brevity,
    )


def stream_ollama_reply(messages: list[dict]) -> Generator[str, None, None]:
    """Streaming da Ollama con limite token per velocità."""
    if ollama is None:
        yield "⚠️ Installa ollama: `pip install ollama`"
        return

    model = active_model_name()
    try:
        stream = ollama.chat(
            model=model,
            messages=messages,
            stream=True,
            options={
                "num_predict": active_num_predict(),
                "temperature": 0.4,
            },
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
            f"⚠️ Errore Ollama (`{model}`): {exc}\n\n"
            "Se usi la visione schermo: `ollama pull qwen2.5vl` "
            "(oppure `llava` / `llama3.2-vision`) e selezionalo in sidebar."
        )


_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def _split_complete_sentences(buffer: str) -> tuple[list[str], str]:
    """Separa frasi complete dall'eventuale coda ancora incompleta."""
    parts = _SENTENCE_END.split(buffer)
    if len(parts) == 1:
        return [], buffer
    complete = [p.strip() for p in parts[:-1] if p.strip()]
    return complete, parts[-1]


def generate_assistant_reply(
    messages: list[dict],
    *,
    speak_early: bool,
) -> str:
    """
    Streaming a schermo. Se speak_early=True, la TTS parte alla prima frase
    completa (comunicazione più reattiva in partita), poi continua col resto.
    """
    stream_area = st.empty()
    full_response = ""
    pending_speech = ""

    for token in stream_ollama_reply(messages):
        full_response += token
        stream_area.markdown(full_response)

        if speak_early and st.session_state.get("tts_enabled", True):
            pending_speech += token
            sentences, pending_speech = _split_complete_sentences(pending_speech)
            for sentence in sentences:
                speak_text(sentence)

    if speak_early and st.session_state.get("tts_enabled", True):
        rest = pending_speech.strip()
        if rest:
            speak_text(rest)
    return full_response


def build_ollama_messages(user_text: str, image_png: bytes | None) -> list[dict]:
    """
    System + cronologia testuale + ultimo user message (con eventuale immagine).
    Le immagini passate non vengono tenute in session_state per non gonfiare la RAM.
    """
    history: list[dict] = []
    for m in st.session_state.messages:
        if m["role"] not in ("user", "assistant"):
            continue
        # Solo testo in cronologia (niente vecchie immagini)
        history.append({"role": m["role"], "content": m["content"]})

    # L'ultimo user è già in history: lo sostituiamo con versione + image se serve
    if history and history[-1]["role"] == "user":
        history.pop()

    user_msg: dict = {"role": "user", "content": user_text}
    if image_png:
        # API ollama-python: lista di bytes o path
        user_msg["images"] = [image_png]

    return [
        {"role": "system", "content": build_system_prompt()},
        *history,
        user_msg,
    ]


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def init_session_state() -> None:
    defaults = {
        "messages": [{"role": "assistant", "content": WELCOME_MESSAGE}],
        "last_spoken_index": -1,
        "pending_voice_prompt": None,
        "pending_image_png": None,
        "match_role": "Non specificato",
        "match_champion": "",
        "match_rank": "Non specificato",
        "match_enemy_notes": "",
        "tts_enabled": True,
        "fast_mode": True,
        "screen_vision": True,
        "text_model": DEFAULT_TEXT_MODEL,
        "vision_model": DEFAULT_VISION_MODEL,
        "monitor_index": 1,
        "show_screenshot_preview": True,
        "early_tts": True,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    with st.sidebar:
        st.header("Contesto partita")
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
            placeholder="es. vs Darius, no flash",
            height=70,
        )

        st.divider()
        st.subheader("👁️ Visione schermo")
        st.session_state.screen_vision = st.toggle(
            "Vedi lo schermo (screenshot → AI)",
            value=st.session_state.screen_vision,
            help="Serve un modello vision in Ollama, es. qwen2.5vl o llava.",
        )
        monitors = list_monitors()
        labels = [label for _, label in monitors]
        indices = [idx for idx, _ in monitors]
        try:
            current = indices.index(st.session_state.monitor_index)
        except ValueError:
            current = min(1, len(indices) - 1)
        chosen = st.selectbox("Monitor da catturare", labels, index=current)
        st.session_state.monitor_index = indices[labels.index(chosen)]
        st.session_state.show_screenshot_preview = st.toggle(
            "Anteprima screenshot in chat",
            value=st.session_state.show_screenshot_preview,
        )
        st.session_state.vision_model = st.text_input(
            "Modello vision Ollama",
            value=st.session_state.vision_model,
        )
        st.caption("Esempio setup: `ollama pull qwen2.5vl`")

        st.divider()
        st.subheader("⚡ Velocità")
        st.session_state.fast_mode = st.toggle(
            "Modalità rapida (consigliata in-game)",
            value=st.session_state.fast_mode,
            help="Risposte più corte, mic più reattivo, TTS più veloce, meno token.",
        )
        st.session_state.early_tts = st.toggle(
            "TTS dalla prima frase (non aspettare tutta la risposta)",
            value=st.session_state.early_tts,
        )
        st.session_state.tts_enabled = st.toggle(
            "Sintesi vocale attiva",
            value=st.session_state.tts_enabled,
        )
        st.session_state.text_model = st.text_input(
            "Modello testo (se visione OFF)",
            value=st.session_state.text_model,
        )

        st.caption(
            f"Modello attivo: `{active_model_name()}` · "
            f"max token: `{active_num_predict()}` · "
            f"TTS rate: `{active_tts_rate()}`"
        )
        st.caption(f"OS: `{platform.system()} ({sys.platform})`")

        if st.button("🗑️ Nuova conversazione", use_container_width=True):
            st.session_state.messages = [
                {
                    "role": "assistant",
                    "content": "Chat azzerata. Contesto partita invariato. Dimmi pure.",
                }
            ]
            st.session_state.pending_voice_prompt = None
            st.session_state.pending_image_png = None
            st.rerun()

        st.divider()
        st.markdown(
            "**In partita:** LoL preferibilmente in *borderless*, "
            "app su secondo monitor. Clicca il microfono e parla: "
            "con visione ON viene allegato lo screenshot del monitor scelto."
        )


def render_chat_history() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("image_png") and st.session_state.get("show_screenshot_preview", True):
                st.image(message["image_png"], caption="Screenshot analizzato", use_container_width=True)
            st.markdown(message["content"])


def handle_user_prompt(prompt: str, image_png: bytes | None = None) -> None:
    prompt = (prompt or "").strip()
    if not prompt:
        return

    # Se visione attiva e nessuna immagine passata, cattura ora
    capture_error = None
    if st.session_state.get("screen_vision", True) and image_png is None:
        with st.spinner("Catturo lo schermo..."):
            image_png, capture_error = capture_screen_png(
                monitor_index=int(st.session_state.get("monitor_index", 1)),
            )
        if capture_error:
            st.warning(capture_error)

    user_entry: dict = {"role": "user", "content": prompt}
    if image_png and st.session_state.get("show_screenshot_preview", True):
        user_entry["image_png"] = image_png

    st.session_state.messages.append(user_entry)
    with st.chat_message("user"):
        if image_png and st.session_state.get("show_screenshot_preview", True):
            st.image(image_png, caption="Screenshot analizzato", use_container_width=True)
        st.markdown(prompt)

    ollama_messages = build_ollama_messages(prompt, image_png)
    speak_early = bool(st.session_state.get("early_tts", True)) and bool(
        st.session_state.get("tts_enabled", True)
    )

    with st.chat_message("assistant"):
        with st.spinner("Il coach guarda la situation..." if image_png else "Il coach sta pensando..."):
            full_response = generate_assistant_reply(
                ollama_messages,
                speak_early=speak_early,
            )

    st.session_state.messages.append({"role": "assistant", "content": full_response})

    # Se early TTS è off, parla tutto a fine generazione (comportamento classico)
    if st.session_state.get("tts_enabled", True) and not speak_early:
        speak_text(full_response, show_missing_voice_info=True)

    st.session_state.last_spoken_index = len(st.session_state.messages) - 1


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="centered")
    init_session_state()

    st.title("⚔️ LoL Coach")
    st.caption(
        "Coach vocale locale con visione schermo — microfono + screenshot → "
        f"Ollama (`{active_model_name()}`)."
    )

    render_sidebar()
    render_chat_history()

    c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
    with c1:
        mic_clicked = st.button("🎙️ Chiedi al Coach", use_container_width=True, type="primary")
    with c2:
        shot_clicked = st.button("📸 Solo schermo", use_container_width=True)
    with c3:
        st.caption("Mic = voce (+ screenshot se visione ON). Solo schermo = «cosa faccio ora?» sullo screenshot.")

    if mic_clicked:
        image_png = None
        # Screenshot PRIMA del mic: cattura il frame di gioco, non la UI mentre parli
        if st.session_state.get("screen_vision", True):
            with st.spinner("Screenshot..."):
                image_png, err = capture_screen_png(
                    monitor_index=int(st.session_state.get("monitor_index", 1)),
                )
            if err:
                st.warning(err)

        with st.spinner("Ti ascolto..."):
            text, error = listen_from_microphone()
        if error:
            st.warning(error)
        elif text:
            st.success(f"Hai detto: {text}")
            st.session_state.pending_voice_prompt = text
            st.session_state.pending_image_png = image_png
            st.rerun()

    if shot_clicked:
        if not st.session_state.get("screen_vision", True):
            st.warning("Attiva «Vedi lo schermo» in sidebar per usare questo pulsante.")
        else:
            with st.spinner("Screenshot..."):
                image_png, err = capture_screen_png(
                    monitor_index=int(st.session_state.get("monitor_index", 1)),
                )
            if err:
                st.warning(err)
            else:
                st.session_state.pending_voice_prompt = (
                    "Guarda lo screenshot della mia partita di League of Legends: "
                    "cosa dovrei fare ora? Risposta brevissima."
                )
                st.session_state.pending_image_png = image_png
                st.rerun()

    if st.session_state.pending_voice_prompt:
        voice_prompt = st.session_state.pending_voice_prompt
        image_png = st.session_state.pending_image_png
        st.session_state.pending_voice_prompt = None
        st.session_state.pending_image_png = None
        handle_user_prompt(voice_prompt, image_png=image_png)

    typed = st.chat_input("Scrivi qui (con visione ON allega comunque lo screenshot)...")
    if typed:
        handle_user_prompt(typed)


if __name__ == "__main__":
    main()
