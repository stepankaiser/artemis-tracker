"""LED strip — Artemis II position tracker across all mission phases.

Visual hierarchy:
  1. ORION — bright warm/cool dot with comet tail (only moving element)
  2. EARTH — steady bright blue (left end)
  3. MOON  — steady bright white (right end)
  4. SPACE — nearly black, 3-4 barely-visible stars

Phase-specific effects:
  outbound:   warm white Orion, orange tail
  flyby:      shimmer near Moon, Orion can go past Moon position
  return:     cool blue-white Orion, cooler tail
  reentry:    Orion becomes red-hot fireball, heat glow on Earth end
  splashdown: rainbow celebration → ocean breathing → trophy mode
"""

import math
import random
import time
import logging

from .config import NUM_LEDS, SPLASHDOWN_TIME
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

EARTH = (0, 2)
SPACE = (3, 56)
MOON = (57, 59)
BLACK = (0, 0, 0)


def _c(v):
    return max(0, min(255, int(v)))


def lerp(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(_c(a + (b - a) * t) for a, b in zip(c1, c2))


def dim(c, f):
    return tuple(_c(v * f) for v in c)


def add(c1, c2):
    return tuple(_c(a + b) for a, b in zip(c1, c2))


class LEDController:
    def __init__(self, simulate=False):
        self.simulate = simulate
        self.pixels = None
        self._buf = [BLACK] * NUM_LEDS

        # 4 very faint stars
        positions = random.sample(range(SPACE[0] + 4, SPACE[1] - 4), 4)
        self._stars = [(p, random.uniform(1.0, 3.0), random.uniform(0, math.tau))
                       for p in sorted(positions)]

        # State (set by tracker)
        self.position_ratio = 0.0
        self.speed_kmh = 0.0
        self.dist_earth_km = 0.0
        self.dist_moon_km = 400_000.0
        self.phase = "outbound"
        self.is_return = False

        self._milestone_flash_end = 0.0
        self._prev_ratio = 0.0
        self._splashdown_start = 0.0
        # Highlight timers: persist effects for key moments
        self._closest_approach_until = 0.0  # intense flyby shimmer
        self._record_broken_until = 0.0     # golden glow

    async def start(self):
        if self.simulate:
            logger.info("LEDs: simulation mode")
            return
        try:
            import board
            import neopixel_spi as neopixel
            from .config import LED_BRIGHTNESS
            self.pixels = neopixel.NeoPixel_SPI(
                board.SPI(), NUM_LEDS, brightness=LED_BRIGHTNESS,
                auto_write=False, pixel_order=neopixel.GRB)
            logger.info(f"LEDs: {NUM_LEDS} pixels via SPI")
        except Exception as e:
            logger.warning(f"LEDs: init failed ({e}), simulation")
            self.simulate = True

    def trigger_milestone_flash(self):
        self._milestone_flash_end = time.time() + 2.0

    def startup_animation(self, target_ratio: float):
        """Rocket flies from Earth across the strip, slows down, lands at current position."""
        if self.simulate or not self.pixels:
            return
        logger.info(f"Startup animation → target ratio {target_ratio:.3f}")

        target_pos = SPACE[0] + target_ratio * (MOON[0] - 1 - SPACE[0])
        total_frames = 90  # ~3 seconds at 30fps

        for frame in range(total_frames):
            t = time.time()
            # Ease-out: fast start, slow finish
            progress = frame / total_frames
            ease = 1.0 - (1.0 - progress) ** 3  # cubic ease-out
            pos = SPACE[0] + ease * (target_pos - SPACE[0])

            # Clear
            for i in range(NUM_LEDS):
                self._buf[i] = BLACK

            # Earth always visible
            self._buf[0] = dim((0, 60, 255), 0.3)
            self._buf[1] = dim((0, 60, 255), 0.8)
            self._buf[2] = dim((0, 60, 255), 0.35)

            # Moon always visible
            self._buf[57] = dim((200, 200, 220), 0.25)
            self._buf[58] = dim((200, 200, 220), 0.7)
            self._buf[59] = dim((200, 200, 220), 0.3)

            # Rocket
            lo = int(math.floor(pos))
            hi = min(lo + 1, MOON[0] - 1)
            frac = pos - lo

            # Capsule
            capsule = (220, 230, 255)
            if SPACE[0] <= lo <= MOON[0] - 1:
                self._buf[lo] = dim(capsule, 0.95 * (1.0 - frac))
            if SPACE[0] <= hi <= MOON[0] - 1:
                self._buf[hi] = dim(capsule, 0.95 * frac)

            # Engine + exhaust trail
            exhaust = [
                ((255, 10, 0),  0.85),
                ((255, 50, 0),  0.50),
                ((255, 120, 0), 0.28),
                ((255, 200, 0), 0.13),
                ((255, 255, 50),0.05),
                ((200, 200, 40),0.015),
            ]
            for j, (color, base_b) in enumerate(exhaust, 1):
                idx = lo - j  # trail behind (toward Earth)
                if SPACE[0] <= idx <= MOON[0] - 1:
                    flicker = base_b * (0.8 + 0.2 * math.sin(t * 12 + j * 1.7))
                    self._buf[idx] = add(self._buf[idx], dim(color, flicker))

            # Light trail: faint line from Earth to current position
            for i in range(SPACE[0], lo - 6):
                self._buf[i] = add(self._buf[i], dim((20, 30, 80), 0.04))

            self._flush()
            time.sleep(1.0 / 30)

        logger.info("Startup animation complete")

    def render(self):
        t = time.time()
        for i in range(NUM_LEDS):
            self._buf[i] = BLACK

        if self.phase == "splashdown":
            if self._splashdown_start == 0:
                self._splashdown_start = t
            self._splashdown(t)
        else:
            self._splashdown_start = 0
            self._earth(t)
            self._moon(t)
            self._faint_stars(t)

            if self.phase == "reentry":
                self._reentry_orion(t)
                self._reentry_heat(t)
            else:
                self._orion(t)

            if self.phase == "flyby":
                self._flyby_shimmer(t)

        if t < self._milestone_flash_end:
            self._flash(t)

        self._flush()

    # ── Earth ──

    def _earth(self, t):
        # Full brightness to shine through paper drawing
        rate = 1.5 if self.phase == "reentry" else 0.6
        breath = 0.92 + 0.08 * math.sin(t * rate)
        color = (0, 80, 255)
        self._buf[0] = dim(color, breath * 0.85)
        self._buf[1] = dim(color, breath * 1.0)
        self._buf[2] = dim(color, breath * 0.85)

    # ── Moon ──

    def _moon(self, t):
        # Full brightness to shine through paper drawing
        proximity = max(0.0, 1.0 - self.dist_moon_km / 150_000)
        breath = 0.92 + 0.08 * math.sin(t * 0.5)
        brightness = min(1.0, breath + proximity * 0.08)
        color = (255, 255, 255)  # pure white for max brightness
        self._buf[57] = dim(color, brightness * 0.85)
        self._buf[58] = dim(color, brightness * 1.0)
        self._buf[59] = dim(color, brightness * 0.85)

    # ── Stars ──

    def _faint_stars(self, t):
        for pos, speed, phase in self._stars:
            twinkle = 0.5 + 0.5 * math.sin(t * speed + phase)
            self._buf[pos] = dim((60, 60, 80), 0.03 + 0.03 * twinkle)

    # ── Orion: outbound / flyby / return ──

    def _orion(self, t):
        first, last = SPACE[0], MOON[0] - 1
        span = last - first
        pos = first + self.position_ratio * span
        pos = max(float(first), min(float(last), pos))

        lo = int(math.floor(pos))
        hi = min(lo + 1, last)
        frac = pos - lo

        # ── Capsule: bright white with blue tint ──
        capsule = (220, 230, 255)
        pulse = 0.90 + 0.10 * math.sin(t * 2.0)
        self._buf[lo] = add(self._buf[lo], dim(capsule, pulse * (1.0 - frac)))
        if hi != lo:
            self._buf[hi] = add(self._buf[hi], dim(capsule, pulse * frac))

        # ── Rocket exhaust: bright red engine → fading red plume ──
        going_out = self.position_ratio >= self._prev_ratio
        trail = -1 if going_out else 1
        self._prev_ratio = self.position_ratio

        # Exhaust: bright red engine → red → orange → yellow → fading out
        exhaust = [
            ((255, 10, 0),   0.85),   # ENGINE — blazing red
            ((255, 50, 0),   0.50),   # red-ish
            ((255, 120, 0),  0.28),   # orange-ish
            ((255, 200, 0),  0.13),   # yellow-ish
            ((255, 255, 50), 0.05),   # pale yellow fading
            ((200, 200, 40), 0.015),  # barely visible
        ]

        for j, (color, base_b) in enumerate(exhaust, 1):
            # Engine flicker: subtle shimmer like a real rocket flame
            flicker = 0.85 + 0.15 * math.sin(t * 12 + j * 1.7)
            # Flowing effect: gentle wave through the plume
            flow = 0.80 + 0.20 * math.sin(t * 3.5 - j * 0.6)
            brightness = base_b * flicker * flow

            tpos = pos + trail * j
            tlo = int(math.floor(tpos))
            thi = tlo + 1
            tfrac = tpos - tlo
            if first <= tlo <= last:
                self._buf[tlo] = add(self._buf[tlo], dim(color, brightness * (1.0 - tfrac)))
            if first <= thi <= last:
                self._buf[thi] = add(self._buf[thi], dim(color, brightness * tfrac))

    # ── Orion during reentry: fireball ──

    def _reentry_orion(self, t):
        first, last = SPACE[0], MOON[0] - 1
        pos = first + self.position_ratio * (last - first)
        pos = max(float(first), min(float(last), pos))
        lo = int(math.floor(pos))
        hi = min(lo + 1, last)
        frac = pos - lo

        # Fireball: red-orange with rapid flicker
        flicker = 0.7 + 0.3 * math.sin(t * 12)
        core = (255, 80, 0)
        self._buf[lo] = add(self._buf[lo], dim(core, flicker * (1.0 - frac)))
        if hi != lo:
            self._buf[hi] = add(self._buf[hi], dim(core, flicker * frac))

        # Longer fiery tail (6 LEDs)
        trail = -1  # always trailing away from Earth during reentry
        if self.position_ratio < self._prev_ratio:
            trail = 1
        self._prev_ratio = self.position_ratio

        tail = [
            ((255, 60, 0),  0.50), ((255, 40, 0),  0.35),
            ((220, 20, 0),  0.22), ((180, 10, 0),  0.12),
            ((140, 5, 0),   0.06), ((80, 0, 0),    0.02),
        ]
        for j, (color, base_b) in enumerate(tail, 1):
            idx = lo + trail * j
            if first <= idx <= last:
                f = base_b * (0.7 + 0.3 * math.sin(t * 10 + j * 1.5))
                self._buf[idx] = add(self._buf[idx], dim(color, f))

    # ── Reentry heat glow on Earth end ──

    def _reentry_heat(self, t):
        # Skip-entry pulsing: slow intensity wave simulating skip trajectory
        skip_phase = 0.5 + 0.5 * math.sin(t * 0.2)  # ~30 sec cycle
        heat = (0.3 + 0.5 * math.sin(t * 8)) * skip_phase
        for i in range(8):
            fade = 1.0 - i / 8
            color = lerp((255, 40, 0), (255, 130, 0), i / 8)
            self._buf[i] = add(self._buf[i], dim(color, heat * fade * 0.5))

    # ── Flyby shimmer ──

    def _flyby_shimmer(self, t):
        # Trigger persistent highlights at key thresholds
        if self.dist_moon_km < 10_000 and self._closest_approach_until < t:
            self._closest_approach_until = t + 1800  # 30 min highlight
        if self.position_ratio > 1.03 and self._record_broken_until < t:
            self._record_broken_until = t + 1800  # 30 min highlight

        # Shimmer intensity: higher during closest approach window
        is_close = t < self._closest_approach_until
        intensity_mult = 0.40 if is_close else 0.25

        for i in range(MOON[0] - 8, MOON[1] + 1):
            if not (0 <= i < NUM_LEDS):
                continue
            d = abs(i - (MOON[0] - 2))
            w = math.sin(t * 4 - d * 0.6)
            if w > 0.2:
                intensity = (w - 0.2) / 0.8 * max(0, 1.0 - d * 0.1)
                self._buf[i] = add(self._buf[i], dim((100, 150, 255), intensity * intensity_mult))

        # Record-breaking golden glow — persists for 30 min after record is broken
        if t < self._record_broken_until:
            glow = 0.3 + 0.3 * math.sin(t * 1.5)
            for i in range(MOON[0] - 3, MOON[1] + 1):
                if 0 <= i < NUM_LEDS:
                    self._buf[i] = add(self._buf[i], dim((255, 200, 50), glow * 0.15))

    # ── Splashdown: 4-phase celebration ──

    def _splashdown(self, t):
        elapsed = t - self._splashdown_start
        minutes = elapsed / 60

        if minutes < 5:
            # Phase 1: Full rainbow celebration
            self._rainbow(t, 0.7)
        elif minutes < 30:
            # Phase 2: Dimming rainbow
            fade = 0.7 - (minutes - 5) / 25 * 0.4  # 0.7 → 0.3
            self._rainbow(t, fade)
        elif minutes < 120:
            # Phase 3: Ocean breathing — capsule floating in the Pacific
            breath = 0.15 + 0.15 * math.sin(t * 0.8)
            for i in range(NUM_LEDS):
                wave = 0.5 + 0.5 * math.sin(t * 0.5 + i * 0.15)
                self._buf[i] = dim((30, 60, 180), breath * wave)
        else:
            # Phase 4: Trophy mode — permanent ambient display
            # Earth blue, Moon white, center golden dot
            self._buf[0] = dim((0, 60, 255), 0.10)
            self._buf[1] = dim((0, 60, 255), 0.15)
            self._buf[2] = dim((0, 60, 255), 0.10)
            self._buf[57] = dim((200, 200, 220), 0.08)
            self._buf[58] = dim((200, 200, 220), 0.15)
            self._buf[59] = dim((200, 200, 220), 0.08)
            # Golden center dot — mission accomplished
            center = NUM_LEDS // 2
            glow = 0.10 + 0.05 * math.sin(t * 0.3)
            self._buf[center] = dim((255, 200, 50), glow)

    def _rainbow(self, t, brightness):
        colors = [(255,0,0),(255,100,0),(255,220,0),(0,255,0),(0,100,255),(80,0,200),(180,0,255)]
        for i in range(NUM_LEDS):
            h = ((i / NUM_LEDS) + t * 0.15) % 1.0
            ci = min(int(h * len(colors)), len(colors) - 1)
            ni = (ci + 1) % len(colors)
            color = lerp(colors[ci], colors[ni], (h * len(colors)) % 1.0)
            w = 0.5 + 0.5 * math.sin(t * 2 + i * 0.3)
            self._buf[i] = dim(color, w * brightness)

    # ── Milestone flash ──

    def _flash(self, t):
        remaining = self._milestone_flash_end - t
        progress = 1.0 - remaining / 2.0
        radius = int(progress * NUM_LEDS * 0.6)
        fade = max(0, 1.0 - progress * 1.3)
        center = NUM_LEDS // 2
        for i in range(NUM_LEDS):
            if abs(i - center) <= radius:
                self._buf[i] = add(self._buf[i], dim((255, 255, 255), fade * 0.4))

    # ── Hardware ──

    def _flush(self):
        if self.simulate or not self.pixels:
            return
        for i in range(NUM_LEDS):
            self.pixels[i] = self._buf[i]
        self.pixels.show()

    def get_buffer(self):
        return list(self._buf)

    async def stop(self):
        if self.pixels:
            self.pixels.fill(BLACK)
            self.pixels.show()
            logger.info("LEDs: off")
