# Avaland Commission Suite — Production System Plan

> **Document Purpose:** Blueprint for evolving `app_management.py` (6 484-line POC) into a production-grade **Finance Commission & Sales Management System** for property developers.

---

## Table of Contents

1. [Current State Audit](#1-current-state-audit)
2. [Target Product Vision](#2-target-product-vision)
3. [Module Architecture](#3-module-architecture)
4. [Feature Gap Analysis](#4-feature-gap-analysis)
5. [Data Model Evolution](#5-data-model-evolution)
6. [Feature Specifications](#6-feature-specifications)
7. [Phase Roadmap](#7-phase-roadmap)
8. [Technical Debt & Refactoring](#8-technical-debt--refactoring)
9. [Infrastructure & Deployment](#9-infrastructure--deployment)
10. [Risk Register](#10-risk-register)

---

## 1. Current State Audit

### 1.1 What Already Exists

| Area | Status | Lines | Notes |
|------|--------|-------|-------|
| **Design System (CSS)** | ✅ Production-quality | ~2 500 | Glassmorphism, animations, dark sidebar, responsive cards |
| **Project Dashboard** | ⚠️ Mock data only | ~450 | CRUD form, KPIs, filters, health indicators, expandable project cards |
| **Memorandums Page** | ✅ Functional | ~550 | 3-step upload wizard (PDF→OCR→Review), approve/reject, side-by-side review |
| **Extracted Rules Page** | ✅ Functional | ~380 | Rule cards, validation, flagging, pagination, confidence bars, filters |
| **Agent Commissions** | ⚠️ Demo data | ~600 | 4-tab dashboard: Breakdown, Entitlement, Teams, Analytics |
| **Entitlement Tracking** | ⚠️ Basic | ~280 | Payment history, progress rings, search/filter, balance tracking |
| **Team Overview** | ⚠️ Basic | ~180 | Team cards, leaderboard, KPIs |
| **Analytics** | ⚠️ Basic | ~200 | Rule utilization table, performance charts |
| **Engine Integration** | ✅ Working | ~110 | `run_engine_calculation()`, `pricing_result_to_sale_entry()`, `save_sale_to_json()` |
| **OCR Pipeline** | ✅ Working | ~120 | `_convert_pdf_to_images()`, `_run_ocr_text()`, `_run_ocr_table()`, `_run_rule_extraction()` |
| **Data Layer** | ❌ File-based JSON | — | `management_mock_data.json`, `memo_store.json`, `artifact/*.json` |
| **Authentication** | ❌ None | — | No user/role management |
| **Audit Trail** | ❌ None | — | No action logging |

### 1.2 Current Data Structures

```
UnitSale:
  unit_id, project, block, floor, unit_type, buyer_name, buyer_ic
  sale_price, spa_date, loan_margin
  commission_rate, commission_amount
  rebate_rate, rebate_amount
  net_commission, adjustment_amount, final_payable
  applied_rules: list[str]

Payment:
  date, reference, amount, status (paid/pending/processing)

Agent:
  agent_id, name, team, avatar_color, is_team_leader, project
  sales: list[UnitSale], payment_history: list[Payment]
  total_commission, total_rebate, total_net, status
```

### 1.3 Current Navigation

```
Sidebar → 4 pages:
  📊 Projects          → render_projects_page()
  📝 Memorandums       → render_memorandums_page() → list / upload / review
  📚 Extracted Rules   → render_extracted_rules_page()
  💰 Agent Commissions → render_dashboard() → Breakdown / Entitlement / Teams / Analytics
```

---

## 2. Target Product Vision

### Avaland Commission Suite v2.0

A **multi-project, multi-memo commission management platform** for property developers that:

1. **Ingests** memorandum PDFs → extracts commission/rebate rules via AI
2. **Validates** extracted rules with human approval workflows
3. **Calculates** agent commissions using the multi-memo rule engine
4. **Tracks** entitlements, claims, and payment disbursements per agent
5. **Manages** agent profiles, teams, and hierarchies
6. **Reports** campaign analytics with time-period comparisons
7. **Audits** every action with full traceability for finance compliance

### Core User Personas

| Persona | Role | Key Actions |
|---------|------|-------------|
| **Ops Admin** | Upload memos, manage projects | Upload PDF, review rules, create projects, assign agents |
| **Finance Manager** | Approve payments, audit calculations | Review entitlements, approve claims, export reports, audit trail |
| **Sales Director** | Monitor team performance | View dashboards, compare campaigns, team KPIs |
| **Auditor** | Compliance verification | Trace calculation → rule → memo page, verify approvals |

---

## 3. Module Architecture

### 3.1 Target File Structure

```
Multiagent/rule-engine/multi_memo/
├── app_management.py              → REFACTOR into thin router (entry point only)
│
├── pages/                         → Page-level modules
│   ├── __init__.py
│   ├── projects.py                → Project CRUD & dashboard
│   ├── memorandums.py             → Memo upload/review/list
│   ├── extracted_rules.py         → Rule browser & validation
│   ├── agent_commissions.py       → Commission breakdown dashboard
│   ├── entitlements.py            → Entitlement & payment tracking
│   ├── agents.py                  → Agent profile & team management (NEW)
│   ├── payments.py                → Payment processing & disbursement (NEW)
│   ├── campaign_analytics.py      → Campaign comparison & analytics (NEW)
│   └── audit_log.py               → Audit trail viewer (NEW)
│
├── components/                    → Reusable UI components
│   ├── __init__.py
│   ├── styles.py                  → All CSS (extracted from inline)
│   ├── kpi_cards.py               → Metric card renderers
│   ├── data_tables.py             → Table/grid components
│   ├── filters.py                 → Common filter bars
│   └── charts.py                  → Chart wrappers
│
├── models/                        → Data models
│   ├── __init__.py
│   ├── project.py                 → Project dataclass/schema
│   ├── agent.py                   → Agent, Team dataclasses
│   ├── memo.py                    → Memo, Rule dataclasses
│   ├── sale.py                    → UnitSale, Commission dataclasses
│   ├── payment.py                 → Payment, Claim, Disbursement
│   └── audit.py                   → AuditEntry dataclass
│
├── services/                      → Business logic layer
│   ├── __init__.py
│   ├── project_service.py         → Project CRUD operations
│   ├── agent_service.py           → Agent management
│   ├── memo_service.py            → Memo pipeline (upload/OCR/extract/approve)
│   ├── commission_service.py      → Commission calculation orchestration
│   ├── payment_service.py         → Payment processing & tracking
│   ├── entitlement_service.py     → Entitlement calculation & claims
│   ├── analytics_service.py       → Aggregation & reporting queries
│   └── audit_service.py           → Audit logging
│
├── data/                          → Data access layer
│   ├── __init__.py
│   ├── json_store.py              → Current JSON file backend (Phase 1)
│   ├── db_store.py                → Database backend (Phase 2)
│   └── migrations/                → Schema migrations
│
├── auth/                          → Authentication (Phase 3)
│   ├── __init__.py
│   ├── session.py                 → Session management
│   └── roles.py                   → RBAC definitions
│
├── multi_memo_engine.py           → (existing) calculation engine
├── memo_manager.py                → (existing) memo management
├── rule_aggregator.py             → (existing) rule aggregation
└── condition_parser.py            → (existing) condition parsing
```

### 3.2 Layer Diagram

```
┌───────────────────────────────────────────────┐
│  PRESENTATION (Streamlit Pages + Components)  │
├───────────────────────────────────────────────┤
│  SERVICES (Business Logic)                    │
├───────────────────────────────────────────────┤
│  MODELS (Dataclasses / Schemas)               │
├───────────────────────────────────────────────┤
│  DATA ACCESS (JSON → DB migration path)       │
├───────────────────────────────────────────────┤
│  RULE ENGINE (existing multi-memo engine)     │
└───────────────────────────────────────────────┘
```

---

## 4. Feature Gap Analysis

### 4.1 Existing Features → Production Gap

| Feature | POC State | Production Requirement | Gap |
|---------|-----------|----------------------|-----|
| **Project Management** | Mock data, basic CRUD | Real data, project lifecycle, memo association | Replace mock generator with real data store |
| **Memo Upload** | Working 3-step wizard | Dual approval, version control, re-extraction | Add approval workflow, versioning |
| **Rule Extraction** | AI extraction + review | Confidence thresholds, cross-check, auditor mode | Add AI cross-check, audit trail |
| **Rule Validation** | Flag/unflag per rule | Bulk validation, rule diff on re-extract, conflict detection | Add diff view, conflict UI |
| **Commission Calc** | Engine integration works | Batch processing, what-if scenarios, recalculation | Add batch mode, scenario builder |
| **Entitlement Tracking** | Basic progress + history | Claim workflow, partial payments, approval chain | Full claim lifecycle |
| **Agent Management** | Data from JSON, no CRUD | Full agent profiles, team hierarchy, licensing | New module |
| **Payment Processing** | Display only | Claim→Approve→Disburse workflow, bank integration prep | New module |
| **Analytics** | Rule utilization table | Campaign comparison, time period filters, trend charts | Major expansion |
| **Audit Trail** | None | Full action logging, calculation traceability | New module |
| **Authentication** | None | Role-based access, session management | New module |

### 4.2 New Features Required

| # | Feature | Priority | Complexity |
|---|---------|----------|------------|
| F1 | **Agent Profile Management** — CRUD, team assignment, commission tier, contact info, license status | P1 | Medium |
| F2 | **Payment Claim Workflow** — Agent submits claim → Finance reviews → Manager approves → Disbursement | P1 | High |
| F3 | **Entitlement Lifecycle** — Auto-compute from rules, track claims against entitlement, balance alerts | P1 | High |
| F4 | **Dual Approval for Memos** — Preparer/Reviewer separation, approval chain, rejection with notes | P2 | Medium |
| F5 | **Campaign Analytics** — Compare campaigns (Raya vs CNY), time period filter, effectiveness scoring | P2 | Medium |
| F6 | **Conflict Resolution UI** — Visual display of overlapping rules, user picks resolution strategy | P2 | Medium |
| F7 | **Audit Trail Module** — Log every action, calculation trace, exportable audit report | P2 | Medium |
| F8 | **Batch Commission Processing** — Run engine for all agents in a project, bulk recalculation | P3 | Medium |
| F9 | **What-If Scenario Builder** — Modify rule parameters, see projected commission impact | P3 | High |
| F10 | **Agent Performance Scoring** — Rank agents by metrics, target tracking, bonus eligibility | P3 | Medium |
| F11 | **Export & Reporting Suite** — PDF reports, Excel exports, scheduled reports | P3 | Medium |
| F12 | **Authentication & RBAC** — Login, roles (Admin/Finance/Sales/Auditor), page-level access | P3 | High |
| F13 | **Database Migration** — Move from JSON to PostgreSQL/SQLite for ACID compliance | P3 | High |
| F14 | **Notification System** — Alerts for pending approvals, expiring memos, payment due | P4 | Medium |
| F15 | **API Layer** — REST API for external integrations (ERP, banking) | P4 | High |

---

## 5. Data Model Evolution

### 5.1 New/Extended Models

```python
# ── Project (extended) ──
@dataclass
class Project:
    project_id: str
    project_name: str
    developer: str                  # NEW: developer company
    location: str                   # NEW: property location
    status: str                     # Active / Completed / Upcoming
    start_date: str
    end_date: str
    target_sales: float
    description: str
    assigned_agents: list[str]      # NEW: agent_id references
    memo_ids: list[str]             # NEW: linked memo references
    created_at: str
    updated_at: str

# ── Agent (extended) ──
@dataclass
class Agent:
    agent_id: str
    name: str
    ic_number: str                  # NEW: Malaysian IC
    team: str
    team_leader_id: str | None      # NEW: hierarchy
    avatar_color: str
    is_team_leader: bool
    license_number: str             # NEW: REN/PEA number
    license_expiry: str             # NEW
    bank_name: str                  # NEW: payment details
    bank_account: str               # NEW
    contact_phone: str              # NEW
    contact_email: str              # NEW
    commission_tier: str            # NEW: Senior/Junior/Trainee
    status: str                     # Active / Inactive / Suspended
    projects: list[str]             # NEW: assigned project_ids
    created_at: str
    updated_at: str

# ── Team (new) ──
@dataclass
class Team:
    team_id: str
    team_name: str
    leader_id: str
    members: list[str]              # agent_ids
    project_id: str

# ── UnitSale (extended) ──
@dataclass
class UnitSale:
    sale_id: str                    # NEW: unique sale identifier
    unit_id: str
    project_id: str                 # NEW: link to project
    agent_id: str                   # NEW: link to agent
    block: str
    floor: str
    unit_type: str
    buyer_name: str
    buyer_ic: str
    sale_price: float
    spa_date: str
    loan_margin: float
    booking_date: str               # NEW
    spa_signed_date: str            # NEW
    status: str                     # NEW: Booked / SPA Signed / Completed / Cancelled
    # Commission breakdown
    commission_rate: float
    commission_amount: float
    rebate_rate: float
    rebate_amount: float
    net_commission: float
    adjustment_amount: float
    final_payable: float
    applied_rules: list[str]
    calculation_timestamp: str      # NEW: when engine last ran
    calculation_version: str        # NEW: engine version used
    # Audit
    created_by: str                 # NEW
    created_at: str                 # NEW
    last_modified_by: str           # NEW
    last_modified_at: str           # NEW

# ── Claim (new) ──
@dataclass
class Claim:
    claim_id: str
    agent_id: str
    project_id: str
    sale_ids: list[str]             # which sales this claim covers
    claim_amount: float
    claim_date: str
    status: str                     # Draft / Submitted / Under Review / Approved / Rejected / Paid
    submitted_by: str
    reviewed_by: str | None
    approved_by: str | None
    review_notes: str
    approval_notes: str
    payment_reference: str | None
    payment_date: str | None

# ── Disbursement (new) ──
@dataclass
class Disbursement:
    disbursement_id: str
    claim_id: str
    agent_id: str
    amount: float
    bank_name: str
    bank_account: str
    reference_number: str
    status: str                     # Processing / Completed / Failed
    processed_date: str
    completed_date: str | None

# ── AuditEntry (new) ──
@dataclass
class AuditEntry:
    entry_id: str
    timestamp: str
    user_id: str
    action: str                     # CREATE / UPDATE / DELETE / APPROVE / REJECT / CALCULATE
    entity_type: str                # Project / Memo / Rule / Sale / Claim / Payment
    entity_id: str
    changes: dict                   # before/after snapshot
    ip_address: str
    notes: str
```

### 5.2 Migration Path

```
Phase 1 (Now):     JSON files → services abstract file I/O
Phase 2 (Later):   SQLite/PostgreSQL → services call db_store.py
Phase 3 (Future):  REST API wraps services → frontend decoupled
```

The key principle: **all data access goes through service functions** so the storage backend can be swapped without touching UI code.

---

## 6. Feature Specifications

### F1: Agent Profile Management

**Page:** `📋 Agents` (new sidebar item)

| Sub-feature | Description |
|-------------|-------------|
| Agent List | Searchable/filterable table of all agents with status badges |
| Agent Profile Card | Full profile: contact, license, bank details, team, commission tier |
| Agent CRUD | Create, edit, deactivate agents via form dialogs |
| Team Management | Create/edit teams, assign leader, bulk-assign members |
| Agent-Project Linking | Assign agents to projects, view cross-project performance |
| License Monitoring | Flag agents with expiring/expired licenses |

**Data Dependencies:** Agent model, Team model, Project linkage

---

### F2: Payment Claim Workflow

**Page:** `💳 Payments` (new sidebar item)

| Sub-feature | Description |
|-------------|-------------|
| Claim Submission | Agent/admin selects sales → system generates claim with calculated amount |
| Claim Review Queue | Finance sees pending claims, can approve/reject with notes |
| Manager Approval | Two-tier approval: Finance Reviewer → Finance Manager |
| Disbursement Tracking | Track bank transfer status (Processing → Completed → Failed) |
| Payment History | Full history per agent, per project, with export |
| Payment Calendar | Visual calendar of upcoming/overdue payments |

**Workflow:**
```
Create Claim → Submit → Finance Review → Manager Approve → Process Payment → Confirm Disbursement
     ↓             ↓            ↓                ↓                ↓
   Draft       Submitted   Under Review      Approved        Processing → Completed
                    ↓            ↓                ↓
                  (edit)     Rejected          Rejected
```

---

### F3: Entitlement Lifecycle (Expansion of existing)

**Enhancement to existing Entitlement tab**

| Sub-feature | Description |
|-------------|-------------|
| Auto-Compute Entitlement | Engine calculates total entitlement from approved rules |
| Claim Against Entitlement | Link claims to entitlement, decrement balance |
| Balance Alerts | Warning when claim exceeds entitlement, alert when balance is low |
| Period Management | Monthly/quarterly entitlement periods with rollover rules |
| Entitlement Report | Exportable entitlement statement per agent |

---

### F4: Dual Approval for Memos

**Enhancement to existing Memorandums page**

| Sub-feature | Description |
|-------------|-------------|
| Preparer/Reviewer Split | Person who uploads ≠ person who approves |
| Two-Level Approval | Reviewer → Approver chain |
| Rejection with Notes | Reject with specific notes, link to flagged rules |
| Version Control | Re-upload creates new version, diff against previous |
| Approval History | Who approved what, when, with what notes |

---

### F5: Campaign Analytics

**Page:** `📈 Analytics` (expanded from current tab)

| Sub-feature | Description |
|-------------|-------------|
| Campaign Comparison | Side-by-side: Raya 2025 vs CNY 2025 effectiveness |
| Time Period Filter | Custom date range, monthly/quarterly/yearly views |
| Rule Effectiveness | Which rules drove the most sales? Utilization rate |
| Agent Performance Ranking | Top/bottom performers with trend arrows |
| Commission Distribution | Box plots, histograms of commission spread |
| Memo Impact Analysis | Before/after: how did a memo change commission patterns? |

---

### F6: Conflict Resolution UI

**Enhancement to Extracted Rules page + Entitlements**

| Sub-feature | Description |
|-------------|-------------|
| Overlap Detection | Visually flag overlapping rules across memos |
| Conflict Cards | Show conflicting rules side-by-side with resolution options |
| Resolution Strategy | Dropdown: Higher Amount / Lower Amount / Latest Memo / Manual Override |
| Double Commission Guard | Alert when same sale could earn commission from multiple rules |
| Conflict Audit | Log how each conflict was resolved |

---

### F7: Audit Trail Module

**Page:** `🔍 Audit Log` (new sidebar item)

| Sub-feature | Description |
|-------------|-------------|
| Action Log | Chronological list of all system actions |
| Entity Filter | Filter by entity type (Memo/Rule/Sale/Payment/Agent) |
| User Filter | Filter by who performed the action |
| Calculation Trace | For any sale: show calculation → rule → memo → page |
| Export | CSV/PDF export of audit log for compliance |

---

## 7. Phase Roadmap

### Phase 1: Foundation & Data Layer (Current → +4 weeks)
> Focus: Refactor for maintainability, real data, core workflows

| # | Task | Priority | Dependencies |
|---|------|----------|--------------|
| 1.1 | Extract CSS into `components/styles.py` | P1 | None |
| 1.2 | Extract page renderers into `pages/` modules | P1 | 1.1 |
| 1.3 | Create `models/` with extended dataclasses | P1 | None |
| 1.4 | Create `services/` layer abstracting JSON storage | P1 | 1.3 |
| 1.5 | Create `data/json_store.py` (formal JSON backend) | P1 | 1.3 |
| 1.6 | Replace mock project data with real project CRUD | P1 | 1.4, 1.5 |
| 1.7 | Agent Profile Management (F1) — basic CRUD | P1 | 1.4, 1.5 |
| 1.8 | Connect agent data to commission dashboard | P1 | 1.7 |

**Deliverable:** Refactored codebase with real CRUD, no more mock data generators.

---

### Phase 2: Workflows & Trust (Phase 1 + 4 weeks)
> Focus: Approval workflows, trust in extraction, payment tracking

| # | Task | Priority | Dependencies |
|---|------|----------|--------------|
| 2.1 | Dual Approval for Memos (F4) | P2 | Phase 1 |
| 2.2 | AI Cross-Check for rule extraction accuracy | P2 | existing OCR pipeline |
| 2.3 | Payment Claim Workflow (F2) — basic flow | P1 | Phase 1 |
| 2.4 | Entitlement Lifecycle (F3) — auto-compute + claims | P1 | Phase 1, 2.3 |
| 2.5 | Audit Trail Module (F7) — core logging | P2 | Phase 1 |
| 2.6 | Conflict Resolution UI (F6) — visual display | P2 | Phase 1 |

**Deliverable:** Complete memo-to-payment workflow with approval chains and audit trail.

---

### Phase 3: Analytics & Intelligence (+4 weeks)
> Focus: Analytics, batch processing, reporting

| # | Task | Priority | Dependencies |
|---|------|----------|--------------|
| 3.1 | Campaign Analytics (F5) — comparison views | P2 | Phase 2 |
| 3.2 | Batch Commission Processing (F8) | P3 | Phase 2 |
| 3.3 | Agent Performance Scoring (F10) | P3 | Phase 2 |
| 3.4 | Export & Reporting Suite (F11) — PDF/Excel | P3 | Phase 2 |
| 3.5 | What-If Scenario Builder (F9) | P3 | Phase 2 |

**Deliverable:** Full analytics suite with campaign comparison and batch processing.

---

### Phase 4: Production Hardening (+4 weeks)
> Focus: Auth, database, API, deployment

| # | Task | Priority | Dependencies |
|---|------|----------|--------------|
| 4.1 | Authentication & RBAC (F12) | P3 | Phase 3 |
| 4.2 | Database Migration (F13) — PostgreSQL/SQLite | P3 | Phase 1 services layer |
| 4.3 | Notification System (F14) | P4 | Phase 2 |
| 4.4 | API Layer (F15) — REST endpoints | P4 | Phase 3 |
| 4.5 | Production deployment (Docker, cloud hosting) | P4 | 4.1, 4.2 |

**Deliverable:** Production-deployed system with auth, database, and API.

---

## 8. Technical Debt & Refactoring

### 8.1 Immediate Refactoring Priorities

| Issue | Impact | Action |
|-------|--------|--------|
| **6484 lines in single file** | Unmaintainable | Split into pages/ + components/ + services/ |
| **~2500 lines of inline CSS** | Hard to update styles | Extract to `components/styles.py` as named constants |
| **Mock data generators** | Can't demo with real data | Replace with real CRUD backed by json_store |
| **HTML string concatenation** | XSS risk, hard to maintain | Use Streamlit native components where possible; sanitize where HTML is needed |
| **Global imports in functions** | Slow, error-prone | Move to top-level module imports |
| **`st.session_state` sprawl** | Unpredictable state | Centralize state management with clear naming conventions |
| **Duplicate render patterns** | Code duplication | Extract into reusable components |

### 8.2 Naming Conventions for session_state

```python
# Proposed convention:
st.session_state["page.{page_name}.{key}"]  # page-scoped
st.session_state["modal.{modal_name}.{key}"] # modal state
st.session_state["filter.{page}.{field}"]    # filter state
st.session_state["data.{entity}.{id}"]       # cached data
```

---

## 9. Infrastructure & Deployment

### 9.1 Deployment Architecture (Target)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Streamlit    │────→│  Services    │────→│  PostgreSQL      │
│  Frontend     │     │  Layer       │     │  (or SQLite)     │
└──────────────┘     └──────┬───────┘     └──────────────────┘
                            │
                    ┌───────┴────────┐
                    │  Rule Engine   │
                    │  (existing)    │
                    └───────┬────────┘
                            │
                    ┌───────┴────────┐
                    │  Azure OpenAI  │
                    │  (OCR + Extract)│
                    └────────────────┘
```

### 9.2 Environment Configuration

```
Phase 1: Local development (Streamlit + JSON files)
Phase 2: Docker containerization
Phase 3: Azure App Service or Azure Container Apps
Phase 4: Azure PostgreSQL Flexible Server
```

---

## 10. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| OCR extraction accuracy too low for production | Medium | High | AI cross-check, dual human review, confidence thresholds |
| Performance degrades with many agents/sales | Medium | Medium | Pagination (already exists), lazy loading, DB indexing |
| Single-file refactoring breaks existing features | Medium | High | Refactor incrementally, test each page after extraction |
| Azure API costs spike during heavy upload periods | Low | Medium | Cache OCR results, batch processing, cost monitoring |
| Streamlit limitations for complex workflows | Medium | Medium | Evaluate FastAPI + React migration for Phase 5 if needed |
| JSON file corruption with concurrent access | High | High | Move to database in Phase 4; add file locking as interim |
| Regulatory compliance requirements change | Low | High | Audit trail (F7) provides foundation for compliance |

---

## Appendix: Quick Reference — Current Functions

| Function | Purpose | Lines |
|----------|---------|-------|
| `main()` | Sidebar router, page dispatch | 6405–6484 |
| `render_projects_page()` | Project dashboard with mock data | 5618–5898 |
| `render_memorandums_page()` | Router for memo sub-views | 5191–5248 |
| `render_memo_list()` | Memo inbox table | 5020–5191 |
| `render_memo_upload()` | 3-step upload wizard | 4771–4942 |
| `render_memo_review()` | Side-by-side memo review | 4942–5020 |
| `render_extracted_rules_page()` | Rule browser + validation | 6275–6402 |
| `_render_rule_card()` | Single rule card with actions | 6041–6275 |
| `render_dashboard()` | Commission dashboard (4 tabs) | 5248–5618 |
| `render_filter_bar()` | Project/scheme/period filters | 2600–2630 |
| `render_summary_metrics()` | 4 KPI cards | 2630–2660 |
| `render_team_overview()` | Team cards + leaderboard | 2660–2841 |
| `render_agent_row()` | Agent summary row | 2841–2892 |
| `render_agent_breakdown()` | Per-unit commission detail | 2892–3068 |
| `render_agent_unit_details()` | Summary table view | 3068–3126 |
| `render_performance_charts()` | Analytics charts | 3126–3327 |
| `render_memo_library()` | Browse loaded memos | 3327–3746 |
| `render_entitlement_metrics()` | Entitlement KPI cards | 3746–3813 |
| `render_entitlement_agent_row()` | Agent entitlement row | 3813–3886 |
| `render_entitlement_detail()` | Payment history + summary | 3886–4165 |
| `_aggregate_all_rules()` | Flatten all memo rules | 5898–6041 |
| `_validate_rule()` | Run validation checks | 6041–6100 (approx) |

---

