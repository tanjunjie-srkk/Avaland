"""
Rule Matcher Module
Matches rules from the library against user context to find applicable rules.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from rule_loader import Rule, RuleLibrary
from multi_memo.condition_parser import ConditionParser


@dataclass
class MatchedRule:
    """Represents a rule that matched the given context."""
    rule: Rule
    matched_condition: Optional[Dict[str, Any]]
    match_score: float  # 0.0 to 1.0 indicating match quality
    
    @property
    def rule_id(self) -> str:
        return self.rule.rule_id
    
    @property
    def rule_name(self) -> str:
        return self.rule.rule_name
    
    @property
    def rule_type(self) -> str:
        return self.rule.rule_type
    
    def get_value(self, key: str, default: Any = None) -> Any:
        """Get a value from the matched condition."""
        if self.matched_condition:
            return self.matched_condition.get(key, default)
        return default
    
    def get_percentage(self) -> Optional[float]:
        """Get percentage value from matched condition (commission or rebate)."""
        if not self.matched_condition:
            return None
        
        for key in ['commission_percentage', 'rebate_percentage']:
            if key in self.matched_condition:
                return self.matched_condition[key]
        return None
    
    def get_amount(self) -> Optional[float]:
        """Get fixed amount from matched condition."""
        if not self.matched_condition:
            return None
        
        for key in ['adjustment_amount', 'reward_amount']:
            if key in self.matched_condition:
                return self.matched_condition[key]
        
        # Check raw data for referral rewards
        if 'reward_amount' in self.rule.raw_data:
            return self.rule.raw_data['reward_amount']
        
        return None


class RuleMatcher:
    """
    Matches rules against user context to find applicable rules.
    
    Supports multiple matching strategies:
    1. Exact condition matching - evaluates IF conditions
    2. Category filtering - filters by rule type, buyer type, etc.
    3. Scoring - ranks matches by specificity
    """
    
    def __init__(self, library: RuleLibrary):
        self.library = library
        self.parser = ConditionParser()
    
    def match(
        self, 
        context: Dict[str, Any],
        rule_types: Optional[List[str]] = None
    ) -> List[MatchedRule]:
        """
        Find all rules that match the given context.
        
        Args:
            context: User context dictionary with values like:
                {
                    "buyer_type": "local",
                    "block": "B",
                    "floor_level": 25,
                    "unit_type": "A1",
                    ...
                }
            rule_types: Optional list of rule types to filter by
                       (e.g., ['commission', 'rebate'])
        
        Returns:
            List of MatchedRule objects sorted by match score
        """
        matched = []
        
        # Get rules to evaluate
        if rule_types:
            rules = []
            for rt in rule_types:
                rules.extend(self.library.get_by_type(rt))
        else:
            rules = self.library.rules
        
        # Pre-filter by buyer type if specified in context
        buyer_type = context.get('buyer_type')
        if buyer_type:
            rules = [
                r for r in rules 
                if r.buyer_type is None or r.buyer_type == buyer_type
            ]
        
        # Evaluate each rule
        for rule in rules:
            match_result = self._evaluate_rule(rule, context)
            if match_result:
                matched.append(match_result)
        
        # Sort by score (highest first)
        matched.sort(key=lambda m: m.match_score, reverse=True)
        
        return matched
    
    def match_single(
        self, 
        context: Dict[str, Any],
        rule_type: str
    ) -> Optional[MatchedRule]:
        """
        Find the best matching rule of a specific type.
        
        Returns the highest-scoring match or None if no match.
        """
        matches = self.match(context, rule_types=[rule_type])
        return matches[0] if matches else None
    
    def match_all_applicable(
        self, 
        context: Dict[str, Any]
    ) -> Dict[str, List[MatchedRule]]:
        """
        Find all applicable rules organized by type.
        
        Returns:
            Dictionary with rule types as keys and lists of matches as values
        """
        all_matches = self.match(context)
        
        result: Dict[str, List[MatchedRule]] = {}
        for match in all_matches:
            if match.rule_type not in result:
                result[match.rule_type] = []
            result[match.rule_type].append(match)
        
        return result
    
    def _evaluate_rule(
        self, 
        rule: Rule, 
        context: Dict[str, Any]
    ) -> Optional[MatchedRule]:
        """
        Evaluate a single rule against the context.
        
        Returns MatchedRule if any condition matches, None otherwise.
        """
        if not rule.conditions:
            # Rules without conditions (like packages) match based on other criteria
            if rule.rule_type == 'package':
                return self._evaluate_package_rule(rule, context)
            elif rule.rule_type == 'referral':
                return self._evaluate_referral_rule(rule, context)
            return None
        
        # Find matching condition
        best_match = None
        best_score = 0.0
        
        for condition in rule.conditions:
            if not isinstance(condition, dict):
                continue
            
            condition_str = condition.get('condition')
            if not condition_str:
                continue
            
            try:
                evaluator = self.parser.parse(condition_str)
                if evaluator(context):
                    # Calculate specificity score
                    score = self._calculate_score(condition_str, context)
                    if score > best_score:
                        best_score = score
                        best_match = condition
            except Exception as e:
                # Log parsing errors but continue
                print(f"Warning: Failed to parse condition '{condition_str}': {e}")
                continue
        
        if best_match:
            return MatchedRule(
                rule=rule,
                matched_condition=best_match,
                match_score=best_score
            )
        
        return None
    
    def _evaluate_package_rule(
        self, 
        rule: Rule, 
        context: Dict[str, Any]
    ) -> Optional[MatchedRule]:
        """Evaluate package rules based on eligibility."""
        eligibility = rule.raw_data.get('eligibility', [])
        
        buyer_type = context.get('buyer_type', '')
        block = context.get('block', '')
        
        # Check eligibility conditions
        for elig in eligibility:
            elig_lower = elig.lower()
            if 'foreign' in elig_lower and buyer_type == 'foreign':
                return MatchedRule(rule=rule, matched_condition=None, match_score=0.5)
            if f'block {block.lower()}' in elig_lower:
                return MatchedRule(rule=rule, matched_condition=None, match_score=0.5)
        
        return None
    
    def _evaluate_referral_rule(
        self, 
        rule: Rule, 
        context: Dict[str, Any]
    ) -> Optional[MatchedRule]:
        """Evaluate referral rules based on referrer category."""
        referrer_category = context.get('referrer_category')
        
        if referrer_category and referrer_category == rule.referrer_category:
            return MatchedRule(
                rule=rule, 
                matched_condition=None, 
                match_score=0.8
            )
        
        return None
    
    def _calculate_score(
        self, 
        condition_str: str, 
        context: Dict[str, Any]
    ) -> float:
        """
        Calculate a specificity score for a matched condition.
        
        More specific conditions (more constraints) get higher scores.
        """
        # Count the number of conditions (AND clauses)
        and_count = condition_str.upper().count(' AND ')
        
        # Base score plus bonus for specificity
        score = 0.5 + (and_count * 0.1)
        
        # Cap at 1.0
        return min(score, 1.0)


def find_matching_rules(
    library: RuleLibrary, 
    context: Dict[str, Any],
    rule_types: Optional[List[str]] = None
) -> List[MatchedRule]:
    """
    Convenience function to find matching rules.
    
    Example:
        >>> library = load_rules('artifact/extracted-rules.json')
        >>> context = {"buyer_type": "local", "block": "B", "floor_level": 25}
        >>> matches = find_matching_rules(library, context, ['commission'])
    """
    matcher = RuleMatcher(library)
    return matcher.match(context, rule_types)
