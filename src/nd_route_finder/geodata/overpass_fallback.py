"""Resilient Overpass requests, retaining OSMnx's on-disk query cache."""

from collections.abc import Callable
import time
from typing import TypeVar
from unittest.mock import patch

import requests

import osmnx as ox
from osmnx import _http, _overpass
from requests.exceptions import RequestException

from nd_route_finder.geodata.overpass_unavailable_error import OverpassUnavailableError

T = TypeVar("T")


class OverpassFallback:
    # Ordered to reuse existing overpass-api.de cache, then fail over to other
    # publicly accessible mirrors. Never retry malformed input or valid empty maps.
    # All configured mirrors must offer worldwide OSM coverage. In particular
    # overpass.osm.ch is Switzerland-only and MUST NOT serve Austrian routes.
    _MIRRORS = (
        "https://overpass-api.de/api",
        "https://overpass.private.coffee/api",
        "https://maps.mail.ru/osm/tools/overpass/api",
        "https://overpass.osm.jp/api",
    )

    def execute(
        self,
        operation: Callable[[], T],
        purpose: str,
        notify: Callable[[str], None] | None = None,
    ) -> T:
        """Run one OSMnx query per mirror, switching only after a server error.

        Keep the standard OSMnx cache and restore the caller's global settings.
        Rate-limit status endpoints sometimes return HTML; a single query per
        mirror with a modest delay is safer than OSMnx's 60-second status fallback.
        """
        message = notify or (lambda _: None)
        original_url = ox.settings.overpass_url
        original_timeout = ox.settings.requests_timeout
        original_rate_limit = ox.settings.overpass_rate_limit
        # Respect locally configured mirrors and provide independently hosted fallbacks.
        mirrors = tuple(dict.fromkeys((original_url.rstrip("/"), *self._MIRRORS)))
        errors: list[str] = []
        try:
            ox.settings.overpass_rate_limit = False
            for index, mirror in enumerate(mirrors):
                ox.settings.overpass_url = mirror
                # Existing OSMnx query-cache hits do not incur HTTP timeouts.
                # Limit first-server waiting; let alternative mirrors have longer.
                ox.settings.requests_timeout = max(
                    1, int(min(float(original_timeout), 22 if index == 0 else 65))
                )
                message(f"Fetching {purpose} via {mirror.split('/')[2]} ({index + 1}/{len(mirrors)}) …")
                try:
                    # OSMnx 2.x normally sleeps 55 seconds then recursively retries
                    # every HTTP 429/504 response. A one-request replacement allows
                    # genuine, bounded automatic failover rather than waiting forever.
                    with patch.object(_overpass, "_overpass_request", self._one_shot_request):
                        return operation()
                except Exception as exc:
                    if not self._is_server_failure(exc):
                        raise
                    errors.append(f"{mirror.split('/')[2]}: {type(exc).__name__}")
                    if index < len(mirrors) - 1:
                        message(f"Map server busy; switching to another Overpass server for {purpose} …")
                        time.sleep(min(1.0 + index, 3.0))
        finally:
            ox.settings.overpass_url = original_url
            ox.settings.requests_timeout = original_timeout
            ox.settings.overpass_rate_limit = original_rate_limit

        raise OverpassUnavailableError(
            "OpenStreetMap servers could not provide the map data right now. "
            "Several independent Overpass servers were tried automatically. "
            "Please try Generate route again later; your selected points are unchanged. "
            f"({purpose})"
        )

    @staticmethod
    def _one_shot_request(data: object) -> dict:
        """OSMnx 2.1-compatible one-shot Overpass call, preserving its disk cache."""
        url = ox.settings.overpass_url.rstrip("/") + "/interpreter"
        prepared = str(requests.Request("GET", url, params=data).prepare().url)
        cached = _http._retrieve_from_cache(prepared)
        if isinstance(cached, dict):
            return cached
        response = requests.post(
            url,
            data=data,
            timeout=ox.settings.requests_timeout,
            headers=_http._get_http_headers(),
            **ox.settings.requests_kwargs,
        )
        if response.status_code in (429, 500, 502, 503, 504):
            raise ox._errors.ResponseStatusCodeError(f"Overpass HTTP {response.status_code}")
        result = _http._parse_response(response)
        if not isinstance(result, dict):
            raise ox._errors.InsufficientResponseError("Overpass did not return map data.")
        _http._save_to_cache(prepared, result, response.ok)
        return result

    @staticmethod
    def _is_server_failure(exc: Exception) -> bool:
        if isinstance(exc, (RequestException, ox._errors.ResponseStatusCodeError)):
            return True
        # Some OSMnx/server versions wrap unsuccessful responses in ValueError.
        message = str(exc).lower()
        return any(
            needle in message
            for needle in (
                "overpass", "gateway timeout", "server at capacity",
                "connection aborted", "connection reset", "read timed out",
                "proxy error", "temporarily unavailable", "http 502",
                "http 503", "http 504", "http 429", "bad gateway",
                "service unavailable", "remote disconnected",
            )
        )
