"""Mission configuration and timeline for Artemis II."""

from dataclasses import dataclass
from datetime import datetime, timezone

# === Hardware ===
NUM_LEDS = 60
LED_BRIGHTNESS = 0.4
SPI_SPEED_HZ = 6_400_000

# OLED (SSD1306 128x64 I2C)
OLED_WIDTH = 128
OLED_HEIGHT = 64

# === Mission Timeline (UTC) ===
LAUNCH_TIME = datetime(2026, 4, 1, 22, 35, 12, tzinfo=timezone.utc)
SPLASHDOWN_TIME = datetime(2026, 4, 11, 0, 17, 0, tzinfo=timezone.utc)

EARTH_MOON_DISTANCE_KM = 384_400  # average

# JPL Horizons IDs
HORIZONS_ARTEMIS_ID = "-1024"
HORIZONS_MOON_ID = "301"

# === API Polling ===
HORIZONS_POLL_INTERVAL_S = 300  # every 5 minutes
WEB_UPDATE_INTERVAL_S = 1       # websocket push rate

# === LED Zones ===
EARTH_LEDS = (0, 2)    # LEDs 0-2
MOON_LEDS = (57, 59)   # LEDs 57-59
SPACE_LEDS = (3, 56)   # LEDs 3-56


@dataclass
class MissionMilestone:
    name: str
    time: datetime
    description: str
    emoji: str


MILESTONES = [
    MissionMilestone(
        "Launch", LAUNCH_TIME,
        "Liftoff from LC-39B, Kennedy Space Center", "🚀"
    ),
    MissionMilestone(
        "Perigee Raise", datetime(2026, 4, 1, 23, 25, tzinfo=timezone.utc),
        "First engine burn to raise orbit", "🔥"
    ),
    MissionMilestone(
        "ICPS Separation", datetime(2026, 4, 2, 1, 59, tzinfo=timezone.utc),
        "Orion separates from upper stage", "✂️"
    ),
    MissionMilestone(
        "TLI Burn", datetime(2026, 4, 2, 23, 49, tzinfo=timezone.utc),
        "Trans-Lunar Injection — on the way to the Moon!", "🌙"
    ),
    MissionMilestone(
        "Lunar SOI Entry", datetime(2026, 4, 6, 4, 43, tzinfo=timezone.utc),
        "Entering the Moon's sphere of influence", "🌑"
    ),
    MissionMilestone(
        "Lunar Flyby", datetime(2026, 4, 6, 23, 6, tzinfo=timezone.utc),
        "Closest approach — 6,513 km from the far side!", "🎯"
    ),
    MissionMilestone(
        "Max Distance", datetime(2026, 4, 6, 23, 9, tzinfo=timezone.utc),
        "Farthest humans from Earth — 406,841 km!", "🏆"
    ),
    MissionMilestone(
        "Lunar SOI Exit", datetime(2026, 4, 7, 17, 27, tzinfo=timezone.utc),
        "Leaving the Moon's gravity, heading home", "🏠"
    ),
    MissionMilestone(
        "Manual Piloting", datetime(2026, 4, 9, 2, 55, tzinfo=timezone.utc),
        "Crew hand-flies Orion — first time since Apollo!", "🎮"
    ),
    MissionMilestone(
        "Entry Interface", datetime(2026, 4, 11, 0, 4, tzinfo=timezone.utc),
        "Hitting atmosphere at 40,000 km/h", "☄️"
    ),
    MissionMilestone(
        "Splashdown", SPLASHDOWN_TIME,
        "Safe landing in the Pacific Ocean!", "🌊"
    ),
]

CREW = [
    {"name": "Reid Wiseman", "role": "Commander", "agency": "NASA"},
    {"name": "Victor Glover", "role": "Pilot", "agency": "NASA"},
    {"name": "Christina Koch", "role": "Mission Specialist", "agency": "NASA"},
    {"name": "Jeremy Hansen", "role": "Mission Specialist", "agency": "CSA"},
]

# Fun distance comparisons (distance_km, description)
DISTANCE_COMPARISONS = [
    (1, "about as far as a 10-minute walk"),
    (12, "about as high as a commercial airplane flies"),
    (400, "as high as the International Space Station"),
    (1_000, "farther than the ISS — truly deep space now"),
    (12_742, "one Earth diameter away"),
    (35_786, "past the geostationary satellite belt"),
    (50_000, "farther than any GPS satellite"),
    (100_000, "a quarter of the way to the Moon"),
    (200_000, "halfway to the Moon"),
    (300_000, "three quarters of the way to the Moon"),
    (384_400, "at the Moon's distance!"),
    (400_171, "past Apollo 13's record — farthest humans ever!"),
]
