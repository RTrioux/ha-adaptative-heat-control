"""Command-line interface for heat-control."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from . import __version__, rooms
from .client import Hass
from .heaters import list_heaters, set_heater_mode, set_heater_power


def _local(timestamp: datetime) -> str:
    return timestamp.astimezone().strftime("%Y-%m-%d %H:%M")


def _heater_line(heater) -> str:
    power = "on" if heater.power_on else ("off" if heater.power_on is False else "n/a")
    return f"{heater.name}: mode={heater.mode or 'n/a'} power={power}"


def cmd_status(hass: Hass, _args: argparse.Namespace) -> None:
    config = hass.get_config()
    heaters = list_heaters(hass)
    print(f"Home Assistant {config.get('version')} - {config.get('location_name')}")
    print(f"  temperature sensors: {len(rooms.temperature_sensors(hass))}")
    print(f"  presence sensors    : {len(rooms.presence_sensors(hass))}")
    print(f"  heaters             : {', '.join(h.name for h in heaters) or 'none'}")


def cmd_rooms(hass: Hass, _args: argparse.Namespace) -> None:
    print("temperature sensors:")
    for state in rooms.temperature_sensors(hass):
        attrs = state.attributes or {}
        print(
            f"  {state.entity_id:<52} {state.state:>8} "
            f"{attrs.get('unit_of_measurement') or '':<4} {attrs.get('friendly_name', '')}"
        )
    print("presence / motion sensors:")
    for state in rooms.presence_sensors(hass):
        attrs = state.attributes or {}
        print(f"  {state.entity_id:<52} {state.state:>8} {attrs.get('friendly_name', '')}")


def cmd_heaters(hass: Hass, _args: argparse.Namespace) -> None:
    heaters = list_heaters(hass)
    if not heaters:
        print("no pilot-wire heaters found")
        return
    for heater in heaters:
        power = "on" if heater.power_on else ("off" if heater.power_on is False else "n/a")
        print(
            f"{heater.name:<26} mode={heater.mode or 'n/a':<16} "
            f"power={power:<5} options=[{', '.join(heater.modes)}]"
        )


def cmd_temp(hass: Hass, args: argparse.Namespace) -> None:
    samples = rooms.temperature_history(
        hass, args.entity, start=args.start, end=args.end, hours=args.hours
    )
    stats = rooms.temperature_stats(samples)
    if stats is None:
        print(f"no temperature samples for {args.entity} in the requested window")
        return
    print(f"{args.entity}")
    print(f"  last   : {stats['last']:.2f} °C at {_local(stats['last_time'])}")
    print(
        f"  window : {_local(stats['window_start'])} -> {_local(stats['window_end'])}"
        f" ({stats['count']} samples)"
    )
    print(f"  mean   : {stats['mean']:.2f} °C  min {stats['min']:.2f}  max {stats['max']:.2f}")
    if args.raw:
        for time, value in samples:
            print(f"  {_local(time)}  {value:.2f}")


def cmd_presence(hass: Hass, args: argparse.Namespace) -> None:
    samples = rooms.presence_history(
        hass, args.entity, start=args.start, end=args.end, hours=args.hours
    )
    stats = rooms.presence_stats(samples)
    if stats is None:
        print(f"no presence samples for {args.entity} in the requested window")
        return
    current = "occupied" if stats["current"] else "empty"
    print(f"{args.entity}")
    print(f"  last      : {current} since {_local(stats['current_since'])}")
    print(
        f"  window    : {_local(stats['window_start'])} -> {_local(stats['window_end'])}"
        f" ({stats['count']} state changes)"
    )
    print(
        f"  occupancy : {stats['occupied_seconds']:.0f} s of"
        f" {stats['covered_seconds']:.0f} s ({stats['occupancy_ratio'] * 100:.0f}%)"
    )
    if args.raw:
        for time, value in samples:
            print(f"  {_local(time)}  {'occupied' if value else 'empty'}")


def cmd_set_mode(hass: Hass, args: argparse.Namespace) -> None:
    heater = set_heater_mode(hass, args.heater, args.mode)
    print(_heater_line(heater))


def cmd_power(hass: Hass, args: argparse.Namespace) -> None:
    heater = set_heater_power(hass, args.heater, args.power == "on")
    print(_heater_line(heater))


def _parse_time(text: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid timestamp {text!r}: {error}") from error
    return parsed.astimezone() if parsed.tzinfo is None else parsed


def _add_window_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("entity", help="entity id, see 'rooms' command")
    parser.add_argument("--hours", type=float, default=24.0, help="window in hours (default: 24)")
    parser.add_argument("--start", type=_parse_time, help="window start, e.g. 2026-11-14T08:00")
    parser.add_argument("--end", type=_parse_time, help="window end")
    parser.add_argument("--raw", action="store_true", help="print every sample")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="heat-control",
        description="Room temperature, room presence and electric heater control "
        "through Home Assistant.",
        epilog="examples:\n"
        "  heat-control temp sensor.thermometre_salon_temperature --hours 6\n"
        "  heat-control presence binary_sensor.capteur_presence_salon_presence\n"
        "  heat-control set-mode salon eco\n"
        "  heat-control power salon off",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="command", required=True)

    subparsers.add_parser("status", help="Home Assistant connection and inventory").set_defaults(
        func=cmd_status
    )
    subparsers.add_parser("rooms", help="list temperature and presence sensors").set_defaults(
        func=cmd_rooms
    )
    subparsers.add_parser("heaters", help="list electric heaters and their modes").set_defaults(
        func=cmd_heaters
    )

    temp = subparsers.add_parser("temp", help="room temperature history")
    _add_window_args(temp)
    temp.set_defaults(func=cmd_temp)

    presence = subparsers.add_parser("presence", help="room presence history")
    _add_window_args(presence)
    presence.set_defaults(func=cmd_presence)

    mode = subparsers.add_parser("set-mode", help="set the pilot-wire mode of a radiator")
    mode.add_argument("heater", help="heater name or entity id, e.g. salon")
    mode.add_argument(
        "mode", help="comfort | comfort_-1 | comfort_-2 | eco | frost_protection | off"
    )
    mode.set_defaults(func=cmd_set_mode)

    power = subparsers.add_parser("power", help="turn the radiator plug on or off")
    power.add_argument("heater", help="heater name or entity id")
    power.add_argument("power", choices=("on", "off"))
    power.set_defaults(func=cmd_power)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        hass = Hass()
        args.func(hass, args)
    except KeyboardInterrupt:
        return 130
    except Exception as error:  # CLI boundary: show a clean message, not a traceback
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
