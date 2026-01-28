"""BANT Lead Qualification Tool for Sales Conversations.

Analyzes conversation history to qualify leads using the BANT framework
(Budget, Authority, Need, Timeline).

The tool:
1. Queries conversation history from nlp_conversation_history table
2. Aggregates user messages into analysis text
3. Calls BANT service for qualification scoring
4. Returns qualification tier and actionable recommendations

Author: Odiseo Team
Version: 1.0.0
"""

import asyncio
from typing import Any

import httpx

from config import settings
from utils.db_async import fetchall_async
from utils.logger import get_logger
from utils.validation import validate_schema_name

logger = get_logger("mcp_tools_bant_analyzer")

# Qualification tiers based on overall_score
QUALIFICATION_TIERS = {
    "hot": {"min": 8, "max": 10, "label": "Hot Lead"},
    "warm": {"min": 6, "max": 7, "label": "Warm Lead"},
    "cold": {"min": 4, "max": 5, "label": "Cold Lead"},
    "unqualified": {"min": 0, "max": 3, "label": "Unqualified"},
}

# Recommendations per tier (Spanish for sales context)
RECOMMENDATIONS = {
    "hot": "Este cliente está listo para comprar. Prioriza el cierre: ofrece opciones de pago, confirma disponibilidad y agenda seguimiento inmediato.",
    "warm": "Buen prospecto. Continúa el nurturing: responde dudas, sugiere productos relacionados y mantén el interés.",
    "cold": "Prospecto en etapa temprana. Proporciona información general sin presionar. Enfócate en educarlo sobre el producto.",
    "unqualified": "No es un prospecto calificado actualmente. Responde amablemente pero no insistas en la venta. Puede reactivarse en el futuro.",
}


def _get_qualification_tier(overall_score: int) -> str:
    """Determine qualification tier from overall score.

    Args:
        overall_score: BANT overall score (0-10)

    Returns:
        Tier name: hot, warm, cold, or unqualified
    """
    for tier, bounds in QUALIFICATION_TIERS.items():
        if bounds["min"] <= overall_score <= bounds["max"]:
            return tier
    return "unqualified"


async def _get_identity_token(audience: str) -> str:
    """Fetch GCP identity token for IAM authentication.

    Uses metadata server on Cloud Run or ADC locally.

    Args:
        audience: Target service URL

    Returns:
        Identity token string
    """
    try:
        # Try Cloud Run metadata server first (fastest on Cloud Run)
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity",
                params={"audience": audience},
                headers={"Metadata-Flavor": "Google"},
            )
            response.raise_for_status()
            return response.text
    except Exception:
        # Fall back to ADC (local development)
        import google.auth.transport.requests
        from google.oauth2 import id_token

        request = google.auth.transport.requests.Request()
        token = await asyncio.to_thread(
            id_token.fetch_id_token, request, audience
        )
        return str(token)


async def _get_conversation_messages(
    conversation_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Retrieve conversation messages from database.

    Args:
        conversation_id: Telegram chat_id or session identifier
        limit: Maximum messages to retrieve (default: 50)

    Returns:
        List of message records with role and content
    """
    validate_schema_name(settings.SCHEMA_NAME)

    sql = f"""
        SELECT role, content, created_at
        FROM {settings.SCHEMA_NAME}.nlp_conversation_history
        WHERE conversation_id = $1
        ORDER BY created_at ASC
        LIMIT $2
    """

    try:
        rows = await fetchall_async(sql, conversation_id, limit)
        logger.info(
            "Retrieved %d messages for conversation %s",
            len(rows),
            conversation_id,
        )
        return rows
    except Exception as e:
        logger.error("Failed to retrieve conversation: %s", e)
        return []


def _aggregate_user_messages(messages: list[dict[str, Any]]) -> str:
    """Aggregate user messages into single text for BANT analysis.

    Args:
        messages: List of conversation messages

    Returns:
        Concatenated user messages
    """
    user_messages = [
        msg["content"]
        for msg in messages
        if msg.get("role") == "user" and msg.get("content")
    ]
    return "\n\n".join(user_messages)


async def analyze_lead_bant_async(
    conversation_id: str,
    user_id: str | None = None,
    channel: str = "telegram",
) -> dict[str, Any]:
    """Analyze conversation for BANT lead qualification.

    Retrieves conversation history, aggregates user messages, and calls
    the BANT service for lead scoring. Returns qualification tier and
    actionable recommendations.

    Args:
        conversation_id: Telegram chat_id or session identifier
        user_id: Optional user UUID for analytics
        channel: Source channel (telegram, whatsapp, etc.)

    Returns:
        Dict with:
        - analyzed: bool indicating success
        - lead_id: UUID of created lead record
        - overall_score: Weighted BANT score (0-10)
        - budget_score, authority_score, need_score, timeline_score: Individual scores
        - qualification: Tier name (hot, warm, cold, unqualified)
        - qualification_label: Human-readable tier label
        - recommendation: Actionable guidance for sales agent
        - message_count: Number of messages analyzed
        - error: Error message if analysis failed
    """
    if not settings.BANT_SERVICE_ENABLED:
        logger.warning("BANT service is disabled")
        return {
            "analyzed": False,
            "error": "BANT service is disabled",
        }

    # Get conversation messages
    messages = await _get_conversation_messages(conversation_id)

    if not messages:
        logger.warning("No messages found for conversation %s", conversation_id)
        return {
            "analyzed": False,
            "error": f"No conversation history found for {conversation_id}",
            "conversation_id": conversation_id,
        }

    # Aggregate user messages for analysis
    analysis_text = _aggregate_user_messages(messages)

    if len(analysis_text) < 10:
        logger.warning("Insufficient user messages for BANT analysis")
        return {
            "analyzed": False,
            "error": "Insufficient conversation content for analysis (minimum 10 characters required)",
            "conversation_id": conversation_id,
            "message_count": len(messages),
        }

    message_count = len([m for m in messages if m.get("role") == "user"])

    logger.info(
        "Analyzing lead: conversation_id=%s, user_messages=%d, text_length=%d",
        conversation_id,
        message_count,
        len(analysis_text),
    )

    # Call BANT service with IAM authentication
    try:
        token = await _get_identity_token(settings.BANT_SERVICE_URL)

        async with httpx.AsyncClient(
            timeout=settings.BANT_SERVICE_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                f"{settings.BANT_SERVICE_URL}/api/v1/leads/analyze",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "text": analysis_text,
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "channel": channel,
                    "message_count": message_count,
                },
            )
            response.raise_for_status()
            result = response.json()

    except httpx.TimeoutException:
        logger.error("BANT service timeout for conversation %s", conversation_id)
        return {
            "analyzed": False,
            "error": "BANT service timeout - try again later",
            "conversation_id": conversation_id,
        }
    except httpx.HTTPStatusError as e:
        logger.error(
            "BANT service HTTP error: %s - %s",
            e.response.status_code,
            e.response.text,
        )
        return {
            "analyzed": False,
            "error": f"BANT service error: {e.response.status_code}",
            "conversation_id": conversation_id,
        }
    except Exception as e:
        logger.error("BANT service call failed: %s", e)
        return {
            "analyzed": False,
            "error": f"Failed to analyze lead: {e!s}",
            "conversation_id": conversation_id,
        }

    # Determine qualification tier and recommendation
    overall_score = result.get("overall_score", 0)
    qualification = _get_qualification_tier(overall_score)
    tier_info = QUALIFICATION_TIERS[qualification]

    logger.info(
        "bant_analysis_complete: conversation_id=%s, overall_score=%d, tier=%s",
        conversation_id,
        overall_score,
        qualification,
    )

    return {
        "analyzed": True,
        "lead_id": result.get("id"),
        "overall_score": overall_score,
        "budget_score": result.get("budget_score", 0),
        "authority_score": result.get("authority_score", 0),
        "need_score": result.get("need_score", 0),
        "timeline_score": result.get("timeline_score", 0),
        "qualification": qualification,
        "qualification_label": tier_info["label"],
        "recommendation": RECOMMENDATIONS[qualification],
        "conversation_id": conversation_id,
        "message_count": message_count,
        "channel": channel,
    }
