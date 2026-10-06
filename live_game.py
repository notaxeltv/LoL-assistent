"""
Tempo reale per LoL Coach.

1) Riot Live Client Data API (https://127.0.0.1:2999) — stato partita strutturato
2) LiveScreenFeed — cattura continua dello schermo in un ring buffer (frame recenti)
"""

from __future__ import annotations

import io
import json
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from typing import Any

try:
    import mss
    from PIL import Image
except ImportError:  # pragma: no cover
    mss = None  # type: ignore
    Image = None  # type: ignore

LIVE_CLIENT_BASE = "https://127.0.0.1:2999/liveclientdata"
_SSL_CTX = ssl._create_unverified_context()  # certificato self-signed del client LoL


# ---------------------------------------------------------------------------
# Live Client Data API
# ---------------------------------------------------------------------------
def fetch_live_client_json(path: str = "allgamedata", timeout: float = 0.8) -> tuple[dict | None, str | None]:
    """
    Legge un endpoint Live Client. Disponibile solo a partita avviata.

    Ritorna (data, errore).
    """
    url = f"{LIVE_CLIENT_BASE}/{path.lstrip('/')}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.URLError as exc:
        return None, (
            "Live Client non raggiungibile (parti una partita LoL / Practice Tool). "
            f"Dettaglio: {exc.reason if hasattr(exc, 'reason') else exc}"
        )
    except TimeoutError:
        return None, "Timeout Live Client API."
    except Exception as exc:
        return None, f"Errore Live Client: {exc}"


def _fmt_items(items: list[dict] | None) -> str:
    if not items:
        return "-"
    names = []
    for it in items:
        name = (it or {}).get("displayName") or (it or {}).get("itemID")
        if name not in (None, 0, "0", ""):
            names.append(str(name))
    return ", ".join(names) if names else "-"


def summarize_live_game(data: dict[str, Any]) -> str:
    """Compatta allgamedata in un briefing testuale per il modello."""
    lines: list[str] = ["=== STATO PARTITA IN TEMPO REALE (Live Client API) ==="]

    stats = data.get("gameData") or {}
    game_time = stats.get("gameTime")
    if game_time is not None:
        mins = int(game_time) // 60
        secs = int(game_time) % 60
        lines.append(f"Tempo di gioco: {mins:02d}:{secs:02d}")
    if stats.get("gameMode"):
        lines.append(f"Modalità: {stats.get('gameMode')}")
    if stats.get("mapName"):
        lines.append(f"Mappa: {stats.get('mapName')}")

    active = data.get("activePlayer") or {}
    if active:
        lines.append("")
        lines.append("--- TU (activePlayer) ---")
        lines.append(f"Summoner: {active.get('summonerName', '?')}")
        lines.append(f"Livello: {active.get('level', '?')}")
        lines.append(f"Gold correnti: {active.get('currentGold', '?')}")
        champion_stats = active.get("championStats") or {}
        if champion_stats:
            lines.append(
                "HP: {h:.0f}/{mh:.0f} | Mana/risorsa: {r:.0f}/{mr:.0f} | AD: {ad:.0f} | AP: {ap:.0f}".format(
                    h=float(champion_stats.get("currentHealth") or 0),
                    mh=float(champion_stats.get("maxHealth") or 0),
                    r=float(champion_stats.get("resourceValue") or 0),
                    mr=float(champion_stats.get("resourceMax") or 0),
                    ad=float(champion_stats.get("attackDamage") or 0),
                    ap=float(champion_stats.get("abilityPower") or 0),
                )
            )
        abilities = active.get("abilities") or {}
        cds = []
        for key in ("Q", "W", "E", "R", "Passive"):
            ab = abilities.get(key) or {}
            if not ab:
                continue
            cd = ab.get("abilityLevel")
            ready = ab.get("displayname") or ab.get("id") or key
            cds.append(f"{key}:{ready}(lv{cd})")
        if cds:
            lines.append("Abilità: " + " | ".join(cds))

    players = data.get("allPlayers") or []
    if players:
        lines.append("")
        lines.append("--- SCOREBOARD ---")
        for p in players:
            scores = p.get("scores") or {}
            team = p.get("team", "?")
            champ = p.get("championName", "?")
            name = p.get("summonerName", "?")
            k = scores.get("kills", 0)
            d = scores.get("deaths", 0)
            a = scores.get("assists", 0)
            cs = scores.get("creepScore", 0)
            level = p.get("level", "?")
            dead = "DEAD" if p.get("isDead") else "alive"
            respawn = p.get("respawnTimer")
            respawn_s = f", respawn {respawn:.0f}s" if dead == "DEAD" and respawn else ""
            items = _fmt_items(p.get("items"))
            is_bot = " [BOT]" if p.get("isBot") else ""
            lines.append(
                f"[{team}] {champ} ({name}){is_bot} lv{level} "
                f"{k}/{d}/{a} CS{cs} {dead}{respawn_s} | items: {items}"
            )
            spells = p.get("summonerSpells") or {}
            sp = []
            for slot in ("summonerSpellOne", "summonerSpellTwo"):
                sp_name = (spells.get(slot) or {}).get("displayName")
                if sp_name:
                    sp.append(sp_name)
            if sp:
                lines.append(f"    spells: {', '.join(sp)}")

    events = (data.get("events") or {}).get("Events") or []
    if events:
        lines.append("")
        lines.append("--- ULTIMI EVENTI ---")
        for ev in events[-8:]:
            et = ev.get("EventName") or ev.get("EventID")
            t = ev.get("EventTime")
            t_s = f"{int(t)//60:02d}:{int(t)%60:02d}" if isinstance(t, (int, float)) else "?"
            extra = []
            for key in (
                "KillerName",
                "VictimName",
                "Assisters",
                "DragonType",
                "TurretKilled",
                "InhibKilled",
                "Acer",
            ):
                if key in ev:
                    extra.append(f"{key}={ev[key]}")
            lines.append(f"[{t_s}] {et}" + (f" ({'; '.join(map(str, extra))})" if extra else ""))

    lines.append("=== FINE STATO LIVE ===")
    return "\n".join(lines)


def get_live_game_briefing() -> tuple[str | None, str | None, dict | None]:
    """Ritorna (briefing_testuale, errore, raw_dict)."""
    data, err = fetch_live_client_json("allgamedata")
    if err or not data:
        return None, err or "Nessun dato", None
    return summarize_live_game(data), None, data


# ---------------------------------------------------------------------------
# Feed schermo continuo (ring buffer)
# ---------------------------------------------------------------------------
class LiveScreenFeed:
    """
    Thread in background che cattura frame dal monitor di gioco.
    Non è uno screenshot on-demand: mantiene gli ultimi secondi di partita.
    """

    def __init__(self, maxlen: int = 10) -> None:
        self._lock = threading.Lock()
        self._frames: deque[tuple[float, bytes]] = deque(maxlen=maxlen)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.monitor_index = 1
        self.fps = 2.0
        self.max_width = 960
        self.last_error: str | None = None
        self.frames_captured = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def configure(self, *, monitor_index: int, fps: float = 2.0, max_width: int = 960) -> None:
        self.monitor_index = monitor_index
        self.fps = max(0.5, min(fps, 5.0))
        self.max_width = max_width

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="lol-live-feed", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()

    def latest_png(self) -> bytes | None:
        with self._lock:
            if not self._frames:
                return None
            return self._frames[-1][1]

    def recent_pngs(self, count: int = 3, min_gap_s: float = 0.4) -> list[bytes]:
        """Ultimi frame distanziati nel tempo (pseudo-video per il modello vision)."""
        with self._lock:
            items = list(self._frames)
        if not items:
            return []
        chosen: list[bytes] = []
        last_t = None
        for ts, png in reversed(items):
            if last_t is None or (last_t - ts) >= min_gap_s:
                chosen.append(png)
                last_t = ts
            if len(chosen) >= count:
                break
        chosen.reverse()
        return chosen

    def status(self) -> dict[str, Any]:
        with self._lock:
            n = len(self._frames)
            age = time.time() - self._frames[-1][0] if self._frames else None
        return {
            "running": self.running,
            "buffered_frames": n,
            "frames_captured": self.frames_captured,
            "latest_age_s": age,
            "last_error": self.last_error,
            "fps": self.fps,
            "monitor_index": self.monitor_index,
        }

    def _capture_once(self) -> bytes | None:
        if mss is None or Image is None:
            self.last_error = "Installa mss e Pillow per il feed live"
            return None
        try:
            with mss.mss() as sct:
                monitors = sct.monitors
                idx = self.monitor_index
                if idx < 0 or idx >= len(monitors):
                    idx = 1 if len(monitors) > 1 else 0
                raw = sct.grab(monitors[idx])
                img = Image.frombytes("RGB", raw.size, raw.rgb)
            if img.width > self.max_width:
                ratio = self.max_width / float(img.width)
                img = img.resize(
                    (self.max_width, max(1, int(img.height * ratio))),
                    Image.Resampling.BILINEAR,
                )
            buf = io.BytesIO()
            # JPEG più leggero per il buffer continuo
            img.save(buf, format="JPEG", quality=70, optimize=True)
            self.last_error = None
            return buf.getvalue()
        except Exception as exc:
            # Fallback ImageGrab (Win/macOS)
            try:
                from PIL import ImageGrab

                grabbed = ImageGrab.grab(all_screens=(self.monitor_index == 0))
                if grabbed.mode != "RGB":
                    grabbed = grabbed.convert("RGB")
                if grabbed.width > self.max_width:
                    ratio = self.max_width / float(grabbed.width)
                    grabbed = grabbed.resize(
                        (self.max_width, max(1, int(grabbed.height * ratio))),
                        Image.Resampling.BILINEAR,
                    )
                buf = io.BytesIO()
                grabbed.save(buf, format="JPEG", quality=70, optimize=True)
                self.last_error = None
                return buf.getvalue()
            except Exception as exc2:
                self.last_error = f"{exc} | fallback: {exc2}"
                return None

    def _loop(self) -> None:
        interval = 1.0 / self.fps
        while not self._stop.is_set():
            t0 = time.time()
            png = self._capture_once()
            if png:
                with self._lock:
                    self._frames.append((time.time(), png))
                    self.frames_captured += 1
            # ricalcola interval se fps cambiato
            interval = 1.0 / max(0.5, self.fps)
            elapsed = time.time() - t0
            self._stop.wait(max(0.01, interval - elapsed))


# Singleton di processo: sopravvive ai rerun di Streamlit
LIVE_FEED = LiveScreenFeed(maxlen=12)
