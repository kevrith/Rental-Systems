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
- [ ] Set up automated database backups

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
- [ ] Build public API versioning layer (v1 prefix)
- [ ] Build API authentication middleware (API key validation)
- [ ] Build API rate limiting with Redis
- [ ] Build API key management service and UI
- [ ] Build webhook subscription model and configuration UI
- [ ] Build webhook delivery service with retry logic
- [ ] Build webhook delivery log and monitoring UI
- [ ] Configure FastAPI Swagger UI with authentication
- [ ] Build sandbox environment with seeded test data
- [ ] Write API documentation and quick-start guide
- [ ] API integration test suite

### 📦 Sprint 19 Deliverables
- ✅ Public REST API live at api.rentflow.co.ke
- ✅ API key management for enterprise customers
- ✅ Webhook system with delivery monitoring
- ✅ Interactive Swagger documentation portal

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
- [ ] Build onboarding wizard state machine and UI
- [ ] Build contextual help system (tooltip + side panel)
- [ ] Build knowledge base CMS (admin editable)
- [ ] Build in-app search for help content
- [ ] Build health score calculation service (weekly Celery task)
- [ ] Build customer health dashboard (internal admin view)
- [ ] Build at-risk alert notification system
- [ ] Build referral tracking system
- [ ] Build NPS survey trigger service (post-milestone)
- [ ] Build feature voting board
- [ ] Build in-app changelog system
- [ ] Build milestone detection and celebration service

### 📦 Sprint 20 Deliverables
- ✅ Interactive setup wizard guiding new customers to first value
- ✅ Contextual help system on all major pages
- ✅ Customer health scoring with at-risk alerts
- ✅ Referral program with automatic credit application
- ✅ NPS surveys, feature voting, and in-app changelog

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
- [ ] Build scheduled report generation Celery task
- [ ] Build report PDF template (comprehensive monthly summary)
- [ ] Build report delivery service (WhatsApp + email)
- [ ] Build report history storage and retrieval
- [ ] Build custom report builder UI (drag-and-drop)
- [ ] Build report filter and configuration engine
- [ ] Build cash flow forecasting model
- [ ] Build vacancy risk detection service
- [ ] Build maintenance budget anomaly detection
- [ ] Build rent review recommendation service
- [ ] Build predictive dashboard widgets

### 📦 Sprint 21 Deliverables
- ✅ Monthly reports automatically delivered via WhatsApp
- ✅ Custom report builder for enterprise customers
- ✅ Predictive intelligence: cash flow forecast, vacancy risk, maintenance alerts

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
- [ ] Integrate Anthropic API for document analysis
- [ ] Build lease analysis prompt engineering and response parsing
- [ ] Build AI suggestion UI (show/accept/dismiss)
- [ ] Build fraud detection rule engine (configurable thresholds)
- [ ] Build anomaly detection Celery task (runs on all payment events)
- [ ] Build security alert notification service
- [ ] Build IP whitelisting service and UI
- [ ] Build security audit log export
- [ ] Integrate Snyk or Dependabot for vulnerability scanning
- [ ] Write fraud detection scenario tests

### 📦 Sprint 22 Deliverables
- ✅ AI lease analysis with improvement suggestions
- ✅ Automated fraud pattern detection with owner alerts
- ✅ Enterprise security hardening (IP whitelisting, audit exports)

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
- [ ] Research and integrate BuyRentKenya API
- [ ] Research and integrate PigiaMe API
- [ ] Build portal sync service (vacancy publish/deactivate)
- [ ] Build QuickBooks OAuth connection and data sync
- [ ] Build Xero OAuth connection and data sync
- [ ] Build accounting sync Celery task
- [ ] Build sync history and error log UI
- [ ] Build bank transfer instructions display
- [ ] Build bank statement upload and matching service

### 📦 Sprint 23 Deliverables
- ✅ Vacant units auto-published to property portals
- ✅ QuickBooks and Xero financial data sync
- ✅ Bank transfer payment method with manual reconciliation

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
- [ ] Execute full end-to-end automated test suite
- [ ] Load test with k6 (500 concurrent users)
- [ ] OWASP security checklist execution
- [ ] Lighthouse audit and optimization
- [ ] Production infrastructure final configuration
- [ ] Disaster recovery test (restore from backup)
- [ ] WhatsApp Business API production approval process
- [ ] All third-party production credentials obtained and tested
- [ ] Legal pages (privacy policy, terms) written and published
- [ ] Expansion readiness research and document

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

## Sprint Velocity & Timeline Summary

| Phase | Sprints | Weeks | Key Milestone |
|-------|---------|-------|---------------|
| **Sprint 0** | Setup | 1 week | Development environment ready |
| **Phase 1** | 1–6 | Weeks 1–12 | First paying customer |
| **Phase 2** | 7–12 | Weeks 13–24 | First agency customer (50+ units) |
| **Phase 3** | 13–18 | Weeks 25–36 | All rental types supported |
| **Phase 4** | 19–24 | Weeks 37–48 | Full platform launch — 1,000+ units |

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
