"""
Rule Engine Module
Orchestrates the full rule matching and calculation flow.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

from rule_loader import RuleLoader, RuleLibrary, load_rules
from rule_matcher import RuleMatcher, MatchedRule, find_matching_rules
from condition_parser import ConditionParser


@dataclass
class CalculationResult:
    """Result of a calculation based on matched rules."""
    rule_type: str
    rule_id: str
    rule_name: str
    description: str
    value: float
    value_type: str  # 'percentage' or 'fixed'
    calculated_amount: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)
    # Memo tracking for transparency
    memo_reference: Optional[str] = None
    memo_file: Optional[str] = None
    effective_period: Optional[Dict[str, str]] = None


@dataclass
class PricingResult:
    """Complete pricing calculation result."""
    base_price: float
    final_price: float
    total_rebate: float
    total_commission: float
    rebate_breakdown: List[CalculationResult] = field(default_factory=list)
    commission_breakdown: List[CalculationResult] = field(default_factory=list)
    price_adjustments: List[CalculationResult] = field(default_factory=list)
    applicable_packages: List[str] = field(default_factory=list)
    matched_rules: List[str] = field(default_factory=list)
    # Memo context for transparency
    memo_reference: Optional[str] = None
    memo_file: Optional[str] = None
    effective_period: Optional[Dict[str, str]] = None
    spa_date: Optional[str] = None


class RuleEngine:
    """
    Main rule engine that orchestrates rule matching and calculations.
    
    Usage:
        engine = RuleEngine('path/to/extracted-rules.json')
        context = {
            "buyer_type": "local",
            "block": "B",
            "floor_level": 25,
            "unit_type": "A1",
            "buyer_is_bumi": True,
            "base_price": 1000000
        }
        result = engine.calculate(context)
    """
    
    def __init__(self, rules_path: str, memo_file: Optional[str] = None):
        self.loader = RuleLoader(rules_path)
        self.library = self.loader.load()
        self.matcher = RuleMatcher(self.library)
        self.metadata = self.loader.get_metadata()
        # Store memo context for transparency
        self.memo_file = memo_file or Path(rules_path).name
        self.memo_reference = self.metadata.get('memo_reference', 'Unknown')
        self.effective_period = self.metadata.get('effective_period', {})
    
    def get_applicable_rules(
        self, 
        context: Dict[str, Any],
        rule_types: Optional[List[str]] = None
    ) -> Dict[str, List[MatchedRule]]:
        """
        Get all applicable rules for the given context.
        
        Args:
            context: User input context
            rule_types: Optional filter for specific rule types
        
        Returns:
            Dictionary of rule type -> list of matched rules
        """
        if rule_types:
            matches = self.matcher.match(context, rule_types)
            result = {}
            for m in matches:
                if m.rule_type not in result:
                    result[m.rule_type] = []
                result[m.rule_type].append(m)
            return result
        
        return self.matcher.match_all_applicable(context)
    
    def calculate(self, context: Dict[str, Any]) -> PricingResult:
        """
        Perform full pricing calculation based on matched rules.
        
        Required context fields:
            - base_price: The list/base price of the unit
        
        Optional context fields:
            - buyer_type: 'local' or 'foreign'
            - block: 'A' or 'B'
            - floor_level: integer
            - unit_type: 'A1', 'A2', 'B1', 'B2', etc.
            - buyer_is_bumi: boolean
            - is_garden_unit: boolean
            - is_penthouse: boolean
            - loan_purchase: boolean
            - marketing_event: boolean
        """
        base_price = context.get('base_price', 0)
        
        # Get all applicable rules
        all_matches = self.get_applicable_rules(context)
        
        # Calculate rebates
        rebate_breakdown = []
        total_rebate = 0.0
        
        for match in all_matches.get('rebate', []):
            result = self._calculate_rebate(match, base_price, total_rebate)
            if result:
                rebate_breakdown.append(result)
                if result.calculated_amount:
                    total_rebate += result.calculated_amount
        
        # Calculate commission
        commission_breakdown = []
        total_commission = 0.0
        net_price = base_price - total_rebate
        
        for match in all_matches.get('commission', []):
            result = self._calculate_commission(match, net_price, context)
            if result:
                commission_breakdown.append(result)
                if result.calculated_amount:
                    total_commission += result.calculated_amount
        
        # Calculate price adjustments
        price_adjustments = []
        for match in all_matches.get('price_adjustment', []):
            result = self._calculate_price_adjustment(match)
            if result:
                price_adjustments.append(result)
        
        # Get applicable packages
        applicable_packages = [
            m.rule_name for m in all_matches.get('package', [])
        ]
        
        # Compile matched rule IDs
        matched_rules = []
        for matches in all_matches.values():
            matched_rules.extend([m.rule_id for m in matches])
        
        # Calculate final price
        adjustment_total = sum(
            r.calculated_amount or 0 for r in price_adjustments
        )
        final_price = base_price + adjustment_total - total_rebate
        
        return PricingResult(
            base_price=base_price,
            final_price=final_price,
            total_rebate=total_rebate,
            total_commission=total_commission,
            rebate_breakdown=rebate_breakdown,
            commission_breakdown=commission_breakdown,
            price_adjustments=price_adjustments,
            applicable_packages=applicable_packages,
            matched_rules=matched_rules,
            # Add memo context for transparency
            memo_reference=self.memo_reference,
            memo_file=self.memo_file,
            effective_period=self.effective_period,
            spa_date=context.get('spa_date')  # Will be string if provided
        )
    
    def _calculate_rebate(
        self, 
        match: MatchedRule, 
        base_price: float,
        accumulated_rebate: float
    ) -> Optional[CalculationResult]:
        """Calculate rebate from a matched rebate rule."""
        percentage = match.get_percentage()
        if percentage is None:
            return None
        
        # Determine calculation base
        calc_base = match.rule.raw_data.get('calculation_base', 'Net Price')
        
        if 'after Bumi' in calc_base:
            # Calculate on price after bumi rebate
            effective_price = base_price - accumulated_rebate
        else:
            effective_price = base_price
        
        calculated_amount = effective_price * (percentage / 100)
        
        return CalculationResult(
            rule_type='rebate',
            rule_id=match.rule_id,
            rule_name=match.rule_name,
            description=match.get_value('description', ''),
            value=percentage,
            value_type='percentage',
            calculated_amount=calculated_amount,
            details={
                'calculation_base': calc_base,
                'effective_price': effective_price
            },
            # Add memo tracking
            memo_reference=self.memo_reference,
            memo_file=self.memo_file,
            effective_period=self.effective_period
        )
    
    def _calculate_commission(
        self, 
        match: MatchedRule, 
        net_price: float,
        context: Dict[str, Any]
    ) -> Optional[CalculationResult]:
        """Calculate commission from a matched commission rule."""
        percentage = match.get_percentage()
        if percentage is None:
            return None
        
        # For foreign buyers, deduct package value
        commission_base = net_price
        if context.get('buyer_type') == 'foreign':
            commission_base = net_price - 200000  # Partially furnished package
        
        calculated_amount = commission_base * (percentage / 100)
        
        # Commission payout split
        payout_spa = calculated_amount * 0.30
        payout_stage2a = calculated_amount * 0.70
        
        return CalculationResult(
            rule_type='commission',
            rule_id=match.rule_id,
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
            # Add memo tracking
            memo_reference=self.memo_reference,
            memo_file=self.memo_file,
            effective_period=self.effective_period
        )
    
    def _calculate_price_adjustment(
        self, 
        match: MatchedRule
    ) -> Optional[CalculationResult]:
        """Calculate price adjustment from a matched rule."""
        amount = match.get_amount()
        if amount is None:
            amount = match.get_value('adjustment_amount', 0)
        
        return CalculationResult(
            rule_type='price_adjustment',
            rule_id=match.rule_id,
            rule_name=match.rule_name,
            description=match.get_value('description', ''),
            value=amount,
            value_type='fixed',
            calculated_amount=amount,
            details={},
            # Add memo tracking
            memo_reference=self.memo_reference,
            memo_file=self.memo_file,
            effective_period=self.effective_period
        )
    
    def explain_rules(self, context: Dict[str, Any]) -> str:
        """
        Generate a human-readable explanation of which rules apply and why.
        """
        all_matches = self.get_applicable_rules(context)
        
        lines = [
            f"Rule Analysis for Context:",
            f"{'='*50}",
            ""
        ]
        
        for key, value in context.items():
            lines.append(f"  {key}: {value}")
        
        lines.append("")
        lines.append(f"{'='*50}")
        lines.append("")
        
        for rule_type, matches in all_matches.items():
            lines.append(f"📋 {rule_type.upper()} RULES ({len(matches)} matched)")
            lines.append("-" * 40)
            
            for match in matches:
                lines.append(f"  ✓ {match.rule_name} ({match.rule_id})")
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
                lines.append("")
            
            lines.append("")
        
        if not any(all_matches.values()):
            lines.append("No rules matched the given context.")
        
        return "\n".join(lines)
    
    def list_all_rules(self) -> Dict[str, List[Dict[str, Any]]]:
        """List all available rules in the library."""
        result = {}
        
        for rule_type in self.library.get_all_types():
            rules = self.library.get_by_type(rule_type)
            result[rule_type] = [
                {
                    'rule_id': r.rule_id,
                    'rule_name': r.rule_name,
                    'conditions_count': len(r.conditions)
                }
                for r in rules
            ]
        
        return result


# Convenience function
def create_engine(rules_path: str) -> RuleEngine:
    """Create a RuleEngine instance."""
    return RuleEngine(rules_path)
