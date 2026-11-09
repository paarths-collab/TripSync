# backend/app/services/map_service.py

import httpx
import math
from typing import Dict, Any, Optional
from app.core.config import settings
from app.core.ttl_cache import MISSING, TTLCache
import logging

# Set up logging
logger = logging.getLogger(__name__)

OLA_DIRECTIONS_API_URL = "https://api.olamaps.io/routing/v1/directions/basic"
OLA_PLACES_BASE_URL = "https://api.olamaps.io/places/v1"
ROUTE_TIMEOUT_SECONDS = 30.0
PLACES_TIMEOUT_SECONDS = 10.0
MAX_PREDICTIONS = 10

# Shared, bounded, per-process caches (results do not depend on who asked).
places_cache = TTLCache(max_entries=settings.MAPS_CACHE_MAX_ENTRIES)
route_cache = TTLCache(max_entries=settings.MAPS_CACHE_MAX_ENTRIES)


def clear_caches() -> None:
    places_cache.clear()
    route_cache.clear()


def ola_client_kwargs(timeout: float) -> dict:
    """httpx.AsyncClient options for every Ola Maps call (honours OLA_MAPS_PROXY)."""
    kwargs: dict = {"timeout": timeout}
    proxy = getattr(settings, "OLA_MAPS_PROXY", None)
    if proxy:
        kwargs["proxy"] = proxy  # httpx >= 0.26 (``proxies`` was removed)
    return kwargs


class RoutingProviderError(Exception):
    """The routing provider could not produce an answer (transport, HTTP, parse or non-SUCCESS status)."""


class RoutingProviderTimeout(RoutingProviderError):
    """The routing provider did not answer in time."""


def parse_route_metric(value: Any) -> int:
    """Require an explicit finite, non-negative numeric provider metric."""
    if (
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not 0 <= value <= 2_147_483_647 or not math.isfinite(value)
    ):
        raise RoutingProviderError("Routing provider returned an invalid metric")
    return int(value)


def decode_polyline(encoded_polyline: str) -> list[tuple[float, float]]:
    """Decode polyline string to list of (lng, lat) coordinates."""
    points = []
    index = 0
    lat = 0
    lng = 0
    len_encoded = len(encoded_polyline)

    while index < len_encoded:
        shift = 0
        result = 0
        while True:
            byte = ord(encoded_polyline[index]) - 63
            index += 1
            result |= (byte & 0x1f) << shift
            shift += 5
            if not byte >= 0x20:
                break

        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift = 0
        result = 0
        while True:
            byte = ord(encoded_polyline[index]) - 63
            index += 1
            result |= (byte & 0x1f) << shift
            shift += 5
            if not byte >= 0x20:
                break

        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        # Append as (longitude, latitude) for GeoJSON compatibility
        points.append((lng / 1E5, lat / 1E5))

    return points


async def get_route_from_ola(
    start_lat: float, start_lng: float, end_lat: float, end_lng: float
) -> Dict[str, Any] | None:
    """
    Calls the OLA Directions API to get a route between two points.

    Returns None only when the provider answers SUCCESS with no routes (a genuine
    "no route"). Any provider failure raises RoutingProviderError (or
    RoutingProviderTimeout). Never returns a synthesized/fallback route.

    Nothing logged here includes the request URL, query params, API key or
    response body; only exception types and HTTP status codes.
    """
    # Validate coordinates
    if not (-90 <= start_lat <= 90) or not (-180 <= start_lng <= 180):
        logger.error("Invalid coordinates rejected (start)")
        return None

    if not (-90 <= end_lat <= 90) or not (-180 <= end_lng <= 180):
        logger.error("Invalid coordinates rejected (end)")
        return None

    # Format coordinates for Ola API
    origin_str = f"{start_lat},{start_lng}"
    destination_str = f"{end_lat},{end_lng}"

    # Ola Maps API parameters
    params = {
        "origin": origin_str,
        "destination": destination_str,
        "api_key": settings.OLA_MAPS_API_KEY,
        "alternatives": "false",  # We only need one route
        "steps": "false",         # We don't need step-by-step directions
        "overview": "full"        # Full geometry overview
    }

    headers = {
        "Content-Type": "application/json",
    }

    logger.info("Requesting route from routing provider")
    logger.debug("Route coordinates origin=%s destination=%s", origin_str, destination_str)

    try:
        async with httpx.AsyncClient(**ola_client_kwargs(ROUTE_TIMEOUT_SECONDS)) as client:
            # Use POST request as per Ola Maps API documentation
            response = await client.post(
                OLA_DIRECTIONS_API_URL,
                params=params,
                headers=headers
            )

        logger.info(f"Ola API Response Status: {response.status_code}")
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            raise RoutingProviderError("Routing provider returned an unexpected payload")

        # The /basic endpoint returns a simpler structure with status: "SUCCESS"
        if data.get("status") != "SUCCESS":
            logger.error(f"Routing provider returned non-SUCCESS status: {data.get('status')!r}")
            raise RoutingProviderError("Routing provider returned an error status")

        routes = data.get("routes")
        if not isinstance(routes, list):
            raise RoutingProviderError("Routing provider response has no routes list")
        if len(routes) == 0:
            logger.info("Routing provider reported no route between the given points")
            return None

        route = routes[0]

        # Get the geometry (overview_polyline)
        geometry = route.get("overview_polyline", "")
        if not geometry:
            raise RoutingProviderError("Routing provider route has no overview_polyline")

        # Get distance and duration from legs
        legs = route.get("legs", [])
        if not legs:
            raise RoutingProviderError("Routing provider route has no legs")

        leg = legs[0]  # Take the first leg

        # Extract distance and duration - they are direct values in the /basic endpoint
        distance_meters = parse_route_metric(leg.get("distance"))
        duration_seconds = parse_route_metric(leg.get("duration"))

        logger.info(f"Route found - Distance: {distance_meters}m, Duration: {duration_seconds}s")

        decoded_points = decode_polyline(geometry)
        logger.info(f"Decoded {len(decoded_points)} polyline points")

        return {
            "polyline": decoded_points,
            "distance_meters": int(distance_meters),
            "duration_seconds": int(duration_seconds),
            "is_fallback": False
        }

    except RoutingProviderError:
        raise
    except httpx.TimeoutException as e:
        logger.error(f"Routing provider request timed out ({type(e).__name__})")
        raise RoutingProviderTimeout("Routing provider timed out") from None
    except httpx.HTTPStatusError as e:
        logger.error(f"Routing provider returned HTTP {e.response.status_code}")
        raise RoutingProviderError("Routing provider unavailable") from None
    except Exception as e:
        logger.error(f"Routing provider call failed ({type(e).__name__})")
        raise RoutingProviderError("Routing provider unavailable") from None


async def get_route_cached(
    start_lat: float, start_lng: float, end_lat: float, end_lng: float
) -> Dict[str, Any] | None:
    """get_route_from_ola with a short TTL cache for found routes (key: coordinates to ~1 m)."""
    key = ("route",) + tuple(round(v, 5) for v in (start_lat, start_lng, end_lat, end_lng))
    cached = route_cache.get(key)
    if cached is not MISSING:
        logger.debug("Route cache hit")
        return cached
    result = await get_route_from_ola(start_lat, start_lng, end_lat, end_lng)
    if result:
        route_cache.set(key, result, settings.ROUTE_CACHE_TTL_SECONDS)
    return result


# ==================== PLACES (autocomplete / details / reverse geocode) ====================

class PlacesProviderError(Exception):
    """The places provider could not answer (transport, HTTP, parse or error status)."""


class PlacesProviderTimeout(PlacesProviderError):
    """The places provider did not answer in time."""


class PlaceNotFound(Exception):
    """The provider does not know the requested place_id."""


_OK_STATUSES = {"ok", "success", "zero_results"}


async def _places_get(path: str, params: dict, *, not_found_statuses: tuple = ()) -> dict:
    """GET an Ola Places endpoint and return its JSON object.

    Logs only exception types and HTTP status codes: never the URL, the query
    (it holds the API key, the search text or coordinates) or the body.
    """
    query = dict(params)
    query["api_key"] = settings.OLA_MAPS_API_KEY
    try:
        async with httpx.AsyncClient(**ola_client_kwargs(PLACES_TIMEOUT_SECONDS)) as client:
            response = await client.get(f"{OLA_PLACES_BASE_URL}/{path}", params=query)
    except httpx.TimeoutException as exc:
        logger.warning("Places provider timed out (%s)", type(exc).__name__)
        raise PlacesProviderTimeout("Places provider timed out") from None
    except Exception as exc:  # noqa: BLE001 - transport errors; messages may embed the URL
        logger.warning("Places provider request failed (%s)", type(exc).__name__)
        raise PlacesProviderError("Places provider request failed") from None

    if response.status_code in not_found_statuses:
        raise PlaceNotFound()
    if not 200 <= response.status_code < 300:
        logger.warning("Places provider returned HTTP %s", response.status_code)
        raise PlacesProviderError("Places provider returned an error status")
    try:
        payload = response.json()
    except ValueError:
        logger.warning("Places provider returned a non-JSON body (HTTP %s)", response.status_code)
        raise PlacesProviderError("Places provider returned an invalid response") from None
    if not isinstance(payload, dict):
        raise PlacesProviderError("Places provider returned an unexpected payload")
    status = payload.get("status")
    if status is not None and str(status).strip().lower() not in _OK_STATUSES:
        logger.warning("Places provider reported a non-ok status")
        raise PlacesProviderError("Places provider reported a failure")
    return payload


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _coordinate(value: Any, low: float, high: float) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        return None
    return float(value)


def _split_address(description: str) -> tuple[str, str]:
    head, sep, tail = description.partition(",")
    return head.strip(), tail.strip() if sep else ""


def normalize_prediction(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    place_id = _text(raw.get("place_id"))
    description = _text(raw.get("description"))
    if not place_id or not description:
        return None
    formatting = raw.get("structured_formatting") if isinstance(raw.get("structured_formatting"), dict) else {}
    fallback_main, fallback_secondary = _split_address(description)
    return {
        "place_id": place_id,
        "description": description,
        "main_text": _text(formatting.get("main_text")) or fallback_main,
        "secondary_text": _text(formatting.get("secondary_text")) or fallback_secondary,
    }


def _location(raw: dict) -> tuple[Optional[float], Optional[float]]:
    geometry = raw.get("geometry") if isinstance(raw.get("geometry"), dict) else {}
    location = geometry.get("location") if isinstance(geometry.get("location"), dict) else {}
    return _coordinate(location.get("lat"), -90, 90), _coordinate(location.get("lng"), -180, 180)


async def autocomplete(text: str, lat: Optional[float] = None, lng: Optional[float] = None) -> list[dict]:
    """Normalised predictions for ``text``, optionally biased towards (lat, lng)."""
    query_text = " ".join(text.split())
    bias = (round(lat, 2), round(lng, 2)) if lat is not None and lng is not None else None  # ~1 km
    key = ("autocomplete", query_text.lower(), bias)
    cached = places_cache.get(key)
    if cached is not MISSING:
        return cached
    params = {"input": query_text}
    if bias is not None:
        params["location"] = f"{bias[0]},{bias[1]}"
    logger.debug("Places autocomplete requested")
    payload = await _places_get("autocomplete", params)
    raw_predictions = payload.get("predictions")
    if raw_predictions is None:
        raw_predictions = []
    if not isinstance(raw_predictions, list):
        raise PlacesProviderError("Places provider returned no predictions list")
    predictions = [p for p in (normalize_prediction(r) for r in raw_predictions) if p][:MAX_PREDICTIONS]
    places_cache.set(key, predictions, settings.PLACES_CACHE_TTL_SECONDS)
    return predictions


async def place_details(place_id: str) -> dict:
    """{"place_id", "name", "address", "lat", "lng"}. Raises PlaceNotFound for unknown ids."""
    key = ("details", place_id)
    cached = places_cache.get(key)
    if cached is not MISSING:
        return cached
    logger.debug("Places details requested")
    payload = await _places_get("details", {"place_id": place_id}, not_found_statuses=(400, 404))
    result = payload.get("result")
    if result is None and str(payload.get("status", "")).strip().lower() == "zero_results":
        raise PlaceNotFound()
    if not isinstance(result, dict):
        raise PlaceNotFound()
    lat, lng = _location(result)
    if lat is None or lng is None:
        raise PlacesProviderError("Places provider returned a place without coordinates")
    address = _text(result.get("formatted_address"))
    name = _text(result.get("name")) or _split_address(address)[0]
    details = {
        "place_id": _text(result.get("place_id")) or place_id,
        "name": name or address,
        "address": address or name,
        "lat": lat,
        "lng": lng,
    }
    places_cache.set(key, details, settings.PLACES_CACHE_TTL_SECONDS)
    return details


async def reverse_geocode(lat: float, lng: float) -> dict:
    """{"address", "name"} for a point. Without a provider match, the coordinates are the label."""
    point = (round(lat, 5), round(lng, 5))  # ~1 m
    key = ("reverse",) + point
    cached = places_cache.get(key)
    if cached is not MISSING:
        return cached
    logger.debug("Places reverse geocode requested")
    payload = await _places_get("reverse-geocode", {"latlng": f"{point[0]},{point[1]}"})
    results = payload.get("results")
    if results is None:
        results = []
    if not isinstance(results, list):
        raise PlacesProviderError("Places provider returned no results list")
    first = next((r for r in results if isinstance(r, dict) and _text(r.get("formatted_address"))), None)
    if first is None:
        label = f"{point[0]:.5f}, {point[1]:.5f}"
        value = {"address": label, "name": label}
    else:
        address = _text(first.get("formatted_address"))
        name = _text(first.get("name")) or _split_address(address)[0]
        value = {"address": address, "name": name or address}
    places_cache.set(key, value, settings.PLACES_CACHE_TTL_SECONDS)
    return value
