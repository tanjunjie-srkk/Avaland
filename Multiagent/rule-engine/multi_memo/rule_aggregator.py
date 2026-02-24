"""
Rule Aggregator Module
Aggregates rules from multiple memos, handles priority ranking and conflict resolution.
Creates a unified, ranked rule library ready for matching.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re

from memo_manager import MemoManager, Memo, MemoMetadata, EnhancedRule, MemoType


class ConflictType(Enum):
    """Types of conflicts between rules."""
    SAME_RULE_ID = "same_rule_id"           # Same rule ID from different memos
    OVERLAPPING_CONDITIONS = "overlapping"   # Different rules, overlapping conditions
    CONTRADICTORY = "contradictory"          # Rules that contradict each other
    SUPERSEDED = "superseded"                # Rule is superseded by another


class ConflictResolution(Enum):
    """Resolution strategies for conflicts."""
    LATEST_WINS = "latest_wins"              # Most recent memo wins
    HIGHEST_PRIORITY = "highest_priority"    # Highest priority score wins
    MOST_SPECIFIC = "most_specific"          # Most specific condition wins
    MERGE = "merge"                          # Attempt to merge rules
    MANUAL_REVIEW = "manual_review"          # Flag for manual review


@dataclass
class RuleConflict:
    """Represents a conflict between two or more rules."""
    conflict_id: str
    conflict_type: ConflictType
    involved_rules: List[str]  # Composite IDs
    description: str
    resolution: ConflictResolution
    resolved_rule: Optional[str] = None  # Composite ID of the winning rule
    requires_review: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'conflict_id': self.conflict_id,
            'type': self.conflict_type.value,
            'involved_rules': self.involved_rules,
            'description': self.description,
            'resolution': self.resolution.value,
            'resolved_rule': self.resolved_rule,
            'requires_review': self.requires_review
        }


@dataclass
class AggregatedRuleLibrary:
    """
    Aggregated and ranked rule library from multiple memos.
    """
    rules: List[EnhancedRule] = field(default_factory=list)
    conflicts: List[RuleConflict] = field(default_factory=list)
    
    # Indexes for fast lookup
    _by_id: Dict[str, EnhancedRule] = field(default_factory=dict)
    _by_composite_id: Dict[str, EnhancedRule] = field(default_factory=dict)
    _by_type: Dict[str, List[EnhancedRule]] = field(default_factory=dict)
    _by_project: Dict[str, List[EnhancedRule]] = field(default_factory=dict)
    _superseded: Set[str] = field(default_factory=set)  # Set of superseded composite IDs
    
    def add_rule(self, rule: EnhancedRule, check_conflicts: bool = True):
        """Add a rule to the library."""
        self.rules.append(rule)
        
        # Index by composite ID (unique across memos)
        self._by_composite_id[rule.composite_id] = rule
        
        # Index by rule ID (may have duplicates from different memos)
        if rule.rule_id not in self._by_id:
            self._by_id[rule.rule_id] = rule
        
        # Index by type
        if rule.rule_type not in self._by_type:
            self._by_type[rule.rule_type] = []
        self._by_type[rule.rule_type].append(rule)
        
        # Index by project
        if rule.project_name not in self._by_project:
            self._by_project[rule.project_name] = []
        self._by_project[rule.project_name].append(rule)
    
    def mark_superseded(self, composite_id: str, superseded_by: str):
        """Mark a rule as superseded."""
        self._superseded.add(composite_id)
        if composite_id in self._by_composite_id:
            self._by_composite_id[composite_id].superseded_by = superseded_by
    
    def get_active_rules(self) -> List[EnhancedRule]:
        """Get all non-superseded rules."""
        return [r for r in self.rules if r.composite_id not in self._superseded]
    
    def get_by_type(self, rule_type: str, include_superseded: bool = False) -> List[EnhancedRule]:
        """Get rules by type, optionally excluding superseded ones."""
        rules = self._by_type.get(rule_type, [])
        if not include_superseded:
            rules = [r for r in rules if r.composite_id not in self._superseded]
        return rules
    
    def get_by_project(self, project_name: str) -> List[EnhancedRule]:
        """Get rules by project name."""
        return self._by_project.get(project_name, [])
    
    def get_ranked_rules(self, rule_type: Optional[str] = None) -> List[EnhancedRule]:
        """
        Get rules sorted by priority (highest first).
        Excludes superseded rules.
        """
        rules = self.get_active_rules()
        if rule_type:
            rules = [r for r in rules if r.rule_type == rule_type]
        
        return sorted(rules, key=lambda r: r.get_total_priority(), reverse=True)
    
    def get_all_types(self) -> List[str]:
        """Get all available rule types."""
        return list(self._by_type.keys())
    
    def get_conflicts_summary(self) -> Dict[str, Any]:
        """Get summary of conflicts."""
        by_type = {}
        for conflict in self.conflicts:
            ctype = conflict.conflict_type.value
            if ctype not in by_type:
                by_type[ctype] = 0
            by_type[ctype] += 1
        
        return {
            'total_conflicts': len(self.conflicts),
            'by_type': by_type,
            'requires_review': sum(1 for c in self.conflicts if c.requires_review),
            'conflicts': [c.to_dict() for c in self.conflicts]
        }


class RuleAggregator:
    """
    Aggregates rules from multiple memos with priority ranking and conflict resolution.
    """
    
    def __init__(self, memo_manager: xMemoManager):
        self.memo_manager = memo_manager
        self.library = AggregatedRuleLibrary()
        self._conflict_counter = 0
    
    def aggregate(
        self,
        memos: Optional[List[Memo]] = None,
        resolution_strategy: ConflictResolution = ConflictResolution.LATEST_WINS
    ) -> AggregatedRuleLibrary:
        """
        Aggregate rules from multiple memos into a unified library.
        
        Args:
            memos: List of memos to aggregate (None = all memos in manager)
            resolution_strategy: Default strategy for conflict resolution
        
        Returns:
            AggregatedRuleLibrary with ranked and deduplicated rules
        """
        self.library = AggregatedRuleLibrary()
        
        # Get memos to process
        if memos is None:
            memos = list(self.memo_manager.memos.values())
        
        # Sort memos by date (oldest first for proper supersession handling)
        memos_sorted = sorted(
            memos,
            key=lambda m: m.metadata.start_date or datetime.min
        )
        
        # Phase 1: Load all rules and detect conflicts
        rule_groups: Dict[str, List[EnhancedRule]] = {}  # rule_id -> [rules from different memos]
        
        for memo in memos_sorted:
            for rule in memo.rules:
                if rule.rule_id not in rule_groups:
                    rule_groups[rule.rule_id] = []
                rule_groups[rule.rule_id].append(rule)
        
        # Phase 2: Process each group of rules with same ID
        for rule_id, rules in rule_groups.items():
            if len(rules) == 1:
                # No conflict, add directly
                self.library.add_rule(rules[0])
            else:
                # Multiple rules with same ID - resolve conflict
                self._resolve_same_id_conflict(rules, resolution_strategy)
        
        # Phase 3: Detect overlapping conditions within same type
        self._detect_overlapping_conflicts()
        
        # Phase 4: Handle supersession chains
        self._handle_supersessions(memos_sorted)
        
        return self.library
    
    def _resolve_same_id_conflict(
        self,
        rules: List[EnhancedRule],
        strategy: ConflictResolution
    ):
        """Resolve conflict between rules with the same ID from different memos."""
        # Sort by priority (we'll determine winner based on strategy)
        if strategy == ConflictResolution.LATEST_WINS:
            # Sort by recency (newest first)
            rules_sorted = sorted(rules, key=lambda r: r.recency_score, reverse=True)
        elif strategy == ConflictResolution.HIGHEST_PRIORITY:
            rules_sorted = sorted(rules, key=lambda r: r.get_total_priority(), reverse=True)
        elif strategy == ConflictResolution.MOST_SPECIFIC:
            rules_sorted = sorted(rules, key=lambda r: r.specificity_score, reverse=True)
        else:
            rules_sorted = rules
        
        winner = rules_sorted[0]
        losers = rules_sorted[1:]
        
        # Create conflict record
        conflict = RuleConflict(
            conflict_id=f"CONF_{self._conflict_counter:04d}",
            conflict_type=ConflictType.SAME_RULE_ID,
            involved_rules=[r.composite_id for r in rules],
            description=f"Rule '{winner.rule_id}' exists in {len(rules)} memos",
            resolution=strategy,
            resolved_rule=winner.composite_id,
            requires_review=(strategy == ConflictResolution.MANUAL_REVIEW)
        )
        self._conflict_counter += 1
        self.library.conflicts.append(conflict)
        
        # Add winning rule
        self.library.add_rule(winner)
        
        # Mark losers as superseded
        for loser in losers:
            loser.superseded_by = winner.composite_id
            self.library.add_rule(loser)
            self.library.mark_superseded(loser.composite_id, winner.composite_id)
    
    def _detect_overlapping_conflicts(self):
        """Detect rules with overlapping conditions within the same type."""
        for rule_type in self.library.get_all_types():
            rules = self.library.get_by_type(rule_type, include_superseded=False)
            
            # Compare each pair of rules
            for i, rule1 in enumerate(rules):
                for rule2 in rules[i+1:]:
                    overlap = self._check_condition_overlap(rule1, rule2)
                    if overlap:
                        # Record the conflict but don't supersede
                        conflict = RuleConflict(
                            conflict_id=f"CONF_{self._conflict_counter:04d}",
                            conflict_type=ConflictType.OVERLAPPING_CONDITIONS,
                            involved_rules=[rule1.composite_id, rule2.composite_id],
                            description=f"Overlapping conditions detected: {overlap}",
                            resolution=ConflictResolution.MOST_SPECIFIC,
                            resolved_rule=None,  # Resolved at match time
                            requires_review=False
                        )
                        self._conflict_counter += 1
                        self.library.conflicts.append(conflict)
                        
                        # Track conflicts on the rules themselves
                        rule1.conflicts_with.append(rule2.composite_id)
                        rule2.conflicts_with.append(rule1.composite_id)
    
    def _check_condition_overlap(
        self,
        rule1: EnhancedRule,
        rule2: EnhancedRule
    ) -> Optional[str]:
        """
        Check if two rules have overlapping conditions.
        
        Two rules conflict if:
        1. Same rule_type and buyer_type (or both None)
        2. Have identical or overlapping condition strings
        """
        # Must be same buyer_type to conflict
        if rule1.buyer_type != rule2.buyer_type:
            return None
        
        # Extract condition strings for comparison
        conds1_strs = self._extract_condition_strings(rule1)
        conds2_strs = self._extract_condition_strings(rule2)
        
        # Check for exact matching conditions
        exact_matches = conds1_strs.intersection(conds2_strs)
        if exact_matches:
            return f"Identical conditions: {exact_matches}"
        
        # Extract condition variables
        conds1_vars = self._extract_condition_vars(rule1)
        conds2_vars = self._extract_condition_vars(rule2)
        
        # Check for overlap in condition variables (relaxed: at least 1 common variable)
        common_vars = conds1_vars.intersection(conds2_vars)
        if common_vars:
            # Further check: do they have similar patterns?
            # This catches cases like both having "block == 'A'"
            for cond1 in conds1_strs:
                for cond2 in conds2_strs:
                    # Normalize and compare
                    norm1 = self._normalize_condition(cond1)
                    norm2 = self._normalize_condition(cond2)
                    if norm1 == norm2:
                        return f"Equivalent conditions: '{cond1}' == '{cond2}'"
        
        return None
    
    def _extract_condition_strings(self, rule: EnhancedRule) -> Set[str]:
        """Extract raw condition strings from a rule."""
        conditions = set()
        for condition in rule.conditions:
            if isinstance(condition, dict) and 'condition' in condition:
                conditions.add(condition['condition'])
        return conditions
    
    def _normalize_condition(self, cond_str: str) -> str:
        """Normalize a condition string for comparison."""
        # Remove IF prefix, extra spaces, and normalize quotes
        normalized = cond_str.upper().strip()
        normalized = normalized.replace("IF ", "")
        normalized = normalized.replace("'", '"')
        normalized = ' '.join(normalized.split())  # Normalize whitespace
        return normalized
    
    def _extract_condition_vars(self, rule: EnhancedRule) -> Set[str]:
        """Extract variable names from rule conditions."""
        variables = set()
        
        for condition in rule.conditions:
            if isinstance(condition, dict) and 'condition' in condition:
                cond_str = condition['condition']
                # Extract variable names (words before operators)
                matches = re.findall(r'(\w+)\s*[=<>!]', cond_str)
                variables.update(matches)
        
        return variables
    
    def _handle_supersessions(self, memos: List[Memo]):
        """Handle memo-level supersessions."""
        for memo in memos:
            if memo.metadata.supersedes:
                superseded_ref = memo.metadata.supersedes
                superseding_ref = memo.metadata.memo_reference
                
                # Find and mark all rules from superseded memo
                superseded_memo = self.memo_manager.get_memo(superseded_ref)
                if superseded_memo:
                    for rule in superseded_memo.rules:
                        # Find corresponding new rule if it exists
                        new_rule_id = f"{superseding_ref}::{rule.rule_id}"
                        if new_rule_id in self.library._by_composite_id:
                            self.library.mark_superseded(
                                rule.composite_id,
                                new_rule_id
                            )
                        else:
                            # Rule was removed in new memo
                            conflict = RuleConflict(
                                conflict_id=f"CONF_{self._conflict_counter:04d}",
                                conflict_type=ConflictType.SUPERSEDED,
                                involved_rules=[rule.composite_id],
                                description=f"Rule removed in superseding memo {superseding_ref}",
                                resolution=ConflictResolution.LATEST_WINS,
                                resolved_rule=None,
                                requires_review=True
                            )
                            self._conflict_counter += 1
                            self.library.conflicts.append(conflict)
                            self.library.mark_superseded(rule.composite_id, "REMOVED")
    
    def get_priority_ranking(
        self,
        rule_type: Optional[str] = None,
        top_n: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get rules ranked by priority with detailed breakdown.
        
        Returns list of dicts with rule info and priority components.
        """
        rules = self.library.get_ranked_rules(rule_type)
        
        if top_n:
            rules = rules[:top_n]
        
        result = []
        for rank, rule in enumerate(rules, 1):
            result.append({
                'rank': rank,
                'composite_id': rule.composite_id,
                'rule_id': rule.rule_id,
                'rule_name': rule.rule_name,
                'rule_type': rule.rule_type,
                'project': rule.project_name,
                'memo_reference': rule.memo_metadata.memo_reference if rule.memo_metadata else None,
                'total_priority': rule.get_total_priority(),
                'priority_breakdown': {
                    'recency_score': rule.recency_score,
                    'specificity_score': rule.specificity_score,
                    'explicit_priority': rule.memo_metadata.priority if rule.memo_metadata else 0
                },
                'is_superseded': rule.composite_id in self.library._superseded,
                'superseded_by': rule.superseded_by,
                'conflicts_with': rule.conflicts_with
            })
        
        return result


class PriorityRanker:
    """
    Advanced priority ranking with customizable weights and strategies.
    """
    
    def __init__(
        self,
        recency_weight: float = 0.40,
        specificity_weight: float = 0.30,
        explicit_priority_weight: float = 0.20,
        memo_hierarchy_weight: float = 0.10
    ):
        self.weights = {
            'recency': recency_weight,
            'specificity': specificity_weight,
            'explicit_priority': explicit_priority_weight,
            'memo_hierarchy': memo_hierarchy_weight
        }
        
        # Memo type hierarchy (higher = more authoritative)
        self.memo_type_scores = {
            MemoType.SUPERSEDING: 1.0,
            MemoType.AMENDMENT: 0.8,
            MemoType.ADDENDUM: 0.6,
            MemoType.STANDARD: 0.5
        }
    
    def rank_rules(self, rules: List[EnhancedRule]) -> List[EnhancedRule]:
        """
        Rank rules by priority using weighted scoring.
        """
        for rule in rules:
            rule.priority_score = self._calculate_priority(rule)
        
        return sorted(rules, key=lambda r: r.priority_score, reverse=True)
    
    def _calculate_priority(self, rule: EnhancedRule) -> float:
        """Calculate weighted priority score for a rule."""
        # Component scores
        recency = rule.recency_score
        specificity = rule.specificity_score
        explicit = (rule.memo_metadata.priority / 10.0) if rule.memo_metadata else 0
        
        memo_type = rule.memo_metadata.memo_type if rule.memo_metadata else MemoType.STANDARD
        hierarchy = self.memo_type_scores.get(memo_type, 0.5)
        
        # Weighted sum
        score = (
            recency * self.weights['recency'] +
            specificity * self.weights['specificity'] +
            explicit * self.weights['explicit_priority'] +
            hierarchy * self.weights['memo_hierarchy']
        )
        
        return score
    
    def compare_rules(
        self,
        rule1: EnhancedRule,
        rule2: EnhancedRule
    ) -> Tuple[EnhancedRule, Dict[str, Any]]:
        """
        Compare two rules and return the higher priority one with explanation.
        """
        score1 = self._calculate_priority(rule1)
        score2 = self._calculate_priority(rule2)
        
        winner = rule1 if score1 >= score2 else rule2
        loser = rule2 if score1 >= score2 else rule1
        
        explanation = {
            'winner': winner.composite_id,
            'loser': loser.composite_id,
            'winner_score': max(score1, score2),
            'loser_score': min(score1, score2),
            'margin': abs(score1 - score2),
            'deciding_factor': self._get_deciding_factor(rule1, rule2, score1, score2)
        }
        
        return winner, explanation
    
    def _get_deciding_factor(
        self,
        rule1: EnhancedRule,
        rule2: EnhancedRule,
        score1: float,
        score2: float
    ) -> str:
        """Determine which factor was most decisive in ranking."""
        factors = []
        
        if rule1.recency_score != rule2.recency_score:
            diff = abs(rule1.recency_score - rule2.recency_score) * self.weights['recency']
            factors.append(('recency', diff))
        
        if rule1.specificity_score != rule2.specificity_score:
            diff = abs(rule1.specificity_score - rule2.specificity_score) * self.weights['specificity']
            factors.append(('specificity', diff))
        
        if factors:
            return max(factors, key=lambda x: x[1])[0]
        
        return "equal_priority"
