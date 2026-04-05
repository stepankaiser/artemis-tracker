"""OLED display — SSD1306 128x64 I2C. Phase-aware, fully autonomous.

Default: live stats with phase-appropriate emphasis.
Every 60s: shows next milestone for 5 seconds.
Handles all phases from outbound through post-splashdown.
Shows data staleness warning if API is unreachable.
"""

import logging
import time
from datetime import datetime, timezone

from .config import (CREW, DISTANCE_COMPARISONS, LAUNCH_TIME, MILESTONES,
                     SPLASHDOWN_TIME)

logger = logging.getLogger(__name__)

MILESTONE_SHOW_DURATION = 5.0
MILESTONE_INTERVAL = 60.0


def _fmt_dist(km):
    if km < 100:
        return f"{km:.0f} km"
    if km < 1_000:
        return f"{km:.0f} km"
    if km < 10_000:
        return f"{km/1000:.1f}k km"
    return f"{km/1000:.0f}k km"


def _fmt_speed(kmh):
    if kmh < 1_000:
        return f"{kmh:.0f} km/h"
    if kmh < 10_000:
        return f"{kmh:,.0f} km/h"
    return f"{kmh/1000:.1f}k km/h"


def _fmt_met(now):
    s = int((now - LAUNCH_TIME).total_seconds())
    if s < 0:
        h, r = divmod(-s, 3600)
        m, sec = divmod(r, 60)
        return f"T-{h:02d}:{m:02d}:{sec:02d}"
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m, sec = divmod(r, 60)
    if d > 0:
        return f"T+{d}d {h:02d}:{m:02d}:{sec:02d}"
    return f"T+{h:02d}:{m:02d}:{sec:02d}"


def _phase_label(phase):
    return {
        "prelaunch": "PRE-LAUNCH",
        "earth_orbit": "EARTH ORBIT",
        "outbound": "OUTBOUND",
        "flyby": "LUNAR FLYBY",
        "return": "HOMEBOUND",
        "reentry": "REENTRY!",
        "splashdown": "SPLASHDOWN!",
    }.get(phase, phase.upper())


def _next_milestone(now):
    for ms in MILESTONES:
        dt = int((ms.time - now).total_seconds())
        if dt > 0:
            if dt > 86400:
                cd = f"in {dt // 86400}d {(dt % 86400) // 3600}h"
            elif dt > 3600:
                cd = f"in {dt // 3600}h {(dt % 3600) // 60}m"
            elif dt > 60:
                cd = f"in {dt // 60}m {dt % 60}s"
            else:
                cd = f"in {dt}s"
            return ms.name, ms.description, cd
    return None


def _distance_comparison(km):
    best = None
    for threshold, desc in DISTANCE_COMPARISONS:
        if km >= threshold:
            best = desc
    return best


def _mission_duration():
    s = int((SPLASHDOWN_TIME - LAUNCH_TIME).total_seconds())
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m, _ = divmod(r, 60)
    return f"{d}d {h}h {m}m"


class OLEDDisplay:
    def __init__(self, simulate=False):
        self.simulate = simulate
        self.device = None
        self.font = None
        self.font_sm = None

        self.dist_earth = 0.0
        self.dist_moon = 0.0
        self.speed = 0.0
        self.phase = "outbound"
        self.data_stale_seconds = 0.0
        self.fact_lines = ["Artemis II: first", "crew to the Moon", "since 1972!"]

        # Display cycle: 60s stats → 5s milestone → 5s fun fact → repeat
        self._cycle_start = 0.0
        self._splash_page = 0
        self._splash_page_t = 0.0

    async def start(self):
        if self.simulate:
            logger.info("OLED: simulation mode")
            return
        try:
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306
            from PIL import ImageFont

            for port in [3, 1, 14, 13]:
                try:
                    serial = i2c(port=port, address=0x3C)
                    self.device = ssd1306(serial, width=128, height=64)
                    logger.info(f"OLED: found on I2C bus {port}")
                    break
                except Exception:
                    continue
            if not self.device:
                raise RuntimeError("OLED not found")

            for path in [
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
            ]:
                try:
                    self.font = ImageFont.truetype(path, 11)
                    self.font_sm = ImageFont.truetype(path, 9)
                    break
                except OSError:
                    continue
            if not self.font:
                self.font = ImageFont.load_default()
                self.font_sm = self.font

            logger.info("OLED: initialized")
        except Exception as e:
            logger.warning(f"OLED: init failed ({e}), simulation mode")
            self.simulate = True

    def render(self):
        if self.simulate or not self.device:
            return

        from luma.core.render import canvas
        now = datetime.now(timezone.utc)
        t = time.time()

        # Display cycle: 60s stats → 10s milestone → 10s fun fact → repeat (80s total)
        if self._cycle_start == 0:
            self._cycle_start = t
        cycle_pos = (t - self._cycle_start) % 80.0

        show_milestone = 60.0 <= cycle_pos < 70.0
        show_fact = 70.0 <= cycle_pos < 80.0

        with canvas(self.device) as draw:
            if self.phase == "splashdown":
                self._page_splashdown(draw, now, t)
            elif show_fact:
                self._page_fact(draw, now)
            elif show_milestone:
                self._page_milestone(draw, now)
            elif self.phase == "flyby":
                self._page_flyby(draw, now)
            elif self.phase == "reentry":
                self._page_reentry(draw, now)
            else:
                self._page_stats(draw, now)

    def _header(self, draw, now):
        """Common header: phase + MET on separate lines."""
        draw.text((0, 0), _phase_label(self.phase), font=self.font, fill="white")
        draw.text((0, 13), _fmt_met(now), font=self.font_sm, fill="white")
        draw.line([(0, 23), (127, 23)], fill="white")

    def _progress_bar(self, draw, now):
        """Mission progress bar at bottom."""
        total = (SPLASHDOWN_TIME - LAUNCH_TIME).total_seconds()
        elapsed = (now - LAUNCH_TIME).total_seconds()
        progress = max(0.0, min(1.0, elapsed / total))
        draw.rectangle([(0, 61), (127, 63)], outline="white")
        if progress > 0:
            draw.rectangle([(1, 62), (int(1 + 125 * progress), 62)], fill="white")

    def _stale_warning(self, draw):
        """Show data age warning if API unreachable."""
        if self.data_stale_seconds > 600:  # 10 min
            mins = int(self.data_stale_seconds / 60)
            draw.text((70, 54), f"[{mins}m old]", font=self.font_sm, fill="white")

    # ── Pages ──

    def _page_stats(self, draw, now):
        """Standard stats: distances, speed."""
        self._header(draw, now)
        draw.text((0, 26), f"Earth {_fmt_dist(self.dist_earth)}", font=self.font_sm, fill="white")
        draw.text((0, 37), f"Moon  {_fmt_dist(self.dist_moon)}", font=self.font_sm, fill="white")
        draw.text((0, 48), f"Speed {_fmt_speed(self.speed)}", font=self.font_sm, fill="white")
        self._stale_warning(draw)
        self._progress_bar(draw, now)

    def _page_flyby(self, draw, now):
        """Flyby: emphasize Moon distance."""
        self._header(draw, now)
        # Moon distance in larger font
        draw.text((0, 26), "Moon distance:", font=self.font_sm, fill="white")
        draw.text((0, 37), _fmt_dist(self.dist_moon), font=self.font, fill="white")
        if self.dist_moon < 10_000:
            draw.text((0, 51), "CLOSEST APPROACH!", font=self.font_sm, fill="white")
        elif self.dist_earth > 400_000:
            draw.text((0, 51), "NEW DISTANCE RECORD!", font=self.font_sm, fill="white")
        else:
            draw.text((0, 51), f"Speed {_fmt_speed(self.speed)}", font=self.font_sm, fill="white")
        self._progress_bar(draw, now)

    def _page_reentry(self, draw, now):
        """Reentry: emphasize speed."""
        draw.text((0, 0), "REENTRY!", font=self.font, fill="white")
        draw.text((0, 14), _fmt_met(now), font=self.font_sm, fill="white")
        draw.line([(0, 24), (127, 24)], fill="white")
        draw.text((0, 28), "Speed:", font=self.font_sm, fill="white")
        draw.text((0, 40), _fmt_speed(self.speed), font=self.font, fill="white")
        # Countdown to splashdown
        dt = int((SPLASHDOWN_TIME - now).total_seconds())
        if dt > 0:
            draw.text((0, 54), f"Splash in {dt // 60}m {dt % 60}s", font=self.font_sm, fill="white")

    def _page_splashdown(self, draw, now, t):
        """Post-splashdown: rotating screens."""
        if self._splash_page_t == 0:
            self._splash_page_t = t  # initialize on first call
        elif t - self._splash_page_t > 10:
            self._splash_page = (self._splash_page + 1) % 3
            self._splash_page_t = t

        draw.text((0, 0), "MISSION COMPLETE!", font=self.font, fill="white")
        draw.line([(0, 14), (127, 14)], fill="white")

        if self._splash_page == 0:
            draw.text((0, 18), f"Duration:", font=self.font_sm, fill="white")
            draw.text((0, 29), _mission_duration(), font=self.font, fill="white")
            draw.text((0, 43), "Max distance:", font=self.font_sm, fill="white")
            draw.text((0, 54), "406,841 km", font=self.font_sm, fill="white")
        elif self._splash_page == 1:
            draw.text((0, 18), "CREW", font=self.font_sm, fill="white")
            for i, c in enumerate(CREW):
                draw.text((0, 29 + i * 9), f"{c['name']}", font=self.font_sm, fill="white")
        else:
            draw.text((20, 22), "Welcome", font=self.font, fill="white")
            draw.text((30, 38), "home!", font=self.font, fill="white")

    def _page_milestone(self, draw, now):
        """Next milestone countdown."""
        ms = _next_milestone(now)
        if not ms:
            self._page_splashdown(draw, now, time.time())
            return
        name, desc, countdown = ms
        draw.text((0, 0), "NEXT MILESTONE", font=self.font_sm, fill="white")
        draw.line([(0, 11), (127, 11)], fill="white")
        draw.text((0, 15), name, font=self.font, fill="white")
        # Word-wrap description
        words = desc.split()
        lines, line = [], ""
        for w in words:
            if len(line) + len(w) + 1 > 24:
                lines.append(line)
                line = w
            else:
                line = f"{line} {w}" if line else w
        if line:
            lines.append(line)
        for i, ln in enumerate(lines[:2]):
            draw.text((0, 29 + i * 10), ln, font=self.font_sm, fill="white")
        draw.text((0, 52), countdown, font=self.font, fill="white")

    def _page_fact(self, draw, now):
        """AI-generated fun fact."""
        draw.text((0, 0), "DID YOU KNOW?", font=self.font_sm, fill="white")
        draw.line([(0, 11), (127, 11)], fill="white")
        for i, line in enumerate(self.fact_lines[:4]):
            draw.text((0, 15 + i * 11), line, font=self.font_sm, fill="white")

    async def stop(self):
        if self.device:
            self.device.hide()
            logger.info("OLED: off")
