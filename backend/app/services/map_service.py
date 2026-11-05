# backend/app/services/map_service.py

import httpx
from typing import Dict, Any
from app.core.config import settings
import logging

# Set up logging
logger = logging.getLogger(__name__)

OLA_DIRECTIONS_API_URL = "https://api.olamaps.io/routing/v1/directions/basic"


class RoutingProviderError(Exception):
    """The routing provider could not produce an answer (transport, HTTP, parse or non-SUCCESS status)."""


class RoutingProviderTimeout(RoutingProviderError):
    """The routing provider did not answer in time."""


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
        async with httpx.AsyncClient(timeout=30.0) as client:
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
        distance_meters = leg.get("distance", 0)
        duration_seconds = leg.get("duration", 0)

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
