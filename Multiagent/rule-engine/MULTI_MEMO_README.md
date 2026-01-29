# Multi-Memo Rule Engine

## Overview

The Multi-Memo Rule Engine extends the single-memo rule engine to support scenarios where multiple memos from various projects need to be processed together. It provides:

1. **Memo Management** - Load, index, and filter memos by date/project
2. **Rule Aggregation** - Combine rules from multiple memos with conflict detection
3. **Priority Ranking** - Rank rules using weighted scoring (recency, specificity, priority)
4. **Conflict Resolution** - Handle overlapping/contradictory rules intelligently
5. **Traceability** - Track every calculation back to its source memo

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-MEMO RULE RETRIEVAL SYSTEM                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. MEMO LOADING & INDEXING (MemoManager)                                   │
│     └── Load all memos from artifacts → Index by project, date, metadata   │
│                                                                             │
│  2. MEMO FILTERING (Pre-processing)                                         │
│     ├── Date Filter: SPA date within effective_period                      │
│     └── Project Filter: Match project_name with query context              │
│                                                                             │
│  3. RULE EXTRACTION & AGGREGATION (RuleAggregator)                          │
│     └── Extract all rules from filtered memos → Attach memo metadata       │
│                                                                             │
│  4. RULE PRIORITY & CONFLICT RESOLUTION (PriorityRanker)                    │
│     ├── Priority Ranking: Specificity, Recency, Explicit Priority          │
│     └── Conflict Resolution: Latest wins, Most specific wins, Merge        │
│                                                                             │
│  5. RULE MATCHING (EnhancedRuleMatcher)                                     │
│     └── Match context against ranked rule library                          │
│                                                                             │
│  6. CALCULATION (MultiMemoRuleEngine)                                       │
│     └── Apply matched rules → Generate results with memo traceability      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module Structure

### Core Modules

| Module | Description |
|--------|-------------|
| `memo_manager.py` | Memo loading, indexing, and filtering |
| `rule_aggregator.py` | Rule aggregation, priority ranking, conflict resolution |
| `multi_memo_engine.py` | Main orchestration engine |

### Data Structures

#### MemoMetadata
```python
@dataclass
class MemoMetadata:
    memo_reference: str          # Unique memo identifier
    memo_file: str               # Path to source file
    project_name: str            # Project this memo belongs to
    effective_period: Dict       # {"start_date": "...", "end_date": "..."}
    memo_type: MemoType          # STANDARD, SUPERSEDING, ADDENDUM, AMENDMENT
    supersedes: Optional[str]    # Reference to memo this supersedes
    priority: int                # Explicit priority (0-10)
    extraction_confidence: float # AI extraction confidence
    warnings: List[str]          # Extraction warnings
```

#### EnhancedRule
```python
@dataclass
class EnhancedRule:
    rule_id: str                 # Original rule ID
    rule_name: str
    rule_type: str               # commission, rebate, referral, etc.
    conditions: List[Dict]
    raw_data: Dict
    
    # Memo traceability
    memo_metadata: MemoMetadata  # Full traceability back to source
    
    # Priority scoring
    priority_score: float        # Composite priority score
    specificity_score: float     # Condition complexity score
    recency_score: float         # How recent the source memo is
    
    # Conflict tracking
    superseded_by: Optional[str] # Rule that supersedes this
    conflicts_with: List[str]    # Other conflicting rules
    
    @property
    def composite_id(self) -> str:
        """Unique ID: MEMO_REF::RULE_ID"""
```

## Priority Ranking System

### Scoring Components

The priority score is calculated as a weighted sum:

| Component | Weight | Description |
|-----------|--------|-------------|
| Recency | 40% | Newer memos get higher scores (0.0 = oldest, 1.0 = newest) |
| Specificity | 30% | More specific conditions score higher (based on AND clauses) |
| Explicit Priority | 20% | Manual priority field from memo (0-10, normalized) |
| Memo Hierarchy | 10% | Superseding memos > Amendments > Addendums > Standard |

### Specificity Calculation

```python
def calculate_specificity(condition_str: str) -> float:
    base_score = 0.2
    and_bonus = condition_str.count(' AND ') * 0.15
    operator_bonus = count_operators(condition_str) * 0.1
    return min(base_score + and_bonus + operator_bonus, 1.0)
```

Example scores:
- `IF block == 'A'` → 0.3
- `IF block == 'B' AND floor_level >= 20` → 0.55
- `IF block == 'B' AND floor_level >= 20 AND floor_level <= 29` → 0.7

## Conflict Resolution

### Conflict Types

| Type | Description | Default Resolution |
|------|-------------|-------------------|
| `SAME_RULE_ID` | Same rule ID in different memos | Latest memo wins |
| `OVERLAPPING_CONDITIONS` | Different rules with overlapping conditions | Most specific at match time |
| `CONTRADICTORY` | Rules that contradict each other | Higher priority wins |
| `SUPERSEDED` | Memo-level supersession | New memo wins |

### Resolution Strategies

```python
class ConflictResolution(Enum):
    LATEST_WINS = "latest_wins"          # Most recent memo wins
    HIGHEST_PRIORITY = "highest_priority" # Highest priority score wins
    MOST_SPECIFIC = "most_specific"       # Most specific condition wins
    MERGE = "merge"                       # Attempt to merge rules
    MANUAL_REVIEW = "manual_review"       # Flag for human review
```

## Enhanced Memo JSON Schema

The memo JSON files should include these metadata fields:

```json
{
  "memo_reference": "PROJECT-MEMO-2025-001",
  "effective_period": {
    "start_date": "15 Jun 2025",
    "end_date": "31 Dec 2025"
  },
  "project_name": "Project Name",
  "memo_type": "standard",        // "standard", "superseding", "addendum", "amendment"
  "supersedes": null,             // or "PROJECT-MEMO-2024-005" if superseding
  "priority": 5,                  // 0-10, higher = more important
  "rules": {
    "commission_rules": [...],
    "rebate_rules": [...],
    "referral_rules": [...],
    "price_adjustment_rules": [...],
    "package_rules": [...]
  },
  "extraction_confidence": 0.9,
  "warnings": ["Any extraction warnings"]
}
```

## Usage Examples

### Basic Multi-Memo Calculation

```python
from multi_memo_engine import create_multi_memo_engine
from datetime import datetime

# Create and load engine
engine = create_multi_memo_engine("path/to/artifacts")

# Prepare rules with filtering
engine.retrieve_and_prepare(
    project_name="Aetas Seputeh",
    target_date=datetime(2025, 8, 15),
    resolution_strategy=ConflictResolution.LATEST_WINS
)

# Define context
context = {
    "buyer_type": "local",
    "block": "B",
    "floor_level": 25,
    "unit_type": "A1",
    "buyer_is_bumi": True,
    "base_price": 1500000
}

# Calculate
result = engine.calculate(
    context=context,
    project_name="Aetas Seputeh",
    spa_date="15 Aug 2025"
)

# Access results with traceability
print(f"Final Price: RM{result.final_price:,.2f}")
print(f"Source Memos: {result.source_memos}")
print(f"Matched Rules: {result.matched_rules}")
```

### Priority Ranking Analysis

```python
from memo_manager import MemoManager
from rule_aggregator import RuleAggregator, ConflictResolution

# Load memos
manager = MemoManager("path/to/artifacts")
manager.load_all_memos()

# Aggregate with conflict detection
aggregator = RuleAggregator(manager)
library = aggregator.aggregate(resolution_strategy=ConflictResolution.LATEST_WINS)

# Get priority ranking
ranking = aggregator.get_priority_ranking(rule_type='commission', top_n=10)

for entry in ranking:
    print(f"Rank {entry['rank']}: {entry['rule_name']}")
    print(f"  Total Priority: {entry['total_priority']:.4f}")
    print(f"  Breakdown: {entry['priority_breakdown']}")
```

### Conflict Analysis

```python
# Get conflict summary
conflicts = library.get_conflicts_summary()

print(f"Total Conflicts: {conflicts['total_conflicts']}")
print(f"Needs Review: {conflicts['requires_review']}")

for conflict in conflicts['conflicts']:
    print(f"\n{conflict['conflict_id']}: {conflict['type']}")
    print(f"  Involved: {conflict['involved_rules']}")
    print(f"  Resolution: {conflict['resolution']}")
```

### Date-Based Filtering

```python
from datetime import datetime

# Filter memos effective on a specific date
target_date = datetime(2025, 8, 15)
effective_memos = manager.filter_by_date(target_date)

print(f"Memos effective on {target_date}:")
for ref in effective_memos:
    memo = manager.memos[ref]
    print(f"  - {ref}: {memo.metadata.effective_period}")
```

## Traceability

Every calculation result includes full traceability:

```python
result = engine.calculate(context)

for rebate in result.rebate_breakdown:
    print(f"Rule: {rebate.rule_name}")
    print(f"Composite ID: {rebate.composite_id}")  # MEMO_REF::RULE_ID
    print(f"Source Memo: {rebate.memo_reference}")
    print(f"Source File: {rebate.memo_file}")
    print(f"Project: {rebate.project_name}")
    print(f"Effective: {rebate.effective_period}")
    print(f"Priority: {rebate.priority_score}")
    print(f"Conflicts: {rebate.conflicts}")
```

## Best Practices

### 1. Memo Organization
- Use consistent `memo_reference` naming: `PROJECT-TYPE-YEAR-SEQ`
- Always include `effective_period` with both start and end dates
- Set `supersedes` when a new memo replaces an old one

### 2. Priority Management
- Use explicit `priority` field sparingly (most cases should rely on recency)
- Set higher priority (7-10) only for urgent/critical memos
- Use `memo_type: "superseding"` for complete replacements

### 3. Conflict Handling
- Review conflicts flagged with `requires_review: true`
- Use `MOST_SPECIFIC` resolution for overlapping conditions
- Use `LATEST_WINS` for same rule ID conflicts

### 4. Performance
- Filter by project and date before aggregation to reduce processing
- Use `top_n` parameter in `get_priority_ranking()` for large libraries

## API Reference

### MemoManager

| Method | Description |
|--------|-------------|
| `load_all_memos(directory)` | Load all JSON memos from directory |
| `filter_by_date(date, memos)` | Filter memos effective on date |
| `filter_by_project(project, fuzzy)` | Filter memos by project name |
| `filter_memos(project, date, types)` | Combined filtering |
| `get_statistics()` | Get memo/rule statistics |

### RuleAggregator

| Method | Description |
|--------|-------------|
| `aggregate(memos, strategy)` | Aggregate rules with conflict resolution |
| `get_priority_ranking(type, top_n)` | Get ranked rules |

### MultiMemoRuleEngine

| Method | Description |
|--------|-------------|
| `load_memos()` | Load all memos from artifacts |
| `retrieve_and_prepare(project, date, strategy)` | Filter and prepare rules |
| `calculate(context, project, spa_date)` | Perform calculation |
| `get_applicable_rules(context, types)` | Get matching rules |
| `explain_rules(context)` | Human-readable explanation |
| `get_conflicts_summary()` | Get conflict information |
| `get_statistics()` | Get engine statistics |
