"""
Multi-Memo Rule Engine Demo - Streamlit UI
Transparent Commission & Rebate Calculation System with Multi-Memo Support

Focus: Transparency for finance stakeholders
- Clear input → rule matching → calculation flow
- Visual step-by-step breakdown
- Conflict resolution visualization
- Audit trail for every calculation
"""

import streamlit as st
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from datetime import date, datetime

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from multi_memo_engine import (
    MultiMemoRuleEngine, 
    create_multi_memo_engine,
    MultiMemoPricingResult,
    MultiMemoCalculationResult,
    MatchedEnhancedRule
)
from rule_aggregator import ConflictType, ConflictResolution, RuleConflict
from memo_manager import MemoType

# Page configuration
st.set_page_config(
    page_title="Avaland Commission Calculator",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better visualization
st.markdown("""
<style>
    .main-header {
        font-size: 2.8rem;
        font-weight: bold;
        color: #1E3A5F;
        text-align: center;
        padding: 1.5rem;
        border-bottom: 4px solid #E8B54B;
        margin-bottom: 1rem;
        background: linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%);
    }
    .executive-summary {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        color: white;
        padding: 2.5rem;
        border-radius: 16px;
        margin: 1.5rem 0;
        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
    }
    .executive-metric {
        background: rgba(255,255,255,0.1);
        backdrop-filter: blur(10px);
        padding: 1.5rem;
        border-radius: 12px;
        text-align: center;
        border: 1px solid rgba(255,255,255,0.2);
    }
    .executive-metric-value {
        font-size: 2rem;
        font-weight: bold;
        color: #4ade80;
    }
    .executive-metric-label {
        font-size: 0.9rem;
        color: rgba(255,255,255,0.8);
        margin-top: 0.5rem;
    }
    .step-header {
        background: linear-gradient(90deg, #1E3A5F 0%, #2E5A8F 100%);
        color: white;
        padding: 0.8rem 1.2rem;
        border-radius: 8px;
        font-size: 1.2rem;
        font-weight: bold;
        margin: 1rem 0;
    }
    .rule-card {
        background: #f8f9fa;
        border-left: 4px solid #28a745;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
    }
    .rule-card-inactive {
        background: #f8f9fa;
        border-left: 4px solid #dee2e6;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
        opacity: 0.6;
    }
    .conflict-card {
        background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
        border-left: 4px solid #f39c12;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
    }
    .conflict-resolved {
        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        border-left: 4px solid #28a745;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
    }
    .conflict-superseded {
        background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
        border-left: 4px solid #dc3545;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
        opacity: 0.7;
    }
    .memo-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: bold;
        margin: 0.2rem;
    }
    .memo-badge-project {
        background: #17a2b8;
        color: white;
    }
    .memo-badge-base {
        background: #6c757d;
        color: white;
    }
    .memo-badge-latest {
        background: #28a745;
        color: white;
    }
    .priority-bar {
        height: 8px;
        border-radius: 4px;
        background: #e9ecef;
        overflow: hidden;
    }
    .priority-fill {
        height: 100%;
        border-radius: 4px;
        transition: width 0.3s ease;
    }
    .calculation-step {
        background: #fff3cd;
        border: 1px solid #ffc107;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 8px;
    }
    .match-reason {
        background: #d4edda;
        color: #155724;
        padding: 0.5rem 1rem;
        border-radius: 4px;
        font-size: 0.9rem;
        margin-top: 0.5rem;
    }
    .no-match-reason {
        background: #f8d7da;
        color: #721c24;
        padding: 0.5rem 1rem;
        border-radius: 4px;
        font-size: 0.9rem;
        margin-top: 0.5rem;
    }
    .transparency-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 12px;
        margin: 1rem 0;
    }
    .formula-box {
        background: #e7f3ff;
        border: 2px solid #0066cc;
        padding: 1rem;
        border-radius: 8px;
        font-family: 'Courier New', monospace;
        margin: 0.5rem 0;
    }
    .highlight-value {
        background: #fff3cd;
        padding: 0.2rem 0.5rem;
        border-radius: 4px;
        font-weight: bold;
    }
    .result-summary {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        color: white;
        padding: 2rem;
        border-radius: 12px;
        text-align: center;
    }
    .pipeline-step {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border: 2px solid #dee2e6;
        padding: 1rem;
        border-radius: 12px;
        margin: 0.5rem 0;
        text-align: center;
    }
    .pipeline-step-active {
        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        border: 2px solid #28a745;
    }
    .pipeline-arrow {
        font-size: 2rem;
        color: #6c757d;
        text-align: center;
        padding: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_currency(amount: float) -> str:
    """Format amount as Malaysian Ringgit."""
    return f"RM {amount:,.2f}"


@st.cache_resource
def load_multi_memo_engine():
    """Load the multi-memo engine with caching."""
    # app is at: rule-engine/multi_memo/app_multi_memo.py
    # artifacts at: Multiagent/artifact/  (3 levels up from multi_memo/)
    artifacts_path = Path(__file__).parent.parent.parent / "artifact"
    engine = create_multi_memo_engine(str(artifacts_path))
    return engine


def get_conflict_type_color(conflict_type: ConflictType) -> str:
    """Get color for conflict type."""
    colors = {
        ConflictType.SAME_RULE_ID: "#f39c12",
        ConflictType.OVERLAPPING_CONDITIONS: "#e74c3c",
        ConflictType.CONTRADICTORY: "#c0392b",
        ConflictType.SUPERSEDED: "#95a5a6"
    }
    return colors.get(conflict_type, "#6c757d")


def get_resolution_icon(resolution: ConflictResolution) -> str:
    """Get icon for resolution strategy."""
    icons = {
        ConflictResolution.LATEST_WINS: "🕐",
        ConflictResolution.HIGHEST_PRIORITY: "⭐",
        ConflictResolution.MOST_SPECIFIC: "🎯",
        ConflictResolution.MERGE: "🔀",
        ConflictResolution.MANUAL_REVIEW: "👁️"
    }
    return icons.get(resolution, "❓")


# ============================================================================
# RENDER FUNCTIONS - HEADER & INPUT
# ============================================================================

def render_header():
    """Render the main header."""
    st.markdown("""
    <div class="main-header">
        🏢 Avaland Commission Calculator
        <div style="font-size: 1rem; color: #666; font-weight: normal; margin-top: 0.5rem;">
            Comission Calculation with Transparency & Conflict Resolution
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_input_section(engine: MultiMemoRuleEngine) -> Dict[str, Any]:
    """Render the input form and return user context."""
    st.markdown('<div class="step-header">📝 Step 1: Enter Property & Buyer Details</div>', unsafe_allow_html=True)
    
    # SPA Signed Date - determines which memo to use
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 1rem 1.5rem; border-radius: 12px; margin-bottom: 1rem;">
        <div style="color: #a0aec0; font-size: 0.8rem; margin-bottom: 0.25rem;">📅 SPA SIGNED DATE</div>
        <div style="color: #e2e8f0; font-size: 0.75rem;">The system will filter applicable memos based on this date</div>
    </div>
    """, unsafe_allow_html=True)
    
    col_date1, col_date2 = st.columns([1, 2])
    with col_date1:
        spa_date = st.date_input(
            "Date of SPA Signing",
            value=date.today(),
            help="The date when the Sale & Purchase Agreement was signed."
        )
    with col_date2:
        # Get available projects from memos
        available_projects = sorted(set(
            memo.metadata.project_name 
            for memo in engine.memo_manager.memos.values()
            if memo.metadata.project_name
        ))
        
        project_options = ["All Projects"] + available_projects
        
        project_filter = st.selectbox(
            "Project Name",
            options=project_options,
            index=0,
            help="Select a specific project or 'All Projects' to include all memos."
        )
        
        # Convert "All Projects" back to None for filtering
        project_filter = None if project_filter == "All Projects" else project_filter
    
    st.markdown("---")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("💰 Property Details")
        base_price = st.number_input(
            "List Price (RM)",
            min_value=100000,
            max_value=10000000,
            value=1500000,
            step=50000,
            help="The original list price of the property unit"
        )
        
        block = st.selectbox(
            "Block",
            options=["A", "B"],
            help="Block A or Block B - different commission structures apply"
        )
        
        floor_level = st.slider(
            "Floor Level",
            min_value=10,
            max_value=40,
            value=25,
            help="Floor level affects commission and rebate tiers"
        )
    
    with col2:
        st.subheader("👤 Buyer Profile")
        buyer_type = st.selectbox(
            "Buyer Type",
            options=["Local", "Foreign"],
            help="Local vs Foreign buyers have different pricing packages"
        )
        
        buyer_is_bumi = st.checkbox(
            "Bumiputera Buyer",
            value=False,
            help="Bumiputera buyers qualify for additional 5% rebate"
        )
        
        unit_type = st.selectbox(
            "Unit Type",
            options=["A1", "A2", "B1", "B2"],
            help="Unit type determines standard rebate percentage"
        )
    
    with col3:
        st.subheader("🏠 Unit Attributes")
        is_garden_unit = st.checkbox(
            "Garden Unit (Level 10)",
            value=False,
            help="Special units with garden access"
        )
        
        is_penthouse = st.checkbox(
            "Penthouse",
            value=False,
            help="Top floor penthouse units"
        )
        
        loan_purchase = st.checkbox(
            "Loan Purchase",
            value=False,
            help="Additional 1% rebate for loan purchases"
        )
    
    # Build context
    context = {
        "spa_date": spa_date,
        "project_filter": project_filter if project_filter else None,
        "base_price": base_price,
        "block": block,
        "floor_level": floor_level,
        "buyer_type": buyer_type.lower(),
        "buyer_is_bumi": buyer_is_bumi,
        "unit_type": unit_type,
        "is_garden_unit": is_garden_unit,
        "is_penthouse": is_penthouse,
        "loan_purchase": loan_purchase,
    }
    
    return context


# ============================================================================
# RENDER FUNCTIONS - CONFLICT RESOLUTION VISUALIZATION
# ============================================================================

def explain_condition_match(condition_str: str, context: Dict[str, Any]) -> str:
    """Generate human-readable explanation of why a condition matched or didn't."""
    # Handle case where condition_str might be a dict
    if isinstance(condition_str, dict):
        condition_str = condition_str.get('condition', str(condition_str))
    
    if not isinstance(condition_str, str):
        return "Condition format not recognized"
    
    explanations = []
    
    # Remove "IF " prefix
    clean_cond = condition_str.replace("IF ", "").strip()
    
    # Split by AND/OR
    parts = clean_cond.replace(" AND ", "|AND|").replace(" OR ", "|OR|").split("|")
    
    for part in parts:
        if part in ["AND", "OR"]:
            continue
        
        part = part.strip()
        
        # Parse comparison
        for op in ["==", "!=", ">=", "<=", ">", "<"]:
            if op in part:
                left, right = part.split(op, 1)
                left = left.strip()
                right = right.strip().strip("'\"")
                
                actual_value = context.get(left, "N/A")
                
                # Determine if this part matched
                try:
                    if op == "==":
                        matched = str(actual_value) == right or actual_value == right
                    elif op == ">=":
                        matched = float(actual_value) >= float(right)
                    elif op == "<=":
                        matched = float(actual_value) <= float(right)
                    elif op == ">":
                        matched = float(actual_value) > float(right)
                    elif op == "<":
                        matched = float(actual_value) < float(right)
                    else:
                        matched = False
                except:
                    matched = False
                
                status = "✓" if matched else "✗"
                explanations.append(f"{status} Your {left} = '{actual_value}' (rule requires {op} '{right}')")
                break
    
    return " | ".join(explanations) if explanations else "Condition evaluated"


def render_rule_matching_details(engine: MultiMemoRuleEngine, result: MultiMemoPricingResult, context: Dict[str, Any]):
    """Render detailed rule matching information showing which rules applied and why."""
    st.markdown('<div class="step-header">🎯 View Rule Matching Details - Which rules were applied and why</div>', unsafe_allow_html=True)
    
    st.markdown("""
    <div style="background: #e7f3ff; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
        <strong>How Rule Matching Works:</strong><br>
        Each rule has specific conditions. We evaluate your inputs against all rules to find which ones apply. 
        <span style="color: green;">✓ Green</span> = Rule applies | 
        <span style="color: gray;">Gray</span> = Rule does not apply
    </div>
    """, unsafe_allow_html=True)
    
    # Get matched rule IDs
    matched_ids = {rule.rule_id for rule in result.rebate_breakdown + result.commission_breakdown}
    
    # Show commission rules
    st.markdown("#### 💼 Commission Rules")
    all_commission_rules = engine.library.get_by_type('commission')
    
    if not all_commission_rules:
        st.info("No commission rules available")
    else:
        for rule in all_commission_rules:
            is_matched = rule.rule_id in matched_ids
            card_class = "rule-card" if is_matched else "rule-card-inactive"
            icon = "✅" if is_matched else "✗"
            
            st.markdown(f"""
            <div class="{card_class}">
                <strong>{icon} {rule.rule_name}</strong> ({rule.rule_id})
            </div>
            """, unsafe_allow_html=True)
            
            # Show conditions with explanations
            if rule.conditions:
                for cond in rule.conditions:
                    # Extract condition string and percentage
                    if isinstance(cond, dict):
                        cond_text = cond.get('condition', str(cond))
                        percentage = cond.get('commission_percentage', 'N/A')
                    elif isinstance(cond, list):
                        cond_text = cond[0] if cond else "Unknown condition"
                        percentage = 'N/A'
                    else:
                        cond_text = str(cond)
                        percentage = 'N/A'
                    
                    match_explanation = explain_condition_match(cond_text, context)
                    
                    # Check if THIS specific condition matches - ALL parts must pass (no ✗)
                    condition_matches = "✗" not in match_explanation
                    
                    if condition_matches:
                        st.markdown(f"""
                        <div class="match-reason">
                            <strong>Condition:</strong> {cond_text}<br>
                            <strong>Commission:</strong> {percentage}%<br>
                            <strong>Why Matched:</strong> {match_explanation}
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="no-match-reason">
                            <strong>Condition:</strong> {cond_text}<br>
                            <strong>Commission:</strong> {percentage}%<br>
                            <strong>Why Not Matched:</strong> {match_explanation}
                        </div>
                        """, unsafe_allow_html=True)
    
    # Show rebate rules
    st.markdown("#### 🎁 Rebate Rules")
    all_rebate_rules = engine.library.get_by_type('rebate')
    
    if not all_rebate_rules:
        st.info("No rebate rules available")
    else:
        for rule in all_rebate_rules:
            is_matched = rule.rule_id in matched_ids
            card_class = "rule-card" if is_matched else "rule-card-inactive"
            icon = "✅" if is_matched else "✗"
            
            st.markdown(f"""
            <div class="{card_class}">
                <strong>{icon} {rule.rule_name}</strong> ({rule.rule_id})
            </div>
            """, unsafe_allow_html=True)
            
            # Show conditions with explanations
            if rule.conditions:
                for cond in rule.conditions:
                    # Extract condition string and percentage
                    if isinstance(cond, dict):
                        cond_text = cond.get('condition', str(cond))
                        percentage = cond.get('rebate_percentage', 'N/A')
                    elif isinstance(cond, list):
                        cond_text = cond[0] if cond else "Unknown condition"
                        percentage = 'N/A'
                    else:
                        cond_text = str(cond)
                        percentage = 'N/A'
                    
                    match_explanation = explain_condition_match(cond_text, context)
                    
                    # Check if THIS specific condition matches - ALL parts must pass (no ✗)
                    condition_matches = "✗" not in match_explanation
                    
                    if condition_matches:
                        st.markdown(f"""
                        <div class="match-reason">
                            <strong>Condition:</strong> {cond_text}<br>
                            <strong>Rebate:</strong> {percentage}%<br>
                            <strong>Why Matched:</strong> {match_explanation}
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="no-match-reason">
                            <strong>Condition:</strong> {cond_text}<br>
                            <strong>Rebate:</strong> {percentage}%<br>
                            <strong>Why Not Matched:</strong> {match_explanation}
                        </div>
                        """, unsafe_allow_html=True)


def render_detailed_calculation_breakdown(result: MultiMemoPricingResult):
    """Render step-by-step calculation with full transparency and formula details."""
    st.markdown('<div class="step-header">📋 View Calculation Details - Step-by-Step Formula Breakdown</div>', unsafe_allow_html=True)
    
    st.markdown("""
    <div style="background: #d4edda; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
        <strong>Calculation Transparency:</strong> Every number is traceable. 
        We show you the exact formula used and how each value was computed.
    </div>
    """, unsafe_allow_html=True)
    
    # Starting point
    st.markdown("### 📌 Starting Point")
    st.markdown(f"""
    <div class="formula-box">
        <strong>Base List Price:</strong> {format_currency(result.base_price)}
    </div>
    """, unsafe_allow_html=True)
    
    # Rebate Calculations
    st.markdown("### 🎁 Rebate Calculations")
    
    accumulated_rebate = 0
    
    if result.rebate_breakdown:
        for i, rebate in enumerate(result.rebate_breakdown, 1):
            calc_base = rebate.effective_price if hasattr(rebate, 'effective_price') else result.base_price
            memo_info = f" ({rebate.memo_reference})" if rebate.memo_reference else ""
            
            st.markdown(f"""
            <div class="calculation-step">
                <strong>Rebate {i}: {rebate.rule_name}</strong>{memo_info}<br>
                <hr style="margin: 0.5rem 0;">
                <strong>Rule Applied:</strong> {rebate.rule_id}<br>
                <strong>Rebate Rate:</strong> {rebate.value}%<br>
                <strong>Calculation Base:</strong> {format_currency(calc_base)}<br>
                <strong>Project:</strong> {rebate.project_name or 'Unknown'}<br>
                <br>
                <div class="formula-box">
                    <strong>Formula:</strong> {format_currency(calc_base)} × {rebate.value}% = <span class="highlight-value">{format_currency(rebate.calculated_amount or 0)}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            accumulated_rebate += rebate.calculated_amount or 0
    else:
        st.info("No rebates applicable for this scenario.")
    
    # Total Rebate
    st.markdown(f"""
    <div style="background: #cce5ff; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
        <strong>Total Rebate:</strong> {format_currency(result.total_rebate)}
    </div>
    """, unsafe_allow_html=True)
    
    # Net Price After Rebate
    net_price = result.base_price - result.total_rebate
    st.markdown(f"""
    <div class="formula-box">
        <strong>Net Price After Rebate:</strong><br>
        {format_currency(result.base_price)} - {format_currency(result.total_rebate)} = <span class="highlight-value">{format_currency(net_price)}</span>
    </div>
    """, unsafe_allow_html=True)
    
    # Commission Calculations
    st.markdown("### 💼 Commission Calculations")
    
    if result.commission_breakdown:
        for i, comm in enumerate(result.commission_breakdown, 1):
            comm_base = net_price
            memo_info = f" ({comm.memo_reference})" if comm.memo_reference else ""
            
            st.markdown(f"""
            <div class="calculation-step">
                <strong>Commission {i}: {comm.rule_name}</strong>{memo_info}<br>
                <hr style="margin: 0.5rem 0;">
                <strong>Rule Applied:</strong> {comm.rule_id}<br>
                <strong>Commission Rate:</strong> {comm.value}%<br>
                <strong>Commission Base:</strong> {format_currency(comm_base)}<br>
                <strong>Project:</strong> {comm.project_name or 'Unknown'}<br>
                <br>
                <div class="formula-box">
                    <strong>Formula:</strong> {format_currency(comm_base)} × {comm.value}% = <span class="highlight-value">{format_currency(comm.calculated_amount or 0)}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No commission applicable for this scenario.")
    
    # Final Summary Section
    st.markdown("### 📊 Final Calculation Summary")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div class="result-summary">
            <h3 style="margin:0;">Base Price</h3>
            <h2 style="margin:0.5rem 0; color: white;">{format_currency(result.base_price)}</h2>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 1.5rem; border-radius: 12px; text-align: center;">
            <h3 style="margin:0;">Total Rebate</h3>
            <h2 style="margin:0.5rem 0;">(-) {format_currency(result.total_rebate)}</h2>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="result-summary">
            <h3 style="margin:0;">Final Price</h3>
            <h2 style="margin:0.5rem 0; color: white;">{format_currency(result.final_price)}</h2>
        </div>
        """, unsafe_allow_html=True)
    
    # Commission Summary
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1.5rem; border-radius: 12px; text-align: center; margin-top: 1rem;">
        <h3 style="margin:0;">Total Agent Commission</h3>
        <h2 style="margin:0.5rem 0;">{format_currency(result.total_commission)}</h2>
    </div>
    """, unsafe_allow_html=True)


def render_conflict_resolution_pipeline(engine: MultiMemoRuleEngine, context: Dict[str, Any]):
    """Render the multi-memo processing pipeline visualization."""
    st.markdown('<div class="step-header">🔄 Multi-Memo Processing Pipeline</div>', unsafe_allow_html=True)
    
    stats = engine.get_statistics()
    last_stats = engine._last_stats
    
    # Pipeline visualization
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.markdown("""
        <div class="pipeline-step pipeline-step-active">
            <div style="font-size: 2rem;">📚</div>
            <div style="font-weight: bold;">Load Memos</div>
            <div style="font-size: 1.5rem; color: #28a745;">{}</div>
            <div style="font-size: 0.8rem; color: #666;">Total Memos</div>
        </div>
        """.format(stats.get('total_memos', 0)), unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="pipeline-step pipeline-step-active">
            <div style="font-size: 2rem;">📅</div>
            <div style="font-weight: bold;">Date Filter</div>
            <div style="font-size: 1.5rem; color: #17a2b8;">{}</div>
            <div style="font-size: 0.8rem; color: #666;">Active Memos</div>
        </div>
        """.format(last_stats.get('memos_after_date_filter', 0)), unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="pipeline-step pipeline-step-active">
            <div style="font-size: 2rem;">🔗</div>
            <div style="font-weight: bold;">Aggregate</div>
            <div style="font-size: 1.5rem; color: #ffc107;">{}</div>
            <div style="font-size: 0.8rem; color: #666;">Total Rules</div>
        </div>
        """.format(last_stats.get('rules_before_conflict_resolution', 0)), unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div class="pipeline-step pipeline-step-active">
            <div style="font-size: 2rem;">⚔️</div>
            <div style="font-weight: bold;">Resolve Conflicts</div>
            <div style="font-size: 1.5rem; color: #dc3545;">{}</div>
            <div style="font-size: 0.8rem; color: #666;">Conflicts Found</div>
        </div>
        """.format(stats.get('conflicts', 0)), unsafe_allow_html=True)
    
    with col5:
        st.markdown("""
        <div class="pipeline-step pipeline-step-active">
            <div style="font-size: 2rem;">✅</div>
            <div style="font-weight: bold;">Active Rules</div>
            <div style="font-size: 1.5rem; color: #28a745;">{}</div>
            <div style="font-size: 0.8rem; color: #666;">Ready to Match</div>
        </div>
        """.format(last_stats.get('rules_after_conflict_resolution', 0)), unsafe_allow_html=True)


def render_conflict_details(engine: MultiMemoRuleEngine):
    """Render detailed conflict resolution visualization."""
    st.markdown('<div class="step-header">⚔️ Conflict Resolution Details</div>', unsafe_allow_html=True)
    
    conflicts_summary = engine.get_conflicts_summary()
    
    if conflicts_summary.get('total_conflicts', 0) == 0:
        st.success("✅ No conflicts detected! All rules from different memos are unique.")
        return
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Conflicts",
            conflicts_summary.get('total_conflicts', 0),
            delta=None,
            delta_color="off"
        )
    
    with col2:
        by_type = conflicts_summary.get('by_type', {})
        same_id = by_type.get('same_rule_id', 0)
        st.metric("Same Rule ID", same_id)
    
    with col3:
        overlapping = by_type.get('overlapping', 0)
        st.metric("Overlapping Rules", overlapping)
    
    with col4:
        needs_review = conflicts_summary.get('requires_review', 0)
        st.metric("Needs Review", needs_review, delta="⚠️" if needs_review > 0 else None)
    
    st.markdown("---")
    
    # Detailed conflict cards
    conflicts = conflicts_summary.get('conflicts', [])
    
    for conflict in conflicts:
        conflict_type = conflict.get('type', 'unknown')
        resolution = conflict.get('resolution', 'unknown')
        involved_rules = conflict.get('involved_rules', [])
        resolved_rule = conflict.get('resolved_rule', '')
        description = conflict.get('description', '')
        
        # Determine card style
        if conflict.get('requires_review'):
            card_class = "conflict-card"
        else:
            card_class = "conflict-resolved"
        
        st.markdown(f"""
        <div class="{card_class}">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-weight: bold; font-size: 1.1rem;">
                        {get_resolution_icon(ConflictResolution(resolution))} {conflict.get('conflict_id', 'Unknown')}
                    </span>
                    <span style="background: {get_conflict_type_color(ConflictType(conflict_type))}; color: white; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; margin-left: 0.5rem;">
                        {conflict_type.upper().replace('_', ' ')}
                    </span>
                </div>
                <div style="font-size: 0.85rem; color: #666;">
                    Resolution: <strong>{resolution.replace('_', ' ').title()}</strong>
                </div>
            </div>
            <div style="margin-top: 0.5rem; color: #333;">
                {description}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Show involved rules with winner highlighted
        with st.expander(f"View {len(involved_rules)} involved rules", expanded=False):
            for rule_id in involved_rules:
                is_winner = rule_id == resolved_rule
                
                if is_winner:
                    st.markdown(f"""
                    <div style="background: #d4edda; padding: 0.5rem 1rem; border-radius: 4px; margin: 0.25rem 0; border-left: 3px solid #28a745;">
                        <strong>✅ WINNER:</strong> <code>{rule_id}</code>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="background: #f8d7da; padding: 0.5rem 1rem; border-radius: 4px; margin: 0.25rem 0; border-left: 3px solid #dc3545; opacity: 0.7;">
                        <strong>❌ Superseded:</strong> <code>{rule_id}</code>
                    </div>
                    """, unsafe_allow_html=True)


def render_priority_ranking(engine: MultiMemoRuleEngine, rule_type: Optional[str] = None):
    """Render the priority ranking of rules."""
    st.markdown('<div class="step-header">⭐ Priority Ranking</div>', unsafe_allow_html=True)
    
    try:
        rankings = engine.get_priority_ranking(rule_type=rule_type, top_n=10)
    except:
        st.info("No rankings available. Run a calculation first.")
        return
    
    if not rankings:
        st.info("No rules to rank.")
        return
    
    # Display as table-like cards
    for i, rank in enumerate(rankings, 1):
        priority = rank.get('total_priority', 0)
        max_priority = 3.0  # Max possible priority
        priority_pct = min(100, (priority / max_priority) * 100)
        
        # Color based on rank
        if i == 1:
            border_color = "#ffd700"  # Gold
            bg_color = "#fffbeb"
        elif i == 2:
            border_color = "#c0c0c0"  # Silver
            bg_color = "#f8f9fa"
        elif i == 3:
            border_color = "#cd7f32"  # Bronze
            bg_color = "#fff8f0"
        else:
            border_color = "#dee2e6"
            bg_color = "#ffffff"
        
        st.markdown(f"""
        <div style="background: {bg_color}; border-left: 4px solid {border_color}; padding: 1rem; margin: 0.5rem 0; border-radius: 0 8px 8px 0;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 1.5rem; font-weight: bold; color: {border_color};">#{i}</span>
                    <span style="margin-left: 1rem; font-weight: bold;">{rank.get('rule_name', 'Unknown')}</span>
                    <span style="color: #666; font-size: 0.85rem; margin-left: 0.5rem;">({rank.get('rule_id', '')})</span>
                </div>
                <div>
                    <span class="memo-badge memo-badge-project">{rank.get('project_name', 'Unknown')}</span>
                </div>
            </div>
            <div style="margin-top: 0.75rem;">
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <div style="flex: 1;">
                        <div class="priority-bar">
                            <div class="priority-fill" style="width: {priority_pct}%; background: linear-gradient(90deg, #28a745, #20c997);"></div>
                        </div>
                    </div>
                    <div style="min-width: 100px; text-align: right;">
                        <strong>{priority:.2f}</strong> / {max_priority:.1f}
                    </div>
                </div>
                <div style="display: flex; gap: 1rem; margin-top: 0.5rem; font-size: 0.8rem; color: #666;">
                    <span>📅 Recency: {rank.get('recency_score', 0):.2f}</span>
                    <span>🎯 Specificity: {rank.get('specificity_score', 0):.2f}</span>
                    <span>📋 Memo: {rank.get('memo_score', 0):.2f}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ============================================================================
# RENDER FUNCTIONS - CALCULATION RESULTS
# ============================================================================

def render_executive_summary(result: MultiMemoPricingResult):
    """Render the executive summary with key metrics."""
    
    savings_percentage = (result.total_rebate / result.base_price) * 100 if result.base_price > 0 else 0
    
    # Safely format source memos
    source_memos_str = ', '.join(list(result.source_memos)) if result.source_memos else 'N/A'
    rules_count = len(result.matched_rules) if result.matched_rules else 0
    
    st.markdown('<div class="step-header">📊 Executive Summary</div>', unsafe_allow_html=True)
    
    # Split into two separate markdown calls to avoid rendering issues
    st.markdown(f"""
    <div class="executive-summary">
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.5rem;">
            <div class="executive-metric">
                <div class="executive-metric-value">{format_currency(result.base_price)}</div>
                <div class="executive-metric-label">List Price</div>
            </div>
            <div class="executive-metric">
                <div class="executive-metric-value" style="color: #f59e0b;">{format_currency(result.total_rebate)}</div>
                <div class="executive-metric-label">Total Rebate ({savings_percentage:.1f}%)</div>
            </div>
            <div class="executive-metric">
                <div class="executive-metric-value" style="color: #3b82f6;">{format_currency(result.total_commission)}</div>
                <div class="executive-metric-label">Total Commission</div>
            </div>
            <div class="executive-metric">
                <div class="executive-metric-value">{format_currency(result.final_price)}</div>
                <div class="executive-metric-label">Final Price</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Source memos and rules count as separate section
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Source Memos:** {source_memos_str}")
    with col2:
        st.markdown(f"**Rules Applied:** {rules_count}")


def render_calculation_breakdown(result: MultiMemoPricingResult):
    """Render detailed calculation breakdown with memo traceability."""
    st.markdown('<div class="step-header">🧮 Calculation Breakdown</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🎁 Rebates Applied")
        if result.rebate_breakdown:
            for rebate in result.rebate_breakdown:
                st.markdown(f"""
                <div class="rule-card">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div>
                            <strong>{rebate.rule_name}</strong>
                            <div style="font-size: 0.85rem; color: #666;">{rebate.description}</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.2rem; font-weight: bold; color: #28a745;">
                                {format_currency(rebate.calculated_amount or 0)}
                            </div>
                            <div style="font-size: 0.75rem; color: #666;">
                                {rebate.value}%
                            </div>
                        </div>
                    </div>
                    <div style="margin-top: 0.5rem; font-size: 0.75rem;">
                        <span class="memo-badge memo-badge-project">{rebate.project_name or 'Unknown'}</span>
                        <span style="color: #666; margin-left: 0.5rem;">📋 {rebate.memo_reference or 'N/A'}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No rebates applied.")
    
    with col2:
        st.markdown("### 💼 Commissions Applied")
        if result.commission_breakdown:
            for commission in result.commission_breakdown:
                st.markdown(f"""
                <div class="rule-card">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div>
                            <strong>{commission.rule_name}</strong>
                            <div style="font-size: 0.85rem; color: #666;">{commission.description}</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.2rem; font-weight: bold; color: #17a2b8;">
                                {format_currency(commission.calculated_amount or 0)}
                            </div>
                            <div style="font-size: 0.75rem; color: #666;">
                                {commission.value}%
                            </div>
                        </div>
                    </div>
                    <div style="margin-top: 0.5rem; font-size: 0.75rem;">
                        <span class="memo-badge memo-badge-project">{commission.project_name or 'Unknown'}</span>
                        <span style="color: #666; margin-left: 0.5rem;">📋 {commission.memo_reference or 'N/A'}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No commissions applied.")


def render_traceability_audit(result: MultiMemoPricingResult):
    """Render the traceability audit trail."""
    st.markdown('<div class="step-header">📜 Traceability & Audit Trail</div>', unsafe_allow_html=True)
    
    # Statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Memos Considered", result.memos_considered)
    with col2:
        st.metric("After Date Filter", result.memos_after_date_filter)
    with col3:
        st.metric("Rules Before Resolution", result.rules_before_conflict_resolution)
    with col4:
        st.metric("Rules After Resolution", result.rules_after_conflict_resolution)
    
    st.markdown("---")
    
    # Matched rules with memo links
    st.markdown("### 🔗 Rule to Memo Mapping")
    
    all_rules = result.rebate_breakdown + result.commission_breakdown + result.price_adjustments
    
    if all_rules:
        for rule in all_rules:
            effective_period = rule.effective_period or {}
            st.markdown(f"""
            <div style="background: #f8f9fa; padding: 0.75rem 1rem; margin: 0.25rem 0; border-radius: 8px; border-left: 3px solid #17a2b8;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong>{rule.rule_id}</strong>
                        <span style="color: #666; margin-left: 0.5rem;">→</span>
                        <span style="color: #17a2b8; margin-left: 0.5rem;">{rule.memo_reference or 'N/A'}</span>
                    </div>
                    <div style="font-size: 0.8rem; color: #666;">
                        {effective_period.get('start_date', '')} - {effective_period.get('end_date', '')}
                    </div>
                </div>
                <div style="font-size: 0.85rem; color: #666; margin-top: 0.25rem;">
                    {rule.rule_name} | {rule.project_name or 'Unknown Project'}
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No rules matched for this transaction.")
    
    # Conflicts detected
    if result.conflicts_detected:
        st.markdown("### ⚠️ Conflicts Detected During Calculation")
        for conflict in result.conflicts_detected:
            st.warning(f"**{conflict.get('conflict_id', 'Unknown')}**: {conflict.get('description', '')}")


# ============================================================================
# RENDER FUNCTIONS - RULE LIBRARY
# ============================================================================

def render_detailed_rule_library(engine: MultiMemoRuleEngine):
    """Render detailed rule library organized by memo with rule statistics."""
    st.markdown('<div class="step-header">📚 Rule Statistics</div>', unsafe_allow_html=True)
    
    # Get rule type counts from the library
    rule_type_counts = {}
    for rule_type in ['commission', 'rebate', 'referral', 'price_adjustment', 'package']:
        rules = engine.library.get_by_type(rule_type)
        rule_type_counts[rule_type] = len(rules)
    
    # Display rule statistics
    icons = {
        'commission': '💼',
        'rebate': '🎁',
        'referral': '🤝',
        'price_adjustment': '📈',
        'package': '📦'
    }
    
    cols = st.columns(5)
    for i, (rule_type, count) in enumerate(rule_type_counts.items()):
        with cols[i]:
            st.metric(
                f"{icons.get(rule_type, '📋')} {rule_type.replace('_', ' ').title()}",
                count
            )
    
    st.markdown("---")
    
    # Commission Rules Section
    st.markdown('<div class="step-header">💼 Commission Rules</div>', unsafe_allow_html=True)
    commission_rules = engine.library.get_by_type('commission')
    
    if commission_rules:
        for rule in commission_rules:
            with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Memo:** {rule.memo_metadata.memo_reference if rule.memo_metadata else 'N/A'}")
                    st.markdown(f"**Project:** {rule.memo_metadata.project_name if rule.memo_metadata else 'N/A'}")
                with col2:
                    st.markdown(f"**Buyer Type:** {rule.buyer_type or 'All'}")
                    st.markdown(f"**Priority Score:** {rule.get_total_priority():.2f}")
                
                if rule.conditions:
                    st.markdown("**Conditions & Rates:**")
                    for cond in rule.conditions:
                        if isinstance(cond, dict):
                            condition = cond.get('condition', 'N/A')
                            rate = cond.get('commission_percentage', 'N/A')
                            desc = cond.get('description', '')
                            
                            st.markdown(f"""
                            <div style="background: #f0f7f0; padding: 0.8rem; margin: 0.5rem 0; border-radius: 8px; border-left: 4px solid #28a745;">
                                <div style="font-family: monospace; font-size: 0.9rem; color: #333;">
                                    <strong>IF</strong> {condition.replace('IF ', '')}
                                </div>
                                <div style="margin-top: 0.5rem;">
                                    <span style="background: #28a745; color: white; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold;">
                                        Commission: {rate}%
                                    </span>
                                </div>
                                {f'<div style="margin-top: 0.5rem; color: #666; font-style: italic;">{desc}</div>' if desc else ''}
                            </div>
                            """, unsafe_allow_html=True)
    else:
        st.info("No commission rules available")
    
    st.markdown("---")
    
    # Rebate Rules Section
    st.markdown('<div class="step-header">🎁 Rebate Rules</div>', unsafe_allow_html=True)
    rebate_rules = engine.library.get_by_type('rebate')
    
    if rebate_rules:
        for rule in rebate_rules:
            with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Memo:** {rule.memo_metadata.memo_reference if rule.memo_metadata else 'N/A'}")
                    st.markdown(f"**Project:** {rule.memo_metadata.project_name if rule.memo_metadata else 'N/A'}")
                with col2:
                    rebate_type = rule.raw_data.get('rebate_type', 'N/A')
                    st.markdown(f"**Rebate Type:** {rebate_type}")
                    st.markdown(f"**Priority Score:** {rule.get_total_priority():.2f}")
                
                if rule.conditions:
                    st.markdown("**Conditions & Rates:**")
                    for cond in rule.conditions:
                        if isinstance(cond, dict):
                            condition = cond.get('condition', 'N/A')
                            rate = cond.get('rebate_percentage', 'N/A')
                            desc = cond.get('description', '')
                            
                            st.markdown(f"""
                            <div style="background: #e7f6fd; padding: 0.8rem; margin: 0.5rem 0; border-radius: 8px; border-left: 4px solid #17a2b8;">
                                <div style="font-family: monospace; font-size: 0.9rem; color: #333;">
                                    <strong>IF</strong> {condition.replace('IF ', '')}
                                </div>
                                <div style="margin-top: 0.5rem;">
                                    <span style="background: #17a2b8; color: white; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold;">
                                        Rebate: {rate}%
                                    </span>
                                </div>
                                {f'<div style="margin-top: 0.5rem; color: #666; font-style: italic;">{desc}</div>' if desc else ''}
                            </div>
                            """, unsafe_allow_html=True)
    else:
        st.info("No rebate rules available")
    
    st.markdown("---")
    
    # Referral Rules Section
    st.markdown('<div class="step-header">🤝 Referral Rules</div>', unsafe_allow_html=True)
    referral_rules = engine.library.get_by_type('referral')
    
    if referral_rules:
        for rule in referral_rules:
            with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Memo:** {rule.memo_metadata.memo_reference if rule.memo_metadata else 'N/A'}")
                    st.markdown(f"**Project:** {rule.memo_metadata.project_name if rule.memo_metadata else 'N/A'}")
                with col2:
                    st.markdown(f"**Priority Score:** {rule.get_total_priority():.2f}")
                
                if rule.conditions:
                    st.markdown("**Conditions & Rates:**")
                    for cond in rule.conditions:
                        if isinstance(cond, dict):
                            condition = cond.get('condition', 'N/A')
                            rate = cond.get('referral_percentage', 'N/A')
                            desc = cond.get('description', '')
                            
                            st.markdown(f"""
                            <div style="background: #fff3cd; padding: 0.8rem; margin: 0.5rem 0; border-radius: 8px; border-left: 4px solid #ffc107;">
                                <div style="font-family: monospace; font-size: 0.9rem; color: #333;">
                                    <strong>IF</strong> {condition.replace('IF ', '')}
                                </div>
                                <div style="margin-top: 0.5rem;">
                                    <span style="background: #ffc107; color: black; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold;">
                                        Referral: {rate}%
                                    </span>
                                </div>
                                {f'<div style="margin-top: 0.5rem; color: #666; font-style: italic;">{desc}</div>' if desc else ''}
                            </div>
                            """, unsafe_allow_html=True)
    else:
        st.info("No referral rules available")


def render_memo_detail_with_rules(engine: MultiMemoRuleEngine, memo_reference: str):
    """Render detailed information about a specific memo and its rules."""
    memo = engine.memo_manager.memos.get(memo_reference)
    if not memo:
        st.error(f"Memo {memo_reference} not found")
        return
    
    metadata = memo.metadata
    
    # Memo Header
    st.markdown(f'<div class="step-header">📋 {metadata.memo_reference} - {metadata.project_name}</div>', unsafe_allow_html=True)
    
    # Memo Info
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📋 Memo Reference", metadata.memo_reference)
    with col2:
        st.metric("🏗️ Project", metadata.project_name)
    with col3:
        effective = metadata.effective_period or {}
        st.metric("📅 Effective From", effective.get('start_date', 'N/A'))
    with col4:
        effective = metadata.effective_period or {}
        st.metric("📅 Effective Until", effective.get('end_date', 'N/A'))
    
    st.markdown("---")
    
    # Additional metadata
    col1, col2, col3 = st.columns(3)
    with col1:
        memo_type = metadata.memo_type.value if hasattr(metadata.memo_type, 'value') else str(metadata.memo_type)
        st.markdown(f"**Memo Type:** {memo_type.upper()}")
    with col2:
        st.markdown(f"**Priority:** {metadata.priority}")
    with col3:
        st.markdown(f"**Total Rules:** {len(memo.rules)}")
    
    st.markdown("---")
    
    # Rule statistics for this memo
    st.markdown("### 📊 Rule Statistics - This Memo")
    
    rule_type_counts = {}
    for rule in memo.rules:
        rule_type = rule.rule_type
        rule_type_counts[rule_type] = rule_type_counts.get(rule_type, 0) + 1
    
    icons = {
        'commission': '💼',
        'rebate': '🎁',
        'referral': '🤝',
        'price_adjustment': '📈',
        'package': '📦'
    }
    
    if rule_type_counts:
        cols = st.columns(len(rule_type_counts))
        for i, (rule_type, count) in enumerate(rule_type_counts.items()):
            with cols[i]:
                st.metric(
                    f"{icons.get(rule_type, '📋')} {rule_type.replace('_', ' ').title()}",
                    count
                )
    
    st.markdown("---")
    
    # Commission Rules for this memo
    commission_rules = [r for r in memo.rules if r.rule_type == 'commission']
    if commission_rules:
        st.markdown('<div class="step-header">💼 Commission Rules</div>', unsafe_allow_html=True)
        for rule in commission_rules:
            with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Buyer Type:** {rule.buyer_type or 'All'}")
                with col2:
                    st.markdown(f"**Priority Score:** {rule.get_total_priority():.2f}")
                
                if rule.conditions:
                    st.markdown("**Conditions & Rates:**")
                    for cond in rule.conditions:
                        if isinstance(cond, dict):
                            condition = cond.get('condition', 'N/A')
                            rate = cond.get('commission_percentage', 'N/A')
                            desc = cond.get('description', '')
                            
                            st.markdown(f"""
                            <div style="background: #f0f7f0; padding: 0.8rem; margin: 0.5rem 0; border-radius: 8px; border-left: 4px solid #28a745;">
                                <div style="font-family: monospace; font-size: 0.9rem; color: #333;">
                                    <strong>IF</strong> {condition.replace('IF ', '')}
                                </div>
                                <div style="margin-top: 0.5rem;">
                                    <span style="background: #28a745; color: white; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold;">
                                        Commission: {rate}%
                                    </span>
                                </div>
                                {f'<div style="margin-top: 0.5rem; color: #666; font-style: italic;">{desc}</div>' if desc else ''}
                            </div>
                            """, unsafe_allow_html=True)
                
                notes = rule.raw_data.get('notes', [])
                if notes:
                    st.markdown("**Notes:**")
                    for note in notes:
                        st.markdown(f"- {note}")
        
        st.markdown("---")
    
    # Rebate Rules for this memo
    rebate_rules = [r for r in memo.rules if r.rule_type == 'rebate']
    if rebate_rules:
        st.markdown('<div class="step-header">🎁 Rebate Rules</div>', unsafe_allow_html=True)
        for rule in rebate_rules:
            with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    rebate_type = rule.raw_data.get('rebate_type', 'N/A')
                    st.markdown(f"**Rebate Type:** {rebate_type}")
                with col2:
                    st.markdown(f"**Priority Score:** {rule.get_total_priority():.2f}")
                
                if rule.conditions:
                    st.markdown("**Conditions & Rates:**")
                    for cond in rule.conditions:
                        if isinstance(cond, dict):
                            condition = cond.get('condition', 'N/A')
                            rate = cond.get('rebate_percentage', 'N/A')
                            desc = cond.get('description', '')
                            
                            st.markdown(f"""
                            <div style="background: #e7f6fd; padding: 0.8rem; margin: 0.5rem 0; border-radius: 8px; border-left: 4px solid #17a2b8;">
                                <div style="font-family: monospace; font-size: 0.9rem; color: #333;">
                                    <strong>IF</strong> {condition.replace('IF ', '')}
                                </div>
                                <div style="margin-top: 0.5rem;">
                                    <span style="background: #17a2b8; color: white; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold;">
                                        Rebate: {rate}%
                                    </span>
                                </div>
                                {f'<div style="margin-top: 0.5rem; color: #666; font-style: italic;">{desc}</div>' if desc else ''}
                            </div>
                            """, unsafe_allow_html=True)
                
                notes = rule.raw_data.get('notes', [])
                if notes:
                    st.markdown("**Notes:**")
                    for note in notes:
                        st.markdown(f"- {note}")
        
        st.markdown("---")
    
    # Referral Rules for this memo
    referral_rules = [r for r in memo.rules if r.rule_type == 'referral']
    if referral_rules:
        st.markdown('<div class="step-header">🤝 Referral Rules</div>', unsafe_allow_html=True)
        for rule in referral_rules:
            with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
                st.markdown(f"**Priority Score:** {rule.get_total_priority():.2f}")
                
                if rule.conditions:
                    st.markdown("**Conditions & Rates:**")
                    for cond in rule.conditions:
                        if isinstance(cond, dict):
                            condition = cond.get('condition', 'N/A')
                            rate = cond.get('referral_percentage', 'N/A')
                            desc = cond.get('description', '')
                            
                            st.markdown(f"""
                            <div style="background: #fff3cd; padding: 0.8rem; margin: 0.5rem 0; border-radius: 8px; border-left: 4px solid #ffc107;">
                                <div style="font-family: monospace; font-size: 0.9rem; color: #333;">
                                    <strong>IF</strong> {condition.replace('IF ', '')}
                                </div>
                                <div style="margin-top: 0.5rem;">
                                    <span style="background: #ffc107; color: black; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold;">
                                        Referral: {rate}%
                                    </span>
                                </div>
                                {f'<div style="margin-top: 0.5rem; color: #666; font-style: italic;">{desc}</div>' if desc else ''}
                            </div>
                            """, unsafe_allow_html=True)
                
                notes = rule.raw_data.get('notes', [])
                if notes:
                    st.markdown("**Notes:**")
                    for note in notes:
                        st.markdown(f"- {note}")
        
        st.markdown("---")
    
    # Price Adjustment Rules for this memo
    adjustment_rules = [r for r in memo.rules if r.rule_type == 'price_adjustment']
    if adjustment_rules:
        st.markdown('<div class="step-header">📈 Price Adjustment Rules</div>', unsafe_allow_html=True)
        for rule in adjustment_rules:
            with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
                st.markdown(f"**Priority Score:** {rule.get_total_priority():.2f}")
                
                if rule.conditions:
                    st.markdown("**Conditions:**")
                    for cond in rule.conditions:
                        if isinstance(cond, dict):
                            condition = cond.get('condition', 'N/A')
                            amount = cond.get('adjustment_amount', 'N/A')
                            desc = cond.get('description', '')
                            
                            st.markdown(f"""
                            <div style="background: #f0e7fd; padding: 0.8rem; margin: 0.5rem 0; border-radius: 8px; border-left: 4px solid #6f42c1;">
                                <div style="font-family: monospace; font-size: 0.9rem; color: #333;">
                                    <strong>IF</strong> {condition.replace('IF ', '')}
                                </div>
                                <div style="margin-top: 0.5rem;">
                                    <span style="background: #6f42c1; color: white; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold;">
                                        Adjustment: {amount}
                                    </span>
                                </div>
                                {f'<div style="margin-top: 0.5rem; color: #666; font-style: italic;">{desc}</div>' if desc else ''}
                            </div>
                            """, unsafe_allow_html=True)


def render_memo_overview(engine: MultiMemoRuleEngine):
    """Render overview of loaded memos."""
    st.markdown('<div class="step-header">📚 Loaded Memos Overview</div>', unsafe_allow_html=True)
    
    stats = engine.get_statistics()
    memos = engine.memo_manager.memos
    
    if not memos:
        st.warning("No memos loaded.")
        return
    
    for memo_key, memo in memos.items():
        metadata = memo.metadata
        memo_type = metadata.memo_type
        
        # Badge color based on memo type
        if memo_type == MemoType.SUPERSEDING:
            badge_class = "memo-badge-project"
            type_label = "SUPERSEDING"
        elif memo_type == MemoType.ADDENDUM:
            badge_class = "memo-badge-latest"
            type_label = "ADDENDUM"
        elif memo_type == MemoType.AMENDMENT:
            badge_class = "memo-badge-latest"
            type_label = "AMENDMENT"
        else:  # STANDARD
            badge_class = "memo-badge-base"
            type_label = "STANDARD"
        
        effective_period = metadata.effective_period or {}
        
        with st.expander(f"📋 {metadata.memo_reference} - {metadata.project_name}", expanded=False):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(f"""
                <span class="memo-badge {badge_class}">{type_label}</span>
                """, unsafe_allow_html=True)
                st.write(f"**File:** {metadata.memo_file}")
            
            with col2:
                st.write(f"**Start Date:** {effective_period.get('start_date', 'N/A')}")
                st.write(f"**End Date:** {effective_period.get('end_date', 'N/A')}")
            
            with col3:
                st.write(f"**Rules:** {len(memo.rules)}")
                st.write(f"**Priority:** {metadata.priority}")
            
            # Rule breakdown by type
            st.markdown("**Rules by Type:**")
            type_counts = {}
            for rule in memo.rules:
                rt = rule.rule_type
                type_counts[rt] = type_counts.get(rt, 0) + 1
            
            type_cols = st.columns(len(type_counts) if type_counts else 1)
            for i, (rtype, count) in enumerate(type_counts.items()):
                with type_cols[i]:
                    st.metric(rtype.replace('_', ' ').title(), count)


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point."""
    
    render_header()
    
    # Load engine
    try:
        engine = load_multi_memo_engine()
    except Exception as e:
        st.error(f"Failed to load memos: {e}")
        return
    
    # Create tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🧮 Calculator",
        "⚔️ Conflict Resolution",
        "⭐ Priority Ranking",
        "📚 Memo Library"
    ])
    
    with tab1:
        render_calculator_tab(engine)
    
    with tab2:
        render_conflict_tab(engine)
    
    with tab3:
        render_priority_tab(engine)
    
    with tab4:
        render_library_tab(engine)


def render_calculator_tab(engine: MultiMemoRuleEngine):
    """Render the main calculator tab."""
    
    # Get user input
    context = render_input_section(engine)
    
    st.markdown("---")
    
    # Calculate button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        calculate_clicked = st.button(
            "🔍 Calculate Commission & Rebates",
            type="primary",
            use_container_width=True
        )
    
    if calculate_clicked:
        with st.spinner("Processing memos and calculating..."):
            # Prepare the engine with filters
            spa_date_str = context['spa_date'].strftime('%d %b %Y') if context.get('spa_date') else None
            
            try:
                # Retrieve and prepare rules
                engine.retrieve_and_prepare(
                    project_name=context.get('project_filter'),
                    target_date=datetime.combine(context['spa_date'], datetime.min.time()) if context.get('spa_date') else None,
                    resolution_strategy=ConflictResolution.LATEST_WINS
                )
                
                # Calculate
                result = engine.calculate(
                    context=context,
                    project_name=context.get('project_filter'),
                    spa_date=spa_date_str
                )
                
                # Store in session state
                st.session_state['mm_result'] = result
                st.session_state['mm_context'] = context
                st.session_state['mm_calculated'] = True
                
            except Exception as e:
                st.error(f"Calculation error: {e}")
                import traceback
                st.code(traceback.format_exc())
                return
    
    # Show results if calculated
    if st.session_state.get('mm_calculated', False):
        result = st.session_state['mm_result']
        
        st.markdown("---")
        
        # Executive summary (FIRST)
        render_executive_summary(result)
        
        st.markdown("---")
        
        # Calculation breakdown cards (SECOND)
        with st.expander("🧮 **View Calculation Breakdown**", expanded=True):
            render_calculation_breakdown(result)
        
        st.markdown("---")
        
        # Detailed step-by-step calculation breakdown (THIRD)
        with st.expander("📋 **View Calculation Details - Step-by-Step Formula Breakdown**", expanded=False):
            render_detailed_calculation_breakdown(result)
        
        st.markdown("---")
        
        # Rule matching details (FOURTH)
        with st.expander("🎯 **View Rule Matching Details - Which rules were applied and why**", expanded=False):
            render_rule_matching_details(engine, result, context)
        
        st.markdown("---")
        
        # Pipeline visualization (FIFTH)
        render_conflict_resolution_pipeline(engine, context)
        
        st.markdown("---")
        
        # Traceability (SIXTH)
        with st.expander("📜 **View Traceability & Audit Trail**", expanded=False):
            render_traceability_audit(result)


def render_conflict_tab(engine: MultiMemoRuleEngine):
    """Render the conflict resolution tab."""
    
    st.markdown("""
    <div style="background: #fff3cd; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
        <strong>⚔️ Conflict Resolution Explained:</strong><br>
        When rules from different memos have the same Rule ID or overlapping conditions, 
        the system automatically resolves conflicts based on the selected strategy.
    </div>
    """, unsafe_allow_html=True)
    
    # Resolution strategy selector
    col1, col2 = st.columns([1, 2])
    with col1:
        strategy = st.selectbox(
            "Resolution Strategy",
            options=[
                "latest_wins",
                "highest_priority",
                "most_specific"
            ],
            format_func=lambda x: {
                "latest_wins": "🕐 Latest Wins (Newest memo takes precedence)",
                "highest_priority": "⭐ Highest Priority (Best priority score wins)",
                "most_specific": "🎯 Most Specific (Most detailed condition wins)"
            }.get(x, x)
        )
    
    with col2:
        if st.button("🔄 Re-process with Selected Strategy", type="primary"):
            try:
                engine.retrieve_and_prepare(
                    resolution_strategy=ConflictResolution(strategy)
                )
                st.success(f"Rules re-processed with '{strategy}' strategy!")
            except Exception as e:
                st.error(f"Error: {e}")
    
    st.markdown("---")
    
    # Render conflict details
    if engine.library:
        render_conflict_details(engine)
    else:
        st.info("Run a calculation first to see conflict resolution details.")


def render_priority_tab(engine: MultiMemoRuleEngine):
    """Render the priority ranking tab."""
    
    st.markdown("""
    <div style="background: #e7f3ff; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
        <strong>⭐ Priority Scoring:</strong><br>
        Rules are ranked by combining: 
        <strong>Recency</strong> (newer memos score higher), 
        <strong>Specificity</strong> (more specific conditions score higher), and 
        <strong>Memo Type</strong> (project-specific memos score higher than base policies).
    </div>
    """, unsafe_allow_html=True)
    
    # Rule type filter
    rule_type_filter = st.selectbox(
        "Filter by Rule Type",
        options=["All", "commission", "rebate", "referral", "price_adjustment", "package"],
        format_func=lambda x: x.replace('_', ' ').title() if x != "All" else "All Types"
    )
    
    if engine.library:
        render_priority_ranking(
            engine,
            rule_type=None if rule_type_filter == "All" else rule_type_filter
        )
    else:
        st.info("Run a calculation first to see priority rankings.")


def render_library_tab(engine: MultiMemoRuleEngine):
    """Render the memo library tab with memo selector."""
    st.markdown('<div class="step-header">📚 Loaded Memos Overview</div>', unsafe_allow_html=True)
    
    # Get list of loaded memos
    memos = engine.memo_manager.memos
    if not memos:
        st.warning("No memos loaded.")
        return
    
    memo_options = sorted(memos.keys())
    
    # Memo selector
    selected_memo = st.selectbox(
        "Select a Memo to View Details",
        options=memo_options,
        format_func=lambda x: f"{x} - {memos[x].metadata.project_name}" if memos[x].metadata else x
    )
    
    st.markdown("---")
    
    # Display selected memo details and rules
    if selected_memo:
        render_memo_detail_with_rules(engine, selected_memo)


if __name__ == "__main__":
    main()
