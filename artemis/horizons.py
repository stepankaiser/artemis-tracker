"""JPL Horizons API client for tracking Artemis II and the Moon."""

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from .config import HORIZONS_ARTEMIS_ID, HORIZONS_MOON_ID

logger = logging.getLogger(__name__)

HORIZONS_API = "https://ssd.jpl.nasa.gov/api/horizons.api"


@dataclass
class SpacecraftState:
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    distance_from_earth_km: float = 0.0
    distance_from_moon_km: float = 0.0
    speed_kmh: float = 0.0
    position_ratio: float = 0.0  # 0=Earth, 1=Moon distance, can exceed 1.0

    def __post_init__(self):
        self.distance_from_earth_km = math.sqrt(self.x**2 + self.y**2 + self.z**2)
        self.speed_kmh = math.sqrt(self.vx**2 + self.vy**2 + self.vz**2) * 3600


@dataclass
class MoonState:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    distance_from_earth_km: float = 0.0

    def __post_init__(self):
        self.distance_from_earth_km = math.sqrt(self.x**2 + self.y**2 + self.z**2)


def _extract_values(line, keys):
    values = []
    for key in keys:
        idx = line.find(key)
        if idx < 0:
            raise ValueError(f"Key '{key}' not found in: {line}")
        after_eq = line[idx + len(key):]
        num_str = ""
        for ch in after_eq:
            if ch in "0123456789.eE+-":
                num_str += ch
            elif num_str:
                break
        values.append(float(num_str))
    return values


def _parse_vectors(text):
    lines = text.split("\n")
    in_data = False
    pos = vel = None
    for line in lines:
        stripped = line.strip()
        if stripped == "$$SOE":
            in_data = True
            continue
        if stripped == "$$EOE":
            break
        if in_data:
            if "X =" in stripped and "VX" not in stripped:
                pos = _extract_values(stripped, ["X =", "Y =", "Z ="])
            elif "VX=" in stripped:
                vel = _extract_values(stripped, ["VX=", "VY=", "VZ="])
    if pos is None or vel is None:
        raise ValueError("Failed to parse Horizons response")
    return pos, vel


def _parse_position_only(text):
    lines = text.split("\n")
    in_data = False
    for line in lines:
        stripped = line.strip()
        if stripped == "$$SOE":
            in_data = True
            continue
        if stripped == "$$EOE":
            break
        if in_data and "X =" in stripped and "VX" not in stripped:
            return _extract_values(stripped, ["X =", "Y =", "Z ="])
    raise ValueError("Failed to parse Moon position")


async def _fetch_horizons(client, command, start, stop):
    params = {
        "format": "text",
        "COMMAND": f"'{command}'",
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "VECTORS",
        "CENTER": "'500@399'",
        "START_TIME": f"'{start}'",
        "STOP_TIME": f"'{stop}'",
        "STEP_SIZE": "'1'",
        "VEC_TABLE": "'2'",
    }
    resp = await client.get(HORIZONS_API, params=params, timeout=30)
    resp.raise_for_status()
    return resp.text


def compute_distances(sc, moon):
    dx, dy, dz = sc.x - moon.x, sc.y - moon.y, sc.z - moon.z
    sc.distance_from_moon_km = math.sqrt(dx**2 + dy**2 + dz**2)
    # Position ratio: fraction of Earth-Moon distance. Can exceed 1.0 during flyby.
    if moon.distance_from_earth_km > 0:
        sc.position_ratio = sc.distance_from_earth_km / moon.distance_from_earth_km
    return sc


class HorizonsTracker:
    def __init__(self, poll_interval=300):
        self.poll_interval = poll_interval
        self.spacecraft = None
        self.moon = None
        self._client = None
        # Resilience
        self.last_update_time = 0.0
        self.consecutive_failures = 0
        self._last_velocity_ratio = 0.0  # ratio change per second for interpolation

    @property
    def staleness_seconds(self):
        if self.last_update_time == 0:
            return float("inf")
        return time.time() - self.last_update_time

    async def start(self):
        self._client = httpx.AsyncClient()
        await self.update()

    async def stop(self):
        if self._client:
            await self._client.aclose()

    async def update(self):
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        start = now.strftime("%Y-%m-%d %H:%M")
        stop = (now + timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M")

        try:
            sc_text, moon_text = await asyncio.gather(
                _fetch_horizons(self._client, HORIZONS_ARTEMIS_ID, start, stop),
                _fetch_horizons(self._client, HORIZONS_MOON_ID, start, stop),
            )
            pos, vel = _parse_vectors(sc_text)
            sc = SpacecraftState(timestamp=now, x=pos[0], y=pos[1], z=pos[2],
                                 vx=vel[0], vy=vel[1], vz=vel[2])
            moon_pos = _parse_position_only(moon_text)
            moon = MoonState(x=moon_pos[0], y=moon_pos[1], z=moon_pos[2])

            old_ratio = self.spacecraft.position_ratio if self.spacecraft else 0
            self.spacecraft = compute_distances(sc, moon)
            self.moon = moon

            # Track velocity for interpolation
            elapsed = time.time() - self.last_update_time if self.last_update_time else self.poll_interval
            if elapsed > 0:
                self._last_velocity_ratio = (self.spacecraft.position_ratio - old_ratio) / elapsed

            self.last_update_time = time.time()
            self.consecutive_failures = 0

            logger.info(
                f"Updated: Earth={sc.distance_from_earth_km:,.0f}km "
                f"Moon={sc.distance_from_moon_km:,.0f}km "
                f"Speed={sc.speed_kmh:,.0f}km/h "
                f"Ratio={sc.position_ratio:.3f}"
            )
        except Exception as e:
            self.consecutive_failures += 1
            logger.error(f"Horizons update failed ({self.consecutive_failures}x): {e}")

    def interpolated_ratio(self):
        """Estimate current ratio between API polls for smoother movement."""
        if not self.spacecraft:
            return 0.0
        elapsed = time.time() - self.last_update_time
        return max(0.0, self.spacecraft.position_ratio + self._last_velocity_ratio * elapsed)

    async def poll_loop(self):
        while True:
            await self.update()
            # Exponential backoff on failure
            if self.consecutive_failures > 0:
                backoff = min(600, self.poll_interval * (2 ** min(self.consecutive_failures, 5)))
                await asyncio.sleep(backoff)
            else:
                await asyncio.sleep(self.poll_interval)
