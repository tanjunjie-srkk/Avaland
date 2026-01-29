"""
Test script for Multi-Memo Rule Engine
Demonstrates the full flow of multi-memo rule retrieval and calculation.
"""

import json
from datetime import datetime
from pathlib import Path
import sys
import io

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from memo_manager import MemoManager, MemoType
from rule_aggregator import RuleAggregator, ConflictResolution, PriorityRanker
from multi_memo_engine import MultiMemoRuleEngine, create_multi_memo_engine


def test_memo_loading():
    """Test loading memos from artifacts."""
    print("\n" + "=" * 60)
    print("TEST 1: MEMO LOADING")
    print("=" * 60)
    
    artifacts_path = Path(__file__).parent.parent / "artifact"
    manager = MemoManager(str(artifacts_path))
    count = manager.load_all_memos()
    
    print(f"\n✅ Loaded {count} memos")
    print(f"\nMemo Statistics:")
    stats = manager.get_statistics()
    print(json.dumps(stats, indent=2, default=str))
    
    # List all memos
    print(f"\nLoaded Memos:")
    for ref, memo in manager.memos.items():
        print(f"  - {ref}")
        print(f"    Project: {memo.metadata.project_name}")
        print(f"    Effective: {memo.metadata.effective_period}")
        print(f"    Rules: {len(memo.rules)}")
    
    return manager


def test_date_filtering(manager: MemoManager):
    """Test date-based filtering of memos."""
    print("\n" + "=" * 60)
    print("TEST 2: DATE FILTERING")
    print("=" * 60)
    
    # Test with a date in mid-2025
    test_date = datetime(2025, 8, 15)
    print(f"\nFiltering memos effective on: {test_date.strftime('%d %b %Y')}")
    
    filtered = manager.filter_by_date(test_date)
    print(f"✅ Found {len(filtered)} memos effective on this date:")
    for ref in filtered:
        memo = manager.memos[ref]
        print(f"  - {ref}: {memo.metadata.effective_period}")
    
    # Test with a date in 2026
    test_date_2026 = datetime(2026, 3, 15)
    print(f"\nFiltering memos effective on: {test_date_2026.strftime('%d %b %Y')}")
    
    filtered_2026 = manager.filter_by_date(test_date_2026)
    print(f"✅ Found {len(filtered_2026)} memos effective on this date:")
    for ref in filtered_2026:
        memo = manager.memos[ref]
        print(f"  - {ref}: {memo.metadata.effective_period}")


def test_project_filtering(manager: MemoManager):
    """Test project-based filtering of memos."""
    print("\n" + "=" * 60)
    print("TEST 3: PROJECT FILTERING")
    print("=" * 60)
    
    # Get all projects
    projects = manager.get_all_projects()
    print(f"\nAvailable Projects: {projects}")
    
    # Filter by project
    if projects:
        test_project = projects[0]
        print(f"\nFiltering memos for project: '{test_project}'")
        
        filtered = manager.filter_by_project(test_project)
        print(f"✅ Found {len(filtered)} memos for this project:")
        for ref in filtered:
            print(f"  - {ref}")
    
    # Test fuzzy matching
    print(f"\nFuzzy matching for 'Aetas':")
    fuzzy_filtered = manager.filter_by_project("Aetas", fuzzy_match=True)
    print(f"✅ Found {len(fuzzy_filtered)} memos")


def test_rule_aggregation(manager: MemoManager):
    """Test rule aggregation with conflict detection."""
    print("\n" + "=" * 60)
    print("TEST 4: RULE AGGREGATION & CONFLICT DETECTION")
    print("=" * 60)
    
    aggregator = RuleAggregator(manager)
    library = aggregator.aggregate(resolution_strategy=ConflictResolution.LATEST_WINS)
    
    print(f"\n✅ Aggregated {len(library.rules)} total rules")
    print(f"✅ Active rules: {len(library.get_active_rules())}")
    print(f"✅ Superseded rules: {len(library._superseded)}")
    
    # Show rule types
    print(f"\nRules by type:")
    for rule_type in library.get_all_types():
        rules = library.get_by_type(rule_type)
        print(f"  {rule_type}: {len(rules)} active rules")
    
    # Show conflicts
    conflicts_summary = library.get_conflicts_summary()
    print(f"\nConflict Summary:")
    print(json.dumps(conflicts_summary, indent=2))
    
    return aggregator, library


def test_priority_ranking(aggregator: RuleAggregator):
    """Test priority ranking of rules."""
    print("\n" + "=" * 60)
    print("TEST 5: PRIORITY RANKING")
    print("=" * 60)
    
    # Get priority ranking for commission rules
    ranking = aggregator.get_priority_ranking(rule_type='commission', top_n=10)
    
    print(f"\nTop Commission Rules by Priority:")
    print("-" * 60)
    
    for entry in ranking:
        print(f"\n  Rank {entry['rank']}: {entry['rule_name']}")
        print(f"    ID: {entry['composite_id']}")
        print(f"    Project: {entry['project']}")
        print(f"    Total Priority: {entry['total_priority']:.4f}")
        print(f"    Breakdown:")
        breakdown = entry['priority_breakdown']
        print(f"      - Recency: {breakdown['recency_score']:.4f}")
        print(f"      - Specificity: {breakdown['specificity_score']:.4f}")
        print(f"      - Explicit Priority: {breakdown['explicit_priority']}")
        if entry['is_superseded']:
            print(f"    ⚠️  SUPERSEDED by: {entry['superseded_by']}")
        if entry['conflicts_with']:
            print(f"    ⚠️  Conflicts: {entry['conflicts_with']}")


def test_full_calculation():
    """Test full multi-memo calculation flow."""
    print("\n" + "=" * 60)
    print("TEST 6: FULL MULTI-MEMO CALCULATION")
    print("=" * 60)
    
    artifacts_path = Path(__file__).parent.parent / "artifact"
    
    # Create engine
    engine = create_multi_memo_engine(str(artifacts_path))
    
    # Show statistics
    stats = engine.get_statistics()
    print(f"\nEngine Statistics:")
    print(json.dumps(stats, indent=2, default=str))
    
    # Prepare with project filter
    print("\n" + "-" * 60)
    print("Preparing rules for project 'Aetas Seputeh'...")
    engine.retrieve_and_prepare(
        project_name="Aetas Seputeh",
        target_date=datetime(2025, 8, 15),
        resolution_strategy=ConflictResolution.LATEST_WINS
    )
    
    # Test context
    context = {
        "buyer_type": "local",
        "block": "B",
        "floor_level": 25,
        "unit_type": "A1",
        "buyer_is_bumi": True,
        "base_price": 1500000
    }
    
    print(f"\nCalculating for context:")
    print(json.dumps(context, indent=2))
    
    # Get explanation first
    print("\n" + "-" * 60)
    print("RULE EXPLANATION:")
    print("-" * 60)
    explanation = engine.explain_rules(context)
    print(explanation)
    
    # Perform calculation
    print("\n" + "-" * 60)
    print("CALCULATION RESULT:")
    print("-" * 60)
    
    result = engine.calculate(
        context=context,
        project_name="Aetas Seputeh",
        spa_date="15 Aug 2025"
    )
    
    print(f"\n📊 PRICING SUMMARY")
    print(f"  Base Price:     RM{result.base_price:,.2f}")
    print(f"  Total Rebate:   RM{result.total_rebate:,.2f}")
    print(f"  Final Price:    RM{result.final_price:,.2f}")
    print(f"  Commission:     RM{result.total_commission:,.2f}")
    
    print(f"\n📁 SOURCE MEMOS:")
    for memo in result.source_memos:
        print(f"  - {memo}")
    
    print(f"\n📋 MATCHED RULES:")
    for rule_id in result.matched_rules:
        print(f"  - {rule_id}")
    
    if result.conflicts_detected:
        print(f"\n⚠️  CONFLICTS DETECTED:")
        for conflict in result.conflicts_detected:
            print(f"  - {conflict['description']}")
    
    print(f"\n📈 FILTERING STATISTICS:")
    print(f"  Memos considered: {result.memos_considered}")
    print(f"  After date filter: {result.memos_after_date_filter}")
    print(f"  After project filter: {result.memos_after_project_filter}")
    print(f"  Rules before resolution: {result.rules_before_conflict_resolution}")
    print(f"  Active rules: {result.rules_after_conflict_resolution}")
    
    # Export full result
    print("\n" + "-" * 60)
    print("FULL RESULT (JSON):")
    print("-" * 60)
    print(json.dumps(result.to_dict(), indent=2))
    
    return result


def test_conflict_scenarios():
    """Test specific conflict resolution scenarios."""
    print("\n" + "=" * 60)
    print("TEST 7: CONFLICT RESOLUTION SCENARIOS")
    print("=" * 60)
    
    artifacts_path = Path(__file__).parent.parent / "artifact"
    manager = MemoManager(str(artifacts_path))
    manager.load_all_memos()
    
    # Test different resolution strategies
    strategies = [
        ConflictResolution.LATEST_WINS,
        ConflictResolution.MOST_SPECIFIC,
        ConflictResolution.HIGHEST_PRIORITY
    ]
    
    for strategy in strategies:
        print(f"\n--- Strategy: {strategy.value} ---")
        aggregator = RuleAggregator(manager)
        library = aggregator.aggregate(resolution_strategy=strategy)
        
        conflicts = library.get_conflicts_summary()
        print(f"  Total conflicts: {conflicts['total_conflicts']}")
        print(f"  Requires review: {conflicts['requires_review']}")
        print(f"  Active rules: {len(library.get_active_rules())}")


def test_traceability():
    """Test rule-to-memo traceability."""
    print("\n" + "=" * 60)
    print("TEST 8: TRACEABILITY")
    print("=" * 60)
    
    artifacts_path = Path(__file__).parent.parent / "artifact"
    engine = create_multi_memo_engine(str(artifacts_path))
    engine.retrieve_and_prepare()
    
    # Get a specific rule and trace back to memo
    if engine.library:
        active_rules = engine.library.get_active_rules()
        if active_rules:
            sample_rule = active_rules[0]
            
            print(f"\nSample Rule Traceability:")
            print(f"  Rule ID: {sample_rule.rule_id}")
            print(f"  Composite ID: {sample_rule.composite_id}")
            print(f"  Rule Name: {sample_rule.rule_name}")
            print(f"  Rule Type: {sample_rule.rule_type}")
            print(f"\n  Memo Metadata:")
            if sample_rule.memo_metadata:
                print(f"    Reference: {sample_rule.memo_metadata.memo_reference}")
                print(f"    File: {sample_rule.memo_metadata.memo_file}")
                print(f"    Project: {sample_rule.memo_metadata.project_name}")
                print(f"    Effective Period: {sample_rule.memo_metadata.effective_period}")
                print(f"    Memo Type: {sample_rule.memo_metadata.memo_type.value}")
                print(f"    Priority: {sample_rule.memo_metadata.priority}")
            
            print(f"\n  Priority Scores:")
            print(f"    Recency: {sample_rule.recency_score:.4f}")
            print(f"    Specificity: {sample_rule.specificity_score:.4f}")
            print(f"    Total: {sample_rule.get_total_priority():.4f}")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("MULTI-MEMO RULE ENGINE TEST SUITE")
    print("=" * 60)
    
    try:
        # Test 1: Memo Loading
        manager = test_memo_loading()
        
        # Test 2: Date Filtering
        test_date_filtering(manager)
        
        # Test 3: Project Filtering
        test_project_filtering(manager)
        
        # Test 4: Rule Aggregation
        aggregator, library = test_rule_aggregation(manager)
        
        # Test 5: Priority Ranking
        test_priority_ranking(aggregator)
        
        # Test 6: Full Calculation
        test_full_calculation()
        
        # Test 7: Conflict Scenarios
        test_conflict_scenarios()
        
        # Test 8: Traceability
        test_traceability()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
