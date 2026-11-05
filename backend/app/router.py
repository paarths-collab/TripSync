# backend/app/router.py

from fastapi import APIRouter
from app.routes import health_router, auth_router,  pooling_router, pooling_ws_router, map_router
from app.routes import profile_router , services_router, message_router, chat_ws_router  # <-- ADD chat_ws_router
from app.routes import campus_requests_router, campus_party_router, campus_events_router

router = APIRouter()

# Include feature-specific routers here
router.include_router(health_router.router, prefix="/health", tags=["Health"])
router.include_router(auth_router.router, prefix="/auth", tags=["Authentication"])
router.include_router(pooling_router.router, prefix="/pool", tags=["Pooling"])
router.include_router(profile_router.router, prefix="/profile", tags=["Profile"]) 
router.include_router(services_router.router, prefix="/services", tags=["Services"])
router.include_router(map_router.router, prefix="/map", tags=["Maps"])
router.include_router(message_router.router, prefix="/chat", tags=["Chat"])

router.include_router(pooling_ws_router.router, tags=["Pooling WebSocket"])
router.include_router(chat_ws_router.router, tags=["Chat WebSocket"])

# Campus scheduling (shared-taxi parties); all endpoints live under /api/campus.
# Route order matters: events_router owns the literal /parties/active, so it is
# mounted BEFORE party_router's /parties/{party_id}.
router.include_router(campus_requests_router.router, prefix="/campus", tags=["Campus Requests"])
router.include_router(campus_events_router.router, prefix="/campus", tags=["Campus Events"])
router.include_router(campus_party_router.router, prefix="/campus", tags=["Campus Parties"])
