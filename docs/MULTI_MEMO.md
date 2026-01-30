# Multi-Memo System Guide

This document explains how multiple memos are managed, filtered, and how conflicts are resolved.

---

## Why Multi-Memo?

In real-world scenarios:
- Multiple memos exist for different projects
- Memos can supersede previous memos
- Addendums and amendments modify existing rules
- SPA date determines which memos are valid
- Conflicting rules need resolution

---

## System Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-MEMO RETRIEVAL FLOW                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 1: LOAD ALL MEMOS                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  MemoManager.load_all_memos()                                       │   │
│  │  - Scan artifact folder for JSON files                              │   │
│  │  - Parse each file into Memo objects                                │   │
│  │  - Extract metadata (reference, dates, project, type)               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  STEP 2: FILTER BY DATE AND PROJECT                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  MemoManager.filter_memos(project_name, target_date)                │   │
│  │  - Remove memos outside effective period                            │   │
│  │  - Remove memos for other projects (if project specified)           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  STEP 3: AGGREGATE RULES                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  RuleAggregator.aggregate()                                         │   │
│  │  - Extract rules from all filtered memos                            │   │
│  │  - Attach memo metadata to each rule                                │   │
│  │  - Detect conflicting rules (same ID, overlapping conditions)       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  STEP 4: PRIORITY RANKING                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PriorityRanker.rank()                                              │   │
│  │  - Calculate recency score (40%)                                    │   │
│  │  - Calculate specificity score (30%)                                │   │
│  │  - Apply explicit priority (20%)                                    │   │
│  │  - Apply memo hierarchy (10%)                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  STEP 5: CONFLICT RESOLUTION                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Apply resolution strategy:                                         │   │
│  │  - LATEST_WINS: Most recent memo's rule wins                       │   │
│  │  - HIGHEST_PRIORITY: Highest composite score wins                  │   │
│  │  - MOST_SPECIFIC: Most specific condition wins                     │   │
│  │  - MERGE: Attempt to combine rules                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  OUTPUT: AGGREGATED RULE LIBRARY                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  - Active rules (non-superseded)                                    │   │
│  │  - Indexed by type, project, composite ID                          │   │
│  │  - Conflict records for audit                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Memo Types

| Type | Code | Description |
|------|------|-------------|
| **Standard** | `standard` | Regular memo with new rules |
| **Superseding** | `superseding` | Completely replaces a previous memo |
| **Addendum** | `addendum` | Adds new rules to an existing memo |
| **Amendment** | `amendment` | Modifies specific rules in an existing memo |

### Hierarchy (Priority Order)

```
SUPERSEDING > AMENDMENT > ADDENDUM > STANDARD
```

---

## Memo JSON Schema

Each memo JSON file should include:

```json
{
  "memo_reference": "AVALUX-AD-MEMO-SM-2025-009",
  "effective_period": {
    "start_date": "15 Jun 2025",
    "end_date": "31 Dec 2025"
  },
  "project_name": "Aetas Seputeh",
  "memo_type": "standard",
  "supersedes": null,
  "priority": 5,
  "rules": {
    "commission_rules": [...],
    "rebate_rules": [...],
    "referral_rules": [...],
    "price_adjustment_rules": [...],
    "package_rules": [...]
  },
  "extraction_confidence": 0.9,
  "warnings": []
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `memo_reference` | string | Yes | Unique identifier for the memo |
| `effective_period` | object | Yes | Start and end dates |
| `project_name` | string | Yes | Project this memo belongs to |
| `memo_type` | string | No | One of: standard, superseding, addendum, amendment |
| `supersedes` | string | No | Reference of memo this supersedes |
| `priority` | integer | No | Explicit priority (0-10, higher = more important) |
| `rules` | object | Yes | Container for all rule types |
| `extraction_confidence` | float | No | AI extraction confidence (0-1) |
| `warnings` | array | No | Any extraction warnings |

---

## Priority Scoring System

### Components

| Component | Weight | Range | Description |
|-----------|--------|-------|-------------|
| **Recency** | 40% | 0.0-1.0 | Newer memos score higher |
| **Specificity** | 30% | 0.0-1.0 | More complex conditions score higher |
| **Explicit Priority** | 20% | 0-1000 | Manual priority field × 100 |
| **Memo Hierarchy** | 10% | 0.0-1.0 | Superseding > Amendment > Addendum > Standard |

### Recency Score Calculation

```python
def calculate_recency(memo_date, oldest_date, newest_date):
    if oldest_date == newest_date:
        return 1.0
    
    date_range = (newest_date - oldest_date).days
    memo_offset = (memo_date - oldest_date).days
    
    return memo_offset / date_range  # 0.0 = oldest, 1.0 = newest
```

### Specificity Score Calculation

```python
def calculate_specificity(condition_str):
    base_score = 0.2
    and_bonus = condition_str.count(' AND ') * 0.15
    operator_bonus = count_operators(condition_str) * 0.1
    return min(base_score + and_bonus + operator_bonus, 1.0)
```

### Total Priority Formula

```python
def get_total_priority(rule):
    explicit_priority = (rule.memo_metadata.priority or 0) * 100
    
    return (
        rule.recency_score * 0.40 +
        rule.specificity_score * 0.30 +
        explicit_priority * 0.20 +
        rule.priority_score * 0.10
    )
```

---

## Conflict Types

| Type | Code | Description |
|------|------|-------------|
| **Same Rule ID** | `same_rule_id` | Same rule ID appears in multiple memos |
| **Overlapping Conditions** | `overlapping` | Different rules with overlapping conditions |
| **Contradictory** | `contradictory` | Rules that contradict each other |
| **Superseded** | `superseded` | Memo-level supersession |

---

## Resolution Strategies

### 1. LATEST_WINS (Default)

The rule from the most recent memo is used.

```python
ConflictResolution.LATEST_WINS
```

**When to use**: When newer memos should always override older ones.

### 2. HIGHEST_PRIORITY

The rule with the highest composite priority score wins.

```python
ConflictResolution.HIGHEST_PRIORITY
```

**When to use**: When explicit priority settings should be respected.

### 3. MOST_SPECIFIC

The rule with the most specific condition wins.

```python
ConflictResolution.MOST_SPECIFIC
```

**When to use**: When you want detailed rules to override general rules.

### 4. MERGE

Attempt to merge non-contradictory rules.

```python
ConflictResolution.MERGE
```

**When to use**: When rules can be combined without contradiction.

### 5. MANUAL_REVIEW

Flag for human review without automatic resolution.

```python
ConflictResolution.MANUAL_REVIEW
```

**When to use**: For critical conflicts that require human judgment.

---

## Usage Example

```python
from multi_memo_engine import create_multi_memo_engine
from rule_aggregator import ConflictResolution
from datetime import datetime

# Create engine
engine = create_multi_memo_engine("Multiagent/artifact")

# Load all memos
engine.load_memos()

# Prepare with filtering
library = engine.retrieve_and_prepare(
    project_name="Aetas Seputeh",
    target_date=datetime(2025, 8, 15),
    resolution_strategy=ConflictResolution.LATEST_WINS
)

# Check conflicts
conflicts = library.get_conflicts_summary()
print(f"Total conflicts detected: {conflicts['total_conflicts']}")
print(f"Requires manual review: {conflicts['requires_review']}")

# Get active rules (non-superseded)
active_rules = library.get_active_rules()
print(f"Active rules: {len(active_rules)}")

# Calculate pricing
context = {
    "buyer_type": "local",
    "block": "B",
    "floor_level": 25,
    "base_price": 1500000
}

result = engine.calculate(context, spa_date="15 Aug 2025")

# Check traceability
for rebate in result.rebate_breakdown:
    print(f"Rebate: {rebate.rule_name}")
    print(f"  From memo: {rebate.memo_reference}")
    print(f"  Amount: RM {rebate.calculated_amount:,.0f}")
```

---

## Traceability

Every calculation result includes full memo traceability:

```python
@dataclass
class MultiMemoCalculationResult:
    rule_type: str
    rule_id: str
    composite_id: str        # Format: "MEMO_REF::RULE_ID"
    rule_name: str
    calculated_amount: float
    
    # Traceability
    memo_reference: str      # Source memo reference
    memo_file: str           # Path to source file
    project_name: str        # Project name
    effective_period: dict   # Start and end dates
    priority_score: float    # Final priority score
    conflicts: List[str]     # Other rules this conflicts with
```

---

## Statistics

The engine tracks filtering statistics:

```python
result = engine.calculate(context)

print(f"Memos considered: {result.memos_considered}")
print(f"After date filter: {result.memos_after_date_filter}")
print(f"After project filter: {result.memos_after_project_filter}")
print(f"Rules before conflict resolution: {result.rules_before_conflict_resolution}")
print(f"Rules after conflict resolution: {result.rules_after_conflict_resolution}")
```
