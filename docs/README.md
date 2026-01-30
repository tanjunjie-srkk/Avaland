# Avaland Multi-Memo Rule Engine

## Project Overview

This project provides an intelligent rule engine for property pricing calculations. It extracts pricing rules from memo documents (commission rates, rebates, referrals, etc.) and applies them programmatically based on buyer context.

**Key Features:**
- Multi-memo support with conflict resolution
- Priority-based rule ranking
- Full traceability from calculations back to source memos
- Condition parsing with safe AST-based evaluation
- Support for temporal filtering (SPA date validity)

---

## Quick Start

```python
from multi_memo_engine import create_multi_memo_engine
from datetime import datetime

# Initialize the engine with your artifact folder
engine = create_multi_memo_engine("path/to/artifacts")

# Prepare rules with filtering
engine.retrieve_and_prepare(
    project_name="Aetas Seputeh",
    target_date=datetime(2025, 8, 15)
)

# Define buyer context
context = {
    "buyer_type": "local",       # 'local' or 'foreign'
    "block": "B",                # 'A' or 'B'
    "floor_level": 25,           # integer
    "unit_type": "A1",           # 'A1', 'A2', 'B1', 'B2', etc.
    "buyer_is_bumi": True,       # boolean
    "base_price": 1500000        # base unit price in RM
}

# Calculate pricing
result = engine.calculate(context)

print(f"Base Price: RM{result.base_price:,.0f}")
print(f"Total Rebate: RM{result.total_rebate:,.0f}")
print(f"Final Price: RM{result.final_price:,.0f}")
print(f"Commission: RM{result.total_commission:,.0f}")
```

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [Architecture Overview](./ARCHITECTURE.md) | System design and module relationships |
| [Rule Calculation Guide](./RULE_CALCULATION.md) | **Deep dive into calculation logic** |
| [Condition Syntax](./CONDITION_SYNTAX.md) | How rule conditions are parsed and evaluated |
| [Multi-Memo System](./MULTI_MEMO.md) | Memo management, filtering, and conflict resolution |
| [Data Schemas](./DATA_SCHEMAS.md) | JSON schema definitions for memos and rules |
| [API Reference](./API_REFERENCE.md) | Complete API documentation |

---

## Project Status

- ✅ Single-memo rule engine
- ✅ Multi-memo aggregation
- ✅ Conflict detection and resolution
- ✅ Priority ranking system
- ✅ Condition parsing (AND/OR, comparisons)
- 🔲 Rule extraction from PDF (in progress)
- 🔲 Web API layer
- 🔲 Admin dashboard

---
# BackLog

1. Error in rule generation
    -> Need to modify the prompt for rule generation
    -> Ask the agent to take note and clearly identify Units, Floor, Type, Block
    -> Refine the prompt so that every rules extracted is according to the correct condiiton (Never mix up units, type and block)
2. Futher Modification in Functionality
    ### UI
    -> Design a finance-want to see view for the calculation part
    -> Include the current calculation method shown in the general view part
    -> Inlucde the functionality that user can edit the rule after they review
    -> Allow user to upload the pdf and show the rule extraction process by mapping the rule with the section in the pdf (Rule Mapping Process)
    ### Functionality
    -> Make sure the rule precidency and priority is tranparent.
    -> Take note on the explicite priority, either given by the user or ask agent to define it based on certain criteria
    -> Define a proper way to track supersession of the memorandum 
    -> Solve the logical conflicts { If two non-conflicts appear together, need to handle either choose one or include all, when ?}
    -> Implement agent framework to orchestrate the process of agent, and further decompose the task for each agent to increase 
    -> Identified the cause of the error ( 2025 -> No conflicts, 2026 ( Supersedes memo)-> filter out but still involve 2025, output correct, process wrong)
    -> Take not the value or the calculation for the priority, recency, granularity, all this 
3. Task To DO
    -> Ask to clarify on the general category of rules, so that this can be used in implementation of the prompt for the agent (Generalization
       Can be used in rule extraction, and rule matching)




