"""heat-control: electric heater regulation through Home Assistant.

Environment / ``.env`` configuration:

* ``HASS_URL``   Home Assistant base URL, e.g. ``http://homeassistant:8123``
* ``HASS_TOKEN`` long-lived access token (HA user profile -> Security)
"""

from .client import Hass, HassError, parse_ha_datetime
from .heaters import (
    PILOT_WIRE_MODES,
    Heater,
    get_heater,
    list_heaters,
    set_heater_mode,
    set_heater_power,
)
from .rooms import (
    Sample,
    presence_history,
    presence_stats,
    presence_sensors,
    temperature_history,
    temperature_stats,
    temperature_sensors,
)

__version__ = "0.1.0"

__all__ = [
    "Hass",
    "HassError",
    "Heater",
    "PILOT_WIRE_MODES",
    "Sample",
    "get_heater",
    "list_heaters",
    "parse_ha_datetime",
    "presence_history",
    "presence_sensors",
    "presence_stats",
    "set_heater_mode",
    "set_heater_power",
    "temperature_history",
    "temperature_sensors",
    "temperature_stats",
]


def main() -> None:
    """Console-script entry point."""
    from .__main__ import main as cli_main

    raise SystemExit(cli_main())
