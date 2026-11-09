# backend/app/routes/map_router.py

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.core import rate_limit
from app.core.errors import CodedErrorRoute, api_error
from app.schemas import map_schema
from app.services import map_service, auth_service
from app.models import user_model
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
# Places proxy: coded errors ({"detail": {"code", "message"}}) for every failure.
places = APIRouter(route_class=CodedErrorRoute)

@router.post(
    "/route",
    response_model=map_schema.RouteResponse,
    dependencies=[Depends(rate_limit.limit_by_user("route_user"))],
)
async def get_route(
    request_data: map_schema.RouteRequest,
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Provides route details (polyline, distance, duration) between two points.
    This endpoint is protected and requires user authentication.
    """
    # Coordinates and user ids are location data: never logged above DEBUG.
    logger.info("Route requested")
    logger.debug(
        "Route request user_id=%s start=(%s, %s) end=(%s, %s)",
        current_user.id,
        request_data.start_lat, request_data.start_lng,
        request_data.end_lat, request_data.end_lng,
    )
    
    # Validate coordinates before calling the service
    if not (-90 <= request_data.start_lat <= 90) or not (-180 <= request_data.start_lng <= 180):
        logger.error("Invalid coordinates rejected (start)")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid start coordinates: latitude must be between -90 and 90, longitude must be between -180 and 180",
        )
    
    if not (-90 <= request_data.end_lat <= 90) or not (-180 <= request_data.end_lng <= 180):
        logger.error("Invalid coordinates rejected (end)")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid end coordinates: latitude must be between -90 and 90, longitude must be between -180 and 180",
        )
    
    try:
        route_details = await map_service.get_route_cached(
            start_lat=request_data.start_lat,
            start_lng=request_data.start_lng,
            end_lat=request_data.end_lat,
            end_lng=request_data.end_lng,
        )

        if not route_details:
            logger.error("Route service returned None - no route found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No route could be found between the specified locations. Please verify that both locations are accessible by road and try again with different locations.",
            )

        logger.info(f"Route found successfully: {route_details['distance_meters']}m, {route_details['duration_seconds']}s")
        
        return map_schema.RouteResponse(
            status="success",
            route=map_schema.RouteDetails(**route_details)
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except map_service.RoutingProviderTimeout:
        logger.error("Routing provider timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Routing provider timed out",
        ) from None
    except map_service.RoutingProviderError:
        logger.error("Routing provider unavailable")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Routing provider unavailable",
        ) from None
    except Exception as e:
        logger.error(f"Unexpected error in route endpoint ({type(e).__name__})")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while calculating the route. Please try again later.",
        )



# --------------------------------------------------------------------------
# Places proxy: the app never sees the Ola Maps key. Search text and
# coordinates are user data and are never logged above DEBUG.
# --------------------------------------------------------------------------
def _places_unavailable():
    return api_error(502, "maps_unavailable", "The maps service is unavailable. Try again shortly.")


def _places_timeout():
    return api_error(504, "maps_timeout", "The maps service took too long to answer. Try again.")


def _validate_point(lat: Optional[float], lng: Optional[float], *, required: bool) -> None:
    if lat is None and lng is None and not required:
        return
    if lat is None or lng is None:
        raise api_error(422, "invalid_request", "lat and lng must be given together.")
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        raise api_error(422, "invalid_request", "lat must be within -90..90 and lng within -180..180.")


_places_dependencies = [Depends(rate_limit.limit_by_user("places_user"))]


@places.get(
    "/places/autocomplete",
    response_model=map_schema.AutocompleteResponse,
    dependencies=_places_dependencies,
)
async def places_autocomplete(
    input: str = Query(..., max_length=200),
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """Place suggestions for at least 3 characters of text, optionally biased to lat/lng."""
    if len(input.strip()) < 3:
        raise api_error(422, "invalid_request", "input must be at least 3 characters.")
    _validate_point(lat, lng, required=False)
    try:
        predictions = await map_service.autocomplete(input, lat, lng)
    except map_service.PlacesProviderTimeout:
        raise _places_timeout() from None
    except map_service.PlacesProviderError:
        raise _places_unavailable() from None
    return {"predictions": predictions}


@places.get(
    "/places/details",
    response_model=map_schema.PlaceDetailsResponse,
    dependencies=_places_dependencies,
)
async def places_details(
    place_id: str = Query(..., min_length=1, max_length=300),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """Name, address and coordinates of a place_id from autocomplete."""
    if not place_id.strip():
        raise api_error(422, "invalid_request", "place_id is required.")
    try:
        return await map_service.place_details(place_id.strip())
    except map_service.PlaceNotFound:
        raise api_error(422, "invalid_request", "Unknown place_id.") from None
    except map_service.PlacesProviderTimeout:
        raise _places_timeout() from None
    except map_service.PlacesProviderError:
        raise _places_unavailable() from None


@places.get(
    "/places/reverse-geocode",
    response_model=map_schema.ReverseGeocodeResponse,
    dependencies=_places_dependencies,
)
async def places_reverse_geocode(
    lat: float = Query(...),
    lng: float = Query(...),
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """A readable address for a point."""
    _validate_point(lat, lng, required=True)
    try:
        return await map_service.reverse_geocode(lat, lng)
    except map_service.PlacesProviderTimeout:
        raise _places_timeout() from None
    except map_service.PlacesProviderError:
        raise _places_unavailable() from None


router.include_router(places)
