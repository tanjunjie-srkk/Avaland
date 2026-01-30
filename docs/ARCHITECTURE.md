# Architecture Overview

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        AVALAND RULE ENGINE SYSTEM                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────────────┐ │
│  │  Memo Documents  │ ──► │  Rule Extractor  │ ──► │  Extracted Rules (JSON)  │ │
│  │  (PDF/Word)      │     │  (AI/LLM based)  │     │  stored in /artifact     │ │
│  └──────────────────┘     └──────────────────┘     └───────────┬──────────────┘ │
│                                                                 │                │
│                                                                 ▼                │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                      MULTI-MEMO RULE ENGINE                               │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌─────────────────────────────┐ │   │
│  │  │ Memo Manager   │  │ Rule Aggregator │  │ Priority Ranker            │ │   │
│  │  │ - Load memos   │  │ - Combine rules │  │ - Recency score (40%)      │ │   │
│  │  │ - Date filter  │  │ - Detect conflicts│ │ - Specificity score (30%) │ │   │
│  │  │ - Project filter│ │ - Supersession   │  │ - Explicit priority (20%) │ │   │
│  │  └────────┬───────┘  └────────┬────────┘  │ - Memo hierarchy (10%)     │ │   │
│  │           │                   │           └──────────────┬──────────────┘ │   │
│  │           ▼                   ▼                          ▼                │   │
│  │  ┌──────────────────────────────────────────────────────────────────────┐│   │
│  │  │             AGGREGATED RULE LIBRARY (AggregatedRuleLibrary)          ││   │
│  │  │  - Indexed by type (commission, rebate, referral, package)           ││   │
│  │  │  - Indexed by project                                                 ││   │
│  │  │  - Tracks superseded rules                                            ││   │
│  │  │  - Maintains conflict records                                         ││   │
│  │  └──────────────────────────────────────────────────────────────────────┘│   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                       │
│                                          ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                         RULE MATCHING LAYER                               │   │
│  │  ┌────────────────────┐    ┌────────────────────────────────────────────┐│   │
│  │  │ Condition Parser   │    │ Enhanced Rule Matcher                      ││   │
│  │  │ - Parse IF...AND   │    │ - Evaluate conditions against context      ││   │
│  │  │ - Build evaluator  │◄──►│ - Calculate match scores                   ││   │
│  │  │ - Cache functions  │    │ - Combine with priority scores             ││   │
│  │  └────────────────────┘    └────────────────────────────────────────────┘│   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                       │
│                                          ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                       CALCULATION ENGINE                                  │   │
│  │                                                                           │   │
│  │   Context (Input)              Matched Rules            Result (Output)   │   │
│  │   ┌─────────────┐              ┌───────────┐           ┌───────────────┐  │   │
│  │   │ buyer_type  │              │ Rebates   │──────────►│ total_rebate  │  │   │
│  │   │ block       │     ────►    │ Commissions│─────────►│ total_commission│ │   │
│  │   │ floor_level │              │ Adjustments│─────────►│ price_adjustments│ │   │
│  │   │ unit_type   │              │ Packages  │──────────►│ final_price   │  │   │
│  │   │ base_price  │              └───────────┘           └───────────────┘  │   │
│  │   └─────────────┘                                                         │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Module Dependency Graph

```
multi_memo_engine.py (Main Orchestrator)
    │
    ├── memo_manager.py
    │       │
    │       └── (dataclasses: MemoMetadata, EnhancedRule, Memo)
    │
    ├── rule_aggregator.py
    │       │
    │       ├── memo_manager.py (imports MemoManager, EnhancedRule)
    │       │
    │       └── (dataclasses: RuleConflict, AggregatedRuleLibrary)
    │
    └── condition_parser.py
            │
            └── (no external dependencies - pure Python)

rule_engine.py (Single-Memo Engine - Legacy/Simple mode)
    │
    ├── rule_loader.py
    │
    ├── rule_matcher.py
    │
    └── condition_parser.py
```

---

## Directory Structure (Recommended)

```
Avaland/
├── docs/                          # Documentation
│   ├── README.md                  # Project overview
│   ├── ARCHITECTURE.md            # This file
│   ├── RULE_CALCULATION.md        # Calculation logic deep-dive
│   ├── CONDITION_SYNTAX.md        # Condition parsing guide
│   ├── MULTI_MEMO.md              # Multi-memo system guide
│   ├── DATA_SCHEMAS.md            # JSON schema definitions
│   └── API_REFERENCE.md           # API documentation
│
├── Multiagent/
│   ├── rule-engine/               # Core rule engine
│   │   ├── __init__.py
│   │   ├── multi_memo_engine.py   # Main multi-memo orchestrator
│   │   ├── rule_engine.py         # Single-memo engine (legacy)
│   │   ├── memo_manager.py        # Memo loading and filtering
│   │   ├── rule_aggregator.py     # Rule aggregation and conflicts
│   │   ├── rule_matcher.py        # Rule matching logic
│   │   ├── rule_loader.py         # JSON rule loading
│   │   ├── condition_parser.py    # Condition string parsing
│   │   ├── app.py                 # Application entry point
│   │   ├── app_multi_memo.py      # Multi-memo app entry
│   │   └── tests/                 # Unit tests
│   │       ├── test_engine.py
│   │       ├── test_multi_memo.py
│   │       └── test_conflict_resolution.py
│   │
│   ├── rule-extract/              # Rule extraction from documents
│   │   └── rule.py
│   │
│   ├── ocr/                       # OCR processing
│   │   ├── ocr.py
│   │   └── ocrtable.py
│   │
│   ├── artifact/                  # Extracted rule JSON files
│   │   ├── extracted-rules.json
│   │   ├── mockedrules.json
│   │   └── superseding-rules.json
│   │
│   └── Data/                      # OCR output data
│       ├── output.json
│       ├── output-table.json
│       └── output-text.json
│
├── docintelligence/               # Document intelligence (Azure)
│   ├── doc_intelligent.py
│   └── output.json
│
├── memo/                          # Source memo documents
│
└── .venv/                         # Python virtual environment
```

---

## Data Flow Summary

1. **Input**: PDF/Word memo documents in `/memo`
2. **Extraction**: OCR + AI extracts rules → JSON in `/artifact`
3. **Loading**: MemoManager loads JSON files
4. **Filtering**: Filter by project name and SPA date
5. **Aggregation**: Combine rules, detect/resolve conflicts
6. **Matching**: Match rules against buyer context
7. **Calculation**: Apply matched rules to compute pricing
8. **Output**: PricingResult with full traceability
