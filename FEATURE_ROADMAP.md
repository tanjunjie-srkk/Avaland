# Avaland Commission Suite — Feature Roadmap

> **Last Updated:** 5 March 2026  
> **Author:** Tan Jun Jie  
> **Prioritization Basis:** Customer demo feedback + technical dependency analysis  

---

## Prioritization Rationale

This roadmap is sequenced based on two inputs:

1. **Customer demo feedback** — Three themes emerged:
   - **(A) Campaign Effectiveness Analytics** — Compare campaigns (Raya vs CNY), time-period filters
   - **(B) Rule Extraction Trust & Approval Workflow** — Readable rules, dual approval, auditor support, AI cross-check, final-only PDF
   - **(C) Overlapping Campaigns & Conflict Handling** — Nested entitlement detection, double commission prevention, conflict resolution prompts

2. **Technical dependency chain** — OCR accuracy feeds everything downstream; if extraction is wrong, nothing else matters.

**Customer-confirmed scope reduction:** Only typed Word→PDF documents (no handwriting), tables are acceptable, language clarity is important. This narrows the OCR challenge significantly.

---

## Priority Legend

| Tag | Meaning |
|-----|---------|
| 🔴 P1 | **Must-have** — System doesn't function without this |
| 🟠 P2 | **Should-have** — Customer won't trust/use it without this |
| 🟡 P3 | **Important** — Core business logic correctness |
| 🔵 P4 | **Valuable** — Dashboards and analytics that demonstrate ROI |
| ⚪ P5 | **Future** — Production hardening and scaling |

---

## Priority 1 — Foundation 🔴

> *"If extraction is wrong, nothing else matters."*  
> Everything in the system depends on accurate rule extraction from memorandum PDFs.

| # | Feature | Description | Current State | What To Do | Affected Files |
|---|---------|-------------|---------------|------------|----------------|
| **1.1** | **OCR extraction improvements** | Improve text + table OCR accuracy for typed Malaysian property memos | ✅ Working pipeline (`ocr.py`, `ocrtable.py`) using Azure OpenAI Vision | Tune prompts for Malaysian property terms. Add post-processing validation (e.g. percentage sanity checks, RM amount format normalization). Test with 10+ real memos to benchmark accuracy. | `Multiagent/ocr/ocr.py`, `Multiagent/ocr/ocrtable.py` |
| **1.2** | **Rule extraction accuracy** | LLM prompt tuning for structured rule JSON output | ✅ Working (`rule.py`) with detailed system prompt | Refine system prompt for edge cases: tiered conditions, conditional rebates, multi-criteria rules. Add few-shot examples from real memos. Test extraction_confidence thresholds. | `Multiagent/rule-extract/rule.py` |
| **1.3** | **Human-readable rule display** | Show extracted rules in layman terms so non-technical users can verify | ⚠️ Rules shown as raw conditions + values in tables | Add a "plain English" summary generator per rule. Example: `IF buyer_type == "bumi"` → "Bumiputera buyers receive 5% rebate on net price". Display alongside technical view. | `app_management.py` → `render_extracted_rules_page()`, `_render_rule_card()`, `_render_memo_rules_panel()` |
| **1.4** | **AI cross-checking** | Use a second AI pass to verify extraction matches the source document | ❌ Not implemented | After extraction, send both the original OCR text AND the extracted rules JSON to a verification prompt. Flag discrepancies (e.g. "extracted 3% but source says 3.5%"). Show confidence delta. | New: `Multiagent/rule-extract/rule_verifier.py` |

### P1 Acceptance Criteria
- [ ] OCR accurately extracts text + tables from 10 real memos with <5% character error rate
- [ ] Rule extraction produces valid JSON with correct percentages/amounts for all 10 test memos
- [ ] Every rule displays a plain-English summary alongside the technical condition
- [ ] AI cross-check catches deliberately introduced errors in test data (≥80% detection rate)

---

## Priority 2 — Trust Workflow 🟠

> *"One upload, one review, one approve — then it's trusted."*  
> The customer explicitly stated they won't use the system until they can verify what was extracted.

| # | Feature | Description | Current State | What To Do | Affected Files |
|---|---------|-------------|---------------|------------|----------------|
| **2.1** | **Upload → Review → Approve workflow** | End-to-end memo ingestion: PDF upload → OCR → extraction → human review → approval | ✅ 3-step wizard exists (`render_memo_upload()`) with approve/reject | Tighten the flow: prevent approved memos from being used in calculations until review is complete. Add "Review Required" status. Connect to rule engine's memo filtering. | `app_management.py` → `render_memo_upload()`, `_save_new_memo()`, `memo_store.json` |
| **2.2** | **Version control / final-only upload** | Only approved final PDFs enter the system; re-uploads create new versions, not overwrites | ⚠️ Each upload creates a new MEMO_xxx entry but no explicit versioning | Add `version` field to memo_store entries. Add `parent_memo_id` for re-extractions. Add "Final Document" checkbox on upload form. Show version history in memo detail view. | `app_management.py` → `render_memo_upload()`, `_save_new_memo()`, `memo_store.json` schema |
| **2.3** | **Dual approval** | Sales admin uploads + reviews, finance manager must also approve before rules go live | ⚠️ Single approve/reject button exists | Add `reviewed_by`, `approved_by`, `review_date`, `approval_date` fields. Add two-stage status flow: `pending` → `reviewed` → `approved`. Show approval chain in memo detail. | `app_management.py` → `render_memo_review()`, `render_memo_list()`, `_save_new_memo()` |
| **2.4** | **Auditor walkthrough** | Side-by-side view: original PDF page vs extracted rules, with line-by-line verification | ✅ Side-by-side view exists in `render_memo_review()` | Enhance: highlight which PDF region maps to which rule. Add per-rule "Verified" checkbox. Show rule source page number. Allow auditor to annotate discrepancies. | `app_management.py` → `render_memo_review()`, `_render_memo_rules_panel()` |

### P2 Acceptance Criteria
- [ ] Memos go through `pending` → `reviewed` → `approved` status transitions
- [ ] Only `approved` memos are loaded by the rule engine for calculations
- [ ] Re-uploaded memos create new versions linked to the original
- [ ] Auditor can verify each rule against its source page with ✅/❌ per rule
- [ ] If the rules are flag, users are allowed to edit the rules and the changes will be tracked and stored in a database
- [ ] Two different users must sign off (uploader ≠ approver enforced)

---

## Priority 3 — Calculation Engine + Conflict Handling 🟡

> *"What happens when Raya promotion overlaps with CNY promotion?"*  
> The engine already handles conflicts — but it needs bulletproof edge-case handling and user-facing controls.

| # | Feature | Description | Current State | What To Do | Affected Files |
|---|---------|-------------|---------------|------------|----------------|
| **3.1** | **Calculation engine refinement** | Fix edge cases in multi-memo calculation based on real extracted rules | ✅ `MultiMemoRuleEngine` works with test data | Run all 10 real memos through the engine. Identify mismatches against manual calculations. Fix condition parsing edge cases. Verify sequential rebate logic (Bumi first, then others). | `multi_memo_engine.py`, `condition_parser.py`, `rule_engine.py` |
| **3.2** | **Nested entitlement detection** | Alert when a single sale qualifies under multiple campaign memos simultaneously | ⚠️ `rule_aggregator.py` detects OVERLAPPING_CONDITIONS conflicts | Surface these overlaps in the UI. Show which campaigns a sale qualifies for. Allow user to toggle which campaign applies. Log the selection. | `rule_aggregator.py`, `app_management.py` → `render_agent_breakdown()` |
| **3.3** | **Double commission prevention** | Hard block — system must NOT pay commission twice for the same sale under overlapping memos | ⚠️ Conflict resolution exists but no hard block at payment level | Add `claimed_under_memo` field to UnitSale. At calculation time, check if sale already has a commission claim. Block duplicate claims with clear error message. | `multi_memo_engine.py`, `app_management.py` → `render_entitlement_detail()` |
| **3.4** | **Conflict resolution UI** | When overlap is detected, user picks which memo/rule applies via a visual interface | ⚠️ Conflict detection exists in engine; `app_multi_memo.py` shows conflict cards | Port conflict visualization to `app_management.py`. Add resolution dropdown (Higher Amount / Latest Memo / Manual Override). Persist resolution choice. | `app_management.py` → new section in `render_dashboard()` or new page |
| **3.5** | **Full audit trail** | Every calculation traceable: sale → applied rules → source memo → PDF page | ⚠️ `applied_rules` list exists on UnitSale; engine returns `MultiMemoPricingResult` with traceability | Store full calculation trace in JSON per sale. Add "Audit" button per agent/sale that shows the complete chain. Export audit report. | `app_management.py` → `render_agent_breakdown()`, new `services/audit_service.py` |

### P3 Acceptance Criteria
- [ ] Engine produces correct results for all 10 real memos (verified against manual calc spreadsheet)
- [ ] Overlapping campaigns are visually flagged with resolution options
- [ ] System blocks duplicate commission payment for the same sale
- [ ] Any calculation can be traced back: amount → rule → memo → original PDF page
- [ ] Audit report exportable as CSV/PDF

---

## Priority 4 — Analytics & Dashboards 🔵

> *"Can we compare how effective Raya campaign was versus CNY?"*  
> Real data flowing through the engine unlocks meaningful analytics.

| # | Feature | Description | Current State | What To Do | Affected Files |
|---|---------|-------------|---------------|------------|----------------|
| **4.1** | **Management dashboard → real data** | Replace mock data with actual sales flowing through the engine | ⚠️ `management_mock_data.json` with mock agents | Connect dashboard to `json_store` / real project data. Load agents from agent profiles, sales from calculation results. Remove `_generate_mock_projects()`. | `app_management.py` → `load_demo_data()`, `render_projects_page()` |
| **4.2** | **Campaign performance dashboard** | Sales performance grouped by campaign/memo, with KPIs per campaign | ⚠️ Basic analytics tab with rule utilization table | Add campaign-level aggregation: total sales, total commission, agent count, avg rate per memo/campaign. New tab or page. | `app_management.py` → `render_performance_charts()`, or new `pages/campaign_analytics.py` |
| **4.3** | **Time period filter** | Filter all views by campaign effective dates, custom date ranges | ⚠️ Period filter exists in `render_filter_bar()` but limited | Extend filter to support custom date range picker. Apply to all pages consistently. Filter by memo effective_period. | `app_management.py` → `render_filter_bar()`, all render functions |
| **4.4** | **Campaign comparison** | Side-by-side comparison: Raya 2025 vs CNY 2025, year-over-year analytics | ❌ Not implemented | New comparison view: select two campaigns, show metrics side-by-side (sales volume, commission paid, agents involved, conversion rate). Bar/line charts for visual comparison. | New: `pages/campaign_analytics.py` |

### P4 Acceptance Criteria
- [ ] Dashboard displays real sales data from approved memos + engine calculations
- [ ] User can view sales performance per campaign with totals and averages
- [ ] Date range filter works across all pages
- [ ] Two campaigns can be compared side-by-side with visual charts

---

## Priority 5 — Production & Hardening ⚪

> Future-proofing for scale, security, and integration.

| # | Feature | Description | Current State | What To Do | Affected Files |
|---|---------|-------------|---------------|------------|----------------|
| **5.1** | **Authentication & access control** | Login system with role-based access (Admin, Finance, Sales, Auditor) | ❌ None | Implement Streamlit-compatible auth (streamlit-authenticator or custom). Define roles and page-level permissions. Tie into dual approval (P2.3). | New: `auth/session.py`, `auth/roles.py` |
| **5.2** | **Database backend** | Replace JSON files with PostgreSQL/SQLite for ACID compliance and concurrent access | ❌ File-based JSON | Abstract data access through `services/` layer (from production plan). Implement `data/db_store.py`. Migrate memo_store, agent data, sales, audit log. | New: `data/db_store.py`, `data/migrations/` |
| **5.3** | **API layer (FastAPI)** | REST API for external integrations (ERP, banking, reporting tools) | ❌ None | Wrap `services/` layer with FastAPI endpoints. Authenticate via API keys. Document with OpenAPI/Swagger. | New: `api/` directory |
| **5.4** | **Production deployment** | Containerization and cloud hosting | ❌ Local Streamlit only | Dockerfile, docker-compose. Azure App Service or Azure Container Apps deployment. CI/CD with GitHub Actions. | New: `Dockerfile`, `docker-compose.yml`, `.github/workflows/` |

### P5 Acceptance Criteria
- [ ] Users must log in; each role sees only permitted pages
- [ ] All data persisted in a proper database with transactions
- [ ] External systems can call API endpoints to query commission data
- [ ] Application deployable via single `docker-compose up` command

---

## Cross-Cutting: Technical Refactoring

These tasks run **in parallel** with feature work and are prerequisites for maintainability:

| # | Task | When | Rationale |
|---|------|------|-----------|
| **R1** | Extract ~2500 lines of CSS → `components/styles.py` | Start of P1 | Unblock parallel work on pages |
| **R2** | Split page renderers into `pages/` modules | During P1–P2 | 6484 lines in one file is unmaintainable |
| **R3** | Create `models/` with extended dataclasses | Start of P1 | Clean data contracts for services |
| **R4** | Create `services/` layer abstracting JSON storage | Start of P1 | Enables P5.2 database migration later |
| **R5** | Create `data/json_store.py` (formal JSON backend) | Start of P1 | Single place for all file I/O |
| **R6** | Centralize `st.session_state` naming | During P2 | Prevent state collision bugs |
| **R7** | Sanitize HTML string concatenation | During P2 | XSS prevention for production |

---

## Dependency Graph

```
P1.1 OCR improvements
 │
 ├──→ P1.2 Rule extraction accuracy
 │     │
 │     ├──→ P1.3 Human-readable display
 │     │
 │     └──→ P1.4 AI cross-checking
 │
 └──→ P2.1 Upload → Review → Approve workflow
       │
       ├──→ P2.2 Version control
       │
       ├──→ P2.3 Dual approval ──────────────→ P5.1 Authentication
       │
       └──→ P2.4 Auditor walkthrough
             │
             └──→ P3.5 Full audit trail ─────→ P5.2 Database backend
                   │
P3.1 Engine refinement                        P5.3 API layer
 │                                              │
 ├──→ P3.2 Nested entitlement detection        P5.4 Deployment
 │
 ├──→ P3.3 Double commission prevention
 │
 └──→ P3.4 Conflict resolution UI
       │
       └──→ P4.1 Dashboard → real data
             │
             ├──→ P4.2 Campaign performance
             │
             ├──→ P4.3 Time period filter
             │
             └──→ P4.4 Campaign comparison
```

---

## Customer Feedback Traceability

Mapping customer feedback themes to roadmap items:

| Customer Theme | Feedback Item | Roadmap Item(s) |
|---------------|---------------|-----------------|
| **(A) Campaign Analytics** | "Compare Raya vs CNY effectiveness" | P4.2, P4.4 |
| **(A) Campaign Analytics** | "Filter by time period" | P4.3 |
| **(A) Campaign Analytics** | "Show campaign performance" | P4.2 |
| **(B) Trust & Approval** | "Rules must be readable by laypeople" | P1.3 |
| **(B) Trust & Approval** | "Upload → review → approve flow" | P2.1 |
| **(B) Trust & Approval** | "Dual sign-off (sales + finance)" | P2.3 |
| **(B) Trust & Approval** | "Auditor should verify line-by-line" | P2.4 |
| **(B) Trust & Approval** | "AI should cross-check extraction" | P1.4 |
| **(B) Trust & Approval** | "Only final PDFs enter the system" | P2.2 |
| **(C) Conflict Handling** | "What if campaigns overlap?" | P3.2, P3.4 |
| **(C) Conflict Handling** | "Don't pay commission twice" | P3.3 |
| **(C) Conflict Handling** | "Full audit trail for compliance" | P3.5 |
| **Budget** | "Optimize Azure API costs" | P1.1 (reduce re-processing), P2.2 (extract once for final docs only) |

---

## Budget Mitigation Notes

Customer raised concern about Azure API costs. Mitigation strategies built into the roadmap:

1. **P1.1** — Better OCR accuracy means fewer re-processing cycles
2. **P2.2** — "Final document only" policy prevents extracting draft versions that will change
3. **P1.4** — AI cross-check adds one extra API call but prevents costly manual re-work
4. **Caching** — Store OCR results and extracted rules; only re-extract when memo is re-uploaded
5. **Batch optimization** — Process all pages in a single API call where possible (already implemented in `_run_ocr_text`)

---

## Success Metrics

| Phase | Metric | Target |
|-------|--------|--------|
| P1 Complete | Rule extraction accuracy (vs manual) | ≥95% |
| P1 Complete | AI cross-check detection rate | ≥80% |
| P2 Complete | Memo approval turnaround time | <1 business day |
| P3 Complete | Calculation accuracy (vs spreadsheet) | 100% match |
| P3 Complete | Duplicate commission incidents | 0 |
| P4 Complete | Dashboard loads real data | Yes |
| P5 Complete | Concurrent users supported | ≥10 |

---
## Customer Feedback for First Demo
    2. Sale commission Apps
        a. Effectiveness of the campaign  - to see the sales performance 
            i. Same festive, see the campaign of the effectiveness , what to know how can be the campaign affected by the time period
            ii. Time period filter to view the sales, they want to know when is the compaign effective period
            iii. Like Raya vs Chines new year, And RAYA vs RAYA
        b. The rules need to be reading in nice way , the description that can be read, Approve the upload, by comparing the validation of the pdf, 
            i. Need to understand what is the extraction
                1) One time upload, one time review, one time approve then all the data is trusted and can be ready to used 
                2) Must be a readable format for the verification, ask the formula to be describe in layman term
                3) 2 people to verify the validation of the rules, sales admin n finance 
                4) Auditor will walk through as well 
                5) Table okay, the language need to be careful to ensure the ambuiguity is less 
                6) Use AI to do cross checking to make sure the language is clear 
                7) They use word to convert pdf -> No handwritting allow, use pdf write - Hand writing will not change the proposal 
                8) They have different version of pdf, so only upload when approve the last final 
            ii. Budget concern 
            iii. Overlapping campaign date, if there are several campaign that overlapp and the effective ness 
                1) Allow to trace the full audit
                2) Double entries in the same festives, ( Nested entitlement )  1-3 and chinese new year -> which one you use-> Alert the similarities and both are still valid memo-> Double memo, don’t offer both commission 
                3)  Handle conflict -> ask to choose which one you should choose 
The scenario is different to the memo,

*This roadmap is a living document. Review and adjust priorities after each phase completion.*
