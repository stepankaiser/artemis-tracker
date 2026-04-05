"""AI-powered fun facts using Gemini — generates one fresh fact per hour."""

import logging
import os
import time

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FACT_INTERVAL = 3600  # 1 hour


class FactGenerator:
    def __init__(self):
        self.current_fact = "Artemis II is the first crewed Moon mission since Apollo 17 in 1972!"
        self._last_generated = 0.0
        self._model = None

    async def start(self):
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            self._model = genai.GenerativeModel("gemini-2.5-flash")
            logger.info("Facts: Gemini initialized")
        except Exception as e:
            logger.warning(f"Facts: Gemini init failed ({e}), using static facts")

    async def maybe_refresh(self, dist_earth_km: float, dist_moon_km: float,
                            speed_kmh: float, phase: str, met_hours: float):
        """Generate a new fact if an hour has passed."""
        now = time.time()
        if now - self._last_generated < FACT_INTERVAL:
            return

        self._last_generated = now

        if not self._model:
            self._static_fact(dist_earth_km, speed_kmh, met_hours)
            return

        try:
            prompt = (
                f"You are a space narrator for a family watching the Artemis II Moon mission "
                f"on a tiny OLED display (max 3 lines of 21 characters each = 63 chars total). "
                f"Current: {dist_earth_km:,.0f}km from Earth, {dist_moon_km:,.0f}km from Moon, "
                f"speed {speed_kmh:,.0f}km/h, phase: {phase}, "
                f"crew has been flying for {met_hours:.0f} hours. "
                f"Write ONE short fun fact. Use everyday comparisons kids understand. "
                f"MUST fit in 63 characters. No emojis. Be accurate and surprising."
            )

            response = await self._model.generate_content_async(prompt)
            fact = response.text.strip().replace("\n", " ")

            # Truncate if needed
            if len(fact) > 70:
                fact = fact[:67] + "..."

            self.current_fact = fact
            logger.info(f"Facts: new fact: {fact}")

        except Exception as e:
            logger.warning(f"Facts: generation failed ({e})")
            self._static_fact(dist_earth_km, speed_kmh, met_hours)

    def _static_fact(self, dist_earth_km, speed_kmh, met_hours):
        """Fallback facts when Gemini is unavailable."""
        import random
        facts = [
            "Orion's heat shield hits 2760C on reentry - half as hot as the Sun!",
            "The SLS rocket is taller than the Statue of Liberty!",
            "Jeremy Hansen is the first Canadian heading to the Moon!",
            "Christina Koch holds the women's longest spaceflight record!",
            "Orion was named after one of the brightest constellations.",
            "The crew named their capsule 'Integrity'.",
            "A phone call to Orion would have over 1 second delay!",
            "Orion will skip off the atmosphere like a stone on water!",
        ]

        if dist_earth_km > 0:
            car_days = dist_earth_km / (120 * 24)
            if car_days > 1:
                facts.append(f"Driving at 120km/h it would take {car_days:.0f} days to reach Orion!")

        if speed_kmh > 1000:
            bullet = speed_kmh / 2736
            facts.append(f"Orion is moving {bullet:.0f}x faster than a bullet!")

        self.current_fact = random.choice(facts)

    def get_display_lines(self) -> list[str]:
        """Word-wrap the current fact into lines of max 21 chars for OLED."""
        words = self.current_fact.split()
        lines = []
        line = ""
        for w in words:
            if len(line) + len(w) + 1 > 21:
                lines.append(line)
                line = w
            else:
                line = f"{line} {w}" if line else w
        if line:
            lines.append(line)
        return lines[:4]  # max 4 lines on the small display
