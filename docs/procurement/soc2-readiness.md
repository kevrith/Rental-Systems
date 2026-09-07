# SOC 2 readiness

**Status: not certified. This is a gap analysis and a path, not a report.**
Nobody should say "SOC 2 compliant" to a customer on the strength of this
document — that claim requires an accredited third-party auditor's opinion,
which does not exist yet. What exists is an honest mapping of the Trust
Services Criteria against what the system actually does today, so the actual
audit — when it happens — starts from a known position rather than a cold
start.

## Why this exists

An enterprise security questionnaire almost always asks "are you SOC 2
certified", and "not yet, here is our control mapping and our timeline" is a
materially better answer than silence or a vague "we take security
seriously." This document is what backs that answer.

## Scope decision

**Recommended initial scope: Security only** (not Availability, Processing
Integrity, Confidentiality or Privacy as additional criteria), for a **Type I**
report first, **Type II** twelve months later. Reasoning:

- Security is the criterion every customer's questionnaire actually asks
  about; the other four are worth adding once there is a customer base large
  enough to justify the extra audit scope and cost.
- Type I (design of controls, at a point in time) is achievable in weeks once
  the gaps below are closed. Type II (operating effectiveness, over a 6–12
  month observation window) cannot be rushed — the "12 months later" figure
  is the honest floor, not a target to compress.

## Control mapping

Mapped against the AICPA Trust Services Criteria (Security / Common Criteria,
"CC" series). Each row states what exists today, in this codebase, by file —
not a policy promise.

| Criterion | Control | Status | Evidence |
|---|---|---|---|
| CC1 — Control Environment | Named ownership of security decisions | ⚠️ Gap | No formal security policy document assigning roles; today it is one founder. Needs a written policy naming who approves access, who owns incident response, before an auditor will accept this criterion. |
| CC2 — Communication | Security policies published | ⚠️ Gap | This document set (`docs/procurement/`, `docs/legal/`) is the start of it. Needs a single internal security policy document (not yet written) that an employee/contractor signs off on. |
| CC3 — Risk Assessment | Documented risk assessment process | ⚠️ Gap | `docs/owasp-top-10-checklist.md` is a point-in-time technical risk review, not a recurring, dated risk register. Needs a lightweight quarterly review process. |
| CC4 — Monitoring | Ongoing control monitoring | ✅ Real | CI enforces lint, type-check, test coverage floor, dependency audit (`pip-audit`, `npm audit`), a Trivy container image scan, and CodeQL on every change (`.github/workflows/ci.yml`). Sentry + OpenTelemetry + Prometheus give operational monitoring (Sprint 26A). |
| CC5 — Control Activities | RBAC, segregation of duties | ✅ Real | `app/core/permissions.py` — role-based access control, enforced per-endpoint. Dual approval for cash above a threshold (`payment_service.py`) and maker-checker on maintenance spend are real segregation-of-duties controls; `app/services/approval_service.py` (Sprint 26A) generalises the same pattern into a configurable framework — a rule names a threshold, a required role, and how many distinct people must sign off — that a new feature can opt into without writing its own approval fields. The requester can never also be an approver on the same request. |
| CC6 — Logical & Physical Access | Access control, encryption, MFA | ✅ Mostly real | JWT + refresh rotation with reuse detection (`session_service.py`), SMS OTP and WebAuthn second factor, per-organisation encrypted credentials (`app/core/crypto.py`), Row Level Security at the database layer. Physical access: inherited from DigitalOcean's own SOC 2 report (a sub-processor's certification the Processor can reference, not duplicate) — **gap**: that inheritance needs to be documented explicitly, not assumed. |
| CC7 — System Operations | Incident detection & response, backup/recovery | ⚠️ Partial | Backup and a tested restore drill exist (`infra/backup/`). Breach detection and the 72-hour notification clock are real (`app/services/breach_service.py`). **Gap**: no written incident response *runbook* covering non-breach operational incidents (an outage, a bad deploy) — see `docs/procurement/disaster-recovery.md` once written (Sprint 26A item 15). |
| CC8 — Change Management | Controlled, tested changes | ✅ Real | Every change runs through CI gates before merge is possible in practice (branch protection is a GitHub-settings gap, not a technical one — see below). Alembic migrations are reviewed code, not manual SQL. |
| CC9 — Risk Mitigation (vendor risk) | Sub-processor oversight | ⚠️ Partial | `docs/legal/sub-processors.md` lists them; no formal vendor risk assessment has been performed on each one (e.g., "does Africa's Talking have its own SOC 2"). |

## What blocks starting a Type I audit today

In priority order:

1. **Branch protection and required reviews are not enabled on GitHub** — an
   account-level setting, not something committable to this repository. An
   auditor will ask "can one person push directly to `main` with no review",
   and today the answer is yes.
2. **No written security policy** naming roles, an access-review cadence, and
   an onboarding/offboarding checklist for anyone who gets production access.
3. **No formal, dated risk register** — `docs/owasp-top-10-checklist.md` is
   close, but needs to become a living, dated document reviewed on a stated
   cadence rather than a one-time pass.
4. **No incident response runbook** beyond the breach-specific process in
   `breach_service.py`.
5. **Single-operator company** — most SOC 2 auditors will still issue an
   opinion for a very small company, but expect extra scrutiny on
   segregation-of-duties criteria (CC5) precisely because one person can, in
   principle, do everything. The technical dual-approval controls already
   built (cash approval, maker-checker) are the right shape of answer to
   that scrutiny — the gap is that they need to extend to *code deployment*
   too (nobody currently has to approve Kelvin's own merges).

## Recommended path

| Step | What | Rough cost/time |
|---|---|---|
| 1 | Close the five gaps above (mostly writing, not building — the technical controls already exist) | 2–4 weeks, no external cost |
| 2 | Select an auditor (Vanta, Drata or Secureframe as a compliance-automation platform paired with an accredited CPA firm auditor is the common path for a company this size — not a specific recommendation, a category) | 1–2 weeks to select and contract |
| 3 | Type I audit | 4–8 weeks from kickoff to report, typically USD 10,000–25,000 all-in including the compliance platform subscription |
| 4 | Operate controls for the observation window | 6–12 months, no shortcut |
| 5 | Type II audit | 4–8 weeks, similar cost range to Type I |

## What this document is not

It is not a substitute for engaging an actual auditor, and it is not
something to hand a customer as proof of certification. Handed to a
prospective enterprise customer's security team as-is, the honest framing is:
"here is our control mapping and our SOC 2 timeline" — which is a real,
credible answer, and a materially better one than most vendors this size can
give.
