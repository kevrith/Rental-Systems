"""AI lease document intelligence via the Anthropic API (Sprint 22, US-096).

A single structured-output request per analysis — no agent loop, no tools —
since this is extraction over one document, not an open-ended task. The model
never touches `LeaseTemplate.body_html` directly: it returns suggestions, and
accepting one goes through `apply_suggestion` below, which is the only code
path that ever writes AI-authored text into a lease (US-096's acceptance
criteria are explicit that this must always be a human decision).
"""

import html
import json
import logging
import uuid
from datetime import UTC, datetime

import anthropic
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import OrgContext, assert_in_org
from app.core.config import settings
from app.core.redis import redis_client
from app.models.ai_analysis import (
    LeaseAnalysis,
    LeaseSuggestion,
    LeaseSuggestionCategory,
    LeaseSuggestionStatus,
)
from app.models.tenant import LeaseTemplate
from app.services import audit_service, lease_service

logger = logging.getLogger("rentflow.ai")


class AiServiceError(Exception):
    """Raised for anything that stops an analysis from completing — an
    unconfigured API key, a provider error, or a refusal."""


SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": (
                "2-4 sentence overall assessment of the lease, including any "
                "Kenya-specific legal requirements it should account for."
            ),
        },
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["missing_clause", "problematic_term", "unclear_language"],
                    },
                    "title": {"type": "string", "description": "Short label, under 10 words."},
                    "issue": {
                        "type": "string",
                        "description": "What is wrong or missing, and why it matters.",
                    },
                    "suggested_text": {
                        "type": ["string", "null"],
                        "description": (
                            "Plain-text drop-in clause or replacement wording. Null if the "
                            "suggestion is only a flag with nothing to insert."
                        ),
                    },
                },
                "required": ["category", "title", "issue", "suggested_text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "suggestions"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are a Kenyan property law assistant reviewing a residential or commercial lease "
    "template for a landlord or agency using RentFlow, a rental management platform. "
    "The body may contain Jinja-style {{ placeholders }} for tenant, unit and rent details — "
    "treat those as normal and do not flag them as unclear language. Review the document for: "
    "missing standard clauses a Kenyan residential or commercial lease would normally include "
    "(e.g. deposit terms, repairs and maintenance, termination, quiet enjoyment, governing law); "
    "potentially problematic or unenforceable terms; and unclear or ambiguous language. For each "
    "finding, give plain-text suggested wording the landlord could paste in directly — never HTML "
    "markup. Be specific and concise. Do not invent facts about the property or parties."
)


def _client() -> anthropic.AsyncAnthropic:
    if not settings.ANTHROPIC_API_KEY:
        raise AiServiceError("AI lease analysis is not configured — set ANTHROPIC_API_KEY.")
    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def _check_rate_limit(organization_id: uuid.UUID) -> None:
    """Each analysis is a real, billed model call with no other cost control
    in front of it — cap it per organization rather than leave it uncapped."""
    hour = datetime.now(UTC).strftime("%Y-%m-%dT%H")
    key = f"ai:analyze:rate:{organization_id}:{hour}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, 3600)
    if count > settings.AI_ANALYSIS_MAX_PER_HOUR:
        limit = settings.AI_ANALYSIS_MAX_PER_HOUR
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"AI analysis limit reached: {limit} per hour. Try again later.",
        )


def _build_prompt(template: LeaseTemplate) -> str:
    reference_clauses = ", ".join(clause["title"] for clause in lease_service.DEFAULT_CLAUSES)
    return (
        f'Lease template "{template.name}" (version {template.version}):\n\n'
        f"{template.body_html}\n\n"
        f"For reference, a standard RentFlow residential lease covers: {reference_clauses}."
    )


async def analyze_template(
    db: AsyncSession, context: OrgContext, template: LeaseTemplate, request: Request | None = None
) -> LeaseAnalysis:
    await _check_rate_limit(context.organization_id)
    client = _client()

    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            # Adaptive thinking's tokens count against this ceiling. On Sonnet
            # at "medium" effort a real analysis of a comprehensive template
            # used ~3.7k of 16k (1.3k of that thinking). max_tokens isn't
            # itself billed — actual usage is — but it does cap the worst-case
            # cost and latency of a runaway or unusually large template; 8000
            # keeps over 2x headroom above observed usage while halving that
            # worst case versus the original 16k ceiling.
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_prompt(template)}],
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": SUGGESTION_SCHEMA},
            },
        )
    except anthropic.RateLimitError as exc:
        raise AiServiceError("The AI service is rate-limited. Try again shortly.") from exc
    except anthropic.APIConnectionError as exc:
        raise AiServiceError("Could not reach the AI service. Try again shortly.") from exc
    except anthropic.APIStatusError as exc:
        raise AiServiceError(f"The AI service returned an error: {exc.message}") from exc

    if response.stop_reason == "refusal":
        detail = response.stop_details.explanation if response.stop_details else "the request was declined"
        raise AiServiceError(f"The AI service declined this analysis: {detail}")
    if response.stop_reason == "max_tokens":
        raise AiServiceError("The AI service's response was too long to complete. Try again.")

    try:
        text = next(block.text for block in response.content if block.type == "text")
        data = json.loads(text)
    except (StopIteration, json.JSONDecodeError) as exc:
        raise AiServiceError("The AI service returned an unreadable response.") from exc

    analysis = LeaseAnalysis(
        organization_id=context.organization_id,
        lease_template_id=template.id,
        requested_by_id=context.user.id,
        model_used=settings.ANTHROPIC_MODEL,
        summary=data.get("summary", ""),
    )
    db.add(analysis)
    await db.flush()

    for item in data.get("suggestions", []):
        try:
            category = LeaseSuggestionCategory(item["category"])
        except ValueError:
            continue
        db.add(
            LeaseSuggestion(
                organization_id=context.organization_id,
                lease_analysis_id=analysis.id,
                category=category,
                title=str(item.get("title", ""))[:255],
                issue=item.get("issue", ""),
                suggested_text=item.get("suggested_text") or None,
            )
        )

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action="lease_template.ai_analyzed",
        entity_type="lease_template",
        entity_id=template.id,
        actor=context.user,
        summary=f"AI analysis requested for lease template '{template.name}'",
        request=request,
    )
    await db.commit()
    # A plain refresh() would leave `suggestions` unloaded, and the response
    # schema serialises it — an unawaited lazy-load in an async session raises
    # MissingGreenlet rather than quietly working.
    refreshed = await db.scalar(
        select(LeaseAnalysis)
        .options(selectinload(LeaseAnalysis.suggestions))
        .where(LeaseAnalysis.id == analysis.id)
    )
    assert refreshed is not None
    return refreshed


async def list_analyses(db: AsyncSession, context: OrgContext, template_id: uuid.UUID) -> list[LeaseAnalysis]:
    rows = await db.scalars(
        select(LeaseAnalysis)
        .options(selectinload(LeaseAnalysis.suggestions))
        .where(
            LeaseAnalysis.organization_id == context.organization_id,
            LeaseAnalysis.lease_template_id == template_id,
        )
        .order_by(LeaseAnalysis.created_at.desc())
    )
    return list(rows)


async def resolve_suggestion(
    db: AsyncSession,
    context: OrgContext,
    suggestion_id: uuid.UUID,
    *,
    new_status: LeaseSuggestionStatus,
    request: Request | None = None,
) -> LeaseSuggestion:
    suggestion = assert_in_org(await db.get(LeaseSuggestion, suggestion_id), context, label="suggestion")
    if suggestion.status != LeaseSuggestionStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This suggestion has already been resolved"
        )

    if new_status == LeaseSuggestionStatus.ACCEPTED and suggestion.suggested_text:
        analysis = await db.get(LeaseAnalysis, suggestion.lease_analysis_id)
        if analysis is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
        template = assert_in_org(
            await db.get(LeaseTemplate, analysis.lease_template_id), context, label="lease template"
        )
        # The AI's suggested text is plain prose, not markup — escape it before
        # dropping it into a body that is otherwise the landlord's own HTML.
        addition = html.escape(suggestion.suggested_text).replace("\n", "<br>")
        template.body_html = f"{template.body_html}\n<p>{addition}</p>"
        template.version += 1

    suggestion.status = new_status
    suggestion.resolved_by_id = context.user.id
    suggestion.resolved_at = datetime.now(UTC)

    audit_service.record(
        db,
        organization_id=context.organization_id,
        action=f"lease_suggestion.{new_status.value}",
        entity_type="lease_suggestion",
        entity_id=suggestion.id,
        actor=context.user,
        summary=f"AI suggestion '{suggestion.title}' {new_status.value}",
        request=request,
    )
    await db.commit()
    await db.refresh(suggestion)
    return suggestion
