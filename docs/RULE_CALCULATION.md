# Rule Calculation Guide

> **This is the most important document for understanding how pricing calculations work.**

This document explains the complete calculation flow, formulas, and business logic used in the rule engine.

---

## Table of Contents

1. [Calculation Overview](#calculation-overview)
2. [Rule Types](#rule-types)
3. [Calculation Order](#calculation-order)
4. [Rebate Calculations](#rebate-calculations)
5. [Commission Calculations](#commission-calculations)
6. [Price Adjustment Calculations](#price-adjustment-calculations)
7. [Final Price Formula](#final-price-formula)
8. [Worked Examples](#worked-examples)
9. [Edge Cases](#edge-cases)

---

## Calculation Overview

The rule engine calculates the final price of a property unit based on:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     PRICING CALCULATION FLOW                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   BASE PRICE (List Price)                                               │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────────────────────────────┐                          │
│   │  (+/-) PRICE ADJUSTMENTS                │                          │
│   │  - Garden unit premium                  │                          │
│   │  - Penthouse premium                    │                          │
│   │  - Floor premium/discount               │                          │
│   └─────────────────────────────────────────┘                          │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────────────────────────────┐                          │
│   │  (-) BUMI REBATE (if applicable)        │  ← Always calculated     │
│   │  Usually 5% of adjusted base price      │    FIRST if buyer is     │
│   └─────────────────────────────────────────┘    Bumiputera            │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────────────────────────────┐                          │
│   │  (-) OTHER REBATES                      │  ← Calculated on price   │
│   │  - Standard rebate (by unit type)       │    AFTER Bumi rebate     │
│   │  - Special rebate (by floor tier)       │                          │
│   │  - Additional rebates                   │                          │
│   └─────────────────────────────────────────┘                          │
│        │                                                                │
│        ▼                                                                │
│   ═══════════════════════════════════════════                          │
│   FINAL PRICE (Net Selling Price)                                      │
│   ═══════════════════════════════════════════                          │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────────────────────────────┐                          │
│   │  COMMISSION CALCULATION                 │  ← Separate from price,  │
│   │  Based on net price (or adjusted)       │    payable to agents     │
│   └─────────────────────────────────────────┘                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Rule Types

| Type | Code | Description |
|------|------|-------------|
| **Commission** | `commission` | Agent commission percentages |
| **Rebate** | `rebate` | Price discounts for buyers |
| **Referral** | `referral` | Referrer rewards |
| **Price Adjustment** | `price_adjustment` | Fixed amount adjustments |
| **Package** | `package` | Included packages (e.g., furniture) |

---

## Calculation Order

**CRITICAL**: The order of calculations matters!

```
1. Price Adjustments   → Applied to base price
2. Bumi Rebate         → Applied FIRST (on adjusted base)
3. Other Rebates       → Applied AFTER Bumi rebate
4. Final Price         → Base + Adjustments - All Rebates
5. Commission          → Calculated on net price (separate)
```

### Why Order Matters

Consider this scenario:
- Base Price: RM 1,000,000
- Bumi Rebate: 5%
- Standard Rebate: 9%

**Correct (Sequential)**:
```
Bumi Rebate = 1,000,000 × 5% = RM 50,000
Price after Bumi = 1,000,000 - 50,000 = RM 950,000
Standard Rebate = 950,000 × 9% = RM 85,500  ← Calculated on RM 950,000
Total Rebate = 50,000 + 85,500 = RM 135,500
```

**Wrong (Parallel)**:
```
Bumi Rebate = 1,000,000 × 5% = RM 50,000
Standard Rebate = 1,000,000 × 9% = RM 90,000  ← WRONG! Uses base price
Total Rebate = 50,000 + 90,000 = RM 140,000   ← Overcharges!
```

---

## Rebate Calculations

### Rebate Rule Structure

```json
{
  "rule_id": "REB_001",
  "rule_name": "Bumi Rebate",
  "rebate_type": "bumi",
  "conditions": [
    {
      "condition": "IF buyer_is_bumi == True",
      "rebate_percentage": 5.0,
      "description": "Applicable to all eligible Bumi buyers"
    }
  ],
  "calculation_base": "Net Price"
}
```

### Calculation Base Options

| `calculation_base` Value | Meaning |
|--------------------------|---------|
| `"Net Price"` | Use the original base price |
| `"Net Price after Bumi Rebate"` | Use price after Bumi rebate is deducted |

### Rebate Formula

```python
def calculate_rebate(match, base_price, accumulated_rebate):
    percentage = match.get_percentage()  # e.g., 5.0 for 5%
    
    calc_base = match.rule.raw_data.get('calculation_base', 'Net Price')
    
    if 'after Bumi' in calc_base:
        # Calculate on price AFTER bumi rebate
        effective_price = base_price - accumulated_rebate
    else:
        # Calculate on original base price
        effective_price = base_price
    
    calculated_amount = effective_price * (percentage / 100)
    
    return calculated_amount
```

### Rebate Types

| Rebate Type | Priority | Description |
|-------------|----------|-------------|
| `bumi` | 1st | Bumiputera discount, always applied first |
| `standard` | 2nd | Standard unit type rebates (A1, A2, B1, B2) |
| `special` | 3rd | Floor tier specific rebates |
| `additional` | 4th | Additional promotional rebates |

---

## Commission Calculations

### Commission Rule Structure

```json
{
  "rule_id": "COM_002",
  "rule_name": "Local Buyer Commission – Block B by Floor Tier",
  "buyer_type": "local",
  "conditions": [
    {
      "condition": "IF block == 'B' AND floor_level >= 11 AND floor_level <= 19",
      "commission_percentage": 6.0,
      "description": "Low floors Block B (Level 11–19)"
    },
    {
      "condition": "IF block == 'B' AND floor_level >= 20 AND floor_level <= 29",
      "commission_percentage": 5.0,
      "description": "Mid floors Block B (Level 20–29)"
    }
  ]
}
```

### Commission Formula

```python
def calculate_commission(match, net_price, context):
    percentage = match.get_percentage()  # e.g., 5.0 for 5%
    
    # For foreign buyers, deduct package value first
    commission_base = net_price
    if context.get('buyer_type') == 'foreign':
        package_value = 200000  # RM 200k partially furnished package
        commission_base = net_price - package_value
    
    calculated_amount = commission_base * (percentage / 100)
    
    # Commission payout split (from memo terms)
    payout_spa = calculated_amount * 0.30      # 30% upon SPA
    payout_stage2a = calculated_amount * 0.70  # 70% upon Stage 2A
    
    return {
        'total_commission': calculated_amount,
        'payout_spa': payout_spa,
        'payout_stage2a': payout_stage2a
    }
```

### Commission by Buyer Type

| Buyer Type | Block | Floor Range | Commission % |
|------------|-------|-------------|--------------|
| Local | A | All | 2% |
| Local | B | 11-19 | 6% |
| Local | B | 20-29 | 5% |
| Local | B | 30-38 | 4% |
| Foreign | B | All | 7% |
| Local | Special | Garden/Penthouse | 3% |

---

## Price Adjustment Calculations

### Price Adjustment Rule Structure

```json
{
  "rule_id": "ADJ_001",
  "rule_name": "Garden Unit Premium",
  "adjustment_type": "premium",
  "conditions": [
    {
      "condition": "IF is_garden_unit == True",
      "adjustment_amount": 50000,
      "description": "Garden unit premium"
    }
  ]
}
```

### Adjustment Formula

```python
def calculate_price_adjustment(match):
    amount = match.get_amount()  # Fixed amount (can be + or -)
    return amount  # Positive = premium, Negative = discount
```

---

## Final Price Formula

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  FINAL PRICE FORMULA                                                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Final Price = Base Price                                                    │
│              + SUM(Price Adjustments)                                        │
│              - SUM(All Rebates)                                              │
│                                                                              │
│  Where:                                                                      │
│    - Price Adjustments: Fixed amounts (+/-)                                  │
│    - All Rebates: Bumi + Standard + Special + Additional                    │
│                                                                              │
│  Commission (separate, not affecting final price):                          │
│    Commission = (Net Price or Adjusted Base) × Commission%                  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Python Implementation:**

```python
# From multi_memo_engine.py
adjustment_total = sum(r.calculated_amount or 0 for r in price_adjustments)
final_price = base_price + adjustment_total - total_rebate
```

---

## Worked Examples

### Example 1: Local Bumi Buyer, Block B, Level 25, Type A1

**Input Context:**
```python
context = {
    "buyer_type": "local",
    "block": "B",
    "floor_level": 25,
    "unit_type": "A1",
    "buyer_is_bumi": True,
    "base_price": 1500000
}
```

**Step-by-Step Calculation:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Base Price                                                          │
│         RM 1,500,000                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 2: Price Adjustments                                                   │
│         None applicable                                                     │
│         Adjusted Base = RM 1,500,000                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 3: Bumi Rebate (REB_001)                                               │
│         Condition: buyer_is_bumi == True ✓                                  │
│         Rate: 5%                                                            │
│         Calculation Base: Net Price = RM 1,500,000                          │
│         Amount: 1,500,000 × 5% = RM 75,000                                  │
│         Price after Bumi: 1,500,000 - 75,000 = RM 1,425,000                │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 4: Standard Rebate by Unit Type (REB_002)                              │
│         Condition: unit_type == 'A1' ✓                                      │
│         Rate: 9%                                                            │
│         Calculation Base: Net Price after Bumi = RM 1,425,000               │
│         Amount: 1,425,000 × 9% = RM 128,250                                 │
│         Price after Standard: 1,425,000 - 128,250 = RM 1,296,750           │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 5: Special Rebate – Block B Floor Tier (REB_003)                       │
│         Condition: block == 'B' AND floor_level >= 20 AND floor <= 29 ✓    │
│         Rate: 7%                                                            │
│         Calculation Base: Net Price after Bumi = RM 1,425,000               │
│         Amount: 1,425,000 × 7% = RM 99,750                                  │
│         Price after Special: 1,296,750 - 99,750 = RM 1,197,000             │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 6: Final Price                                                         │
│         Base: RM 1,500,000                                                  │
│         Total Rebates: 75,000 + 128,250 + 99,750 = RM 303,000              │
│         Final Price: 1,500,000 - 303,000 = RM 1,197,000                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP 7: Commission (COM_002 - Block B Mid Floor)                            │
│         Condition: block == 'B' AND floor >= 20 AND floor <= 29 ✓          │
│         Rate: 5%                                                            │
│         Commission Base: Final Price = RM 1,197,000                         │
│         Commission: 1,197,000 × 5% = RM 59,850                              │
│         Payout SPA (30%): RM 17,955                                         │
│         Payout Stage 2A (70%): RM 41,895                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Final Result:**
```
Base Price:      RM 1,500,000
Bumi Rebate:     RM    75,000 (5%)
Standard Rebate: RM   128,250 (9% of post-Bumi)
Special Rebate:  RM    99,750 (7% of post-Bumi)
─────────────────────────────
Total Rebates:   RM   303,000
Final Price:     RM 1,197,000
─────────────────────────────
Commission:      RM    59,850 (5%)
```

---

### Example 2: Foreign Buyer, Block B, Level 15

**Input Context:**
```python
context = {
    "buyer_type": "foreign",
    "block": "B",
    "floor_level": 15,
    "unit_type": "B1",
    "buyer_is_bumi": False,
    "base_price": 2000000
}
```

**Calculation:**

```
Base Price:           RM 2,000,000
Bumi Rebate:          RM         0 (not eligible)
Standard Rebate:      RM         0 (assume no B1 rebate defined)
Special Rebate (B 11-19): RM 200,000 (10%)
─────────────────────────────────────
Final Price:          RM 1,800,000

Commission (Foreign 7%):
  Commission Base = Final Price - Package = 1,800,000 - 200,000 = RM 1,600,000
  Commission = 1,600,000 × 7% = RM 112,000
```

---

## Edge Cases

### 1. Multiple Conditions Match Same Rule

When multiple conditions in a rule match, the engine uses the **first matching condition** with the highest match score.

```python
# Rule COM_002 has 3 conditions for Block B floors
# Only ONE will be applied based on floor_level
```

### 2. Overlapping Rules from Multiple Memos

When the same rule ID exists in multiple memos, conflict resolution applies:

```
Resolution Strategies:
├── LATEST_WINS        → Most recent memo's rule is used
├── HIGHEST_PRIORITY   → Highest priority score wins
├── MOST_SPECIFIC      → Most specific condition wins
└── MANUAL_REVIEW      → Flagged for human review
```

### 3. Missing Context Values

If a context value is missing, the condition evaluates to `False`:

```python
# Condition: "IF block == 'B'"
# Context: {"buyer_type": "local"}  # No 'block' key
# Result: False (does not match)
```

### 4. Zero Percentage Rules

Rules with 0% are still tracked but produce RM 0 amounts.

---

## Code References

| Calculation | File | Function |
|-------------|------|----------|
| Rebate | `multi_memo_engine.py` | `_calculate_rebate()` |
| Commission | `multi_memo_engine.py` | `_calculate_commission()` |
| Price Adjustment | `multi_memo_engine.py` | `_calculate_price_adjustment()` |
| Final Price | `multi_memo_engine.py` | `calculate()` |
| Condition Parsing | `condition_parser.py` | `parse()` |

---

## Validation Checklist

Use this checklist when adding new rules:

- [ ] Condition syntax is valid (`IF ... == ... AND ...`)
- [ ] Percentage values are numeric (not strings)
- [ ] `calculation_base` is specified for rebates
- [ ] `buyer_type` filter is set (if applicable)
- [ ] Rule ID is unique within the memo
- [ ] Effective period is specified in memo metadata
