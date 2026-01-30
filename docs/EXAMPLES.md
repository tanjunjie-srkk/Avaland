# Calculation Examples

Real-world calculation examples for reference.

---

## Example 1: Local Bumi Buyer - Block B, Mid Floor

### Input
```python
context = {
    "base_price": 1_500_000,
    "buyer_type": "local",
    "block": "B",
    "floor_level": 25,
    "unit_type": "A1",
    "buyer_is_bumi": True
}
```

### Matched Rules
| Rule ID | Rule Name | Type | Rate |
|---------|-----------|------|------|
| REB_001 | Bumi Rebate | rebate | 5% |
| REB_002 | Standard Rebate (A1) | rebate | 9% |
| REB_003 | Special Rebate (B 20-29) | rebate | 7% |
| COM_002 | Block B Commission (20-29) | commission | 5% |

### Step-by-Step Calculation

```
STEP 1: Base Price
         RM 1,500,000

STEP 2: Bumi Rebate (5% of base)
         1,500,000 × 5% = RM 75,000
         After Bumi: 1,500,000 - 75,000 = RM 1,425,000

STEP 3: Standard Rebate A1 (9% of post-Bumi)
         1,425,000 × 9% = RM 128,250
         After Standard: 1,425,000 - 128,250 = RM 1,296,750

STEP 4: Special Rebate B 20-29 (7% of post-Bumi)
         1,425,000 × 7% = RM 99,750
         After Special: 1,296,750 - 99,750 = RM 1,197,000

STEP 5: Final Price
         RM 1,197,000

STEP 6: Commission (5% of final)
         1,197,000 × 5% = RM 59,850
         - Payout at SPA (30%): RM 17,955
         - Payout at Stage 2A (70%): RM 41,895
```

### Summary
| Item | Amount |
|------|--------|
| Base Price | RM 1,500,000 |
| Bumi Rebate | -RM 75,000 |
| Standard Rebate | -RM 128,250 |
| Special Rebate | -RM 99,750 |
| **Total Rebates** | **-RM 303,000** |
| **Final Price** | **RM 1,197,000** |
| Agent Commission | RM 59,850 |

---

## Example 2: Local Non-Bumi Buyer - Block A

### Input
```python
context = {
    "base_price": 2_000_000,
    "buyer_type": "local",
    "block": "A",
    "floor_level": 15,
    "unit_type": "A2",
    "buyer_is_bumi": False
}
```

### Matched Rules
| Rule ID | Rule Name | Type | Rate |
|---------|-----------|------|------|
| REB_002 | Standard Rebate (A2) | rebate | 6% |
| COM_001 | Block A Commission | commission | 2% |

### Calculation

```
Base Price:        RM 2,000,000
Bumi Rebate:       RM 0 (not eligible)
Standard Rebate:   2,000,000 × 6% = RM 120,000
Final Price:       2,000,000 - 120,000 = RM 1,880,000
Commission:        1,880,000 × 2% = RM 37,600
```

### Summary
| Item | Amount |
|------|--------|
| Base Price | RM 2,000,000 |
| Standard Rebate (A2) | -RM 120,000 |
| **Final Price** | **RM 1,880,000** |
| Agent Commission | RM 37,600 |

---

## Example 3: Foreign Buyer - Block B, Low Floor

### Input
```python
context = {
    "base_price": 1_800_000,
    "buyer_type": "foreign",
    "block": "B",
    "floor_level": 15,
    "unit_type": "B1",
    "buyer_is_bumi": False
}
```

### Matched Rules
| Rule ID | Rule Name | Type | Rate |
|---------|-----------|------|------|
| REB_003 | Special Rebate (B 11-19) | rebate | 10% |
| COM_004 | Foreign Commission | commission | 7% |
| PKG_001 | Partially Furnished Package | package | RM 200,000 |

### Calculation

```
Base Price:         RM 1,800,000
Bumi Rebate:        RM 0 (not eligible)
Special Rebate:     1,800,000 × 10% = RM 180,000
Final Price:        1,800,000 - 180,000 = RM 1,620,000

Commission Base:    1,620,000 - 200,000 (package) = RM 1,420,000
Commission:         1,420,000 × 7% = RM 99,400
  - Payout SPA:     RM 29,820
  - Payout 2A:      RM 69,580
```

### Summary
| Item | Amount |
|------|--------|
| Base Price | RM 1,800,000 |
| Special Rebate (B 11-19) | -RM 180,000 |
| **Final Price** | **RM 1,620,000** |
| Package Value | RM 200,000 |
| Commission Base | RM 1,420,000 |
| Agent Commission | RM 99,400 |

---

## Example 4: Garden Unit

### Input
```python
context = {
    "base_price": 2_500_000,
    "buyer_type": "local",
    "block": "B",
    "floor_level": 10,
    "unit_type": "A1",
    "buyer_is_bumi": True,
    "is_garden_unit": True
}
```

### Matched Rules
| Rule ID | Rule Name | Type | Rate/Amount |
|---------|-----------|------|-------------|
| ADJ_001 | Garden Unit Premium | adjustment | +RM 50,000 |
| REB_001 | Bumi Rebate | rebate | 5% |
| REB_002 | Standard Rebate (A1) | rebate | 9% |
| COM_003 | Special Units Commission | commission | 3% |

### Calculation

```
Base Price:          RM 2,500,000
Garden Premium:      +RM 50,000
Adjusted Base:       RM 2,550,000

Bumi Rebate:         2,550,000 × 5% = RM 127,500
After Bumi:          2,550,000 - 127,500 = RM 2,422,500

Standard Rebate:     2,422,500 × 9% = RM 218,025
Final Price:         2,422,500 - 218,025 = RM 2,204,475

Commission:          2,204,475 × 3% = RM 66,134
```

### Summary
| Item | Amount |
|------|--------|
| Base Price | RM 2,500,000 |
| Garden Premium | +RM 50,000 |
| Adjusted Base | RM 2,550,000 |
| Bumi Rebate | -RM 127,500 |
| Standard Rebate | -RM 218,025 |
| **Final Price** | **RM 2,204,475** |
| Agent Commission | RM 66,134 |

---

## Example 5: High Floor Block B

### Input
```python
context = {
    "base_price": 3_000_000,
    "buyer_type": "local",
    "block": "B",
    "floor_level": 35,
    "unit_type": "A1",
    "buyer_is_bumi": False
}
```

### Matched Rules
| Rule ID | Rule Name | Type | Rate |
|---------|-----------|------|------|
| REB_002 | Standard Rebate (A1) | rebate | 9% |
| REB_003 | Special Rebate (B 30+) | rebate | 6% |
| COM_002 | Block B Commission (30-38) | commission | 4% |

### Calculation

```
Base Price:          RM 3,000,000
Bumi Rebate:         RM 0 (not eligible)

Standard Rebate:     3,000,000 × 9% = RM 270,000
After Standard:      3,000,000 - 270,000 = RM 2,730,000

Special Rebate:      3,000,000 × 6% = RM 180,000
After Special:       2,730,000 - 180,000 = RM 2,550,000

Final Price:         RM 2,550,000

Commission:          2,550,000 × 4% = RM 102,000
```

### Summary
| Item | Amount |
|------|--------|
| Base Price | RM 3,000,000 |
| Standard Rebate (A1) | -RM 270,000 |
| Special Rebate (B 30+) | -RM 180,000 |
| **Final Price** | **RM 2,550,000** |
| Agent Commission | RM 102,000 |

---

## Python Code to Run Examples

```python
from multi_memo_engine import create_multi_memo_engine

# Initialize
engine = create_multi_memo_engine("Multiagent/artifact")
engine.retrieve_and_prepare(project_name="Aetas Seputeh")

# Example 1: Local Bumi Buyer
result = engine.calculate({
    "base_price": 1_500_000,
    "buyer_type": "local",
    "block": "B",
    "floor_level": 25,
    "unit_type": "A1",
    "buyer_is_bumi": True
})

print(f"Example 1: Local Bumi Buyer - Block B, Mid Floor")
print(f"  Base Price:  RM {result.base_price:,.0f}")
print(f"  Total Rebate: RM {result.total_rebate:,.0f}")
print(f"  Final Price: RM {result.final_price:,.0f}")
print(f"  Commission:  RM {result.total_commission:,.0f}")
print()

# Print breakdown
print("  Rebate Breakdown:")
for r in result.rebate_breakdown:
    print(f"    - {r.rule_name}: RM {r.calculated_amount:,.0f} ({r.value}%)")

print("\n  Commission Breakdown:")
for c in result.commission_breakdown:
    print(f"    - {c.rule_name}: RM {c.calculated_amount:,.0f} ({c.value}%)")
```

---

## Quick Reference Table

| Scenario | Block | Floor | Bumi | Unit | Final Rebate | Commission |
|----------|-------|-------|------|------|--------------|------------|
| Local Bumi Mid | B | 25 | Yes | A1 | ~20% | 5% |
| Local Non-Bumi | A | 15 | No | A2 | 6% | 2% |
| Foreign Low | B | 15 | No | B1 | 10% | 7%* |
| Garden Unit | B | 10 | Yes | A1 | ~14% | 3% |
| High Floor | B | 35 | No | A1 | 15% | 4% |

*Foreign commission calculated on (net price - RM200k package)
