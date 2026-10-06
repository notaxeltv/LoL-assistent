"""
LoL Coach — assistente vocale con visione DELLA PARTITA IN TEMPO REALE.

Fonte principale (default): feed schermo continuo — nessuna API key Riot.
Extra opzionale: Live Client locale su 127.0.0.1:2999 (niente developer portal).

Avvio:
    streamlit run lol_coach.py
"""

from __future__ import annotations

import platform
import re
import sys
from typing import Generator

import streamlit as st

from live_game import LIVE_FEED, get_live_game_briefing

# ---------------------------------------------------------------------------
# Dipendenze opzionali
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
DEFAULT_VISION_MODEL = "qwen2.5vl"
SPEECH_LANG = "it-IT"
TTS_RATE_NORMAL = 175
TTS_RATE_FAST = 200
PAGE_TITLE = "LoL Coach — Tempo Reale"
PAGE_ICON = "⚔️"
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

SYSTEM_PROMPT_TEMPLATE = """Sei un coach vocale di League of Legends in TEMPO REALE.

Contesto utente:
- Ruolo: {role}
- Campione dichiarato: {champion}
- Elo/Rank: {rank}
- Note: {enemy_notes}
- Fonti live: {live_sources}
- Modalità: {speed_mode}

Regole:
1. Rispondi SEMPRE in italiano, da coach in cuffia.
2. {brevity_rule}
3. Usa i dati LIVE CLIENT (scoreboard, gold, eventi, HP) come verità sulla partita: sono aggiornati in tempo reale.
4. Se ci sono frame recenti del feed video, usali per posizione/wave/obiettivi visibili — non descrivere i frame, dai il consiglio.
5. Priorità: cosa fare ORA. Niente guide lunghe, niente markdown pesante.
"""

WELCOME_MESSAGE = (
    "Modalità **tempo reale** via **feed schermo continuo** (nessuna API Riot da registrare). "
    "Scegli il monitor di LoL nella sidebar, lascia il feed attivo, poi "
    "**🎙️ Chiedi al Coach**: usa gli ultimi frame della partita. "
    "Opzionale: la Live Client locale (senza API key) se vuoi anche gold/KDA strutturati."
)


# ---------------------------------------------------------------------------
# Monitor helper (UI)
# ---------------------------------------------------------------------------
def list_monitors() -> list[tuple[int, str]]:
    if mss is None:
        return [(1, "Monitor 1 (installa mss + Pillow)")]
    try:
        labels: list[tuple[int, str]] = []
        with mss.mss() as sct:
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
        return [(1, f"Monitor 1 (rilevamento fallito: {exc})")]


# ---------------------------------------------------------------------------
# Velocità / modello
# ---------------------------------------------------------------------------
def is_fast_mode() -> bool:
    return bool(st.session_state.get("fast_mode", True))


def active_tts_rate() -> int:
    return TTS_RATE_FAST if is_fast_mode() else TTS_RATE_NORMAL


def active_num_predict() -> int:
    return NUM_PREDICT_FAST if is_fast_mode() else NUM_PREDICT_NORMAL


def uses_vision_frames() -> bool:
    return bool(st.session_state.get("live_screen_feed", True))


def active_model_name() -> str:
    if uses_vision_frames():
        return (st.session_state.get("vision_model") or DEFAULT_VISION_MODEL).strip()
    return (st.session_state.get("text_model") or DEFAULT_TEXT_MODEL).strip()


def sync_live_feed() -> None:
    """Avvia/ferma/configura il thread di cattura continua in base alla sidebar."""
    want = bool(st.session_state.get("live_screen_feed", True))
    LIVE_FEED.configure(
        monitor_index=int(st.session_state.get("monitor_index", 1)),
        fps=float(st.session_state.get("live_fps", 2.0)),
        max_width=960,
    )
    if want and not LIVE_FEED.running:
        LIVE_FEED.start()
    elif not want and LIVE_FEED.running:
        LIVE_FEED.stop()


# ---------------------------------------------------------------------------
# TTS
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
        if any(k in " ".join(parts).lower() for k in keywords):
            return voice.id
    return None


def speak_text(text: str, *, show_missing_voice_info: bool = False) -> None:
    if not text or not text.strip():
        return
    if pyttsx3 is None:
        st.warning("pyttsx3 non installato.")
        return
    engine = None
    try:
        driver = _tts_driver_name()
        try:
            engine = pyttsx3.init(driverName=driver) if driver else pyttsx3.init()
        except Exception:
            engine = pyttsx3.init()
        voice = _pick_italian_voice(engine)
        if voice:
            engine.setProperty("voice", voice)
        elif show_missing_voice_info:
            st.info("Nessuna voce italiana: uso quella predefinita.")
        engine.setProperty("rate", active_tts_rate())
        try:
            engine.setProperty("volume", 1.0)
        except Exception:
            pass
        engine.say(text.strip())
        engine.runAndWait()
    except Exception as exc:
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
    if sr is None:
        return None, "SpeechRecognition non installato."
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    fast = is_fast_mode()
    recognizer.pause_threshold = 0.55 if fast else 0.7
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.25 if fast else 0.45)
            audio = recognizer.listen(source, timeout=4, phrase_time_limit=12 if fast else 18)
    except sr.WaitTimeoutError:
        return None, "Nessun audio rilevato."
    except OSError as exc:
        return None, f"Microfono non accessibile: {exc}"
    except Exception as exc:
        return None, f"Errore microfono: {exc}"
    try:
        text = (recognizer.recognize_google(audio, language=SPEECH_LANG) or "").strip()
        return (text, None) if text else (None, "Trascrizione vuota.")
    except sr.UnknownValueError:
        return None, "Audio non chiaro. Riprova."
    except sr.RequestError as exc:
        return None, f"Riconoscimento non raggiungibile: {exc}"
    except Exception as exc:
        return None, f"Errore riconoscimento: {exc}"


# ---------------------------------------------------------------------------
# Prompt + Ollama
# ---------------------------------------------------------------------------
def build_system_prompt(live_sources: str) -> str:
    fast = is_fast_mode()
    brevity = (
        "Massimo 2 frasi corte."
        if fast
        else "Massimo 3-5 frasi corte."
    )
    return SYSTEM_PROMPT_TEMPLATE.format(
        role=st.session_state.get("match_role", "Non specificato"),
        champion=(st.session_state.get("match_champion") or "Non specificato").strip()
        or "Non specificato",
        rank=st.session_state.get("match_rank", "Non specificato"),
        enemy_notes=(st.session_state.get("match_enemy_notes") or "Nessuna").strip() or "Nessuna",
        live_sources=live_sources,
        speed_mode="RAPIDA" if fast else "normale",
        brevity_rule=brevity,
    )


def collect_realtime_context() -> tuple[str, list[bytes], str]:
    """
    Raccoglie briefing Live Client + frame recenti dal feed continuo.

    Ritorna (blocco_testo_da_allegare_al_prompt, frames, descrizione_fonti).
    """
    chunks: list[str] = []
    frames: list[bytes] = []
    sources: list[str] = []

    if st.session_state.get("live_client_api", True):
        briefing, err, _raw = get_live_game_briefing()
        if briefing:
            chunks.append(briefing)
            sources.append("Live Client API")
            st.session_state["live_client_last_ok"] = True
            st.session_state["live_client_last_error"] = None
        else:
            st.session_state["live_client_last_ok"] = False
            st.session_state["live_client_last_error"] = err
            # Non inquinare il prompt se l'utente ha attivato l'extra ma non è in partita:
            # un avviso corto basta; il feed schermo resta la fonte principale.
            chunks.append(
                "=== LIVE CLIENT (opzionale) ===\n"
                f"Non disponibile ora: {err}\n"
                "Ignora questo blocco e basa il consiglio sui frame del feed video."
            )
            sources.append("Live Client (offline)")

    if st.session_state.get("live_screen_feed", True):
        sync_live_feed()
        n = int(st.session_state.get("live_frame_count", 3))
        frames = LIVE_FEED.recent_pngs(count=n, min_gap_s=0.35)
        if frames:
            sources.append(f"Feed video continuo ({len(frames)} frame)")
            chunks.append(
                f"=== FEED VIDEO ===\n"
                f"Allegati {len(frames)} frame recenti dal monitor di gioco "
                f"(cattura continua ~{st.session_state.get('live_fps', 2)} FPS). "
                "Usali come visione in tempo reale della partita."
            )
        else:
            sources.append("Feed video (buffer vuoto)")
            chunks.append(
                "=== FEED VIDEO ===\n"
                "Buffer ancora vuoto o cattura fallita. "
                f"Stato: {LIVE_FEED.status()}"
            )

    return "\n\n".join(chunks), frames, ", ".join(sources) if sources else "nessuna"


def stream_ollama_reply(messages: list[dict]) -> Generator[str, None, None]:
    if ollama is None:
        yield "⚠️ Installa ollama: pip install ollama"
        return
    model = active_model_name()
    try:
        stream = ollama.chat(
            model=model,
            messages=messages,
            stream=True,
            options={"num_predict": active_num_predict(), "temperature": 0.4},
        )
        for chunk in stream:
            if isinstance(chunk, dict):
                content = (chunk.get("message") or {}).get("content") or ""
            else:
                message = getattr(chunk, "message", None)
                content = getattr(message, "content", "") if message else ""
            if content:
                yield content
    except Exception as exc:
        yield (
            f"⚠️ Errore Ollama (`{model}`): {exc}\n"
            "Per i frame video: `ollama pull qwen2.5vl`. "
            "Con sola Live Client API puoi usare il modello testo `qwen`."
        )


_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def _split_complete_sentences(buffer: str) -> tuple[list[str], str]:
    parts = _SENTENCE_END.split(buffer)
    if len(parts) == 1:
        return [], buffer
    return [p.strip() for p in parts[:-1] if p.strip()], parts[-1]


def generate_assistant_reply(messages: list[dict], *, speak_early: bool) -> str:
    stream_area = st.empty()
    full = ""
    pending = ""
    for token in stream_ollama_reply(messages):
        full += token
        stream_area.markdown(full)
        if speak_early and st.session_state.get("tts_enabled", True):
            pending += token
            sentences, pending = _split_complete_sentences(pending)
            for s in sentences:
                speak_text(s)
    if speak_early and st.session_state.get("tts_enabled", True):
        rest = pending.strip()
        if rest:
            speak_text(rest)
    return full


def build_ollama_messages(
    user_text: str,
    *,
    realtime_block: str,
    frames: list[bytes],
    live_sources: str,
) -> list[dict]:
    history: list[dict] = []
    for m in st.session_state.messages:
        if m["role"] in ("user", "assistant"):
            history.append({"role": m["role"], "content": m["content"]})
    if history and history[-1]["role"] == "user":
        history.pop()

    content = (
        f"{realtime_block}\n\n"
        f"=== DOMANDA GIOCATORE ===\n{user_text}"
    )
    user_msg: dict = {"role": "user", "content": content}
    if frames:
        user_msg["images"] = frames

    return [
        {"role": "system", "content": build_system_prompt(live_sources)},
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
        "match_role": "Non specificato",
        "match_champion": "",
        "match_rank": "Non specificato",
        "match_enemy_notes": "",
        "tts_enabled": True,
        "fast_mode": True,
        "early_tts": True,
        # Default: solo feed schermo (niente API). Live Client è opzionale e locale (no API key).
        "live_client_api": False,
        "live_screen_feed": True,
        "live_fps": 2.0,
        "live_frame_count": 3,
        "text_model": DEFAULT_TEXT_MODEL,
        "vision_model": DEFAULT_VISION_MODEL,
        "monitor_index": 1,
        "show_live_preview": True,
        "live_client_last_ok": False,
        "live_client_last_error": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


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
            "Note rapide",
            value=st.session_state.match_enemy_notes,
            placeholder="es. focus sull'ADC",
            height=60,
        )

        st.divider()
        st.subheader("🔴 Tempo reale (senza account Riot)")
        st.session_state.live_screen_feed = st.toggle(
            "Feed schermo continuo (consigliato)",
            value=st.session_state.live_screen_feed,
            help=(
                "Cattura la partita in background (~2 FPS). "
                "Non serve alcuna API Riot: alla domanda invia gli ultimi frame."
            ),
        )
        st.session_state.live_client_api = st.toggle(
            "Extra opzionale: Live Client locale",
            value=st.session_state.live_client_api,
            help=(
                "NON è l'API Developer di Riot (niente registrazione / API key). "
                "È un endpoint locale del client LoL su 127.0.0.1:2999, attivo solo in partita. "
                "Puoi lasciarlo OFF: il coach funziona col solo feed schermo."
            ),
        )
        if st.session_state.live_client_api:
            st.caption(
                "ℹ️ Live Client = dati dal tuo PC durante la partita, "
                "**senza** developer portal Riot. Se non ti interessa, spegnila."
            )

        monitors = list_monitors()
        labels = [label for _, label in monitors]
        indices = [idx for idx, _ in monitors]
        try:
            current = indices.index(st.session_state.monitor_index)
        except ValueError:
            current = min(1, len(indices) - 1)
        chosen = st.selectbox("Monitor di gioco", labels, index=current)
        st.session_state.monitor_index = indices[labels.index(chosen)]

        st.session_state.live_fps = st.slider(
            "FPS feed video",
            min_value=1.0,
            max_value=4.0,
            value=float(st.session_state.live_fps),
            step=0.5,
        )
        st.session_state.live_frame_count = st.slider(
            "Frame inviati per domanda",
            min_value=1,
            max_value=5,
            value=int(st.session_state.live_frame_count),
        )
        st.session_state.show_live_preview = st.toggle(
            "Anteprima live in sidebar",
            value=st.session_state.show_live_preview,
        )
        st.session_state.vision_model = st.text_input(
            "Modello vision (per feed frame)",
            value=st.session_state.vision_model,
        )
        st.session_state.text_model = st.text_input(
            "Modello testo (se feed OFF)",
            value=st.session_state.text_model,
        )

        sync_live_feed()
        feed_status = LIVE_FEED.status()
        if st.session_state.live_client_api:
            if st.session_state.get("live_client_last_ok"):
                st.success("Live Client: dati ok (ultima lettura)")
            elif st.session_state.get("live_client_last_error"):
                st.warning("Live Client: in attesa di partita")
            else:
                st.info("Live Client: verrà letto a ogni domanda")
        if st.session_state.live_screen_feed:
            if feed_status["running"] and feed_status["buffered_frames"] > 0:
                st.success(
                    f"Feed video: LIVE · {feed_status['buffered_frames']} frame in buffer · "
                    f"totale {feed_status['frames_captured']}"
                )
            elif feed_status["running"]:
                st.info("Feed video: avviato, buffer in riempimento…")
            else:
                st.warning("Feed video: non in esecuzione")
            if feed_status.get("last_error"):
                st.caption(f"Cattura: {feed_status['last_error']}")

        st.divider()
        st.subheader("⚡ Velocità")
        st.session_state.fast_mode = st.toggle(
            "Modalità rapida",
            value=st.session_state.fast_mode,
        )
        st.session_state.early_tts = st.toggle(
            "TTS dalla prima frase",
            value=st.session_state.early_tts,
        )
        st.session_state.tts_enabled = st.toggle(
            "Sintesi vocale attiva",
            value=st.session_state.tts_enabled,
        )
        st.caption(
            f"Modello: `{active_model_name()}` · token `{active_num_predict()}` · "
            f"TTS `{active_tts_rate()}` · OS `{platform.system()}`"
        )

        if st.button("🗑️ Nuova conversazione", use_container_width=True):
            st.session_state.messages = [
                {"role": "assistant", "content": "Chat azzerata. Il feed live continua."}
            ]
            st.session_state.pending_voice_prompt = None
            st.rerun()

        st.divider()
        st.markdown(
            "**Non serve l’API Riot pubblica.** Il coach guarda la partita dal "
            "**feed schermo continuo**. LoL in *borderless*, app sul 2° monitor, "
            "seleziona il monitor di gioco qui sopra."
        )


@st.fragment(run_every=2.0)
def render_live_preview() -> None:
    """Anteprima che si aggiorna da sola: stato API + ultimo frame del feed."""
    st.markdown("##### Monitor live")
    cols = st.columns(2)
    with cols[0]:
        if st.session_state.get("live_client_api", True):
            briefing, err, _ = get_live_game_briefing()
            if briefing:
                st.session_state["live_client_last_ok"] = True
                # mostra solo le prime righe
                preview = "\n".join(briefing.splitlines()[:12])
                st.code(preview, language="text")
            else:
                st.session_state["live_client_last_ok"] = False
                st.caption(err or "In attesa della partita…")
        else:
            st.caption("Live Client disattivata")
    with cols[1]:
        if st.session_state.get("live_screen_feed", True):
            sync_live_feed()
            frame = LIVE_FEED.latest_png()
            if frame:
                st.image(frame, caption="Ultimo frame del feed continuo", use_container_width=True)
            else:
                st.caption("Nessun frame ancora (avvio feed / controlla monitor)")
        else:
            st.caption("Feed schermo disattivato")


def render_chat_history() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("preview_frames") and st.session_state.get("show_live_preview", True):
                # mostra solo l'ultimo frame in chat per non appesantire
                st.image(
                    message["preview_frames"][-1],
                    caption=f"Frame live usati: {len(message['preview_frames'])}",
                    use_container_width=True,
                )
            st.markdown(message["content"])


def handle_user_prompt(prompt: str) -> None:
    prompt = (prompt or "").strip()
    if not prompt:
        return

    with st.spinner("Leggo la partita in tempo reale..."):
        realtime_block, frames, live_sources = collect_realtime_context()

    user_entry: dict = {"role": "user", "content": prompt}
    if frames:
        user_entry["preview_frames"] = frames[-1:]  # anteprima leggera in history

    st.session_state.messages.append(user_entry)
    with st.chat_message("user"):
        if frames:
            st.image(
                frames[-1],
                caption=f"Contesto video: {len(frames)} frame recenti · {live_sources}",
                use_container_width=True,
            )
        st.markdown(prompt)
        with st.expander("Dati live inviati al modello"):
            st.code(realtime_block[:3500], language="text")

    messages = build_ollama_messages(
        prompt,
        realtime_block=realtime_block,
        frames=frames,
        live_sources=live_sources,
    )
    speak_early = bool(st.session_state.get("early_tts", True)) and bool(
        st.session_state.get("tts_enabled", True)
    )

    with st.chat_message("assistant"):
        with st.spinner(f"Coach ({active_model_name()})…"):
            full_response = generate_assistant_reply(messages, speak_early=speak_early)

    st.session_state.messages.append({"role": "assistant", "content": full_response})
    if st.session_state.get("tts_enabled", True) and not speak_early:
        speak_text(full_response, show_missing_voice_info=True)
    st.session_state.last_spoken_index = len(st.session_state.messages) - 1


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="centered")
    init_session_state()
    sync_live_feed()

    st.title("⚔️ LoL Coach — Tempo reale")
    st.caption(
        "Vede la partita dal feed schermo continuo (niente API key Riot) · "
        f"modello `{active_model_name()}`"
    )

    render_sidebar()
    if st.session_state.get("show_live_preview", True):
        render_live_preview()

    render_chat_history()

    c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
    with c1:
        mic_clicked = st.button("🎙️ Chiedi al Coach", use_container_width=True, type="primary")
    with c2:
        now_clicked = st.button("🔴 Analizza ora (live)", use_container_width=True)
    with c3:
        st.caption(
            "Ogni domanda legge lo stato live corrente + gli ultimi frame del feed, "
            "non uno screenshot isolato."
        )

    if mic_clicked:
        with st.spinner("Ti ascolto..."):
            text, error = listen_from_microphone()
        if error:
            st.warning(error)
        elif text:
            st.success(f"Hai detto: {text}")
            st.session_state.pending_voice_prompt = text
            st.rerun()

    if now_clicked:
        st.session_state.pending_voice_prompt = (
            "Basandoti sullo stato LIVE della partita in questo istante, "
            "cosa dovrei fare ora? Risposta brevissima."
        )
        st.rerun()

    if st.session_state.pending_voice_prompt:
        voice_prompt = st.session_state.pending_voice_prompt
        st.session_state.pending_voice_prompt = None
        handle_user_prompt(voice_prompt)

    typed = st.chat_input("Domanda (usa sempre i dati live della partita)...")
    if typed:
        handle_user_prompt(typed)


if __name__ == "__main__":
    main()
