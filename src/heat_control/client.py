"""Home Assistant client used by heat-control.

Builds on the ``hassapi`` REST client and adds the pieces heat-control needs
that upstream does not provide:

* the ``/api/history/period`` endpoint (room temperature / presence history),
* tolerant JSON parsing: Home Assistant serialises some entity attributes
  with raw control characters, which strict parsers (``Response.json()``,
  jq) reject.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Union

import requests

from hassapi import Hass as _Hass

from .config import ensure_env

DEFAULT_HASS_URL = "http://homeassistant:8123"


class HassError(RuntimeError):
    """heat-control could not talk to Home Assistant."""


def parse_ha_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse a Home Assistant timestamp into a timezone-aware datetime."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def to_ha_iso(value: datetime) -> str:
    """Format a datetime as UTC ISO 8601 for the Home Assistant API."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class Hass(_Hass):
    """:class:`hassapi.Hass` with a history endpoint and tolerant JSON parsing.

    Args:
        hassurl: Home Assistant base URL, e.g. ``http://homeassistant:8123``.
            Falls back to the ``HASS_URL`` environment variable / ``.env``.
        token: long-lived access token. Falls back to ``HASS_TOKEN``.
        verify: verify TLS certificates (ignored on plain HTTP).
        timeout: HTTP timeout in seconds; history queries can be slow.
    """

    def __init__(
        self,
        hassurl: Optional[str] = None,
        token: Optional[str] = None,
        verify: bool = True,
        timeout: float = 30.0,
    ) -> None:
        ensure_env()
        url = hassurl or os.environ.get("HASS_URL", DEFAULT_HASS_URL)
        token = token or os.environ.get("HASS_TOKEN")
        if not token:
            raise HassError(
                "no Home Assistant token: set HASS_TOKEN (environment or .env file)"
            )
        super().__init__(hassurl=url, token=token, verify=verify, timeout=timeout)

    def _process_response(self, response: requests.Response) -> Any:
        # Home Assistant may emit raw control characters inside attribute
        # strings; json.loads(strict=False) tolerates them, .json() does not.
        if response.ok:
            try:
                return json.loads(response.text, strict=False)
            except ValueError:
                return response.text
        return self._raise_error(response.status_code, response.url)

    def get_config(self) -> dict:
        """Home Assistant instance configuration (version, location, ...)."""
        return self._get("config")

    def get_history(
        self,
        entity_ids: Union[str, Iterable[str]],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        significant_changes_only: bool = False,
        minimal_response: bool = True,
    ) -> list[list[dict]]:
        """Entity state history, one list of state dicts per requested entity.

        States are ordered oldest first. Entities without records yield an
        empty inner list. Requires the recorder integration on the server.
        """
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        params: dict[str, Any] = {
            "filter_entity_id": ",".join(entity_ids),
            "significant_changes_only": "true" if significant_changes_only else "false",
            "minimal_response": "true" if minimal_response else "false",
        }
        if end is not None:
            params["end_time"] = to_ha_iso(end)
        if start is not None:
            return self._get(f"history/period/{to_ha_iso(start)}", params=params)
        return self._get("history/period", params=params)
