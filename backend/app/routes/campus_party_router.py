# backend/app/routes/campus_party_router.py
"""Campus party router: /connections (+ accept/decline/withdraw), /parties/{id} (+ changes, note, report, cancel)."""

from fastapi import APIRouter

router = APIRouter()
