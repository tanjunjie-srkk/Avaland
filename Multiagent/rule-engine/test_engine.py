"""
Test script for the Rule Engine.
Demonstrates how to use the rule engine for rule matching and calculations.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from rule_engine import RuleEngine, create_engine
from rule_loader import load_rules
from rule_matcher import RuleMatcher
from condition_parser import ConditionParser


def test_condition_parser():
    """Test the condition parser with various conditions."""
    print("\n" + "="*60)
    print("TESTING CONDITION PARSER")
    print("="*60)
    
    parser = ConditionParser()
    
    test_cases = [
        # (condition, context, expected_result)
        (
            "IF block == 'A'",
            {"block": "A"},
            True
        ),
        (
            "IF block == 'B' AND floor_level >= 20 AND floor_level <= 29",
            {"block": "B", "floor_level": 25},
            True
        ),
        (
            "IF block == 'B' AND floor_level >= 20 AND floor_level <= 29",
            {"block": "B", "floor_level": 15},
            False
        ),
        (
            "IF buyer_type == 'foreign' AND block == 'B'",
            {"buyer_type": "foreign", "block": "B"},
            True
        ),
        (
            "IF is_garden_unit == True OR is_penthouse == True",
            {"is_garden_unit": False, "is_penthouse": True},
            True
        ),
        (
            "IF buyer_is_bumi == True",
            {"buyer_is_bumi": True},
            True
        ),
    ]
    
    for condition, context, expected in test_cases:
        evaluator = parser.parse(condition)
        result = evaluator(context)
        status = "✓" if result == expected else "✗"
        print(f"\n{status} Condition: {condition}")
        print(f"   Context: {context}")
        print(f"   Expected: {expected}, Got: {result}")


def test_rule_loading():
    """Test loading rules from JSON."""
    print("\n" + "="*60)
    print("TESTING RULE LOADER")
    print("="*60)
    
    rules_path = Path(__file__).parent.parent / "artifact" / "extracted-rules.json"
    
    if not rules_path.exists():
        print(f"Rules file not found: {rules_path}")
        return None
    
    library = load_rules(str(rules_path))
    
    print(f"\nLoaded {len(library.rules)} rules")
    print(f"Rule types: {library.get_all_types()}")
    
    for rule_type in library.get_all_types():
        rules = library.get_by_type(rule_type)
        print(f"\n{rule_type.upper()} ({len(rules)} rules):")
        for rule in rules:
            print(f"  - {rule.rule_id}: {rule.rule_name}")
    
    return library


def test_rule_matching(library):
    """Test rule matching with various contexts."""
    print("\n" + "="*60)
    print("TESTING RULE MATCHER")
    print("="*60)
    
    if not library:
        print("No library to test with")
        return
    
    matcher = RuleMatcher(library)
    
    test_contexts = [
        {
            "name": "Local Buyer - Block A",
            "context": {
                "buyer_type": "local",
                "block": "A",
                "floor_level": 15,
                "unit_type": "A1",
                "buyer_is_bumi": False
            }
        },
        {
            "name": "Local Buyer - Block B Low Floor",
            "context": {
                "buyer_type": "local",
                "block": "B",
                "floor_level": 15,
                "unit_type": "B1",
                "buyer_is_bumi": True
            }
        },
        {
            "name": "Local Buyer - Block B High Floor",
            "context": {
                "buyer_type": "local",
                "block": "B",
                "floor_level": 35,
                "unit_type": "A2",
                "buyer_is_bumi": False
            }
        },
        {
            "name": "Foreign Buyer - Block B",
            "context": {
                "buyer_type": "foreign",
                "block": "B",
                "floor_level": 25,
                "unit_type": "A1",
                "buyer_is_bumi": False
            }
        },
        {
            "name": "Penthouse Buyer",
            "context": {
                "buyer_type": "local",
                "block": "B",
                "floor_level": 38,
                "is_penthouse": True,
                "buyer_is_bumi": False
            }
        }
    ]
    
    for test in test_contexts:
        print(f"\n{'─'*50}")
        print(f"Scenario: {test['name']}")
        print(f"Context: {test['context']}")
        print(f"{'─'*50}")
        
        matches = matcher.match_all_applicable(test['context'])
        
        for rule_type, matched_rules in matches.items():
            print(f"\n  {rule_type.upper()}:")
            for match in matched_rules:
                pct = match.get_percentage()
                amt = match.get_amount()
                value_str = f"{pct}%" if pct else f"RM{amt:,.0f}" if amt else "N/A"
                print(f"    ✓ {match.rule_name}: {value_str}")


def test_full_calculation():
    """Test full pricing calculation."""
    print("\n" + "="*60)
    print("TESTING FULL CALCULATION")
    print("="*60)
    
    rules_path = Path(__file__).parent.parent / "artifact" / "extracted-rules.json"
    
    if not rules_path.exists():
        print(f"Rules file not found: {rules_path}")
        return
    
    engine = create_engine(str(rules_path))
    
    # Test scenario: Local Bumi buyer, Block B, mid-floor
    context = {
        "buyer_type": "local",
        "block": "B",
        "floor_level": 25,
        "unit_type": "A1",
        "buyer_is_bumi": True,
        "is_garden_unit": False,
        "is_penthouse": False,
        "base_price": 1_500_000  # RM 1.5 million
    }
    
    print(f"\nScenario: Local Bumi Buyer - Block B Mid Floor")
    print(f"Base Price: RM {context['base_price']:,.0f}")
    print(f"\nContext: {context}")
    
    # Get explanation
    print("\n" + engine.explain_rules(context))
    
    # Calculate
    result = engine.calculate(context)
    
    print("\n" + "="*50)
    print("CALCULATION RESULTS")
    print("="*50)
    
    print(f"\nBase Price:       RM {result.base_price:>15,.2f}")
    
    if result.rebate_breakdown:
        print(f"\nRebates:")
        for rebate in result.rebate_breakdown:
            print(f"  - {rebate.rule_name}: RM {rebate.calculated_amount:>12,.2f} ({rebate.value}%)")
    
    print(f"\nTotal Rebate:     RM {result.total_rebate:>15,.2f}")
    print(f"Final Price:      RM {result.final_price:>15,.2f}")
    
    if result.commission_breakdown:
        print(f"\nCommissions:")
        for comm in result.commission_breakdown:
            print(f"  - {comm.rule_name}: RM {comm.calculated_amount:>12,.2f} ({comm.value}%)")
            if comm.details:
                print(f"    Payout SPA:     RM {comm.details.get('payout_spa', 0):>12,.2f}")
                print(f"    Payout Stage2A: RM {comm.details.get('payout_stage2a', 0):>12,.2f}")
    
    print(f"\nTotal Commission: RM {result.total_commission:>15,.2f}")
    
    print(f"\nMatched Rules: {result.matched_rules}")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("RULE ENGINE TEST SUITE")
    print("="*60)
    
    # Test 1: Condition Parser
    test_condition_parser()
    
    # Test 2: Rule Loading
    library = test_rule_loading()
    
    # Test 3: Rule Matching
    test_rule_matching(library)
    
    # Test 4: Full Calculation
    test_full_calculation()
    
    print("\n" + "="*60)
    print("ALL TESTS COMPLETED")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
