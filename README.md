# heat-control

Python tools to read room temperature and presence history from Home
Assistant and to drive electric radiators through pilot-wire (fil pilote)
plugs.

Managed with [uv](https://docs.astral.sh/uv/); dependencies in
`pyproject.toml`: `hassapi` (Home Assistant REST client), `numpy`
(statistics / control maths) and `control` (python-control, for the
regulation loop to come).

## Configuration

`HASS_URL` and `HASS_TOKEN` come from the environment or a `.env` file in the
project root (git-ignored, permissions 600). The token is a Home Assistant
long-lived access token (user profile -> Security) sent as
`Authorization: Bearer ...`.

## CLI

```bash
uv run heat-control status      # connection and inventory
uv run heat-control rooms       # temperature + presence sensors
uv run heat-control heaters     # radiators: mode, power, options

uv run heat-control temp sensor.thermometre_salon_temperature --hours 6 [--raw]
uv run heat-control presence binary_sensor.capteur_presence_salon_presence

uv run heat-control set-mode salon eco    # comfort | comfort_-1 | comfort_-2 | eco | frost_protection | off
uv run heat-control power salon off       # cut mains to the radiator plug
```

Rooms on this installation: salon, chambre, cuisine (+ chauffage_vertical_cuisine).

## Library

```python
from heat_control import (
    Hass, set_heater_mode, set_heater_power,
    temperature_history, temperature_stats,
    presence_history, presence_stats,
)

hass = Hass()  # HASS_URL / HASS_TOKEN from environment or .env

samples = temperature_history(hass, "sensor.thermometre_salon_temperature", hours=6)
stats = temperature_stats(samples)   # mean / min / max / last, computed with numpy
if stats["mean"] < 19.0:
    set_heater_mode(hass, "salon", "comfort")
else:
    set_heater_mode(hass, "salon", "eco")

present = presence_history(hass, "binary_sensor.capteur_presence_salon_presence")
ratio = presence_stats(present)["occupancy_ratio"]
```

`Hass` subclasses `hassapi.Hass`: `get_states()`, `get_state(entity_id)`,
`call_service(...)`, `turn_on/turn_off`, `select_option`, websocket
subscriptions, plus heat-control additions `get_config()` and
`get_history(entities, start, end)` (the `/api/history/period` endpoint).

## Notes

- Heaters are Zigbee plug + pilot-wire select pairs, e.g.
  `switch.chauffage_salon` with `select.chauffage_salon_pilot_wire_mode`.
  `set_heater_mode` writes the select, `set_heater_power` the switch;
  `ensure_power_on=True` powers the plug on first when a heating mode is
  requested.
- History comes from the Home Assistant recorder; it contains what HA
  recorded and nothing more.
- On this network the name `homeassistant` resolves only through the router
  DNS (`dig @192.168.50.1 homeassistant`); this machine's stub resolver does
  not forward it, hence the direct IP in `.env`. An entry in `/etc/hosts`
  would restore the name everywhere if wanted.
