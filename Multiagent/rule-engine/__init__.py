"""
Rule Engine Package
A rule matching and calculation engine for property pricing rules.
Supports both single-memo and multi-memo workflows.
"""

# Core rule engine (single memo)
from .multi_memo.condition_parser import ConditionParser, parse_condition
from .single_memo.rule_loader import Rule, RuleLibrary, RuleLoader, load_rules
from .single_memo.rule_matcher import RuleMatcher, MatchedRule, find_matching_rules
from .multi_memo.rule_engine import RuleEngine, CalculationResult, PricingResult, create_engine

# Multi-memo support
from .multi_memo.memo_manager import (
    MemoType,
    MemoMetadata,
    EnhancedRule,
    Memo,
    MemoManager
)
from .multi_memo.rule_aggregator import (
    ConflictType,
    ConflictResolution,
    RuleConflict,
    AggregatedRuleLibrary,
    RuleAggregator,
    PriorityRanker
)
from .multi_memo.multi_memo_engine import (
    MatchedEnhancedRule,
    MultiMemoCalculationResult,
    MultiMemoPricingResult,
    EnhancedRuleMatcher,
    MultiMemoRuleEngine,
    create_multi_memo_engine
)

__all__ = [
    # Condition Parser
    'ConditionParser',
    'parse_condition',
    
    # Rule Loader
    'Rule',
    'RuleLibrary', 
    'RuleLoader',
    'load_rules',
    
    # Rule Matcher
    'RuleMatcher',
    'MatchedRule',
    'find_matching_rules',
    
    # Rule Engine
    'RuleEngine',
    'CalculationResult',
    'PricingResult',
    'create_engine',
    
    # Multi-Memo Support
    'MemoType',
    'MemoMetadata',
    'EnhancedRule',
    'Memo',
    'MemoManager',
    'ConflictType',
    'ConflictResolution',
    'RuleConflict',
    'AggregatedRuleLibrary',
    'RuleAggregator',
    'PriorityRanker',
    'MatchedEnhancedRule',
    'MultiMemoCalculationResult',
    'MultiMemoPricingResult',
    'EnhancedRuleMatcher',
    'MultiMemoRuleEngine',
    'create_multi_memo_engine',
]
