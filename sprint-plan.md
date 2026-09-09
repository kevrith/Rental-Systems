# RentFlow Kenya — Detailed Development Sprint Plan
## Complete 12-Month Engineering Roadmap

---

> **Document Type:** Development Sprint Plan
> **Project:** RentFlow Kenya — Universal Rental Management Platform
> **Total Duration:** 12 Months (24 Sprints × 2 Weeks + Sprint 0)
> **Sprint Length:** 2 Weeks
> **Developer:** Kelvin — Avinaya Solutions
> **Stack:** React/TypeScript · FastAPI · PostgreSQL · Redis · Cloudflare R2

---

## How to Read This Document

Each sprint contains:
- 🎯 **Sprint Goal** — the single most important outcome
- 📖 **User Stories** — what each user type should be able to do
- 🔧 **Technical Tasks** — backend, frontend, and integration work
- ✅ **Acceptance Criteria** — definition of "done" per story
- 📦 **Sprint Deliverables** — what ships at end of sprint
- ⚠️ **Dependencies** — what must be done first
- 🧪 **Testing Focus** — what to test before moving on

**Story Point Scale:**
| Points | Effort | Time Estimate |
|--------|--------|---------------|
| 1 | Trivial | < 1 hour |
| 2 | Small | 1–3 hours |
| 3 | Medium | Half day |
| 5 | Large | 1 day |
| 8 | Complex | 2 days |
| 13 | Very Complex | 3–4 days |

**Target velocity per sprint:** 50–60 story points (solo developer)

---

## Sprint 0 — Project Foundation & Architecture Setup
**Duration:** 1 Week (Pre-Development)
**Goal:** Everything in place before writing a single line of product code

### 🔧 Technical Setup Tasks

**Development Environment**
- [x] Initialize Git repository with branching strategy (main, develop, feature/*, hotfix/*)
- [ ] Set up GitHub repository with branch protection rules on main and develop
- [x] Configure GitHub Actions CI/CD pipeline (lint → test → build → deploy)
- [x] Set up local development environment with Docker Compose
- [x] Configure pre-commit hooks (linting, formatting, type checking)

**Backend Foundation**
- [x] Initialize FastAPI project structure with recommended folder layout:
  ```
  /app
    /api          → route handlers
    /core          → config, security, database
    /models        → SQLAlchemy models
    /schemas       → Pydantic schemas
    /services      → business logic
    /tasks         → Celery background tasks
    /tests         → test suite
  ```
- [x] Set up PostgreSQL with Alembic for migrations
- [x] Configure Redis connection for caching and Celery
- [x] Set up Celery with Celery Beat for scheduled tasks
- [x] Configure environment variables and settings management
- [ ] Set up Sentry for error tracking
- [x] Configure CORS and security middleware

**Frontend Foundation**
- [x] Initialize React + TypeScript project with Vite
- [x] Configure Tailwind CSS with custom design tokens (colors, typography, spacing)
- [x] Set up Shadcn/UI component library (hand-rolled kit in `src/components/ui` instead — same conventions, no CLI dependency)
- [x] Configure React Query (TanStack Query) for data fetching
- [x] Set up Zustand for global state management
- [x] Configure React Router for navigation
- [x] Set up PWA with Workbox (manifest, service worker)
- [x] Configure ESLint + Prettier + TypeScript strict mode (using oxlint instead of ESLint; Prettier + TS strict are done)

**Infrastructure**
- [ ] Set up DigitalOcean account and initial droplet
- [ ] Configure Nginx with SSL (Let's Encrypt)
- [ ] Set up Cloudflare R2 bucket for file storage
- [ ] Configure staging and production environments
- [ ] Set up automated database backups (scripts, systemd timers and restore drill in `infra/backup/` and tested against the dev database — needs a host to install on and an R2 bucket to ship to)

**Database Architecture**
- [x] Design and document complete Entity Relationship Diagram (ERD)
- [x] Define multi-tenant isolation strategy (org_id on every table)
- [x] Plan Row Level Security (RLS) policies for PostgreSQL
- [x] Create initial migration with all base tables

**Sprint 0 Deliverable:** Running "Hello World" — both frontend and backend deployed to staging, CI/CD pipeline green, database connected. ✅

---

## PHASE 1 — CORE FOUNDATION
### Months 1–3 | Sprints 1–6
**Phase Goal:** A working platform that an individual landlord can use to replace their exercise book

---

### 📍 Phase 1 status — build complete

All six sprints are built, tested and verified end-to-end. Sprint checkboxes below
are ticked per task.

| Sprint | Scope | State |
|---|---|---|
| 1 | Auth, 2FA, sessions, RBAC, multi-tenancy, trial | ✅ Done |
| 2 | Properties, units, bulk creation, uploads, portfolio dashboard | ✅ Done |
| 3 | Caretaker invites, tenants, tenancies, lease PDFs | ✅ Done |
| 4 | M-Pesa STK push, cash payments, invoices, receipts, arrears | ✅ Done |
| 5 | Caretaker PWA, offline queue, meter readings, maintenance | ✅ Done |
| 6 | Tenant portal, push, notification workflows, financial dashboard | ✅ Done |

**Verification:** 148 backend tests passing · ruff, black and mypy clean ·
frontend typecheck and production build clean · golden path (register → property →
6 units → tenant → tenancy + lease PDF → invoice → payment + receipt → dashboard)
exercised against a live API.

**Multi-tenant isolation is enforced twice:** application-layer scoping (403 on
cross-tenant access, never 404) *and* PostgreSQL Row Level Security (23 policies).
See [`docs/data-model.md`](docs/data-model.md).

**Still open — all need Kelvin's own accounts or physical devices, not code:**

- GitHub branch protection on `main` / `develop`
- Sentry project + DSN
- DigitalOcean droplet, Nginx + Let's Encrypt, staging/production envs
- Cloudflare R2 bucket (code is written and falls back to local disk until keys exist)
- Automated database backups
- Safaricom Daraja sandbox credentials (the integration is complete and simulates
  locally without them)
- PWA testing on real Android and iOS Safari devices

Every third-party integration degrades gracefully: with no credentials, SMS and
WhatsApp log to the console, M-Pesa simulates a checkout, and file storage writes
to disk. Nothing is stubbed out — the same code paths run either way.

---

## Sprint 1 — Authentication & Multi-Tenant Foundation
**Weeks 1–2 | Story Points Target: 55**
**🎯 Sprint Goal:** Any user can register, verify their account, log in securely with 2FA, and be isolated in their own organization

---

### 📖 User Stories

**US-001 — Organization Registration** `[13 pts]`
*As a property owner or agency admin, I want to register my organization on RentFlow so that I can start managing my rental portfolio*

Acceptance Criteria:
- Registration form captures: full name, organization name, email, phone number, password
- Email verification link sent on registration (expires in 24 hours)
- SMS OTP sent on registration for phone number verification
- Organization record created with unique slug and default settings
- Owner role automatically assigned to registering user
- Welcome WhatsApp message sent after successful registration
- Registration fails gracefully with clear error messages on duplicate email/phone

**US-002 — Secure Login with 2FA** `[13 pts]`
*As any user, I want to log in securely with two-factor authentication so that my account is protected*

Acceptance Criteria:
- Login accepts email + password
- After valid password, SMS OTP sent to registered phone (expires in 5 minutes)
- Maximum 5 failed login attempts before 15-minute lockout
- Successful login returns JWT access token (15 min expiry) + refresh token (7 days)
- Device fingerprint stored on successful 2FA completion
- Known device skips 2FA (configurable — owner can enforce always)
- "Remember this device for 30 days" option available
- Suspicious login (new device/location) triggers WhatsApp alert

**US-003 — Role-Based Access Control** `[8 pts]`
*As a system, I want every API endpoint protected by role and organization so that no user can access another organization's data*

Acceptance Criteria:
- Every API request validates: JWT valid → user active → user belongs to org → user has permission
- Organization ID automatically injected into all database queries
- Attempting to access another org's data returns 403 (not 404)
- Permission matrix defined and enforced for all 8 user roles
- Unit tests covering cross-tenant access attempts

**US-004 — User Profile Management** `[5 pts]`
*As any user, I want to manage my profile so that my details are current*

Acceptance Criteria:
- User can update name, phone number (triggers re-verification), and profile photo
- Password change requires current password confirmation
- Account deletion request workflow (soft delete with 30-day grace period)

**US-005 — Session Management** `[8 pts]`
*As a user, I want to see and manage my active sessions so that I can revoke access from unknown devices*

Acceptance Criteria:
- Active sessions list shows: device name, location, last active, current session highlighted
- User can revoke any individual session or all other sessions
- Auto-logout after configurable inactivity period (default: 30 min for owner, 4 hours for caretaker)

**US-006 — Subscription Plan Setup** `[8 pts]`
*As a new account, I want to start a 30-day free trial automatically so that I can explore the platform before committing*

Acceptance Criteria:
- New organization starts on 30-day free trial automatically (no credit card required)
- Trial expiry date displayed prominently in dashboard
- 7-day, 3-day, and 1-day trial expiry reminders sent via WhatsApp + SMS
- Trial expiry locks new data creation (read-only mode) with upgrade prompt

### 🔧 Technical Tasks
- [x] Build auth service: register, verify-email, verify-phone, login, refresh-token, logout endpoints
- [x] Implement JWT with refresh token rotation
- [x] Build OTP service (generation, validation, expiry) using Redis
- [x] Implement organization multi-tenant middleware (inject org context on every request)
- [x] Build RBAC permission system with decorator-based enforcement on FastAPI routes
- [x] Create PostgreSQL RLS policies for all base tables
- [x] Build React auth flows: registration, email verification, login, 2FA, forgot password
- [x] Set up protected route wrapper in React (role-based UI rendering)
- [x] Implement Axios interceptor for token refresh on 401
- [x] Build session management UI (active sessions page)
- [x] Integrate Africa's Talking for OTP SMS delivery
- [x] Set up WhatsApp Business API connection and template registration
- [x] Write auth test suite (unit + integration tests for all auth flows)

### 📦 Sprint 1 Deliverables
- ✅ Complete registration and login flow live on staging
- ✅ 2FA working via SMS OTP
- ✅ Multi-tenant isolation verified with tests
- ✅ Trial plan automatically assigned on registration
- ✅ WhatsApp and SMS notifications connected

---

## Sprint 2 — Property & Unit Management
**Weeks 3–4 | Story Points Target: 55**
**🎯 Sprint Goal:** An owner can add their properties, define all units, and see their entire portfolio at a glance

---

### 📖 User Stories

**US-007 — Add Property** `[8 pts]`
*As a property owner, I want to add a property to my account so that I can start managing it*

Acceptance Criteria:
- Property form captures: name, type (residential/commercial/vehicle fleet/equipment), address, county, photos (up to 10), description, amenities checklist
- Google Maps integration for address lookup and coordinates capture
- Property saved with unique reference code auto-generated
- Up to 5 property photos uploadable directly to Cloudflare R2
- Property appears in owner's portfolio dashboard immediately

**US-008 — Add Units/Assets** `[13 pts]`
*As a property owner, I want to add individual units or assets under a property so that I can track each rentable item*

Acceptance Criteria:
- Unit form captures: unit number/name, type, size (sqm), floor, bedrooms, bathrooms, monthly rent, deposit amount, features
- Bulk unit creation: "This property has 24 identical units" → creates 24 units with sequential naming
- Each unit assigned a unique reference code
- Unit status defaults to "Vacant" on creation
- Unit photos uploadable (up to 5 per unit)
- Units displayed in a structured list under their property

**US-009 — Portfolio Dashboard** `[8 pts]`
*As a property owner, I want to see all my properties and key stats on one screen so that I understand my portfolio at a glance*

Acceptance Criteria:
- Dashboard shows: total properties, total units, occupied units, vacant units, occupancy rate %
- Property cards showing: name, total units, occupied/vacant breakdown, monthly rent potential
- Quick action buttons: Add Property, View Units, Add Tenant
- Mobile responsive — works perfectly on phone screen

**US-010 — Unit Status Management** `[5 pts]`
*As a property owner or caretaker, I want to update a unit's status so that the portfolio reflects current reality*

Acceptance Criteria:
- Statuses: Occupied, Vacant, Under Maintenance, Reserved
- Status change logged in audit trail with timestamp and user
- Vacancy date automatically set when unit status changes to Vacant
- Owner notified via push notification when caretaker changes unit status

**US-011 — Property & Unit Edit/Archive** `[5 pts]`
*As a property owner, I want to edit and archive properties and units so that my portfolio stays accurate*

Acceptance Criteria:
- All property and unit fields editable
- Archive (soft delete) available — archived items hidden from active views but retained in history
- Cannot archive a property with active tenancies (warning shown)
- Edit history tracked in audit log

**US-012 — File Upload Service** `[8 pts]`
*As the system, I want a reliable, secure file upload service so that all photos and documents are stored safely*

Acceptance Criteria:
- Files uploaded directly to Cloudflare R2 via pre-signed URLs (never through backend)
- File size limit: 10MB per file, 50MB per upload batch
- Accepted types: jpg, png, pdf, docx (validated server-side)
- Uploaded files accessible via signed expiring URLs (60-minute expiry)
- Virus scanning on upload (Phase 2 — note for later)

### 🔧 Technical Tasks
- [x] Build Property CRUD API endpoints with multi-tenant scoping
- [x] Build Unit CRUD API endpoints with bulk creation support
- [x] Implement Cloudflare R2 file upload service with pre-signed URL generation
- [x] Build image optimization pipeline (resize and compress on upload)
- [x] Create portfolio dashboard API with aggregated stats
- [x] Build Property management UI (list, add, edit, view)
- [x] Build Unit management UI (list, add, edit, bulk add)
- [x] Build portfolio dashboard with property cards and stats
- [x] Implement file upload component (drag-drop + camera on mobile)
- [x] Write property and unit API tests

### 📦 Sprint 2 Deliverables
- ✅ Owner can add properties and units
- ✅ Portfolio dashboard showing real stats
- ✅ Photo upload working via Cloudflare R2
- ✅ Unit status tracking working

---

## Sprint 3 — Tenant Management & Lease Generation
**Weeks 5–6 | Story Points Target: 55**
**🎯 Sprint Goal:** A caretaker can onboard a new tenant, capture all their details, and generate a lease agreement ready for signing

---

### 📖 User Stories

**US-013 — Invite Caretaker** `[5 pts]`
*As a property owner, I want to invite a caretaker and assign them to specific properties so that they can operate on my behalf*

Acceptance Criteria:
- Owner enters caretaker name, phone number, and selects assigned properties
- Invitation SMS sent to caretaker with one-click registration link
- Caretaker sets their own password on first login
- Caretaker access scoped strictly to assigned properties (cannot see others)
- Owner can revoke caretaker access at any time

**US-014 — Tenant Profile Creation** `[8 pts]`
*As a caretaker or owner, I want to create a complete tenant profile so that all tenant information is captured digitally*

Acceptance Criteria:
- Tenant form captures: full name, phone, email (optional), national ID number, ID photo, passport photo, employment details, emergency contact details
- KYC documents uploadable (National ID front/back, passport photo)
- Tenant assigned a unique reference number
- Tenant profile searchable by name, phone, or ID number
- Duplicate phone/ID number detection with warning

**US-015 — Create Tenancy & Link Tenant to Unit** `[8 pts]`
*As a caretaker or owner, I want to create a tenancy record linking a tenant to a unit so that the rental relationship is formally recorded*

Acceptance Criteria:
- Tenancy form captures: start date, end date (or "open-ended"), monthly rent, deposit amount, billing day (day of month rent is due), payment method preference
- Selected unit status automatically changes from Vacant to Occupied
- Tenancy reference number auto-generated
- Cannot create tenancy for an already occupied unit
- Previous tenancy history preserved when unit is re-tenanted

**US-016 — Lease Agreement Generation** `[13 pts]`
*As a property owner or caretaker, I want the system to automatically generate a lease agreement from the tenancy details so that I don't have to type it manually*

Acceptance Criteria:
- Lease generated as professional PDF automatically on tenancy creation
- Template includes: landlord details, tenant details, property address, unit number, monthly rent, deposit, lease start/end date, standard terms and conditions
- Owner can customize: their company letterhead, logo upload, and specific clauses
- Generated PDF stored in tenant's document vault automatically
- Lease PDF downloadable immediately after generation

**US-017 — Tenant List & Search** `[5 pts]`
*As an owner or caretaker, I want to search and filter my tenants so that I can find anyone quickly*

Acceptance Criteria:
- Tenant list searchable by name, phone, unit number, property
- Filter by status: active, expiring, vacated
- Tenant record shows: current unit, rent amount, payment status, lease end date
- Exportable to CSV

**US-018 — Tenancy Lifecycle Tracking** `[5 pts]`
*As an owner, I want the system to track each tenancy's stage so that I always know the status of every unit*

Acceptance Criteria:
- Tenancy statuses: Active, Expiring Soon (within 60 days), Expired, Vacated
- Status automatically calculated from dates — no manual updates needed
- Expiring tenancies highlighted in dashboard

### 🔧 Technical Tasks
- [x] Build User invitation flow (caretaker invite, magic link, first-time setup)
- [x] Build Tenant CRUD API endpoints
- [x] Build Tenancy CRUD API endpoints with unit status side effects
- [x] Build PDF generation service using WeasyPrint (lease template engine)
- [x] Create default lease template with variable substitution
- [x] Build template customization system (logo upload, clause editor)
- [x] Store generated PDFs in Cloudflare R2 with tenant reference
- [x] Build Tenant management UI (list, add, edit, view profile)
- [x] Build Tenancy creation wizard (multi-step form: select unit → tenant details → terms → generate lease)
- [x] Build lease preview in browser before download
- [x] Write tenant and tenancy API tests

### 📦 Sprint 3 Deliverables
- ✅ Caretaker invitation and onboarding working
- ✅ Full tenant profile creation with document upload
- ✅ Tenancy creation linking tenant to unit
- ✅ Automatic professional lease PDF generated on tenancy creation
- ✅ Tenant list and search working

---

## Sprint 4 — M-Pesa Integration & Payment Management
**Weeks 7–8 | Story Points Target: 55**
**🎯 Sprint Goal:** Tenants can pay rent via M-Pesa and receive instant WhatsApp receipts — the most critical feature of the entire platform

---

### 📖 User Stories

**US-019 — M-Pesa STK Push Payment** `[13 pts]`
*As a tenant, I want to receive an M-Pesa payment prompt on my phone so that I can pay my rent with just my PIN*

Acceptance Criteria:
- Tenant or caretaker initiates STK push from the system
- System calls Safaricom Daraja STK Push API with correct tenant phone and amount
- Tenant receives M-Pesa prompt on phone within 10 seconds
- After tenant enters PIN, Daraja webhook received by system within 30 seconds
- Payment automatically marked as confirmed on webhook receipt
- Transaction reference verified against Daraja API before marking paid
- Failed or cancelled payments shown with clear error message and retry option
- Duplicate transaction detection (same M-Pesa reference cannot be recorded twice)

**US-020 — Cash Payment Recording** `[8 pts]`
*As a caretaker, I want to record cash payments I collect so that they appear in the system and the tenant is notified*

Acceptance Criteria:
- Caretaker selects tenant, enters amount received, enters date of payment, adds optional notes
- System records payment against current invoice
- Tenant immediately receives WhatsApp + SMS confirmation: "Your cash payment of KES X has been recorded by [Caretaker Name] for [Property/Unit]. Reference: [REF]"
- Caretaker cash limit enforced (owner-configurable) — amounts above limit show warning and owner notification
- Receipt downloadable immediately after recording

**US-021 — Invoice Generation** `[8 pts]`
*As the system, I want to automatically generate monthly invoices for every active tenancy so that every tenant always knows exactly what they owe*

Acceptance Criteria:
- Invoice automatically generated on the billing day (day of month) for each active tenancy
- Invoice itemizes: rent, water/utility charges (if any), any arrears from previous month, total due
- Invoice reference number generated (format: INV-YYYY-MM-XXXXX)
- Tenants notified of new invoice via WhatsApp with PDF attachment
- Invoice status: Pending → Partially Paid → Paid
- Partial payments tracked — balance carried to next invoice

**US-022 — Arrears Tracking** `[8 pts]`
*As a property owner, I want to see who owes money and how much so that I can take action on defaulters*

Acceptance Criteria:
- Arrears report shows: tenant name, unit, days overdue, amount owed, last payment date
- Aging analysis: Current, 1–30 days, 31–60 days, 61–90 days, 90+ days (colour-coded)
- Total portfolio arrears KES shown on dashboard
- One-click send reminder to individual or all defaulters
- Arrears exportable to CSV/PDF

**US-023 — Enterprise Receipt Generation** `[8 pts]`
*As a tenant, I want to receive a professional receipt immediately after every payment so that I have proof of payment*

Acceptance Criteria:
- Receipt generated automatically on every payment confirmation (M-Pesa, cash, or bank)
- Receipt includes: receipt number, date/time, tenant name, unit, property, payment amount, payment method, M-Pesa reference (if applicable), balance remaining, landlord details
- Receipt professional branding (landlord logo if configured)
- Receipt delivered via WhatsApp as PDF within 5 seconds of payment confirmation
- Receipt also available for download from tenant portal anytime
- Receipt tamper-evident (cryptographically signed, cannot be edited)

### 🔧 Technical Tasks
- [ ] Set up Safaricom Daraja API account and sandbox credentials
- [x] Build M-Pesa STK Push service (initiate payment, handle callback)
- [x] Build Daraja webhook handler (payment confirmation endpoint)
- [x] Implement payment verification against Daraja Query API
- [x] Build transaction duplicate detection (Redis-based idempotency)
- [x] Build cash payment recording API with caretaker limit enforcement
- [x] Build automated invoice generation service (Celery task, runs daily)
- [x] Build receipt PDF generation service (professional template)
- [x] Implement WhatsApp receipt delivery (PDF attachment via WhatsApp API)
- [x] Build arrears calculation service (runs on payment events and daily)
- [x] Build payment management UI (record payment, payment history)
- [x] Build invoice list and detail UI
- [x] Build arrears dashboard with aging analysis
- [x] Write comprehensive M-Pesa flow tests (including webhook simulation)

### 📦 Sprint 4 Deliverables
- ✅ M-Pesa STK Push working end-to-end (tested in Daraja sandbox)
- ✅ Cash payment recording with tenant confirmation via WhatsApp
- ✅ Monthly invoices auto-generated
- ✅ Professional receipts delivered via WhatsApp in under 5 seconds
- ✅ Arrears tracking with aging analysis working

---

## Sprint 5 — Caretaker PWA & Meter Readings
**Weeks 9–10 | Story Points Target: 50**
**🎯 Sprint Goal:** A caretaker can use RentFlow from their phone like a native app — offline when needed — to record meter readings, inspections, and maintenance requests

---

### 📖 User Stories

**US-024 — Caretaker PWA Mobile Interface** `[13 pts]`
*As a caretaker, I want a mobile-first app-like experience so that I can complete my daily tasks quickly and easily on my phone*

Acceptance Criteria:
- PWA installable from browser ("Add to Home Screen") on Android and iOS
- Caretaker home screen shows: today's tasks, units requiring attention, recent activity
- Navigation: Today's Tasks, Units, Payments, Inspections, Maintenance, Meter Readings
- All touch targets minimum 44px — usable with one thumb
- Loading time under 2 seconds on 3G connection
- Works in portrait orientation optimized (landscape supported)

**US-025 — Offline Capability** `[13 pts]`
*As a caretaker, I want the app to work even when I have no internet so that I can keep working in areas with poor connectivity*

Acceptance Criteria:
- Core caretaker flows available offline: record payment, record meter reading, create maintenance request, capture inspection notes
- Data queued locally (IndexedDB) when offline
- Sync status indicator always visible at top of screen (green = synced, orange = pending sync, red = sync error)
- Automatic sync triggered when internet connection restored
- Conflict notification if a sync conflict is detected (e.g., unit status changed by someone else)
- Maximum offline data age: 7 days (older unsynced data prompts warning)

**US-026 — Meter Reading Capture** `[8 pts]`
*As a caretaker, I want to record water and electricity meter readings each month so that utility bills are automatically calculated*

Acceptance Criteria:
- Caretaker selects property → unit → opens meter reading form
- Form shows: previous reading (pre-filled), date of reading, current reading field, photo capture button
- Photo of meter required before submission (enforced)
- System auto-calculates consumption (current - previous) and billing amount based on configured unit rate
- Reading submitted → billing automatically added to tenant's next invoice
- Previous and current readings stored with timestamp and photo
- Reading history per unit viewable

**US-027 — Maintenance Request from Caretaker** `[8 pts]`
*As a caretaker, I want to submit a maintenance request for a unit so that the owner is aware and the job can be tracked*

Acceptance Criteria:
- Caretaker selects unit, describes issue, selects category (plumbing/electrical/structural/other), sets priority (emergency/urgent/routine)
- Minimum one photo required for non-routine requests
- Request submitted → owner receives WhatsApp notification immediately
- Caretaker can view status of all submitted requests
- Emergency requests trigger immediate WhatsApp alert to owner (marked URGENT)

**US-028 — Caretaker Activity Tracking** `[8 pts]`
*As a property owner, I want to see everything my caretaker does in the system so that I have full accountability*

Acceptance Criteria:
- Every caretaker action logged: what, when, which unit, GPS coordinates (if enabled)
- Owner receives daily summary WhatsApp at 7pm: "Today's activity for [Caretaker Name]: X payments recorded, X meter readings, X maintenance requests"
- Caretaker login time tracked — inactivity alert to owner if caretaker hasn't logged in for 3+ days
- Owner can view full caretaker activity log per day, week, or month

### 🔧 Technical Tasks
- [x] Configure Workbox service worker for offline caching strategies
- [x] Implement IndexedDB data persistence layer for offline queue
- [x] Build background sync for offline-queued actions
- [x] Build sync conflict detection and resolution UI
- [x] Implement PWA install prompt (custom, not browser default)
- [x] Build mobile navigation shell for caretaker interface
- [x] Build meter reading form with camera integration and GPS tagging
- [x] Build utility billing calculation service (auto-generates invoice line item)
- [x] Build maintenance request form with photo upload
- [x] Build caretaker activity logging service (middleware layer)
- [x] Build daily activity summary Celery task (scheduled 7pm daily)
- [x] Build caretaker dashboard UI (today's tasks, recent activity)
- [ ] Test PWA on multiple Android devices and iOS Safari

### 📦 Sprint 5 Deliverables
- ✅ PWA installable on Android and iOS
- ✅ Offline mode working — data syncs when internet restored
- ✅ Meter reading capture with mandatory photo and auto-billing
- ✅ Maintenance request submission with owner WhatsApp alert
- ✅ Daily caretaker activity summary delivered to owner

---

## Sprint 6 — Tenant Portal, Notifications & Basic Dashboard
**Weeks 11–12 | Story Points Target: 50**
**🎯 Sprint Goal:** Tenants have their own self-service portal, all communication channels are fully connected, and the owner sees a complete financial dashboard — Phase 1 is DONE

---

### 📖 User Stories

**US-029 — Tenant Self-Service Portal** `[13 pts]`
*As a tenant, I want my own portal where I can pay rent, download receipts, and submit requests so that I don't need to visit the caretaker for everything*

Acceptance Criteria:
- Tenant portal accessible via PWA (installable on phone)
- Home screen shows: current balance, next rent due date, property/unit name
- "Pay Rent" button prominent — triggers M-Pesa STK push in 2 taps
- Payment history: all past payments with receipt download
- Maintenance request form with photo upload
- Lease agreement viewable and downloadable as PDF
- Profile page: personal details, payment preferences
- Tenant receives invitation via WhatsApp/SMS with one-click portal access link

**US-030 — Push Notification System** `[8 pts]`
*As any user, I want to receive push notifications on my phone so that I'm instantly informed of important events*

Acceptance Criteria:
- PWA push notifications working on Android (Chrome) and iOS (Safari 16.4+)
- Notification types working: payment confirmed, rent reminder, maintenance update, lease expiry alert
- Notifications clickable — open to relevant section of app
- Notification preferences manageable (user can choose which types to receive)
- Unread notification count visible on app icon (badge)

**US-031 — Automated Notification Workflows** `[8 pts]`
*As the system, I want to send the right message to the right person at the right time so that no important event is missed*

Acceptance Criteria:
- Rent reminder sequence working: 7 days before, 3 days before, on due date (via WhatsApp + SMS)
- Payment confirmation sent within 5 seconds of payment (WhatsApp + SMS)
- Lease expiry alerts: 90, 60, 30, and 14 days before end date (WhatsApp)
- Maintenance request status updates sent to tenant on change
- All notifications logged in notification history with delivery status

**US-032 — Owner Financial Dashboard** `[13 pts]`
*As a property owner, I want a real-time financial dashboard so that I can see my portfolio's financial performance instantly*

Acceptance Criteria:
- Dashboard KPI cards: Total Expected Rent, Total Collected, Collection Rate %, Total Arrears
- Monthly income chart (bar chart: last 6 months)
- Top defaulters list (tenant name, amount owed, days overdue)
- Occupancy rate dial/gauge (% occupied of all units)
- Recent payments list (last 10 payments across portfolio)
- All data real-time — refreshes without page reload
- Dashboard mobile-responsive (works perfectly on phone)

**US-033 — Vacating Notice Workflow** `[8 pts]`
*As a tenant, I want to submit my notice to vacate digitally so that the process is formal and documented*

Acceptance Criteria:
- Tenant submits notice via portal: selects move-out date, adds reason (optional)
- System validates notice period (checks lease terms — e.g., 30-day notice required)
- Owner and caretaker notified via WhatsApp immediately
- Notice acknowledged digitally — stored in tenant's document vault
- Caretaker prompted to schedule move-out inspection
- Unit status set to "Vacating" with expected vacancy date visible on dashboard

### 🔧 Technical Tasks
- [x] Build tenant portal PWA shell and navigation
- [x] Build tenant home screen with balance and payment button
- [x] Build tenant payment history and receipt download
- [x] Build tenant maintenance request form
- [x] Build tenant lease document viewer
- [x] Implement Web Push API (VAPID keys, push subscription management)
- [x] Build notification dispatch service (WhatsApp, SMS, push unified interface)
- [x] Build notification scheduling with Celery Beat (rent reminders, lease alerts)
- [x] Build notification history and preferences API + UI
- [x] Build financial dashboard API with real-time aggregations
- [x] Build dashboard UI with Recharts (income chart, KPI cards)
- [x] Build vacating notice API and workflow
- [x] End-to-end testing of complete tenant payment flow

### 🏁 Phase 1 Complete — First Paying Customer Milestone
**All of Phase 1 deliverables:**
- ✅ Multi-tenant SaaS with organization onboarding
- ✅ Secure authentication with 2FA
- ✅ Property and unit management
- ✅ Tenant onboarding and lease generation
- ✅ M-Pesa real-time payment reconciliation
- ✅ Enterprise receipt generation via WhatsApp
- ✅ Caretaker mobile PWA with offline capability
- ✅ Tenant self-service portal
- ✅ Automated notification workflows
- ✅ Owner financial dashboard

---

## PHASE 2 — ENTERPRISE FEATURES
### Months 4–6 | Sprints 7–12
**Phase Goal:** Platform ready for professional property management agencies

---

### 📍 Phase 2 status — build complete

Audited against the codebase on 2026-09-04.
**All 71 technical tasks are ticked.**

| Sprint | Scope | Backend | Frontend |
|---|---|---|---|
| 7 | Agency mode, owner profiles, portal invitation, agency dashboard | ✅ Done | ✅ Done |
| 8 | Trust accounting, disbursements, management fees | ✅ Done | ✅ Done |
| 8 | Owner statement PDF, M-Pesa B2C payout, approval workflow | ✅ Done | ✅ Done |
| 9 | Digital signatures + OTP, signing security tests | ✅ Done | ✅ Done |
| 9 | Document vault, lease template editor + preview | ✅ Done | ✅ Done |
| 10 | Move-in/move-out inspections, comparison, deductions | ✅ Done | ✅ Done |
| 11 | Late fee automation, analytics, cash flow forecasting | ✅ Done | ✅ Done |
| 11 | KRA eTIMS, demand letters | ✅ Done | ✅ Done |
| 12 | Recurring task engine, lease renewal detection | ✅ Done | ✅ Done |
| 12 | Renewal auto-generation, caretaker performance, task monitoring | ✅ Done | ✅ Done |

**Verification:** 260 backend tests passing · ruff, black and mypy clean across
100 source files · frontend typecheck, oxlint and production build clean.
The migration chain is exercised end-to-end by `tests/test_migrations.py`, which
asserts a single head, that every model table exists, that each enum type carries
the Python member names, and that all 26 org-scoped tables have an isolation
policy.

**Screens shipped:**
- `/agency`, `/agency/owners/*`, `/agency/disbursements` — review → approve →
  M-Pesa payout → statement, with rejection reasons and failure causes surfaced
- `/owner-portal` — Mode 3 read-only view with itemised statements
- `/tenants/:id/documents`, `/properties/:id/documents` — the document vault,
  with search, tags, version history, WhatsApp delivery and storage usage
- `/lease-templates` — rich-text editor with a placeholder palette and a
  server-rendered PDF preview filled with sample data
- `/inspections`, `/inspections/new`, `/inspections/:id` — one-room-at-a-time
  capture on a phone, and the move-in/move-out comparison viewer with the
  deposit deduction form beneath it
- `/analytics` — revenue, collection rate, forecast and property comparison
- `/settings/etims` — credentials plus the submission report
- `/automation`, `/team/performance`, `/renew/:token` — task monitoring,
  caretaker scores, and the tenant-facing renewal accept/decline page

**Defects found and fixed this phase:**
- **Late fees never applied.** `late_fee_service` read `prop.late_fee_type`
  through a `getattr` default. The columns existed in the Phase 2 migration but
  no model mapped them, so the lookup always returned None and every late fee
  evaluated to zero. The column is now a real enum with a per-property cap, and
  the calculator bounds a fee by both the cap and the outstanding balance.
- **A signing request could target another organisation's document.** The signing
  link is public and unauthenticated, so nothing downstream could catch it: org B
  could raise a request against org A's lease and have a stranger sign it.
  `create_signing_request` now proves ownership of both the document and the
  tenancy, answering 404 rather than 403.
- **Local-storage download links were unsigned.** The R2 backend signed reads with
  a 60-minute expiry; the local backend served any object to anyone who guessed a
  key. Both now issue HMAC-signed, expiring URLs, so the difference between
  development and production is not a security boundary.
- **Disbursements could be paid without review.** Any pending payout could be
  marked paid. A payout now moves PENDING → APPROVED → PROCESSING → COMPLETED,
  approval refuses a zero or negative net, and rejection records a reason.
- **The B2C result callback had no idempotency gate.** Safaricom re-delivers
  results; a duplicate would have settled a disbursement twice. Now claimed
  through Redis `SET NX`, like the STK callback.
- **The demand letter sweep discarded its own work.** A rollback for one bad
  tenancy rolled back every letter already written in the same transaction. It
  now commits per tenancy.
- **The move-out comparison PDF was never generated** — `generate_comparison_pdf`
  existed and nothing called it. Now produced on submit, alongside the report PDF.
- **Deposit deductions were unbounded** — a deduction could exceed the deposit
  held, or be negative, or be set on an unsubmitted inspection. All three are now
  refused.
- Two `except Exception: pass` blocks (signature overlay, inspection PDF) hid real
  failures. Both now log; neither blocks the operation it was guarding.

**Deliberate limits:**
- KRA eTIMS runs against the sandbox host until production credentials exist. The
  submission, retry, backoff, abandonment and reporting paths are all exercised;
  what is untested against the real endpoint is the response shape.
- Signature overlay appends a signature page rather than compositing onto the
  original page. `pypdf` would allow true compositing; the audit trail is
  unaffected either way.

---

## Sprint 7 — Agency Mode & Multi-Owner Account Management
**Weeks 13–14 | Story Points Target: 55**
**🎯 Sprint Goal:** A property management agency can set up their account, add all their client owners as profiles, and manage their entire portfolio from one place

---

### 📖 User Stories

**US-034 — Agency Account Setup** `[8 pts]`
*As an agency admin, I want to configure my account as an agency so that I can manage multiple client owners from one place*

Acceptance Criteria:
- Account type selection during onboarding: "I manage my own properties" vs "I manage properties for multiple owners"
- Agency profile: company name, registration number, license number, logo, address, contact details
- Agency admin can switch between portfolio view (all owners) and single owner view
- Agency branding applied to owner statements and receipts

**US-035 — Owner Profile Management** `[13 pts]`
*As an agency admin, I want to add and manage client owner profiles so that properties and finances are attributed to the correct owner*

Acceptance Criteria:
- Owner profile captures: full name, phone, email, national ID/company reg number, bank account details (for disbursements), KRA PIN (for eTIMS)
- Each owner profile assigned unique reference
- Owner profile linked to their properties and units
- Management agreement details stored per owner: fee %, disbursement date, authority limits
- Owner profiles searchable and filterable
- Agency can deactivate an owner profile when management agreement ends (preserves history)

**US-036 — Property & Financial Attribution to Owner** `[8 pts]`
*As an agency, I want every property, payment, and transaction attributed to the correct owner so that accounting is accurate*

Acceptance Criteria:
- Every property linked to an owner profile
- Every payment automatically attributed to the owner of the property's unit
- Financial reports filterable by owner
- Cross-owner data isolation: financial data from Owner A never appears in Owner B's reports
- Agency admin can see consolidated view (all owners) or per-owner view

**US-037 — Agency Dashboard** `[13 pts]`
*As an agency admin, I want an overview dashboard of my entire managed portfolio so that I can monitor everything efficiently*

Acceptance Criteria:
- Portfolio-level KPIs: total units managed, total occupancy rate, total rent collected this month, total outstanding arrears, total management fees earned
- Per-owner summary cards: owner name, properties managed, units, collection rate, arrears, disbursement status
- Pending actions queue: maintenance approvals needed, leases expiring, units vacant >30 days
- Filterable by owner or by property
- All KPIs real-time

**US-038 — Owner Portal Invitation (Mode 3)** `[13 pts]`
*As an agency admin, I want to invite property owners to a read-only portal so that they can see their investment performance without interfering with operations*

Acceptance Criteria:
- Agency sends invitation to owner via email + WhatsApp with portal link
- Owner sets up their access (password + 2FA) via invitation link
- Owner portal shows ONLY their properties within the agency account
- Complete data isolation: Owner A cannot see Owner B's data even though both are in same agency account
- Owner portal is strictly read-only: no edit, create, or delete permissions
- Owner can download their monthly statement as PDF
- Invitation can be revoked by agency at any time

### 🔧 Technical Tasks
- [x] Build account type selector in onboarding flow
- [x] Build OwnerProfile data model and CRUD API
- [x] Build management agreement storage and display
- [x] Implement owner-scoped data filtering on all financial queries
- [x] Build agency dashboard API with aggregated stats
- [x] Build owner portal authentication (separate token scope: owner-portal)
- [x] Build owner portal invitation flow (email + WhatsApp)
- [x] Implement owner-portal-scoped data isolation (can only see own properties)
- [x] Build agency dashboard UI with owner summary cards
- [x] Build owner portal UI (read-only financial overview)
- [x] Write comprehensive cross-tenant isolation tests

### 📦 Sprint 7 Deliverables
- ✅ Agency account mode fully configured
- ✅ Owner profiles created and linked to properties
- ✅ Agency portfolio dashboard working
- ✅ Owner portal invitation and read-only access working

---

## Sprint 8 — Trust Accounting & Owner Disbursement
**Weeks 15–16 | Story Points Target: 55**
**🎯 Sprint Goal:** The agency can calculate what each owner is owed, initiate disbursements, and automatically deliver professional statements — eliminating every "where is my money?" dispute forever

---

### 📖 User Stories

**US-039 — Management Fee Calculation** `[8 pts]`
*As an agency, I want management fees automatically calculated from every rent payment so that my revenue is tracked without manual effort*

Acceptance Criteria:
- Management fee calculated on every payment received: Gross × Fee% = Fee Amount
- Fee calculation uses the rate defined in the owner's management agreement
- Fee accumulated in real-time as payments come in
- Agency can view: total fees earned this month, per owner, per property
- Adjustments (discounts, waivers) recordable with reason

**US-040 — Maintenance Cost Deduction** `[8 pts]`
*As an agency, I want maintenance costs automatically deducted from what's owed to the owner so that disbursements are accurate*

Acceptance Criteria:
- When maintenance job cost is recorded: cost auto-allocated to the property's owner account
- Cost deducted from owner's pending disbursement amount
- Owner portal shows maintenance deductions itemized
- Owner maintenance approval workflow: costs above threshold require WhatsApp approval before deduction applied
- Maintenance cost history per owner per month

**US-041 — Disbursement Calculation & Initiation** `[13 pts]`
*As an agency, I want to calculate and initiate net disbursements to each owner so that they receive their money accurately and on time*

Acceptance Criteria:
- Disbursement summary per owner: Gross Rent - Management Fee - Maintenance Costs = Net Payable
- Agency reviews disbursement summary before initiating (preview step)
- Disbursement initiated via M-Pesa or bank transfer
- Transaction reference recorded against disbursement
- Owner receives WhatsApp notification with full breakdown on disbursement
- Failed disbursements (insufficient funds, wrong number) flagged for manual resolution

**US-042 — Owner Monthly Statement** `[13 pts]`
*As a property owner, I want to receive a detailed monthly statement so that I know exactly what was collected and paid on my behalf*

Acceptance Criteria:
- Statement auto-generated on disbursement date for each owner
- Statement PDF includes: period, all units, gross rent per unit, total gross, management fee, maintenance deductions itemized, net disbursement, outstanding arrears
- Agency branding (logo, address) on statement
- Statement delivered via WhatsApp as PDF + email attachment
- Statement stored in owner's document vault (accessible from portal)
- Year-to-date totals shown on statement

**US-043 — Disbursement Scheduling** `[8 pts]`
*As an agency, I want disbursements triggered automatically on each owner's configured date so that I don't have to remember to pay 40 different owners each month*

Acceptance Criteria:
- Each owner has a configured disbursement day (e.g., 5th of every month)
- Celery Beat task runs daily — checks if any owner disbursement is due today
- Disbursement summary prepared and notification sent to agency admin for review + approval
- After agency approval, disbursements processed
- Owners notified on disbursement date regardless of approval status

### 🔧 Technical Tasks
- [x] Build Disbursement data model (gross, fees, deductions, net, status)
- [x] Build management fee calculation service (triggered on every payment)
- [x] Build maintenance cost allocation service (triggered on cost recording)
- [x] Build disbursement calculation engine (aggregates per owner per period)
- [x] Build disbursement initiation flow with M-Pesa integration
- [x] Build owner statement PDF generation service (agency branded)
- [x] Build disbursement scheduling Celery Beat task
- [x] Build disbursement approval workflow (agency reviews before processing)
- [x] Build agency disbursement management UI
- [x] Build owner statement viewer in owner portal
- [x] Write disbursement calculation accuracy tests

### 📦 Sprint 8 Deliverables
- ✅ Management fees calculated automatically on every payment
- ✅ Maintenance costs deducted from owner disbursements
- ✅ Disbursements calculated and initiated with M-Pesa
- ✅ Professional owner statements delivered via WhatsApp + email
- ✅ Automated monthly disbursement scheduling working

---

## Sprint 9 — Digital Signatures & Document Vault
**Weeks 17–18 | Story Points Target: 55**
**🎯 Sprint Goal:** Lease agreements can be digitally signed by tenants on their phone with full legal validity, and every document is securely stored in an organized vault

---

### 📖 User Stories

**US-044 — Digital Signature Workflow** `[13 pts]`
*As a tenant, I want to sign my lease agreement digitally on my phone so that the process is fast, paperless, and legally valid*

Acceptance Criteria:
- Tenant receives WhatsApp/SMS with unique signing link
- Signing link opens in PWA — no app install required
- Tenant reviews complete lease document (scrollable PDF viewer)
- Before signing: identity verification via OTP sent to registered phone
- After OTP verified: tenant signs using finger on touchscreen
- Signature captured as image overlaid on document
- Signed document immediately delivered to tenant and landlord via WhatsApp + stored in vault
- Audit trail captured: timestamp, IP address, device type, phone number used for OTP, geolocation (if permitted)
- Signing link expires after 72 hours if unused
- Landlord/agency countersign capability (Phase 2)

**US-045 — Document Vault — Tenant** `[8 pts]`
*As a tenant, I want a secure vault where all my rental documents are stored so that I can access them anytime from my phone*

Acceptance Criteria:
- Tenant vault contains: signed lease, all receipts, inspection reports, notices received, ID documents
- Documents organized by type and date
- Each document downloadable as PDF
- Document accessible via tenant portal anytime
- Tenant notified via WhatsApp when new document added to their vault

**US-046 — Document Vault — Property** `[8 pts]`
*As a property owner, I want a vault for each property where all important documents are stored so that nothing gets lost*

Acceptance Criteria:
- Property vault contains: title deed, insurance certificate, all lease agreements (current and historical), compliance certificates, maintenance records
- Documents categorized and searchable by type and date
- Multiple file formats supported: PDF, JPG, PNG, DOCX
- Storage usage visible per account
- Documents accessible to owner and agency (not caretaker or tenant)

**US-047 — Lease Template Customization** `[13 pts]`
*As a property owner, I want to customize my lease agreement template so that it reflects my specific terms and branding*

Acceptance Criteria:
- Template editor with customizable sections: header (logo/letterhead), standard clauses, custom clauses, footer
- Variable placeholders clearly shown: {{tenant_name}}, {{unit_number}}, {{rent_amount}}, etc.
- Preview before saving (renders as PDF)
- Multiple templates per account (e.g., different templates for different property types)
- Template versioning — changing a template doesn't affect already-generated leases
- Default template provided out of the box (ready to use with no customization required)

**US-048 — Document Version History** `[5 pts]`
*As an owner or agency, I want to see the history of all document versions so that I have a complete paper trail*

Acceptance Criteria:
- Every document version retained with timestamp and who uploaded/generated it
- Version history viewable from document detail page
- No documents can be deleted from vault (only archived)
- Audit log entry created for every document access

### 🔧 Technical Tasks
- [x] Build digital signature service: unique link generation, OTP verification, signature capture
- [x] Build signature overlay service (place signature image on PDF at designated position)
- [x] Build signing audit trail capture and storage
- [x] Build document vault API (create, read, categorize, tag)
- [x] Build secure document access with signed URLs (60-min expiry)
- [x] Build tenant vault UI (organized document list with download)
- [x] Build property vault UI (categorized document storage)
- [x] Build lease template editor (rich text with variable placeholders)
- [x] Build template preview service (render template as PDF with sample data)
- [x] Build document version history UI
- [x] Build WhatsApp document delivery service (PDF as attachment)
- [x] Write signing workflow security tests

### 📦 Sprint 9 Deliverables
- ✅ Digital signature on lease agreements working end-to-end
- ✅ Tenant and property document vaults organized and secure
- ✅ Lease template customization with preview working
- ✅ All signed documents delivered via WhatsApp and stored in vaults

---

## Sprint 10 — Inspection System & Property Condition Management
**Weeks 19–20 | Story Points Target: 50**
**🎯 Sprint Goal:** Caretakers can conduct complete move-in and move-out inspections with photos, and the system automatically generates a before/after comparison report that protects both landlord and tenant

---

### 📖 User Stories

**US-049 — Move-In Inspection** `[13 pts]`
*As a caretaker, I want to conduct a structured move-in inspection with photos for every new tenant so that the unit's condition is documented before they move in*

Acceptance Criteria:
- Inspection form: select tenancy → select inspection type (Move-In) → room-by-room assessment
- Rooms pre-configured per unit type (e.g., Living Room, Kitchen, Bedroom 1, Bathroom, Common Area)
- For each room: condition rating (Excellent/Good/Fair/Poor), mandatory photo (minimum 2 per room), optional notes
- Photos tagged with GPS coordinates and timestamp automatically
- Inspection cannot be submitted without at least 1 photo per room
- On submission: inspection PDF auto-generated and stored in tenant vault
- Tenant receives WhatsApp with inspection report link to review
- Tenant can acknowledge receipt of inspection report via portal

**US-050 — Move-Out Inspection & Before/After Comparison** `[13 pts]`
*As a caretaker, I want to conduct a move-out inspection and have the system automatically create a side-by-side comparison with the move-in inspection so that any damage is clearly documented*

Acceptance Criteria:
- Move-out inspection follows same room-by-room structure as move-in
- After submission, system auto-generates comparison report showing:
  - Side-by-side photos (move-in left, move-out right) for each room
  - Condition change indicated (Excellent → Fair = highlighted change)
  - Text notes comparison
- Owner receives WhatsApp with comparison report immediately
- Owner can annotate report: mark damaged items, assign repair costs
- Deposit deduction calculation: owner marks damages, system calculates deductions from deposit
- Report stored in both tenant vault and property vault
- Tamper-proof: report timestamped and cannot be modified after submission

**US-051 — Routine Periodic Inspection** `[8 pts]`
*As a property owner, I want routine inspections conducted and reported so that I can monitor property condition proactively*

Acceptance Criteria:
- Owner/agency schedules periodic inspection (quarterly, bi-annual, or annual)
- Caretaker receives WhatsApp reminder on inspection due date
- Routine inspection uses same room-by-room format (no tenant comparison)
- Report generated and sent to owner on completion
- Inspection compliance tracked: overdue inspections flagged on dashboard

**US-052 — Inspection Compliance Tracking** `[8 pts]`
*As a property owner, I want to know which tenancies are missing their move-in inspection so that compliance is enforced*

Acceptance Criteria:
- Dashboard shows: tenancies without move-in inspection (highlighted in amber)
- Move-in inspection overdue alert if not completed within 48 hours of tenancy start
- Caretaker reminded via WhatsApp if inspection not done on move-in day
- Inspection completion rate metric on caretaker performance dashboard

### 🔧 Technical Tasks
- [x] Build Inspection data model (rooms, conditions, photos, type, tenancy reference)
- [x] Build inspection API endpoints (create, submit, retrieve)
- [x] Build room configuration system (default rooms by unit type, customizable)
- [x] Build inspection comparison engine (maps move-in photos/ratings to move-out)
- [x] Build inspection PDF report generator (professional layout with photos)
- [x] Build comparison PDF report generator (side-by-side photo layout)
- [x] Build damage assessment and deposit deduction calculation tool
- [x] Build caretaker inspection mobile UI (room-by-room with camera)
- [x] Build inspection review UI for owner (comparison report viewer)
- [x] Build deposit deduction annotation UI
- [x] Build inspection compliance dashboard widgets
- [x] Implement GPS tagging on photo capture

### 📦 Sprint 10 Deliverables
- ✅ Move-in inspection with mandatory photos working
- ✅ Move-out inspection with automatic before/after comparison report
- ✅ Deposit deduction calculation from comparison report
- ✅ Inspection compliance tracking on dashboard

---

## Sprint 11 — eTIMS Integration, Advanced Analytics & Late Fees
**Weeks 21–22 | Story Points Target: 55**
**🎯 Sprint Goal:** Every receipt is KRA eTIMS compliant for registered landlords, the analytics dashboard delivers deep financial intelligence, and late fees are automated

---

### 📖 User Stories

**US-053 — KRA eTIMS Integration** `[13 pts]`
*As a property owner registered with KRA, I want every receipt to be automatically eTIMS compliant so that I am tax-compliant without extra effort*

Acceptance Criteria:
- Owner enters their KRA PIN and eTIMS credentials in settings (encrypted storage)
- On every payment receipt generation: system submits to eTIMS API and retrieves eTIMS QR code + serial number
- eTIMS QR code embedded on the receipt PDF
- Receipt clearly shows: "eTIMS Verified" badge with serial number
- eTIMS submission logged with timestamp and response from KRA
- If eTIMS API fails: receipt generated without eTIMS, retried in background, owner notified
- eTIMS report: total receipts submitted, total verified, any failures in a given period
- Owners without KRA PIN: receipts generated normally without eTIMS fields

**US-054 — Advanced Financial Analytics** `[13 pts]`
*As a property owner, I want deep analytics on my portfolio's financial performance so that I can make better decisions*

Acceptance Criteria:
- Revenue analytics: monthly income chart (6 months), collection rate, income vs potential
- Property performance: best and worst performing properties by collection rate and occupancy
- Tenant payment behavior: on-time, late, chronic defaulters segmentation
- Utility analytics: highest consuming units, billing efficiency
- Expense tracking: maintenance costs per property, expense vs income ratio
- Predictive: cash flow forecast for next 3 months based on current occupancy and collection rates
- All charts interactive (hover for exact values)
- All reports exportable to PDF

**US-055 — Late Fee Automation** `[13 pts]`
*As a property owner, I want late fees applied automatically without me having to remember so that my revenue is protected*

Acceptance Criteria:
- Owner configures per property: grace period (days), late fee type (fixed/percentage/daily), fee amount
- Celery Beat task runs daily: checks all overdue invoices past grace period
- Late fee calculated and added to invoice automatically
- Tenant notified via WhatsApp when late fee applied: "A late fee of KES X has been added to your account for [Unit]. Total outstanding: KES Y"
- Late fee escalation: after 60 days overdue, demand letter automatically triggered
- Owner can waive a late fee for specific tenant with reason logged
- Late fee report: total fees collected, total waived, per property

### 🔧 Technical Tasks
- [x] Set up KRA eTIMS API integration (sandbox first, production on launch)
- [x] Build eTIMS submission service with retry logic
- [x] Build eTIMS QR code embedding in receipt PDF
- [x] Build eTIMS report dashboard
- [x] Build analytics aggregation service (complex SQL queries with materialized views for performance)
- [x] Build revenue charts UI with Recharts (interactive, responsive)
- [x] Build property performance comparison table
- [x] Build cash flow forecast model (based on current data)
- [x] Build late fee configuration UI per property
- [x] Build late fee calculation Celery task (daily)
- [x] Build late fee waiver API with audit trail
- [x] Build demand letter generation service (PDF template)
- [x] Performance test analytics queries with large dataset simulation

### 📦 Sprint 11 Deliverables
- ✅ eTIMS receipts generated for registered landlords
- ✅ Advanced analytics dashboard with charts and forecasts
- ✅ Late fees applied automatically with tenant notification
- ✅ Demand letters auto-generated at 60 days overdue

---

## Sprint 12 — Caretaker Accountability, Recurring Tasks & Lease Automation
**Weeks 23–24 | Story Points Target: 50**
**🎯 Sprint Goal:** The platform runs on autopilot — automated invoices, lease renewals, reminders, and reports flow without any manual intervention. Phase 2 is DONE

---

### 📖 User Stories

**US-056 — Recurring Tasks Engine** `[13 pts]`
*As a property owner, I want the system to run routine tasks automatically so that I don't have to log in every month to trigger things*

Acceptance Criteria:
- Monthly invoice generation runs automatically on configured billing days
- Rent reminder sequences run automatically (7, 3, 0 days before due date)
- Lease expiry alerts run automatically (90, 60, 30, 14 days before end)
- Monthly owner financial reports sent automatically via WhatsApp + email
- Late fee application runs daily automatically
- Monthly data backup automatically generated and emailed to account owner
- Task monitoring dashboard: all scheduled tasks visible, status (pending/running/completed/failed), last run time

**US-057 — Lease Renewal Automation** `[13 pts]`
*As a property owner, I want lease renewals managed automatically so that no lease expires without action*

Acceptance Criteria:
- Automated alert sequence: 90 → 60 → 30 → 14 days before lease expiry (WhatsApp to both owner and tenant)
- At 30 days: system auto-generates renewal lease agreement with updated terms (new rent amount if owner configured rent increase)
- Renewal agreement sent to tenant for digital signing via same digital signature workflow
- Tenant can accept (signs renewal) or decline (triggers move-out workflow)
- If no action by 14 days: owner and caretaker alerted with escalation flag
- Renewed lease stored in vault with new effective date
- Lease renewal history tracked per tenancy

**US-058 — Caretaker Performance Dashboard** `[8 pts]`
*As a property owner, I want a clear performance dashboard for my caretaker so that I can hold them accountable objectively*

Acceptance Criteria:
- Dashboard shows per caretaker: meter reading compliance % (readings submitted on time/total due), cash collection efficiency (cash recorded vs M-Pesa reconciled), inspection completion rate, average response time on maintenance requests, last login date
- Monthly performance trend (are they improving or declining?)
- Performance score (0-100) calculated from weighted metrics
- Underperforming caretakers flagged with amber/red indicator

**US-059 — Phase 2 QA & Performance Review** `[13 pts]`
*As the development team, we want to review, fix, and optimize everything built in Phase 2 before proceeding*

Acceptance Criteria:
- Complete regression test of all Phase 1 and Phase 2 features
- API response time audit (all endpoints under 500ms)
- Mobile performance audit (Lighthouse score > 80)
- Security review: all endpoints tested for unauthorized access
- Bug backlog cleared
- Database query optimization (add indexes where needed)
- Load test: simulate 100 concurrent users

### 🔧 Technical Tasks
- [x] Build Celery Beat scheduled task registry (all tasks defined and tested)
- [x] Build task monitoring dashboard (admin view)
- [x] Build failed task retry and alerting system
- [x] Build lease renewal detection service
- [x] Build renewal agreement auto-generation
- [x] Build renewal confirmation workflow (tenant accepts/declines)
- [x] Build caretaker performance metrics calculation service
- [x] Build caretaker performance dashboard UI
- [x] Complete regression testing suite
- [x] API performance profiling and optimization
- [x] Database index optimization (EXPLAIN ANALYZE on slow queries)
- [x] Lighthouse performance audit and fixes

### 🏁 Phase 2 Complete — First Agency Customer Milestone
**All Phase 2 deliverables:**
- ✅ Agency mode with multi-owner management
- ✅ Owner portal (read-only transparency)
- ✅ Trust accounting and owner disbursements
- ✅ Digital signatures with full audit trail
- ✅ Document vaults (tenant and property)
- ✅ Move-in/move-out inspections with before/after comparison
- ✅ eTIMS compliance
- ✅ Advanced analytics and forecasting
- ✅ Late fee automation
- ✅ Recurring tasks engine running on autopilot
- ✅ Lease renewal automation
- ✅ Caretaker performance accountability

---

## PHASE 3 — FULL PLATFORM
### Months 7–9 | Sprints 13–18
**Phase Goal:** All rental types supported, every enterprise feature complete

---

## Sprint 13 — Maintenance & Vendor Management
**Weeks 25–26 | Story Points Target: 55**
**🎯 Sprint Goal:** Every maintenance request has a complete lifecycle — from submission to vendor assignment to cost tracking — with full owner visibility

---

### 📖 User Stories

**US-060 — Vendor Registry** `[8 pts]`
*As a property owner, I want to maintain a list of trusted contractors so that maintenance jobs can be assigned quickly and tracked*

Acceptance Criteria:
- Vendor profile: name, specialty tags (plumbing/electrical/carpentry/painting/etc.), phone, email (optional), rate/quote info, notes
- Multiple specialties per vendor
- Vendor rating (1–5 stars) from completed job reviews
- Vendor status: active/inactive
- Vendor searchable by specialty and availability

**US-061 — Maintenance Request Full Lifecycle** `[13 pts]`
*As an owner or caretaker, I want to manage maintenance requests from submission to completion with full tracking so that nothing falls through the cracks*

Acceptance Criteria:
- Request states: Submitted → Under Review → Approved → Assigned → In Progress → Completed → Closed
- Owner/manager can approve, reject (with reason), or request more info
- On approval: select vendor from registry, WhatsApp notification sent automatically to vendor with job details
- Cost estimate recordable before and actual cost after completion
- Caretaker marks job complete and rates the vendor (1–5 stars)
- Job completion triggers final cost recording and maintenance expense allocated to owner (agency mode)
- Complete maintenance history per unit and per property
- Overdue jobs (not completed within expected timeframe) flagged automatically

**US-062 — Maintenance Cost Analytics** `[8 pts]`
*As a property owner, I want to see maintenance spending patterns so that I can budget better and identify problematic units*

Acceptance Criteria:
- Total maintenance cost per property (monthly, annual)
- Most expensive units (maintenance cost vs rent ratio)
- Most common maintenance issues (by category)
- Most used vendors and their average costs
- Maintenance budget vs actual tracking

**US-063 — Tenant Maintenance Request Portal** `[8 pts]`
*As a tenant, I want to submit maintenance requests and track their status from my portal so that I'm kept informed*

Acceptance Criteria:
- Tenant submits request: category, description, urgency, photo upload (optional)
- Tenant sees status of all their open requests
- Tenant notified via WhatsApp when status changes (approved, assigned, completed)
- Tenant rates the completed job (optional feedback)

### 🔧 Technical Tasks
- [x] Build Vendor CRUD API and registry
- [x] Build maintenance request state machine (status transitions with validation)
- [x] Build vendor assignment service with WhatsApp notification
- [x] Build maintenance cost recording and allocation service
- [x] Build vendor performance calculation (from job ratings)
- [x] Build maintenance analytics aggregation queries
- [x] Build vendor registry UI
- [x] Build maintenance management UI (request list, detail, approval workflow)
- [x] Build maintenance cost analytics charts
- [x] Update tenant portal with maintenance request and tracking

### 📦 Sprint 13 Deliverables
- ✅ Vendor registry with profiles and ratings
- ✅ Complete maintenance lifecycle with vendor assignment
- ✅ Automated vendor WhatsApp notifications
- ✅ Maintenance cost analytics dashboard
- ✅ Tenant maintenance request portal updated

**Built:** `vendors` table + `/api/v1/vendors` CRUD with specialty filtering, ratings
(running total/count) and deactivation guarded on in-flight jobs. `maintenance_status`
rebuilt into the nine-state lifecycle with the transition table in
`app/models/operations.py`; one endpoint per move (`/review`, `/request-info`,
`/approve`, `/reject`, `/assign`, `/start`, `/complete`, `/close`, `/cancel`), each
audited — the audit log doubles as the job timeline. Vendor assignment sends the job,
address and deadline over WhatsApp. Estimate vs actual cost with an overrun audit line;
closing allocates the expense to the owner in agency mode. Nightly
`rentflow.flag_overdue_maintenance` beat flags jobs past their due date and alerts
managers. `/maintenance/analytics` covers cost by property (against a new
per-property `maintenance_budget_monthly`), issues by category, units ranked by
maintenance-to-rent ratio, a vendor leaderboard and a monthly trend. UI: vendor
registry + detail, rebuilt maintenance detail with the approval workflow, a cost
dashboard, and tenant-portal progress tracking with a job rating.
17 tests in `backend/tests/test_maintenance.py`.

---

## Sprint 14 — Tenant Screening & KYC
**Weeks 27–28 | Story Points Target: 55**
**🎯 Sprint Goal:** Prospective tenants go through a rigorous digital vetting process before being approved — protecting owners from bad tenants from day one

---

### 📖 User Stories

**US-064 — Online Tenant Application Form** `[8 pts]`
*As a prospective tenant, I want to apply for a vacant unit online so that the process is fast and paperless*

Acceptance Criteria:
- Application captures: personal details, current residence, employment status, employer details, monthly income, ID document upload, passport photo upload
- Application linked to specific vacant unit (from vacancy listing)
- Application confirmation sent via WhatsApp after submission
- Duplicate application detection (same phone/ID for same unit)
- Application status: Submitted → Under Review → Interview Scheduled → Approved/Rejected

**US-065 — Guarantor Management** `[8 pts]`
*As a property owner, I want to capture and verify guarantor details so that there is someone accountable if the tenant defaults*

Acceptance Criteria:
- Guarantor section of application: name, relationship, phone, ID number, ID document upload, employment details, monthly income
- System sends WhatsApp to guarantor to digitally acknowledge their guarantee
- Guarantor signs a separate guarantee agreement digitally (same signing flow as lease)
- Guarantor details stored in tenant's KYC vault
- Multiple guarantors supported

**US-066 — Creditworthiness Assessment** `[8 pts]`
*As a property owner, I want the system to assess a tenant's financial suitability so that I can make an informed decision*

Acceptance Criteria:
- System calculates: income-to-rent ratio (monthly rent / monthly income × 100%)
- Flagged if rent exceeds 30% of stated income
- Employment stability indicator (employed/self-employed/unemployed)
- Tenant score generated (0-100) based on: application completeness, income ratio, guarantor provided, reference check status
- Score displayed with traffic light color (green ≥70, amber 40-69, red <40)
- Owner sees score and breakdown before making decision

**US-067 — Application Review & Approval Workflow** `[8 pts]`
*As a property owner or manager, I want to review applications and approve or reject with documented reasons so that decisions are traceable*

Acceptance Criteria:
- Application review page shows all captured information, documents, and creditworthiness score
- Approve action: triggers tenancy creation, unit status changes to Reserved, tenant notified
- Reject action: requires reason selection + optional note, tenant notified via WhatsApp with reason
- Waiting list: multiple applicants per unit ranked by score and application date
- All decisions logged with timestamp and approving user

**US-068 — Previous Landlord Reference Check** `[8 pts]`
*As a property owner, I want to request and record reference checks from a tenant's previous landlord so that I know their rental history*

Acceptance Criteria:
- System sends WhatsApp to previous landlord phone number provided by tenant: "Hi, you're listed as a previous landlord for [Tenant Name]. Please confirm: Was this tenant reliable and did they pay rent on time? Reply YES or NO."
- Response recorded against tenant application
- Owner sees reference check status (Sent/Responded Yes/Responded No/No Response)
- Negative reference flagged prominently in application review

### 🔧 Technical Tasks
- [x] Build TenantApplication data model and CRUD API
- [x] Build application form UI (multi-step, mobile-friendly)
- [x] Build creditworthiness score calculation service
- [x] Build guarantor capture and WhatsApp acknowledgment workflow
- [x] Build guarantor digital signature flow
- [x] Build application review UI with score display and document viewer
- [x] Build approval/rejection workflow with WhatsApp notifications
- [x] Build reference check WhatsApp bot (send and receive responses)
- [x] Build waiting list management UI
- [x] Write screening workflow tests

### 📦 Sprint 14 Deliverables
- ✅ Online tenant application with document upload
- ✅ Creditworthiness score automatically calculated
- ✅ Guarantor management with digital signature
- ✅ Previous landlord WhatsApp reference check
- ✅ Application approval/rejection with documented reason

**Built:** `tenant_applications`, `guarantors` and `reference_checks` — screening is
deliberately separate from `tenants`, since most applicants never become one and
folding them in would poison every duplicate check. Public, login-free flows at
`/apply/{unit_id}`, `/guarantee/{token}` and `/reference/{token}` reach the three
people who have no account: applicant, guarantor, previous landlord. The 0–100
score in `app/services/screening_service.py` is four explainable components
(completeness 20, affordability 40, guarantor 20, reference 20) with a
traffic-light band; affordability is the rent-to-income ratio tapered from the 30%
guideline and discounted by employment stability. Guarantors confirm over
WhatsApp; the applicant's previous landlord is asked automatically and answers two
questions, with a negative answer pushed to managers and a nightly
`rentflow.sweep_stale_references` closing the ones nobody answers. Approval creates
the `Tenant`, reserves the unit and closes out the rest of the waiting list with a
message to each. UI: applications list with screening counts, a review page with the
score's working shown, a four-step mobile application form, and the two public
response pages. 22 tests in `backend/tests/test_screening.py`.

---

## Sprint 15 — Service Charges, Commercial Properties & Bulk Operations
**Weeks 29–30 | Story Points Target: 55**
**🎯 Sprint Goal:** Commercial properties are fully supported with service charge management, and bulk operations let large portfolios be managed with single actions

---

### 📖 User Stories

**US-069 — Commercial Property Support** `[8 pts]`
*As a commercial property manager, I want to add and manage commercial units (offices, retail) so that my commercial portfolio is managed alongside residential*

Acceptance Criteria:
- Unit type "Commercial" with relevant fields: floor area (sqm), use class (office/retail/warehouse/industrial), number of car bays allocated
- Commercial lease template (different clauses from residential)
- Service charge configuration per commercial property

**US-070 — Service Charge Management** `[13 pts]`
*As a commercial property manager, I want to bill tenants for their share of service charges so that shared building costs are recovered*

Acceptance Criteria:
- Service charge configuration: fixed amount per tenant, or proportional by unit size
- Service charge invoice generated monthly alongside rent (or separately configurable)
- Service charge categories: security, cleaning, maintenance of common areas, generator, lift
- Actual cost vs budgeted charge tracking (monthly reconciliation)
- Sinking fund tracking: reserve amount accumulated for capital maintenance
- Annual service charge statement: actual costs incurred vs charges collected, surplus or deficit
- Tenant notified of service charge in invoice

**US-071 — Bulk Rent Increase** `[8 pts]`
*As a property owner, I want to apply a rent increase to all units in a property at once so that I don't have to update 50 units one by one*

Acceptance Criteria:
- Select property → choose increase type (% or fixed KES amount) → enter value → preview shows new rent per unit
- Effective date picker (increase applies from chosen date)
- Bulk rent increase notice automatically generated and sent to all affected tenants
- Increase applies to future invoices from effective date
- Audit trail: who applied the increase, when, to which units, old and new rent

**US-072 — Bulk Operations Suite** `[13 pts]`
*As a property owner or agency, I want to perform actions on multiple tenants or units at once so that portfolio management is efficient*

Acceptance Criteria:
- Bulk operations available: Send Payment Reminder (to all defaulters), Send Announcement, Generate All Invoices, Send Lease Renewal Notices (to all expiring), Bulk Tenant Onboarding (import from Excel)
- Each bulk operation has a preview step (shows who will be affected before executing)
- Progress indicator during bulk operation execution
- Summary report after completion (X of Y succeeded, Z failed with reasons)
- All bulk operations logged in audit trail

**US-073 — Bulk Document Distribution** `[5 pts]`
*As a property owner, I want to send a document to all tenants in a property at once so that communications are efficient*

Acceptance Criteria:
- Select document (or upload new), select recipients (all tenants in property, or filter by unit type/floor), send
- Document delivered via WhatsApp to each tenant
- Delivery status tracked per recipient

### 🔧 Technical Tasks
- [x] Add commercial unit type and fields to property/unit model
- [x] Build commercial lease template
- [x] Build service charge configuration model
- [x] Build service charge billing service (adds to invoice monthly)
- [x] Build service charge reconciliation UI
- [x] Build sinking fund tracking
- [x] Build bulk rent increase service with preview
- [x] Build rent increase notice PDF generator
- [x] Build bulk operations framework (job queue based, with progress tracking)
- [x] Build bulk operations UI with preview and progress
- [x] Build Excel import service for bulk tenant onboarding

### 📦 Sprint 15 Deliverables
- ✅ Commercial property type with service charge management
- ✅ Bulk rent increase with automatic tenant notices
- ✅ Full bulk operations suite with preview and progress tracking
- ✅ Sinking fund and service charge reconciliation working

**Built:** Commercial units gained `use_class` and `car_bays` (floor area reuses
`size_sqm`). Service charges keep three truths apart — `service_charge_budgets`
(what was budgeted), invoice line items (what was charged) and
`service_charge_expenses` (what was spent) — because a scheme that cannot show all
three is one tenants are right to dispute. Three apportionment methods: flat per
unit, by floor area, and split between occupied units only (so a vacancy costs the
landlord, not the neighbours); the rounding remainder goes to the largest share
rather than vanishing. The charge is added to the rent invoice automatically, and
`sinking_fund_entries` takes its percentage slice as the charge is *billed* rather
than collected, so one late tenant cannot shrink the roof fund. Bulk operations are
preview-then-execute against a stored target list (`bulk_operations`), so execution
can never widen its blast radius; one failed target never aborts the run, and the
per-target reason is recorded. Rent increase, arrears chase, announcement, invoice
run, renewal offers and document distribution all share that engine. The Excel
importer generates its own template from the parser's column list, validates in two
passes (format, then database), and turns an opening balance into a real invoice so
arrears and statements see it. UI: bulk actions hub with preview dialogs, a
three-step import wizard, and a four-tab service charge page. 20 tests in
`backend/tests/test_service_charges.py`.

---

## Sprint 16 — Vacancy Marketing & Data Import/Migration
**Weeks 31–32 | Story Points Target: 50**
**🎯 Sprint Goal:** Vacant units get filled faster through shareable online listings, and new customers can migrate their existing data without pain

---

### 📖 User Stories

**US-074 — Vacancy Listing Portal** `[13 pts]`
*As a property owner, I want each vacant unit to have a shareable listing page so that I can fill vacancies by sharing a link on WhatsApp*

Acceptance Criteria:
- Each vacant unit automatically gets a public listing page (no login required to view)
- Listing page shows: unit photos, description, size, amenities, monthly rent, deposit, property location (map), contact info
- "Apply Now" button opens inline application form
- Listing URL copyable and WhatsApp-shareable with one tap
- Listing automatically deactivated when unit is occupied
- Internal vacancy portal: owner sees all vacant units with days-vacant counter
- Vacancy cost report: monthly revenue lost per vacant unit

**US-075 — Lead Pipeline Management** `[8 pts]`
*As a property owner, I want to track all inquiries and applicants for each vacant unit so that I follow up effectively*

Acceptance Criteria:
- Each vacancy has a pipeline: Inquired → Applied → Under Review → Approved/Rejected
- Inquiries captured when someone contacts via listing page (name + phone)
- All applications per unit listed with their status and score
- Follow-up reminders for stale leads (no action in 3 days)
- Conversion rate report: inquiries to applications to approvals per unit

**US-076 — Data Import & Migration Wizard** `[13 pts]`
*As a new customer switching from manual management, I want a guided import wizard so that I can get my data into RentFlow without starting from scratch*

Acceptance Criteria:
- Downloadable Excel template for: properties, units, tenants, opening balances, payment history
- Upload completed template → validation runs → errors highlighted with clear fix instructions
- Preview of what will be imported before committing
- Opening balances correctly handled (what each tenant already owes as of import date)
- Failed rows reported with reason — partial imports allowed (skip error rows)
- Import history log (when imported, by whom, how many records)
- Post-import checklist guiding customer through next steps

**US-077 — Data Export** `[8 pts]`
*As a property owner, I want to export all my data at any time so that I'm never locked into the platform*

Acceptance Criteria:
- Export available for: tenants, tenancy history, payment history, properties, units
- Export formats: CSV, Excel
- Date range filter for payment exports
- Exports generated in background for large datasets (notified when ready)
- Scheduled monthly auto-export emailed to owner

### 🔧 Technical Tasks
- [x] Build public vacancy listing page (no auth required, SEO friendly)
- [x] Build listing URL generation and sharing service
- [x] Build inquiry capture form on vacancy listing
- [x] Build lead pipeline tracking per vacancy
- [x] Build days-vacant tracking and vacancy cost calculation
- [x] Build Excel template generator (downloadable import template)
- [x] Build Excel import parser and validation service
- [x] Build import preview and confirmation UI
- [x] Build opening balance import handling
- [x] Build data export service with CSV/Excel generation
- [x] Build scheduled export Celery task

### 📦 Sprint 16 Deliverables
- ✅ Shareable vacancy listings with online application
- ✅ Lead pipeline tracking per vacant unit
- ✅ Data import wizard with validation and preview
- ✅ Data export in CSV and Excel formats

**Built:** `vacancy_listings` carries its own opaque, rotatable slug rather than
reusing the unit id — the link is meant to be pasted into WhatsApp groups, and an
over-shared one has to be replaceable without touching the unit. Listings are
created on first use (a 2,000-unit portfolio should not carry 2,000 dormant
adverts) and close themselves the moment a tenancy starts. The public page at
`/listing/{slug}` needs no login and carries an enquiry form that asks only for a
name and a number. `inquiries` is the pipeline: a second enquiry from the same
number is enthusiasm rather than a new lead, an application absorbs the lead it
came from, and every application state change moves the lead with it, so the
conversion report can never contradict the file. A nightly
`rentflow.chase_stale_leads` nudges the office about anything untouched for three
days, once. The vacancy desk multiplies days-empty by daily rent to show the number
nobody usually tracks. Export covers six datasets in CSV and Excel from one
row-shaping function each, so the two formats can never disagree, and every export
is logged with who took it. 17 tests in `backend/tests/test_vacancy.py`.

---

## Sprint 17 — Compliance Calendar, Parking & Amenities
**Weeks 33–34 | Story Points Target: 50**
**🎯 Sprint Goal:** Enterprise clients have complete compliance and certificate tracking, and complex residential/commercial properties manage parking bays and shared amenities professionally

---

### 📖 User Stories

**US-078 — Compliance & Legal Calendar** `[13 pts]`
*As a property owner, I want to track all compliance requirements for my properties so that nothing expires without my knowledge*

Acceptance Criteria:
- Compliance items: fire safety cert, health inspection cert, NEMA certificate, lift inspection cert, electrical inspection cert, water safety cert, insurance policy
- Each item has: expiry date, document upload, responsible party, status
- Status dashboard: green (valid), amber (expires in 60 days), red (expired)
- Automatic reminders: 90, 60, 30 days before expiry (WhatsApp to owner)
- Insurance policy tracking: premium due date, coverage amount, insurer contact
- Compliance audit report: PDF showing all compliance items and their status per property

**US-079 — Parking Bay Management** `[8 pts]`
*As a property manager, I want to allocate and track parking bays so that parking is managed fairly and revenue is captured*

Acceptance Criteria:
- Parking bay registry: bay number, type (covered/open/reserved), level/location
- Bay allocation to tenant with start/end date
- Separate parking fee billing (added to tenant's monthly invoice)
- Unallocated bay inventory visible (available for new allocation)
- Visitor parking: temporary allocation with duration and guest name
- Parking revenue report: income from parking per month

**US-080 — Shared Amenity Booking** `[8 pts]`
*As a tenant, I want to book shared amenities (gym, meeting room, rooftop) through the portal so that there are no conflicts*

Acceptance Criteria:
- Amenity booking: select amenity → view availability calendar → select date/time → confirm
- Booking rules: max booking duration, advance notice required, max bookings per week per tenant
- Booking confirmation via WhatsApp
- Conflicts prevented (cannot book already-booked slot)
- Owner/manager can block amenity for maintenance
- Amenity usage report per month

**US-081 — KPLC & Water Utility Account Management** `[5 pts]`
*As a property owner, I want to track utility account details for each property so that I can manage payment status easily*

Acceptance Criteria:
- KPLC account number and water board account stored per property
- Utility payment status: paid/unpaid/unknown
- Manual update of payment status by owner/caretaker
- Overdue utility payment alert to owner
- All utility account details stored in property vault

### 🔧 Technical Tasks
- [x] Build ComplianceItem model and CRUD API
- [x] Build compliance expiry monitoring Celery task (daily check)
- [x] Build compliance status dashboard UI (traffic light)
- [x] Build compliance PDF report generator
- [x] Build ParkingBay model and allocation service
- [x] Build parking fee billing integration (adds to invoice)
- [x] Build parking management UI
- [x] Build Amenity booking model with conflict detection
- [x] Build amenity booking calendar UI (available/booked slots)
- [x] Build amenity rules configuration per amenity
- [x] Build utility account tracking UI

### 📦 Sprint 17 Deliverables
- ✅ Compliance calendar with automatic renewal reminders
- ✅ Compliance status dashboard (traffic light per property)
- ✅ Parking bay allocation and billing
- ✅ Shared amenity booking system
- ✅ Utility account management per property

**Built:** Four things that share a shape — obligations attached to a *building*
rather than a tenancy. `compliance_items` treats expiry as a first-class indexed
date with a 90/60/30/7-day reminder ladder where each rung fires once and a renewal
resets it; an item with no expiry is `MISSING` rather than silently valid, because
silence is not compliance. The traffic light rolls up to the worst item per
property, and `/compliance/report` renders the PDF an insurer or county inspector
asks for. `parking_bays` + `parking_allocations` enforce one holder per bay, treat a
visitor as the same row with a guest name and a mandatory end date, and push the
monthly fee onto the tenant's rent invoice. `amenities` carry their own booking
rules (duration, notice, weekly cap, opening hours) and `amenity_bookings` makes a
maintenance block just another booking, so the overlap check is one query that
cannot disagree with itself. `utility_accounts` track the block's own KPLC and water
accounts, default to `UNKNOWN` rather than assuming, and a weekly sweep alerts on
anything overdue — a disconnection hits every tenant. UI: compliance calendar with
renewal dialog and PDF, and a three-tab facilities page per property. 24 tests in
`backend/tests/test_facilities.py`.

---

## Sprint 18 — Vehicle Rentals, Equipment Rentals & Phase 3 QA
**Weeks 35–36 | Story Points Target: 50**
**🎯 Sprint Goal:** Non-residential rental types are fully supported — vehicle and equipment rental businesses can use RentFlow. Phase 3 is DONE.

---

### 📖 User Stories

**US-082 — Vehicle Rental Management** `[13 pts]`
*As a vehicle rental company, I want to manage my fleet and rental agreements on RentFlow so that my business operations are organized*

Acceptance Criteria:
- Vehicle asset type: registration number, make, model, year, color, mileage, insurance expiry, inspection date, photos
- Vehicle rental agreement template (includes: daily/weekly/monthly rate, mileage limit, fuel policy, damage deposit, driver's license upload)
- Vehicle availability calendar (booked vs available)
- Check-out inspection: mileage out, fuel level, condition photos
- Check-in inspection: mileage in, fuel level, condition photos + auto-comparison
- Daily rate billing and deposit management
- Vehicle compliance tracking: insurance, road license, inspection

**US-083 — Equipment Rental Management** `[8 pts]`
*As an equipment rental company, I want to manage my equipment inventory and rental tracking so that assets are accounted for*

Acceptance Criteria:
- Equipment asset: name, serial number, category, daily/weekly/monthly rate, deposit, photos, service schedule
- Equipment rental agreement (includes: rental period, rate, deposit, condition at handover)
- Equipment condition inspection at check-out and check-in
- Equipment availability tracking
- Maintenance/service schedule tracking per equipment item

**US-084 — Phase 3 QA, Performance & Security Audit** `[13 pts]`
*As the development team, we want to ensure all Phase 3 features are solid before proceeding to Phase 4*

Acceptance Criteria:
- All Phase 3 features regression tested
- API response times all under 500ms under normal load
- Security audit: penetration test checklist completed
- Lighthouse mobile score > 85 on all core pages
- All critical user journeys tested end-to-end
- Database optimized for expected load (10,000 units)

### 🔧 Technical Tasks
- [x] Build vehicle asset model with vehicle-specific fields
- [x] Build vehicle availability calendar
- [x] Build vehicle rental agreement template
- [x] Build check-out and check-in inspection flows with mileage tracking
- [x] Build vehicle compliance tracking
- [x] Build equipment asset model and inventory
- [x] Build equipment rental agreement and inspection flows
- [x] Complete Phase 3 regression testing
- [x] Security penetration test checklist execution
- [x] Performance profiling and optimization

### 🏁 Phase 3 Complete — All Rental Types Supported
**All Phase 3 deliverables:**
- ✅ Commercial property with service charges
- ✅ Vehicle rental management
- ✅ Equipment rental management
- ✅ Tenant screening and KYC
- ✅ Vacancy marketing and lead pipeline
- ✅ Compliance and legal calendar
- ✅ Parking and amenity management
- ✅ Bulk operations suite
- ✅ Data import and migration tools

**Sprint 18 built:** A car and a generator are the same business — an asset that
goes out, comes back, and is worth less if it comes back worse — so `rental_assets`
holds both behind a `kind` discriminator and `rental_agreements` covers the hire.
The condition snapshot is the point: mileage, fuel (in eighths, because that is
what a gauge shows) and photos at check-out and again at check-in turn "you
scratched it" from an argument into a comparison. Check-in derives every extra —
excess mileage against the included allowance, fuel against the policy, a late
charge at the daily rate, damage — and floors the deposit refund at zero. An asset
with lapsed insurance does not go out: the override exists but demands a written
reason and is recorded against the person who gave it. Bookings check the calendar
for an overlap rather than trusting a status field, and a hire moves strictly
forward — a second check-out is refused, because it would overwrite the evidence a
deposit dispute turns on. Weekly and monthly rates charge per started period, the
way a counter quotes them. UI: fleet screen with compliance warnings up front, and
an asset page with the hand-over and return flows. 24 tests in
`backend/tests/test_rentals.py`.

**Phase 3 QA (US-084):** `backend/tests/test_phase3.py` holds the cross-cutting
properties no single feature test would notice breaking — every Phase 3 table is
inside the RLS policy set *and* carries an `organization_id`; every new Celery task
is actually on the beat schedule; the four new public prefixes are declared
decisions; one invoice carrying rent, service charge and parking still adds up; a
caretaker scoped to one property sees only its compliance, vacancy and parking
data; and the screening score can never exceed its own maximum.

The penetration-test checklist is executed rather than signed:
`backend/tests/test_phase3_security.py` runs it on every commit, aimed at what
Phase 3 actually introduced — four routes anyone on the internet can reach. It
covers unit-id enumeration through the public apply route, parameter tampering
(the unit in the path is authoritative, so a crafted body cannot file against
another organisation), forged and expired link tokens, information disclosure on
the shared listing, link revocation by rotation, horizontal privilege escalation
across every Phase 3 resource, RLS being enabled with a policy on every new
table, SQL injection through the one field a stranger controls, oversized
submissions, blast radius on bulk execution, and token hashes never reaching a
response body. The API performance audit in `backend/tests/test_api_performance.py`
now covers all sixteen Phase 3 read endpoints under the same
queries-per-request budget, which is what catches an N+1 before a stopwatch does.

---

## PHASE 4 — INTELLIGENCE & ECOSYSTEM
### Months 10–12 | Sprints 19–24
**Phase Goal:** AI features, partner integrations, and market leadership

---

### 📍 Phase 4 status — build complete

All six sprints are built. Sprint checkboxes are ticked per task, with the
account/hosting/legal-review items each sprint left for Kelvin called out
inline rather than checked off.

| Sprint | Scope | State |
|---|---|---|
| 19 | Public API, API keys, webhooks, developer docs | ✅ Done |
| 20 | Onboarding wizard, help/knowledge base, health scoring, referrals | ✅ Done |
| 21 | Scheduled + custom reports, predictive intelligence | ✅ Done |
| 22 | AI lease analysis, fraud detection, security hardening | ✅ Done |
| 23 | Property portal sync, accounting integrations, bank transfer | ✅ Done |
| 24 | Golden-path test, OWASP checklist, Lighthouse, legal pages, expansion doc | ✅ Done |

**Verification:** 488 backend tests passing · ruff and mypy clean across 176
source files · frontend typecheck, oxlint and production build clean. The
Phase 1 golden path — register, a property with 6 bulk-created units, a
tenant, a tenancy with its lease generated on creation, an invoice, an
M-Pesa payment confirmed by a simulated Daraja callback, a receipt, both
dashboards reflecting all of it — is now a committed, passing test
(`tests/test_critical_journeys.py`), not just something verified by hand
against a live server once in Sprint 6.

**Still open — all need Kelvin's own accounts, hosting, or professional
sign-off, not more code:**

- GitHub branch protection on `main`/`develop`, and switching on Dependabot
  (config already committed, Sprint 22)
- DigitalOcean droplet, Nginx + Let's Encrypt, staging/production environments
- Sentry project + DSN, uptime monitoring, Grafana
- Cloudflare R2 bucket, WhatsApp Business API production approval, Safaricom
  Daraja production credentials, KRA eTIMS production credentials
- The k6 load test (`infra/loadtest/k6-load-test.js`) run for real against a
  production-sized staging environment
- A qualified Kenyan lawyer's review of the drafted legal pages
  (`/legal/privacy`, `/legal/terms`, `/legal/cookies`)
- Real Uganda/Tanzania market-pricing research (`docs/expansion-readiness.md`
  lays out the framework; the conversations with landlords in each market
  still need to happen)

Every third-party integration still degrades gracefully with no credentials
configured — this phase added AI lease analysis, accounting-software OAuth,
and property-portal sync to that list, and none of them behave differently
in that respect from Phase 1's M-Pesa simulation.

---

## Sprint 19 — Open API, Webhooks & Developer Portal
**Weeks 37–38 | Story Points Target: 55**

### 📖 User Stories

**US-085 — Public REST API** `[13 pts]`
*As an enterprise customer's developer, I want API access to RentFlow data so that I can integrate with my company's systems*

Acceptance Criteria:
- All major resources exposed via REST API: properties, units, tenants, payments, invoices
- API versioned (v1) to protect against breaking changes
- Consistent response format (status, data, errors)
- Pagination on all list endpoints (cursor-based)
- Filtering, sorting, and field selection supported
- Rate limiting: 1,000 requests/hour (configurable per enterprise plan)

**US-086 — API Key Management** `[8 pts]`
*As an enterprise account owner, I want to generate and manage API keys so that I can control programmatic access to my data*

Acceptance Criteria:
- Generate named API keys with expiry dates and scope restrictions
- API key usage statistics: requests per day, last used, endpoints hit
- Revoke any API key immediately
- API keys never shown after initial generation (only once, then hashed)
- Failed API key attempts logged and alerted after 10 consecutive failures

**US-087 — Webhook System** `[13 pts]`
*As an enterprise customer, I want to configure webhooks so that my systems are notified in real-time when events happen in RentFlow*

Acceptance Criteria:
- Configurable webhook endpoints per account (up to 10)
- Events available: payment.received, tenant.created, lease.signed, inspection.completed, maintenance.status_changed, invoice.generated
- Webhook payload includes event type, timestamp, affected entity data
- Delivery with retry logic (3 attempts, exponential backoff)
- Webhook delivery log: success/failure per event
- Webhook secret for HMAC signature verification

**US-088 — Interactive API Documentation Portal** `[8 pts]`
*As a developer, I want interactive API documentation so that I can understand and test the API without reading a PDF*

Acceptance Criteria:
- Swagger UI auto-generated from FastAPI (already built-in)
- Sandbox environment with test data for API exploration
- Code samples in Python, JavaScript, and cURL
- Authentication guide and quick-start guide
- Hosted at docs.rentflow.co.ke

### 🔧 Technical Tasks
- [x] Build public API versioning layer (v1 prefix)
- [x] Build API authentication middleware (API key validation)
- [x] Build API rate limiting with Redis
- [x] Build API key management service and UI
- [x] Build webhook subscription model and configuration UI
- [x] Build webhook delivery service with retry logic
- [x] Build webhook delivery log and monitoring UI
- [x] Configure FastAPI Swagger UI with authentication (built into FastAPI at `/docs`; gated the same way as every other endpoint)
- [ ] Build sandbox environment with seeded test data — needs hosting, not just code
- [x] Write API documentation and quick-start guide (`docs/public-api.md`)
- [x] API integration test suite (`tests/test_developer_platform.py`, 16 tests)

### 📦 Sprint 19 Deliverables
- ✅ Public REST API — versioned, scoped, rate-limited, cursor-paginated. Live on any running instance at `/api/v1/external/*`; `api.rentflow.co.ke` itself waits on the DNS/hosting from Sprint 0
- ✅ API key management for enterprise customers
- ✅ Webhook system with delivery monitoring (HMAC-signed, 3 attempts with backoff)
- ✅ Interactive Swagger documentation portal — `/docs` and `/redoc` on the running instance; a separately branded `docs.rentflow.co.ke` needs the same hosting as above

---

## Sprint 20 — In-App Onboarding, Help System & Customer Success
**Weeks 39–40 | Story Points Target: 55**

### 📖 User Stories

**US-089 — Interactive Setup Wizard** `[13 pts]`
*As a new customer, I want a guided setup wizard so that I can get my account fully configured without needing to call support*

Acceptance Criteria:
- Wizard activated on first login (dismissible but accessible from settings)
- Step-by-step: Add your first property → Add units → Invite your caretaker → Add your first tenant → Set up payment account
- Progress bar showing completion % and estimated time remaining
- Each step has a short explanation and help link
- Steps can be completed in any order
- Wizard completion triggers celebration animation and confetti 🎉
- Progress saved — can resume later if wizard is closed

**US-090 — Contextual Help System** `[8 pts]`
*As any user, I want help available in context so that I don't have to leave the app to find answers*

Acceptance Criteria:
- Help icon (?) on every major page and form field that needs explanation
- Clicking help icon shows a tooltip or side panel with relevant explanation
- Search bar in help panel searches knowledge base articles
- "Contact Support" option in help panel opens in-app chat
- Help content managed from admin CMS (updatable without code deployment)

**US-091 — Customer Health Scoring** `[13 pts]`
*As the RentFlow team, I want a health score per customer so that we can proactively reach out to at-risk accounts before they churn*

Acceptance Criteria:
- Health score (0-100) calculated weekly per account based on: login frequency (20%), payments processed (25%), feature adoption (20%), caretaker activity (15%), tenant portal adoption (10%), support tickets (10%)
- Score trend (improving/declining/stable) shown
- At-risk threshold: score drops below 50 → internal alert to customer success team
- Health score dashboard for RentFlow team: all customers sorted by score
- Automated at-risk email/WhatsApp triggered to customer when score drops below threshold

**US-092 — Retention & Referral Features** `[8 pts]`
*As a happy customer, I want to be rewarded for referring others to RentFlow so that both I and my referred friend benefit*

Acceptance Criteria:
- Referral link generated per account (shareable on WhatsApp)
- When referred account upgrades to paid plan: referee gets 1 month free credit applied automatically
- Referral dashboard: total referrals, pending, converted, credits earned
- In-app NPS survey appears after: first successful payment, first completed inspection, end of first month
- Feature request voting board: customers submit and upvote feature ideas
- In-app changelog: new features announced with brief description on login
- Milestone celebrations: confetti on first 100 payments processed, 50th tenant, first eTIMS receipt

### 🔧 Technical Tasks
- [x] Build onboarding wizard state machine and UI
- [x] Build contextual help system (side panel, global header trigger — not per-field tooltips)
- [x] Build knowledge base CMS (admin editable) — `/internal/content`, platform-staff only
- [x] Build in-app search for help content
- [x] Build health score calculation service (weekly Celery task, `rentflow.compute_health_scores`)
- [x] Build customer health dashboard (internal admin view) — `/internal/health`
- [x] Build at-risk alert notification system
- [x] Build referral tracking system (credit is a ledger — see note below)
- [x] Build NPS survey trigger service (post-milestone)
- [x] Build feature voting board
- [x] Build in-app changelog system
- [x] Build milestone detection and celebration service

**Sprint 20 built:** RentFlow had no cross-tenant identity at all before this —
every endpoint resolved one organisation. `User.is_platform_staff` plus a new
`require_platform_staff` dependency (`app/api/deps.py`) is the whole
mechanism: it reuses the existing JWT login, so RentFlow's own team is just a
normal user with one extra flag, gating a new `/internal/*` router that
deliberately reads across every organisation — health scores, alerts, and now
the knowledge-base/changelog CMS the previous paragraph's checkboxes needed
(built after the first pass shipped with the backend CRUD but no UI to drive
it — caught in browser testing, not by any gate). Health, help, referrals,
NPS, milestones and support requests are per-organisation tables joining
`PHASE_4_ORG_SCOPED_TABLES`; help articles, the feature board and the
changelog are platform-wide, the same treatment `task_runs` already gets, so
they carry no `organization_id` and sit outside RLS on purpose.

Referral credit (`Organization.credit_months`) is a ledger, not an applied
invoice discount — RentFlow has no billing engine yet for its own
subscription fee, so there was nothing to hook a real "upgrade" event onto.
The internal `PATCH /internal/organizations/{id}/plan` endpoint this sprint
added is the first way RentFlow staff can change a plan at all, even by hand;
it's what triggers the credit grant.

A real, pre-existing bug surfaced by testing this against the actual migrated
dev database (not just the test suite, which builds its schema straight from
the ORM models and never touches Alembic): SQLAlchemy's `Enum` type binds a
`(str, Enum)` member by its Python **name**, not its `.value`, with no
`values_callable` configured anywhere in this codebase. Every migration's
hand-written `postgresql.ENUM(...)` labels have to be the uppercase member
names to match — Sprint 19's `webhook_delivery_status` migration used
lowercase `.value`s instead, which would have thrown "invalid input value for
enum" the first time anything touched a real migrated webhook delivery row.
Fixed alongside this sprint's own migration, which had the identical bug
before this was caught.

24 backend tests in `tests/test_customer_success.py`, plus
`tests/test_phase4.py` — the cross-cutting Phase 4 suite `test_phase3.py`'s
pattern implies but Sprint 19 never actually added, now covering both
sprints' tables and tasks.

### 📦 Sprint 20 Deliverables
- ✅ Interactive setup wizard guiding new customers to first value
- ✅ Contextual help: global search panel + contact-support form, backed by an
  admin-editable knowledge base — not yet a per-field "?" hint on every page
- ✅ Customer health scoring with at-risk alerts, and the internal dashboard
  to see it (RentFlow's first cross-tenant surface)
- ✅ Referral program with automatic credit ledger (not yet wired to a real
  invoice — no billing engine exists for that yet)
- ✅ NPS surveys, feature voting, and in-app changelog (with its own admin UI)

---

## Sprint 21 — Advanced Analytics, Reporting & Custom Reports
**Weeks 41–42 | Story Points Target: 50**

### 📖 User Stories

**US-093 — Scheduled Report Delivery** `[8 pts]`
*As a property owner, I want financial reports delivered to me automatically every month so that I stay informed without logging in*

Acceptance Criteria:
- Monthly summary report auto-generated on 1st of each month
- Report includes: prior month income, expenses, collection rate, arrears, occupancy, top defaulters
- Delivered via WhatsApp as PDF + email attachment
- Owner configures preferred delivery: WhatsApp only, email only, or both
- Report accessible from dashboard history for last 12 months

**US-094 — Custom Report Builder** `[13 pts]`
*As an enterprise customer, I want to build custom reports so that I can get exactly the data I need in the format I prefer*

Acceptance Criteria:
- Drag-and-drop report builder with available data fields
- Filter options: date range, properties, unit types, tenant status
- Chart types selectable: bar, line, pie, table
- Report saveable and renameable
- Saved reports schedulable for automatic delivery
- Report exportable to PDF, CSV, Excel

**US-095 — Predictive Intelligence Features** `[13 pts]`
*As a property owner, I want the system to forecast future events so that I can take action proactively*

Acceptance Criteria:
- Cash flow forecast: next 3 months projected income based on current occupancy and collection rates
- Vacancy risk forecast: units whose tenants' leases expire without renewal intention flagged
- Maintenance budget alert: when maintenance costs this month are 50% above monthly average
- Rent review suggestions: units that haven't had a rent increase in 12+ months, with market average comparison
- All forecasts shown with confidence indicator and assumptions used

### 🔧 Technical Tasks
- [x] Build scheduled report generation Celery task
- [x] Build report PDF template (comprehensive monthly summary)
- [x] Build report delivery service (WhatsApp + email)
- [x] Build report history storage and retrieval
- [x] Build custom report builder UI (drag-and-drop)
- [x] Build report filter and configuration engine
- [x] Build cash flow forecasting model — already shipped in Sprint 11; reused as-is
- [x] Build vacancy risk detection service
- [x] Build maintenance budget anomaly detection — already shipped in Sprint 11; reused as-is
- [x] Build rent review recommendation service
- [x] Build predictive dashboard widgets

**Sprint 21 built:** Sprint 11's `analytics_service.py` already covered cash-flow
forecasting and a maintenance-spend spike alert, so this sprint's predictive work
was narrower than the plan implied: `vacancy_risk_forecast` (tenancies expiring
within 90 days *and* carrying no live renewal offer — built on Sprint 12's
`LeaseRenewal`/`RenewalStatus`, not just a lease-expiry count) and
`rent_review_suggestions` (12+ months since the last rent change, compared
against the average rent this organisation itself charges on same-bedroom-count
units — an explicit estimate from the owner's own portfolio, never presented as
external market data). Both ship as two new Analytics page cards alongside the
existing forecast/maintenance widgets.

The custom report builder (`report_definitions`, US-094) reuses
`export_service`'s six row-shaping functions rather than a second query layer:
`reporting_service.execute` calls the same `BUILDERS` dict, applies equality
filters in Python, and projects down to the chosen columns. The builder UI
(`/reports/new`, `/reports/:id/edit`) is a dataset picker, a reorderable column
list (native HTML5 drag-and-drop — no new dependency), value-checkbox filters,
an optional bar/line/pie chart over a group-by/measure pair, and CSV/Excel/PDF
export. Saved reports can be scheduled weekly or monthly and delivered by
WhatsApp, email or in-app notification, run by the same daily Celery task that
also under-pins the automatic monthly summary (`monthly_reports`, US-093) —
one PDF per organisation per calendar month, built from
`dashboard_service`'s period-bound aggregates and `arrears_service`'s current
snapshot, delivered per the organisation's own delivery-channel preference
(Settings → Defaults → Monthly report delivery) the same way
`owner_statement_service` already delivers agency statements.

**A real, pre-existing bug found while wiring the payments dataset into the
builder:** `export_service._payment_rows` read `payment.mpesa_receipt_number`,
a column that has never existed — the model field is `mpesa_receipt`. Every
payments CSV/Excel export (Sprint 16, US-077) has thrown `AttributeError` on
any account with at least one real payment row since it shipped; the existing
export test only ever ran against an empty payments list, so nothing caught
it. Fixed alongside this sprint's own payments-dataset tests, which seed a
real payment specifically so this class of bug can't hide again.

**Deliberate limits:** WeasyPrint has no chart engine, so a PDF export of a
bar/line/pie report renders as a table — CSV/Excel carry the same rows for
anyone who wants to chart it themselves. The builder's checkbox filters only
cover string/enum/boolean columns with 30 or fewer distinct values; a numeric
or date range filter on an arbitrary column is not built (the two date-range
fields are wired to each dataset's natural date column instead). Chart
grouping caps at three slices — the top two plus an "Other" bucket — reusing
the app's existing three-hue validated categorical palette rather than
generating new colours for arbitrary cardinality.

### 📦 Sprint 21 Deliverables
- ✅ Monthly reports automatically delivered via WhatsApp and/or email, with a
  12-month browsable history
- ✅ Custom report builder: any of six datasets, filtered, column-picked,
  optionally charted, exported to CSV/Excel/PDF, and optionally scheduled
- ✅ Predictive intelligence: cash flow forecast and maintenance alerts (Sprint
  11) plus new renewal-aware vacancy risk and portfolio-relative rent review
  suggestions

---

## Sprint 22 — AI Features & Advanced Security
**Weeks 43–44 | Story Points Target: 50**

### 📖 User Stories

**US-096 — AI Document Intelligence** `[13 pts]`
*As a property owner, I want AI to analyze my lease templates and suggest improvements so that my leases are comprehensive and legally sound*

Acceptance Criteria:
- Owner uploads existing lease template → AI analyzes it
- AI flags: missing standard clauses, potentially problematic terms, unclear language
- AI suggests: alternative wording, additional protective clauses, Kenya-specific legal requirements
- Owner can accept or dismiss each suggestion
- Accepted suggestions incorporated into template
- AI cannot modify leases automatically — all changes require owner approval

**US-097 — AI Fraud Detection** `[13 pts]`
*As the system, I want to detect suspicious patterns automatically so that fraud is caught before it causes damage*

Acceptance Criteria:
- Pattern detection: caretaker recording more than X cash payments in Y minutes (configurable)
- Off-hours activity: payments or large changes recorded between midnight and 5am flagged
- Unusual amount detection: payment amounts significantly different from normal rent
- Velocity detection: same amount paid multiple times in quick succession
- All anomalies generate internal alert + owner WhatsApp notification
- Owner can mark alert as legitimate (suppress future alerts for same pattern)

**US-098 — Advanced Security Hardening** `[13 pts]`
*As an enterprise customer, I want enterprise-grade security features so that I can trust the platform with sensitive data*

Acceptance Criteria:
- IP whitelisting: enterprise accounts restrict logins to specific IP ranges
- Custom session timeout policies per role
- Security audit log export: downloadable CSV/PDF of all security events for compliance
- Failed login attempt reporting: daily summary of failed attempts per account
- API key rotation reminder after 90 days
- Automated dependency vulnerability scanning in CI/CD (Dependabot / Snyk)

### 🔧 Technical Tasks
- [x] Integrate Anthropic API for document analysis
- [x] Build lease analysis prompt engineering and response parsing
- [x] Build AI suggestion UI (show/accept/dismiss)
- [x] Build fraud detection rule engine (configurable thresholds)
- [x] Build anomaly detection on every payment event (inline, not a Celery task — see note)
- [x] Build security alert notification service
- [x] Build IP whitelisting service and UI
- [x] Build security audit log export
- [x] Add Dependabot for dependency vulnerability scanning (config only — needs
      enabling on the GitHub repo, same as branch protection in Sprint 0)
- [x] Write fraud detection scenario tests

**Sprint 22 built:** AI lease analysis (US-096) calls Claude (`claude-opus-5`,
structured JSON output, adaptive thinking) with the template body and the
sprint's own standard-clause list as reference, and returns missing-clause,
problematic-term and unclear-language findings — each its own `LeaseSuggestion`
row under a `LeaseAnalysis`. Accepting one appends the AI's plain-text wording
(HTML-escaped) to `LeaseTemplate.body_html` and bumps its version through the
same path a manual edit takes; dismissing changes nothing. The AI never writes
to a template directly — every acceptance is a human clicking Accept, per the
acceptance criteria. With no `ANTHROPIC_API_KEY` configured the endpoint
returns a clear 503 rather than a stack trace, the same degrade-gracefully
treatment every other third-party integration gets.

Fraud detection (US-097) runs inline from `payment_service._confirm` — the one
function every confirmed payment (cash or M-Pesa) already funnels through —
rather than as a separate Celery sweep. That is a deliberate deviation from
the technical task as written: a nightly batch would report a rapid-cash
pattern after the shift that produced it is over, and every other
per-payment side effect in this codebase (milestones, NPS prompts) already
runs the same way. Four rules, each keyed by a stable `pattern_key` so the
same subject doesn't re-alert every few minutes and so an owner's "not fraud"
decision (`FraudSuppression`) silences it for good: rapid cash payments by one
caretaker, off-hours activity (00:00–05:00 Nairobi time), an amount outside
`rent × threshold` in either direction, and the same amount paid twice on one
tenancy within ten minutes. Thresholds live on `Organization` and are
editable from Settings → Organization → Fraud detection thresholds.

Security hardening (US-098): an IP whitelist (exact IPs or CIDR ranges) is
enforced at login for every account, not gated to an enterprise plan — the
plan doesn't have a real billing engine yet to gate on (see Sprint 20's
referral-credit note), so any owner can opt in. Per-role session timeout is
an organisation-wide policy (`Organization.role_session_timeouts`) that
overwrites `inactivity_timeout_minutes` on every existing user of that role
the moment it's saved, rather than a preference a user could quietly keep
lapsed. The security audit log export (CSV/PDF) reuses `export_service.to_csv`
and the reporting PDF template. Failed logins are now durable
(`SecurityEvent`, distinct from `AuditLog`, which only ever recorded
privileged successes) and summarised to owners daily; API keys past 90 days
get the same treatment. `AiServiceError`, `FraudAlert` and `SecurityEvent`
are additive — nothing about existing auth, payment or lease-template
behaviour changed for an organisation that never touches any of this.

**Deliberate limits:** off-hours detection has no dedicated test — it depends
on wall-clock time at the moment a payment confirms, which the test suite
does not freeze. IP whitelisting and the security digest were not built as
plan-gated enterprise features, since RentFlow has no subscription enforcement
to gate on yet. Dependabot's config file is committed; the scan itself only
runs once Dependabot is switched on in the GitHub repo's own settings,
which needs a real repo and Kelvin's account, like branch protection.

24 backend tests across `tests/test_ai_lease_analysis.py` and
`tests/test_advanced_security.py` (470 total passing across the whole suite,
up from Phase 2's 260), plus `tests/test_phase4.py` extended to cover every
table Sprints 20–22 added and their scheduled tasks — a gap from Sprint 21,
whose own reporting tables (`report_definitions`, `monthly_reports`) had
never been added to that cross-cutting check either, closed alongside this
sprint's own tables.

### 📦 Sprint 22 Deliverables
- ✅ AI lease analysis with improvement suggestions, accept/dismiss per
  finding, nothing changes without an explicit accept
- ✅ Automated fraud pattern detection (rapid cash, off-hours, unusual amount,
  velocity) with owner WhatsApp alerts and per-organisation suppression
- ✅ Enterprise security hardening: IP whitelisting, per-role session policy,
  audit log export, failed-login digest, API key rotation reminders,
  Dependabot configured

---

## Sprint 23 — Partner Integrations & Financial Services Foundation
**Weeks 45–46 | Story Points Target: 50**

### 📖 User Stories

**US-099 — Property Portal Integration** `[13 pts]`
*As a property owner, I want my vacant units to be automatically published to BuyRentKenya and PigiaMe so that I reach more potential tenants*

Acceptance Criteria:
- Owner connects their BuyRentKenya/PigiaMe account in settings
- When unit becomes vacant: auto-published to connected portals
- When unit becomes occupied: listing auto-deactivated on portals
- Inquiries from portals captured in RentFlow lead pipeline
- Portal sync status visible per vacancy (Published/Pending/Failed)

**US-100 — Accounting Software Integration** `[13 pts]`
*As a property owner using QuickBooks or Xero, I want to sync my RentFlow financial data so that I don't have to double-enter information*

Acceptance Criteria:
- QuickBooks Online OAuth connection in settings
- Xero OAuth connection in settings
- Sync: rent payments → sales receipts in QuickBooks/Xero
- Sync: maintenance costs → expenses in QuickBooks/Xero
- Sync: owner disbursements → transactions in QuickBooks/Xero
- Sync runs daily (configurable)
- Sync history and error log visible

**US-101 — Bank Transfer Payment Method** `[8 pts]`
*As a tenant, I want to pay rent via bank transfer so that I have a payment option beyond M-Pesa*

Acceptance Criteria:
- Bank transfer instructions shown in tenant portal: account name, account number, bank, reference code
- Caretaker/owner can manually mark bank transfer as received with transaction reference
- System matches bank reference code to tenant for easier reconciliation
- Bank statement upload feature: owner uploads monthly statement, system highlights matched and unmatched entries

### 🔧 Technical Tasks
- [x] Research and integrate BuyRentKenya API — no self-serve developer API is
      published today; see the sprint note below for what was built instead
- [x] Research and integrate PigiaMe API — same limit as BuyRentKenya
- [x] Build portal sync service (vacancy publish/deactivate)
- [x] Build QuickBooks OAuth connection and data sync
- [x] Build Xero OAuth connection and data sync
- [x] Build accounting sync Celery task
- [x] Build sync history and error log UI
- [x] Build bank transfer instructions display
- [x] Build bank statement upload and matching service

**Sprint 23 built:** Property portal sync (US-099) follows `etims_service`'s
shape exactly — an organisation's own API key, encrypted at rest
(`PortalConnection`), and a durable per-listing sync row (`PortalListingSync`)
rather than a fire-and-forget call. It hooks into the existing, opt-in
`VacancyListing` lifecycle from Sprint 15: `ensure_listing`/`update_listing`
publishing a listing now calls `portal_integration_service.publish_listing`,
and `close_listing_for_unit` (already called when a tenancy starts) now calls
`deactivate_listing`. Neither BuyRentKenya nor PigiaMe publishes a self-serve
developer API today, so the adapter posts to a configurable base URL using
the smallest REST contract a listings API is ever likely to expose
(`settings.BUYRENTKENYA_API_BASE_URL` / `PIGIAME_API_BASE_URL`); a real
partnership only changes the payload shape in `_call_portal`, not the
credential storage, retry accounting or lead capture around it. Inbound
leads are captured through a public, unguessable-URL webhook
(`/portal-webhooks/{connection_id}/inquiries`) that resolves the listing by
`external_listing_id` and joins the same `Inquiry` pipeline Sprint 15 built,
tagged with a new `Inquiry.source` column so a portal-sourced lead is
distinguishable from one that came through the public listing page.

Accounting sync (US-100) is the one of the three that runs against real,
stable, publicly documented endpoints today — standard OAuth2
authorization-code grants against Intuit's and Xero's own token and API
hosts. What's missing is Kelvin's own developer app registration:
`QUICKBOOKS_CLIENT_ID`/`XERO_CLIENT_ID` are blank locally, and `connect()`
returns a clear 503 rather than starting a broken OAuth round-trip, the same
degrade-gracefully treatment `ai_service` gives a missing
`ANTHROPIC_API_KEY`. The OAuth callback
(`/oauth/accounting/{provider}/callback`) carries no session — only a
short-lived, signed `state` token identifies which organisation is
connecting — and QuickBooks' `realmId` arrives on that same redirect while
Xero's `tenantId` needs a follow-up call to `/connections`. A daily Celery
task (`rentflow.sync_accounting_connections`) pushes every unsynced confirmed
payment, completed maintenance job cost and completed disbursement outward,
each recorded once in `AccountingSyncRecord` keyed by
(connection, entity type, entity id) so a re-run never double-posts and a
failure sits there for the settings page to show and retry.

Bank transfer (US-101) turned out to be mostly a bug fix: `PaymentMethod.
BANK_TRANSFER` and the `reference` field already existed end-to-end in the
frontend's record-payment form, but `payment_service.record_cash_payment`
only ever stored `reference` into `mpesa_receipt`, and only for
`PaymentMethod.MPESA` — a bank or cheque reference was silently dropped the
moment it was typed in, despite the request schema's own docstring promising
otherwise. Fixed by giving `Payment` its own `bank_reference` column, not
reusing `mpesa_receipt` (whose uniqueness is global and M-Pesa-specific;
bank reference formats can collide across organisations). What Sprint 23
actually added: `Organization.bank_*` fields surfaced as instructions in both
the operator settings page and the tenant portal's "Pay by bank transfer"
dialog, and a statement reconciliation flow
(`bank_transfer_service.parse_statement`/`match_rows`/`commit_statement`)
that follows the same preview-then-commit shape the Sprint 15 tenant bulk
import already established: a CSV/Excel upload is parsed and matched by
scanning each line's bank-supplied narrative for a `TCY-XXXXXX` tenancy
reference — nothing is written until the operator reviews and confirms each
row, and only credit lines are considered.

51 backend tests across `tests/test_partner_integrations.py`, extending
`test_phase4.py` and `test_migrations.py`'s enum/RLS checks to cover all six
new tables and the new scheduled task.

**Deliberate limits:** BuyRentKenya/PigiaMe's endpoint paths and payload
shape are a reasonable placeholder pending a real partnership — nothing
about the credential storage or retry accounting depends on getting that
shape right today. Portal sync status is visible from Settings → Property
portals per connection, but not yet as a per-listing badge on the vacancy
desk table. The bank statement reference match is a straight substring scan
for a `TCY-` code in the narrative — a bank that truncates or reformats the
reference will show the line as unmatched rather than partially matched.

### 📦 Sprint 23 Deliverables
- ✅ Vacant units auto-published to connected property portals, deactivated
  the moment a tenancy starts, with inbound portal leads joining the same
  lead pipeline as direct enquiries
- ✅ QuickBooks and Xero OAuth connection and daily financial data sync
  (payments, maintenance costs, disbursements), with a sync history and
  retry surface in Settings
- ✅ Bank transfer payment method with a tenant-facing instructions dialog
  and a statement upload → match → confirm reconciliation flow — plus a
  fix for a pre-existing bug that silently discarded the bank/cheque
  reference on every such payment ever recorded

---

## Sprint 24 — Final QA, Performance, Launch Preparation & Expansion Readiness
**Weeks 47–48 | Story Points Target: 40**
**🎯 Sprint Goal:** The platform is hardened, polished, and ready for aggressive customer acquisition. Phase 4 is DONE.

---

### 📖 User Stories

**US-102 — Comprehensive System Testing** `[13 pts]`
*As the development team, we want to thoroughly test the complete system so that launch is risk-free*

Acceptance Criteria:
- End-to-end test coverage for all critical user journeys (payment, inspection, lease signing, agency disbursement)
- Load testing: 500 concurrent users with 10,000 units without degradation
- API response times: 95th percentile under 800ms under load
- Mobile performance: Lighthouse score > 90 on PWA
- All known bugs from backlog resolved or scheduled
- Security scan: OWASP Top 10 checklist completed

**US-103 — Expansion Readiness Assessment** `[8 pts]`
*As the business owner, I want to assess readiness for Uganda/Tanzania expansion so that we can plan next year's roadmap*

Acceptance Criteria:
- Technical audit: what changes needed for Uganda M-Pesa, Tanzania M-Pesa
- Legal audit: data residency requirements for Uganda, Tanzania
- Pricing research: appropriate pricing for each target market
- Expansion roadmap document produced

**US-104 — Production Launch Checklist** `[13 pts]`
*As the development team, we want to confirm every launch requirement is met so that go-live is smooth*

Acceptance Criteria:
- Production environment on DigitalOcean fully configured and tested
- SSL certificates active and auto-renewing
- Automated backup verified (daily database backup, tested restoration)
- Monitoring and alerting active (Sentry for errors, Grafana for performance)
- Uptime monitoring configured with 5-minute checks
- Domain and email (rentflow.co.ke) configured
- WhatsApp Business API production account approved
- Africa's Talking production account live
- Safaricom Daraja production credentials obtained and tested
- KRA eTIMS production credentials obtained and tested
- Privacy policy, terms of service, and cookie policy live on site
- GDPR/Kenya Data Protection Act compliance checklist completed

### 🔧 Technical Tasks
- [x] Execute full end-to-end automated test suite (`tests/test_critical_journeys.py` — the
      Phase 1 golden path, chained through the real API for the first time — plus the full
      existing suite re-verified green)
- [ ] Load test with k6 (500 concurrent users) — script written and ready
      (`infra/loadtest/k6-load-test.js`), not run for real: no staging environment sized like
      production exists yet to point it at (same gap as Sprint 19's sandbox environment)
- [x] OWASP security checklist execution (`docs/owasp-top-10-checklist.md` — two real fixes
      made, three gaps documented rather than silently left implicit)
- [x] Lighthouse audit and optimization (`docs/lighthouse-report.md` — 95-100 on every
      category except a deliberately non-indexed login page's SEO score; three real
      accessibility/SEO bugs found and fixed)
- [ ] Production infrastructure final configuration — needs the DigitalOcean droplet from
      Sprint 0
- [x] Disaster recovery test (restore from backup) — re-ran the actual drill against the dev
      database after all of Sprints 13–23's schema changes; still passes (`infra/backup/README.md`)
- [ ] WhatsApp Business API production approval process — needs Kelvin's own business account
- [ ] All third-party production credentials obtained and tested — Daraja, eTIMS, R2, Sentry:
      all need Kelvin's own accounts, same as every earlier phase
- [x] Legal pages (privacy policy, terms) written and published — cookie policy added too
      (`/legal/privacy`, `/legal/terms`, `/legal/cookies`); published to the running app, not
      to a live domain (Sprint 0 hosting gap) or past a qualified lawyer yet — both flagged
      on the pages themselves
- [x] Expansion readiness research and document (`docs/expansion-readiness.md` — a technical
      and legal audit grounded in this codebase; pricing itself needs real people in-market,
      which no document can substitute for)

**Sprint 24 built:** Before adding anything new, the tree's substantial *uncommitted* Sprint
21–23 work (advanced reporting, AI/fraud/security hardening, partner integrations) was
verified rather than assumed: full gates green, 487 backend tests passing. Two real,
independently-found issues were fixed as part of the OWASP pass rather than left for later —
`Settings.DEBUG` defaulted to `True` (a production deployment that forgot to set it explicitly
would leak stack traces) and there were no security response headers at all
(`SecurityHeadersMiddleware`, `app/main.py`) — plus two dependency bumps (`python-jose`,
`jinja2`) after `pip-audit` surfaced 28 advisories across 8 packages, re-verified against the
auth/signing/PDF test suites before being folded in. The Lighthouse pass caught and fixed a
missing `<main>` landmark on every unauthenticated screen, a pre-existing insufficient-contrast
caption on the login page (`text-slate-400` at 12px, below WCAG's 4.5:1 minimum — the new
legal-page footer links were about to repeat the same mistake, caught before they shipped), and
added a `robots.txt` that didn't exist before (scoped to keep the authenticated app out of
search indexing while allowing the new legal pages and existing public listing pages to be
crawled). `test_critical_journeys.py` chains Phase 1's own "golden path" — register, a property
with 6 bulk-created units, a tenant, a tenancy with its lease generated on creation, an invoice,
an M-Pesa STK push confirmed by a simulated Daraja callback, a receipt, both dashboards
reflecting all of it — through nothing but the public API in one continuous test, reusing every
existing test helper (`make_property`, `make_tenancy`, `daraja_callback`) rather than
duplicating the many already-passing single-stage tests those helpers already cover.

**Deliberate limits, same category as every earlier phase's leftover list:** the k6 script is
untested against real infrastructure because none exists yet; production credentials
(WhatsApp, Daraja, eTIMS, Sentry, R2) all need Kelvin's own accounts; the legal pages are
Kelvin's draft, not a lawyer's, and say so on the page; expansion pricing needs real
conversations with landlords in Uganda and Tanzania that no document can substitute for.

### 🏁 Phase 4 Complete — Full Platform Launch!
**All deliverables across all phases:**
- ✅ 26 complete feature modules
- ✅ 3 operating modes (Owner / Agency / Agency+Owner Portal)
- ✅ All rental types (residential, commercial, vehicle, equipment)
- ✅ M-Pesa real-time reconciliation
- ✅ KRA eTIMS compliance
- ✅ AI document intelligence and fraud detection
- ✅ Public REST API with webhook system
- ✅ Partner integrations (accounting software, property portals)
- ✅ Customer success and health scoring
- ✅ Enterprise security hardening
- ✅ Expansion-ready architecture

---

## PHASE 5 — ENTERPRISE HARDENING & MARKET EXPANSION
### Months 13–14.5 | Sprints 25–29
**Phase Goal:** Close every real gap found between the masterplan's promises and the Phase 1–4 build, and add the identity, billing, and financial-services features that turn "feature-complete" into "enterprise-ready"

---

### 📍 Phase 5 status — in progress (Sprint 25 of 5 complete)

This phase was scoped on 2026-09-07 from a gap analysis: the masterplan and sprint-plan
were re-read against the actual Phase 1–4 codebase rather than trusting the checkboxes.
Everything below was genuinely missing at that point, not just unverified — each item
was confirmed absent by grep before being added here.

| Sprint | Scope | State |
|---|---|---|
| 25 | Virus scanning, DSAR export/erasure, co-tenants, WebAuthn, visitor log | ✅ Done |
| 26A | Masterplan gap closure — 16 promised features that were in no sprint | ✅ Done |
| 26 | SSO/SAML, custom roles, session policy, security compliance pack | ⬜ Not started |
| 27 | Subscription billing engine, referral credit, white-label | ⬜ Not started |
| 28 | General ledger, ML fraud scoring, two-way messaging, rent pricing | ⬜ Not started |
| 29 | Credit bureau, card payments, bank/insurance foundations, floor plans | ⬜ Not started |

**Sprint 25 verification:** 507 backend tests passing (488 carried over + 19 new in
`tests/test_sprint25.py`) · ruff and mypy clean · frontend typecheck, oxlint and
production build clean · the actual Alembic migration applied to a live
`docker compose` Postgres and inspected via `psql` (not just the test suite's
ORM-built schema) · every new endpoint hit with `curl` against the real running
server · a full Playwright session driving real Chromium against the real dev
server through five pages and three real mutations (log a visitor, add a
co-tenant, promote a co-tenant to primary), screenshotted at each step. See
Sprint 25's own "Built" and "Gap-closing pass" notes below for what shipped,
what a second read against its own acceptance criteria found and fixed, and a
real crash this pass caught in the live backend container.

**Confirmed gaps this phase closes:**

| Gap | Promised in |
|---|---|
| Virus scanning on uploads | Sprint 2 (US-012), flagged "Phase 2 — note for later," never revisited |
| DSAR / right-to-erasure self-service | Kenya Data Protection Act compliance section |
| Co-tenant / joint tenancy support | Module 3 |
| Biometric / WebAuthn login | Security Architecture section |
| Caretaker visitor log | Module 5 |
| SSO/SAML | Security Architecture section, Module 25 |
| Custom roles beyond the 8 built-in | implied by "granular permission flags per role" in Security Architecture |
| Real subscription billing for RentFlow's own fees | Pricing Strategy section — plans exist, nothing enforces or bills them |
| White-label capability | Module 25 + explicit Phase 4 deliverable (only a CSS comment exists today) |
| Double-entry general ledger | implied by "Trust fund compliance" (Module 9) and the accounting sync being one-way |
| General two-way WhatsApp messaging | Module 21 (only a narrow Y/N reference-check bot exists) |
| Credit bureau integration (TransUnion/Metropol) | Module 4 + explicit Phase 4 deliverable |
| Card payments (Flutterwave/Stripe) | Integrations table, marked Phase 2 |
| Bank partner / insurance marketplace | Phase 4 deliverable + Future Expansion section |
| Floor plan / unit mapping | Module 1 |

---

## Sprint 25 — Security, Privacy & Compliance Closeout
**Weeks 49–50 | Story Points Target: 50**
**🎯 Sprint Goal:** Close the gaps that matter most in a compliance audit or a customer's security questionnaire — nothing here is optional once RentFlow is being sold as enterprise-ready

---

### 📖 User Stories

**US-105 — Virus Scanning on Uploads** `[8 pts]`
*As the system, I want every uploaded file scanned for malware before it's stored so that RentFlow never becomes a distribution vector for infected documents*

Acceptance Criteria:
- Every upload (property/unit photos, KYC docs, lease PDFs, inspection photos) is scanned via ClamAV (or equivalent) before being persisted to R2/local storage
- Infected files rejected with a clear error; the attempt is logged
- Scanning does not add more than ~2 seconds to typical single-file upload flows (async scan + quarantine for large batch imports)
- Existing stored files can be swept retroactively via a one-off Celery task

**US-106 — Data Subject Access & Erasure Workflow** `[8 pts]`
*As a tenant or user, I want to request a copy of my data or its deletion so that my rights under the Kenya Data Protection Act are actually usable, not just promised in a policy page*

Acceptance Criteria:
- "Request my data" and "Request deletion" actions available from the tenant portal and user profile
- DSAR request generates a complete export (profile, tenancy history, payments, documents) delivered securely within the policy's stated window
- Erasure request soft-deletes PII while preserving the financial/audit records the law requires landlords to keep
- Every request and its resolution logged in the audit trail
- Owner/agency notified when a request affects one of their tenants

**US-107 — Co-Tenant / Joint Tenancy Support** `[8 pts]`
*As a caretaker or owner, I want to link more than one tenant to a single tenancy so that couples, roommates, and business partners can share legal responsibility for one unit*

Acceptance Criteria:
- A tenancy supports multiple tenant records with one designated primary contact
- Each co-tenant can view the shared tenancy from their own portal login
- Lease document lists all co-tenants and requires each to digitally sign
- Payments and arrears are tracked once per tenancy, never duplicated per co-tenant
- Vacating/renewal workflows explicitly handle partial turnover (one co-tenant leaves, one stays)

**US-108 — Biometric / WebAuthn Login** `[5 pts]`
*As a user on a supported device, I want to log in with fingerprint or face ID so that daily login is fast without weakening security*

Acceptance Criteria:
- WebAuthn registration flow available from account settings
- Login offers biometric as an alternative second factor to SMS OTP where a platform authenticator is available
- Falls back cleanly to SMS OTP on unsupported devices/browsers
- Registered authenticators listed and individually revocable from session management

**US-109 — Caretaker Visitor Log** `[5 pts]`
*As a caretaker, I want to log visitors to the property so that there's a record of who came and went, for security and dispute purposes*

Acceptance Criteria:
- Caretaker logs visitor name, phone, unit visited, purpose, and time in/out from the mobile PWA
- Visible to the owner in the property's activity log
- Works offline like other caretaker flows, syncs when connectivity returns
- Searchable by date/unit for incident investigation

### 🔧 Technical Tasks
- [x] Integrate ClamAV (or a cloud AV API) into the upload pipeline for all file types
- [x] Build quarantine + rejection flow with audit logging
- [x] Build DSAR export service that aggregates all tenant-linked data into a downloadable package
- [x] Build erasure workflow with legal-hold logic for financial/audit records
- [x] Extend the Tenancy model to support multiple linked tenants with a primary flag
- [x] Update lease template and signing flow for multi-signer documents
- [x] Build WebAuthn registration and authentication endpoints
- [x] Build authenticator management UI in session settings
- [x] Build VisitorLog model, offline-queue support, and caretaker UI
- [x] Write tests for DSAR/erasure legal-hold edge cases and co-tenant payment attribution

**Built:** Virus scanning (`app/services/virus_scan_service.py`) talks to a clamd
daemon over the standard INSTREAM protocol; with no `CLAMAV_HOST` configured it
returns `SKIPPED` rather than blocking anything, and a configured-but-unreachable
daemon returns `FAILED` without blocking the upload either — scanning is defence
in depth, not a single point of failure for the upload button. `StoredFile` gets
a `scan_status`/`scanned_at`/`scan_detail` verdict rather than a separate log
table; an `INFECTED` result deletes the object and the row is never marked
`UPLOADED`, so it never becomes visible or attachable anywhere. A one-off
`rentflow.rescan_stored_files` Celery task (deliberately **not** on the beat
schedule — it's a catch-up run, not a recurring job) re-scans anything left
`PENDING`/`SKIPPED`/`FAILED`.

The visitor log (`VisitorLog` in `app/models/operations.py`) is a plain record,
not a state machine — check-in creates it, a separate check-out action closes
it, property-scoped through the existing `accessible_property_ids` caretaker
guard like every other field-operations table.

Co-tenancy (`TenancyCoTenant`) is purely additive next to `Tenancy.tenant_id`:
every invoice, payment and arrears query still keys off the one primary tenant,
so adding a co-tenant can never duplicate a charge or split a balance. The
portal's `_owned_tenancy_ids` now unions direct tenancies with co-tenancies, so
a roommate added this way sees the shared tenancy and balance from their own
login. The lease template gained a `co_tenant_names` variable (`lease_service.
build_variables`) rendered through a `{% if %}` guard in the starter template —
a tenancy with no co-tenants renders byte-for-byte as before. Each co-tenant is
sent their own signing request through the existing, already-generic
`POST /signatures` endpoint — no signature-service changes were needed for
"multi-signer," since it never assumed exactly one signer per document.

`DataRequest` (`app/models/privacy.py`) is scoped to tenants only. A staff
account's own equivalent rights already had a working path from Sprint 1
(`/auth/me/delete`, US-004's 30-day grace deletion) — export was the only gap,
closed with a plain `/auth/me/data-export` endpoint that needs no tracking
table since it's always self-served. Tenant erasure redacts name, phone
(replaced with a unique `erased-<id>` placeholder, since phone carries a
per-organisation uniqueness constraint), email, national ID, KYC photo
references, employment and emergency-contact fields, and notes — then archives
the row. `Tenancy`, `Invoice` and `Payment` rows are never touched, since Kenyan
tax and accounting law require they be kept regardless of what the tenant who
generated them later asks for. Both export and erasure are processed
synchronously and immediately (no approval queue — an export can't leak
anything the requester didn't already have a right to see, and erasure only
ever narrows what's stored), with the owner/agency notified either way. Erasing
an already-erased tenant is refused with a 409 rather than silently re-run.

WebAuthn (`app/services/webauthn_service.py`) rides the exact same login
challenge token `initiate_login` already mints for the SMS OTP: after password
verification, `authentication_options_for_login` checks whether this user has
any registered passkey and, if so, returns options alongside the OTP dispatch —
never instead of it. Whichever the user completes first (SMS code or passkey)
finishes the login; the other path is simply never consumed.
`complete_login_with_webauthn` (new) mirrors `complete_login`, substituting a
verified assertion for a verified OTP. Challenges live in Redis with the same
short TTL discipline as an OTP. A real, pre-existing test-infra gap surfaced
while testing this: `tests/conftest.py`'s `fake_redis` fixture patches a fixed
list of modules that hold their own `from app.core.redis import redis_client`
reference, and `webauthn_service` wasn't on it — so every WebAuthn test was
silently exercising a real local Redis connection rather than the fake one,
until a stale connection from a previous test's closed event loop surfaced it
as a `RuntimeError`. Fixed by adding the module to that list.

19 backend tests in `tests/test_sprint25.py`, including a full WebAuthn
registration-and-login ceremony driven by a from-scratch software authenticator
(`SoftAuthenticator`) — a real ES256 keypair, a spec-shaped `authenticatorData`
structure, a genuine CBOR "none"-format attestation object, and a real ECDSA
signature over the assertion — rather than mocking the verification call, so
the test proves the cryptographic round trip actually works end to end, not
just that the code path was reached.

**Deliberate limits:** the co-tenant clause added to the default lease template
names co-tenants but doesn't extend the ID-number clause to each of them
individually (only the primary tenant's national ID appears there) — adding a
second, fully-formed identity clause per co-tenant was judged more legally
risky to get wrong than valuable to add speculatively. The frontend's
device-name guess for a newly registered passkey ("iPhone/iPad passkey" /
"Android passkey" / "This device") is a plain user-agent sniff, not derived
from the authenticator's own attestation data. Nothing here has been run
against a real ClamAV daemon or a physical fingerprint sensor — both degrade
gracefully with no credentials/hardware configured, the same treatment every
other third-party integration in this codebase gets, and the WebAuthn
cryptography itself is verified for real by the software-authenticator test
rather than left as an assumption.

**Gap-closing pass (same day):** re-read against its own acceptance criteria
after the first "done" claim, which surfaced real gaps the pytest suite alone
couldn't see:

- The DSAR export bundle listed profile/tenancy/invoice/payment data but no
  *documents*, despite that being one of the four things US-106 explicitly asks
  for. Fixed by having `privacy_service` pull every document filed against the
  tenant (leases, notices, KYC files, inspection reports) through a new
  `vault_service.documents_for_tenant`, the same entity-resolution logic
  `tenant_vault` already used — extracted into a shared `_tenant_entity_pairs`
  helper so the in-app vault and the export bundle can never disagree about
  what counts as "this tenant's documents."
- US-107's explicit "vacating/renewal workflows require explicit handling of
  partial co-tenant turnover (one moves out, one stays)" had nothing built for
  it — co-tenants could be added and removed, but there was no way to make one
  the primary tenant when the *current* primary is the one leaving. Added
  `promote_co_tenant` (`POST /tenancies/{id}/co-tenants/{tenant_id}/promote`):
  swaps `Tenancy.tenant_id` to the co-tenant, drops the old primary from the
  tenancy entirely rather than leaving them behind as a stale co-tenant, and
  leaves every past invoice and payment untouched since they key off
  `tenancy_id`, never `tenant_id`.
- The visitor log's own acceptance criterion — "searchable by date/unit" — was
  true of the API (it already took `unit_id`/`since` params) but not of the
  page: the frontend only exposed an "on site" checkbox. Added the unit and
  date filters to `VisitorLogPage`.
- WebAuthn credential registration and removal weren't audit-logged, unlike
  every other security-sensitive action in this codebase (password changes,
  account deletion requests). Added `webauthn.credential_registered` /
  `webauthn.credential_removed` entries.
- No test proved a caretaker is actually refused the new DSAR and co-tenant
  endpoints — the permission matrix was correct (`CARETAKER` was never given
  `DATA_REQUEST_MANAGE`/`CO_TENANT_MANAGE`) but nothing exercised the refusal.
  Added `test_caretaker_is_denied_data_privacy_and_co_tenant_management`.

**A separate, more consequential gap this pass caught: the running app was
actually broken.** `pytest` builds its schema straight from the ORM
(`Base.metadata.create_all()`) and never proves the real Alembic migration or
the real Docker image — a gap this file has flagged before (Sprint 20's
`webhook_delivery_status` enum-case bug shipped the same way). Checking the
live `docker compose` stack found the backend container crash-looping:
`webauthn`/`clamd` were installed into the local `.venv` used for gate-running
but never rebuilt into the backend image, so the container's Python had no
`webauthn` module at all. Fixed with `docker compose build backend`, then
verified for real rather than assumed: `alembic upgrade head` against the live
Postgres (not just the test database), the resulting `scan_status` enum and
`visitor_logs` RLS policy inspected directly via `psql`, and every new
endpoint hit with `curl` against the real running server. A full Playwright
session then drove the actual browser against the actual dev server —
registered a real user via the API, logged a visitor, added a co-tenant, and
promoted that co-tenant to primary tenant, screenshotting each step — rather
than trusting that green `tsc`/`oxlint`/`npm run build` output meant the pages
actually render and their mutations actually work.

**Found but out of scope for this sprint:** there is no frontend anywhere in
the app for requesting a *lease* signature — Sprint 9 built the digital
signature service and a generic `POST /signatures` endpoint, but no UI ever
calls it for a lease (only the guarantor-agreement flow in tenant screening
triggers one automatically). So while a co-tenant *can* be sent a signing
request through that existing generic endpoint exactly like a primary tenant
can, "requires each to digitally sign" has no operator-facing button to make
it happen for anyone, co-tenant or not. This predates Sprint 25 and is a
pre-existing gap in Sprint 9's feature, not something introduced or promised
to be fixed here — flagging it rather than quietly building a lease-signing UI
as unplanned scope.

### 📦 Sprint 25 Deliverables
- ✅ Upload pipeline scans every file before storage, with a retry sweep for
  anything scanned before ClamAV was configured
- ✅ Tenants can self-serve a data export or erasure request from their portal;
  an owner/agency can raise either on a tenant's behalf
- ✅ Tenancies support multiple co-tenants, each with their own portal
  visibility and signing request, with zero change to how payments or arrears
  are calculated
- ✅ Biometric login available as a WebAuthn second factor alongside (not
  instead of) SMS OTP, with full passkey management in Settings
- ✅ Caretaker visitor log working, property-scoped like every other
  field-operations table

---

## Sprint 26A — Masterplan Gap Closure
**Weeks 51–52 (run alongside Sprint 26) | Story Points Target: 55**
**🎯 Sprint Goal:** Build the masterplan features that no sprint had ever picked up — not the ones that were scoped and unbuilt, the ones that were promised and forgotten

> **Why this exists.** A second gap review on 2026-09-07 read the masterplan
> against the code rather than against this plan, and found sixteen promised
> capabilities that appeared in **no sprint at all**. They are not late; they
> were never scheduled. Each was confirmed absent by grep before being written
> here, and each is now built. Numbered `26A` rather than renumbering
> Sprints 26–29, which are unaffected.

### 📖 What was missing, and what was built

**US-M01 — Meter reading camera OCR** `[5 pts]` (Module 5)
The meter photo was already mandatory and already stored; nothing read it. Now
`ocr_service` proposes a reading from the photo and the capture form pre-fills
it *only* above a confidence threshold. `current_reading` remains what a person
asserted — `ocr_reading`, `ocr_confidence` and `ocr_accepted` sit beside it as
the record of what the machine proposed and whether the caretaker took it.

**US-M02 — Utility analytics** `[5 pts]` (Module 12, US-054 acceptance criteria)
Consumption was computed at reading time and billed, and never aggregated.
`analytics_service.utility_analytics` adds the consumption trend, above-average
unit flagging against property-then-portfolio peers, and billing efficiency —
the gap between what was measured and what was actually charged, which is the
single commonest way utility revenue leaks out of a manual process.

**US-M03 — Payment-behaviour segmentation** `[5 pts]` (Module 12, US-054)
Arrears answered "who owes money today". Nothing answered "who is a problem". A
tenant who clears every invoice three weeks late never enters the top-defaulters
list yet costs the same cash-flow pain monthly. Settlement dates are recovered
by replaying the real oldest-first allocation policy over each tenancy's
history, because `Invoice.amount_paid` records the outcome but not the day.

**US-M04 — Tenant turnover and average tenancy duration** `[3 pts]` (Module 12)
`property_performance()` returned occupancy, collection rate and maintenance
cost only. Turnover is now measured against tenancies actually held rather than
unit count — an empty unit has nobody in it to leave.

**US-M05 — Management agreement generation, dual OTP signing and termination** `[13 pts]`
(masterplan §"Management Agreement Module")
Sprint 7 built storage and display. The instrument itself did not exist. Now:
a generated PDF, terms frozen as signed (so editing the owner profile afterwards
cannot rewrite what was agreed), two independent OTP signing requests that must
both complete before the agreement is in force, and a termination workflow where
notice starts a clock and management continues until it runs out.

**US-M06 — Editable communication templates** `[8 pts]` (Module 21)
Every notification's copy was hardcoded in whichever service raised it.
`notification_service.send` now consults a per-organisation template per channel
and falls back to the built-in wording whenever there isn't one, or the template
references a variable the caller never supplied — a slightly generic message
that is correct beats a personalised one with a hole in it.

**US-M07 — Import properties, units and historical payments** `[8 pts]` (Module 20)
The importer had one sheet, "Tenants", and the property had to exist already,
which made a first migration impossible. Four sheets now, in the order a
landlord actually migrates. Historical payments allocate exactly as a live one
would but issue no receipt and notify nobody — it is history, not a new payment.

**US-M08 — Magic-link login for the tenant portal** `[5 pts]` (Security §
Authentication Layers)
A tenant signs in twice a year on a borrowed phone and mostly has no email
address on file, so password reset was not a route back in for them. The request
endpoint answers identically whether or not the number belongs to a tenant, so
it cannot be walked as a directory of a landlord's book.

**US-M09 — Sample data / demo mode** `[5 pts]` (Module 24)
An empty account demonstrates nothing. Seeding records every created id in a
`DemoDataset` ledger and teardown walks it in reverse, so removal is exact and
can never take a customer's own row with it.

**US-M10 — Video tutorials** `[2 pts]` (Module 24)
`HelpArticle` gains video fields with an https-and-known-provider guard, and the
help search gains a `video_only` filter. `body` stays required — text is
searchable and works on a metered connection.

**US-M11 — Account suspension and reactivation** `[3 pts]` (Module 25)
`Organization.is_active` was enforced at `deps.py` and nothing could flip it.
Suspension now records why, by whom, and revokes every live session so the cut
takes effect immediately; the refused request says why rather than being a
locked door with no notice on it.

**US-M12 — Breach detection and the 72-hour notification protocol** `[8 pts]`
(Kenya DPA s.43)
A platform-level breach register with the clock running from awareness, hourly
escalation at 48 and 72 hours, a required regulator reference to mark a breach
notified, and a required reason to dismiss one. Two automatic detectors
(credential stuffing, export bursts) raise candidates; everything else is
reported by a person, which is how breaches are actually found.

**US-M13 — Dual approval for cash above a threshold** `[5 pts]` (Fraud Prevention)
Over-limit cash raised an alert and was banked anyway. Above the organisation's
threshold it is now recorded but held — not allocated, not receipted, tenant not
told — until a *different* person approves it. Off by default, and skipped
entirely when nobody else could approve, so a solo landlord is never locked out
of their own money.

**US-M14 — Native mobile app evaluation** `[2 pts]` (Phase 4 deliverable)
Written up in `docs/native-mobile-evaluation.md`. Decision: stay on the PWA, with
the instrumentation needed to revisit it named and the triggers that would
reopen it listed.

**US-M15 — Concurrent session limits** `[2 pts]` (Security § Authentication)
List, revoke and trust existed; no cap did. The newest session always survives —
signing in must never fail because you already had too many logins.

**US-M16 — Per-organisation encryption keys** `[5 pts]` (Multi-Tenant Data Isolation)
Envelope encryption. Every stored third-party credential — eTIMS, portal API
keys, accounting OAuth tokens, webhook secrets — is now sealed under a key
belonging to that one organisation. Rotating one customer's key no longer forces
every other customer to re-enter theirs, and ciphertext lifted from one tenant is
inert against another. Legacy master-key ciphertext still reads, and moves across
the next time it is saved.

### 🔧 Engineering debt closed alongside

- [x] **Frontend tests** — there were none across 101 `.tsx` files. 92 now, over
      the layer that fails silently: money formatting, the API client's
      concurrent-refresh collapsing (verified to fail when the collapsing is
      removed), the offline queue's FIFO and idempotency guarantees, the auth
      store, the route guard and the UI primitives.
- [x] **Coverage measured for the first time** — backend **66%**, frontend
      **83%** over the tested layer. Both enforced in CI as a ratchet. The
      Definition of Done asks for 80% backend; see `pyproject.toml` for where
      the gap is and why the floor was not set at a number that fails today.
- [x] **Sentry wired in** — it had been in the stack list since the masterplan
      and never installed. PII scrubbing is explicit, not left to defaults.
- [x] **Supply-chain scanning in CI** — `pip-audit`, `npm audit` and CodeQL.
      Dependabot alone only opens PRs on its own schedule.
- [x] **Application rate limiting** — only the external API-key surface was
      metered. The app's own endpoints, including the ones that send SMS and
      render PDFs, had nothing but the login lockout in front of them.
- [x] **Latent bug fixed while testing** — `Button` did not set `type`, so any
      non-submit button inside a form submitted it. 264 of 287 usages relied on
      the default.

### 📦 Sprint 26A Deliverables
- Sixteen masterplan capabilities that were in no sprint, now built and tested
- 66 new backend tests (`test_sprint26.py`, `test_rate_limit.py`) and 92
  frontend tests, from zero
- Coverage, error tracking, supply-chain scanning and rate limiting in CI

---

## Sprint 26 — Enterprise Identity & Access
**Weeks 51–52 | Story Points Target: 50**
**🎯 Sprint Goal:** Give enterprise IT departments and large agencies the identity and access controls they'll actually require before signing a contract

---

### 📖 User Stories

**US-110 — SSO / SAML Integration** `[13 pts]`
*As an enterprise account admin, I want my staff to log in via our own identity provider so that access is centrally managed and deprovisioning is instant when someone leaves*

Acceptance Criteria:
- SAML 2.0 and OAuth2/OIDC connection configurable per organization
- Just-in-time user provisioning on first SSO login, mapped to existing roles
- Organization can enforce SSO-only login (disable password login) for their users
- Tested against at least one real IdP (e.g., Google Workspace, Azure AD/Entra, Okta)
- SSO configuration changes logged in the audit trail

**US-111 — Custom Roles & Permission Builder** `[13 pts]`
*As an agency admin, I want to define custom roles beyond the 8 built-in ones so that access matches our actual org chart*

Acceptance Criteria:
- Admin can create a role, name it, and toggle granular permissions (view/create/edit/delete/approve) per resource type
- Custom roles assignable to users alongside built-in roles
- Permission changes take effect immediately and are audit logged
- Built-in roles remain as sensible defaults/templates that can be cloned as a starting point

**US-112 — Enterprise Session & Device Policy** `[8 pts]`
*As an enterprise admin, I want stricter, centrally-configured session and device policies so that our security posture meets our own IT standards*

Acceptance Criteria:
- Per-organization policy: max concurrent sessions per user, forced re-auth interval, device trust duration
- Admin can view and revoke any user's active sessions org-wide, not just their own
- Policy violations (e.g., login from outside the IP whitelist) generate a security event, building on the existing IP whitelist and SecurityEvent model

**US-113 — Security Compliance Pack** `[8 pts]`
*As an enterprise buyer's procurement team, I want a documented security posture so that we can complete our vendor risk assessment without a lengthy back-and-forth*

Acceptance Criteria:
- Downloadable security whitepaper covering encryption, RLS isolation, RBAC, and audit logging
- SOC 2 readiness self-assessment checklist published, with gaps stated honestly rather than implied as certified
- Public status/uptime page reachable outside the main app
- Data Processing Agreement (DPA) template available for enterprise customers to countersign

### 🔧 Technical Tasks
- [ ] Build SAML 2.0 SP endpoints and metadata configuration UI
- [ ] Build OIDC connection flow as an alternative to SAML
- [ ] Build JIT provisioning and role-mapping configuration
- [ ] Build organization-level "SSO required" enforcement
- [ ] Build custom role/permission data model and builder UI
- [ ] Migrate existing permission checks to consult custom roles alongside built-in ones
- [ ] Build org-wide session policy configuration and admin session-revocation UI
- [ ] Write and publish the security whitepaper and SOC 2 readiness checklist
- [ ] Stand up a public status page (self-hosted or a lightweight third-party page)
- [ ] Write SSO and custom-role permission isolation tests

### 📦 Sprint 26 Deliverables
- SSO/SAML login working against at least one real identity provider
- Custom role builder live for agency/enterprise accounts
- Org-wide session and device policy enforcement
- Published security whitepaper, SOC 2 checklist, and status page

---

## Sprint 27 — Subscription Billing Engine & White-Label
**Weeks 53–54 | Story Points Target: 71**
**🎯 Sprint Goal:** RentFlow can finally charge, meter, and bill its own customers automatically — on every revenue stream in masterplan §10, not just the monthly plan fee — and large agencies can run the platform under their own brand

> **Scope note (Sprint 26 gap review):** this sprint originally covered the
> subscription fee alone. Transaction fees, the six premium add-ons, annual
> billing and the one-time fee schedule were all in masterplan §10 and in no
> sprint. US-117a and US-117b close that, which is what takes the target from
> 55 to 71 points — over a normal sprint's capacity, so if it has to be split,
> **US-117a ships first**: transaction fees accrue per payment and cannot be
> backfilled from history that was never metered.

---

### 📖 User Stories

**US-114 — Subscription Billing Engine** `[13 pts]`
*As the business, I want subscriptions to actually be billed and enforced so that revenue collection isn't manual and plan limits mean something*

Acceptance Criteria:
- Plan definitions (Starter/Professional/Business/Enterprise) enforced: unit count, user count, and feature flags checked at the point of use, not just displayed
- Recurring billing via M-Pesa and card, monthly or annual, with automatic retry on failure
- Invoices generated for RentFlow's own subscription fee, downloadable by the customer
- Grace period and read-only lockout on non-payment, mirroring the existing trial-expiry lockout pattern
- Plan upgrade/downgrade prorates correctly

**US-115 — Referral Credit Application** `[5 pts]`
*As a customer who referred a friend, I want my earned credit to actually reduce my bill so that the referral program pays out as promised*

Acceptance Criteria:
- The existing `credit_months` ledger is applied automatically against the next invoice generated by the new billing engine
- Customer sees applied credit itemized on their invoice
- Admin can view and adjust credit balances with an audit trail

**US-116 — Usage Metering Dashboard** `[8 pts]`
*As an account owner, I want to see my usage against my plan limits so that I know when I'm approaching an upgrade point*

Acceptance Criteria:
- Dashboard shows units, users, storage, API calls, and SMS sent this period vs. plan limits
- Approaching-limit warning (e.g., 90% of unit allowance) with an upsell prompt
- Usage history available for the last 12 months

**US-117 — White-Label & Custom Branding** `[13 pts]`
*As a large agency, I want to run RentFlow under our own brand so that our clients see us, not RentFlow*

Acceptance Criteria:
- Custom domain support (agency's own subdomain or domain)
- Custom logo, color scheme, and sender name applied across the app, emails, WhatsApp templates, and PDFs
- "Powered by RentFlow" footer configurable (visible/hidden per plan tier)
- White-label configuration isolated per organization — no bleed between agencies

**US-117a — Transaction Fee Collection** `[8 pts]`
*As the business, I want the 0.5% M-Pesa transaction fee to be metered and collected so that the revenue stream the pricing model is built on actually exists*

> Added in the Sprint 26 gap review. The masterplan's §10 puts transaction fees
> at KES 50–500 per unit per month — on a 200-unit agency that is comparable to
> the subscription itself — and the sprint that builds billing did not mention
> them. Subscription-only billing would ship a revenue model that is materially
> smaller than the one the business case assumes.

Acceptance Criteria:
- 0.5% accrued on every confirmed M-Pesa payment processed through the platform, capped at **KES 500 per transaction**
- Fee accrues at confirmation, in its own ledger line — never deducted from the landlord's money in transit, and never from a payment that later reverses
- Cash, bank transfer and cheque accrue nothing: the fee is for payments RentFlow actually processed
- Accrued fees roll into the next subscription invoice, itemised separately from the plan fee
- The landlord can see the running fee total for the current period before it is billed
- Fee rate and cap are configurable per plan, so an enterprise contract can negotiate them

**US-117b — Add-Ons, Annual Billing and One-Time Fees** `[8 pts]`
*As the business, I want the six premium add-ons, the annual discount and the one-time fee schedule to be sellable so that the whole of §10's price list is billable, not just the monthly plan row*

> Also added in the Sprint 26 gap review — §10 lists six add-ons, a two-months-free
> annual commitment and a one-time fee schedule, none of which appeared in this
> sprint. Annual billing in particular is a cash-flow and churn mechanism, not a
> discount: leaving it out means every customer stays monthly by default.

Acceptance Criteria:
- Add-ons subscribable per organization, each with its own monthly fee, prorated on mid-period activation: eTIMS Compliance (KES 1,000), Advanced Analytics (KES 2,000), Extra SMS Bundle (KES 500 / 500 SMS), Extra Storage (KES 500 / 50GB), Vacancy Marketing Portal (KES 1,000), Open API for Starter/Professional (KES 3,000)
- An add-on grants the feature flag or quota it pays for — buying the eTIMS module switches eTIMS on, buying storage raises the storage limit
- Annual billing offered alongside monthly at the §10 annual price (two months free), with the saving shown at the point of choice
- Switching monthly→annual mid-term credits the unused monthly portion
- One-time fees (enterprise onboarding, data migration, custom integration, training) raisable as a manual invoice line by RentFlow staff, on the same invoice as the subscription
- Special pricing programs supported as a per-organization discount percentage with a reason on the record: non-profit/faith-based 20%, student accommodation Starter pricing, early-adopter locked pricing

### 🔧 Technical Tasks
- [ ] Build Plan/Subscription/Invoice data model for RentFlow's own billing
- [ ] Build plan-limit enforcement middleware (units, users, storage, API calls, SMS)
- [ ] Build recurring billing via M-Pesa STK and card, reusing the existing Daraja integration where possible
- [ ] Build dunning flow: retry, grace period, read-only lockout
- [ ] Wire the `credit_months` ledger into invoice generation
- [ ] Build usage metering aggregation and dashboard UI
- [ ] Build custom domain routing and SSL provisioning per organization
- [ ] Build white-label theming (logo, colors) applied to the app shell, PDFs, and notification templates
- [ ] Build the transaction fee accrual: hook `payment_service._confirm`, 0.5% capped at KES 500, M-Pesa only, reversed if the payment reverses
- [ ] Build the add-on catalogue and per-organization subscriptions, with proration and feature-flag/quota grants
- [ ] Build annual billing terms, the two-months-free price, and monthly→annual switching with credit
- [ ] Build the one-time fee line item, raisable by platform staff onto a subscription invoice
- [ ] Build per-organization discount programs (non-profit, student, early adopter) with an auditable reason
- [ ] Write billing engine tests (proration, dunning, credit application, plan-limit enforcement, fee cap boundary, reversal, annual switch)

### 📦 Sprint 27 Deliverables
- Subscriptions billed and enforced automatically — no more implicit free-forever accounts
- Transaction fees metered and billed — the second revenue stream in §10 is live
- All six premium add-ons sellable, with annual billing and one-time fees
- Referral credits actually reduce a real invoice
- Usage dashboard showing plan consumption
- Agencies can run RentFlow under their own domain and branding

---

## Sprint 28 — Financial Intelligence & Trust Infrastructure
**Weeks 55–56 | Story Points Target: 50**
**🎯 Sprint Goal:** Deepen the financial and fraud intelligence beyond rule-based thresholds, and close the accounting and communication gaps an enterprise finance team will notice

---

### 📖 User Stories

**US-118 — Double-Entry General Ledger** `[13 pts]`
*As an accountant, I want a real general ledger behind the numbers so that RentFlow's financial reports reconcile the way accounting software expects, not just as one-way exports*

Acceptance Criteria:
- Every financial event (payment, disbursement, fee, refund, deposit) posts a balanced double-entry journal entry
- Trial balance and ledger detail viewable per organization/owner
- The existing accounting sync (QuickBooks/Xero) reads from the ledger rather than ad hoc tables
- Historical data backfilled from existing payment/disbursement records

**US-119 — ML-Based Fraud Scoring** `[8 pts]`
*As the system, I want fraud detection that learns from confirmed and dismissed alerts so that accuracy improves over time instead of relying on fixed thresholds forever*

Acceptance Criteria:
- Historical `FraudAlert` outcomes (confirmed vs. suppressed) used to train/tune a scoring model
- Each new alert carries a confidence score, not just a binary rule match
- Rule-based detection remains as a fallback/floor — the model augments rather than replaces it
- Model performance (false positive rate) tracked and visible to the RentFlow team

**US-120 — General Two-Way Messaging** `[8 pts]`
*As a tenant, I want to reply to any WhatsApp notification and have my message reach the right person in the system, not just respond to a Yes/No reference check*

Acceptance Criteria:
- Inbound WhatsApp messages matched to the sending tenant/user and threaded against the relevant tenancy, maintenance request, or conversation
- Caretaker/owner sees inbound replies in-app and can respond from the app or WhatsApp
- Unmatched senders (unknown numbers) routed to a general inbox for manual triage

**US-121 — Rent Pricing Recommendations** `[8 pts]`
*As a property owner, I want data-informed rent pricing suggestions so that I'm not leaving money on the table or overpricing a vacant unit*

Acceptance Criteria:
- Recommendation built from the owner's own portfolio (extends the existing rent-review suggestions) to include comparable vacant-unit fill times and rejection rates at the current price
- Suggested range shown with the assumptions used, never presented as external market data unless a real market data source is later integrated
- Available on the vacancy listing and unit detail screens

### 🔧 Technical Tasks
- [ ] Design and build the double-entry ledger schema (accounts, journal entries, postings)
- [ ] Wire every financial-event service to post ledger entries
- [ ] Build trial balance / ledger detail UI and a backfill migration
- [ ] Repoint QuickBooks/Xero sync to read from the ledger
- [ ] Build fraud alert outcome tracking and a lightweight scoring model (logistic regression or similar — no need for a heavyweight ML platform at this scale)
- [ ] Build inbound WhatsApp webhook message-threading service
- [ ] Build a unified inbox UI for matched and unmatched inbound messages
- [ ] Extend the rent-review service with fill-time/rejection-rate signals
- [ ] Write ledger-balance invariant tests (every entry must net to zero) and fraud-model backtests

### 📦 Sprint 28 Deliverables
- Real general ledger behind every financial report and accounting sync
- Fraud detection scored by a learning model, not fixed thresholds alone
- Two-way WhatsApp conversations threaded into the right context
- Rent pricing recommendations informed by the owner's own vacancy data

---

## Sprint 29 — Financial Services & Ecosystem Partnerships
**Weeks 57–58 | Story Points Target: 50**
**🎯 Sprint Goal:** Turn the partnership ambitions in the masterplan's Future Expansion section into real integrations, and round out the remaining physical-space and payment gaps. Phase 5 is DONE.

---

### 📖 User Stories

**US-122 — Credit Bureau Integration** `[13 pts]`
*As a property owner, I want to check a prospective tenant's credit history so that screening decisions are backed by more than income ratio and references*

Acceptance Criteria:
- Integration with at least one Kenyan credit bureau (TransUnion Kenya or Metropol) via their API
- Credit check triggered from the existing tenant application/screening flow, with the applicant's consent captured first (DPA-compliant)
- Credit score/report folds into the existing 0–100 screening score as a new weighted component
- Bureau unavailable/no-credentials-configured degrades gracefully — screening still works without it, consistent with every other optional integration

**US-123 — Card Payment Support** `[8 pts]`
*As a tenant paying from outside Kenya or without M-Pesa, I want to pay by card so that I'm not blocked from paying rent*

Acceptance Criteria:
- Card payment via Flutterwave or Stripe available alongside M-Pesa and bank transfer in the tenant portal
- Same reconciliation, receipt, and audit trail treatment as any other payment method
- Currency handling explicit (KES primary, card processor handles FX where applicable)

**US-124 — Bank Partner & Insurance Marketplace Foundations** `[13 pts]`
*As a property owner, I want visibility into financing and insurance options relevant to my portfolio so that RentFlow is useful beyond day-to-day operations*

Acceptance Criteria:
- Rent-roll summary exportable in a bank-partner-ready format (foundation for a future loan-referral integration, not a live lending product)
- Insurance marketplace tab surfaces partner products relevant to the owner's property types — initially a curated directory with lead capture, live quoting once a real partner is signed
- Both explicitly framed as informational/referral, with RentFlow never handling loan or policy funds

**US-125 — Floor Plan & Unit Mapping** `[8 pts]`
*As a property owner, I want to see a visual floor plan of my property with unit status overlaid so that I can understand occupancy spatially, not just as a list*

Acceptance Criteria:
- Floor plan image uploadable per property (or per floor for multi-floor buildings)
- Units placeable on the plan via simple click-to-pin positioning
- Plan view color-codes units by status (occupied/vacant/maintenance), matching the existing status colors
- Falls back to the existing list view where no plan has been uploaded

**US-126 — Zapier / Webhook-Friendly Ecosystem** `[5 pts]`
*As a smaller customer without developer resources, I want to connect RentFlow to other tools via Zapier so that I get integration value without writing code*

Acceptance Criteria:
- RentFlow published as a Zapier (or Make.com) app using the existing public API and webhook events
- Common triggers (payment received, tenant added, maintenance status changed) and actions (create tenant, send announcement) available
- Documented alongside the existing developer portal

### 🔧 Technical Tasks
- [ ] Integrate TransUnion Kenya or Metropol API with consent capture
- [ ] Fold the credit result into the screening score calculation
- [x] Integrate a Flutterwave/Stripe card payment flow into the tenant portal payment options — **built with Paystack** rather than Flutterwave/Stripe (native KES support on Kenyan card rails). Portal `Pay by card` opens a Paystack checkout; the charge webhook is HMAC-SHA512 verified, replay-locked in Redis, re-verified against Paystack's own API before banking, and then settles through the same `_confirm` path as M-Pesa, so reconciliation, receipts and the audit trail are identical. Hidden entirely unless `PAYSTACK_SECRET_KEY` is set. The rest of Sprint 29 is untouched.
- [ ] Build a rent-roll export format for bank partner referrals
- [ ] Build an insurance marketplace directory and lead capture UI
- [ ] Build floor plan upload and click-to-pin unit mapping UI
- [ ] Publish a Zapier app (or Make.com equivalent) wrapping the existing public API
- [ ] Write tests for credit bureau consent/degrade-gracefully behavior and card payment reconciliation

### 🏁 Phase 5 Complete — Enterprise-Ready
**All deliverables across Phase 5:**
- Every masterplan gap identified in the Sprint 24 review closed
- Real subscription billing, white-labeling, SSO, and custom roles — the features enterprise procurement actually checks for
- General ledger accounting, ML-assisted fraud detection, and two-way messaging
- Credit bureau, card payment, bank/insurance partnership foundations, and floor plan mapping

---

## Sprint Velocity & Timeline Summary

| Phase | Sprints | Weeks | Key Milestone |
|-------|---------|-------|---------------|
| **Sprint 0** | Setup | 1 week | Development environment ready |
| **Phase 1** | 1–6 | Weeks 1–12 | First paying customer |
| **Phase 2** | 7–12 | Weeks 13–24 | First agency customer (50+ units) |
| **Phase 3** | 13–18 | Weeks 25–36 | All rental types supported |
| **Phase 4** | 19–24 | Weeks 37–48 | Full platform launch — 1,000+ units |
| **Phase 5** | 25–29 | Weeks 49–58 | Enterprise-ready: billing, SSO, white-label, financial services |

---

## Definition of Done (Global)

Every user story is only marked DONE when ALL of the following are true:

- [ ] Feature works as described in acceptance criteria
- [ ] API endpoints have unit tests (minimum 80% coverage)
- [ ] No critical or high-severity bugs
- [ ] Mobile responsive (tested on 375px and 768px viewport)
- [ ] Offline behavior tested (for caretaker PWA features)
- [ ] Audit log entry generated for all data-modifying actions
- [ ] Notification delivered (where applicable — WhatsApp/SMS/push)
- [ ] Code reviewed (self-review checklist completed)
- [ ] Deployed to staging and smoke-tested
- [ ] Performance: page load under 3 seconds on 3G
- [ ] Security: new endpoints tested for unauthorized access attempt

---

## Technology Stack Quick Reference

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 18 + TypeScript + Vite | UI Application |
| Styling | Tailwind CSS + Shadcn/UI | Design System |
| State | Zustand + TanStack Query | Data & UI State |
| PWA | Workbox | Offline & Push |
| Backend | FastAPI (Python 3.11+) | REST API |
| ORM | SQLAlchemy + Alembic | Database Access |
| Queue | Celery + Celery Beat | Background & Scheduled Tasks |
| Cache | Redis | Sessions, Cache, Queue Broker |
| Database | PostgreSQL 15 | Primary Data Store |
| Files | Cloudflare R2 | Document & Photo Storage |
| PDF | WeasyPrint | Receipt, Lease & Report Generation |
| Payments | Safaricom Daraja API | M-Pesa Integration |
| SMS | Africa's Talking | SMS Notifications |
| Messaging | WhatsApp Business API | Rich Notifications |
| Tax | KRA eTIMS API | Receipt Compliance |
| Hosting | DigitalOcean → AWS | Infrastructure |
| CI/CD | GitHub Actions | Deployment Pipeline |
| Monitoring | Sentry + Grafana | Error & Performance |

---

## Key Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Daraja API instability during Sprint 4 | Medium | High | Build robust retry and fallback mechanisms from day one |
| WhatsApp Business API approval delays | Medium | Medium | Apply in Sprint 1, use SMS fallback during approval period |
| eTIMS API changes from KRA | Low | High | Build eTIMS as isolated module, monitor KRA communications weekly |
| Scope creep delaying milestones | High | High | Strict sprint planning, defer non-critical requests to backlog |
| Single developer burnout | Medium | High | Build in buffer sprints (QA sprints), maintain sustainable pace |
| Performance issues at scale | Low | High | Implement pagination and caching from Sprint 1, not as afterthought |
| M-Pesa sandbox vs production differences | Medium | Medium | Test with real M-Pesa account (own phone) before customer launch |

---

*Sprint Plan Version 1.0*
*Prepared: September 2026*
*Project: RentFlow Kenya — Avinaya Solutions*
*Developer: Kelvin*
*Review: End of each sprint — adjust next sprint based on actual velocity*

---

> **"Ship working software every two weeks. Each sprint should make a real landlord's life better."**
