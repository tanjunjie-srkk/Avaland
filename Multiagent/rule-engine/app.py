"""
Rule Engine Demo - Streamlit UI
Transparent Commission & Rebate Calculation System

Focus: Transparency for finance stakeholders
- Clear input → rule matching → calculation flow
- Visual step-by-step breakdown
- Audit trail for every calculation
"""

import streamlit as st
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from rule_engine import RuleEngine, create_engine, PricingResult
from rule_matcher import MatchedRule

# Page configuration
st.set_page_config(
    page_title="Commission Calculator - Aetas Seputeh",
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
    .savings-highlight {
        background: linear-gradient(135deg, #ff6b6b 0%, #feca57 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 12px;
        text-align: center;
        margin: 1rem 0;
    }
    .commission-highlight {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 12px;
        text-align: center;
    }
    .input-section {
        background: #ffffff;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        border: 1px solid #e9ecef;
    }
    .audit-trail {
        background: #f1f3f4;
        border: 1px solid #dadce0;
        padding: 1rem;
        border-radius: 8px;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)


# Available memos configuration with effective periods
AVAILABLE_MEMOS = {
    "extracted-rules.json": {
        "display_name": "AVALUX-AD-MEMO-SM-2025-009 - Aetas Seputeh",
        "start_date": "2025-06-15",
        "end_date": "2025-12-31"
    },
    "mockedrules.json": {
        "display_name": "MOCK-MEMO-TEST-001 - Mock Project Alpha",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31"
    },
    "mockedrules2.json": {
        "display_name": "MOCK-MEMO-TEST-002 - Mock Project Beta",
        "start_date": "2026-07-01",
        "end_date": "2027-06-30"
    }
}


def get_memo_for_date(spa_date) -> tuple[str, dict]:
    """
    Find the correct memo based on SPA signed date.
    Returns (memo_file, memo_info) or (None, None) if no match.
    """
    from datetime import datetime
    
    for memo_file, memo_info in AVAILABLE_MEMOS.items():
        start = datetime.strptime(memo_info["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(memo_info["end_date"], "%Y-%m-%d").date()
        
        if start <= spa_date <= end:
            return memo_file, memo_info
    
    return None, None


def load_engine(memo_file: str = "extracted-rules.json"):
    """Load the rule engine for a specific memo file."""
    rules_path = Path(__file__).parent.parent / "artifact" / memo_file
    return create_engine(str(rules_path))


def format_currency(amount: float) -> str:
    """Format amount as Malaysian Ringgit."""
    return f"RM {amount:,.2f}"


def render_header(engine: RuleEngine):
    """Render the main header with dynamic project info."""
    metadata = engine.metadata
    project_name = metadata.get('project_name', 'Property Project')
    memo_ref = metadata.get('memo_reference', 'N/A')
    
    st.markdown(f'<div class="main-header">🏢 {project_name}<br><span style="font-size: 1.2rem; font-weight: normal;">Intelligent Commission & Rebate Calculator</span><br><span style="font-size: 0.9rem; color: #666;">📋 {memo_ref}</span></div>', unsafe_allow_html=True)


def render_rule_library(engine: RuleEngine):
    """Render the complete rule library visualization in the sidebar."""
    with st.sidebar:
        st.markdown("## 📚 Rule Library")
        st.markdown("---")
        
        # Get metadata
        metadata = engine.metadata
        
        # Show memo info
        st.markdown(f"""
        <div style="background: #e8f4f8; padding: 0.8rem; border-radius: 8px; margin-bottom: 1rem; font-size: 0.85rem;">
            <strong>📋 Memo Reference:</strong><br>
            {metadata.get('memo_reference', 'N/A')}<br><br>
            <strong>📅 Effective Period:</strong><br>
            {metadata.get('effective_period', {}).get('start_date', 'N/A')} - {metadata.get('effective_period', {}).get('end_date', 'N/A')}<br><br>
            <strong>🏗️ Project:</strong><br>
            {metadata.get('project_name', 'N/A')}
        </div>
        """, unsafe_allow_html=True)
        
        # Rule counts
        total_rules = len(engine.library.rules)
        rule_types = engine.library.get_all_types()
        
        st.metric("Total Rules", total_rules)
        
        st.markdown("---")
        
        # Commission Rules
        with st.expander("💼 Commission Rules", expanded=False):
            comm_rules = engine.library.get_by_type('commission')
            for rule in comm_rules:
                render_rule_card(rule, 'commission')
        
        # Rebate Rules
        with st.expander("🎁 Rebate Rules", expanded=False):
            rebate_rules = engine.library.get_by_type('rebate')
            for rule in rebate_rules:
                render_rule_card(rule, 'rebate')
        
        # Referral Rules
        with st.expander("🤝 Referral Rules", expanded=False):
            ref_rules = engine.library.get_by_type('referral')
            for rule in ref_rules:
                render_rule_card(rule, 'referral')
        
        # Price Adjustment Rules
        with st.expander("📈 Price Adjustment Rules", expanded=False):
            price_rules = engine.library.get_by_type('price_adjustment')
            for rule in price_rules:
                render_rule_card(rule, 'price_adjustment')
        
        # Package Rules
        with st.expander("📦 Package Rules", expanded=False):
            pkg_rules = engine.library.get_by_type('package')
            for rule in pkg_rules:
                render_rule_card(rule, 'package')
        
        st.markdown("---")
        st.markdown(f"""
        <div style="font-size: 0.75rem; color: #666;">
            <strong>Confidence:</strong> {metadata.get('extraction_confidence', 0) * 100:.0f}%
        </div>
        """, unsafe_allow_html=True)


def render_rule_card(rule, rule_type: str):
    """Render a single rule card in the sidebar."""
    # Color coding by rule type
    colors = {
        'commission': '#28a745',
        'rebate': '#17a2b8',
        'referral': '#ffc107',
        'price_adjustment': '#6f42c1',
        'package': '#fd7e14'
    }
    color = colors.get(rule_type, '#6c757d')
    
    st.markdown(f"""
    <div style="background: white; border-left: 3px solid {color}; padding: 0.6rem; margin: 0.4rem 0; border-radius: 0 6px 6px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
        <div style="font-weight: bold; font-size: 0.85rem; color: #333;">{rule.rule_name}</div>
        <div style="font-size: 0.7rem; color: #666;">{rule.rule_id}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Show conditions
    if rule.conditions:
        for cond in rule.conditions:
            if isinstance(cond, dict):
                condition_str = cond.get('condition', '')
                
                # Get value based on rule type
                if 'commission_percentage' in cond:
                    value = f"{cond['commission_percentage']}%"
                    value_label = "Commission"
                elif 'rebate_percentage' in cond:
                    value = f"{cond['rebate_percentage']}%"
                    value_label = "Rebate"
                elif 'adjustment_amount' in cond:
                    value = f"RM {cond['adjustment_amount']:,}"
                    value_label = "Adjustment"
                else:
                    value = None
                    value_label = None
                
                desc = cond.get('description', '')
                
                if condition_str:
                    # Clean up condition for display
                    display_cond = condition_str.replace("IF ", "").replace(" AND ", " & ").replace(" OR ", " | ")
                    st.markdown(f"""
                    <div style="font-size: 0.7rem; color: #555; padding: 0.3rem 0.5rem; background: #f8f9fa; border-radius: 4px; margin: 0.2rem 0;">
                        <code style="font-size: 0.65rem;">{display_cond}</code>
                        {f'<br><span style="color: {color}; font-weight: bold;">→ {value_label}: {value}</span>' if value else ''}
                        {f'<br><span style="color: #888; font-style: italic;">{desc}</span>' if desc else ''}
                    </div>
                    """, unsafe_allow_html=True)
    
    # For referral rules, show reward
    if rule_type == 'referral':
        reward = rule.raw_data.get('reward_amount', 0)
        reward_type = rule.raw_data.get('reward_type', 'fixed')
        payout = rule.raw_data.get('payout_timing', '')
        
        if reward_type == 'percentage':
            reward_str = f"{reward}%"
        else:
            reward_str = f"RM {reward:,}"
        
        st.markdown(f"""
        <div style="font-size: 0.7rem; padding: 0.3rem 0.5rem; background: #fff3cd; border-radius: 4px; margin: 0.2rem 0;">
            <span style="color: #856404; font-weight: bold;">Reward: {reward_str}</span>
            {f'<br><span style="color: #666;">Payout: {payout}</span>' if payout else ''}
        </div>
        """, unsafe_allow_html=True)
    
    # For package rules, show value
    if rule_type == 'package':
        pkg_value = rule.raw_data.get('value', '')
        eligibility = rule.raw_data.get('eligibility', [])
        
        st.markdown(f"""
        <div style="font-size: 0.7rem; padding: 0.3rem 0.5rem; background: #ffe5d0; border-radius: 4px; margin: 0.2rem 0;">
            <span style="color: #a54200; font-weight: bold;">Value: {pkg_value}</span>
            {f'<br><span style="color: #666;">For: {", ".join(eligibility[:2])}</span>' if eligibility else ''}
        </div>
        """, unsafe_allow_html=True)


def render_input_section() -> Dict[str, Any]:
    """Render the input form and return user context."""
    st.markdown('<div class="step-header">📝 Step 1: Enter Property & Buyer Details</div>', unsafe_allow_html=True)
    
    # SPA Signed Date - determines which memo to use
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 1rem 1.5rem; border-radius: 12px; margin-bottom: 1rem;">
        <div style="color: #a0aec0; font-size: 0.8rem; margin-bottom: 0.25rem;">📅 SPA SIGNED DATE</div>
        <div style="color: #e2e8f0; font-size: 0.75rem;">The system will automatically select the correct policy memo based on this date</div>
    </div>
    """, unsafe_allow_html=True)
    
    from datetime import date, datetime
    spa_date = st.date_input(
        "Date of SPA Signing",
        value=date.today(),
        help="The date when the Sale & Purchase Agreement was signed. This determines which policy memo applies."
    )
    
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


def render_input_summary(context: Dict[str, Any]):
    """Render a summary of user inputs."""
    st.markdown("### 📋 Your Input Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("List Price", format_currency(context["base_price"]))
    with col2:
        st.metric("Block", context["block"])
    with col3:
        st.metric("Floor Level", context["floor_level"])
    with col4:
        st.metric("Buyer Type", context["buyer_type"].title())
    
    # Show special attributes
    special_attrs = []
    if context["buyer_is_bumi"]:
        special_attrs.append("🏷️ Bumiputera")
    if context["is_garden_unit"]:
        special_attrs.append("🌿 Garden Unit")
    if context["is_penthouse"]:
        special_attrs.append("🏰 Penthouse")
    if context["loan_purchase"]:
        special_attrs.append("🏦 Loan Purchase")
    
    if special_attrs:
        st.info(f"**Special Attributes:** {' | '.join(special_attrs)}")


def render_rule_matching(engine: RuleEngine, context: Dict[str, Any]):
    """Render the rule matching process with transparency."""
    st.markdown("""
    <div style="background: #e7f3ff; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
        <strong>How Rule Matching Works:</strong><br>
        Each rule has specific conditions. We evaluate your inputs against all rules to find which ones apply.
        <span style="color: green;">✓ Green</span> = Rule applies | 
        <span style="color: gray;">Gray</span> = Rule does not apply
    </div>
    """, unsafe_allow_html=True)
    
    all_matches = engine.get_applicable_rules(context)
    
    # Show commission rules
    st.markdown("#### 💼 Commission Rules")
    render_commission_rule_matching(engine, context, all_matches.get('commission', []))
    
    # Show rebate rules
    st.markdown("#### 🎁 Rebate Rules")
    render_rebate_rule_matching(engine, context, all_matches.get('rebate', []))


def render_commission_rule_matching(engine: RuleEngine, context: Dict[str, Any], matched: List[MatchedRule]):
    """Render commission rule matching with why/why not explanations."""
    matched_ids = {m.rule_id for m in matched}
    
    # Get all commission rules
    all_comm_rules = engine.library.get_by_type('commission')
    
    for rule in all_comm_rules:
        is_matched = rule.rule_id in matched_ids
        card_class = "rule-card" if is_matched else "rule-card-inactive"
        icon = "✅" if is_matched else "❌"
        
        st.markdown(f"""
        <div class="{card_class}">
            <strong>{icon} {rule.rule_name}</strong> ({rule.rule_id})
        </div>
        """, unsafe_allow_html=True)
        
        # Show conditions and why it matched/didn't match
        for cond in rule.conditions:
            if isinstance(cond, dict) and 'condition' in cond:
                condition_str = cond['condition']
                description = cond.get('description', '')
                percentage = cond.get('commission_percentage', 'N/A')
                
                # Explain the condition
                match_explanation = explain_condition_match(condition_str, context)
                
                if is_matched and any(m.rule_id == rule.rule_id and m.get_percentage() == percentage for m in matched):
                    st.markdown(f"""
                    <div class="match-reason">
                        <strong>Condition:</strong> {condition_str}<br>
                        <strong>Commission:</strong> {percentage}%<br>
                        <strong>Why Matched:</strong> {match_explanation}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="no-match-reason">
                        <strong>Condition:</strong> {condition_str}<br>
                        <strong>Commission:</strong> {percentage}%<br>
                        <strong>Why Not Matched:</strong> {match_explanation}
                    </div>
                    """, unsafe_allow_html=True)


def render_rebate_rule_matching(engine: RuleEngine, context: Dict[str, Any], matched: List[MatchedRule]):
    """Render rebate rule matching with why/why not explanations."""
    matched_ids = {m.rule_id for m in matched}
    
    # Get matched percentages for each rule to identify which specific condition matched
    matched_conditions = {}
    for m in matched:
        if m.matched_condition:
            pct = m.matched_condition.get('rebate_percentage')
            if pct:
                matched_conditions[(m.rule_id, pct)] = True
    
    all_rebate_rules = engine.library.get_by_type('rebate')
    
    for rule in all_rebate_rules:
        is_matched = rule.rule_id in matched_ids
        card_class = "rule-card" if is_matched else "rule-card-inactive"
        icon = "✅" if is_matched else "❌"
        
        st.markdown(f"""
        <div class="{card_class}">
            <strong>{icon} {rule.rule_name}</strong> ({rule.rule_id})
        </div>
        """, unsafe_allow_html=True)
        
        for cond in rule.conditions:
            if isinstance(cond, dict) and 'condition' in cond:
                condition_str = cond['condition']
                percentage = cond.get('rebate_percentage', 'N/A')
                
                match_explanation = explain_condition_match(condition_str, context)
                
                # Check if THIS specific condition matched (not just the rule)
                condition_matched = (rule.rule_id, percentage) in matched_conditions
                
                if condition_matched:
                    st.markdown(f"""
                    <div class="match-reason">
                        <strong>Condition:</strong> {condition_str}<br>
                        <strong>Rebate:</strong> {percentage}%<br>
                        <strong>Why Matched:</strong> {match_explanation}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="no-match-reason">
                        <strong>Condition:</strong> {condition_str}<br>
                        <strong>Rebate:</strong> {percentage}%<br>
                        <strong>Why Not Matched:</strong> {match_explanation}
                    </div>
                    """, unsafe_allow_html=True)


def explain_condition_match(condition_str: str, context: Dict[str, Any]) -> str:
    """Generate human-readable explanation of why a condition matched or didn't."""
    explanations = []
    
    # Parse the condition and explain each part
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


def render_calculation_breakdown(engine: RuleEngine, context: Dict[str, Any], result: PricingResult):
    """Render step-by-step calculation with full transparency."""
    st.markdown('<div class="step-header">🧮 Step 3: Calculation Breakdown - How We Got the Numbers</div>', unsafe_allow_html=True)
    
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
    
    running_total = result.base_price
    accumulated_rebate = 0
    
    if result.rebate_breakdown:
        for i, rebate in enumerate(result.rebate_breakdown, 1):
            calc_base = rebate.details.get('effective_price', result.base_price)
            
            st.markdown(f"""
            <div class="calculation-step">
                <strong>Rebate {i}: {rebate.rule_name}</strong><br>
                <hr style="margin: 0.5rem 0;">
                <strong>Rule Applied:</strong> {rebate.rule_id}<br>
                <strong>Rebate Rate:</strong> {rebate.value}%<br>
                <strong>Calculation Base:</strong> {format_currency(calc_base)}<br>
                <br>
                <div class="formula-box">
                    <strong>Formula:</strong> {format_currency(calc_base)} × {rebate.value}% = <span class="highlight-value">{format_currency(rebate.calculated_amount)}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            accumulated_rebate += rebate.calculated_amount
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
            comm_base = comm.details.get('commission_base', net_price)
            payout_spa = comm.details.get('payout_spa', 0)
            payout_stage2a = comm.details.get('payout_stage2a', 0)
            
            st.markdown(f"""
            <div class="calculation-step">
                <strong>Commission: {comm.rule_name}</strong><br>
                <hr style="margin: 0.5rem 0;">
                <strong>Rule Applied:</strong> {comm.rule_id}<br>
                <strong>Commission Rate:</strong> {comm.value}%<br>
                <strong>Commission Base:</strong> {format_currency(comm_base)}<br>
                <br>
                <div class="formula-box">
                    <strong>Formula:</strong> {format_currency(comm_base)} × {comm.value}% = <span class="highlight-value">{format_currency(comm.calculated_amount)}</span>
                </div>
                <br>
                <strong>Payout Schedule:</strong>
                <ul>
                    <li>Upon SPA (30%): {format_currency(payout_spa)}</li>
                    <li>Upon Stage 2A (70%): {format_currency(payout_stage2a)}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No commission applicable for this scenario.")


def render_final_summary(result: PricingResult):
    """Render the final summary with all numbers."""
    st.markdown('<div class="step-header">📊 Step 4: Final Summary</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="result-summary">
            <h2 style="margin:0;">Base Price</h2>
            <h1 style="margin:0.5rem 0;">{}</h1>
        </div>
        """.format(format_currency(result.base_price)), unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 2rem; border-radius: 12px; text-align: center;">
            <h2 style="margin:0;">Total Rebate</h2>
            <h1 style="margin:0.5rem 0;">(-) {}</h1>
        </div>
        """.format(format_currency(result.total_rebate)), unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="result-summary">
            <h2 style="margin:0;">Final Price</h2>
            <h1 style="margin:0.5rem 0;">{}</h1>
        </div>
        """.format(format_currency(result.final_price)), unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Commission Summary
    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1.5rem; border-radius: 12px; text-align: center;">
        <h2 style="margin:0;">Total Agent Commission</h2>
        <h1 style="margin:0.5rem 0;">{}</h1>
    </div>
    """.format(format_currency(result.total_commission)), unsafe_allow_html=True)


def render_audit_trail(context: Dict[str, Any], result: PricingResult):
    """Render a complete audit trail for compliance."""
    st.markdown('<div class="step-header">📜 Audit Trail - Complete Record</div>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="audit-trail">
        <strong>This section provides a complete audit trail for compliance and record-keeping purposes.</strong>
    </div>
    """, unsafe_allow_html=True)
    
    with st.expander("📋 View Complete Audit Trail", expanded=False):
        render_audit_trail_content(context, result)


def render_audit_trail_content(context: Dict[str, Any], result: PricingResult):
    """Render the audit trail content (can be used standalone or in expander)."""
    st.markdown("#### 📥 Input Parameters")
    st.json(context)
    
    st.markdown("#### ✅ Rules Applied")
    st.write(f"**Matched Rule IDs:** {', '.join(result.matched_rules)}")
    
    st.markdown("#### 🎁 Rebate Details")
    for r in result.rebate_breakdown:
        st.write(f"- **{r.rule_id}**: {r.rule_name} - {r.value}% = {format_currency(r.calculated_amount)}")
    
    st.markdown("#### 💼 Commission Details")
    for c in result.commission_breakdown:
        st.write(f"- **{c.rule_id}**: {c.rule_name} - {c.value}% = {format_currency(c.calculated_amount)}")
    
    st.markdown("#### 📊 Final Amounts")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"- **Base Price:** {format_currency(result.base_price)}")
        st.write(f"- **Total Rebate:** {format_currency(result.total_rebate)}")
    with col2:
        st.write(f"- **Final Price:** {format_currency(result.final_price)}")
        st.write(f"- **Total Commission:** {format_currency(result.total_commission)}")


def main():
    """Main application entry point."""
    
    # Create tabs for different views
    tab1, tab2 = st.tabs(["🧮 Calculator", "📚 Full Rule Library"])
    
    with tab1:
        render_calculator_tab()
    
    with tab2:
        render_full_rule_library_tab_with_selector()


def render_calculator_tab():
    """Render the main calculator tab with auto-memo selection based on SPA date."""
    
    # Step 1: Input - Make it compact and professional
    context = render_input_section()
    
    # Auto-select memo based on SPA date
    spa_date = context.get('spa_date')
    memo_file, memo_info = get_memo_for_date(spa_date)
    
    if memo_file is None:
        st.error(f"""
        ⚠️ **No Policy Memo Found**
        
        No active policy memo covers the SPA date of **{spa_date.strftime('%d %b %Y')}**.
        
        Please check the SPA signed date or contact administration for guidance.
        """)
        return
    
    # Load engine for the matched memo
    engine = load_engine(memo_file)
    
    # Show which memo is being used
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #0f5132 0%, #198754 100%); padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1rem;">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span style="font-size: 1.2rem;">✅</span>
            <div>
                <div style="color: #d1e7dd; font-size: 0.7rem; text-transform: uppercase;">Auto-Selected Policy Memo</div>
                <div style="color: white; font-weight: 600;">{memo_info['display_name']}</div>
                <div style="color: #a3cfbb; font-size: 0.75rem;">Effective: {memo_info['start_date']} to {memo_info['end_date']}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Render header with memo context
    render_header(engine)
    
    st.markdown("---")
    
    # Calculate button for presentation control
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        calculate_clicked = st.button(
            "🔍 Calculate Commission & Rebates",
            type="primary",
            use_container_width=True
        )
    
    # Use session state to persist calculation results
    if calculate_clicked:
        st.session_state['calculated'] = True
        st.session_state['context'] = context
        st.session_state['result'] = engine.calculate(context)
        st.session_state['all_matches'] = engine.get_applicable_rules(context)
    
    # Show results if calculated
    if st.session_state.get('calculated', False):
        result = st.session_state['result']
        all_matches = st.session_state['all_matches']
        
        st.markdown("---")
        
        # EXECUTIVE SUMMARY - Show results FIRST
        render_executive_summary(engine, context, result, all_matches)
        
        st.markdown("---")
        
        # Expandable details section
        st.markdown('<div class="step-header">📊 Detailed Breakdown</div>', unsafe_allow_html=True)
        
        # Calculation breakdown in expander
        with st.expander("🧮 **View Calculation Details** - Step-by-step formula breakdown", expanded=False):
            render_calculation_breakdown(engine, context, result)
        
        # Rule matching in expander
        with st.expander("🎯 **View Rule Matching Details** - Which rules were applied and why", expanded=False):
            render_rule_matching(engine, context)
        
        # Audit Trail
        with st.expander("📜 **Audit Trail** - Complete record for compliance", expanded=False):
            render_audit_trail_content(context, result)


def render_executive_summary(engine: RuleEngine, context: Dict[str, Any], result: PricingResult, all_matches: Dict):
    """Render the executive summary with key metrics upfront."""
    
    # Calculate key metrics
    savings_percentage = (result.total_rebate / result.base_price) * 100 if result.base_price > 0 else 0
    commission_percentage = (result.total_commission / (result.base_price - result.total_rebate)) * 100 if (result.base_price - result.total_rebate) > 0 else 0
    rules_applied = len(result.matched_rules)
    total_rules = len(engine.library.rules)
    
    # Executive Summary Header
    st.markdown("""
    <div style="text-align: center; margin-bottom: 1.5rem;">
        <h2 style="color: #1E3A5F; margin: 0; font-size: 1.8rem;">💼 Executive Summary</h2>
        <p style="color: #666; margin: 0.5rem 0 0 0; font-size: 0.9rem;">Calculation results based on your transaction details</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Main KPI Cards Row
    st.markdown("""
    <style>
        .kpi-card {
            text-align: center;
            padding: 1.25rem 1rem;
            border-radius: 12px;
            min-height: 120px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .kpi-label {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 0.5rem;
        }
        .kpi-value {
            font-size: 1.6rem;
            font-weight: 700;
        }
        .kpi-subtitle {
            font-size: 0.8rem;
            margin-top: 0.3rem;
            min-height: 1.2rem;
        }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="kpi-card" style="background: rgba(173, 216, 230, 0.15); border: 1px solid rgba(0, 0, 139, 0.3);">
            <div class="kpi-label" style="color:#00008B;">List Price</div>
            <div class="kpi-value" style="color: #00008B;">{format_currency(result.base_price)}</div>
            <div class="kpi-subtitle" style="color: #00008B;">&nbsp;</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="kpi-card" style="background: rgba(74, 222, 128, 0.15); border: 1px solid rgba(74, 222, 128, 0.3);">
            <div class="kpi-label" style="color: #4ade80;">💰 Total Savings</div>
            <div class="kpi-value" style="color: #4ade80;">{format_currency(result.total_rebate)}</div>
            <div class="kpi-subtitle" style="color: #4ade80;">↓ {savings_percentage:.1f}% discount</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="kpi-card" style="background: rgba(96, 165, 250, 0.15); border: 1px solid rgba(96, 165, 250, 0.3);">
            <div class="kpi-label" style="color: #60a5fa;">🏷️ Net Price</div>
            <div class="kpi-value" style="color: #60a5fa;">{format_currency(result.final_price)}</div>
            <div class="kpi-subtitle" style="color: #60a5fa;">&nbsp;</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="kpi-card" style="background: rgba(244, 114, 182, 0.15); border: 1px solid rgba(244, 114, 182, 0.3);">
            <div class="kpi-label" style="color: #f472b6;">💼 Commission</div>
            <div class="kpi-value" style="color: #f472b6;">{format_currency(result.total_commission)}</div>
            <div class="kpi-subtitle" style="color: #f472b6;">{commission_percentage:.1f}% rate</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Rules Applied Section
    st.markdown("""
    <div style="margin-bottom: 1rem;">
        <h3 style="color: #1E3A5F; margin: 0 0 1rem 0; font-size: 1.3rem; border-bottom: 2px solid #E8B54B; padding-bottom: 0.5rem;">
            📋 Applied Rules & Breakdown
        </h3>
    </div>
    """, unsafe_allow_html=True)
    
    # Two column layout for rebates and commission
    col_rebate, col_commission = st.columns(2)
    
    with col_rebate:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #f0fff4 0%, #dcfce7 100%); padding: 1.5rem; border-radius: 12px; border: 1px solid #86efac; height: 100%;">
            <div style="display: flex; align-items: center; margin-bottom: 1rem;">
                <span style="font-size: 1.5rem; margin-right: 0.5rem;">🎁</span>
                <span style="font-size: 1.1rem; font-weight: 600; color: #166534;">Rebates Applied</span>
            </div>
        """, unsafe_allow_html=True)
        
        if result.rebate_breakdown:
            for rebate in result.rebate_breakdown:
                st.markdown(f"""
                <div style="background: white; padding: 1rem; border-radius: 8px; margin-bottom: 0.75rem; border-left: 4px solid #22c55e; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <div style="font-weight: 600; color: #166534; font-size: 0.95rem;">{rebate.rule_name}</div>
                            <div style="color: #666; font-size: 0.8rem; margin-top: 0.25rem;">Rate: {rebate.value}%</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 1.2rem; font-weight: 700; color: #16a34a;">-{format_currency(rebate.calculated_amount)}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="background: #166534; color: white; padding: 0.75rem 1rem; border-radius: 8px; margin-top: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 600;">Total Rebate</span>
                    <span style="font-size: 1.1rem; font-weight: 700;">{format_currency(result.total_rebate)}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="color: #666; font-style: italic;">No rebates applicable</div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col_commission:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%); padding: 1.5rem; border-radius: 12px; border: 1px solid #c4b5fd; height: 100%;">
            <div style="display: flex; align-items: center; margin-bottom: 1rem;">
                <span style="font-size: 1.5rem; margin-right: 0.5rem;">💼</span>
                <span style="font-size: 1.1rem; font-weight: 600; color: #5b21b6;">Commission Details</span>
            </div>
        """, unsafe_allow_html=True)
        
        if result.commission_breakdown:
            for comm in result.commission_breakdown:
                payout_spa = comm.details.get('payout_spa', 0)
                payout_stage2a = comm.details.get('payout_stage2a', 0)
                comm_base = comm.details.get('commission_base', 0)
                
                st.markdown(f"""
                <div style="background: white; padding: 1rem; border-radius: 8px; margin-bottom: 0.75rem; border-left: 4px solid #8b5cf6; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <div style="font-weight: 600; color: #5b21b6; font-size: 0.95rem; margin-bottom: 0.5rem;">{comm.rule_name}</div>
                    <div style="color: #666; font-size: 0.8rem; margin-bottom: 0.75rem;">
                        Rate: {comm.value}% on {format_currency(comm_base)}
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; padding-top: 0.5rem; border-top: 1px dashed #e5e7eb;">
                        <div style="font-size: 1.3rem; font-weight: 700; color: #7c3aed;">{format_currency(comm.calculated_amount)}</div>
                    </div>
                </div>
                
                <div style="background: #f5f3ff; padding: 0.75rem; border-radius: 8px; margin-bottom: 0.75rem;">
                    <div style="font-size: 0.8rem; color: #5b21b6; font-weight: 600; margin-bottom: 0.5rem;">📅 Payout Schedule</div>
                    <div style="display: flex; justify-content: space-between;">
                        <div style="text-align: center; flex: 1;">
                            <div style="font-size: 0.7rem; color: #666;">Upon SPA (30%)</div>
                            <div style="font-weight: 600; color: #5b21b6;">{format_currency(payout_spa)}</div>
                        </div>
                        <div style="width: 1px; background: #c4b5fd; margin: 0 0.5rem;"></div>
                        <div style="text-align: center; flex: 1;">
                            <div style="font-size: 0.7rem; color: #666;">Stage 2A (70%)</div>
                            <div style="font-weight: 600; color: #5b21b6;">{format_currency(payout_stage2a)}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="background: #5b21b6; color: white; padding: 0.75rem 1rem; border-radius: 8px; margin-top: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 600;">Total Commission</span>
                    <span style="font-size: 1.1rem; font-weight: 700;">{format_currency(result.total_commission)}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="color: #666; font-style: italic;">No commission applicable</div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Summary Stats Footer
    st.markdown(f"""
    <div style="background: #f8fafc; padding: 1rem 1.5rem; border-radius: 12px; margin-top: 1.5rem; border: 1px solid #e2e8f0;">
        <div style="display: flex; justify-content: space-around; text-align: center;">
            <div>
                <div style="font-size: 2rem; font-weight: 700; color: #1E3A5F;">{len(result.rebate_breakdown)}</div>
                <div style="font-size: 0.85rem; color: #64748b;">Rebates Applied</div>
            </div>
            <div style="width: 1px; background: #e2e8f0;"></div>
            <div>
                <div style="font-size: 2rem; font-weight: 700; color: #1E3A5F;">{len(result.commission_breakdown)}</div>
                <div style="font-size: 0.85rem; color: #64748b;">Commission Rules</div>
            </div>
            <div style="width: 1px; background: #e2e8f0;"></div>
            <div>
                <div style="font-size: 2rem; font-weight: 700; color: #1E3A5F;">{rules_applied}</div>
                <div style="font-size: 0.85rem; color: #64748b;">Total Rules Matched</div>
            </div>
            <div style="width: 1px; background: #e2e8f0;"></div>
            <div>
                <div style="font-size: 2rem; font-weight: 700; color: #16a34a;">{savings_percentage:.1f}%</div>
                <div style="font-size: 0.85rem; color: #64748b;">Buyer Savings</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_full_rule_library_tab(engine: RuleEngine):
    """Render the full rule library visualization tab."""
    st.markdown('<div class="main-header">📚 Complete Rule Library</div>', unsafe_allow_html=True)
    
    metadata = engine.metadata
    
    # Header info
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📋 Memo Reference", metadata.get('memo_reference', 'N/A'))
    with col2:
        st.metric("🏗️ Project", metadata.get('project_name', 'N/A'))
    with col3:
        effective = metadata.get('effective_period', {})
        st.metric("📅 Effective From", effective.get('start_date', 'N/A'))
    with col4:
        st.metric("📅 Effective Until", effective.get('end_date', 'N/A'))
    
    st.markdown("---")
    
    # Rule statistics
    st.markdown("### 📊 Rule Statistics")
    
    rule_counts = {}
    for rule_type in engine.library.get_all_types():
        rule_counts[rule_type] = len(engine.library.get_by_type(rule_type))
    
    cols = st.columns(len(rule_counts))
    icons = {
        'commission': '💼',
        'rebate': '🎁',
        'referral': '🤝',
        'price_adjustment': '📈',
        'package': '📦'
    }
    
    for i, (rule_type, count) in enumerate(rule_counts.items()):
        with cols[i]:
            st.metric(f"{icons.get(rule_type, '📋')} {rule_type.replace('_', ' ').title()}", count)
    
    st.markdown("---")
    
    # Detailed rule tables
    st.markdown("### 💼 Commission Rules")
    render_commission_rules_table(engine)
    
    st.markdown("---")
    
    st.markdown("### 🎁 Rebate Rules")
    render_rebate_rules_table(engine)
    
    st.markdown("---")
    
    st.markdown("### 🤝 Referral Rules")
    render_referral_rules_table(engine)
    
    st.markdown("---")
    
    st.markdown("### 📈 Price Adjustment Rules")
    render_price_adjustment_rules_table(engine)
    
    st.markdown("---")
    
    st.markdown("### 📦 Package Rules")
    render_package_rules_table(engine)
    
    # Warnings
    warnings = metadata.get('warnings', [])
    if warnings:
        st.markdown("---")
        st.markdown("### ⚠️ Extraction Warnings")
        for warning in warnings:
            st.warning(warning)


def render_commission_rules_table(engine: RuleEngine):
    """Render commission rules as a detailed table."""
    rules = engine.library.get_by_type('commission')
    
    for rule in rules:
        with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
            st.markdown(f"**Buyer Type:** {rule.buyer_type or 'All'}")
            
            # Create table for conditions
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
            
            # Notes
            notes = rule.raw_data.get('notes', [])
            if notes:
                st.markdown("**Notes:**")
                for note in notes:
                    st.markdown(f"- {note}")


def render_rebate_rules_table(engine: RuleEngine):
    """Render rebate rules as a detailed table."""
    rules = engine.library.get_by_type('rebate')
    
    for rule in rules:
        with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
            rebate_type = rule.raw_data.get('rebate_type', 'N/A')
            calc_base = rule.raw_data.get('calculation_base', 'N/A')
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Rebate Type:** {rebate_type}")
            with col2:
                st.markdown(f"**Calculation Base:** {calc_base}")
            
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


def render_referral_rules_table(engine: RuleEngine):
    """Render referral rules as a detailed table."""
    rules = engine.library.get_by_type('referral')
    
    for rule in rules:
        with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
            category = rule.raw_data.get('referrer_category', 'N/A')
            reward = rule.raw_data.get('reward_amount', 0)
            reward_type = rule.raw_data.get('reward_type', 'fixed')
            payout = rule.raw_data.get('payout_timing', 'N/A')
            
            if reward_type == 'percentage':
                reward_str = f"{reward}%"
            else:
                reward_str = f"RM {reward:,}"
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"**Category:** {category}")
            with col2:
                st.markdown(f"**Reward:** {reward_str}")
            with col3:
                st.markdown(f"**Payout:** {payout}")
            
            # Conditions (these are text-based for referrals)
            conditions = rule.raw_data.get('conditions', [])
            if conditions:
                st.markdown("**Requirements:**")
                for cond in conditions:
                    if isinstance(cond, str):
                        st.markdown(f"- ✓ {cond}")
                    elif isinstance(cond, dict) and 'description' in cond:
                        st.markdown(f"- ✓ {cond['description']}")


def render_price_adjustment_rules_table(engine: RuleEngine):
    """Render price adjustment rules as a detailed table."""
    rules = engine.library.get_by_type('price_adjustment')
    
    for rule in rules:
        with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
            adj_type = rule.raw_data.get('adjustment_type', 'N/A')
            st.markdown(f"**Adjustment Type:** {adj_type}")
            
            if rule.conditions:
                st.markdown("**Conditions & Amounts:**")
                for cond in rule.conditions:
                    if isinstance(cond, dict):
                        condition = cond.get('condition', 'N/A')
                        amount = cond.get('adjustment_amount', 0)
                        desc = cond.get('description', '')
                        
                        st.markdown(f"""
                        <div style="background: #f3f0ff; padding: 0.8rem; margin: 0.5rem 0; border-radius: 8px; border-left: 4px solid #6f42c1;">
                            <div style="font-family: monospace; font-size: 0.9rem; color: #333;">
                                <strong>IF</strong> {condition.replace('IF ', '')}
                            </div>
                            <div style="margin-top: 0.5rem;">
                                <span style="background: #6f42c1; color: white; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold;">
                                    Adjustment: RM {amount:,}
                                </span>
                            </div>
                            {f'<div style="margin-top: 0.5rem; color: #666; font-style: italic;">{desc}</div>' if desc else ''}
                        </div>
                        """, unsafe_allow_html=True)


def render_package_rules_table(engine: RuleEngine):
    """Render package rules as a detailed table."""
    rules = engine.library.get_by_type('package')
    
    for rule in rules:
        with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
            pkg_type = rule.raw_data.get('package_type', 'N/A')
            value = rule.raw_data.get('value', 'N/A')
            eligibility = rule.raw_data.get('eligibility', [])
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Package Type:** {pkg_type}")
            with col2:
                st.markdown(f"**Value:** {value}")
            
            if eligibility:
                st.markdown("**Eligibility:**")
                for elig in eligibility:
                    st.markdown(f"- ✓ {elig}")
            
            notes = rule.raw_data.get('notes', [])
            if notes:
                st.markdown("**Notes:**")
                for note in notes:
                    st.markdown(f"- {note}")


def render_full_rule_library_tab_with_selector():
    """Render the full rule library tab with manual memo selector."""
    
    # Memo selector for browsing different policy memos
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 1rem 1.5rem; border-radius: 12px; margin-bottom: 1rem;">
        <div style="color: #a0aec0; font-size: 0.8rem; margin-bottom: 0.25rem;">📋 SELECT POLICY MEMO TO VIEW</div>
        <div style="color: #e2e8f0; font-size: 0.75rem;">Browse rules from different policy memos</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Memo selection dropdown
    selected_memo_file = st.selectbox(
        "Choose a memo to view:",
        options=list(AVAILABLE_MEMOS.keys()),
        format_func=lambda x: AVAILABLE_MEMOS[x]['display_name'],
        key="rule_library_memo_selector"
    )
    
    # Show effective period for selected memo
    memo_info = AVAILABLE_MEMOS[selected_memo_file]
    st.markdown(f"""
    <div style="background: #f0f9ff; padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1rem; border-left: 4px solid #0ea5e9;">
        <span style="color: #0369a1; font-weight: 600;">📅 Effective Period:</span>
        <span style="color: #0c4a6e;">{memo_info['start_date']} to {memo_info['end_date']}</span>
    </div>
    """, unsafe_allow_html=True)
    
    # Load engine for selected memo
    engine = load_engine(selected_memo_file)
    
    # Render the full rule library
    render_full_rule_library_tab(engine)


if __name__ == "__main__":
    main()
