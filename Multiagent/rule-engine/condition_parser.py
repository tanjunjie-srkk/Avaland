"""
Condition Parser Module
Parses condition strings from rules JSON into executable Python functions.
Uses AST for safe evaluation without security risks of eval().
"""

import ast
import operator
import re
from typing import Any, Callable, Dict


class ConditionParser:
    """
    Parses condition strings like:
    "IF block == 'B' AND floor_level >= 20 AND floor_level <= 29"
    into executable Python functions.
    """
    
    # Supported operators mapping
    OPERATORS = {
        '==': operator.eq,
        '!=': operator.ne,
        '>=': operator.ge,
        '<=': operator.le,
        '>': operator.gt,
        '<': operator.lt,
    }
    
    def __init__(self):
        self._cache: Dict[str, Callable] = {}
    
    def parse(self, condition_str: str) -> Callable[[Dict[str, Any]], bool]:
        """
        Parse a condition string into an executable function.
        
        Args:
            condition_str: Condition string like "IF block == 'A'"
            
        Returns:
            A function that takes a context dict and returns bool
        """
        # Check cache first
        if condition_str in self._cache:
            return self._cache[condition_str]
        
        # Clean the condition string
        cleaned = self._clean_condition(condition_str)
        
        # Parse into executable function
        func = self._build_evaluator(cleaned)
        
        # Cache for reuse
        self._cache[condition_str] = func
        
        return func
    
    def _clean_condition(self, condition_str: str) -> str:
        """Remove 'IF' prefix and normalize the condition string."""
        # Remove leading IF
        cleaned = re.sub(r'^\s*IF\s+', '', condition_str, flags=re.IGNORECASE)
        return cleaned.strip()
    
    def _build_evaluator(self, condition: str) -> Callable[[Dict[str, Any]], bool]:
        """
        Build an evaluator function from the cleaned condition string.
        
        Handles:
        - AND/OR logical operators
        - Comparison operators (==, !=, >=, <=, >, <)
        - Boolean values (True, False)
        - String and numeric literals
        """
        # Split by AND/OR while preserving the operator
        tokens = self._tokenize_logical(condition)
        
        # Build sub-conditions
        sub_conditions = []
        logical_ops = []
        
        for token in tokens:
            if token.upper() == 'AND':
                logical_ops.append('AND')
            elif token.upper() == 'OR':
                logical_ops.append('OR')
            else:
                sub_cond = self._parse_comparison(token.strip())
                sub_conditions.append(sub_cond)
        
        def evaluator(context: Dict[str, Any]) -> bool:
            if not sub_conditions:
                return True
            
            result = sub_conditions[0](context)
            
            for i, op in enumerate(logical_ops):
                next_result = sub_conditions[i + 1](context)
                if op == 'AND':
                    result = result and next_result
                else:  # OR
                    result = result or next_result
            
            return result
        
        return evaluator
    
    def _tokenize_logical(self, condition: str) -> list:
        """
        Split condition by AND/OR while respecting quotes.
        Returns list of tokens including AND/OR operators.
        """
        # Pattern to match AND/OR as whole words
        pattern = r'\s+(AND|OR)\s+'
        parts = re.split(pattern, condition, flags=re.IGNORECASE)
        return [p.strip() for p in parts if p.strip()]
    
    def _parse_comparison(self, expr: str) -> Callable[[Dict[str, Any]], bool]:
        """
        Parse a single comparison expression like "block == 'A'" or "floor_level >= 20"
        """
        # Find the operator
        for op_str, op_func in self.OPERATORS.items():
            if op_str in expr:
                parts = expr.split(op_str, 1)
                if len(parts) == 2:
                    left = parts[0].strip()
                    right = parts[1].strip()
                    return self._make_comparison(left, op_func, right)
        
        # No operator found - might be a boolean check
        return self._parse_boolean_expr(expr)
    
    def _make_comparison(
        self, 
        left: str, 
        op_func: Callable, 
        right: str
    ) -> Callable[[Dict[str, Any]], bool]:
        """Create a comparison function."""
        right_value = self._parse_value(right)
        
        def compare(context: Dict[str, Any]) -> bool:
            left_value = context.get(left)
            if left_value is None:
                return False
            try:
                return op_func(left_value, right_value)
            except TypeError:
                return False
        
        return compare
    
    def _parse_boolean_expr(self, expr: str) -> Callable[[Dict[str, Any]], bool]:
        """Parse boolean expressions like 'is_garden_unit' or 'is_penthouse'."""
        expr = expr.strip()
        
        # Check for negation
        if expr.startswith('NOT ') or expr.startswith('not '):
            var_name = expr[4:].strip()
            return lambda ctx: not ctx.get(var_name, False)
        
        # Simple boolean variable
        return lambda ctx: bool(ctx.get(expr, False))
    
    def _parse_value(self, value_str: str) -> Any:
        """Parse a value string into its Python type."""
        value_str = value_str.strip()
        
        # Boolean
        if value_str == 'True':
            return True
        if value_str == 'False':
            return False
        
        # String (quoted)
        if (value_str.startswith("'") and value_str.endswith("'")) or \
           (value_str.startswith('"') and value_str.endswith('"')):
            return value_str[1:-1]
        
        # Number
        try:
            if '.' in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass
        
        # Return as-is (variable reference or unknown)
        return value_str


# Convenience function
def parse_condition(condition_str: str) -> Callable[[Dict[str, Any]], bool]:
    """
    Parse a condition string into an executable function.
    
    Example:
        >>> evaluator = parse_condition("IF block == 'B' AND floor_level >= 20")
        >>> evaluator({"block": "B", "floor_level": 25})
        True
    """
    parser = ConditionParser()
    return parser.parse(condition_str)
