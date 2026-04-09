"""
Rule Loader Module
Loads rules from JSON and creates indexed structures for efficient lookup.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class Rule:
    """Represents a single rule with its metadata and conditions."""
    rule_id: str
    rule_name: str
    rule_type: str  # commission, rebate, referral, price_adjustment, package
    conditions: List[Dict[str, Any]]
    raw_data: Dict[str, Any]
    
    # Optional fields based on rule type
    buyer_type: Optional[str] = None
    rebate_type: Optional[str] = None
    referrer_category: Optional[str] = None
    adjustment_type: Optional[str] = None
    package_type: Optional[str] = None
    
    def get_applicable_condition(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find the first condition that matches the given context.
        Returns the condition dict with its parameters (percentage, amount, etc.)
        """
        from multi_memo.condition_parser import ConditionParser
        parser = ConditionParser()
        
        for condition in self.conditions:
            if isinstance(condition, dict) and 'condition' in condition:
                evaluator = parser.parse(condition['condition'])
                if evaluator(context):
                    return condition
            elif isinstance(condition, str):
                # Simple string condition (like referral conditions)
                # These are informational, not evaluable
                continue
        
        return None


@dataclass
class RuleLibrary:
    """Container for all rules with indexing for fast lookup."""
    rules: List[Rule] = field(default_factory=list)
    
    # Indexes for fast lookup
    _by_id: Dict[str, Rule] = field(default_factory=dict)
    _by_type: Dict[str, List[Rule]] = field(default_factory=dict)
    _by_buyer_type: Dict[str, List[Rule]] = field(default_factory=dict)
    
    def add_rule(self, rule: Rule):
        """Add a rule to the library and update indexes."""
        self.rules.append(rule)
        
        # Index by ID
        self._by_id[rule.rule_id] = rule
        
        # Index by type
        if rule.rule_type not in self._by_type:
            self._by_type[rule.rule_type] = []
        self._by_type[rule.rule_type].append(rule)
        
        # Index by buyer type
        if rule.buyer_type:
            if rule.buyer_type not in self._by_buyer_type:
                self._by_buyer_type[rule.buyer_type] = []
            self._by_buyer_type[rule.buyer_type].append(rule)
    
    def get_by_id(self, rule_id: str) -> Optional[Rule]:
        """Get a rule by its ID."""
        return self._by_id.get(rule_id)
    
    def get_by_type(self, rule_type: str) -> List[Rule]:
        """Get all rules of a specific type."""
        return self._by_type.get(rule_type, [])
    
    def get_by_buyer_type(self, buyer_type: str) -> List[Rule]:
        """Get all rules for a specific buyer type."""
        return self._by_buyer_type.get(buyer_type, [])
    
    def get_all_types(self) -> List[str]:
        """Get all available rule types."""
        return list(self._by_type.keys())
    
    def search(
        self, 
        rule_type: Optional[str] = None,
        buyer_type: Optional[str] = None
    ) -> List[Rule]:
        """Search for rules with optional filters."""
        results = self.rules
        
        if rule_type:
            results = [r for r in results if r.rule_type == rule_type]
        
        if buyer_type:
            results = [r for r in results if r.buyer_type == buyer_type or r.buyer_type is None]
        
        return results


class RuleLoader:
    """Loads and parses rules from JSON files."""
    
    def __init__(self, rules_path: str):
        self.rules_path = Path(rules_path)
        self.raw_data: Dict[str, Any] = {}
        self.library = RuleLibrary()
    
    def load(self) -> RuleLibrary:
        """Load rules from JSON file and return a RuleLibrary."""
        with open(self.rules_path, 'r', encoding='utf-8') as f:
            self.raw_data = json.load(f)
        
        rules_section = self.raw_data.get('rules', {})
        
        # Load each rule category
        self._load_commission_rules(rules_section.get('commission_rules', []))
        self._load_rebate_rules(rules_section.get('rebate_rules', []))
        self._load_referral_rules(rules_section.get('referral_rules', []))
        self._load_price_adjustment_rules(rules_section.get('price_adjustment_rules', []))
        self._load_package_rules(rules_section.get('package_rules', []))
        
        return self.library
    
    def _load_commission_rules(self, rules_data: List[Dict]):
        """Load commission rules."""
        for rule_data in rules_data:
            rule = Rule(
                rule_id=rule_data['rule_id'],
                rule_name=rule_data['rule_name'],
                rule_type='commission',
                conditions=rule_data.get('conditions', []),
                raw_data=rule_data,
                buyer_type=rule_data.get('buyer_type')
            )
            self.library.add_rule(rule)
    
    def _load_rebate_rules(self, rules_data: List[Dict]):
        """Load rebate rules."""
        for rule_data in rules_data:
            rule = Rule(
                rule_id=rule_data['rule_id'],
                rule_name=rule_data['rule_name'],
                rule_type='rebate',
                conditions=rule_data.get('conditions', []),
                raw_data=rule_data,
                rebate_type=rule_data.get('rebate_type')
            )
            self.library.add_rule(rule)
    
    def _load_referral_rules(self, rules_data: List[Dict]):
        """Load referral rules."""
        for rule_data in rules_data:
            # Referral rules have different condition structure
            conditions = rule_data.get('conditions', [])
            # Convert string conditions to dict format for consistency
            if conditions and isinstance(conditions[0], str):
                conditions = [{'description': c} for c in conditions]
            
            rule = Rule(
                rule_id=rule_data['rule_id'],
                rule_name=rule_data['rule_name'],
                rule_type='referral',
                conditions=conditions,
                raw_data=rule_data,
                referrer_category=rule_data.get('referrer_category')
            )
            self.library.add_rule(rule)
    
    def _load_price_adjustment_rules(self, rules_data: List[Dict]):
        """Load price adjustment rules."""
        for rule_data in rules_data:
            rule = Rule(
                rule_id=rule_data['rule_id'],
                rule_name=rule_data['rule_name'],
                rule_type='price_adjustment',
                conditions=rule_data.get('conditions', []),
                raw_data=rule_data,
                adjustment_type=rule_data.get('adjustment_type')
            )
            self.library.add_rule(rule)
    
    def _load_package_rules(self, rules_data: List[Dict]):
        """Load package rules."""
        for rule_data in rules_data:
            rule = Rule(
                rule_id=rule_data['rule_id'],
                rule_name=rule_data['rule_name'],
                rule_type='package',
                conditions=[],  # Package rules don't have conditions
                raw_data=rule_data,
                package_type=rule_data.get('package_type')
            )
            self.library.add_rule(rule)
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get memo metadata from the loaded rules."""
        return {
            'memo_reference': self.raw_data.get('memo_reference'),
            'effective_period': self.raw_data.get('effective_period'),
            'project_name': self.raw_data.get('project_name'),
            'extraction_confidence': self.raw_data.get('extraction_confidence'),
            'warnings': self.raw_data.get('warnings', [])
        }


def load_rules(rules_path: str) -> RuleLibrary:
    """
    Convenience function to load rules from a JSON file.
    
    Example:
        >>> library = load_rules('artifact/extracted-rules.json')
        >>> commission_rules = library.get_by_type('commission')
    """
    loader = RuleLoader(rules_path)
    return loader.load()
