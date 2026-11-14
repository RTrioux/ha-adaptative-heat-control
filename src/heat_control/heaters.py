"""Electric heater inventory and control.

The radiators on this installation are Zigbee plugs driven by pilot wire
(fil pilote), exposed by Home Assistant as paired entities:

* ``switch.chauffage_<room>``                 -- mains power to the radiator
* ``select.chauffage_<room>_pilot_wire_mode`` -- pilot-wire heating order

Pilot-wire modes: ``comfort``, ``comfort_-1``, ``comfort_-2``, ``eco``,
``frost_protection``, ``off``. The pilot wire carries the order while the
radiator's own room thermostat does the modulation; switching mains power off
is the hard off.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional, Union

from .client import Hass

PILOT_WIRE_MODES = (
    "comfort",
    "comfort_-1",
    "comfort_-2",
    "eco",
    "frost_protection",
    "off",
)

_MODE_ALIASES = {
    "confort": "comfort",
    "comfort_1": "comfort_-1",
    "comfort_2": "comfort_-2",
    "confort_1": "comfort_-1",
    "confort_2": "comfort_-2",
    "comfort": "comfort",
    "eco": "eco",
    "frost_protection": "frost_protection",
    "frost": "frost_protection",
    "hors_gel": "frost_protection",
    "off": "off",
    "arret": "off",
    "stop": "off",
    "on": "comfort",
    "heat": "comfort",
}


@dataclass(frozen=True)
class Heater:
    """An electric radiator plug and its pilot-wire select entity."""

    name: str
    power_switch: Optional[str]
    mode_select: str
    power_on: Optional[bool]
    mode: Optional[str]
    modes: tuple[str, ...]


def normalise_mode(mode: str) -> str:
    """Map user input (French labels, comfort-1, "heat", ...) to a mode id."""
    canonical = str(mode).strip().lower()
    fuzzy = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", canonical)).strip("_")
    return _MODE_ALIASES.get(fuzzy, _MODE_ALIASES.get(canonical, canonical))


def list_heaters(hass: Hass) -> list[Heater]:
    """All pilot-wire heaters found on the Home Assistant instance."""
    states = {state.entity_id: state for state in hass.get_states()}
    heaters: list[Heater] = []
    for entity_id, state in sorted(states.items()):
        if not (entity_id.startswith("select.") and entity_id.endswith("_pilot_wire_mode")):
            continue
        name = entity_id.removeprefix("select.").removesuffix("_pilot_wire_mode")
        switch = states.get(f"switch.{name}")
        heaters.append(
            Heater(
                name=name,
                power_switch=f"switch.{name}" if switch else None,
                power_on=(switch.state == "on") if switch else None,
                mode_select=entity_id,
                mode=None if state.state in ("unknown", "unavailable") else state.state,
                modes=tuple((state.attributes or {}).get("options") or ()),
            )
        )
    return heaters


def get_heater(hass: Hass, ref: Union[str, Heater]) -> Heater:
    """Find a heater by base name, substring, switch or select entity id."""
    if isinstance(ref, Heater):
        return ref
    heaters = list_heaters(hass)
    lookup = str(ref).strip().lower()
    for heater in heaters:
        candidates = {
            heater.name.lower(),
            (heater.power_switch or "").lower(),
            heater.mode_select.lower(),
            f"switch.{heater.name}".lower(),
            f"select.{heater.name}".lower(),
        }
        if lookup in candidates:
            return heater
    matches = [heater for heater in heaters if lookup in heater.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise KeyError(
            f"ambiguous heater {ref!r}: {', '.join(heater.name for heater in matches)}"
        )
    known = ", ".join(heater.name for heater in heaters) or "none"
    raise KeyError(f"unknown heater {ref!r}. Known heaters: {known}")


def _wait(hass: Hass, name: str, predicate, timeout: float) -> Heater:
    """Poll the heater until `predicate` holds (Zigbee round-trip). Best effort."""
    heater = get_heater(hass, name)
    deadline = time.monotonic() + timeout
    while not predicate(heater) and time.monotonic() < deadline:
        time.sleep(0.5)
        heater = get_heater(hass, name)
    return heater


def set_heater_mode(
    hass: Hass,
    heater: Union[str, Heater],
    mode: str,
    ensure_power_on: bool = True,
    settle_seconds: float = 5.0,
) -> Heater:
    """Set the pilot-wire heating mode of an electric heater (fil pilote).

    Args:
        hass: connected :class:`heat_control.Hass` client.
        heater: heater name, substring, switch or select entity id
            (e.g. ``"salon"``, ``"chauffage_salon"``, ``"select.chauffage_salon_pilot_wire_mode"``).
        mode: one of the heater's pilot-wire modes. Accepted aliases:
            French labels (``confort``, ``hors gel``, ...), ``comfort-1``,
            ``on``/``heat`` -> ``comfort``.
        ensure_power_on: when requesting a heating mode on a powered-off
            plug, power the plug on first so the order can take effect.
        settle_seconds: how long to poll until the Zigbee state confirms.

    Returns:
        The refreshed :class:`Heater` (best effort even if it did not settle).
    """
    target = get_heater(hass, heater)
    wanted = normalise_mode(mode)
    allowed = target.modes or PILOT_WIRE_MODES
    if wanted not in allowed:
        raise ValueError(
            f"mode {mode!r} is not valid for {target.name}; available: {', '.join(allowed)}"
        )
    if ensure_power_on and wanted != "off" and target.power_switch and target.power_on is False:
        hass.turn_on(target.power_switch)
    hass.select_option(target.mode_select, wanted)
    return _wait(hass, target.name, lambda h: h.mode == wanted, settle_seconds)


def set_heater_power(
    hass: Hass,
    heater: Union[str, Heater],
    on: bool,
    settle_seconds: float = 5.0,
) -> Heater:
    """Cut or restore mains power to the radiator plug."""
    target = get_heater(hass, heater)
    if not target.power_switch:
        raise ValueError(f"{target.name} has no power switch")
    if on:
        hass.turn_on(target.power_switch)
    else:
        hass.turn_off(target.power_switch)
    return _wait(hass, target.name, lambda h: h.power_on is on, settle_seconds)
