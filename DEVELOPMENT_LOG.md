# Avaland Project — Development Log

> **Last Updated**: 5 March 2026  
> **Author**: Tan Jun Jie  
> **Purpose**: Comprehensive development log to capture project state, decisions, and progress before context switch to another project.

---

## 1. Project Overview

**Avaland** is a multi-memo rule engine system for calculating property sales commissions, rebates, and pricing adjustments in Malaysian real estate. It is built for the **Aetas Seputeh** residential project under the Avalux brand.

**Core Problem Solved**: Automate the extraction of business rules from PDF sales memos and apply them transparently to calculate agent commissions, buyer rebates, and price adjustments — with full auditability back to source documents.

---

## 2. Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.x |
| Web UI | Streamlit |
| LLM Integration | Azure OpenAI (GPT) |
| Document Parsing | Azure Document Intelligence (prebuilt layout) |
| OCR | Azure OpenAI Vision API |
| PDF Processing | PyMuPDF (fitz) |
| Config Management | python-dotenv + Streamlit secrets |
| Storage | Azure Blob Storage (SAS-authenticated PDF access) |

**Key Dependencies** (from `requirements.txt`):
- `streamlit`, `openai`, `python-dotenv`, `PyMuPDF`

---

## 3. Architecture Summary

The system follows a **pipeline architecture** with 4 layers:

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCUMENT EXTRACTION LAYER                     │
│  PDF → Azure Doc Intelligence / PyMuPDF → OCR (Vision API)      │
│  Output: Structured JSON (text + tables)                         │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     RULE EXTRACTION LAYER                        │
│  OCR JSON → Azure OpenAI Agent → Structured Rule JSON            │
│  Output: /artifact/*.json                                        │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       RULE ENGINE LAYER                          │
│  ┌───────────────┐    ┌──────────────────────────────────────┐  │
│  │  Single-Memo   │    │  Multi-Memo (Primary)                │  │
│  │  rule_engine.py│    │  memo_manager → rule_aggregator →    │  │
│  │  rule_loader   │    │  condition_parser → engine            │  │
│  │  rule_matcher  │    │  + conflict detection & resolution   │  │
│  └───────────────┘    └──────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      STREAMLIT UI LAYER                          │
│  app.py (single-memo) │ app_multi_memo.py │ app_management.py   │
│  Finance dashboard     │ Conflict viewer   │ Agent commission    │
│                        │                   │ tracking & payment  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Key Modules — What Each Does

### 4.1 Document Extraction (`docintelligence/`, `Multiagent/ocr/`)

| File | Purpose |
|------|---------|
| `docintelligence/doc_intelligent.py` | Calls Azure Document Intelligence to extract text + tables from PDFs. Outputs raw JSON. |
| `Multiagent/ocr/pdf_to_images.py` | Converts PDF pages to 300 DPI PNG images using PyMuPDF for high-quality OCR. |
| `Multiagent/ocr/ocr.py` | Sends page images to Azure OpenAI Vision API for faithful text transcription (strict non-inferential prompt). |
| `Multiagent/ocr/ocrtable.py` | Specialized OCR for table detection and structure preservation via Vision API. |

**Important design decision**: OCR prompts are deliberately strict — "transcribe exactly, do not interpret" — to avoid hallucinated data in financial documents.

### 4.2 Rule Extraction (`Multiagent/rule-extract/`)

| File | Purpose |
|------|---------|
| `rule.py` | LLM-based extraction agent. Takes OCR output, uses a detailed system prompt to produce structured rule JSON (commissions, rebates, referrals, price adjustments, packages). |

**Output schema** includes: `memo_reference`, `effective_period`, `project_name`, `rules` (by type), `extraction_confidence`, `pseudo_code`.

### 4.3 Configuration (`Multiagent/config.py`)

Centralized secrets manager with 3-tier resolution:
1. Streamlit Cloud secrets (`st.secrets`)
2. Environment variables (`.env`)
3. Hardcoded fallback (empty)

Provides: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` (default: `gpt-5.2-chat`), `AZURE_OPENAI_API_VERSION` (default: `2024-12-01-preview`), plus parallel `AGENT_*` variants.

### 4.4 Agent Framework (`Multiagent/agent.py`)

Thin wrapper using `agent_framework.azure.AzureOpenAIChatClient` — a test/POC agent for Azure OpenAI chat completions. Currently used for testing connectivity.

### 4.5 Single-Memo Rule Engine (`Multiagent/rule-engine/single_memo/`)

| File | Purpose |
|------|---------|
| `rule_loader.py` | `Rule` dataclass + `RuleLibrary` + `RuleLoader` — parse extracted JSON into indexed rule collections. Methods: `add_rule()`, `get_by_type()`, `get_by_buyer_type()`, `search()`. |
| `rule_matcher.py` | `MatchedRule` dataclass + `RuleMatcher` — evaluate conditions against buyer context, return matched rules with confidence scores. Methods: `match()`, `match_single()`, `match_all_applicable()`. |
| `rule_engine.py` | `RuleEngine` — orchestrate load → match → calculate. Output: `PricingResult` with `base_price`, `final_price`, line-item breakdowns. |
| `app.py` | Streamlit dashboard — finance transparency view with step-by-step calculation audit trail. |
| `test_engine.py` | Test suite for condition parsing, rule loading, matching, and full calculation scenarios. |

### 4.6 Multi-Memo Rule Engine (`Multiagent/rule-engine/multi_memo/`) — PRIMARY SYSTEM

| File | Purpose |
|------|---------|
| `memo_manager.py` | `MemoType` enum (STANDARD, SUPERSEDING, ADDENDUM, AMENDMENT), `MemoMetadata`, `EnhancedRule` (with composite ID `{memo_ref}::{rule_id}`), `Memo`. Loads all memos from `/artifact`, filters by date/project. |
| `rule_aggregator.py` | `RuleAggregator` + `PriorityRanker` — merge rules from multiple memos, detect conflicts (SAME_RULE_ID, OVERLAPPING_CONDITIONS, CONTRADICTORY, SUPERSEDED), resolve by strategy (LATEST_WINS, HIGHEST_PRIORITY, MOST_SPECIFIC, MERGE, MANUAL_REVIEW). Output: `AggregatedRuleLibrary`. |
| `condition_parser.py` | AST-based parser for rule condition strings. Syntax: `IF <field> <op> <value> [AND/OR ...]`. Supports `==`, `!=`, `>=`, `<=`, `>`, `<`. Safe — no `eval()`. Caches compiled functions. |
| `rule_engine.py` | Core calculation logic for matched rules (same as single-memo but enhanced). |
| `multi_memo_engine.py` | `MultiMemoRuleEngine` — top-level orchestrator. Flow: `load_memos()` → `retrieve_and_prepare(project, date)` → `get_applicable_rules(context)` → `calculate(context)`. Output: `MultiMemoPricingResult` with full traceability. |
| `rule_aggregator.py` | Also contains `PriorityRanker` with weighted scoring: Recency 40% + Specificity 30% + Explicit Priority 20% + Memo Hierarchy 10%. |
| `app_multi_memo.py` | Streamlit UI — shows memo source badges, conflict cards, priority rankings, filtering stats. |
| `app_management.py` | Streamlit management dashboard — agent portfolios, commission summaries, per-sale breakdowns, payment history, CSV/Excel export, manual sale entry with engine validation. |
| `test_multi_memo.py` | Tests memo loading, date/project filtering, aggregation, conflict detection, priority ranking. |
| `test_conflict_resolution.py` | Tests conflict handling — engine init, memo filtering, calculation with supersession. |

---

## 5. How Calculation Works

```
BASE PRICE (list price of the unit)
    │
    ▼
+ PRICE ADJUSTMENTS (floor premium, car park premium, block adjustment)
    │
    ▼
= NET PRICE
    │
    ▼
- BUMI REBATE (5% if buyer_is_bumi == True, calculated on Net Price)
    │
    ▼
= NET PRICE AFTER BUMI
    │
    ▼
- STANDARD REBATE (calculated on "Net Price after Bumi Rebate")
- SPECIAL REBATE (calculated on "Net Price after Bumi Rebate")
- ADDITIONAL REBATE (calculated on "Net Price after Bumi Rebate")
    │
    ▼
= FINAL PRICE (Net Selling Price)
    │
    ▼
COMMISSION (calculated separately on Net Selling Price, not deducted)
```

**Key design decision**: Rebate `calculation_base` field determines whether a rebate is applied on "Net Price" or "Net Price after Bumi Rebate" — this sequential dependency is critical for accuracy.

---

## 6. Rule Types & JSON Schema

### 6.1 Commission Rules (`COM_*`)
```json
{
  "rule_id": "COM_002",
  "rule_name": "Local Buyer Commission – Block B by Floor Tier",
  "rule_type": "commission",
  "buyer_type": "local",
  "conditions": [
    {
      "condition": "IF block == 'B' AND floor_level >= 20 AND floor_level <= 29",
      "commission_percentage": 5.0,
      "description": "Mid floors Block B (Level 20–29)"
    }
  ]
}
```

### 6.2 Rebate Rules (`REB_*`)
```json
{
  "rule_id": "REB_001",
  "rule_name": "Bumi Rebate",
  "rule_type": "rebate",
  "rebate_type": "bumi",
  "calculation_base": "Net Price",
  "conditions": [
    {
      "condition": "IF buyer_is_bumi == True",
      "rebate_percentage": 5.0
    }
  ]
}
```

### 6.3 Referral Rules (`REF_*`)
- Referrer categories: `guest`, `business_associate`, `staff`, `bgb`
- Reward types: `fixed` amount or `percentage`

### 6.4 Price Adjustment Rules (`PRC_*`)
- Types: `floor_premium`, `car_park_premium`, `block_adjustment`
- Fixed amounts applied to base price

### 6.5 Package Rules (`PKG_*`)
- Package types: `partially_furnished`, `foreign_package`
- Eligibility based on buyer conditions

---

## 7. Multi-Memo Conflict Resolution

### Priority Scoring (Weighted)
```
Total = (Recency × 0.4) + (Specificity × 0.3) + (Explicit × 0.2) + (Hierarchy × 0.1)
```

| Factor | Weight | Range | Description |
|--------|--------|-------|-------------|
| Recency | 40% | 0.0–1.0 | Newer memos score higher |
| Specificity | 30% | 0.0–1.0 | More conditions = more specific |
| Explicit Priority | 20% | 0–10 | Manual override from memo metadata |
| Memo Hierarchy | 10% | — | SUPERSEDING > AMENDMENT > ADDENDUM > STANDARD |

### Conflict Types
- `SAME_RULE_ID` — Same rule ID across different memos
- `OVERLAPPING_CONDITIONS` — Different rules with same conditions
- `CONTRADICTORY` — Conflicting outcomes
- `SUPERSEDED` — Explicitly superseded by newer memo

### Resolution Strategies
- `LATEST_WINS` — Most recent memo takes precedence
- `HIGHEST_PRIORITY` — Highest priority score wins
- `MOST_SPECIFIC` — Rule with more conditions wins
- `MERGE` — Combine rule outcomes
- `MANUAL_REVIEW` — Flag for human decision

---

## 8. Streamlit UIs

### 8.1 Single-Memo Calculator (`single_memo/app.py`)
- Buyer input form (base price, buyer type, block, floor, unit type, Bumi status)
- Step-by-step calculation breakdown
- Rule library sidebar with color-coded cards
- Financial dashboard styling

### 8.2 Multi-Memo Calculator (`multi_memo/app_multi_memo.py`)
- Everything from single-memo PLUS:
- Memo source badges on each rule
- Conflict visualization (winner/loser highlighting)
- Priority ranking display
- Filtering statistics (memos at each pipeline stage)

### 8.3 Management Dashboard (`multi_memo/app_management.py`)
- Agent portfolio viewer (name, team, sales count)
- Per-agent commission summaries
- Individual sale breakdown (unit, buyer, sale price, commission, rebate)
- Payment history and status tracking
- Live engine calculation from dashboard
- CSV/Excel export
- Manual sale entry with rule engine validation
- Uses mock data from `demo_data/management_mock_data.json`

---

## 9. Data Files

| File | Description |
|------|-------------|
| `Multiagent/artifact/extracted-rules.json` | Main extracted rules — Aetas Seputeh memo AVALUX-AD-MEMO-SM-2025-009 (effective 15 Jun – 31 Dec 2025). 4 commission, 4 rebate, 4 referral, 2 price adjustment, 2 package rules. |
| `Multiagent/artifact/extracted-rules-memo_004.json` | Additional extracted rules from memo 004. |
| `Multiagent/artifact/mockedrules.json` | Mock rules — Project Alpha (MOCK-MEMO-TEST-001), effective Jan–Dec 2026. For POC testing. |
| `Multiagent/artifact/mockedrules2.json` | Additional mock rules for testing. |
| `Multiagent/artifact/superseding-rules.json` | Supersession test data — newer memo overriding older rules. |
| `Multiagent/rule-engine/multi_memo/memo_store.json` | Memo processing metadata — upload dates, status (approved/pending/rejected), source PDF, extraction confidence, reviewer notes, rule counts. |
| `Multiagent/rule-engine/multi_memo/demo_data/management_mock_data.json` | Mock agent sales data — agents (Ahmad Razak, Nur Azlina, etc.), their sales portfolios, commission breakdowns, payment history. |
| `Multiagent/Data/output.json` | Raw Document Intelligence output. |
| `Multiagent/Data/output-table.json` | Extracted table data. |
| `Multiagent/Data/output-text.json` | Extracted text data. |
| `docintelligence/output.json` | Azure Doc Intelligence raw output. |
| `docintelligence/sampleoutput.json` | Sample output for reference. |

---

## 10. Existing Documentation (in `docs/`)

| File | Contents |
|------|----------|
| `README.md` | Project overview, quick start, documentation index |
| `ARCHITECTURE.md` | System design, module dependencies, data flow diagrams |
| `MULTI_MEMO.md` | Memo types, filtering logic, conflict resolution details |
| `CONDITION_SYNTAX.md` | Rule condition syntax reference (IF/AND/OR, operators) |
| `RULE_CALCULATION.md` | Calculation order, formulas, worked examples (CRITICAL reference) |
| `DATA_SCHEMAS.md` | JSON schema definitions for memos and rules |
| `API_REFERENCE.md` | Complete API docs for all public classes and methods |
| `EXAMPLES.md` | Usage examples |
| `CHEAT_SHEET.md` | Quick reference for common operations |

---

## 11. Test Coverage

| Test File | What It Tests |
|-----------|---------------|
| `single_memo/test_engine.py` | Condition parsing (AND/OR logic), rule loading from JSON, rule matching with various buyer contexts, full end-to-end calculation. |
| `multi_memo/test_multi_memo.py` | Memo loading from artifacts, date filtering, project filtering with fuzzy match, rule aggregation, conflict detection, priority ranking. |
| `multi_memo/test_conflict_resolution.py` | Conflict handling demo — engine init, memo filtering, calculation with supersession, commission breakdown with memo references. |

---

## 12. Development Status

### Completed
- [x] Azure Document Intelligence integration for PDF parsing
- [x] OCR pipeline (text + table) via Azure OpenAI Vision API
- [x] PDF to image conversion (300 DPI)
- [x] LLM-based rule extraction agent with structured JSON output
- [x] Single-memo rule engine (load → match → calculate)
- [x] Multi-memo support (memo manager, loading, date/project filtering)
- [x] Rule aggregation across multiple memos
- [x] Conflict detection (same ID, overlapping conditions, supersession)
- [x] Conflict resolution strategies (latest wins, highest priority, most specific, merge, manual)
- [x] Priority ranking system (recency 40%, specificity 30%, explicit 20%, hierarchy 10%)
- [x] AST-based condition parser (safe, no eval)
- [x] Streamlit single-memo calculator UI
- [x] Streamlit multi-memo calculator UI with conflict visualization
- [x] Management dashboard (agent tracking, payment history, export)
- [x] Memo store (processing metadata tracking)
- [x] Comprehensive documentation (8 doc files)
- [x] Test suites for all engines
- [x] Mock data for testing and demos

### In Progress / Partially Done
- [ ] Rule extraction accuracy refinement (LLM prompt tuning)
- [ ] OCR table extraction improvements
- [ ] Management dashboard uses mock data — needs real data integration
- [ ] `agent.py` is a test stub — full agent framework integration pending

### Not Yet Started / Future
- [ ] Authentication / user access control in Streamlit UIs
- [ ] Database backend (currently file-based JSON)
- [ ] API layer (REST/FastAPI) for headless integration
- [ ] Bulk calculation / batch processing
- [ ] Memo upload workflow through UI (end-to-end PDF → rules → engine)
- [ ] Audit logging / change history
- [ ] Unit test expansion (more edge cases, boundary conditions)
- [ ] Production deployment (containerization, CI/CD)

---

## 13. Key Design Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| **AST-based condition parsing** (no `eval`) | Security — financial system cannot risk code injection |
| **Composite rule IDs** (`memo_ref::rule_id`) | Uniqueness across memos — same rule_id in different memos must be distinguishable |
| **Weighted priority scoring** | Flexible conflict resolution — recency alone isn't sufficient, specificity and explicit overrides matter |
| **Sequential rebate calculation** | Business requirement — Bumi rebate applies first, then other rebates apply on the reduced base |
| **Strict OCR prompts** | Accuracy — financial documents cannot tolerate hallucinated values |
| **File-based JSON storage** | MVP simplicity — database can be added later without changing engine logic |
| **Streamlit for UI** | Rapid prototyping — suitable for internal stakeholder demos and validation |

---

## 14. How to Run

### Prerequisites
```bash
pip install -r requirements.txt
```

### Environment Setup
Create a `.env` file with:
```
AZURE_OPENAI_ENDPOINT=<your-endpoint>
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_DEPLOYMENT=gpt-5.2-chat
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AGENT_OPENAI_ENDPOINT=<your-endpoint>
AGENT_OPENAI_API_KEY=<your-key>
```

### Run Streamlit Apps
```bash
# Single-memo calculator
cd Multiagent/rule-engine/single_memo
streamlit run app.py

# Multi-memo calculator
cd Multiagent/rule-engine/multi_memo
streamlit run app_multi_memo.py

# Management dashboard
cd Multiagent/rule-engine/multi_memo
streamlit run app_management.py
```

### Run Tests
```bash
# Single-memo tests
cd Multiagent/rule-engine/single_memo
python test_engine.py

# Multi-memo tests
cd Multiagent/rule-engine/multi_memo
python test_multi_memo.py
python test_conflict_resolution.py
```

---

## 15. File Tree (annotated)

```
Avaland/
├── requirements.txt                          # Python dependencies
├── .env                                      # Azure credentials (not committed)
├── DEVELOPMENT_LOG.md                        # THIS FILE
│
├── docintelligence/
│   ├── doc_intelligent.py                    # Azure Document Intelligence client
│   ├── output.json                           # Raw extraction output
│   └── sampleoutput.json                     # Reference sample
│
├── docs/
│   ├── README.md                             # Project overview & quick start
│   ├── ARCHITECTURE.md                       # System design
│   ├── MULTI_MEMO.md                         # Multi-memo support docs
│   ├── CONDITION_SYNTAX.md                   # Condition syntax reference
│   ├── RULE_CALCULATION.md                   # Calculation logic (CRITICAL)
│   ├── DATA_SCHEMAS.md                       # JSON schemas
│   ├── API_REFERENCE.md                      # API documentation
│   ├── EXAMPLES.md                           # Usage examples
│   └── CHEAT_SHEET.md                        # Quick reference
│
├── memo/
│   └── Memo1_upload/                         # Source PDF memos
│
└── Multiagent/
    ├── agent.py                              # Azure OpenAI agent test stub
    ├── config.py                             # Centralized secrets/config
    ├── test.py                               # Streamlit test UI (early version)
    │
    ├── artifact/                             # Extracted rule JSONs
    │   ├── extracted-rules.json              # Aetas Seputeh main rules
    │   ├── extracted-rules-memo_004.json     # Memo 004 rules
    │   ├── mockedrules.json                  # Test mock rules
    │   ├── mockedrules2.json                 # Additional mock rules
    │   └── superseding-rules.json            # Supersession test data
    │
    ├── Data/                                 # OCR/extraction outputs
    │   ├── output.json
    │   ├── output-table.json
    │   └── output-text.json
    │
    ├── ocr/                                  # OCR pipeline
    │   ├── ocr.py                            # Vision API text OCR
    │   ├── ocrtable.py                       # Vision API table OCR
    │   └── pdf_to_images.py                  # PDF → PNG converter
    │
    ├── rule-extract/
    │   └── rule.py                           # LLM rule extraction agent
    │
    └── rule-engine/
        ├── __init__.py                       # Package init
        │
        ├── single_memo/                      # Single-memo engine
        │   ├── app.py                        # Streamlit calculator UI
        │   ├── rule_loader.py                # Rule loading & indexing
        │   ├── rule_matcher.py               # Rule matching logic
        │   ├── rule_engine.py                # Calculation engine (aliased)
        │   └── test_engine.py                # Tests
        │
        └── multi_memo/                       # Multi-memo engine (PRIMARY)
            ├── app_management.py             # Management dashboard UI
            ├── app_management.py.bak         # Backup of management UI
            ├── app_multi_memo.py             # Multi-memo calculator UI
            ├── condition_parser.py           # AST-based condition parser
            ├── memo_manager.py               # Memo loading & filtering
            ├── memo_store.json               # Memo processing metadata
            ├── multi_memo_engine.py          # Top-level orchestrator
            ├── rule_aggregator.py            # Cross-memo aggregation
            ├── rule_engine.py                # Core calculation logic
            ├── test_conflict_resolution.py   # Conflict handling tests
            ├── test_multi_memo.py            # Multi-memo tests
            ├── MULTI_MEMO_README.md          # Module-level readme
            └── demo_data/
                └── management_mock_data.json # Mock agent/sales data
```

---

*End of Development Log*
