# Rule Engine Cheat Sheet

Quick reference for the Avaland Rule Engine.

---

## 🚀 Quick Start

```python
from multi_memo_engine import create_multi_memo_engine

engine = create_multi_memo_engine("Multiagent/artifact")
engine.retrieve_and_prepare(project_name="Aetas Seputeh")

result = engine.calculate({
    "base_price": 1500000,
    "buyer_type": "local",
    "block": "B",
    "floor_level": 25,
    "unit_type": "A1",
    "buyer_is_bumi": True
})
```

---

## 📋 Context Fields

| Field | Type | Values |
|-------|------|--------|
| `base_price` | number | Required! e.g., `1500000` |
| `buyer_type` | string | `'local'`, `'foreign'` |
| `block` | string | `'A'`, `'B'` |
| `floor_level` | int | `11` - `38` |
| `unit_type` | string | `'A1'`, `'A2'`, `'B1'`, `'B2'` |
| `buyer_is_bumi` | bool | `True`, `False` |
| `is_garden_unit` | bool | `True`, `False` |
| `is_penthouse` | bool | `True`, `False` |

---

## 🧮 Calculation Order

```
1. Base Price
2. + Price Adjustments
3. - Bumi Rebate (FIRST)
4. - Other Rebates (on post-Bumi price)
5. = Final Price
6. × Commission % (separate)
```

---

## 💰 Key Formulas

### Rebate (on post-Bumi price)
```python
rebate = (base_price - bumi_rebate) × rebate_percentage / 100
```

### Commission (Foreign)
```python
commission = (net_price - package_value) × commission_percentage / 100
```

### Commission Payout Split
```python
payout_spa = commission × 0.30
payout_stage2a = commission × 0.70
```

---

## 📝 Condition Syntax

```
IF <field> <operator> <value> [AND/OR ...]
```

**Operators:** `==`, `!=`, `>=`, `<=`, `>`, `<`

**Examples:**
```
IF block == 'B'
IF floor_level >= 20 AND floor_level <= 29
IF buyer_is_bumi == True
```

---

## 🔧 Conflict Resolution

```python
from rule_aggregator import ConflictResolution

ConflictResolution.LATEST_WINS      # Default
ConflictResolution.HIGHEST_PRIORITY
ConflictResolution.MOST_SPECIFIC
```

---

## 📊 Result Access

```python
result = engine.calculate(context)

result.base_price          # Original price
result.final_price         # After rebates
result.total_rebate        # Sum of all rebates
result.total_commission    # Agent commission

result.rebate_breakdown    # List of rebate details
result.source_memos        # Which memos were used
result.conflicts_detected  # Any conflicts found
```

---

## 🗂️ File Structure

```
docs/
├── README.md              # Overview
├── ARCHITECTURE.md        # System design
├── RULE_CALCULATION.md    # ⭐ Calculation logic
├── CONDITION_SYNTAX.md    # How conditions work
├── MULTI_MEMO.md          # Multi-memo handling
├── DATA_SCHEMAS.md        # JSON schemas
└── API_REFERENCE.md       # Full API docs

Multiagent/
├── rule-engine/           # Core engine
├── artifact/              # Extracted rules JSON
├── ocr/                   # OCR processing
└── rule-extract/          # Rule extraction
```

---

## ⚠️ Common Mistakes

| Mistake | Fix |
|---------|-----|
| Forgot `base_price` | Always include in context |
| String not quoted | Use `'A'` not `A` |
| Wrong boolean case | Use `True` not `true` |
| Called calculate before prepare | Call `retrieve_and_prepare()` first |
| Rebate order wrong | Bumi rebate applies FIRST |

---

## 🔗 Quick Links

- [Full Calculation Guide](./RULE_CALCULATION.md)
- [API Reference](./API_REFERENCE.md)
- [Data Schemas](./DATA_SCHEMAS.md)
