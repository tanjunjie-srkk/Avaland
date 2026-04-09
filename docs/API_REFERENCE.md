# API Reference

Complete API documentation for the Avaland Rule Engine.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [MultiMemoRuleEngine](#multimemoruleengine)
3. [RuleEngine (Single Memo)](#ruleengine-single-memo)
4. [Support Classes](#support-classes)
5. [Utility Functions](#utility-functions)

---

## Quick Start

```python
from multi_memo_engine import create_multi_memo_engine

# Create engine from artifacts folder
engine = create_multi_memo_engine("Multiagent/artifact")

# Prepare rules
engine.retrieve_and_prepare(project_name="Aetas Seputeh")

# Calculate
result = engine.calculate({
    "base_price": 1500000,
    "buyer_type": "local",
    "block": "B",
    "floor_level": 25,
    "buyer_is_bumi": True
})

print(f"Final Price: RM {result.final_price:,.0f}")
```

---

## MultiMemoRuleEngine

The main engine for multi-memo rule processing.

### Constructor

```python
MultiMemoRuleEngine(artifacts_path: str)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `artifacts_path` | `str` | Path to folder containing extracted rule JSON files |

### Methods

#### `load_memos() -> int`

Load all memo JSON files from the artifacts directory.

**Returns**: Number of memos loaded.

```python
engine = MultiMemoRuleEngine("Multiagent/artifact")
count = engine.load_memos()
print(f"Loaded {count} memos")
```

---

#### `retrieve_and_prepare(...) -> AggregatedRuleLibrary`

Filter memos and aggregate rules with conflict resolution.

```python
retrieve_and_prepare(
    project_name: Optional[str] = None,
    target_date: Optional[datetime] = None,
    resolution_strategy: ConflictResolution = ConflictResolution.LATEST_WINS
) -> AggregatedRuleLibrary
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_name` | `str` | Filter by project name |
| `target_date` | `datetime` | Filter by SPA date |
| `resolution_strategy` | `ConflictResolution` | How to resolve conflicts |

**Returns**: `AggregatedRuleLibrary` with ranked rules.

```python
from datetime import datetime
from rule_aggregator import ConflictResolution

library = engine.retrieve_and_prepare(
    project_name="Aetas Seputeh",
    target_date=datetime(2025, 8, 15),
    resolution_strategy=ConflictResolution.HIGHEST_PRIORITY
)
```

---

#### `get_applicable_rules(...) -> Dict[str, List[MatchedEnhancedRule]]`

Get all rules that match the given context.

```python
get_applicable_rules(
    context: Dict[str, Any],
    rule_types: Optional[List[str]] = None
) -> Dict[str, List[MatchedEnhancedRule]]
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `context` | `dict` | Buyer/unit context |
| `rule_types` | `list` | Optional filter for specific types |

**Returns**: Dictionary of rule type → matched rules.

```python
matches = engine.get_applicable_rules(
    context={"block": "B", "floor_level": 25},
    rule_types=["commission", "rebate"]
)

for rule_type, rules in matches.items():
    print(f"{rule_type}: {len(rules)} rules matched")
```

---

#### `calculate(...) -> MultiMemoPricingResult`

Perform full pricing calculation.

```python
calculate(
    context: Dict[str, Any],
    project_name: Optional[str] = None,
    spa_date: Optional[str] = None
) -> MultiMemoPricingResult
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `context` | `dict` | Buyer/unit context (must include `base_price`) |
| `project_name` | `str` | Target project for filtering |
| `spa_date` | `str` | SPA date string (e.g., "15 Aug 2025") |

**Returns**: `MultiMemoPricingResult` with full breakdown.

```python
result = engine.calculate(
    context={
        "base_price": 1500000,
        "buyer_type": "local",
        "block": "B",
        "floor_level": 25,
        "unit_type": "A1",
        "buyer_is_bumi": True
    },
    project_name="Aetas Seputeh",
    spa_date="15 Aug 2025"
)

print(f"Base Price: RM {result.base_price:,.0f}")
print(f"Total Rebate: RM {result.total_rebate:,.0f}")
print(f"Final Price: RM {result.final_price:,.0f}")
print(f"Commission: RM {result.total_commission:,.0f}")
```

---

## RuleEngine (Single Memo)

Simpler engine for single-memo scenarios.

### Constructor

```python
RuleEngine(rules_path: str, memo_file: Optional[str] = None)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `rules_path` | `str` | Path to single extracted rules JSON file |
| `memo_file` | `str` | Optional memo file reference |

### Methods

#### `calculate(context: Dict[str, Any]) -> PricingResult`

Calculate pricing from single memo rules.

```python
from rule_engine import RuleEngine

engine = RuleEngine("Multiagent/artifact/extracted-rules.json")

result = engine.calculate({
    "base_price": 1500000,
    "buyer_type": "local",
    "block": "B",
    "floor_level": 25
})
```

---

#### `get_applicable_rules(...) -> Dict[str, List[MatchedRule]]`

Get matching rules organized by type.

---

#### `explain_rules(context: Dict[str, Any]) -> str`

Generate human-readable explanation of which rules apply.

```python
explanation = engine.explain_rules(context)
print(explanation)
```

---

#### `list_all_rules() -> Dict[str, List[Dict]]`

List all available rules in the library.

```python
all_rules = engine.list_all_rules()
for rule_type, rules in all_rules.items():
    print(f"{rule_type}: {len(rules)} rules")
```

---

## Support Classes

### MultiMemoPricingResult

```python
@dataclass
class MultiMemoPricingResult:
    base_price: float
    final_price: float
    total_rebate: float
    total_commission: float
    
    rebate_breakdown: List[MultiMemoCalculationResult]
    commission_breakdown: List[MultiMemoCalculationResult]
    price_adjustments: List[MultiMemoCalculationResult]
    applicable_packages: List[str]
    
    matched_rules: List[str]
    source_memos: List[str]
    conflicts_detected: List[Dict[str, Any]]
    
    target_project: Optional[str]
    spa_date: Optional[str]
    
    # Statistics
    memos_considered: int
    memos_after_date_filter: int
    memos_after_project_filter: int
    rules_before_conflict_resolution: int
    rules_after_conflict_resolution: int
    
    def to_dict(self) -> Dict[str, Any]: ...
```

---

### MultiMemoCalculationResult

```python
@dataclass
class MultiMemoCalculationResult:
    rule_type: str
    rule_id: str
    composite_id: str
    rule_name: str
    description: str
    value: float
    value_type: str  # 'percentage' or 'fixed'
    calculated_amount: Optional[float]
    details: Dict[str, Any]
    
    # Traceability
    memo_reference: Optional[str]
    memo_file: Optional[str]
    project_name: Optional[str]
    effective_period: Optional[Dict[str, str]]
    priority_score: float
    
    conflicts: List[str]
    
    def to_dict(self) -> Dict[str, Any]: ...
```

---

### ConflictResolution

```python
from rule_aggregator import ConflictResolution

class ConflictResolution(Enum):
    LATEST_WINS = "latest_wins"
    HIGHEST_PRIORITY = "highest_priority"
    MOST_SPECIFIC = "most_specific"
    MERGE = "merge"
    MANUAL_REVIEW = "manual_review"
```

---

### AggregatedRuleLibrary

```python
@dataclass
class AggregatedRuleLibrary:
    rules: List[EnhancedRule]
    conflicts: List[RuleConflict]
    
    def add_rule(self, rule: EnhancedRule, check_conflicts: bool = True): ...
    def get_active_rules(self) -> List[EnhancedRule]: ...
    def get_by_type(self, rule_type: str) -> List[EnhancedRule]: ...
    def get_by_project(self, project_name: str) -> List[EnhancedRule]: ...
    def get_ranked_rules(self, rule_type: Optional[str] = None) -> List[EnhancedRule]: ...
    def get_all_types(self) -> List[str]: ...
    def get_conflicts_summary(self) -> Dict[str, Any]: ...
```

---

## Utility Functions

### create_multi_memo_engine

```python
from multi_memo_engine import create_multi_memo_engine

engine = create_multi_memo_engine(artifacts_path: str) -> MultiMemoRuleEngine
```

Creates and initializes a `MultiMemoRuleEngine` with memos loaded.

---

### create_engine

```python
from rule_engine import create_engine

engine = create_engine(rules_path: str) -> RuleEngine
```

Creates a single-memo `RuleEngine`.

---

### parse_condition

```python
from condition_parser import parse_condition

evaluator = parse_condition(condition_str: str) -> Callable[[Dict], bool]
```

Parse a condition string into an evaluator function.

```python
evaluator = parse_condition("IF block == 'B' AND floor_level >= 20")
result = evaluator({"block": "B", "floor_level": 25})  # True
```

---

## Error Handling

### Common Exceptions

| Exception | Cause | Solution |
|-----------|-------|----------|
| `FileNotFoundError` | Artifacts path doesn't exist | Check path to JSON files |
| `RuntimeError("Call retrieve_and_prepare() first")` | Methods called before preparation | Call `retrieve_and_prepare()` first |
| `JSONDecodeError` | Invalid JSON in memo file | Validate JSON syntax |
| `KeyError: 'base_price'` | Missing required context field | Include `base_price` in context |

---

## Performance Tips

1. **Call `retrieve_and_prepare()` once** - Reuse the engine for multiple calculations
2. **Use `rule_types` filter** - Limit matching to specific rule types when possible
3. **Condition caching** - `ConditionParser` caches parsed conditions automatically
4. **Batch calculations** - Reuse the same engine instance for multiple contexts
