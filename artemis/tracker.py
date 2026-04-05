"""Artemis II LED Tracker — main entry point.

Usage:
  python -m artemis              # auto-detect hardware
  python -m artemis --simulate   # no hardware, log only
  python -m artemis --demo       # fake moving spacecraft for testing
"""

import argparse
import asyncio
import logging
import math
import signal
import sys
import time
from datetime import datetime, timezone

from .config import HORIZONS_POLL_INTERVAL_S, LAUNCH_TIME, MILESTONES, SPLASHDOWN_TIME
from .display import OLEDDisplay
from .facts import FactGenerator
from .horizons import HorizonsTracker
from .leds import LEDController

# Web server is optional — phone display
try:
    from .web import run_web_server, update_web_state
    HAS_WEB = True
except ImportError:
    HAS_WEB = False
    def update_web_state(*a): pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("artemis")

FPS = 30
FRAME_INTERVAL = 1.0 / FPS
OLED_INTERVAL = 1.0


def get_phase(now, state=None):
    """Determine mission phase using both timeline and live data."""
    if now < LAUNCH_TIME:
        return "prelaunch"

    tli = MILESTONES[3].time
    soi_in = MILESTONES[4].time
    soi_out = MILESTONES[7].time
    entry = MILESTONES[9].time
    splash = MILESTONES[10].time

    # If we have live data, use it for better phase detection
    if state:
        ratio = state.get("position_ratio", 0)
        dist_moon = state.get("dist_moon_km", 999999)
        dist_earth = state.get("dist_earth_km", 0)

        # Post-splashdown: clock past splashdown AND very close to Earth or data stale
        if now > splash and (dist_earth < 500 or state.get("data_stale", False)):
            return "splashdown"

        # Reentry: within 13 min of splashdown and close to Earth
        if now > entry and dist_earth < 50_000:
            return "reentry"

        # Flyby: near the Moon
        if dist_moon < 50_000 and ratio > 0.85:
            return "flyby"

        # Return: ratio is decreasing (heading home) and past SOI exit
        if state.get("is_return", False) and now > soi_in:
            return "return"

    # Fallback to timeline
    if now < tli:
        return "earth_orbit"
    if now < soi_in:
        return "outbound"
    if now < soi_out:
        return "flyby"
    if now < entry:
        return "return"
    if now < splash:
        return "reentry"
    return "splashdown"


class DemoTracker:
    """Fake tracker simulating the full mission in 2 minutes."""

    def __init__(self):
        self.spacecraft = None
        self.moon = None
        self._start = time.time()
        self.last_update_time = time.time()
        self.staleness_seconds = 0
        self._last_velocity_ratio = 0

    async def start(self):
        logger.info("Demo mode: full mission in 2 minutes")

    async def stop(self):
        pass

    async def update(self):
        pass

    def interpolated_ratio(self):
        return self.get_demo_state()["position_ratio"]

    def get_demo_state(self):
        elapsed = time.time() - self._start
        cycle = (elapsed % 120) / 120  # 2-minute full mission

        # Mission profile: outbound (0-0.45), flyby (0.45-0.55), return (0.55-1.0)
        if cycle < 0.45:
            ratio = (cycle / 0.45) * 1.05  # go slightly past Moon
            phase = "flyby" if ratio > 0.9 else "outbound"
        elif cycle < 0.55:
            # At/past Moon, coming back
            t = (cycle - 0.45) / 0.10
            ratio = 1.05 - t * 0.15
            phase = "flyby"
        elif cycle < 0.95:
            t = (cycle - 0.55) / 0.40
            ratio = 0.90 - t * 0.88
            phase = "return" if ratio > 0.02 else "reentry"
        else:
            ratio = 0.0
            phase = "splashdown"

        dist_earth = ratio * 400_000
        dist_moon = abs(1.0 - ratio) * 400_000
        speed = abs(math.sin(cycle * math.pi)) * 35_000 + 2_000

        return {
            "position_ratio": max(0, ratio),
            "speed_kmh": speed,
            "dist_earth_km": dist_earth,
            "dist_moon_km": dist_moon,
            "phase": phase,
            "is_return": cycle > 0.50,
            "data_stale": False,
        }

    async def poll_loop(self):
        while True:
            await asyncio.sleep(1)


async def run(args):
    simulate = args.simulate or sys.platform == "darwin"
    demo_mode = args.demo

    leds = LEDController(simulate=simulate)
    oled = OLEDDisplay(simulate=simulate)
    facts = FactGenerator()
    tracker = DemoTracker() if demo_mode else HorizonsTracker(HORIZONS_POLL_INTERVAL_S)

    shutdown = asyncio.Event()
    signal.signal(signal.SIGTERM, lambda *_: shutdown.set())
    signal.signal(signal.SIGINT, lambda *_: shutdown.set())
    signal.signal(signal.SIGUSR1, lambda *_: leds.trigger_milestone_flash())

    await leds.start()
    await oled.start()
    await facts.start()
    await tracker.start()

    # Startup animation: rocket flies to current position
    if tracker.spacecraft:
        leds.startup_animation(tracker.spacecraft.position_ratio)

    # Start web server for phone display (optional)
    web_task = None
    if HAS_WEB:
        try:
            web_task = asyncio.create_task(run_web_server())
            logger.info("Web dashboard on http://0.0.0.0:8080")
        except Exception as e:
            logger.warning(f"Web server failed: {e}")

    logger.info("=== Artemis II Tracker running ===")
    logger.info(f"Mode: {'DEMO' if demo_mode else 'SIMULATE' if simulate else 'LIVE'}")

    announced = {ms.name for ms in MILESTONES if ms.time <= datetime.now(timezone.utc)}
    poll_task = asyncio.create_task(tracker.poll_loop())

    # Track direction (outbound vs return) with a rolling window
    ratio_history = []
    last_oled = 0.0

    try:
        while not shutdown.is_set():
            frame_start = time.time()
            now = datetime.now(timezone.utc)

            if demo_mode:
                state = tracker.get_demo_state()
            elif tracker.spacecraft:
                sc = tracker.spacecraft
                # Use interpolated ratio for smoother LED movement between polls
                interp_ratio = tracker.interpolated_ratio()

                # Determine direction from ratio history
                ratio_history.append(sc.position_ratio)
                if len(ratio_history) > 5:
                    ratio_history.pop(0)
                is_return = (len(ratio_history) >= 3 and
                             ratio_history[-1] < ratio_history[0] - 0.001)

                state = {
                    "position_ratio": interp_ratio,
                    "speed_kmh": sc.speed_kmh,
                    "dist_earth_km": sc.distance_from_earth_km,
                    "dist_moon_km": sc.distance_from_moon_km,
                    "phase": "outbound",  # placeholder, computed below
                    "is_return": is_return,
                    "data_stale": tracker.staleness_seconds > 1800,
                }
                state["phase"] = get_phase(now, state)
            else:
                state = {
                    "position_ratio": 0.0, "speed_kmh": 0.0,
                    "dist_earth_km": 0.0, "dist_moon_km": 400_000.0,
                    "phase": get_phase(now), "is_return": False,
                    "data_stale": True,
                }

            # Milestone announcements
            for ms in MILESTONES:
                if ms.name not in announced and ms.time <= now:
                    announced.add(ms.name)
                    logger.info(f"MILESTONE: {ms.emoji} {ms.name} — {ms.description}")
                    leds.trigger_milestone_flash()

            # Update LEDs
            leds.position_ratio = state["position_ratio"]
            leds.speed_kmh = state["speed_kmh"]
            leds.dist_earth_km = state["dist_earth_km"]
            leds.dist_moon_km = state["dist_moon_km"]
            leds.phase = state["phase"]
            leds.is_return = state.get("is_return", False)
            leds.render()

            # Update OLED + facts (1 Hz)
            if frame_start - last_oled >= OLED_INTERVAL:
                met_hours = (now - LAUNCH_TIME).total_seconds() / 3600
                await facts.maybe_refresh(
                    state["dist_earth_km"], state["dist_moon_km"],
                    state["speed_kmh"], state["phase"], met_hours)
                oled.dist_earth = state["dist_earth_km"]
                oled.dist_moon = state["dist_moon_km"]
                oled.speed = state["speed_kmh"]
                oled.phase = state["phase"]
                oled.data_stale_seconds = tracker.staleness_seconds if not demo_mode else 0
                oled.fact_lines = facts.get_display_lines()
                oled.render()
                # Push to phone dashboard
                update_web_state(state, facts.current_fact)
                last_oled = frame_start

            elapsed = time.time() - frame_start
            await asyncio.sleep(max(0, FRAME_INTERVAL - elapsed))

    finally:
        poll_task.cancel()
        if web_task:
            web_task.cancel()
        await leds.stop()
        await oled.stop()
        logger.info("=== Tracker stopped ===")


def main():
    parser = argparse.ArgumentParser(description="Artemis II LED Tracker")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--demo", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
