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
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E3A5F;
        text-align: center;
        padding: 1rem;
        border-bottom: 3px solid #E8B54B;
        margin-bottom: 2rem;
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
    .audit-trail {
        background: #f1f3f4;
        border: 1px solid #dadce0;
        padding: 1rem;
        border-radius: 8px;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def load_engine():
    """Load the rule engine (cached for performance)."""
    rules_path = Path(__file__).parent.parent / "artifact" / "extracted-rules.json"
    return create_engine(str(rules_path))


def format_currency(amount: float) -> str:
    """Format amount as Malaysian Ringgit."""
    return f"RM {amount:,.2f}"


def render_header():
    """Render the main header."""
    st.markdown('<div class="main-header">🏢 Aetas Seputeh<br>Commission & Rebate Calculator</div>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="transparency-box">
        <h3 style="margin:0;">🔍 Transparency First</h3>
        <p style="margin:0.5rem 0 0 0;">
            This system provides complete visibility into how commissions and rebates are calculated. 
            Every rule selection and calculation step is fully traceable and auditable.
        </p>
    </div>
    """, unsafe_allow_html=True)


def render_input_section() -> Dict[str, Any]:
    """Render the input form and return user context."""
    st.markdown('<div class="step-header">📝 Step 1: Enter Property & Buyer Details</div>', unsafe_allow_html=True)
    
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


def render_rule_matching(engine: RuleEngine, context: Dict[str, Any]) -> Dict[str, List[MatchedRule]]:
    """Render the rule matching process with transparency."""
    st.markdown('<div class="step-header">🎯 Step 2: Rule Matching - Which Rules Apply?</div>', unsafe_allow_html=True)
    
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
    with st.expander("💼 **Commission Rules** - Click to see matching details", expanded=True):
        render_commission_rule_matching(engine, context, all_matches.get('commission', []))
    
    # Show rebate rules
    with st.expander("🎁 **Rebate Rules** - Click to see matching details", expanded=True):
        render_rebate_rule_matching(engine, context, all_matches.get('rebate', []))
    
    return all_matches


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
                        <strong>Why Not Matched:</strong> {match_explanation}
                    </div>
                    """, unsafe_allow_html=True)


def render_rebate_rule_matching(engine: RuleEngine, context: Dict[str, Any], matched: List[MatchedRule]):
    """Render rebate rule matching with why/why not explanations."""
    matched_ids = {m.rule_id for m in matched}
    
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
                
                if is_matched:
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
        st.markdown("#### Input Parameters")
        st.json(context)
        
        st.markdown("#### Rules Applied")
        st.write(f"**Matched Rule IDs:** {', '.join(result.matched_rules)}")
        
        st.markdown("#### Rebate Details")
        for r in result.rebate_breakdown:
            st.write(f"- **{r.rule_id}**: {r.rule_name} - {r.value}% = {format_currency(r.calculated_amount)}")
        
        st.markdown("#### Commission Details")
        for c in result.commission_breakdown:
            st.write(f"- **{c.rule_id}**: {c.rule_name} - {c.value}% = {format_currency(c.calculated_amount)}")
        
        st.markdown("#### Final Amounts")
        st.write(f"- **Base Price:** {format_currency(result.base_price)}")
        st.write(f"- **Total Rebate:** {format_currency(result.total_rebate)}")
        st.write(f"- **Final Price:** {format_currency(result.final_price)}")
        st.write(f"- **Total Commission:** {format_currency(result.total_commission)}")


def main():
    """Main application entry point."""
    # Load engine
    engine = load_engine()
    
    # Render header
    render_header()
    
    st.markdown("---")
    
    # Step 1: Input
    context = render_input_section()
    
    st.markdown("---")
    
    # Show input summary
    render_input_summary(context)
    
    st.markdown("---")
    
    # Calculate button
    if st.button("🔍 Calculate Commission & Rebates", type="primary", use_container_width=True):
        st.markdown("---")
        
        # Step 2: Rule Matching
        all_matches = render_rule_matching(engine, context)
        
        st.markdown("---")
        
        # Get calculation result
        result = engine.calculate(context)
        
        # Step 3: Calculation Breakdown
        render_calculation_breakdown(engine, context, result)
        
        st.markdown("---")
        
        # Step 4: Final Summary
        render_final_summary(result)
        
        st.markdown("---")
        
        # Audit Trail
        render_audit_trail(context, result)
        
        # Success message
        st.success("✅ Calculation complete! All steps have been documented above for full transparency.")


if __name__ == "__main__":
    main()
