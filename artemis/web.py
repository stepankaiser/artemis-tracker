"""Lightweight web server for phone display — FastAPI + WebSocket."""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import CREW, LAUNCH_TIME, MILESTONES, SPLASHDOWN_TIME

logger = logging.getLogger(__name__)

# Shared state — updated by tracker main loop
_state = {}
_fact = ""


def update_web_state(state: dict, fact: str):
    global _state, _fact
    _state = state
    _fact = fact


async def run_web_server(host="0.0.0.0", port=8080):
    """Run the web server for the phone dashboard."""
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    import uvicorn

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = Path(__file__).parent / "dashboard.html"
        return HTMLResponse(html_path.read_text())

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                now = datetime.now(timezone.utc)
                met_s = int((now - LAUNCH_TIME).total_seconds())
                d, r = divmod(abs(met_s), 86400)
                h, r = divmod(r, 3600)
                m, s = divmod(r, 60)
                prefix = "T+" if met_s >= 0 else "T-"
                met = f"{prefix}{d}d {h:02d}:{m:02d}:{s:02d}"

                total = (SPLASHDOWN_TIME - LAUNCH_TIME).total_seconds()
                elapsed = (now - LAUNCH_TIME).total_seconds()
                progress = max(0, min(1, elapsed / total))

                # Next milestone
                next_ms = None
                for ms in MILESTONES:
                    dt = int((ms.time - now).total_seconds())
                    if dt > 0:
                        next_ms = {"name": ms.name, "desc": ms.description,
                                   "emoji": ms.emoji, "seconds": dt}
                        break

                # Milestones timeline
                milestones = []
                for ms in MILESTONES:
                    milestones.append({
                        "name": ms.name, "emoji": ms.emoji,
                        "passed": ms.time <= now,
                    })

                data = {
                    "met": met,
                    "phase": _state.get("phase", "outbound"),
                    "progress": progress,
                    "dist_earth": _state.get("dist_earth_km", 0),
                    "dist_moon": _state.get("dist_moon_km", 0),
                    "speed": _state.get("speed_kmh", 0),
                    "ratio": _state.get("position_ratio", 0),
                    "next_milestone": next_ms,
                    "milestones": milestones,
                    "crew": CREW,
                    "fact": _fact,
                }
                await websocket.send_text(json.dumps(data))
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
