"""Phase 4 QA.

Sprint 19 (developer platform) shipped without this file — `PHASE_4_ORG_SCOPED_TABLES`
existed in `app.core.rls` with nothing checking it stayed in sync. This closes that
gap and extends it with what Sprint 20 (customer success) added, following the
same template `test_phase3.py` established: every new table carries RLS and an
`organization_id`, and every new Celery task is actually on the beat schedule.

`help_articles`, `feature_requests`, `feature_votes` and `changelog_entries` are
deliberately absent from `PHASE_4_TABLES` — like `task_runs`, they hold the same
content for every organisation and have no `organization_id` to scope by.
"""

from app.core.rls import ORG_SCOPED_TABLES, PHASE_4_ORG_SCOPED_TABLES
from app.models.base import Base

# Everything Phase 4 added that belongs to one organisation.
PHASE_4_TABLES = {
    # Sprint 19
    "api_keys",
    "webhook_endpoints",
    "webhook_deliveries",
    # Sprint 20
    "onboarding_progress",
    "organization_health_scores",
    "customer_success_alerts",
    "referral_codes",
    "referrals",
    "support_requests",
    "nps_survey_prompts",
    "milestone_events",
}

# Platform-wide tables Phase 4 added — same content for every organisation, so
# they are not part of the RLS-scoped set above.
PHASE_4_SHARED_TABLES = {
    "help_articles",
    "feature_requests",
    "feature_votes",
    "changelog_entries",
}

# The scheduled work Phase 4 introduced. Sprint 19's webhook delivery is
# push-triggered (`.delay(...)` from `webhook_service.dispatch`), not polled, so
# it has nothing on the beat schedule.
PHASE_4_TASKS = {
    "rentflow.compute_health_scores",
}


def test_every_phase_4_table_is_covered_by_row_level_security():
    declared = set(PHASE_4_ORG_SCOPED_TABLES)
    missing = PHASE_4_TABLES - declared
    assert not missing, f"Phase 4 tables with no RLS policy: {sorted(missing)}"
    assert PHASE_4_TABLES <= set(ORG_SCOPED_TABLES)


def test_every_phase_4_table_carries_an_organization_id():
    for name in sorted(PHASE_4_TABLES):
        table = Base.metadata.tables.get(name)
        assert table is not None, f"{name} is not in the model metadata"
        assert "organization_id" in table.c, f"{name} has no organization_id"


def test_platform_wide_phase_4_tables_are_deliberately_not_org_scoped():
    """The inverse of the two checks above: these tables must exist, have no
    `organization_id`, and must not be in the RLS-scoped set — a stray addition
    of either would either break the shared-content model or silently drop RLS
    protection a reviewer expected."""
    for name in sorted(PHASE_4_SHARED_TABLES):
        table = Base.metadata.tables.get(name)
        assert table is not None, f"{name} is not in the model metadata"
        assert "organization_id" not in table.c, f"{name} unexpectedly carries organization_id"
        assert name not in ORG_SCOPED_TABLES, f"{name} is in the RLS-scoped set but has no organization_id"


def test_every_phase_4_scheduled_task_is_actually_scheduled():
    from app.tasks.celery_app import celery_app

    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    missing = PHASE_4_TASKS - scheduled
    assert not missing, f"Tasks defined but never scheduled: {sorted(missing)}"
