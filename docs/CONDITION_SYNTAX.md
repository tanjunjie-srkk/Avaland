# Condition Syntax Guide

This document explains how rule conditions are written and parsed by the rule engine.

---

## Overview

Conditions are strings that define when a rule applies. They follow a simple, human-readable syntax:

```
IF <field> <operator> <value> [AND/OR <field> <operator> <value> ...]
```

**Example:**
```
IF block == 'B' AND floor_level >= 20 AND floor_level <= 29
```

---

## Syntax Reference

### Basic Structure

```
IF <condition_expression>
```

The `IF` prefix is optional but recommended for clarity.

### Supported Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `==` | Equal to | `block == 'A'` |
| `!=` | Not equal to | `buyer_type != 'foreign'` |
| `>=` | Greater than or equal | `floor_level >= 20` |
| `<=` | Less than or equal | `floor_level <= 29` |
| `>` | Greater than | `floor_level > 10` |
| `<` | Less than | `floor_level < 40` |

### Logical Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `AND` | Both conditions must be true | `block == 'B' AND floor_level >= 20` |
| `OR` | Either condition can be true | `is_garden_unit == True OR is_penthouse == True` |

### Value Types

| Type | Syntax | Example |
|------|--------|---------|
| String | Single quotes | `'A'`, `'local'`, `'foreign'` |
| String | Double quotes | `"A"`, `"local"` |
| Integer | No quotes | `20`, `100`, `0` |
| Float | Decimal | `3.5`, `0.05` |
| Boolean | True/False | `True`, `False` |

---

## Common Patterns

### 1. Simple Field Check

```
IF block == 'A'
```

Matches when the `block` field equals `'A'`.

### 2. Range Check

```
IF floor_level >= 20 AND floor_level <= 29
```

Matches floors 20 through 29 (inclusive).

### 3. Boolean Flag

```
IF buyer_is_bumi == True
```

Matches when the buyer is Bumiputera.

### 4. Compound Conditions

```
IF block == 'B' AND floor_level >= 11 AND floor_level <= 19
```

Matches Block B, floors 11-19.

### 5. Alternative Conditions

```
IF is_garden_unit == True OR is_penthouse == True
```

Matches either garden units or penthouses.

---

## Available Context Fields

These are the standard fields you can use in conditions:

| Field | Type | Description | Example Values |
|-------|------|-------------|----------------|
| `buyer_type` | string | Type of buyer | `'local'`, `'foreign'` |
| `block` | string | Building block | `'A'`, `'B'` |
| `floor_level` | integer | Floor number | `11`, `25`, `38` |
| `unit_type` | string | Unit type code | `'A1'`, `'A2'`, `'B1'`, `'B2'` |
| `buyer_is_bumi` | boolean | Is Bumiputera buyer | `True`, `False` |
| `is_garden_unit` | boolean | Is garden unit | `True`, `False` |
| `is_penthouse` | boolean | Is penthouse unit | `True`, `False` |
| `loan_purchase` | boolean | Using loan | `True`, `False` |
| `marketing_event` | boolean | During event | `True`, `False` |
| `referrer_category` | string | Referrer type | `'staff'`, `'agent'`, `'purchaser'` |

---

## How Parsing Works

The `ConditionParser` class converts condition strings into executable Python functions.

### Step 1: Clean the String

Remove the `IF` prefix:

```python
"IF block == 'A'" → "block == 'A'"
```

### Step 2: Tokenize Logical Operators

Split by AND/OR:

```python
"block == 'B' AND floor_level >= 20"
→ ["block == 'B'", "AND", "floor_level >= 20"]
```

### Step 3: Parse Each Comparison

Convert each comparison to a function:

```python
"block == 'B'" → lambda ctx: ctx.get('block') == 'B'
"floor_level >= 20" → lambda ctx: ctx.get('floor_level') >= 20
```

### Step 4: Combine with Logical Operators

```python
result = func1(context) AND func2(context)
```

---

## Code Example

```python
from condition_parser import ConditionParser

parser = ConditionParser()

# Parse a condition
evaluator = parser.parse("IF block == 'B' AND floor_level >= 20")

# Test against context
context1 = {"block": "B", "floor_level": 25}
print(evaluator(context1))  # True

context2 = {"block": "A", "floor_level": 25}
print(evaluator(context2))  # False

context3 = {"block": "B", "floor_level": 15}
print(evaluator(context3))  # False
```

---

## Error Handling

### Missing Fields

If a field is not in the context, the comparison returns `False`:

```python
condition = "IF block == 'B'"
context = {"floor_level": 25}  # No 'block' field
# Result: False
```

### Invalid Operators

Unsupported operators will cause parsing to fall back to boolean evaluation:

```python
condition = "IF block IN ['A', 'B']"  # 'IN' not supported
# This won't work as expected
```

### Type Mismatches

Comparing incompatible types (e.g., string to integer) returns `False` safely:

```python
condition = "IF floor_level == 'twenty'"
context = {"floor_level": 20}  # Integer vs string
# Result: False (types don't match)
```

---

## Best Practices

1. **Always quote strings**: Use `'A'` not `A`
2. **Use proper case for booleans**: `True` and `False` (capitalized)
3. **Keep conditions simple**: Complex logic is harder to debug
4. **Test conditions**: Use unit tests to verify matching
5. **Document conditions**: Add a `description` field explaining the rule

---

## Specificity Scoring

Conditions are scored for specificity to help with conflict resolution:

| Pattern | Score |
|---------|-------|
| Simple comparison | 0.3 |
| Two conditions with AND | 0.55 |
| Three conditions with AND | 0.7 |
| Four+ conditions with AND | 0.85 (max ~1.0) |

**Formula:**
```python
base_score = 0.2
and_bonus = count(' AND ') * 0.15
operator_bonus = count_operators() * 0.1
specificity = min(base_score + and_bonus + operator_bonus, 1.0)
```

More specific conditions get higher priority when resolving conflicts.
