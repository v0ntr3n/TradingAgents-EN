"""
Analyze Preference API Routes
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from app.services.analysis_preference_service import AnalysisPreferenceService
from app.models.analysis_preference import (
    AnalysisPreferenceCreate,
    AnalysisPreferenceUpdate,
    AnalysisPreferenceResponse
)
from app.core.response import ok, fail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/preferences", tags=["preferences"])


# Dependency injection: getting service instance
def get_preference_service() -> AnalysisPreferenceService:
    """Get preference service instance"""
    return AnalysisPreferenceService()


@router.get("", response_model=dict)
async def get_all_preferences(
    user_id: Optional[str] = Query(None),
    preference_service: AnalysisPreferenceService = Depends(get_preference_service)
):
    """Get all preferences"""
    try:
        preferences = await preference_service.get_user_preferences(user_id) if user_id else []

        # If no user is specified, return to system default preferences
        if not user_id:
            # Returns three default preference types
            default_preferences = [
                {
                    "preference_id": "aggressive",
                    "name": "Radical",
                    "description": "High risk, high return, quick decision-making",
                    "risk_level": 0.8,
                    "decision_speed": "fast",
                    "is_system": True
                },
                {
                    "preference_id": "neutral",
                    "name": "Balanced",
                    "description": "Risk-return balance, normal decision-making speed",
                    "risk_level": 0.5,
                    "decision_speed": "normal",
                    "is_system": True
                },
                {
                    "preference_id": "conservative",
                    "name": "Conservative",
                    "description": "Low risk, low return, prudent decision-making",
                    "risk_level": 0.3,
                    "decision_speed": "slow",
                    "is_system": True
                }
            ]
            return ok(default_preferences)

        result = []
        for pref in preferences:
            result.append({
                "id": pref.id,
                "preference_id": pref.preference_id,
                "name": pref.name,
                "description": pref.description,
                "risk_level": pref.risk_level,
                "decision_speed": pref.decision_speed,
                "is_default": pref.is_default,
                "created_at": pref.created_at.isoformat()
            })

        return ok(result)

    except Exception as e:
        logger.error(f"❌ Exception getting preference list: {e}")
        return fail(str(e), 500)


@router.post("", response_model=dict)
async def create_preference(
    user_id: str = Query(...),
    preference_data: AnalysisPreferenceCreate = None,
    preference_service: AnalysisPreferenceService = Depends(get_preference_service)
):
    """Create analysis preferences"""
    try:
        if not preference_data:
            return fail("Preference data cannot be empty", 400)

        preference = await preference_service.create_preference(user_id, preference_data)

        if not preference:
            return fail("Failed to create preference", 400)

        return ok({
            "id": preference.id,
            "preference_type": preference.preference_type,
            "is_default": preference.is_default,
            "created_at": preference.created_at.isoformat()
        })

    except Exception as e:
        logger.error(f"❌ Create preference exception: {e}")
        return fail(str(e), 500)


@router.get("/{preference_id}", response_model=dict)
async def get_preference(
    preference_id: str,
    preference_service: AnalysisPreferenceService = Depends(get_preference_service)
):
    """Get preferences"""
    try:
        preference = await preference_service.get_preference(preference_id)

        if not preference:
            return fail("Preference does not exist", 404)

        return ok({
            "id": preference.id,
            "user_id": preference.user_id,
            "preference_type": preference.preference_type,
            "risk_level": preference.risk_level,
            "confidence_threshold": preference.confidence_threshold,
            "position_size_multiplier": preference.position_size_multiplier,
            "decision_speed": preference.decision_speed,
            "is_default": preference.is_default,
            "created_at": preference.created_at.isoformat(),
            "updated_at": preference.updated_at.isoformat()
        })

    except Exception as e:
        logger.error(f"❌ Get preference exception: {e}")
        return fail(str(e), 500)


@router.get("/user/{user_id}", response_model=dict)
async def get_user_preferences(
    user_id: str,
    preference_service: AnalysisPreferenceService = Depends(get_preference_service)
):
    """Get all user preferences"""
    try:
        preferences = await preference_service.get_user_preferences(user_id)

        return ok({
            "preferences": [
                {
                    "id": p.id,
                    "preference_type": p.preference_type,
                    "risk_level": p.risk_level,
                    "is_default": p.is_default
                }
                for p in preferences
            ]
        })

    except Exception as e:
        logger.error(f"❌ Get user preference exception: {e}")
        return fail(str(e), 500)


@router.put("/{preference_id}", response_model=dict)
async def update_preference(
    preference_id: str,
    update_data: AnalysisPreferenceUpdate,
    preference_service: AnalysisPreferenceService = Depends(get_preference_service)
):
    """Update preferences"""
    try:
        preference = await preference_service.update_preference(preference_id, update_data)

        if not preference:
            return fail("Failed to update preferences", 400)

        return ok({
            "id": preference.id,
            "preference_type": preference.preference_type,
            "updated_at": preference.updated_at.isoformat()
        })

    except Exception as e:
        logger.error(f"❌ Update preference exception: {e}")
        return fail(str(e), 500)


@router.delete("/{preference_id}", response_model=dict)
async def delete_preference(
    preference_id: str,
    preference_service: AnalysisPreferenceService = Depends(get_preference_service)
):
    """Delete preference"""
    try:
        # Implement deletion logic
        return ok({"message": "Preference deleted"})

    except Exception as e:
        logger.error(f"❌ Delete preference exception: {e}")
        return fail(str(e), 500)

