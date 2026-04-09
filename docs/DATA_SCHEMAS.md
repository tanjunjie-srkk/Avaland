# Data Schemas

This document defines the JSON schemas for memos, rules, and API responses.

---

## Table of Contents

1. [Memo Schema](#memo-schema)
2. [Rule Schemas by Type](#rule-schemas-by-type)
3. [Calculation Result Schema](#calculation-result-schema)
4. [Context Input Schema](#context-input-schema)

---

## Memo Schema

The top-level schema for extracted memo JSON files.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ExtractedMemo",
  "type": "object",
  "required": ["memo_reference", "effective_period", "project_name", "rules"],
  "properties": {
    "memo_reference": {
      "type": "string",
      "description": "Unique identifier for the memo",
      "example": "AVALUX-AD-MEMO-SM-2025-009"
    },
    "effective_period": {
      "type": "object",
      "required": ["start_date"],
      "properties": {
        "start_date": {
          "type": "string",
          "description": "Start date (format: DD MMM YYYY)",
          "example": "15 Jun 2025"
        },
        "end_date": {
          "type": "string",
          "description": "End date (format: DD MMM YYYY)",
          "example": "31 Dec 2025"
        }
      }
    },
    "project_name": {
      "type": "string",
      "description": "Project this memo belongs to",
      "example": "Aetas Seputeh"
    },
    "memo_type": {
      "type": "string",
      "enum": ["standard", "superseding", "addendum", "amendment"],
      "default": "standard"
    },
    "supersedes": {
      "type": ["string", "null"],
      "description": "Reference of memo this supersedes",
      "example": "AVALUX-AD-MEMO-SM-2024-005"
    },
    "priority": {
      "type": "integer",
      "minimum": 0,
      "maximum": 10,
      "default": 5,
      "description": "Explicit priority (higher = more important)"
    },
    "rules": {
      "type": "object",
      "properties": {
        "commission_rules": { "type": "array", "items": { "$ref": "#/definitions/CommissionRule" } },
        "rebate_rules": { "type": "array", "items": { "$ref": "#/definitions/RebateRule" } },
        "referral_rules": { "type": "array", "items": { "$ref": "#/definitions/ReferralRule" } },
        "price_adjustment_rules": { "type": "array", "items": { "$ref": "#/definitions/PriceAdjustmentRule" } },
        "package_rules": { "type": "array", "items": { "$ref": "#/definitions/PackageRule" } }
      }
    },
    "extraction_confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "AI extraction confidence score"
    },
    "warnings": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Extraction warnings or notes"
    }
  }
}
```

---

## Rule Schemas by Type

### Commission Rule

```json
{
  "title": "CommissionRule",
  "type": "object",
  "required": ["rule_id", "rule_name", "conditions"],
  "properties": {
    "rule_id": {
      "type": "string",
      "pattern": "^COM_\\d{3}$",
      "example": "COM_001"
    },
    "rule_name": {
      "type": "string",
      "example": "Local Buyer Commission – Block A"
    },
    "buyer_type": {
      "type": "string",
      "enum": ["local", "foreign"],
      "description": "Filter for buyer type"
    },
    "conditions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["condition", "commission_percentage"],
        "properties": {
          "condition": {
            "type": "string",
            "description": "Condition expression",
            "example": "IF block == 'A'"
          },
          "commission_percentage": {
            "type": "number",
            "minimum": 0,
            "maximum": 100,
            "example": 2.0
          },
          "description": {
            "type": "string",
            "example": "Applicable to all levels in Block A"
          }
        }
      }
    },
    "notes": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

### Rebate Rule

```json
{
  "title": "RebateRule",
  "type": "object",
  "required": ["rule_id", "rule_name", "conditions"],
  "properties": {
    "rule_id": {
      "type": "string",
      "pattern": "^REB_\\d{3}$",
      "example": "REB_001"
    },
    "rule_name": {
      "type": "string",
      "example": "Bumi Rebate"
    },
    "rebate_type": {
      "type": "string",
      "enum": ["bumi", "standard", "special", "additional"],
      "description": "Type of rebate for ordering"
    },
    "conditions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["condition", "rebate_percentage"],
        "properties": {
          "condition": {
            "type": "string",
            "example": "IF buyer_is_bumi == True"
          },
          "rebate_percentage": {
            "type": "number",
            "minimum": 0,
            "maximum": 100,
            "example": 5.0
          },
          "description": {
            "type": "string",
            "example": "Applicable to all eligible Bumi buyers"
          }
        }
      }
    },
    "calculation_base": {
      "type": "string",
      "enum": ["Net Price", "Net Price after Bumi Rebate"],
      "default": "Net Price",
      "description": "Base price for percentage calculation"
    },
    "notes": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

### Referral Rule

```json
{
  "title": "ReferralRule",
  "type": "object",
  "required": ["rule_id", "rule_name", "referrer_category"],
  "properties": {
    "rule_id": {
      "type": "string",
      "pattern": "^REF_\\d{3}$",
      "example": "REF_001"
    },
    "rule_name": {
      "type": "string",
      "example": "Staff Referral Reward"
    },
    "referrer_category": {
      "type": "string",
      "enum": ["staff", "purchaser", "external_agent", "business_partner"],
      "example": "staff"
    },
    "reward_amount": {
      "type": "number",
      "description": "Fixed reward amount in RM",
      "example": 5000
    },
    "reward_percentage": {
      "type": "number",
      "description": "Percentage reward (alternative to fixed amount)"
    },
    "conditions": {
      "type": "array",
      "items": { "type": "object" }
    },
    "notes": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

### Price Adjustment Rule

```json
{
  "title": "PriceAdjustmentRule",
  "type": "object",
  "required": ["rule_id", "rule_name", "conditions"],
  "properties": {
    "rule_id": {
      "type": "string",
      "pattern": "^ADJ_\\d{3}$",
      "example": "ADJ_001"
    },
    "rule_name": {
      "type": "string",
      "example": "Garden Unit Premium"
    },
    "adjustment_type": {
      "type": "string",
      "enum": ["premium", "discount"],
      "description": "Whether this adds or subtracts from price"
    },
    "conditions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["condition", "adjustment_amount"],
        "properties": {
          "condition": {
            "type": "string",
            "example": "IF is_garden_unit == True"
          },
          "adjustment_amount": {
            "type": "number",
            "description": "Fixed amount to add/subtract",
            "example": 50000
          },
          "description": {
            "type": "string"
          }
        }
      }
    },
    "notes": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

### Package Rule

```json
{
  "title": "PackageRule",
  "type": "object",
  "required": ["rule_id", "rule_name"],
  "properties": {
    "rule_id": {
      "type": "string",
      "pattern": "^PKG_\\d{3}$",
      "example": "PKG_001"
    },
    "rule_name": {
      "type": "string",
      "example": "Partially Furnished Package"
    },
    "package_type": {
      "type": "string",
      "example": "furnishing"
    },
    "package_value": {
      "type": "number",
      "description": "Value of the package in RM",
      "example": 200000
    },
    "eligibility": {
      "type": "array",
      "items": { "type": "string" },
      "example": ["All Foreign Buyers", "Block B Units"]
    },
    "inclusions": {
      "type": "array",
      "items": { "type": "string" },
      "description": "What's included in the package"
    },
    "notes": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

---

## Context Input Schema

The context object passed to `calculate()`:

```json
{
  "title": "CalculationContext",
  "type": "object",
  "required": ["base_price"],
  "properties": {
    "base_price": {
      "type": "number",
      "description": "Base/list price of the unit in RM",
      "example": 1500000
    },
    "buyer_type": {
      "type": "string",
      "enum": ["local", "foreign"],
      "default": "local"
    },
    "block": {
      "type": "string",
      "enum": ["A", "B"],
      "example": "B"
    },
    "floor_level": {
      "type": "integer",
      "minimum": 1,
      "example": 25
    },
    "unit_type": {
      "type": "string",
      "enum": ["A1", "A2", "B1", "B2"],
      "example": "A1"
    },
    "buyer_is_bumi": {
      "type": "boolean",
      "default": false
    },
    "is_garden_unit": {
      "type": "boolean",
      "default": false
    },
    "is_penthouse": {
      "type": "boolean",
      "default": false
    },
    "loan_purchase": {
      "type": "boolean",
      "default": false
    },
    "marketing_event": {
      "type": "boolean",
      "default": false
    },
    "referrer_category": {
      "type": "string",
      "enum": ["staff", "purchaser", "external_agent", "business_partner"]
    }
  }
}
```

---

## Calculation Result Schema

The response from `calculate()`:

```json
{
  "title": "MultiMemoPricingResult",
  "type": "object",
  "properties": {
    "pricing": {
      "type": "object",
      "properties": {
        "base_price": { "type": "number" },
        "final_price": { "type": "number" },
        "total_rebate": { "type": "number" },
        "total_commission": { "type": "number" }
      }
    },
    "breakdown": {
      "type": "object",
      "properties": {
        "rebates": {
          "type": "array",
          "items": { "$ref": "#/definitions/CalculationItem" }
        },
        "commissions": {
          "type": "array",
          "items": { "$ref": "#/definitions/CalculationItem" }
        },
        "price_adjustments": {
          "type": "array",
          "items": { "$ref": "#/definitions/CalculationItem" }
        },
        "packages": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "traceability": {
      "type": "object",
      "properties": {
        "matched_rules": {
          "type": "array",
          "items": { "type": "string" }
        },
        "source_memos": {
          "type": "array",
          "items": { "type": "string" }
        },
        "conflicts": {
          "type": "array",
          "items": { "type": "object" }
        }
      }
    },
    "context": {
      "type": "object",
      "properties": {
        "target_project": { "type": "string" },
        "spa_date": { "type": "string" }
      }
    },
    "statistics": {
      "type": "object",
      "properties": {
        "memos_considered": { "type": "integer" },
        "memos_after_date_filter": { "type": "integer" },
        "memos_after_project_filter": { "type": "integer" },
        "rules_before_conflict_resolution": { "type": "integer" },
        "rules_after_conflict_resolution": { "type": "integer" }
      }
    }
  }
}
```

### Calculation Item

```json
{
  "title": "CalculationItem",
  "type": "object",
  "properties": {
    "rule_type": { "type": "string" },
    "rule_id": { "type": "string" },
    "composite_id": { "type": "string" },
    "rule_name": { "type": "string" },
    "description": { "type": "string" },
    "value": { "type": "number" },
    "value_type": { 
      "type": "string", 
      "enum": ["percentage", "fixed"] 
    },
    "calculated_amount": { "type": "number" },
    "details": { "type": "object" },
    "traceability": {
      "type": "object",
      "properties": {
        "memo_reference": { "type": "string" },
        "memo_file": { "type": "string" },
        "project_name": { "type": "string" },
        "effective_period": { "type": "object" }
      }
    },
    "priority_score": { "type": "number" },
    "conflicts": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

---

## Date Formats

Supported date formats for `effective_period` and `spa_date`:

| Format | Example |
|--------|---------|
| `DD MMM YYYY` | `15 Jun 2025` (Preferred) |
| `DD-MM-YYYY` | `15-06-2025` |
| `YYYY-MM-DD` | `2025-06-15` |
| `DD/MM/YYYY` | `15/06/2025` |
| `Month DD, YYYY` | `June 15, 2025` |
