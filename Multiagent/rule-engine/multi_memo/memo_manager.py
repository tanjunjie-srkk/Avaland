"""
Memo Manager Module
Manages loading, indexing, and filtering of multiple memos from various projects.
Provides traceability from rules back to their source memos.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import os
import re


class MemoType(Enum):
    """Types of memos that affect priority handling."""
    SUPERSEDING = "superseding"     # Completely replaces previous memo
    ADDENDUM = "addendum"           # Adds to existing rules
    AMENDMENT = "amendment"         # Modifies specific rules
    STANDARD = "standard"           # Regular memo


@dataclass
class MemoMetadata:
    """Metadata for a memo with traceability information."""
    memo_reference: str
    memo_file: str
    project_name: str
    effective_period: Dict[str, str]
    memo_type: MemoType = MemoType.STANDARD
    supersedes: Optional[str] = None  # Reference to memo this supersedes
    priority: int = 0  # Explicit priority (higher = more important)
    extraction_confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)
    
    @property
    def start_date(self) -> Optional[datetime]:
        """Parse and return the start date."""
        return self._parse_date(self.effective_period.get('start_date'))
    
    @property
    def end_date(self) -> Optional[datetime]:
        """Parse and return the end date."""
        return self._parse_date(self.effective_period.get('end_date'))
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string in various formats."""
        if not date_str:
            return None
        
        formats = [
            "%d %b %Y",     # "15 Jun 2025"
            "%d-%m-%Y",     # "15-06-2025"
            "%Y-%m-%d",     # "2025-06-15"
            "%d/%m/%Y",     # "15/06/2025"
            "%B %d, %Y",    # "June 15, 2025"
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        
        return None
    
    def is_effective_on(self, check_date: datetime) -> bool:
        """Check if memo is effective on the given date."""
        start = self.start_date
        end = self.end_date
        
        if start and check_date < start:
            return False
        if end and check_date > end:
            return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'memo_reference': self.memo_reference,
            'memo_file': self.memo_file,
            'project_name': self.project_name,
            'effective_period': self.effective_period,
            'memo_type': self.memo_type.value,
            'supersedes': self.supersedes,
            'priority': self.priority,
            'extraction_confidence': self.extraction_confidence,
            'warnings': self.warnings
        }


@dataclass
class EnhancedRule:
    """
    Rule with enhanced metadata for multi-memo tracking.
    Extends the base Rule concept with memo traceability.
    """
    rule_id: str
    rule_name: str
    rule_type: str
    conditions: List[Dict[str, Any]]
    raw_data: Dict[str, Any]
    
    # Memo traceability
    memo_metadata: MemoMetadata = None
    
    # Priority and conflict resolution
    priority_score: float = 0.0
    specificity_score: float = 0.0
    recency_score: float = 0.0
    
    # Optional fields based on rule type
    buyer_type: Optional[str] = None
    rebate_type: Optional[str] = None
    referrer_category: Optional[str] = None
    adjustment_type: Optional[str] = None
    package_type: Optional[str] = None
    
    # Conflict tracking
    superseded_by: Optional[str] = None  # Rule ID that supersedes this
    conflicts_with: List[str] = field(default_factory=list)
    
    @property
    def composite_id(self) -> str:
        """Unique ID combining rule ID and memo reference."""
        memo_ref = self.memo_metadata.memo_reference if self.memo_metadata else "unknown"
        return f"{memo_ref}::{self.rule_id}"
    
    @property
    def project_name(self) -> str:
        """Get project name from memo metadata."""
        return self.memo_metadata.project_name if self.memo_metadata else ""
    
    def get_total_priority(self) -> float:
        """Calculate total priority score for ranking."""
        # Weighted combination of priority factors
        explicit_priority = (self.memo_metadata.priority if self.memo_metadata else 0) * 100
        return (
            self.recency_score * 0.40 +
            self.specificity_score * 0.30 +
            explicit_priority * 0.20 +
            self.priority_score * 0.10
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with memo metadata."""
        result = {
            'rule_id': self.rule_id,
            'composite_id': self.composite_id,
            'rule_name': self.rule_name,
            'rule_type': self.rule_type,
            'conditions': self.conditions,
            'priority_score': self.get_total_priority(),
            'specificity_score': self.specificity_score,
            'recency_score': self.recency_score,
        }
        
        if self.memo_metadata:
            result['memo'] = self.memo_metadata.to_dict()
        
        if self.superseded_by:
            result['superseded_by'] = self.superseded_by
        
        if self.conflicts_with:
            result['conflicts_with'] = self.conflicts_with
        
        return result


@dataclass
class Memo:
    """Represents a complete memo with its rules and metadata."""
    metadata: MemoMetadata
    raw_data: Dict[str, Any]
    rules: List[EnhancedRule] = field(default_factory=list)
    
    @classmethod
    def from_file(cls, file_path: str) -> 'Memo':
        """Load a memo from a JSON file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract metadata
        memo_type = MemoType.STANDARD
        if 'memo_type' in data:
            try:
                memo_type = MemoType(data['memo_type'])
            except ValueError:
                pass
        
        metadata = MemoMetadata(
            memo_reference=data.get('memo_reference', Path(file_path).stem),
            memo_file=str(file_path),
            project_name=data.get('project_name', ''),
            effective_period=data.get('effective_period', {}),
            memo_type=memo_type,
            supersedes=data.get('supersedes'),
            priority=data.get('priority', 0),
            extraction_confidence=data.get('extraction_confidence', 0.0),
            warnings=data.get('warnings', [])
        )
        
        memo = cls(metadata=metadata, raw_data=data)
        memo._load_rules()
        
        return memo
    
    def _load_rules(self):
        """Load and enhance rules from raw data."""
        rules_section = self.raw_data.get('rules', {})
        
        # Load each rule category
        self._load_rules_category(rules_section.get('commission_rules', []), 'commission')
        self._load_rules_category(rules_section.get('rebate_rules', []), 'rebate')
        self._load_rules_category(rules_section.get('referral_rules', []), 'referral')
        self._load_rules_category(rules_section.get('price_adjustment_rules', []), 'price_adjustment')
        self._load_rules_category(rules_section.get('package_rules', []), 'package')
    
    def _load_rules_category(self, rules_data: List[Dict], rule_type: str):
        """Load rules of a specific category."""
        for rule_data in rules_data:
            # Handle referral rules with string conditions
            conditions = rule_data.get('conditions', [])
            if conditions and isinstance(conditions[0], str):
                conditions = [{'description': c} for c in conditions]
            
            rule = EnhancedRule(
                rule_id=rule_data['rule_id'],
                rule_name=rule_data['rule_name'],
                rule_type=rule_type,
                conditions=conditions,
                raw_data=rule_data,
                memo_metadata=self.metadata,
                buyer_type=rule_data.get('buyer_type'),
                rebate_type=rule_data.get('rebate_type'),
                referrer_category=rule_data.get('referrer_category'),
                adjustment_type=rule_data.get('adjustment_type'),
                package_type=rule_data.get('package_type')
            )
            
            # Calculate specificity score
            rule.specificity_score = self._calculate_specificity(rule)
            
            self.rules.append(rule)
    
    def _calculate_specificity(self, rule: EnhancedRule) -> float:
        """Calculate specificity score based on condition complexity."""
        score = 0.0
        
        for condition in rule.conditions:
            if isinstance(condition, dict) and 'condition' in condition:
                cond_str = condition['condition']
                # Count AND clauses
                and_count = cond_str.upper().count(' AND ')
                # Count comparison operators
                comp_count = len(re.findall(r'(==|>=|<=|>|<|!=)', cond_str))
                
                score += 0.2 + (and_count * 0.15) + (comp_count * 0.1)
        
        return min(score, 1.0)


class MemoManager:
    """
    Manages multiple memos with indexing, filtering, and retrieval capabilities.
    """
    
    def __init__(self, artifacts_path: Optional[str] = None):
        self.artifacts_path = Path(artifacts_path) if artifacts_path else None
        self.memos: Dict[str, Memo] = {}  # memo_reference -> Memo
        
        # Indexes for fast lookup
        self._by_project: Dict[str, List[str]] = {}  # project_name -> [memo_refs]
        self._by_date: List[Tuple[datetime, str]] = []  # [(start_date, memo_ref)]
        self._supersession_chain: Dict[str, str] = {}  # superseded_memo -> superseding_memo
    
    def load_all_memos(self, directory: Optional[str] = None) -> int:
        """
        Load all memo JSON files from a directory.
        
        Returns:
            Number of memos loaded
        """
        dir_path = Path(directory) if directory else self.artifacts_path
        if not dir_path:
            raise ValueError("No directory specified for loading memos")
        
        count = 0
        for file_path in dir_path.glob("*.json"):
            try:
                memo = Memo.from_file(str(file_path))
                self.add_memo(memo)
                count += 1
            except Exception as e:
                print(f"Warning: Failed to load {file_path}: {e}")
        
        # Calculate recency scores after loading all memos
        self._calculate_recency_scores()
        
        return count
    
    def add_memo(self, memo: Memo):
        """Add a memo to the manager and update indexes."""
        ref = memo.metadata.memo_reference
        self.memos[ref] = memo
        
        # Index by project
        project = memo.metadata.project_name
        if project not in self._by_project:
            self._by_project[project] = []
        self._by_project[project].append(ref)
        
        # Index by date
        if memo.metadata.start_date:
            self._by_date.append((memo.metadata.start_date, ref))
            self._by_date.sort(key=lambda x: x[0], reverse=True)  # Most recent first
        
        # Track supersession
        if memo.metadata.supersedes:
            self._supersession_chain[memo.metadata.supersedes] = ref
    
    def _calculate_recency_scores(self):
        """Calculate recency scores for all rules based on memo dates."""
        if not self._by_date:
            return
        
        # Get the date range
        dates = [d for d, _ in self._by_date if d]
        if not dates:
            return
        
        newest = max(dates)
        oldest = min(dates)
        date_range = (newest - oldest).days or 1
        
        for memo in self.memos.values():
            start_date = memo.metadata.start_date
            if start_date:
                # Normalize to 0-1 scale (1 = newest)
                days_from_oldest = (start_date - oldest).days
                recency = days_from_oldest / date_range
            else:
                recency = 0.5  # Default middle value
            
            # Apply recency score to all rules in this memo
            for rule in memo.rules:
                rule.recency_score = recency
    
    def filter_by_date(
        self,
        target_date: datetime,
        memos: Optional[List[str]] = None
    ) -> List[str]:
        """
        Filter memos that are effective on the target date.
        
        Args:
            target_date: The date to check (typically SPA date)
            memos: Optional list of memo references to filter (None = all)
        
        Returns:
            List of memo references that are effective
        """
        refs_to_check = memos if memos else list(self.memos.keys())
        
        return [
            ref for ref in refs_to_check
            if ref in self.memos and self.memos[ref].metadata.is_effective_on(target_date)
        ]
    
    def filter_by_project(
        self,
        project_name: str,
        memos: Optional[List[str]] = None,
        fuzzy_match: bool = True
    ) -> List[str]:
        """
        Filter memos by project name.
        
        Args:
            project_name: The project name to match
            memos: Optional list of memo references to filter
            fuzzy_match: Whether to use fuzzy matching (partial match)
        
        Returns:
            List of memo references for the project
        """
        refs_to_check = memos if memos else list(self.memos.keys())
        
        if fuzzy_match:
            project_lower = project_name.lower()
            return [
                ref for ref in refs_to_check
                if ref in self.memos and
                (project_lower in self.memos[ref].metadata.project_name.lower() or
                 self.memos[ref].metadata.project_name.lower() in project_lower)
            ]
        else:
            return [
                ref for ref in refs_to_check
                if ref in self.memos and 
                self.memos[ref].metadata.project_name == project_name
            ]
    
    def filter_memos(
        self,
        project_name: Optional[str] = None,
        target_date: Optional[datetime] = None,
        memo_types: Optional[List[MemoType]] = None
    ) -> List[Memo]:
        """
        Apply multiple filters to get relevant memos.
        
        Args:
            project_name: Filter by project name
            target_date: Filter by effective date
            memo_types: Filter by memo types
        
        Returns:
            List of filtered Memo objects
        """
        memo_refs = list(self.memos.keys())
        
        # Apply project filter
        if project_name:
            memo_refs = self.filter_by_project(project_name, memo_refs)
        
        # Apply date filter
        if target_date:
            memo_refs = self.filter_by_date(target_date, memo_refs)
        
        # Apply memo type filter
        if memo_types:
            memo_refs = [
                ref for ref in memo_refs
                if self.memos[ref].metadata.memo_type in memo_types
            ]
        
        return [self.memos[ref] for ref in memo_refs]
    
    def get_memo(self, memo_reference: str) -> Optional[Memo]:
        """Get a memo by its reference."""
        return self.memos.get(memo_reference)
    
    def get_all_projects(self) -> List[str]:
        """Get list of all project names."""
        return list(self._by_project.keys())
    
    def get_superseding_memo(self, memo_reference: str) -> Optional[str]:
        """Get the memo that supersedes the given memo."""
        return self._supersession_chain.get(memo_reference)
    
    def get_memo_chain(self, memo_reference: str) -> List[str]:
        """Get the chain of memos (from oldest to newest) for a supersession chain."""
        chain = [memo_reference]
        current = memo_reference
        
        while current in self._supersession_chain:
            current = self._supersession_chain[current]
            chain.append(current)
        
        return chain
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about loaded memos."""
        total_rules = sum(len(m.rules) for m in self.memos.values())
        rules_by_type = {}
        
        for memo in self.memos.values():
            for rule in memo.rules:
                if rule.rule_type not in rules_by_type:
                    rules_by_type[rule.rule_type] = 0
                rules_by_type[rule.rule_type] += 1
        
        return {
            'total_memos': len(self.memos),
            'total_rules': total_rules,
            'projects': list(self._by_project.keys()),
            'rules_by_type': rules_by_type,
            'date_range': {
                'earliest': min((d for d, _ in self._by_date), default=None),
                'latest': max((d for d, _ in self._by_date), default=None)
            }
        }
