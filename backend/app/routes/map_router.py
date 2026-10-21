# backend/app/routes/map_router.py

from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas import map_schema
from app.services import map_service, auth_service
from app.models import user_model
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/route", response_model=map_schema.RouteResponse)
async def get_route(
    request_data: map_schema.RouteRequest,
    current_user: user_model.User = Depends(auth_service.get_current_user),
):
    """
    Provides route details (polyline, distance, duration) between two points.
    This endpoint is protected and requires user authentication.
    """
    logger.info(f"Route request from user {current_user.id}: "
                f"({request_data.start_lat}, {request_data.start_lng}) -> "
                f"({request_data.end_lat}, {request_data.end_lng})")
    
    # Validate coordinates before calling the service
    if not (-90 <= request_data.start_lat <= 90) or not (-180 <= request_data.start_lng <= 180):
        logger.error(f"Invalid start coordinates: {request_data.start_lat}, {request_data.start_lng}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid start coordinates: latitude must be between -90 and 90, longitude must be between -180 and 180",
        )
    
    if not (-90 <= request_data.end_lat <= 90) or not (-180 <= request_data.end_lng <= 180):
        logger.error(f"Invalid end coordinates: {request_data.end_lat}, {request_data.end_lng}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid end coordinates: latitude must be between -90 and 90, longitude must be between -180 and 180",
        )
    
    try:
        route_details = await map_service.get_route_from_ola(
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
