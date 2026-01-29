"""
Multi-Memo Rule Engine Module
Orchestrates the full multi-memo rule retrieval, ranking, matching, and calculation flow.
Provides traceability from calculations back to source memos.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

from memo_manager import xMemoManager, Memo, MemoMetadata, EnhancedRule, MemoType
from rule_aggregator import (
    RuleAggregator, 
    AggregatedRuleLibrary, 
    PriorityRanker,
    ConflictResolution,
    ConflictType,
    RuleConflict
)
from condition_parser import ConditionParser


@dataclass
class MatchedEnhancedRule:
    """Represents a matched rule with enhanced memo traceability."""
    rule: EnhancedRule
    matched_condition: Optional[Dict[str, Any]]
    match_score: float
    priority_score: float
    
    @property
    def rule_id(self) -> str:
        return self.rule.rule_id
    
    @property
    def composite_id(self) -> str:
        return self.rule.composite_id
    
    @property
    def rule_name(self) -> str:
        return self.rule.rule_name
    
    @property
    def rule_type(self) -> str:
        return self.rule.rule_type
    
    @property
    def memo_reference(self) -> Optional[str]:
        return self.rule.memo_metadata.memo_reference if self.rule.memo_metadata else None
    
    @property
    def project_name(self) -> str:
        return self.rule.project_name
    
    def get_value(self, key: str, default: Any = None) -> Any:
        """Get a value from the matched condition."""
        if self.matched_condition:
            return self.matched_condition.get(key, default)
        return default
    
    def get_percentage(self) -> Optional[float]:
        """Get percentage value from matched condition."""
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
        if 'reward_amount' in self.rule.raw_data:
            return self.rule.raw_data['reward_amount']
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'rule_id': self.rule_id,
            'composite_id': self.composite_id,
            'rule_name': self.rule_name,
            'rule_type': self.rule_type,
            'match_score': self.match_score,
            'priority_score': self.priority_score,
            'combined_score': self.match_score * 0.5 + self.priority_score * 0.5,
            'matched_condition': self.matched_condition,
            'memo': {
                'reference': self.memo_reference,
                'project': self.project_name,
                'effective_period': self.rule.memo_metadata.effective_period if self.rule.memo_metadata else None
            }
        }


@dataclass
class MultiMemoCalculationResult:
    """Result of a calculation with full memo traceability."""
    rule_type: str
    rule_id: str
    composite_id: str
    rule_name: str
    description: str
    value: float
    value_type: str
    calculated_amount: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)
    
    # Enhanced memo traceability
    memo_reference: Optional[str] = None
    memo_file: Optional[str] = None
    project_name: Optional[str] = None
    effective_period: Optional[Dict[str, str]] = None
    priority_score: float = 0.0
    
    # Conflict information
    conflicts: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'rule_type': self.rule_type,
            'rule_id': self.rule_id,
            'composite_id': self.composite_id,
            'rule_name': self.rule_name,
            'description': self.description,
            'value': self.value,
            'value_type': self.value_type,
            'calculated_amount': self.calculated_amount,
            'details': self.details,
            'traceability': {
                'memo_reference': self.memo_reference,
                'memo_file': self.memo_file,
                'project_name': self.project_name,
                'effective_period': self.effective_period
            },
            'priority_score': self.priority_score,
            'conflicts': self.conflicts
        }


@dataclass
class MultiMemoPricingResult:
    """Complete pricing result from multi-memo calculation."""
    base_price: float
    final_price: float
    total_rebate: float
    total_commission: float
    
    rebate_breakdown: List[MultiMemoCalculationResult] = field(default_factory=list)
    commission_breakdown: List[MultiMemoCalculationResult] = field(default_factory=list)
    price_adjustments: List[MultiMemoCalculationResult] = field(default_factory=list)
    applicable_packages: List[str] = field(default_factory=list)
    
    # Multi-memo context
    matched_rules: List[str] = field(default_factory=list)
    source_memos: List[str] = field(default_factory=list)
    conflicts_detected: List[Dict[str, Any]] = field(default_factory=list)
    
    # Query context
    target_project: Optional[str] = None
    spa_date: Optional[str] = None
    
    # Filtering statistics
    memos_considered: int = 0
    memos_after_date_filter: int = 0
    memos_after_project_filter: int = 0
    rules_before_conflict_resolution: int = 0
    rules_after_conflict_resolution: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'pricing': {
                'base_price': self.base_price,
                'final_price': self.final_price,
                'total_rebate': self.total_rebate,
                'total_commission': self.total_commission
            },
            'breakdown': {
                'rebates': [r.to_dict() for r in self.rebate_breakdown],
                'commissions': [c.to_dict() for c in self.commission_breakdown],
                'price_adjustments': [p.to_dict() for p in self.price_adjustments],
                'packages': self.applicable_packages
            },
            'traceability': {
                'matched_rules': self.matched_rules,
                'source_memos': self.source_memos,
                'conflicts': self.conflicts_detected
            },
            'context': {
                'target_project': self.target_project,
                'spa_date': self.spa_date
            },
            'statistics': {
                'memos_considered': self.memos_considered,
                'memos_after_date_filter': self.memos_after_date_filter,
                'memos_after_project_filter': self.memos_after_project_filter,
                'rules_before_conflict_resolution': self.rules_before_conflict_resolution,
                'rules_after_conflict_resolution': self.rules_after_conflict_resolution
            }
        }


class EnhancedRuleMatcher:
    """
    Matches rules from the aggregated library against user context.
    Uses priority scores in combination with match scores.
    """
    
    def __init__(self, library: AggregatedRuleLibrary):
        self.library = library
        self.parser = ConditionParser()
    
    def match(
        self,
        context: Dict[str, Any],
        rule_types: Optional[List[str]] = None
    ) -> List[MatchedEnhancedRule]:
        """
        Find all rules that match the given context.
        Results are sorted by combined score (match + priority).
        """
        matched = []
        
        # Get active (non-superseded) rules
        rules = self.library.get_active_rules()
        
        # Filter by type if specified
        if rule_types:
            rules = [r for r in rules if r.rule_type in rule_types]
        
        # Pre-filter by buyer type if specified
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
        
        # Sort by combined score (priority + match)
        matched.sort(
            key=lambda m: m.match_score * 0.5 + m.priority_score * 0.5,
            reverse=True
        )
        
        return matched
    
    def match_all_applicable(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, List[MatchedEnhancedRule]]:
        """Find all applicable rules organized by type."""
        all_matches = self.match(context)
        
        result: Dict[str, List[MatchedEnhancedRule]] = {}
        for match in all_matches:
            if match.rule_type not in result:
                result[match.rule_type] = []
            result[match.rule_type].append(match)
        
        return result
    
    def match_best_per_type(
        self,
        context: Dict[str, Any],
        rule_types: Optional[List[str]] = None
    ) -> Dict[str, MatchedEnhancedRule]:
        """Get the best matching rule for each type."""
        all_matches = self.match_all_applicable(context)
        
        if rule_types:
            all_matches = {k: v for k, v in all_matches.items() if k in rule_types}
        
        return {
            rule_type: matches[0] if matches else None
            for rule_type, matches in all_matches.items()
        }
    
    def _evaluate_rule(
        self,
        rule: EnhancedRule,
        context: Dict[str, Any]
    ) -> Optional[MatchedEnhancedRule]:
        """Evaluate a single rule against the context."""
        if not rule.conditions:
            if rule.rule_type == 'package':
                return self._evaluate_package_rule(rule, context)
            elif rule.rule_type == 'referral':
                return self._evaluate_referral_rule(rule, context)
            return None
        
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
                    score = self._calculate_match_score(condition_str, context)
                    if score > best_score:
                        best_score = score
                        best_match = condition
            except Exception as e:
                print(f"Warning: Failed to parse condition '{condition_str}': {e}")
                continue
        
        if best_match:
            return MatchedEnhancedRule(
                rule=rule,
                matched_condition=best_match,
                match_score=best_score,
                priority_score=rule.get_total_priority()
            )
        
        return None
    
    def _evaluate_package_rule(
        self,
        rule: EnhancedRule,
        context: Dict[str, Any]
    ) -> Optional[MatchedEnhancedRule]:
        """Evaluate package rules based on eligibility."""
        eligibility = rule.raw_data.get('eligibility', [])
        buyer_type = context.get('buyer_type', '')
        block = context.get('block', '')
        
        for elig in eligibility:
            elig_lower = elig.lower()
            if 'foreign' in elig_lower and buyer_type == 'foreign':
                return MatchedEnhancedRule(
                    rule=rule,
                    matched_condition=None,
                    match_score=0.5,
                    priority_score=rule.get_total_priority()
                )
            if f'block {block.lower()}' in elig_lower:
                return MatchedEnhancedRule(
                    rule=rule,
                    matched_condition=None,
                    match_score=0.5,
                    priority_score=rule.get_total_priority()
                )
        
        return None
    
    def _evaluate_referral_rule(
        self,
        rule: EnhancedRule,
        context: Dict[str, Any]
    ) -> Optional[MatchedEnhancedRule]:
        """Evaluate referral rules based on referrer category."""
        referrer_category = context.get('referrer_category')
        
        if referrer_category and referrer_category == rule.referrer_category:
            return MatchedEnhancedRule(
                rule=rule,
                matched_condition=None,
                match_score=0.8,
                priority_score=rule.get_total_priority()
            )
        
        return None
    
    def _calculate_match_score(
        self,
        condition_str: str,
        context: Dict[str, Any]
    ) -> float:
        """Calculate match score based on condition specificity."""
        and_count = condition_str.upper().count(' AND ')
        score = 0.5 + (and_count * 0.1)
        return min(score, 1.0)


class MultiMemoRuleEngine:
    """
    Main engine for multi-memo rule retrieval and calculation.
    
    Flow:
    1. Load memos from artifacts
    2. Filter by date and project
    3. Aggregate rules with conflict resolution
    4. Match rules against context
    5. Calculate with full traceability
    """
    
    def __init__(self, artifacts_path: str):
        self.artifacts_path = Path(artifacts_path)
        self.memo_manager = xMemoManager(str(self.artifacts_path))
        self.aggregator: Optional[RuleAggregator] = None
        self.library: Optional[AggregatedRuleLibrary] = None
        self.matcher: Optional[EnhancedRuleMatcher] = None
        self.ranker = PriorityRanker()
        
        # Statistics for the last operation
        self._last_stats = {}
    
    def load_memos(self) -> int:
        """Load all memos from the artifacts directory."""
        count = self.memo_manager.load_all_memos()
        print(f"Loaded {count} memos from {self.artifacts_path}")
        return count
    
    def retrieve_and_prepare(
        self,
        project_name: Optional[str] = None,
        target_date: Optional[datetime] = None,
        resolution_strategy: ConflictResolution = ConflictResolution.LATEST_WINS
    ) -> AggregatedRuleLibrary:
        """
        Retrieve rules with filtering and conflict resolution.
        
        Args:
            project_name: Filter memos by project
            target_date: Filter memos by effective date (SPA date)
            resolution_strategy: Strategy for resolving conflicts
        
        Returns:
            Aggregated and ranked rule library
        """
        # Track statistics
        self._last_stats = {
            'memos_considered': len(self.memo_manager.memos),
            'memos_after_date_filter': 0,
            'memos_after_project_filter': 0,
            'rules_before_conflict_resolution': 0,
            'rules_after_conflict_resolution': 0
        }
        
        # Step 1: Filter memos
        filtered_memos = self.memo_manager.filter_memos(
            project_name=project_name,
            target_date=target_date
        )
        
        self._last_stats['memos_after_date_filter'] = len(filtered_memos)
        self._last_stats['memos_after_project_filter'] = len(filtered_memos)
        
        # Step 2: Aggregate with conflict resolution
        self.aggregator = RuleAggregator(self.memo_manager)
        self.library = self.aggregator.aggregate(
            memos=filtered_memos,
            resolution_strategy=resolution_strategy
        )
        
        self._last_stats['rules_before_conflict_resolution'] = len(self.library.rules)
        self._last_stats['rules_after_conflict_resolution'] = len(self.library.get_active_rules())
        
        # Step 3: Create matcher
        self.matcher = EnhancedRuleMatcher(self.library)
        
        return self.library
    
    def get_applicable_rules(
        self,
        context: Dict[str, Any],
        rule_types: Optional[List[str]] = None
    ) -> Dict[str, List[MatchedEnhancedRule]]:
        """Get all applicable rules for the given context."""
        if not self.matcher:
            raise RuntimeError("Call retrieve_and_prepare() first")
        
        if rule_types:
            matches = self.matcher.match(context, rule_types)
            result = {}
            for m in matches:
                if m.rule_type not in result:
                    result[m.rule_type] = []
                result[m.rule_type].append(m)
            return result
        
        return self.matcher.match_all_applicable(context)
    
    def _resolve_matched_conflicts(
        self,
        matches: List[MatchedEnhancedRule]
    ) -> Tuple[List[MatchedEnhancedRule], List[Dict[str, Any]]]:
        """
        Resolve conflicts within matched rules, keeping only winners.
        
        Returns:
            Tuple of (winning_matches, conflict_records)
        """
        if not matches:
            return [], []
        
        conflict_records = []
        
        # Group rules that conflict with each other
        # Build conflict groups using the conflicts_with field
        processed = set()
        conflict_groups = []
        
        for match in matches:
            if match.composite_id in processed:
                continue
            
            # Find all rules this one conflicts with
            group = [match]
            conflicts_with = set(match.rule.conflicts_with)
            
            for other_match in matches:
                if other_match.composite_id != match.composite_id:
                    if other_match.composite_id in conflicts_with or match.composite_id in other_match.rule.conflicts_with:
                        group.append(other_match)
                        processed.add(other_match.composite_id)
            
            processed.add(match.composite_id)
            conflict_groups.append(group)
        
        # For each group, select the winner (highest combined score)
        winners = []
        for group in conflict_groups:
            if len(group) == 1:
                # No conflict, keep the rule
                winners.append(group[0])
            else:
                # Sort by combined score (priority + match)
                group.sort(
                    key=lambda m: m.match_score * 0.5 + m.priority_score * 0.5,
                    reverse=True
                )
                winner = group[0]
                losers = group[1:]
                
                winners.append(winner)
                
                # Record the conflict resolution
                conflict_records.append({
                    'conflict_type': 'runtime_resolution',
                    'winner': {
                        'composite_id': winner.composite_id,
                        'rule_name': winner.rule_name,
                        'memo_reference': winner.memo_reference,
                        'score': winner.match_score * 0.5 + winner.priority_score * 0.5
                    },
                    'losers': [
                        {
                            'composite_id': l.composite_id,
                            'rule_name': l.rule_name,
                            'memo_reference': l.memo_reference,
                            'score': l.match_score * 0.5 + l.priority_score * 0.5
                        }
                        for l in losers
                    ],
                    'description': f"'{winner.rule_name}' selected over {len(losers)} conflicting rule(s)"
                })
        
        return winners, conflict_records

    def calculate(
        self,
        context: Dict[str, Any],
        project_name: Optional[str] = None,
        spa_date: Optional[str] = None
    ) -> MultiMemoPricingResult:
        """
        Perform full pricing calculation with multi-memo support.
        
        Args:
            context: User context with base_price and property details
            project_name: Target project for filtering
            spa_date: SPA date for temporal filtering (format: "DD MMM YYYY")
        
        Returns:
            Complete pricing result with traceability
        """
        # Parse SPA date if provided
        target_date = None
        if spa_date:
            for fmt in ["%d %b %Y", "%d-%m-%Y", "%Y-%m-%d"]:
                try:
                    target_date = datetime.strptime(spa_date, fmt)
                    break
                except ValueError:
                    continue
        
        # Prepare the rule library if not done
        if not self.library or not self.matcher:
            self.retrieve_and_prepare(
                project_name=project_name,
                target_date=target_date
            )
        
        base_price = context.get('base_price', 0)
        
        # Get all applicable rules
        all_matches = self.get_applicable_rules(context)
        
        # Track source memos and runtime conflicts
        source_memos = set()
        matched_rules = []
        all_runtime_conflicts = []
        
        # Resolve conflicts within rebate rules
        rebate_matches = all_matches.get('rebate', [])
        resolved_rebates, rebate_conflicts = self._resolve_matched_conflicts(rebate_matches)
        all_runtime_conflicts.extend(rebate_conflicts)
        
        # Calculate rebates (using resolved/deduped rules)
        rebate_breakdown = []
        total_rebate = 0.0
        
        for match in resolved_rebates:
            result = self._calculate_rebate(match, base_price, total_rebate)
            if result:
                rebate_breakdown.append(result)
                if result.calculated_amount:
                    total_rebate += result.calculated_amount
                source_memos.add(result.memo_reference or "unknown")
                matched_rules.append(result.composite_id)
        
        # Resolve conflicts within commission rules
        commission_matches = all_matches.get('commission', [])
        resolved_commissions, commission_conflicts = self._resolve_matched_conflicts(commission_matches)
        all_runtime_conflicts.extend(commission_conflicts)
        
        # Calculate commission (using resolved/deduped rules)
        commission_breakdown = []
        total_commission = 0.0
        net_price = base_price - total_rebate
        
        for match in resolved_commissions:
            result = self._calculate_commission(match, net_price, context)
            if result:
                commission_breakdown.append(result)
                if result.calculated_amount:
                    total_commission += result.calculated_amount
                source_memos.add(result.memo_reference or "unknown")
                matched_rules.append(result.composite_id)
        
        # Resolve conflicts within price adjustment rules
        adjustment_matches = all_matches.get('price_adjustment', [])
        resolved_adjustments, adjustment_conflicts = self._resolve_matched_conflicts(adjustment_matches)
        all_runtime_conflicts.extend(adjustment_conflicts)
        
        # Calculate price adjustments (using resolved/deduped rules)
        price_adjustments = []
        for match in resolved_adjustments:
            result = self._calculate_price_adjustment(match)
            if result:
                price_adjustments.append(result)
                source_memos.add(result.memo_reference or "unknown")
                matched_rules.append(result.composite_id)
        
        # Get applicable packages (resolve conflicts too)
        package_matches = all_matches.get('package', [])
        resolved_packages, package_conflicts = self._resolve_matched_conflicts(package_matches)
        all_runtime_conflicts.extend(package_conflicts)
        
        applicable_packages = [
            m.rule_name for m in resolved_packages
        ]
        
        # Combine static conflicts (from aggregation) and runtime conflicts
        conflicts_detected = all_runtime_conflicts.copy()
        if self.library:
            for conflict in self.library.conflicts:
                if any(rule_id in matched_rules for rule_id in conflict.involved_rules):
                    conflicts_detected.append(conflict.to_dict())
        
        # Calculate final price
        adjustment_total = sum(r.calculated_amount or 0 for r in price_adjustments)
        final_price = base_price + adjustment_total - total_rebate
        
        return MultiMemoPricingResult(
            base_price=base_price,
            final_price=final_price,
            total_rebate=total_rebate,
            total_commission=total_commission,
            rebate_breakdown=rebate_breakdown,
            commission_breakdown=commission_breakdown,
            price_adjustments=price_adjustments,
            applicable_packages=applicable_packages,
            matched_rules=matched_rules,
            source_memos=list(source_memos),
            conflicts_detected=conflicts_detected,
            target_project=project_name,
            spa_date=spa_date,
            memos_considered=self._last_stats.get('memos_considered', 0),
            memos_after_date_filter=self._last_stats.get('memos_after_date_filter', 0),
            memos_after_project_filter=self._last_stats.get('memos_after_project_filter', 0),
            rules_before_conflict_resolution=self._last_stats.get('rules_before_conflict_resolution', 0),
            rules_after_conflict_resolution=self._last_stats.get('rules_after_conflict_resolution', 0)
        )
    
    def _calculate_rebate(
        self,
        match: MatchedEnhancedRule,
        base_price: float,
        accumulated_rebate: float
    ) -> Optional[MultiMemoCalculationResult]:
        """Calculate rebate from a matched rule."""
        percentage = match.get_percentage()
        if percentage is None:
            return None
        
        calc_base = match.rule.raw_data.get('calculation_base', 'Net Price')
        
        if 'after Bumi' in calc_base:
            effective_price = base_price - accumulated_rebate
        else:
            effective_price = base_price
        
        calculated_amount = effective_price * (percentage / 100)
        
        return MultiMemoCalculationResult(
            rule_type='rebate',
            rule_id=match.rule_id,
            composite_id=match.composite_id,
            rule_name=match.rule_name,
            description=match.get_value('description', ''),
            value=percentage,
            value_type='percentage',
            calculated_amount=calculated_amount,
            details={
                'calculation_base': calc_base,
                'effective_price': effective_price
            },
            memo_reference=match.memo_reference,
            memo_file=match.rule.memo_metadata.memo_file if match.rule.memo_metadata else None,
            project_name=match.project_name,
            effective_period=match.rule.memo_metadata.effective_period if match.rule.memo_metadata else None,
            priority_score=match.priority_score,
            conflicts=match.rule.conflicts_with
        )
    
    def _calculate_commission(
        self,
        match: MatchedEnhancedRule,
        net_price: float,
        context: Dict[str, Any]
    ) -> Optional[MultiMemoCalculationResult]:
        """Calculate commission from a matched rule."""
        percentage = match.get_percentage()
        if percentage is None:
            return None
        
        commission_base = net_price
        if context.get('buyer_type') == 'foreign':
            commission_base = net_price - 200000
        
        calculated_amount = commission_base * (percentage / 100)
        payout_spa = calculated_amount * 0.30
        payout_stage2a = calculated_amount * 0.70
        
        return MultiMemoCalculationResult(
            rule_type='commission',
            rule_id=match.rule_id,
            composite_id=match.composite_id,
            rule_name=match.rule_name,
            description=match.get_value('description', ''),
            value=percentage,
            value_type='percentage',
            calculated_amount=calculated_amount,
            details={
                'commission_base': commission_base,
                'payout_spa': payout_spa,
                'payout_stage2a': payout_stage2a
            },
            memo_reference=match.memo_reference,
            memo_file=match.rule.memo_metadata.memo_file if match.rule.memo_metadata else None,
            project_name=match.project_name,
            effective_period=match.rule.memo_metadata.effective_period if match.rule.memo_metadata else None,
            priority_score=match.priority_score,
            conflicts=match.rule.conflicts_with
        )
    
    def _calculate_price_adjustment(
        self,
        match: MatchedEnhancedRule
    ) -> Optional[MultiMemoCalculationResult]:
        """Calculate price adjustment from a matched rule."""
        amount = match.get_amount()
        if amount is None:
            amount = match.get_value('adjustment_amount', 0)
        
        return MultiMemoCalculationResult(
            rule_type='price_adjustment',
            rule_id=match.rule_id,
            composite_id=match.composite_id,
            rule_name=match.rule_name,
            description=match.get_value('description', ''),
            value=amount,
            value_type='fixed',
            calculated_amount=amount,
            details={},
            memo_reference=match.memo_reference,
            memo_file=match.rule.memo_metadata.memo_file if match.rule.memo_metadata else None,
            project_name=match.project_name,
            effective_period=match.rule.memo_metadata.effective_period if match.rule.memo_metadata else None,
            priority_score=match.priority_score,
            conflicts=match.rule.conflicts_with
        )
    
    def get_priority_ranking(
        self,
        rule_type: Optional[str] = None,
        top_n: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get the priority ranking of rules."""
        if not self.aggregator:
            raise RuntimeError("Call retrieve_and_prepare() first")
        
        return self.aggregator.get_priority_ranking(rule_type, top_n)
    
    def get_conflicts_summary(self) -> Dict[str, Any]:
        """Get summary of detected conflicts."""
        if not self.library:
            return {'total_conflicts': 0}
        
        return self.library.get_conflicts_summary()
    
    def explain_rules(self, context: Dict[str, Any]) -> str:
        """Generate human-readable explanation of applicable rules."""
        all_matches = self.get_applicable_rules(context)
        
        lines = [
            "Multi-Memo Rule Analysis",
            "=" * 60,
            "",
            "Context:",
        ]
        
        for key, value in context.items():
            lines.append(f"  {key}: {value}")
        
        lines.extend(["", "=" * 60, ""])
        
        for rule_type, matches in all_matches.items():
            lines.append(f"📋 {rule_type.upper()} RULES ({len(matches)} matched)")
            lines.append("-" * 50)
            
            for match in matches:
                lines.append(f"  ✓ {match.rule_name} ({match.rule_id})")
                lines.append(f"    📁 Memo: {match.memo_reference}")
                lines.append(f"    🏗️  Project: {match.project_name}")
                
                if match.matched_condition:
                    desc = match.matched_condition.get('description', '')
                    if desc:
                        lines.append(f"    Description: {desc}")
                    
                    pct = match.get_percentage()
                    if pct:
                        lines.append(f"    Rate: {pct}%")
                    
                    amt = match.get_amount()
                    if amt:
                        lines.append(f"    Amount: RM{amt:,.0f}")
                
                lines.append(f"    Match Score: {match.match_score:.2f}")
                lines.append(f"    Priority Score: {match.priority_score:.2f}")
                
                if match.rule.conflicts_with:
                    lines.append(f"    ⚠️  Conflicts with: {match.rule.conflicts_with}")
                
                lines.append("")
        
        # Add conflict summary
        if self.library and self.library.conflicts:
            lines.extend([
                "",
                "⚠️  CONFLICT SUMMARY",
                "-" * 50
            ])
            for conflict in self.library.conflicts[:5]:  # Show first 5
                lines.append(f"  {conflict.conflict_id}: {conflict.description}")
                lines.append(f"    Resolution: {conflict.resolution.value}")
            
            if len(self.library.conflicts) > 5:
                lines.append(f"  ... and {len(self.library.conflicts) - 5} more conflicts")
        
        return "\n".join(lines)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about loaded memos and rules."""
        memo_stats = self.memo_manager.get_statistics()
        
        if self.library:
            memo_stats['aggregated_rules'] = len(self.library.rules)
            memo_stats['active_rules'] = len(self.library.get_active_rules())
            memo_stats['superseded_rules'] = len(self.library._superseded)
            memo_stats['conflicts'] = len(self.library.conflicts)
        
        return memo_stats


# Convenience function
def create_multi_memo_engine(artifacts_path: str) -> MultiMemoRuleEngine:
    """Create and initialize a multi-memo rule engine."""
    engine = MultiMemoRuleEngine(artifacts_path)
    engine.load_memos()
    return engine
