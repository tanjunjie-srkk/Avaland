"""
Management Commission Dashboard - Streamlit UI
POC / Demo: Bird's-eye view for management to review agent commissions,
drill into per-agent breakdowns, and track payment status.

Mock data sourced from demo_data/management_mock_data.json which uses
real rule IDs, memo references, and commission/rebate structures from
the Aetas Seputeh pricing memos.
"""

import streamlit as st
import sys
import pandas as pd
import io
import shutil
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import date, datetime, timedelta
import json

# Add current directory to path so engine imports work
sys.path.insert(0, str(Path(__file__).parent))

from multi_memo_engine import (
    MultiMemoRuleEngine,
    create_multi_memo_engine,
    MultiMemoPricingResult,
    MultiMemoCalculationResult,
)
from memo_manager import MemoType

# ---------------------------------------------------------------------------
# Page configuration (MUST be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Avaland · Commission Management",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# PATH CONSTANTS
# ---------------------------------------------------------------------------

CURRENT_DIR = Path(__file__).parent
ARTIFACT_DIR = CURRENT_DIR.parent.parent / "artifact"
MEMO_IMG_DIR = CURRENT_DIR.parent.parent.parent / "memo"
MEMO_STORE_PATH = CURRENT_DIR / "memo_store.json"

# Ensure OCR & rule-extract modules are importable
OCR_DIR = CURRENT_DIR.parent.parent / "ocr"
RULE_EXTRACT_DIR = CURRENT_DIR.parent.parent / "rule-extract"
sys.path.insert(0, str(OCR_DIR))
sys.path.insert(0, str(RULE_EXTRACT_DIR))

# ---------------------------------------------------------------------------
# DEMO DATA LOADER
# ---------------------------------------------------------------------------

DEMO_DATA_PATH = Path(__file__).parent / "demo_data" / "management_mock_data.json"


@dataclass
class UnitSale:
    """A single property unit sale tied to an agent."""
    unit_id: str
    project: str
    block: str
    floor: int
    unit_type: str
    buyer_name: str
    buyer_type: str  # local / foreign
    buyer_is_bumi: bool
    sale_price: float
    spa_date: str
    # Calculated fields
    commission_rate: float = 0.0
    commission_amount: float = 0.0
    rebate_rate: float = 0.0
    rebate_amount: float = 0.0
    net_price: float = 0.0
    # Breakdown items: list of dicts with {rule_id, label, memo_reference, rate, amount}
    commission_breakdown: List[Dict[str, Any]] = field(default_factory=list)
    rebate_breakdown: List[Dict[str, Any]] = field(default_factory=list)
    packages: List[str] = field(default_factory=list)


@dataclass
class Payment:
    """A single commission payment record."""
    date: str
    reference: str
    amount: float
    status: str  # "paid" | "pending" | "processing"


@dataclass
class Agent:
    """An agent with their portfolio of sales."""
    agent_id: str
    name: str
    initials: str
    team: str
    avatar_color: str
    is_team_leader: bool
    project: str  # primary project
    sales: List[UnitSale] = field(default_factory=list)
    # Aggregated
    total_sales: float = 0.0
    total_commission: float = 0.0
    total_rebate: float = 0.0
    total_previously_paid: float = 0.0
    net_payable: float = 0.0
    status: str = "Pending"  # Pending / Paid / Partial
    payment_history: List[Payment] = field(default_factory=list)


def load_demo_data() -> tuple:
    """Load demo data from JSON file and return (metadata, agents)."""
    with open(DEMO_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    metadata = data["metadata"]
    project_name = metadata["project"]
    agents: List[Agent] = []

    for ag in data["agents"]:
        sales: List[UnitSale] = []
        for s in ag["sales"]:
            comm_breakdown = s.get("commission_breakdown", [])
            reb_breakdown = s.get("rebate_breakdown", [])
            pkgs = s.get("packages", [])

            total_comm = sum(item["amount"] for item in comm_breakdown)
            total_reb = sum(item["amount"] for item in reb_breakdown)
            comm_rate = sum(item["rate"] for item in comm_breakdown)
            reb_rate = sum(item["rate"] for item in reb_breakdown)
            net_price = round(s["sale_price"] - total_reb, 2)

            sale = UnitSale(
                unit_id=s["unit_id"],
                project=project_name,
                block=s["block"],
                floor=s["floor"],
                unit_type=s["unit_type"],
                buyer_name=s["buyer_name"],
                buyer_type=s["buyer_type"],
                buyer_is_bumi=s["buyer_is_bumi"],
                sale_price=s["sale_price"],
                spa_date=s["spa_date"],
                commission_rate=round(comm_rate, 2),
                commission_amount=round(total_comm, 2),
                rebate_rate=round(reb_rate, 2),
                rebate_amount=round(total_reb, 2),
                net_price=net_price,
                commission_breakdown=comm_breakdown,
                rebate_breakdown=reb_breakdown,
                packages=pkgs,
            )
            sales.append(sale)

        total_sales = sum(s.sale_price for s in sales)
        total_comm = sum(s.commission_amount for s in sales)
        total_reb = sum(s.rebate_amount for s in sales)
        # Parse payment history
        payments: List[Payment] = []
        for p in ag.get("payment_history", []):
            pmt_amount = round(total_comm * p["pct"], 2)
            payments.append(Payment(
                date=p["date"],
                reference=p["reference"],
                amount=pmt_amount,
                status=p["status"],
            ))

        previously_paid_pct = ag.get("previously_paid_pct", 0.0)
        previously_paid = round(total_comm * previously_paid_pct, 2)
        net_payable = round(total_comm - previously_paid, 2)

        if net_payable <= 0:
            status = "Paid"
        elif previously_paid > 0:
            status = "Partial"
        else:
            status = "Pending"

        agents.append(Agent(
            agent_id=ag["agent_id"],
            name=ag["name"],
            initials=ag["initials"],
            team=ag["team"],
            avatar_color=ag["avatar_color"],
            is_team_leader=ag["is_team_leader"],
            project=project_name,
            sales=sales,
            total_sales=total_sales,
            total_commission=total_comm,
            total_rebate=total_reb,
            total_previously_paid=previously_paid,
            net_payable=net_payable,
            status=status,
            payment_history=payments,
        ))

    return metadata, agents


# ---------------------------------------------------------------------------
# CALCULATION ENGINE (uses real multi-memo engine from app_multi_memo.py)
# ---------------------------------------------------------------------------

def _create_engine() -> MultiMemoRuleEngine:
    """Create a fresh multi-memo engine instance."""
    artifacts_path = Path(__file__).parent.parent.parent / "artifact"
    return create_multi_memo_engine(str(artifacts_path))


def run_engine_calculation(form_data: Dict[str, Any]) -> MultiMemoPricingResult:
    """
    Run the real rule engine against user-supplied property / buyer inputs.
    Returns a MultiMemoPricingResult with full commission & rebate breakdowns.
    """
    engine = _create_engine()

    spa_dt = form_data["spa_date"]  # date object
    target_datetime = datetime.combine(spa_dt, datetime.min.time())

    # Prepare (filter memos by project + date, resolve conflicts)
    engine.retrieve_and_prepare(
        project_name="Aetas Seputeh",
        target_date=target_datetime,
    )

    # Build context dict matching what app_multi_memo.py sends
    context = {
        "spa_date": spa_dt,
        "project_filter": "Aetas Seputeh",
        "base_price": form_data["sale_price"],
        "block": form_data["block"],
        "floor_level": form_data["floor"],
        "buyer_type": form_data["buyer_type"].lower(),
        "buyer_is_bumi": form_data["buyer_is_bumi"],
        "unit_type": form_data["unit_type"],
        "is_garden_unit": form_data.get("is_garden_unit", False),
        "is_penthouse": form_data.get("is_penthouse", False),
        "loan_purchase": form_data.get("loan_purchase", False),
    }

    spa_date_str = spa_dt.strftime("%d %b %Y")
    result = engine.calculate(context, project_name="Aetas Seputeh", spa_date=spa_date_str)
    return result


def pricing_result_to_sale_entry(form_data: Dict[str, Any], result: MultiMemoPricingResult) -> Dict:
    """Convert a MultiMemoPricingResult into the JSON sale-entry schema used by management_mock_data.json."""
    comm_breakdown = []
    for item in result.commission_breakdown:
        comm_breakdown.append({
            "rule_id": item.rule_id,
            "label": item.rule_name,
            "memo_reference": item.memo_reference or "",
            "rate": item.value,
            "amount": round(item.calculated_amount or 0, 2),
        })

    reb_breakdown = []
    for item in result.rebate_breakdown:
        reb_breakdown.append({
            "rule_id": item.rule_id,
            "label": item.rule_name,
            "memo_reference": item.memo_reference or "",
            "rate": item.value,
            "amount": round(item.calculated_amount or 0, 2),
        })

    return {
        "unit_id": form_data["unit_id"],
        "block": form_data["block"],
        "floor": form_data["floor"],
        "unit_type": form_data["unit_type"],
        "buyer_name": form_data["buyer_name"],
        "buyer_type": form_data["buyer_type"].lower(),
        "buyer_is_bumi": form_data["buyer_is_bumi"],
        "sale_price": form_data["sale_price"],
        "spa_date": form_data["spa_date"].strftime("%d %b %Y"),
        "commission_breakdown": comm_breakdown,
        "rebate_breakdown": reb_breakdown,
        "packages": result.applicable_packages or [],
    }


def save_sale_to_json(agent_id: str, sale_entry: Dict):
    """Append a new sale to the target agent inside management_mock_data.json."""
    with open(DEMO_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    for agent in data["agents"]:
        if agent["agent_id"] == agent_id:
            agent["sales"].append(sale_entry)
            break

    with open(DEMO_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def fmt(amount: float) -> str:
    """Format to RM short form."""
    if abs(amount) >= 1_000_000:
        return f"RM {amount / 1_000_000:,.2f}M"
    if abs(amount) >= 1_000:
        return f"RM {amount / 1_000:,.0f}K"
    return f"RM {amount:,.0f}"


def fmt_full(amount: float) -> str:
    """Full RM format."""
    return f"RM {amount:,.2f}"


def export_csv(agents: List[Agent]) -> str:
    """Build a CSV string from agents data."""
    rows = []
    for a in agents:
        for s in a.sales:
            row = {
                "Agent": a.name,
                "Team": a.team,
                "Project": s.project,
                "Unit": s.unit_id,
                "Block": s.block,
                "Floor": s.floor,
                "Unit Type": s.unit_type,
                "Buyer": s.buyer_name,
                "Buyer Type": s.buyer_type,
                "Bumi": "Yes" if s.buyer_is_bumi else "No",
                "Sale Price": s.sale_price,
                "Commission Rate (%)": s.commission_rate,
                "Commission Amount": s.commission_amount,
                "Rebate Rate (%)": s.rebate_rate,
                "Rebate Amount": s.rebate_amount,
                "Net Price": s.net_price,
                "SPA Date": s.spa_date,
                "Status": a.status,
            }
            # Add commission breakdown columns
            for i, item in enumerate(s.commission_breakdown, 1):
                row[f"Comm Rule {i} ID"] = item.get("rule_id", "")
                row[f"Comm Rule {i} Name"] = item.get("label", "")
                row[f"Comm Rule {i} Rate"] = item.get("rate", 0)
                row[f"Comm Rule {i} Amount"] = item.get("amount", 0)
                row[f"Comm Rule {i} Memo"] = item.get("memo_reference", "")
            # Add rebate breakdown columns
            for i, item in enumerate(s.rebate_breakdown, 1):
                row[f"Rebate Rule {i} ID"] = item.get("rule_id", "")
                row[f"Rebate Rule {i} Name"] = item.get("label", "")
                row[f"Rebate Rule {i} Rate"] = item.get("rate", 0)
                row[f"Rebate Rule {i} Amount"] = item.get("amount", 0)
                row[f"Rebate Rule {i} Memo"] = item.get("memo_reference", "")
            rows.append(row)
    df = pd.DataFrame(rows)
    return df.to_csv(index=False)


# ---------------------------------------------------------------------------
# CSS (matches the dark sidebar / clean card aesthetic from the design)
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
<style>
/* ---- Google Fonts: Inter + DM Sans ---- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=DM+Sans:wght@400;500;600;700&display=swap');

/* ---- Entrance Animations ---- */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}
@keyframes slideInLeft {
    from { opacity: 0; transform: translateX(-12px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes scaleIn {
    from { opacity: 0; transform: scale(0.95); }
    to   { opacity: 1; transform: scale(1); }
}
@keyframes shimmer {
    0%   { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
@keyframes pulseGlow {
    0%, 100% { box-shadow: 0 0 0 0 rgba(79, 70, 229, 0.15); }
    50%      { box-shadow: 0 0 0 8px rgba(79, 70, 229, 0); }
}

/* ---- Design System Variables ---- */
:root {
    --primary: #4F46E5;
    --primary-light: #EEF2FF;
    --primary-dark: #3730A3;
    --surface: #FFFFFF;
    --background: #F8FAFC;
    --text-primary: #0F172A;
    --text-secondary: #64748B;
    --text-muted: #94A3B8;
    --border: #E2E8F0;
    --border-light: #F1F5F9;
    --success: #10B981;
    --success-light: #D1FAE5;
    --warning: #F59E0B;
    --warning-light: #FEF3C7;
    --error: #EF4444;
    --error-light: #FEE2E2;
    --teal: #0D9488;
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.03);
    --shadow-md: 0 4px 6px rgba(0,0,0,0.04), 0 2px 4px rgba(0,0,0,0.03);
    --shadow-lg: 0 10px 25px rgba(0,0,0,0.06), 0 4px 10px rgba(0,0,0,0.04);
    --shadow-hover: 0 12px 32px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04);
    --transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

/* ---- Global: force light-mode text on light background ---- */
[data-testid="stAppViewContainer"] {
    background: var(--background);
    background-image:
        radial-gradient(ellipse 80% 50% at 50% -20%, rgba(79, 70, 229, 0.04), transparent),
        radial-gradient(ellipse 60% 40% at 80% 50%, rgba(13, 148, 136, 0.02), transparent);
    color: #1e293b;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
[data-testid="stAppViewContainer"] * {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
/* Animate main content entrance */
[data-testid="stAppViewContainer"] [data-testid="stMain"] > .block-container {
    animation: fadeInUp 0.45s cubic-bezier(0.22, 1, 0.36, 1) both;
}
h1, h2, h3, h4, h5, h6 { color: #0f172a !important; letter-spacing: -0.025em; }

/* ---- Force dark text for ALL Streamlit native elements ---- */
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] span,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] td,
[data-testid="stAppViewContainer"] th,
[data-testid="stAppViewContainer"] div {
    color: #1e293b;
}

/* Markdown rendered text */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] strong,
[data-testid="stMarkdownContainer"] em,
[data-testid="stMarkdownContainer"] code {
    color: #1e293b !important;
}
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4 {
    color: #0f172a !important;
}

/* Streamlit metric values & labels */
[data-testid="stMetric"] {
    background: transparent;
}
[data-testid="stMetricValue"] > div {
    color: #0f172a !important;
}
[data-testid="stMetricLabel"] > div,
[data-testid="stMetricLabel"] > div > div,
[data-testid="stMetricLabel"] p {
    color: #475569 !important;
}
[data-testid="stMetricDelta"] > div {
    color: #dc2626 !important;
}

/* Tab labels */
button[data-baseweb="tab"] {
    color: #475569 !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #4F46E5 !important;
}

/* Widget labels (selectbox, text input, date, number, slider, checkbox) */
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label {
    color: #1e293b !important;
}

/* Selectbox displayed value */
div[data-baseweb="select"] > div {
    color: #1e293b !important;
}
div[data-baseweb="select"] span {
    color: #1e293b !important;
}

/* Text input value */
input[data-testid="stTextInput"],
[data-testid="stTextInput"] input {
    color: #1e293b !important;
}

/* Number input */
[data-testid="stNumberInput"] input {
    color: #1e293b !important;
}

/* Date input */
[data-testid="stDateInput"] input {
    color: #1e293b !important;
}

/* Checkbox label */
[data-testid="stCheckbox"] label span {
    color: #1e293b !important;
}

/* Slider labels */
[data-testid="stSlider"] div[data-testid="stTickBarMin"],
[data-testid="stSlider"] div[data-testid="stTickBarMax"] {
    color: #64748b !important;
}

/* Sidebar text (also force dark) */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #1e293b !important;
}

/* Info / Warning / Success / Error boxes */
[data-testid="stAlert"] p {
    color: inherit !important;
}

/* DataFrame / Table */
[data-testid="stDataFrame"],
[data-testid="stDataFrame"] * {
    color: #1e293b !important;
}

/* st.columns dividers */
[data-testid="stHorizontalBlock"] {
    color: #1e293b;
}

/* Ensure bold text is also dark */
strong, b {
    color: #0f172a !important;
}

/* ---- Top filter bar ---- */
.filter-bar {
    background: linear-gradient(135deg, #0c1222 0%, #131d35 60%, #1a2240 100%);
    padding: 1.35rem 2rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: end;
    gap: 1.5rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 4px 16px rgba(15,23,42,0.2);
}
.filter-bar::before {
    content: '';
    position: absolute; inset: 0;
    background:
        radial-gradient(ellipse 60% 100% at 10% 0%, rgba(79,70,229,0.1), transparent 50%),
        radial-gradient(circle at 90% 100%, rgba(13,148,136,0.06), transparent 40%);
    pointer-events: none;
}
.filter-label {
    color: #94a3b8;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 0.25rem;
}

/* ---- Metric cards (top row) ---- */
.metric-card {
    background: white;
    border-radius: 18px;
    padding: 1.5rem 2rem;
    display: flex;
    align-items: center;
    gap: 1.25rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05), 0 4px 12px rgba(0,0,0,0.02);
    transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
    border: 1px solid rgba(226, 232, 240, 0.8);
    position: relative;
    overflow: hidden;
    animation: fadeInUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
    backdrop-filter: blur(8px);
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px; height: 100%;
    border-radius: 18px 0 0 18px;
}
.metric-card::after {
    content: '';
    position: absolute;
    top: -50%; right: -50%;
    width: 100%; height: 100%;
    background: radial-gradient(circle, rgba(79,70,229,0.03) 0%, transparent 70%);
    pointer-events: none;
}
.metric-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 32px rgba(0,0,0,0.1), 0 4px 12px rgba(79,70,229,0.06);
    border-color: rgba(79, 70, 229, 0.15);
}
.metric-icon {
    width: 52px; height: 52px;
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem;
    flex-shrink: 0;
    transition: transform 0.3s ease;
}
.metric-card:hover .metric-icon {
    transform: scale(1.08);
}
.metric-label { color: #64748b; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; }
.metric-value { font-size: 1.6rem; font-weight: 800; color: #0f172a; line-height: 1.2; letter-spacing: -0.02em; }

.metric-card-highlight {
    background: linear-gradient(135deg, #0D9488 0%, #0f766e 50%, #14B8A6 100%);
    background-size: 200% 200%;
    border-radius: 18px;
    padding: 1.5rem 2rem;
    display: flex;
    align-items: center;
    gap: 1.25rem;
    box-shadow: 0 4px 20px rgba(13,148,136,0.3), 0 8px 32px rgba(13,148,136,0.15);
    transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
    border: none;
    position: relative;
    overflow: hidden;
    animation: fadeInUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) 0.1s both;
}
.metric-card-highlight::after {
    content: '';
    position: absolute;
    top: -50%; right: -20%;
    width: 80%; height: 180%;
    background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 60%);
    pointer-events: none;
}
.metric-card-highlight:hover {
    transform: translateY(-4px) scale(1.01);
    box-shadow: 0 12px 40px rgba(13,148,136,0.4), 0 4px 12px rgba(13,148,136,0.2);
}
.metric-card-highlight .metric-label { color: rgba(255,255,255,0.9); font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.metric-card-highlight .metric-value { color: white; font-weight: 800; letter-spacing: -0.02em; }

/* ---- Agent row card ---- */
.agent-row {
    background: white;
    border-radius: 16px;
    padding: 1.15rem 1.75rem;
    margin: 0.5rem 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
    border: 1px solid rgba(226, 232, 240, 0.8);
    position: relative;
    overflow: hidden;
    animation: fadeInUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.agent-row::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px; height: 100%;
    background: linear-gradient(180deg, #e2e8f0, #cbd5e1);
    transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
}
.agent-row:hover {
    box-shadow: 0 8px 28px rgba(0,0,0,0.09), 0 2px 8px rgba(79,70,229,0.04);
    transform: translateY(-2px);
    border-color: rgba(79, 70, 229, 0.12);
}
.agent-row:hover::before {
    background: linear-gradient(180deg, #4F46E5, #6366F1);
    width: 5px;
}
.agent-avatar {
    width: 44px; height: 44px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    color: white; font-weight: 700; font-size: 0.85rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    flex-shrink: 0;
}
.agent-info { margin-left: 1rem; }
.agent-name { font-weight: 600; color: #0f172a; font-size: 1rem; }
.agent-project { color: #64748b; font-size: 0.82rem; margin-top: 0.1rem; }
.agent-metrics { display: flex; gap: 2rem; align-items: center; }
.agent-metric-block {
    text-align: center;
    padding: 0.35rem 0.75rem;
    border-radius: 8px;
    transition: background 0.2s ease;
}
.agent-metric-block:hover { background: #f8fafc; }
.agent-metric-label { font-size: 0.68rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.4px; font-weight: 600; }
.agent-metric-value { font-size: 0.95rem; font-weight: 600; color: #0f172a; }
.agent-metric-value.highlight { color: #0D9488; font-weight: 700; font-size: 1.05rem; }
/* Agent rank badge */
.agent-rank {
    width: 26px; height: 26px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.72rem;
    margin-right: 0.5rem;
    flex-shrink: 0;
}
.agent-rank-1 { background: #fef3c7; color: #d97706; }
.agent-rank-2 { background: #e2e8f0; color: #475569; }
.agent-rank-3 { background: #fed7aa; color: #c2410c; }
.agent-rank-default { background: #f1f5f9; color: #94a3b8; }
/* Agent commission mini bar */
.agent-comm-bar {
    width: 100%; height: 3px;
    background: #f1f5f9;
    border-radius: 2px;
    margin-top: 0.35rem;
    overflow: hidden;
}
.agent-comm-fill {
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(90deg, #4F46E5, #0D9488);
    transition: width 0.4s ease;
}

.badge-pending {
    background: #fef3c7; color: #d97706;
    padding: 0.25rem 0.85rem; border-radius: 20px; font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.3px;
    display: inline-flex; align-items: center; gap: 0.3rem;
}
.badge-paid {
    background: #d1fae5; color: #059669;
    padding: 0.25rem 0.85rem; border-radius: 20px; font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.3px;
    display: inline-flex; align-items: center; gap: 0.3rem;
}
.badge-partial {
    background: #e0e7ff; color: #4338ca;
    padding: 0.25rem 0.85rem; border-radius: 20px; font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.3px;
    display: inline-flex; align-items: center; gap: 0.3rem;
}

/* ---- Breakdown detail panel ---- */
.breakdown-panel {
    background: white;
    border-radius: 12px;
    padding: 1.5rem 2rem;
    margin: 0.5rem 0 1rem 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.breakdown-row {
    display: flex;
    justify-content: space-between;
    padding: 0.65rem 0.75rem;
    border-bottom: 1px solid #f1f5f9;
    align-items: center;
    border-radius: 6px;
    margin: 0.15rem 0;
    transition: background 0.15s ease;
}
.breakdown-row:last-child { border-bottom: none; }
.breakdown-row:hover { background: #f8fafc; }
.breakdown-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 0.75rem;
    flex-shrink: 0;
    box-shadow: 0 0 0 3px rgba(0,0,0,0.05);
}
.breakdown-label { color: #334155; font-size: 0.9rem; font-weight: 500; }
.breakdown-badge {
    background: #f1f5f9; color: #64748b;
    padding: 0.15rem 0.55rem; border-radius: 6px; font-size: 0.72rem;
    margin-left: 0.5rem;
    font-weight: 500;
}
.breakdown-badge-rule {
    background: #EEF2FF; color: #4338CA;
    padding: 0.18rem 0.55rem; border-radius: 6px; font-size: 0.68rem;
    font-weight: 600;
    margin-left: 0.4rem;
    letter-spacing: 0.2px;
}
.breakdown-badge-memo {
    background: #fef3c7; color: #b45309;
    padding: 0.18rem 0.55rem; border-radius: 6px; font-size: 0.68rem;
    margin-left: 0.4rem;
    font-weight: 600;
}
.breakdown-amount { font-weight: 700; color: #0f172a; font-size: 0.95rem; font-variant-numeric: tabular-nums; }

.breakdown-total-row {
    display: flex; justify-content: space-between;
    padding: 0.75rem 1rem; border-radius: 8px;
    margin-top: 0.5rem; font-weight: 600;
}
.breakdown-deduction {
    background: #f8fafc; color: #475569;
}
.breakdown-net {
    background: linear-gradient(90deg, #ecfdf5 0%, #d1fae5 100%);
    color: #059669;
}
.breakdown-net .breakdown-amount { color: #059669; font-size: 1.1rem; }

/* ---- Rebate section styling ---- */
.rebate-section-header {
    font-size: 0.8rem;
    font-weight: 700;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 0.75rem 0.75rem 0.4rem 0.75rem;
    border-top: 2px solid #e2e8f0;
    margin-top: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}

/* ---- Section headers ---- */
.section-header {
    display: flex; justify-content: space-between; align-items: center;
    margin: 1.5rem 0 0.75rem 0;
}
.section-title { font-size: 1.15rem; font-weight: 700; color: #0f172a; letter-spacing: -0.2px; }
.section-subtitle { font-size: 0.82rem; color: #94a3b8; margin-top: 0.15rem; }
/* Count badge */
.section-count-badge {
    background: #EEF2FF; color: #4F46E5;
    padding: 0.2rem 0.65rem; border-radius: 20px;
    font-size: 0.72rem; font-weight: 600;
    margin-left: 0.5rem;
}

/* ---- Unit sale detail table ---- */
.unit-table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
.unit-table th {
    text-align: left; font-size: 0.72rem; color: #94a3b8;
    text-transform: uppercase; padding: 0.5rem 0.75rem; border-bottom: 2px solid #e2e8f0;
}
.unit-table td {
    padding: 0.6rem 0.75rem; font-size: 0.88rem; color: #334155;
    border-bottom: 1px solid #f1f5f9;
}
.unit-table tr:hover td { background: #f8fafc; }

/* ---- Scheme / memo info bar ---- */
.scheme-info {
    background: linear-gradient(135deg, #EEF2FF 0%, #f0f4ff 100%);
    border: 1px solid #C7D2FE;
    border-radius: 10px;
    padding: 0.75rem 1.25rem;
    font-size: 0.85rem;
    color: #3730A3;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.6rem;
}
.memo-tag {
    display: inline-block;
    background: #fef3c7;
    color: #b45309;
    padding: 0.2rem 0.7rem;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.2px;
}

/* ---- Team cards equal-height grid ---- */
.team-cards-grid {
    display: flex;
    gap: 1rem;
    align-items: stretch;
    margin-bottom: 1.5rem;
}
.team-cards-grid > .team-card-col {
    flex: 1;
    display: flex;
    min-width: 0;
}
/* ---- Team summary card (enhanced) ---- */
.team-card {
    background: white;
    border-radius: 18px;
    overflow: hidden;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    display: flex;
    flex-direction: column;
    width: 100%;
    border: 1px solid #f1f5f9;
    animation: fadeInUp 0.45s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.team-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 32px rgba(79,70,229,0.08), 0 4px 12px rgba(0,0,0,0.04);
    border-color: #E0E7FF;
}
.team-card-header {
    padding: 1.25rem 1.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.team-card-header-left {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}
.team-card-icon {
    width: 44px; height: 44px;
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem;
    background: rgba(255,255,255,0.25);
}
.team-name {
    font-weight: 700;
    font-size: 1.05rem;
}
.team-member-count {
    font-size: 0.78rem;
    opacity: 0.85;
}
.team-card-net {
    text-align: right;
}
.team-card-net-label {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    opacity: 0.8;
}
.team-card-net-value {
    font-size: 1.45rem;
    font-weight: 800;
    line-height: 1.2;
}
.team-card-body {
    padding: 1rem 1.5rem 1.25rem;
    flex: 1;
    display: flex;
    flex-direction: column;
}
.team-card-body .team-member-list {
    flex: 1;
}
.team-kpi-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.75rem;
    margin-bottom: 1rem;
}
.team-kpi-item {
    background: #f8fafc;
    border-radius: 8px;
    padding: 0.6rem 0.75rem;
    text-align: center;
}
.team-kpi-label {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    color: #94a3b8;
    margin-bottom: 0.15rem;
}
.team-kpi-value {
    font-size: 1rem;
    font-weight: 700;
    color: #0f172a;
}
.team-kpi-value.tkv-blue { color: #4F46E5; }
.team-kpi-value.tkv-red { color: #dc2626; }
.team-kpi-value.tkv-teal { color: #0D9488; }
/* Team progress bar */
.team-progress-section {
    margin-bottom: 1rem;
}
.team-progress-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.35rem;
}
.team-progress-label {
    font-size: 0.72rem;
    color: #64748b;
    font-weight: 500;
}
.team-progress-pct {
    font-size: 0.82rem;
    font-weight: 700;
    color: #0f172a;
}
.team-progress-bar {
    width: 100%;
    height: 8px;
    background: #e2e8f0;
    border-radius: 4px;
    overflow: hidden;
}
.team-progress-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.4s ease;
}
/* Team member list */
.team-member-list {
    border-top: 1px solid #f1f5f9;
    padding-top: 0.75rem;
}
.team-member-list-title {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #94a3b8;
    margin-bottom: 0.5rem;
}
.team-member-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.4rem 0;
    border-bottom: 1px solid #f8fafc;
}
.team-member-row:last-child { border-bottom: none; }
.team-member-left {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.team-member-avatar {
    width: 28px; height: 28px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.6rem; font-weight: 700;
}
.team-member-name {
    font-size: 0.85rem;
    font-weight: 500;
    color: #334155;
}
.team-member-leader-tag {
    font-size: 0.6rem;
    background: #fef3c7;
    color: #d97706;
    padding: 0.1rem 0.35rem;
    border-radius: 4px;
    font-weight: 600;
}
.team-member-right {
    display: flex;
    gap: 1rem;
    align-items: center;
}
.team-member-stat {
    text-align: right;
}
.team-member-stat-label {
    font-size: 0.6rem;
    color: #94a3b8;
    text-transform: uppercase;
}
.team-member-stat-value {
    font-size: 0.82rem;
    font-weight: 600;
    color: #334155;
}
/* Overview KPI row */
.team-overview-kpi-row {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 1rem;
    margin-bottom: 1.5rem;
}
.team-overview-kpi {
    background: white;
    border-radius: 12px;
    padding: 1.25rem 1rem;
    text-align: center;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.team-overview-kpi-label {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #94a3b8;
    margin-bottom: 0.3rem;
}
.team-overview-kpi-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #0f172a;
}
.team-overview-kpi-value.tok-blue { color: #4F46E5; }
.team-overview-kpi-value.tok-teal { color: #0D9488; }
.team-overview-kpi-value.tok-red { color: #dc2626; }
/* Leaderboard */
.team-leaderboard {
    background: white;
    border-radius: 14px;
    padding: 1.5rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    margin-top: 1.5rem;
}
.team-leaderboard-title {
    font-weight: 700;
    color: #0f172a;
    font-size: 1rem;
    margin-bottom: 1rem;
    padding-bottom: 0.6rem;
    border-bottom: 2px solid #f1f5f9;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.team-lb-row {
    display: grid;
    grid-template-columns: 40px 1.5fr repeat(4, 1fr);
    align-items: center;
    padding: 0.75rem 0.5rem;
    border-bottom: 1px solid #f1f5f9;
}
.team-lb-row:last-child { border-bottom: none; }
.team-lb-row:hover { background: #f8fafc; border-radius: 8px; }
.team-lb-rank {
    width: 30px; height: 30px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.85rem;
}
.team-lb-rank-1 { background: #fef3c7; color: #d97706; }
.team-lb-rank-2 { background: #e2e8f0; color: #475569; }
.team-lb-rank-3 { background: #fed7aa; color: #c2410c; }
.team-lb-name {
    font-weight: 600;
    color: #0f172a;
    font-size: 0.95rem;
}
.team-lb-value {
    font-weight: 600;
    color: #334155;
    font-size: 0.9rem;
    text-align: right;
}
.team-lb-header {
    display: grid;
    grid-template-columns: 40px 1.5fr repeat(4, 1fr);
    padding: 0 0.5rem 0.5rem;
    border-bottom: 2px solid #e2e8f0;
    margin-bottom: 0.25rem;
}
.team-lb-header-cell {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #94a3b8;
    text-align: right;
}
.team-lb-header-cell:first-child,
.team-lb-header-cell:nth-child(2) { text-align: left; }
.team-stat-label { font-size: 0.72rem; color: #94a3b8; text-transform: uppercase; margin-top: 0.5rem; }
.team-stat-value { font-size: 1.2rem; font-weight: 700; color: #0f172a; }

/* ---- Chart area ---- */
.chart-placeholder {
    background: white; border-radius: 12px; padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

/* ---- Analytics panels ---- */
.analytics-panel {
    background: white;
    border-radius: 18px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    overflow: hidden;
    margin-bottom: 1.5rem;
    border: 1px solid #e2e8f0;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    animation: fadeInUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.analytics-panel:hover {
    box-shadow: 0 8px 28px rgba(79,70,229,0.07), 0 4px 12px rgba(0,0,0,0.03);
    border-color: #E0E7FF;
}
.analytics-panel-header {
    padding: 1.15rem 1.5rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    border-bottom: 1px solid #f1f5f9;
    background: linear-gradient(180deg, #FAFBFF, white);
}
.analytics-panel-icon {
    width: 40px; height: 40px;
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.05rem;
    flex-shrink: 0;
}
.analytics-panel-title {
    font-size: 1rem;
    font-weight: 700;
    color: #0f172a;
}
.analytics-panel-subtitle {
    font-size: 0.72rem;
    color: #94a3b8;
    font-weight: 500;
}
.analytics-panel-body {
    padding: 1.25rem 1.5rem;
}
/* Commission bar rows */
.comm-bar-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.6rem 0;
    border-bottom: 1px solid #f8fafc;
}
.comm-bar-row:last-child { border-bottom: none; }
.comm-bar-avatar {
    width: 32px; height: 32px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.6rem; font-weight: 700; color: white;
    flex-shrink: 0;
}
.comm-bar-info {
    flex: 1;
    min-width: 0;
}
.comm-bar-name {
    font-size: 0.85rem;
    font-weight: 600;
    color: #0f172a;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.comm-bar-track {
    height: 8px;
    background: #f1f5f9;
    border-radius: 4px;
    margin-top: 0.3rem;
    overflow: hidden;
    position: relative;
}
.comm-bar-fill-comm {
    height: 100%;
    border-radius: 4px;
    background: #4F46E5;
    position: absolute;
    top: 0; left: 0;
    transition: width 0.5s cubic-bezier(.4,0,.2,1);
}
.comm-bar-fill-net {
    height: 100%;
    border-radius: 4px;
    background: #0D9488;
    position: absolute;
    top: 0; left: 0;
    transition: width 0.5s cubic-bezier(.4,0,.2,1);
    opacity: 0.5;
}
.comm-bar-values {
    display: flex;
    gap: 1rem;
    flex-shrink: 0;
    text-align: right;
}
.comm-bar-val {
    font-size: 0.82rem;
    font-weight: 600;
    min-width: 90px;
    text-align: right;
}
.comm-bar-val.cv-blue { color: #4F46E5; }
.comm-bar-val.cv-teal { color: #0D9488; }
/* Top performer podium */
.top-perf-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.65rem 0.75rem;
    border-radius: 10px;
    transition: background 0.15s ease;
}
.top-perf-row:hover { background: #f8fafc; }
.top-perf-rank {
    width: 30px; height: 30px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.95rem;
    flex-shrink: 0;
}
.top-perf-rank-1 { background: linear-gradient(135deg,#fef3c7,#fde68a); color: #b45309; }
.top-perf-rank-2 { background: linear-gradient(135deg,#e2e8f0,#cbd5e1); color: #475569; }
.top-perf-rank-3 { background: linear-gradient(135deg,#fed7aa,#fdba74); color: #c2410c; }
.top-perf-rank-default { background: #f1f5f9; color: #64748b; }
.top-perf-name {
    flex: 1;
    font-size: 0.88rem;
    font-weight: 600;
    color: #0f172a;
}
.top-perf-amount {
    font-size: 0.88rem;
    font-weight: 700;
    color: #0D9488;
}
.top-perf-pct {
    font-size: 0.72rem;
    color: #94a3b8;
    font-weight: 500;
    min-width: 48px;
    text-align: right;
}
/* Payment status cards */
.pay-status-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
    margin-bottom: 0.75rem;
}
.pay-status-card {
    border-radius: 12px;
    padding: 1rem;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.pay-status-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
}
.pay-status-card.psc-paid { background: #f0fdf4; }
.pay-status-card.psc-paid::before { background: #22c55e; }
.pay-status-card.psc-partial { background: #fffbeb; }
.pay-status-card.psc-partial::before { background: #f59e0b; }
.pay-status-card.psc-pending { background: #fef2f2; }
.pay-status-card.psc-pending::before { background: #ef4444; }
.pay-status-count {
    font-size: 1.8rem;
    font-weight: 800;
    line-height: 1.2;
}
.pay-status-count.psc-paid { color: #16a34a; }
.pay-status-count.psc-partial { color: #d97706; }
.pay-status-count.psc-pending { color: #dc2626; }
.pay-status-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #64748b;
    margin-top: 0.2rem;
}
.pay-outstanding {
    background: #f8fafc;
    border-radius: 10px;
    padding: 0.75rem 1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.pay-outstanding-label {
    font-size: 0.78rem;
    color: #64748b;
    font-weight: 500;
}
.pay-outstanding-value {
    font-size: 1rem;
    font-weight: 700;
    color: #dc2626;
}
/* Rule utilisation table */
.rule-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
}
.rule-table thead th {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #94a3b8;
    padding: 0.6rem 0.75rem;
    border-bottom: 2px solid #e2e8f0;
    text-align: left;
}
.rule-table thead th:nth-child(n+4) { text-align: right; }
.rule-table tbody tr {
    transition: background 0.15s ease;
}
.rule-table tbody tr:hover { background: #f8fafc; }
.rule-table tbody td {
    padding: 0.65rem 0.75rem;
    border-bottom: 1px solid #f1f5f9;
    font-size: 0.85rem;
    color: #334155;
}
.rule-table tbody td:nth-child(n+4) { text-align: right; font-weight: 600; }
.rule-type-badge {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 6px;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.3px;
}
.rule-type-badge.rtb-commission { background: #EEF2FF; color: #4338CA; }
.rule-type-badge.rtb-rebate { background: #fef2f2; color: #dc2626; }
.rule-bar-cell {
    width: 100px;
}
.rule-bar-track {
    height: 6px;
    background: #f1f5f9;
    border-radius: 3px;
    overflow: hidden;
}
.rule-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.4s ease;
}
.rule-bar-fill.rbf-commission { background: #4F46E5; }
.rule-bar-fill.rbf-rebate { background: #dc2626; }

/* ---- Per-unit breakdown cards ---- */
.unit-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    transition: all 0.25s ease;
    position: relative;
    overflow: hidden;
}
.unit-card:hover {
    box-shadow: 0 6px 20px rgba(0,0,0,0.07);
    transform: translateY(-1px);
    border-color: #cbd5e1;
}
.unit-card-number {
    position: absolute;
    top: 0; left: 0;
    width: 32px; height: 32px;
    background: linear-gradient(135deg, #4F46E5, #818CF8);
    display: flex; align-items: center; justify-content: center;
    color: white; font-weight: 700; font-size: 0.75rem;
    border-radius: 14px 0 10px 0;
}
.unit-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 0.75rem;
    border-bottom: 2px solid #f1f5f9;
    margin-bottom: 0.6rem;
}
.unit-card-title {
    font-weight: 700;
    color: #0f172a;
    font-size: 1rem;
}
.unit-card-badge {
    display: inline-block;
    padding: 0.15rem 0.6rem;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 600;
    margin-left: 0.5rem;
}
.unit-card-commission {
    text-align: right;
}
.unit-card-commission-label {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #64748b;
}
.unit-card-commission-value {
    font-weight: 700;
    color: #4F46E5;
    font-size: 1.25rem;
    line-height: 1.2;
}
.unit-card-meta {
    display: flex;
    gap: 1.5rem;
    font-size: 0.82rem;
    color: #64748b;
    padding: 0.4rem 0;
}
.unit-card-meta span {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
}
.unit-subtotal {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.75rem;
    background: linear-gradient(135deg, #f8fafc, #f1f5f9);
    border-radius: 10px;
    padding: 0.85rem 1rem;
    margin-top: 0.6rem;
    border: 1px solid #e2e8f0;
}
.unit-subtotal-item {
    text-align: center;
    padding: 0.25rem 0;
}
.unit-subtotal-label {
    font-size: 0.62rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #94a3b8;
    margin-bottom: 0.2rem;
}
.unit-subtotal-value {
    font-size: 0.95rem;
    font-weight: 700;
    color: #334155;
    font-variant-numeric: tabular-nums;
}
/* ---- Agent summary dashboard card ---- */
.agent-summary-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.5rem 2rem;
    margin-bottom: 1.25rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    position: relative;
    overflow: hidden;
}
.agent-summary-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #4F46E5, #0D9488, #7c3aed);
}
.agent-summary-title {
    font-weight: 700;
    color: #0f172a;
    font-size: 1.05rem;
    margin-bottom: 1rem;
    padding-bottom: 0.6rem;
    border-bottom: 2px solid #f1f5f9;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.agent-summary-metrics {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 1rem;
}
.agent-summary-metric {
    text-align: center;
    padding: 0.85rem 0.5rem;
    border-radius: 10px;
    transition: transform 0.2s ease;
}
.agent-summary-metric:hover {
    transform: scale(1.03);
}
.agent-summary-metric-label {
    font-size: 0.62rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.35rem;
    color: #64748b;
}
.agent-summary-metric-value {
    font-size: 1.55rem;
    font-weight: 700;
    line-height: 1.2;
    font-variant-numeric: tabular-nums;
}
.asm-sales { background: #f8fafc; }
.asm-sales .agent-summary-metric-value { color: #0f172a; }
.asm-commission { background: #EEF2FF; }
.asm-commission .agent-summary-metric-value { color: #4F46E5; }
.asm-rebate { background: #fef2f2; }
.asm-rebate .agent-summary-metric-value { color: #dc2626; }
.asm-paid { background: #f8fafc; }
.asm-paid .agent-summary-metric-value { color: #64748b; }
.asm-net { background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); }
.asm-net .agent-summary-metric-value { color: #059669; font-size: 1.75rem; }
.asm-net .agent-summary-metric-label { color: #059669; }

/* ---- Expander styling ---- */
[data-testid="stExpander"] {
    background: white !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
    margin-bottom: 0.75rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    overflow: hidden;
}
[data-testid="stExpander"] details {
    background: white !important;
    border: none !important;
}
[data-testid="stExpander"] summary {
    background: #f8fafc !important;
    border-radius: 10px !important;
    padding: 0.6rem 1rem !important;
    color: #475569 !important;
    list-style: none !important;
}
[data-testid="stExpander"] summary::marker,
[data-testid="stExpander"] summary::-webkit-details-marker {
    display: none !important;
}
/* Hide the arrow/toggle icon container completely */
[data-testid="stExpander"] summary svg {
    display: none !important;
}
[data-testid="stExpander"] summary [data-testid="stExpanderToggleIcon"],
[data-testid="stExpander"] summary > span > div:first-child {
    display: none !important;
    width: 0 !important;
    height: 0 !important;
    overflow: hidden !important;
    font-size: 0 !important;
    line-height: 0 !important;
    visibility: hidden !important;
}
/* Extra: hide any icon/image element inside expander header */
[data-testid="stExpander"] summary img,
[data-testid="stExpander"] summary [data-testid*="Icon"],
[data-testid="stExpander"] summary [data-testid*="icon"],
[data-testid="stExpander"] summary [class*="icon"],
[data-testid="stExpander"] summary [role="img"] {
    display: none !important;
    width: 0 !important;
    height: 0 !important;
    visibility: hidden !important;
}
/* Hide Streamlit Material Symbols icon text (renders as "keyboard_arrow_down" etc.) */
[data-testid="stExpander"] summary span[data-icon],
[data-testid="stExpander"] summary .material-symbols-rounded,
[data-testid="stExpander"] summary .e1nzilvr5,
[data-testid="stExpander"] summary > span:first-child > span:first-child {
    display: none !important;
    width: 0 !important;
    overflow: hidden !important;
    font-size: 0 !important;
}
/* Nuclear: set font-size to 0 on the summary wrapper, then restore on text */
[data-testid="stExpander"] summary > span {
    font-size: 0 !important;
}
[data-testid="stExpander"] summary > span [data-testid="stMarkdownContainer"],
[data-testid="stExpander"] summary > span [data-testid="stMarkdownContainer"] p,
[data-testid="stExpander"] summary > span > span:last-child,
[data-testid="stExpander"] summary > span > span:last-child p {
    font-size: 0.88rem !important;
    visibility: visible !important;
    display: inline !important;
}
[data-testid="stExpander"] summary span,
[data-testid="stExpander"] summary p {
    color: #475569 !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
}

[data-testid="stExpander"] summary:hover {
    background: #EEF2FF !important;
}
[data-testid="stExpander"] summary:hover span,
[data-testid="stExpander"] summary:hover p {
    color: #3730A3 !important;
}

[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    background: white !important;
    padding: 0.75rem 1rem !important;
    color: #334155 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] * {
    color: #334155 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] .memo-section-header {
    color: white !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] .breakdown-amount {
    color: #0f172a !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] .breakdown-amount[style*="dc2626"] {
    color: #dc2626 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] .rebate-section-header {
    color: #475569 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] .breakdown-badge-rule {
    color: #4338CA !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] .breakdown-badge-memo {
    color: #b45309 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] .breakdown-badge {
    color: #64748b !important;
}

/* ---- Button hover: ensure dark readable text ---- */
button[data-testid="stBaseButton-secondary"]:hover,
button[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-secondary"] button:hover,
[data-testid="stBaseButton-primary"] button:hover,
.stDownloadButton button:hover,
button[kind="secondary"]:hover,
button[kind="primary"]:hover {
    color: #0f172a !important;
}
button[data-testid="stBaseButton-secondary"]:hover p,
button[data-testid="stBaseButton-primary"]:hover p,
button[data-testid="stBaseButton-secondary"]:hover span,
button[data-testid="stBaseButton-primary"]:hover span,
.stDownloadButton button:hover p,
.stDownloadButton button:hover span {
    color: #0f172a !important;
}

/* ---- Entitlement tracking ---- */
.entitlement-row {
    background: white;
    border-radius: 14px;
    padding: 1.15rem 1.75rem;
    margin: 0.6rem 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    transition: all 0.25s ease;
    border: 1px solid #f1f5f9;
    position: relative;
    overflow: hidden;
}
.entitlement-row::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px; height: 100%;
    border-radius: 14px 0 0 14px;
    background: linear-gradient(180deg, #4F46E5 0%, #0D9488 100%);
    opacity: 0;
    transition: opacity 0.25s ease;
}
.entitlement-row:hover {
    box-shadow: 0 6px 20px rgba(0,0,0,0.08);
    transform: translateY(-1px);
    border-color: #e2e8f0;
}
.entitlement-row:hover::before { opacity: 1; }
.entitlement-metrics {
    display: flex;
    gap: 1.75rem;
    align-items: center;
}
.entitlement-metric-label {
    font-size: 0.68rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    font-weight: 600;
}
.entitlement-metric-value {
    font-size: 0.95rem;
    font-weight: 600;
    color: #0f172a;
    margin-top: 0.15rem;
}
.entitlement-metric-value.ent-claimed { color: #4F46E5; }
.entitlement-metric-value.ent-balance { color: #dc2626; }

/* Progress bar */
.ent-progress-container {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.3rem;
    min-width: 120px;
}
.ent-progress-header {
    display: flex;
    justify-content: space-between;
    width: 100%;
    align-items: baseline;
}
.ent-progress-bar {
    width: 100%;
    height: 8px;
    background: #e2e8f0;
    border-radius: 6px;
    overflow: hidden;
}
.ent-progress-fill {
    height: 100%;
    border-radius: 6px;
    background: linear-gradient(90deg, #4F46E5, #0D9488);
    transition: width 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}
.ent-progress-fill.ent-progress-full {
    background: linear-gradient(90deg, #059669, #10b981);
}
.ent-progress-fill.ent-progress-zero {
    background: #e2e8f0;
}
.ent-progress-text {
    font-size: 0.78rem;
    font-weight: 700;
    color: #475569;
}

.badge-fully-paid {
    background: #d1fae5; color: #059669;
    padding: 0.25rem 0.85rem; border-radius: 20px; font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.3px;
    display: inline-flex; align-items: center; gap: 0.3rem;
    box-shadow: 0 1px 3px rgba(5,150,105,0.15);
}

/* Payment history */
.payment-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.85rem 0.75rem;
    border-bottom: 1px solid #f1f5f9;
    border-radius: 8px;
    margin: 0.1rem 0;
    transition: background 0.2s ease;
}
.payment-row:last-child { border-bottom: none; }
.payment-row:hover { background: #f8fafc; }
.payment-info {
    display: flex;
    align-items: center;
    gap: 0.85rem;
}
.payment-check {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #d1fae5;
    color: #059669;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.8rem;
    flex-shrink: 0;
    box-shadow: 0 1px 3px rgba(5,150,105,0.15);
}
.payment-date {
    font-weight: 600;
    color: #0f172a;
    font-size: 0.9rem;
}
.payment-ref {
    color: #94a3b8;
    font-size: 0.78rem;
    margin-top: 0.1rem;
}
.payment-right {
    display: flex;
    align-items: center;
    gap: 0.85rem;
}
.payment-amount {
    font-weight: 700;
    color: #0f172a;
    font-size: 0.95rem;
}
.payment-badge-paid {
    background: #d1fae5;
    color: #059669;
    padding: 0.2rem 0.6rem;
    border-radius: 8px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: capitalize;
}

/* Entitlement summary panel */
.ent-summary-panel {
    background: white;
    border-radius: 14px;
    padding: 1.5rem 1.75rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border: 1px solid #f1f5f9;
    position: relative;
    overflow: hidden;
}
.ent-summary-panel::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #0D9488 0%, #14B8A6 100%);
}
.ent-summary-panel-title {
    font-weight: 700;
    color: #0f172a;
    font-size: 0.95rem;
    padding-bottom: 0.85rem;
    border-bottom: 2px solid #f1f5f9;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.ent-summary-row {
    display: flex;
    justify-content: space-between;
    padding: 0.7rem 0.5rem;
    border-bottom: 1px solid #f1f5f9;
    border-radius: 6px;
    margin: 0.1rem 0;
    transition: background 0.2s ease;
}
.ent-summary-row:last-child { border-bottom: none; }
.ent-summary-row:hover { background: #f8fafc; }
.ent-summary-label {
    color: #64748b;
    font-size: 0.88rem;
}
.ent-summary-value {
    font-weight: 600;
    color: #0f172a;
    font-size: 0.92rem;
}
.ent-summary-value.ent-green { color: #059669; }
.ent-summary-value.ent-red { color: #dc2626; }
.ent-summary-value.ent-blue { color: #4F46E5; }
.ent-summary-total {
    border-top: 2px solid #e2e8f0 !important;
    border-bottom: none !important;
    margin-top: 0.25rem;
    padding-top: 0.85rem;
}
.ent-summary-total .ent-summary-label {
    font-weight: 700;
    color: #0f172a;
}
.ent-summary-total .ent-summary-value {
    font-size: 1rem;
    font-weight: 700;
}

.ent-payment-panel {
    background: white;
    border-radius: 14px;
    padding: 1.5rem 1.75rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border: 1px solid #f1f5f9;
    position: relative;
    overflow: hidden;
}
.ent-payment-panel::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #4F46E5 0%, #6366F1 100%);
}
.ent-payment-panel-title {
    font-weight: 700;
    color: #0f172a;
    font-size: 0.95rem;
    padding-bottom: 0.85rem;
    border-bottom: 2px solid #f1f5f9;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.ent-no-payments {
    color: #94a3b8;
    font-size: 0.88rem;
    padding: 2rem 0;
    text-align: center;
    font-style: italic;
}
.ent-payment-count {
    font-size: 0.72rem;
    color: #94a3b8;
    font-weight: 500;
    margin-left: auto;
}

/* ---- Preserve white/light text on dark/colored backgrounds ---- */
.metric-card-highlight,
.metric-card-highlight div,
.metric-card-highlight span,
.metric-card-highlight p {
    color: white !important;
}
.metric-card-highlight .metric-label {
    color: rgba(255,255,255,0.85) !important;
}
.metric-card-highlight .metric-value {
    color: white !important;
}
.agent-avatar,
.agent-avatar * {
    color: white !important;
}
.filter-bar span,
.filter-bar div,
.filter-bar label,
.filter-bar p,
.filter-label {
    color: #94a3b8 !important;
}
/* Badge text colors (override global dark) */
.badge-pending { color: #d97706 !important; }
.badge-paid { color: #059669 !important; }
.badge-partial { color: #4338ca !important; }
.badge-fully-paid { color: #059669 !important; }
.payment-badge-paid { color: #059669 !important; }
/* Breakdown badges */
.breakdown-badge { color: #64748b !important; }
.breakdown-badge-rule { color: #4338CA !important; }
.breakdown-badge-memo { color: #b45309 !important; }
/* Section subtitle */
.section-subtitle { color: #94a3b8 !important; }
/* Metric card specific label color */
.metric-label { color: #64748b !important; }
.metric-value { color: #0f172a !important; }
/* Agent row metric label */
.agent-metric-label { color: #94a3b8 !important; }
.agent-metric-value.highlight { color: #0D9488 !important; }
/* Entitlement specific */
.entitlement-metric-label { color: #94a3b8 !important; }
.entitlement-metric-value.ent-claimed { color: #4F46E5 !important; }
.entitlement-metric-value.ent-balance { color: #dc2626 !important; }
.ent-progress-text { color: #475569 !important; }
/* Summary panel value colors */
.ent-summary-value.ent-green { color: #059669 !important; }
.ent-summary-value.ent-red { color: #dc2626 !important; }
.ent-summary-value.ent-blue { color: #4F46E5 !important; }
/* Agent summary metric value colors */
.asm-commission .agent-summary-metric-value { color: #4F46E5 !important; }
.asm-rebate .agent-summary-metric-value { color: #dc2626 !important; }
.asm-paid .agent-summary-metric-value { color: #64748b !important; }
.asm-net .agent-summary-metric-value { color: #059669 !important; }
.asm-net .agent-summary-metric-label { color: #059669 !important; }
/* Team card stat colors */
.team-stat-label { color: #94a3b8 !important; }
/* Team card header text (white on colored bg) */
.team-card-header,
.team-card-header * {
    color: white !important;
}
.team-card-net-label { color: rgba(255,255,255,0.8) !important; }
.team-card-net-value { color: white !important; }
.team-name { color: white !important; }
.team-member-count { color: rgba(255,255,255,0.85) !important; }
.team-card-icon { color: white !important; }
/* Team card body preserve colors */
.team-kpi-label { color: #94a3b8 !important; }
.team-kpi-value.tkv-blue { color: #4F46E5 !important; }
.team-kpi-value.tkv-red { color: #dc2626 !important; }
.team-kpi-value.tkv-teal { color: #0D9488 !important; }
.team-progress-label { color: #64748b !important; }
.team-member-name { color: #334155 !important; }
.team-member-avatar { color: white !important; }
.team-member-leader-tag { color: #d97706 !important; }
.team-member-stat-label { color: #94a3b8 !important; }
.team-member-stat-value { color: #334155 !important; }
/* Overview KPI colors */
.team-overview-kpi-label { color: #94a3b8 !important; }
.team-overview-kpi-value.tok-blue { color: #4F46E5 !important; }
.team-overview-kpi-value.tok-teal { color: #0D9488 !important; }
.team-overview-kpi-value.tok-red { color: #dc2626 !important; }
/* Leaderboard colors */
.team-lb-header-cell { color: #94a3b8 !important; }
.team-lb-rank-1 { color: #d97706 !important; }
.team-lb-rank-2 { color: #475569 !important; }
.team-lb-rank-3 { color: #c2410c !important; }
/* Unit subtotal label */
.unit-subtotal-label { color: #94a3b8 !important; }
.unit-card-commission-label { color: #64748b !important; }
/* Scheme info */
.scheme-info { color: #3730A3 !important; }
.scheme-info span { color: #3730A3 !important; }
.memo-tag { color: #b45309 !important; }
/* Rebate breakdown amounts should be red */
.breakdown-amount[style*="dc2626"] { color: #dc2626 !important; }
/* Payment row specific */
.payment-check { color: #059669 !important; }
.payment-ref { color: #94a3b8 !important; }
.payment-date { color: #0f172a !important; }
.payment-amount { color: #0f172a !important; }
/* Expander overrides - preserve inner custom colors */
.ent-summary-label { color: #64748b !important; }
.agent-project { color: #64748b !important; }
/* Breakdown net row */
.breakdown-net .breakdown-amount { color: #059669 !important; }
/* Rebate section header */
.rebate-section-header { color: #475569 !important; }

/* ============================================================
   FLAG FORM CONTAINER  –  bordered card for rule flagging
   ============================================================ */
.flag-form-container {
    border: 1.5px solid #e0e4ef;
    border-radius: 12px;
    padding: 1.25rem 1.5rem 1rem;
    margin: 1rem 0 0.5rem;
    background: linear-gradient(135deg, #fef9f3 0%, #fff5f5 50%, #fef2f2 100%);
    box-shadow: 0 2px 8px rgba(239, 68, 68, 0.06), 0 0 0 1px rgba(239, 68, 68, 0.04);
    position: relative;
    animation: fadeInUp 0.3s ease-out;
}
.flag-form-container::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
    background: linear-gradient(90deg, #ef4444 0%, #f97316 50%, #eab308 100%);
}
.flag-form-header {
    font-size: 0.95rem;
    font-weight: 600;
    color: #b91c1c;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-family: 'DM Sans', 'Inter', sans-serif;
}
.flag-form-icon {
    font-size: 1.1rem;
}
/* 1) The header container that holds the collapse button (Streamlit 1.53+) */
[data-testid="stSidebarHeader"] {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    overflow: hidden !important;
    visibility: hidden !important;
    position: absolute !important;
}
/* 2) The collapse button itself—various test-id names across versions */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCloseButton"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
button[data-testid="baseButton-headerNoPadding"],
button[data-testid="baseButton-header"],
[data-testid="stSidebar"] button[kind="header"],
[data-testid="stSidebar"] button[kind="headerNoPadding"] {
    display: none !important;
    visibility: hidden !important;
    width: 0 !important;
    height: 0 !important;
    overflow: hidden !important;
    position: absolute !important;
    pointer-events: none !important;
}
/* 3) Wildcard catch for any future collapse-related testid */
[data-testid*="ollapse"] {
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
}
/* 4) Hide the expand-sidebar control shown when sidebar is collapsed */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {
    display: none !important;
    visibility: hidden !important;
    width: 0 !important;
    height: 0 !important;
    position: absolute !important;
}
/* 5) Force Material-Icons ligature text invisible as fallback */
[data-testid="stSidebar"] .material-symbols-rounded,
[data-testid="stSidebar"] .material-icons {
    display: none !important;
    font-size: 0 !important;
    line-height: 0 !important;
    visibility: hidden !important;
}

/* ================================================================
   DARK SIDEBAR THEME  –  glassmorphism
   ================================================================ */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0c1222 0%, #131d35 40%, #172042 100%) !important;
    border-right: 1px solid rgba(255,255,255,0.05) !important;
    box-shadow: 4px 0 24px rgba(0,0,0,0.12) !important;
}
[data-testid="stSidebar"]::before {
    content: '';
    position: absolute; inset: 0;
    background:
        radial-gradient(ellipse 120% 50% at 30% 0%, rgba(79,70,229,0.12), transparent 60%),
        radial-gradient(circle at 80% 100%, rgba(13,148,136,0.06), transparent 50%);
    pointer-events: none; z-index: 0;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    background: transparent !important;
    position: relative; z-index: 1;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] div {
    color: #CBD5E1 !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.06) !important;
    margin: 0.5rem 1rem !important;
}
/* Sidebar radio buttons → styled nav items */
[data-testid="stSidebar"] [role="radiogroup"] {
    gap: 0.3rem !important;
    padding: 0 0.25rem !important;
}
[data-testid="stSidebar"] [role="radiogroup"] label {
    background: transparent !important;
    border-radius: 12px !important;
    padding: 0.7rem 1rem !important;
    margin: 0 0.4rem !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    border: 1px solid transparent !important;
    cursor: pointer !important;
    position: relative;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    background: rgba(255,255,255,0.06) !important;
    border-color: rgba(255,255,255,0.08) !important;
    transform: translateX(2px);
}
[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"],
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: rgba(79, 70, 229, 0.18) !important;
    border-color: rgba(79, 70, 229, 0.35) !important;
    box-shadow: 0 2px 12px rgba(79,70,229,0.15), inset 0 0 0 1px rgba(165,180,252,0.1) !important;
}
/* Active indicator bar */
[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"]::before,
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked)::before {
    content: '';
    position: absolute; left: -0.4rem; top: 50%; transform: translateY(-50%);
    width: 3px; height: 60%; border-radius: 2px;
    background: linear-gradient(180deg, #818CF8, #4F46E5);
}
[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"] p,
[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"] span,
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p,
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) span {
    color: #C7D2FE !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] [role="radiogroup"] label p,
[data-testid="stSidebar"] [role="radiogroup"] label span {
    color: #94A3B8 !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.01em;
}
/* Hide radio button circles */
[data-testid="stSidebar"] [role="radiogroup"] input[type="radio"] {
    display: none !important;
}
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child {
    display: none !important;
}

/* ================================================================
   MODERNIZED BUTTONS
   ================================================================ */
button[data-testid="stBaseButton-secondary"] {
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    padding: 0.5rem 1.25rem !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    border: 1px solid #E2E8F0 !important;
    background: white !important;
    color: #334155 !important;
    position: relative;
    overflow: hidden;
}
button[data-testid="stBaseButton-secondary"]::after {
    content: '';
    position: absolute; inset: 0;
    background: linear-gradient(135deg, rgba(79,70,229,0.04), rgba(99,102,241,0.06));
    opacity: 0;
    transition: opacity 0.25s ease;
}
button[data-testid="stBaseButton-secondary"]:hover {
    background: #FAFAFE !important;
    border-color: #C7D2FE !important;
    box-shadow: 0 4px 12px rgba(79,70,229,0.08) !important;
    transform: translateY(-1px);
}
button[data-testid="stBaseButton-secondary"]:hover::after { opacity: 1; }
button[data-testid="stBaseButton-primary"] {
    border-radius: 12px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    padding: 0.55rem 1.4rem !important;
    background: linear-gradient(135deg, #4F46E5 0%, #6366F1 50%, #4F46E5 100%) !important;
    background-size: 200% 200% !important;
    border: none !important;
    color: white !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 2px 8px rgba(79, 70, 229, 0.3), 0 1px 3px rgba(79, 70, 229, 0.15) !important;
    letter-spacing: 0.01em;
}
button[data-testid="stBaseButton-primary"] p,
button[data-testid="stBaseButton-primary"] span {
    color: white !important;
}
button[data-testid="stBaseButton-primary"]:hover {
    background-position: 100% 100% !important;
    box-shadow: 0 6px 20px rgba(79, 70, 229, 0.4), 0 2px 8px rgba(79, 70, 229, 0.2) !important;
    transform: translateY(-2px);
}
button[data-testid="stBaseButton-primary"]:hover p,
button[data-testid="stBaseButton-primary"]:hover span {
    color: white !important;
}
/* Ensure primary button white text even inside expanders */
[data-testid="stExpander"] button[data-testid="stBaseButton-primary"],
[data-testid="stExpander"] button[data-testid="stBaseButton-primary"] p,
[data-testid="stExpander"] button[data-testid="stBaseButton-primary"] span {
    color: white !important;
}

/* ================================================================
   TEXT AREA BORDER
   ================================================================ */
[data-testid="stTextArea"] textarea {
    border: 1.5px solid #cbd5e1 !important;
    border-radius: 10px !important;
    background: white !important;
}
[data-testid="stTextArea"] textarea:focus {
    border-color: #4F46E5 !important;
    box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.15) !important;
}

/* ================================================================
   MODERNIZED TABS
   ================================================================ */
[data-baseweb="tab-list"] {
    background: white !important;
    border-radius: 14px !important;
    padding: 0.4rem !important;
    border: 1px solid #E2E8F0 !important;
    gap: 0.3rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}
button[data-baseweb="tab"] {
    border-radius: 10px !important;
    padding: 0.55rem 1.35rem !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    color: #64748B !important;
    border: none !important;
    letter-spacing: 0.01em;
}
button[data-baseweb="tab"]:hover {
    background: #F1F5F9 !important;
    color: #334155 !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    background: linear-gradient(135deg, #4F46E5, #6366F1) !important;
    color: white !important;
    box-shadow: 0 3px 10px rgba(79, 70, 229, 0.25) !important;
    font-weight: 600 !important;
}
button[data-baseweb="tab"][aria-selected="true"] p,
button[data-baseweb="tab"][aria-selected="true"] span {
    color: white !important;
}
/* Hide default tab highlight bar */
[data-baseweb="tab-highlight"] {
    display: none !important;
}
[data-baseweb="tab-border"] {
    display: none !important;
}

/* ================================================================
   MODERNIZED SELECTBOX & INPUTS
   ================================================================ */
div[data-baseweb="select"] > div {
    border-radius: 10px !important;
    border-color: #E2E8F0 !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}
div[data-baseweb="select"] > div:hover {
    border-color: #CBD5E1 !important;
}
div[data-baseweb="select"] > div:focus-within {
    border-color: #4F46E5 !important;
    box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1) !important;
}
input[type="text"], input[type="number"] {
    border-radius: 10px !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}
input:focus {
    border-color: #4F46E5 !important;
    box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1) !important;
}

/* ================================================================
   SCROLLBAR STYLING
   ================================================================ */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #94A3B8; }

/* ================================================================
   PAGE HEADER   –   consistent branded header for every page
   ================================================================ */
.page-header-wrap {
    background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%);
    border: 1px solid #E2E8F0;
    border-radius: 20px;
    padding: 1.6rem 2rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}
.page-header-wrap::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #4F46E5, #818CF8, #6366F1, #4F46E5);
    background-size: 300% 100%;
    animation: shimmer 4s ease infinite;
}
.page-header-wrap::after {
    content: '';
    position: absolute; top: -40%; right: -5%; width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(79,70,229,0.04), transparent 70%);
    pointer-events: none;
}
.page-header-title {
    font-size: 1.85rem;
    font-weight: 800;
    color: #0F172A;
    letter-spacing: -0.03em;
    line-height: 1.2;
    font-family: 'DM Sans', 'Inter', sans-serif;
}
.page-header-subtitle {
    font-size: 0.88rem;
    color: #64748B;
    font-weight: 400;
    margin-top: 0.3rem;
    line-height: 1.4;
}
.page-header-badge {
    display: inline-flex; align-items: center; gap: 0.35rem;
    background: #EEF2FF; color: #4F46E5;
    padding: 0.25rem 0.85rem; border-radius: 20px;
    font-size: 0.7rem; font-weight: 600;
    letter-spacing: 0.3px; margin-top: 0.5rem;
}

/* ================================================================
   EXPANDER REFINEMENTS
   ================================================================ */
[data-testid="stExpander"] {
    border: 1px solid #E2E8F0 !important;
    border-radius: 14px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.03) !important;
    overflow: hidden;
    transition: all 0.25s ease !important;
}
[data-testid="stExpander"]:hover {
    border-color: #CBD5E1 !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.05) !important;
}
[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    color: #1e293b !important;
    padding: 0.75rem 1rem !important;
}

/* ================================================================
   DIVIDER REFINEMENTS
   ================================================================ */
[data-testid="stAppViewContainer"] hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent, #E2E8F0, transparent) !important;
    margin: 1rem 0 !important;
}
</style>
"""


# ---------------------------------------------------------------------------
# RENDER FUNCTIONS
# ---------------------------------------------------------------------------

def render_filter_bar(metadata: Dict) -> Dict[str, Any]:
    """Render the top filter bar and return selected filters."""
    schemes = metadata.get("commission_schemes", [])
    periods = metadata.get("periods", [])

    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])

    with col1:
        project = st.selectbox(
            "**Project**",
            ["All Projects", metadata["project"]],
            key="f_project",
        )
    with col2:
        scheme = st.selectbox("**Memo / Scheme**", schemes, key="f_scheme")
    with col3:
        period = st.selectbox("**Period**", periods, key="f_period")
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        run_clicked = st.button("Filter", type="primary", use_container_width=True)

    return {
        "project": None if project == "All Projects" else project,
        "scheme": scheme,
        "period": period,
        "run_clicked": run_clicked,
    }


def render_summary_metrics(agents: List[Agent]):
    """Render the four summary metric cards."""
    total_sellers = len(agents)
    total_units = sum(len(a.sales) for a in agents)
    total_commission = sum(a.total_commission for a in agents)
    total_payable = sum(a.net_payable for a in agents)

    cards = [
        ("📋", "Agents Calculated", str(total_sellers), "#EEF2FF", "#4F46E5", "metric-card"),
        ("🏠", "Units Sold", str(total_units), "#faf5ff", "#7c3aed", "metric-card"),
        ("💰", "Total Commission", fmt(total_commission), "#ecfdf5", "#0D9488", "metric-card"),
        ("⬇️", "Net Payable", fmt(total_payable), "rgba(255,255,255,0.2)", "", "metric-card-highlight"),
    ]

    cols = st.columns(4)
    for col, (icon, label, value, icon_bg, accent, cls) in zip(cols, cards):
        accent_css = f'background:{accent};' if accent else ''
        html = (
            f'<div class="{cls}" style="cursor:default;">'
            f'<div style="position:absolute;top:0;left:0;width:4px;height:100%;{accent_css}border-radius:14px 0 0 14px;"></div>'
            f'<div class="metric-icon" style="background:{icon_bg};">{icon}</div>'
            '<div>'
            f'<div class="metric-label">{label}</div>'
            f'<div class="metric-value">{value}</div>'
            '</div>'
            '</div>'
        )
        with col:
            st.markdown(html, unsafe_allow_html=True)


def render_team_overview(agents: List[Agent]):
    """Render an enhanced team overview with KPIs, styled team cards, and leaderboard."""
    teams: Dict[str, List[Agent]] = {}
    for a in agents:
        teams.setdefault(a.team, []).append(a)

    # ── Section header ──
    st.markdown(
        '<div class="section-header">'
        '<div>'
        '<div class="section-title">Team Overview</div>'
        '<div class="section-subtitle">At-a-glance team performance, member contributions, and rankings</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Top-level KPIs across all teams ──
    total_teams = len(teams)
    total_agents = len(agents)
    total_units = sum(len(a.sales) for a in agents)
    grand_sales = sum(a.total_sales for a in agents)
    grand_comm = sum(a.total_commission for a in agents)
    grand_net = sum(a.net_payable for a in agents)
    grand_rebate = sum(a.total_rebate for a in agents)

    kpi_html = '<div class="team-overview-kpi-row">'
    for lbl, val, cls in [
        ("Teams", str(total_teams), ""),
        ("Total Agents", str(total_agents), ""),
        ("Units Sold", str(total_units), ""),
        ("Total Commission", fmt(grand_comm), " tok-blue"),
        ("Total Net Payable", fmt(grand_net), " tok-teal"),
    ]:
        kpi_html += (
            '<div class="team-overview-kpi">'
            f'<div class="team-overview-kpi-label">{lbl}</div>'
            f'<div class="team-overview-kpi-value{cls}">{val}</div>'
            '</div>'
        )
    kpi_html += '</div>'
    st.markdown(kpi_html, unsafe_allow_html=True)

    # ── Team color palette ──
    team_colors = [
        ("linear-gradient(135deg, #4F46E5 0%, #818CF8 100%)", "#4F46E5"),
        ("linear-gradient(135deg, #0D9488 0%, #14B8A6 100%)", "#0D9488"),
        ("linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)", "#7c3aed"),
        ("linear-gradient(135deg, #ea580c 0%, #fb923c 100%)", "#ea580c"),
        ("linear-gradient(135deg, #dc2626 0%, #f87171 100%)", "#dc2626"),
    ]

    # ── Team Cards (equal-height flex grid) ──
    cards_html = '<div class="team-cards-grid">'
    for i, (team_name, members) in enumerate(sorted(teams.items())):
        team_sales = sum(a.total_sales for a in members)
        team_comm = sum(a.total_commission for a in members)
        team_reb = sum(a.total_rebate for a in members)
        team_payable = sum(a.net_payable for a in members)
        team_units = sum(len(a.sales) for a in members)
        sales_pct = (team_sales / grand_sales * 100) if grand_sales > 0 else 0
        gradient, bar_color = team_colors[i % len(team_colors)]

        # Build member rows HTML
        member_rows = ""
        for m in sorted(members, key=lambda x: x.net_payable, reverse=True):
            leader_tag = '<span class="team-member-leader-tag">Lead</span>' if m.is_team_leader else ''
            member_rows += (
                '<div class="team-member-row">'
                '<div class="team-member-left">'
                f'<div class="team-member-avatar" style="background:{m.avatar_color};color:white;">{m.initials}</div>'
                f'<span class="team-member-name">{m.name}</span>'
                f'{leader_tag}'
                '</div>'
                '<div class="team-member-right">'
                '<div class="team-member-stat">'
                '<div class="team-member-stat-label">Units</div>'
                f'<div class="team-member-stat-value">{len(m.sales)}</div>'
                '</div>'
                '<div class="team-member-stat">'
                '<div class="team-member-stat-label">Net</div>'
                f'<div class="team-member-stat-value" style="color:#0D9488;">{fmt(m.net_payable)}</div>'
                '</div>'
                '</div>'
                '</div>'
            )

        s_suffix = "s" if len(members) != 1 else ""
        cards_html += (
            '<div class="team-card-col">'
            '<div class="team-card">'
            f'<div class="team-card-header" style="background:{gradient};">'
            '<div class="team-card-header-left">'
            '<div class="team-card-icon">👥</div>'
            '<div>'
            f'<div class="team-name">{team_name}</div>'
            f'<div class="team-member-count">{len(members)} member{s_suffix} · {team_units} units</div>'
            '</div>'
            '</div>'
            '<div class="team-card-net">'
            '<div class="team-card-net-label">Net Payable</div>'
            f'<div class="team-card-net-value">{fmt(team_payable)}</div>'
            '</div>'
            '</div>'
            '<div class="team-card-body">'
            '<div class="team-kpi-grid">'
            '<div class="team-kpi-item">'
            '<div class="team-kpi-label">Total Sales</div>'
            f'<div class="team-kpi-value">{fmt(team_sales)}</div>'
            '</div>'
            '<div class="team-kpi-item">'
            '<div class="team-kpi-label">Commission</div>'
            f'<div class="team-kpi-value tkv-blue">{fmt(team_comm)}</div>'
            '</div>'
            '<div class="team-kpi-item">'
            '<div class="team-kpi-label">Buyer Rebates</div>'
            f'<div class="team-kpi-value tkv-red">{fmt(team_reb)}</div>'
            '</div>'
            '<div class="team-kpi-item">'
            '<div class="team-kpi-label">Avg / Agent</div>'
            f'<div class="team-kpi-value tkv-teal">{fmt(team_payable / len(members) if members else 0)}</div>'
            '</div>'
            '</div>'
            '<div class="team-progress-section">'
            '<div class="team-progress-header">'
            '<span class="team-progress-label">Share of Total Sales</span>'
            f'<span class="team-progress-pct">{sales_pct:.1f}%</span>'
            '</div>'
            '<div class="team-progress-bar">'
            f'<div class="team-progress-fill" style="width:{sales_pct}%; background:{bar_color};"></div>'
            '</div>'
            '</div>'
            '<div class="team-member-list">'
            '<div class="team-member-list-title">Members</div>'
            f'{member_rows}'
            '</div>'
            '</div>'
            '</div>'
            '</div>'
        )
    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)

    # ── Team Leaderboard ──
    sorted_teams = sorted(teams.items(), key=lambda t: sum(a.net_payable for a in t[1]), reverse=True)

    lb_html = (
        '<div class="team-leaderboard">'
        '<div class="team-leaderboard-title">🏆 Team Rankings — by Net Payable</div>'
        '<div class="team-lb-header">'
        '<div class="team-lb-header-cell">#</div>'
        '<div class="team-lb-header-cell">Team</div>'
        '<div class="team-lb-header-cell">Units</div>'
        '<div class="team-lb-header-cell">Total Sales</div>'
        '<div class="team-lb-header-cell">Commission</div>'
        '<div class="team-lb-header-cell">Net Payable</div>'
        '</div>'
    )

    for rank, (tname, tmembers) in enumerate(sorted_teams, 1):
        t_sales = sum(a.total_sales for a in tmembers)
        t_comm = sum(a.total_commission for a in tmembers)
        t_net = sum(a.net_payable for a in tmembers)
        t_units = sum(len(a.sales) for a in tmembers)
        rank_class = f"team-lb-rank-{rank}" if rank <= 3 else ""
        rank_style = '' if rank <= 3 else 'background:#f1f5f9;color:#64748b;'
        lb_html += (
            '<div class="team-lb-row">'
            f'<div><div class="team-lb-rank {rank_class}" style="{rank_style}">{rank}</div></div>'
            f'<div class="team-lb-name">{tname} <span style="font-size:0.75rem;color:#94a3b8;">({len(tmembers)} agents)</span></div>'
            f'<div class="team-lb-value">{t_units}</div>'
            f'<div class="team-lb-value">{fmt(t_sales)}</div>'
            f'<div class="team-lb-value" style="color:#4F46E5;">{fmt(t_comm)}</div>'
            f'<div class="team-lb-value" style="color:#0D9488;">{fmt(t_net)}</div>'
            '</div>'
        )

    lb_html += '</div>'
    st.markdown(lb_html, unsafe_allow_html=True)


def render_agent_row(agent: Agent, rank: int = 0, max_commission: float = 1.0):
    """Render a single agent summary row with rank badge and commission bar."""
    badge_map = {
        "Paid": ("badge-paid", "✓"),
        "Pending": ("badge-pending", "⏳"),
        "Partial": ("badge-partial", "◐"),
    }
    badge_class, badge_icon = badge_map.get(agent.status, ("badge-pending", "⏳"))
    leader_tag = (' <span style="font-size:0.65rem;background:#fef3c7;color:#d97706;'
                  'padding:0.12rem 0.45rem;border-radius:4px;font-weight:600;'
                  'letter-spacing:0.2px;">★ Team Lead</span>') if agent.is_team_leader else ""

    # Commission bar percentage
    comm_pct = min((agent.total_commission / max_commission * 100) if max_commission > 0 else 0, 100)

    # Rank badge class
    rank_cls = f"agent-rank-{rank}" if rank <= 3 else "agent-rank-default"

    html = (
        '<div class="agent-row">'
        '<div style="display:flex;align-items:center;gap:0.5rem;">'
        f'<div class="agent-rank {rank_cls}">{rank}</div>'
        f'<div class="agent-avatar" style="background:{agent.avatar_color};">{agent.initials}</div>'
        '<div class="agent-info">'
        f'<div class="agent-name">{agent.name}{leader_tag}</div>'
        f'<div class="agent-project">{agent.project} · {len(agent.sales)} units</div>'
        '</div>'
        '</div>'
        '<div class="agent-metrics">'
        '<div class="agent-metric-block">'
        '<div class="agent-metric-label">Sales</div>'
        f'<div class="agent-metric-value">{fmt(agent.total_sales)}</div>'
        '</div>'
        '<div class="agent-metric-block">'
        '<div class="agent-metric-label">Commission</div>'
        f'<div class="agent-metric-value">{fmt(agent.total_commission)}</div>'
        '<div class="agent-comm-bar">'
        f'<div class="agent-comm-fill" style="width:{comm_pct:.1f}%;"></div>'
        '</div>'
        '</div>'
        '<div class="agent-metric-block">'
        '<div class="agent-metric-label">Net Payable</div>'
        f'<div class="agent-metric-value highlight">{fmt(agent.net_payable)}</div>'
        '</div>'
        f'<div><span class="{badge_class}">{badge_icon} {agent.status}</span></div>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_agent_breakdown(agent: Agent, scheme: str):
    """Render agent summary first, then per-unit breakdown cards."""

    # --- Memo info ---
    memos = set()
    for sale in agent.sales:
        for item in sale.commission_breakdown:
            if item.get("memo_reference"):
                memos.add(item["memo_reference"])
        for item in sale.rebate_breakdown:
            if item.get("memo_reference"):
                memos.add(item["memo_reference"])
    memo_tags = " ".join(f'<span class="memo-tag">{m}</span>' for m in sorted(memos))

    scheme_html = (
        '<div class="scheme-info">'
        'ℹ️ Calculation based on: '
        f'{memo_tags if memo_tags else scheme}'
        '</div>'
    )
    st.markdown(scheme_html, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════
    # AGENT SUMMARY — shown first at the top for at-a-glance view
    # ═══════════════════════════════════════════════════════════════════
    total_sales = sum(s.sale_price for s in agent.sales)
    total_comm = agent.total_commission
    total_reb = agent.total_rebate

    summary_html = (
        '<div class="agent-summary-card">'
        '<div class="agent-summary-title">'
        f'📊 Agent Summary — {agent.name} · {len(agent.sales)} unit(s)'
        '</div>'
        '<div class="agent-summary-metrics">'
        '<div class="agent-summary-metric asm-sales">'
        '<div class="agent-summary-metric-label">Total Sales</div>'
        f'<div class="agent-summary-metric-value">{fmt(total_sales)}</div>'
        '</div>'
        '<div class="agent-summary-metric asm-commission">'
        '<div class="agent-summary-metric-label">Commission</div>'
        f'<div class="agent-summary-metric-value">{fmt(total_comm)}</div>'
        '</div>'
        '<div class="agent-summary-metric asm-rebate">'
        '<div class="agent-summary-metric-label">Buyer Rebates</div>'
        f'<div class="agent-summary-metric-value">- {fmt(total_reb)}</div>'
        '</div>'
        '<div class="agent-summary-metric asm-paid">'
        '<div class="agent-summary-metric-label">Previously Paid</div>'
        f'<div class="agent-summary-metric-value">- {fmt(agent.total_previously_paid)}</div>'
        '</div>'
        '<div class="agent-summary-metric asm-net">'
        '<div class="agent-summary-metric-label">Net Payable</div>'
        f'<div class="agent-summary-metric-value">{fmt(agent.net_payable)}</div>'
        '</div>'
        '</div>'
        '</div>'
    )
    st.markdown(summary_html, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════
    # PER-UNIT CARDS — detail below summary
    # ═══════════════════════════════════════════════════════════════════
    helper_html = (
        '<div style="font-size:0.85rem;color:#64748b;margin-bottom:0.75rem;'
        'display:flex;align-items:center;gap:0.4rem;">'
        f'Showing <strong>{len(agent.sales)}</strong> unit(s) sold by '
        f'<strong>{agent.name}</strong>.'
        ' Click on a unit to view detailed commission &amp; rebate rules applied.'
        '</div>'
    )
    st.markdown(helper_html, unsafe_allow_html=True)

    dot_colors = ["#4F46E5", "#0D9488", "#f59e0b", "#7c3aed", "#dc2626", "#ea580c"]
    rebate_colors = ["#dc2626", "#ea580c", "#f59e0b", "#d97706", "#b45309", "#92400e"]

    for idx, sale in enumerate(agent.sales, 1):
        bumi_badge = ('<span class="unit-card-badge" style="background:#d1fae5;color:#059669;">Bumi</span>'
                      if sale.buyer_is_bumi else '')
        type_badge = (f'<span class="unit-card-badge" style="background:#e0e7ff;color:#4338ca;">'
                      f'{sale.buyer_type.title()}</span>')

        # --- Always-visible unit summary card ---
        st.markdown(f"""
        <div class="unit-card">
            <div class="unit-card-header">
                <div>
                    <span class="unit-card-title">🏠 Unit {idx}: {sale.unit_id}</span>
                    {type_badge}{bumi_badge}
                </div>
                <div class="unit-card-commission">
                    <div class="unit-card-commission-label">Commission</div>
                    <div class="unit-card-commission-value">{fmt_full(sale.commission_amount)}</div>
                </div>
            </div>
            <div class="unit-card-meta">
                <span>📍 Block {sale.block} · Floor {sale.floor}</span>
                <span>🏷️ Type {sale.unit_type}</span>
                <span>👤 {sale.buyer_name}</span>
                <span>📅 {sale.spa_date}</span>
            </div>
            <div class="unit-subtotal">
                <div class="unit-subtotal-item">
                    <div class="unit-subtotal-label">Sale Price</div>
                    <div class="unit-subtotal-value">{fmt_full(sale.sale_price)}</div>
                </div>
                <div class="unit-subtotal-item">
                    <div class="unit-subtotal-label">Commission</div>
                    <div class="unit-subtotal-value" style="color:#4F46E5;">{fmt_full(sale.commission_amount)}</div>
                </div>
                <div class="unit-subtotal-item">
                    <div class="unit-subtotal-label">Rebate</div>
                    <div class="unit-subtotal-value" style="color:#dc2626;">- {fmt_full(sale.rebate_amount)}</div>
                </div>
                <div class="unit-subtotal-item">
                    <div class="unit-subtotal-label">Net Price</div>
                    <div class="unit-subtotal-value" style="color:#059669;">{fmt_full(sale.net_price)}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # --- Expandable detail (commission & rebate rules) ---
        num_rules = len(sale.commission_breakdown) + len(sale.rebate_breakdown)
        with st.expander(f"🔍 View {num_rules} rule(s) applied to {sale.unit_id}", expanded=False):
            # Commission rules for this unit
            if sale.commission_breakdown:
                st.markdown('<div class="rebate-section-header" style="margin-top:0;border-top:none;">💰 Commission Rules</div>',
                            unsafe_allow_html=True)
                for i, item in enumerate(sale.commission_breakdown):
                    color = dot_colors[i % len(dot_colors)]
                    rule_badge = (f'<span class="breakdown-badge-rule">{item["rule_id"]}</span>'
                                  if item.get("rule_id") else '')
                    rate_badge = f'<span class="breakdown-badge">{item["rate"]}%</span>'
                    memo_badge = (f'<span class="breakdown-badge-memo">{item["memo_reference"]}</span>'
                                  if item.get("memo_reference") else '')
                    st.markdown(f"""
                    <div class="breakdown-row">
                        <div style="display:flex; align-items:center; flex-wrap:wrap;">
                            <span class="breakdown-dot" style="background:{color};"></span>
                            <span class="breakdown-label">{item['label']}</span>
                            {rule_badge} {rate_badge} {memo_badge}
                        </div>
                        <div class="breakdown-amount">{fmt_full(item['amount'])}</div>
                    </div>
                    """, unsafe_allow_html=True)

            # Rebate rules for this unit
            if sale.rebate_breakdown:
                st.markdown('<div class="rebate-section-header">🏷️ Buyer Rebate Rules</div>',
                            unsafe_allow_html=True)
                for i, item in enumerate(sale.rebate_breakdown):
                    color = rebate_colors[i % len(rebate_colors)]
                    rule_badge = (f'<span class="breakdown-badge-rule">{item["rule_id"]}</span>'
                                  if item.get("rule_id") else '')
                    rate_badge = f'<span class="breakdown-badge">{item["rate"]}%</span>'
                    memo_badge = (f'<span class="breakdown-badge-memo">{item["memo_reference"]}</span>'
                                  if item.get("memo_reference") else '')
                    st.markdown(f"""
                    <div class="breakdown-row">
                        <div style="display:flex; align-items:center; flex-wrap:wrap;">
                            <span class="breakdown-dot" style="background:{color};"></span>
                            <span class="breakdown-label">{item['label']}</span>
                            {rule_badge} {rate_badge} {memo_badge}
                        </div>
                        <div class="breakdown-amount" style="color:#dc2626 !important;">- {fmt_full(item['amount'])}</div>
                    </div>
                    """, unsafe_allow_html=True)

            # Packages for this unit
            if sale.packages:
                pkgs_str = ", ".join(sale.packages)
                st.markdown(f'<div style="font-size:0.82rem;color:#64748b;padding:0.3rem 0;">📦 {pkgs_str}</div>',
                            unsafe_allow_html=True)


def render_agent_unit_details(agent: Agent):
    """Render per-unit sales detail table for an agent."""
    st.markdown("""
    <table class="unit-table">
        <tr>
            <th>Unit</th>
            <th>Buyer</th>
            <th>Type</th>
            <th>Bumi</th>
            <th>Floor</th>
            <th>Sale Price</th>
            <th>Commission</th>
            <th>Rebate</th>
            <th>Net Price</th>
            <th>SPA Date</th>
        </tr>
    """, unsafe_allow_html=True)

    for s in agent.sales:
        bumi_badge = '<span style="background:#d1fae5;color:#059669;padding:0.1rem 0.4rem;border-radius:4px;font-size:0.75rem;">Yes</span>' if s.buyer_is_bumi else '<span style="color:#94a3b8;font-size:0.75rem;">No</span>'
        buyer_type_badge = f'<span style="background:#e0e7ff;color:#4338ca;padding:0.1rem 0.4rem;border-radius:4px;font-size:0.7rem;">{s.buyer_type.title()}</span>'

        # Commission breakdown tooltip text
        comm_details = " + ".join(
            f'{item.get("rule_id", "")} {item["rate"]}%'
            for item in s.commission_breakdown
        )
        reb_details = " + ".join(
            f'{item.get("rule_id", "")} {item["rate"]}%'
            for item in s.rebate_breakdown
        ) if s.rebate_breakdown else "—"

        st.markdown(f"""
        <tr>
            <td><strong>{s.unit_id}</strong></td>
            <td>{s.buyer_name} {buyer_type_badge}</td>
            <td>{s.unit_type}</td>
            <td>{bumi_badge}</td>
            <td>L{s.floor}</td>
            <td>{fmt_full(s.sale_price)}</td>
            <td title="{comm_details}"><strong>{fmt_full(s.commission_amount)}</strong><br><span style="font-size:0.7rem;color:#64748b;">{comm_details}</span></td>
            <td title="{reb_details}" style="color:#dc2626;">{fmt_full(s.rebate_amount)}<br><span style="font-size:0.7rem;color:#94a3b8;">{reb_details}</span></td>
            <td>{fmt_full(s.net_price)}</td>
            <td>{s.spa_date}</td>
        </tr>
        """, unsafe_allow_html=True)

    st.markdown("</table>", unsafe_allow_html=True)

    # Show packages if any
    all_packages = [pkg for s in agent.sales for pkg in s.packages]
    if all_packages:
        st.markdown("---")
        st.markdown("**📦 Applicable Packages:**")
        for pkg in set(all_packages):
            st.markdown(f"- {pkg}")


def render_performance_charts(agents: List[Agent]):
    """Render enhanced performance visualisations with styled HTML panels."""

    # ── Section header ──
    st.markdown(
        '<div class="section-header">'
        '<div>'
        '<div class="section-title">Analytics &amp; Insights</div>'
        '<div class="section-subtitle">Commission distribution, top performers, payment status, and rule utilisation</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ═══════════════════════════════════════════════════════════════════════
    # Commission Distribution by Agent — horizontal bar chart panel
    # ═══════════════════════════════════════════════════════════════════════
    max_comm = max((a.total_commission for a in agents), default=1) or 1

    dist_html = (
        '<div class="analytics-panel">'
        '<div class="analytics-panel-header">'
        '<div class="analytics-panel-icon" style="background:#EEF2FF;color:#4F46E5;">📊</div>'
        '<div>'
        '<div class="analytics-panel-title">Commission Distribution by Agent</div>'
        '<div class="analytics-panel-subtitle">Commission vs Net Payable for each agent</div>'
        '</div>'
        '</div>'
        '<div class="analytics-panel-body">'
        # Legend
        '<div style="display:flex;gap:1.25rem;margin-bottom:0.75rem;">'
        '<span style="display:flex;align-items:center;gap:0.35rem;font-size:0.72rem;color:#64748b;">'
        '<span style="width:10px;height:10px;border-radius:2px;background:#4F46E5;display:inline-block;"></span> Commission</span>'
        '<span style="display:flex;align-items:center;gap:0.35rem;font-size:0.72rem;color:#64748b;">'
        '<span style="width:10px;height:10px;border-radius:2px;background:#0D9488;display:inline-block;"></span> Net Payable</span>'
        '</div>'
    )

    for a in sorted(agents, key=lambda x: x.total_commission, reverse=True):
        comm_pct = min((a.total_commission / max_comm * 100), 100) if max_comm > 0 else 0
        net_pct = min((a.net_payable / max_comm * 100), 100) if max_comm > 0 else 0
        dist_html += (
            '<div class="comm-bar-row">'
            f'<div class="comm-bar-avatar" style="background:{a.avatar_color};">{a.initials}</div>'
            '<div class="comm-bar-info">'
            f'<div class="comm-bar-name">{a.name}</div>'
            '<div class="comm-bar-track">'
            f'<div class="comm-bar-fill-net" style="width:{net_pct}%;"></div>'
            f'<div class="comm-bar-fill-comm" style="width:{comm_pct}%;"></div>'
            '</div>'
            '</div>'
            '<div class="comm-bar-values">'
            f'<div class="comm-bar-val cv-blue">{fmt(a.total_commission)}</div>'
            f'<div class="comm-bar-val cv-teal">{fmt(a.net_payable)}</div>'
            '</div>'
            '</div>'
        )

    dist_html += '</div></div>'
    st.markdown(dist_html, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════════
    # Two-column: Top Performers + Payment Status
    # ═══════════════════════════════════════════════════════════════════════
    col1, col2 = st.columns(2)

    with col1:
        top = sorted(agents, key=lambda a: a.total_sales, reverse=True)
        total_sales_all = sum(ag.total_sales for ag in agents) or 1

        perf_html = (
            '<div class="analytics-panel">'
            '<div class="analytics-panel-header">'
            '<div class="analytics-panel-icon" style="background:#fef3c7;color:#b45309;">🏆</div>'
            '<div>'
            '<div class="analytics-panel-title">Top Performers</div>'
            '<div class="analytics-panel-subtitle">Ranked by total sales volume</div>'
            '</div>'
            '</div>'
            '<div class="analytics-panel-body">'
        )
        for i, a in enumerate(top[:5], 1):
            pct = (a.total_sales / total_sales_all) * 100
            rank_cls = f"top-perf-rank-{i}" if i <= 3 else "top-perf-rank-default"
            perf_html += (
                '<div class="top-perf-row">'
                f'<div class="top-perf-rank {rank_cls}">{i}</div>'
                f'<div class="top-perf-name">{a.name}</div>'
                f'<div class="top-perf-amount">{fmt(a.total_sales)}</div>'
                f'<div class="top-perf-pct">{pct:.1f}%</div>'
                '</div>'
            )
        perf_html += '</div></div>'
        st.markdown(perf_html, unsafe_allow_html=True)

    with col2:
        paid = sum(1 for a in agents if a.status == "Paid")
        partial = sum(1 for a in agents if a.status == "Partial")
        pending = sum(1 for a in agents if a.status == "Pending")
        total_outstanding = sum(a.net_payable for a in agents if a.status != "Paid")

        pay_html = (
            '<div class="analytics-panel">'
            '<div class="analytics-panel-header">'
            '<div class="analytics-panel-icon" style="background:#f0fdf4;color:#16a34a;">💳</div>'
            '<div>'
            '<div class="analytics-panel-title">Payment Status</div>'
            '<div class="analytics-panel-subtitle">Overview of agent payment progress</div>'
            '</div>'
            '</div>'
            '<div class="analytics-panel-body">'
            '<div class="pay-status-grid">'
            '<div class="pay-status-card psc-paid">'
            f'<div class="pay-status-count psc-paid">{paid}</div>'
            '<div class="pay-status-label">Paid</div>'
            '</div>'
            '<div class="pay-status-card psc-partial">'
            f'<div class="pay-status-count psc-partial">{partial}</div>'
            '<div class="pay-status-label">Partial</div>'
            '</div>'
            '<div class="pay-status-card psc-pending">'
            f'<div class="pay-status-count psc-pending">{pending}</div>'
            '<div class="pay-status-label">Pending</div>'
            '</div>'
            '</div>'
            '<div class="pay-outstanding">'
            '<div class="pay-outstanding-label">Total Outstanding</div>'
            f'<div class="pay-outstanding-value">{fmt(total_outstanding)}</div>'
            '</div>'
            '</div></div>'
        )
        st.markdown(pay_html, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════════
    # Rule Utilisation Across All Sales — styled table
    # ═══════════════════════════════════════════════════════════════════════
    rule_usage: Dict[str, Dict] = {}
    for a in agents:
        for s in a.sales:
            for item in s.commission_breakdown:
                rid = item.get("rule_id", item["label"])
                if rid not in rule_usage:
                    rule_usage[rid] = {"rule_id": rid, "rule_name": item["label"], "type": "Commission", "count": 0, "amount": 0.0}
                rule_usage[rid]["count"] += 1
                rule_usage[rid]["amount"] += item["amount"]
            for item in s.rebate_breakdown:
                rid = item.get("rule_id", item["label"])
                if rid not in rule_usage:
                    rule_usage[rid] = {"rule_id": rid, "rule_name": item["label"], "type": "Rebate", "count": 0, "amount": 0.0}
                rule_usage[rid]["count"] += 1
                rule_usage[rid]["amount"] += item["amount"]

    if rule_usage:
        sorted_rules = sorted(rule_usage.values(), key=lambda r: r["amount"], reverse=True)
        max_amount = sorted_rules[0]["amount"] if sorted_rules else 1

        rule_html = (
            '<div class="analytics-panel">'
            '<div class="analytics-panel-header">'
            '<div class="analytics-panel-icon" style="background:#f5f3ff;color:#7c3aed;">📐</div>'
            '<div>'
            '<div class="analytics-panel-title">Rule Utilisation Across All Sales</div>'
            f'<div class="analytics-panel-subtitle">{len(sorted_rules)} rules applied across {sum(len(a.sales) for a in agents)} sales</div>'
            '</div>'
            '</div>'
            '<div class="analytics-panel-body" style="padding:0;">'
            '<table class="rule-table">'
            '<thead><tr>'
            '<th>Rule ID</th>'
            '<th>Rule Name</th>'
            '<th>Type</th>'
            '<th>Times Applied</th>'
            '<th>Impact</th>'
            '<th>Total Amount</th>'
            '</tr></thead>'
            '<tbody>'
        )
        for r in sorted_rules:
            type_cls = "rtb-commission" if r["type"] == "Commission" else "rtb-rebate"
            bar_cls = "rbf-commission" if r["type"] == "Commission" else "rbf-rebate"
            bar_pct = min((r["amount"] / max_amount * 100), 100) if max_amount > 0 else 0
            rule_html += (
                '<tr>'
                f'<td><strong>{r["rule_id"]}</strong></td>'
                f'<td>{r["rule_name"]}</td>'
                f'<td><span class="rule-type-badge {type_cls}">{r["type"]}</span></td>'
                f'<td>{r["count"]}</td>'
                f'<td class="rule-bar-cell"><div class="rule-bar-track">'
                f'<div class="rule-bar-fill {bar_cls}" style="width:{bar_pct}%;"></div>'
                '</div></td>'
                f'<td>RM {r["amount"]:,.2f}</td>'
                '</tr>'
            )
        rule_html += '</tbody></table></div></div>'
        st.markdown(rule_html, unsafe_allow_html=True)

    # ---- Memo Library section ----
    st.markdown("---")
    render_memo_library()


def render_memo_library():
    """Render memo library section showing available memos and their rules."""
    st.markdown("#### 📚 Memo Library")
    st.markdown('<span style="color:#64748b;font-size:0.88rem;">Browse loaded memos and view available rules from each memo.</span>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    try:
        engine = _create_engine()
    except Exception as e:
        st.warning(f"Could not load memo engine: {e}")
        return

    memos = engine.memo_manager.memos
    if not memos:
        st.info("No memos loaded.")
        return

    memo_options = sorted(memos.keys())

    selected_memo = st.selectbox(
        "Select a Memo to View Details",
        options=memo_options,
        format_func=lambda x: f"{x} - {memos[x].metadata.project_name}" if memos[x].metadata else x,
        key="memo_lib_select",
    )

    if not selected_memo:
        return

    memo = memos[selected_memo]
    metadata = memo.metadata

    st.markdown("---")

    # ---- Memo Header Card ----
    memo_type = metadata.memo_type.value if hasattr(metadata.memo_type, 'value') else str(metadata.memo_type)
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#0F172A 0%,#1E293B 100%);border-radius:14px;padding:1.15rem 1.5rem;margin-bottom:1rem;border:1px solid rgba(255,255,255,0.06);">
        <div style="color:rgba(255,255,255,0.7);font-size:0.75rem;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;">📋 {memo_type.upper()}</div>
        <div style="color:white;font-size:1.15rem;font-weight:700;margin-top:0.2rem;letter-spacing:-0.01em;">{metadata.memo_reference} - {metadata.project_name}</div>
    </div>
    """, unsafe_allow_html=True)

    # Memo info metrics
    effective = metadata.effective_period or {}
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📋 Memo Reference", metadata.memo_reference)
    with col2:
        st.metric("🏗️ Project", metadata.project_name)
    with col3:
        st.metric("📅 Effective From", effective.get('start_date', 'N/A'))
    with col4:
        st.metric("📅 Effective Until", effective.get('end_date', 'N/A'))

    st.markdown("")

    # Additional metadata row
    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.markdown(f"**Memo Type:** {memo_type.upper()}")
    with mc2:
        st.markdown(f"**Priority:** {metadata.priority}")
    with mc3:
        st.markdown(f"**Total Rules:** {len(memo.rules)}")

    st.markdown("---")

    # ---- Rule Statistics ----
    st.markdown("#### 📊 Rule Statistics - This Memo")

    rule_type_counts = {}
    for rule in memo.rules:
        rule_type = rule.rule_type
        rule_type_counts[rule_type] = rule_type_counts.get(rule_type, 0) + 1

    icons = {
        'commission': '💼',
        'rebate': '🎁',
        'referral': '🤝',
        'price_adjustment': '📈',
        'package': '📦',
    }

    if rule_type_counts:
        cols = st.columns(len(rule_type_counts))
        for i, (rule_type, count) in enumerate(rule_type_counts.items()):
            with cols[i]:
                st.metric(
                    f"{icons.get(rule_type, '📋')} {rule_type.replace('_', ' ').title()}",
                    count,
                )

    st.markdown("---")

    # ---- Commission Rules ----
    commission_rules = [r for r in memo.rules if r.rule_type == 'commission']
    if commission_rules:
        st.markdown("##### 💼 Commission Rules")
        for rule in commission_rules:
            with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
                rc1, rc2 = st.columns(2)
                with rc1:
                    st.markdown(f"**Buyer Type:** {rule.buyer_type or 'All'}")
                with rc2:
                    st.markdown(f"**Priority Score:** {rule.get_total_priority():.2f}")

                if rule.conditions:
                    st.markdown("**Conditions & Rates:**")
                    for cond in rule.conditions:
                        if isinstance(cond, dict):
                            condition = cond.get('condition', 'N/A')
                            rate = cond.get('commission_percentage', 'N/A')
                            desc = cond.get('description', '')
                            st.markdown(
                                '<div style="background:#ecfdf5;padding:0.8rem;margin:0.5rem 0;border-radius:8px;border-left:4px solid #059669;">'
                                '<div style="font-family:monospace;font-size:0.9rem;color:#1e293b;">'
                                f'<strong>IF</strong> {condition.replace("IF ", "")}'
                                '</div>'
                                '<div style="margin-top:0.5rem;">'
                                f'<span style="background:#059669;color:white;padding:0.2rem 0.6rem;border-radius:4px;font-weight:bold;">Commission: {rate}%</span>'
                                '</div>'
                                + (f'<div style="margin-top:0.5rem;color:#64748b;font-style:italic;">{desc}</div>' if desc else '')
                                + '</div>',
                                unsafe_allow_html=True,
                            )

                notes = rule.raw_data.get('notes', [])
                if notes:
                    st.markdown("**Notes:**")
                    for note in notes:
                        st.markdown(f"- {note}")

    # ---- Rebate Rules ----
    rebate_rules = [r for r in memo.rules if r.rule_type == 'rebate']
    if rebate_rules:
        st.markdown("##### 🎁 Rebate Rules")
        for rule in rebate_rules:
            with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
                rc1, rc2 = st.columns(2)
                with rc1:
                    rebate_type = rule.raw_data.get('rebate_type', 'N/A')
                    st.markdown(f"**Rebate Type:** {rebate_type}")
                with rc2:
                    st.markdown(f"**Priority Score:** {rule.get_total_priority():.2f}")

                if rule.conditions:
                    st.markdown("**Conditions & Rates:**")
                    for cond in rule.conditions:
                        if isinstance(cond, dict):
                            condition = cond.get('condition', 'N/A')
                            rate = cond.get('rebate_percentage', 'N/A')
                            desc = cond.get('description', '')
                            st.markdown(
                                '<div style="background:#EEF2FF;padding:0.8rem;margin:0.5rem 0;border-radius:8px;border-left:4px solid #4F46E5;">'
                                '<div style="font-family:monospace;font-size:0.9rem;color:#1e293b;">'
                                f'<strong>IF</strong> {condition.replace("IF ", "")}'
                                '</div>'
                                '<div style="margin-top:0.5rem;">'
                                f'<span style="background:#4F46E5;color:white;padding:0.2rem 0.6rem;border-radius:4px;font-weight:bold;">Rebate: {rate}%</span>'
                                '</div>'
                                + (f'<div style="margin-top:0.5rem;color:#64748b;font-style:italic;">{desc}</div>' if desc else '')
                                + '</div>',
                                unsafe_allow_html=True,
                            )

                notes = rule.raw_data.get('notes', [])
                if notes:
                    st.markdown("**Notes:**")
                    for note in notes:
                        st.markdown(f"- {note}")

    # ---- Referral Rules ----
    referral_rules = [r for r in memo.rules if r.rule_type == 'referral']
    if referral_rules:
        st.markdown("##### 🤝 Referral Rules")
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
                            st.markdown(
                                '<div style="background:#fef3c7;padding:0.8rem;margin:0.5rem 0;border-radius:8px;border-left:4px solid #f59e0b;">'
                                '<div style="font-family:monospace;font-size:0.9rem;color:#1e293b;">'
                                f'<strong>IF</strong> {condition.replace("IF ", "")}'
                                '</div>'
                                '<div style="margin-top:0.5rem;">'
                                f'<span style="background:#f59e0b;color:black;padding:0.2rem 0.6rem;border-radius:4px;font-weight:bold;">Referral: {rate}%</span>'
                                '</div>'
                                + (f'<div style="margin-top:0.5rem;color:#64748b;font-style:italic;">{desc}</div>' if desc else '')
                                + '</div>',
                                unsafe_allow_html=True,
                            )

                notes = rule.raw_data.get('notes', [])
                if notes:
                    st.markdown("**Notes:**")
                    for note in notes:
                        st.markdown(f"- {note}")

    # ---- Price Adjustment Rules ----
    adjustment_rules = [r for r in memo.rules if r.rule_type == 'price_adjustment']
    if adjustment_rules:
        st.markdown("##### 📈 Price Adjustment Rules")
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
                            st.markdown(
                                '<div style="background:#f5f3ff;padding:0.8rem;margin:0.5rem 0;border-radius:8px;border-left:4px solid #7c3aed;">'
                                '<div style="font-family:monospace;font-size:0.9rem;color:#1e293b;">'
                                f'<strong>IF</strong> {condition.replace("IF ", "")}'
                                '</div>'
                                '<div style="margin-top:0.5rem;">'
                                f'<span style="background:#7c3aed;color:white;padding:0.2rem 0.6rem;border-radius:4px;font-weight:bold;">Adjustment: {amount}</span>'
                                '</div>'
                                + (f'<div style="margin-top:0.5rem;color:#64748b;font-style:italic;">{desc}</div>' if desc else '')
                                + '</div>',
                                unsafe_allow_html=True,
                            )

    # ---- Package Rules ----
    package_rules = [r for r in memo.rules if r.rule_type == 'package']
    if package_rules:
        st.markdown("##### 📦 Package Rules")
        for rule in package_rules:
            with st.expander(f"**{rule.rule_id}**: {rule.rule_name}", expanded=False):
                st.markdown(f"**Priority Score:** {rule.get_total_priority():.2f}")

                if rule.conditions:
                    st.markdown("**Conditions:**")
                    for cond in rule.conditions:
                        if isinstance(cond, dict):
                            condition = cond.get('condition', 'N/A')
                            desc = cond.get('description', '')
                            st.markdown(
                                '<div style="background:#fff7ed;padding:0.8rem;margin:0.5rem 0;border-radius:8px;border-left:4px solid #ea580c;">'
                                '<div style="font-family:monospace;font-size:0.9rem;color:#1e293b;">'
                                f'<strong>IF</strong> {condition.replace("IF ", "")}'
                                '</div>'
                                + (f'<div style="margin-top:0.5rem;color:#64748b;font-style:italic;">{desc}</div>' if desc else '')
                                + '</div>',
                                unsafe_allow_html=True,
                            )


# ---------------------------------------------------------------------------
# ADD ENTRY DIALOG
# ---------------------------------------------------------------------------

@st.dialog("➕ Add New Sale Entry", width="large")
def add_entry_dialog(agents_data: List[Dict]):
    """
    Full-screen dialog that mirrors the calculator inputs from app_multi_memo.py.
    Flow: fill form → Calculate → review result → Save & Close.
    """

    # ---- Agent selector (top) ----
    agent_options = {f"{a['name']} ({a['agent_id']})": a["agent_id"] for a in agents_data}
    selected_label = st.selectbox("**Assign to Agent**", list(agent_options.keys()))
    selected_agent_id = agent_options[selected_label]

    st.markdown("---")

    # ---- Row 1: SPA date + Project ----
    c_date, c_proj = st.columns(2)
    with c_date:
        spa_date = st.date_input(
            "Date of SPA Signing",
            value=date.today(),
            help="The system filters applicable memos based on this date.",
        )
    with c_proj:
        project = st.selectbox("Project Name", ["Aetas Seputeh"], index=0)

    st.markdown("---")

    # ---- Row 2: Property Details | Buyer Profile | Unit Attributes ----
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("##### 💰 Property Details")
        sale_price = st.number_input(
            "List Price (RM)", min_value=100000, max_value=10000000,
            value=1500000, step=50000, help="Original list price of the unit",
        )
        block = st.selectbox("Block", ["A", "B"], help="Block A or B – different commission structures apply")
        floor = st.slider("Floor Level", 10, 40, 25, help="Floor level affects commission and rebate tiers")

    with col2:
        st.markdown("##### 👤 Buyer Profile")
        buyer_type = st.selectbox("Buyer Type", ["Local", "Foreign"], help="Different pricing packages apply")
        buyer_is_bumi = st.checkbox("Bumiputera Buyer", value=False, help="Qualifies for additional rebate")
        unit_type = st.selectbox("Unit Type", ["A1", "A2", "B1", "B2"], help="Determines standard rebate %")

    with col3:
        st.markdown("##### 🏠 Unit Attributes")
        is_garden_unit = st.checkbox("Garden Unit (Level 10)", value=False)
        is_penthouse = st.checkbox("Penthouse", value=False)
        loan_purchase = st.checkbox("Loan Purchase", value=False, help="Additional 1% rebate for loan purchases")

    st.markdown("---")

    # ---- Row 3: Buyer & Unit ID ----
    cb1, cb2 = st.columns(2)
    with cb1:
        buyer_name = st.text_input("Buyer Name", value="", placeholder="e.g. Tan Wei Ling")
    with cb2:
        suggested_id = f"{block}-{floor}-{unit_type}"
        unit_id = st.text_input("Unit ID", value=suggested_id, help="Auto-suggested, feel free to edit")

    # ---- Calculate button ----
    st.markdown("")
    calc_clicked = st.button("🔄  Calculate Commission & Rebates", type="primary", use_container_width=True)

    if calc_clicked:
        if not buyer_name.strip():
            st.warning("Please enter the buyer's name.")
            return

        form_data = {
            "spa_date": spa_date,
            "sale_price": sale_price,
            "block": block,
            "floor": floor,
            "buyer_type": buyer_type,
            "buyer_is_bumi": buyer_is_bumi,
            "unit_type": unit_type,
            "is_garden_unit": is_garden_unit,
            "is_penthouse": is_penthouse,
            "loan_purchase": loan_purchase,
            "buyer_name": buyer_name.strip(),
            "unit_id": unit_id.strip(),
        }

        with st.spinner("Running rule engine …"):
            try:
                result = run_engine_calculation(form_data)
            except Exception as e:
                st.error(f"Calculation failed: {e}")
                return

        # Store result in session so the Save button can access it
        st.session_state["_add_entry_result"] = result
        st.session_state["_add_entry_form"] = form_data
        st.session_state["_add_entry_agent"] = selected_agent_id

    # ---- Show result (if calculated) ----
    result: Optional[MultiMemoPricingResult] = st.session_state.get("_add_entry_result")
    form_data_saved: Optional[Dict] = st.session_state.get("_add_entry_form")

    if result and form_data_saved:
        st.markdown("---")
        st.markdown("### 📊 Calculation Result")

        # Summary metrics
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("List Price", fmt_full(result.base_price))
        mc2.metric("Total Commission", fmt_full(result.total_commission))
        mc3.metric("Total Rebate", fmt_full(result.total_rebate))
        mc4.metric("Net Price", fmt_full(result.final_price))

        # Commission breakdown
        if result.commission_breakdown:
            st.markdown("**💰 Commission Breakdown**")
            for item in result.commission_breakdown:
                st.markdown(
                    f"- `{item.rule_id}` **{item.rule_name}** — {item.value}% → **{fmt_full(item.calculated_amount or 0)}**"
                    f"  *(Memo: {item.memo_reference})*"
                )

        # Rebate breakdown
        if result.rebate_breakdown:
            st.markdown("**🏷️ Rebate Breakdown**")
            for item in result.rebate_breakdown:
                st.markdown(
                    f"- `{item.rule_id}` **{item.rule_name}** — {item.value}% → **{fmt_full(item.calculated_amount or 0)}**"
                    f"  *(Memo: {item.memo_reference})*"
                )

        # Packages
        if result.applicable_packages:
            st.markdown(f"**📦 Packages:** {', '.join(result.applicable_packages)}")

        # ---- Save button ----
        st.markdown("")
        if st.button("💾  Save Entry & Close", type="primary", use_container_width=True):
            sale_entry = pricing_result_to_sale_entry(form_data_saved, result)
            agent_id = st.session_state.get("_add_entry_agent", "AG001")
            save_sale_to_json(agent_id, sale_entry)

            # Clean up temp state
            for k in ["_add_entry_result", "_add_entry_form", "_add_entry_agent"]:
                st.session_state.pop(k, None)
            # Force data reload
            st.session_state.pop("mgmt_agents", None)
            st.session_state.pop("mgmt_calculated", None)

            st.success("✅ Entry saved! Refreshing dashboard …")
            st.rerun()


# ---------------------------------------------------------------------------
# ENTITLEMENT TRACKING – Render functions
# ---------------------------------------------------------------------------

def render_entitlement_metrics(agents: List[Agent]):
    """Render the four entitlement summary metric cards."""
    total_entitlement = sum(a.total_commission for a in agents)
    claimed_to_date = sum(a.total_previously_paid for a in agents)
    balance_to_claim = total_entitlement - claimed_to_date
    current_period = 0.0
    for a in agents:
        for p in a.payment_history:
            if p.status == "paid":
                current_period += p.amount

    # Claim rate for an extra visual indicator
    claim_rate = round(claimed_to_date / total_entitlement * 100) if total_entitlement > 0 else 0

    cols = st.columns(4)
    with cols[0]:
        st.markdown(
            '<div class="metric-card" style="border-left:4px solid #4F46E5;">'
            '<div class="metric-icon" style="background:#EEF2FF; color:#4F46E5;">💰</div>'
            '<div>'
            '<div class="metric-label">Total Entitlement</div>'
            '<div class="metric-value">' + fmt(total_entitlement) + '</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            '<div class="metric-card" style="border-left:4px solid #059669;">'
            '<div class="metric-icon" style="background:#d1fae5; color:#059669;">✅</div>'
            '<div>'
            '<div class="metric-label">Claimed to Date</div>'
            '<div class="metric-value" style="color:#059669;">' + fmt(claimed_to_date) + '</div>'
            '<div style="margin-top:0.25rem;">'
            '<div style="width:100%;height:4px;background:#e2e8f0;border-radius:2px;overflow:hidden;">'
            '<div style="width:' + str(claim_rate) + '%;height:100%;background:linear-gradient(90deg,#059669,#10b981);border-radius:2px;"></div>'
            '</div>'
            '<div style="font-size:0.68rem;color:#94a3b8;margin-top:0.15rem;">' + str(claim_rate) + '% of total</div>'
            '</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            '<div class="metric-card" style="border-left:4px solid #dc2626;">'
            '<div class="metric-icon" style="background:#fef2f2; color:#dc2626;">⏳</div>'
            '<div>'
            '<div class="metric-label">Balance to Claim</div>'
            '<div class="metric-value" style="color:#dc2626;">' + fmt(balance_to_claim) + '</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with cols[3]:
        st.markdown(
            '<div class="metric-card-highlight">'
            '<div class="metric-icon" style="background:rgba(255,255,255,0.2); color:white;">📈</div>'
            '<div>'
            '<div class="metric-label">Current Period</div>'
            '<div class="metric-value">' + fmt(current_period) + '</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )


def render_entitlement_agent_row(agent: Agent):
    """Render a single agent row for the entitlement tab."""
    total_entitlement = agent.total_commission
    claimed = agent.total_previously_paid
    balance = total_entitlement - claimed

    if total_entitlement > 0:
        progress = min(round(claimed / total_entitlement * 100), 100)
    else:
        progress = 0

    if progress >= 100:
        status_badge = '<span class="badge-fully-paid">✅ Fully Paid</span>'
        progress_class = 'ent-progress-full'
    elif progress > 0:
        status_badge = '<span class="badge-partial">⚠ Partial</span>'
        progress_class = ''
    else:
        status_badge = '<span class="badge-pending">⏳ Pending</span>'
        progress_class = 'ent-progress-zero'

    leader_tag = (' <span style="font-size:0.68rem;background:linear-gradient(135deg,#fef3c7,#fde68a);'
                  'color:#d97706;padding:0.15rem 0.5rem;border-radius:6px;font-weight:600;">'
                  '⭐ Team Lead</span>') if agent.is_team_leader else ""

    num_payments = len(agent.payment_history)
    payments_info = (
        '<div style="font-size:0.7rem;color:#94a3b8;margin-top:0.15rem;">'
        + str(num_payments) + ' payment' + ('s' if num_payments != 1 else '')
        + '</div>'
    )

    html = (
        '<div class="entitlement-row">'
        '<div style="display:flex; align-items:center; min-width:240px;">'
        '<div class="agent-avatar" style="background:' + agent.avatar_color + ';">' + agent.initials + '</div>'
        '<div class="agent-info">'
        '<div class="agent-name">' + agent.name + leader_tag + '</div>'
        '<div class="agent-project">' + agent.team + ' · ' + agent.project + '</div>'
        + payments_info +
        '</div>'
        '</div>'
        '<div class="entitlement-metrics">'
        '<div>'
        '<div class="entitlement-metric-label">Total Entitlement</div>'
        '<div class="entitlement-metric-value">' + fmt(total_entitlement) + '</div>'
        '</div>'
        '<div>'
        '<div class="entitlement-metric-label">Claimed</div>'
        '<div class="entitlement-metric-value ent-claimed">' + fmt(claimed) + '</div>'
        '</div>'
        '<div>'
        '<div class="entitlement-metric-label">Balance</div>'
        '<div class="entitlement-metric-value ent-balance">' + fmt(balance) + '</div>'
        '</div>'
        '<div>'
        '<div class="ent-progress-container">'
        '<div class="ent-progress-header">'
        '<span style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;font-weight:600;letter-spacing:0.4px;">Progress</span>'
        '<span class="ent-progress-text">' + str(progress) + '%</span>'
        '</div>'
        '<div class="ent-progress-bar">'
        '<div class="ent-progress-fill ' + progress_class + '" style="width:' + str(progress) + '%;"></div>'
        '</div>'
        '</div>'
        '</div>'
        '<div>' + status_badge + '</div>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_entitlement_detail(agent: Agent):
    """Render the expanded entitlement detail: payment history + summary."""
    total_entitlement = agent.total_commission
    claimed = agent.total_previously_paid
    balance = total_entitlement - claimed
    current_period_claim = sum(p.amount for p in agent.payment_history if p.status == "paid")
    progress = min(round(claimed / total_entitlement * 100), 100) if total_entitlement > 0 else 0

    col_hist, col_summary = st.columns(2)

    with col_hist:
        # Payment history panel
        if agent.payment_history:
            num_paid = sum(1 for p in agent.payment_history if p.status == "paid")
            num_total = len(agent.payment_history)
            payment_rows_html = ""
            for idx, p in enumerate(agent.payment_history):
                date_display = p.date
                try:
                    dt = datetime.strptime(p.date, "%Y-%m-%d")
                    date_display = dt.strftime("%d %b %Y")
                except ValueError:
                    pass

                if p.status == "paid":
                    check_html = '<div class="payment-check">✓</div>'
                    badge_html = '<span class="payment-badge-paid">paid</span>'
                else:
                    check_html = '<div class="payment-check" style="background:#fef3c7;color:#d97706;">⏳</div>'
                    badge_html = ('<span class="payment-badge-paid" style="background:#fef3c7;color:#d97706;">'
                                  + p.status + '</span>')

                payment_rows_html += (
                    '<div class="payment-row">'
                    '<div class="payment-info">'
                    + check_html +
                    '<div><div class="payment-date">' + date_display + '</div>'
                    '<div class="payment-ref">' + p.reference + '</div></div>'
                    '</div>'
                    '<div class="payment-right">'
                    '<span class="payment-amount">' + fmt(p.amount) + '</span>'
                    + badge_html +
                    '</div>'
                    '</div>'
                )

            full_html = (
                '<div class="ent-payment-panel">'
                '<div class="ent-payment-panel-title">'
                '📋 Payment History'
                '<span class="ent-payment-count">' + str(num_paid) + '/' + str(num_total) + ' completed</span>'
                '</div>'
                + payment_rows_html +
                '</div>'
            )
            st.markdown(full_html, unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="ent-payment-panel">'
                '<div class="ent-payment-panel-title">📋 Payment History</div>'
                '<div class="ent-no-payments">No payments recorded yet</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    with col_summary:
        # Entitlement summary panel
        balance_class = "ent-red" if balance > 0 else "ent-green"
        claimed_class = "ent-blue" if claimed > 0 else ""

        # Mini progress ring (CSS circle)
        ring_color = '#059669' if progress >= 100 else ('#4F46E5' if progress > 0 else '#e2e8f0')
        progress_ring = (
            '<div style="display:flex;align-items:center;justify-content:center;margin:0.75rem 0 0.5rem 0;">'
            '<div style="position:relative;width:80px;height:80px;">'
            '<svg viewBox="0 0 36 36" style="width:80px;height:80px;transform:rotate(-90deg);">'
            '<path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" '
            'fill="none" stroke="#e2e8f0" stroke-width="3"/>'
            '<path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" '
            'fill="none" stroke="' + ring_color + '" stroke-width="3" '
            'stroke-dasharray="' + str(progress) + ', 100" stroke-linecap="round"/>'
            '</svg>'
            '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);">'
            '<div style="font-size:1rem;font-weight:700;color:#0f172a;text-align:center;">' + str(progress) + '%</div>'
            '<div style="font-size:0.6rem;color:#94a3b8;text-align:center;">claimed</div>'
            '</div>'
            '</div>'
            '</div>'
        )

        summary_html = (
            '<div class="ent-summary-panel">'
            '<div class="ent-summary-panel-title">💰 Entitlement Summary</div>'
            + progress_ring +
            '<div class="ent-summary-row">'
            '<span class="ent-summary-label">Total Entitlement</span>'
            '<span class="ent-summary-value">' + fmt(total_entitlement) + '</span>'
            '</div>'
            '<div class="ent-summary-row">'
            '<span class="ent-summary-label">Claimed to Date</span>'
            '<span class="ent-summary-value ' + claimed_class + '">' + fmt(claimed) + '</span>'
            '</div>'
            '<div class="ent-summary-row">'
            '<span class="ent-summary-label">Balance to Claim</span>'
            '<span class="ent-summary-value ' + balance_class + '">' + fmt(balance) + '</span>'
            '</div>'
            '<div class="ent-summary-row ent-summary-total">'
            '<span class="ent-summary-label">Current Period Claim</span>'
            '<span class="ent-summary-value">' + fmt(current_period_claim) + '</span>'
            '</div>'
            '</div>'
        )
        st.markdown(summary_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# MEMO CSS (appended to page)
# ---------------------------------------------------------------------------

MEMO_CSS = """
<style>
/* ---- Memo management page ---- */
.memo-page-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 1.5rem;
}
.memo-page-title { font-size: 1.85rem; font-weight: 800; color: #0f172a; letter-spacing: -0.03em; }
.memo-page-subtitle { color: #64748b; font-size: 0.9rem; font-weight: 400; }

/* Status pills */
.memo-status-approved {
    background: #D1FAE5; color: #059669;
    padding: 0.25rem 0.85rem; border-radius: 20px; font-size: 0.72rem; font-weight: 600;
    display: inline-flex; align-items: center; gap: 0.3rem;
    letter-spacing: 0.2px;
}
.memo-status-pending {
    background: #FEF3C7; color: #D97706;
    padding: 0.25rem 0.85rem; border-radius: 20px; font-size: 0.72rem; font-weight: 600;
    display: inline-flex; align-items: center; gap: 0.3rem;
    letter-spacing: 0.2px;
}
.memo-status-rejected {
    background: #FEE2E2; color: #DC2626;
    padding: 0.25rem 0.85rem; border-radius: 20px; font-size: 0.72rem; font-weight: 600;
    display: inline-flex; align-items: center; gap: 0.3rem;
    letter-spacing: 0.2px;
}

/* KPI Cards — equal-height columns */
[data-testid="stHorizontalBlock"]:has(.memo-kpi-card) {
    align-items: stretch !important;
}
[data-testid="stHorizontalBlock"]:has(.memo-kpi-card) [data-testid="stColumn"] {
    display: flex !important;
    flex-direction: column !important;
}
[data-testid="stHorizontalBlock"]:has(.memo-kpi-card) [data-testid="stColumn"] > [data-testid="stElementContainer"],
[data-testid="stHorizontalBlock"]:has(.memo-kpi-card) [data-testid="stColumn"] > div {
    flex: 1 !important;
    display: flex !important;
    flex-direction: column !important;
}
.memo-kpi-card {
    background: white; border-radius: 18px;
    padding: 1.35rem 1.5rem; text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02);
    border: 1px solid #f1f5f9;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
    height: 130px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    animation: fadeInUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.memo-kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #4F46E5, #818CF8, #4F46E5);
    background-size: 200% 100%;
    opacity: 0;
    transition: opacity 0.3s ease;
}
.memo-kpi-card::after {
    content: '';
    position: absolute; inset: 0;
    background: radial-gradient(circle at 50% -20%, rgba(79,70,229,0.03), transparent 70%);
    pointer-events: none;
}
.memo-kpi-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 32px rgba(79,70,229,0.1), 0 4px 12px rgba(0,0,0,0.04);
    border-color: #E0E7FF;
}
.memo-kpi-card:hover::before { opacity: 1; animation: shimmer 2s ease infinite; }
.memo-kpi-value { font-size: 2rem; font-weight: 800; color: #0f172a; letter-spacing: -0.03em; font-family: 'DM Sans', sans-serif; }
.memo-kpi-label { font-size: 0.72rem; color: #64748b; font-weight: 600; margin-top: 0.25rem; text-transform: uppercase; letter-spacing: 0.8px; }

/* Table rows */
.memo-table-row {
    background: white; border-radius: 16px;
    padding: 1rem 1.5rem; margin: 0.5rem 0;
    box-shadow: 0 1px 4px rgba(0,0,0,0.03);
    border: 1px solid #f1f5f9;
    display: grid; grid-template-columns: 2fr 1fr 1fr 1fr 1fr;
    align-items: center; gap: 0.5rem;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    animation: fadeInUp 0.35s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.memo-table-row:hover {
    box-shadow: 0 8px 24px rgba(79,70,229,0.07), 0 2px 8px rgba(0,0,0,0.04);
    transform: translateY(-2px);
    border-color: #E0E7FF;
}
.memo-table-row > div {
    overflow: hidden; text-overflow: ellipsis; min-width: 0;
}

/* Section headers */
.memo-section-header {
    background: linear-gradient(135deg, #0F172A 0%, #1E293B 60%, #1a2744 100%);
    color: white !important; padding: 0.75rem 1.25rem; border-radius: 12px;
    font-weight: 600; margin-bottom: 0.5rem; font-size: 0.88rem;
    letter-spacing: 0.02em;
    box-shadow: 0 2px 8px rgba(15,23,42,0.15);
}

/* Rule cards in memo view */
.memo-rule-card {
    background: #f8fafc; border-left: 4px solid #10B981;
    padding: 0.85rem 1.15rem; margin: 0.4rem 0; border-radius: 0 12px 12px 0;
    transition: all 0.2s ease;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}
.memo-rule-card:hover { background: #f1f5f9; }
.memo-rule-card-flagged {
    background: #FEF3C7; border-left: 4px solid #EF4444;
    padding: 0.85rem 1.15rem; margin: 0.4rem 0; border-radius: 0 10px 10px 0;
}

/* Step badges */
.memo-step-badge {
    display: inline-flex; align-items: center; justify-content: center;
    width: 36px; height: 36px; border-radius: 50%;
    background: linear-gradient(135deg, #4F46E5 0%, #6366F1 100%);
    color: white; font-weight: 700;
    margin-right: 0.6rem; font-size: 0.95rem;
    box-shadow: 0 2px 6px rgba(79, 70, 229, 0.25);
}
.memo-step-badge-done {
    background: linear-gradient(135deg, #059669 0%, #10B981 100%);
    box-shadow: 0 2px 6px rgba(16, 185, 129, 0.25);
}
.memo-step-badge-active {
    background: linear-gradient(135deg, #F59E0B 0%, #FBBF24 100%);
    color: #78350F;
    box-shadow: 0 2px 6px rgba(245, 158, 11, 0.25);
}
.memo-confidence-high { color: #059669; font-weight: 700; }
.memo-confidence-med  { color: #D97706; font-weight: 700; }
.memo-confidence-low  { color: #DC2626; font-weight: 700; }

/* ---- Rule-oriented cards (Extracted Rules page) ---- */
.rule-card {
    background: white; border-radius: 18px;
    padding: 1.4rem 1.5rem; margin-bottom: 1rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.02);
    border: 1px solid #e2e8f0;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
    animation: fadeInUp 0.45s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.rule-card::after {
    content: '';
    position: absolute; top: 0; left: 0;
    width: 3px; height: 100%;
    background: linear-gradient(180deg, #818CF8, #4F46E5);
    border-radius: 3px;
    opacity: 0;
    transition: opacity 0.25s ease;
}
.rule-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 32px rgba(79,70,229,0.08), 0 4px 12px rgba(0,0,0,0.04);
    border-color: #C7D2FE;
}
.rule-card:hover::after { opacity: 1; }
.rule-card-flagged {
    background: #FFFBEB; border-left: 4px solid #F59E0B;
}
.rule-card-invalid {
    background: #FEF2F2; border-left: 4px solid #EF4444;
}
.rule-card-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 0.75rem;
}
.rule-card-icon {
    width: 42px; height: 42px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.15rem; background: #EEF2FF; margin-right: 0.85rem;
    flex-shrink: 0;
}
.rule-card-title {
    font-size: 1rem; font-weight: 700; color: #0f172a; letter-spacing: -0.01em;
}
.rule-card-subtitle {
    font-size: 0.78rem; color: #64748b; margin-top: 2px;
}

/* Rule status badges */
.rule-badge-active {
    background: #DCFCE7; color: #16A34A;
    padding: 0.2rem 0.75rem; border-radius: 20px;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.2px;
}
.rule-badge-flagged {
    background: #FEF3C7; color: #D97706;
    padding: 0.2rem 0.75rem; border-radius: 20px;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.2px;
}
.rule-badge-invalid {
    background: #FEE2E2; color: #DC2626;
    padding: 0.2rem 0.75rem; border-radius: 20px;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.2px;
}

/* Rule info blocks */
.rule-info-block {
    background: #F8FAFC; border-radius: 10px;
    padding: 0.8rem 1rem; flex: 1;
    min-width: 0;
    border: 1px solid #F1F5F9;
}
.rule-info-label {
    font-size: 0.68rem; color: #94a3b8; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
}
.rule-info-value {
    font-size: 0.92rem; font-weight: 600; color: #0f172a;
    margin-top: 0.2rem;
}
.rule-confidence-bar {
    height: 6px; border-radius: 3px; background: #e2e8f0;
    margin-top: 0.35rem; overflow: hidden;
}
.rule-confidence-fill {
    height: 100%; border-radius: 3px;
    transition: width 0.4s ease;
}

/* Validation badges */
.vbadge-validated {
    background: #DCFCE7; color: #16A34A;
    padding: 0.2rem 0.75rem; border-radius: 20px;
    font-size: 0.7rem; font-weight: 600; margin-left: 0.4rem;
    letter-spacing: 0.2px;
}
.vbadge-not-validated {
    background: #FEE2E2; color: #DC2626;
    padding: 0.2rem 0.75rem; border-radius: 20px;
    font-size: 0.7rem; font-weight: 600; margin-left: 0.4rem;
    letter-spacing: 0.2px;
}
.vbadge-pending {
    background: #F1F5F9; color: #64748B;
    padding: 0.2rem 0.75rem; border-radius: 20px;
    font-size: 0.7rem; font-weight: 600; margin-left: 0.4rem;
    letter-spacing: 0.2px;
}

/* ---- Project Dashboard ---- */
.prj-card {
    background: white; border-radius: 18px;
    padding: 1.5rem; margin-bottom: 1.2rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.02);
    border: 1px solid #e2e8f0;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
    animation: fadeInUp 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.prj-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px; height: 100%;
    background: linear-gradient(180deg, #6366F1, #4F46E5, #3730A3);
    border-radius: 16px 0 0 16px;
    opacity: 0;
    transition: opacity 0.25s ease;
}
.prj-card::after {
    content: '';
    position: absolute; inset: 0;
    background: radial-gradient(ellipse at top right, rgba(79,70,229,0.02), transparent 60%);
    pointer-events: none;
}
.prj-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 32px rgba(79,70,229,0.08), 0 4px 12px rgba(0,0,0,0.04);
    border-color: #C7D2FE;
}
.prj-card:hover::before { opacity: 1; }
.prj-card-header {
    display: flex; align-items: flex-start; justify-content: space-between;
    margin-bottom: 1rem;
}
.prj-name {
    font-size: 1.15rem; font-weight: 700; color: #0f172a; letter-spacing: -0.01em;
}
.prj-id {
    font-size: 0.75rem; color: #94a3b8; margin-top: 2px; font-family: 'SF Mono', 'Fira Code', monospace;
}

/* Project status pills */
.prj-status-active {
    background: #DCFCE7; color: #16A34A;
    padding: 0.2rem 0.75rem; border-radius: 20px;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.2px;
}
.prj-status-completed {
    background: #EEF2FF; color: #4F46E5;
    padding: 0.2rem 0.75rem; border-radius: 20px;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.2px;
}
.prj-status-upcoming {
    background: #FEF3C7; color: #D97706;
    padding: 0.2rem 0.75rem; border-radius: 20px;
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.2px;
}

/* Project metrics grid — fixed 4-col for balanced rows */
.prj-metrics {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.6rem 0.75rem;
    margin-top: 0.25rem;
}
.prj-metric {
    background: #FAFAFD; border-radius: 12px;
    padding: 0.85rem 1rem;
    border: 1px solid #F0F1F5;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
}
.prj-metric::before {
    content: '';
    position: absolute; top: 0.9rem; left: 0;
    width: 3px; height: 1.6rem; border-radius: 0 3px 3px 0;
    background: var(--accent, #94a3b8);
    opacity: 0;
    transition: opacity 0.2s ease;
}
.prj-metric:hover {
    background: #F4F3FF;
    border-color: #E0E7FF;
    transform: translateY(-1px);
    box-shadow: 0 3px 10px rgba(79,70,229,0.06);
}
.prj-metric:hover::before { opacity: 1; }
/* Color accents per metric position */
.prj-metric:nth-child(1) { --accent: #6366F1; }
.prj-metric:nth-child(2) { --accent: #8B5CF6; }
.prj-metric:nth-child(3) { --accent: #10B981; }
.prj-metric:nth-child(4) { --accent: #0EA5E9; }
.prj-metric:nth-child(5) { --accent: #F59E0B; }
.prj-metric:nth-child(6) { --accent: #EC4899; }
.prj-metric:nth-child(7) { --accent: #14B8A6; }
.prj-metric:nth-child(8) { --accent: #6366F1; }
.prj-metric-label {
    font-size: 0.62rem; color: #94a3b8; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.6px;
    display: flex; align-items: center; gap: 0.35rem;
}
.prj-metric-label::before {
    content: '';
    display: inline-block; width: 6px; height: 6px;
    border-radius: 50%; background: var(--accent, #94a3b8);
    flex-shrink: 0;
}
.prj-metric-value {
    font-size: 1.1rem; font-weight: 700; color: #0f172a;
    margin-top: 0.2rem; letter-spacing: -0.01em;
    font-family: 'DM Sans', 'Inter', sans-serif;
}
.prj-health-green { color: #16A34A; }
.prj-health-yellow { color: #D97706; }
.prj-health-red { color: #DC2626; }
</style>
"""


# ---------------------------------------------------------------------------
# MEMO DATA HELPERS
# ---------------------------------------------------------------------------

def _load_memo_store() -> list:
    """Load the memo registry from memo_store.json."""
    if MEMO_STORE_PATH.exists():
        return json.loads(MEMO_STORE_PATH.read_text(encoding="utf-8"))
    return []


def _save_memo_store(data: list):
    """Persist the memo registry."""
    MEMO_STORE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_memo_rules(rules_filename: str | None) -> dict | None:
    """Load extracted rules JSON for a specific memo."""
    if not rules_filename:
        return None
    p = ARTIFACT_DIR / rules_filename
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _get_memo_images(image_files: list) -> list:
    """Return list of existing image paths from the memo folder."""
    return [MEMO_IMG_DIR / f for f in image_files if (MEMO_IMG_DIR / f).exists()]


def _next_memo_id(memos: list) -> str:
    existing = []
    for m in memos:
        mid = m.get("memo_id", "")
        if mid.startswith("MEMO_"):
            try:
                existing.append(int(mid.split("_")[1]))
            except ValueError:
                pass
    return f"MEMO_{max(existing, default=0) + 1:03d}"


def _memo_status_badge(status: str) -> str:
    return f'<span class="memo-status-{status}">{status.upper()}</span>'


def _memo_confidence_span(conf) -> str:
    if conf is None:
        return "—"
    cls = "memo-confidence-high" if conf >= 0.8 else ("memo-confidence-med" if conf >= 0.6 else "memo-confidence-low")
    return f'<span class="{cls}">{conf:.0%}</span>'


# ---------------------------------------------------------------------------
# MEMO PIPELINE FUNCTIONS (Upload flow)
# ---------------------------------------------------------------------------

def _convert_pdf_to_images(pdf_bytes: bytes, pdf_name: str) -> list:
    """Convert uploaded PDF bytes to images using PyMuPDF."""
    import fitz  # PyMuPDF

    stem = Path(pdf_name).stem
    output_dir = MEMO_IMG_DIR / f"{stem}_upload"
    output_dir.mkdir(parents=True, exist_ok=True)

    tmp = output_dir / f"_tmp_{pdf_name}"
    tmp.write_bytes(pdf_bytes)

    doc = fitz.open(str(tmp))
    image_paths = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=300)
        out = output_dir / f"{stem}_page-{i+1:04d}.jpg"
        pix.save(str(out))
        image_paths.append(out)
    doc.close()
    tmp.unlink(missing_ok=True)
    return image_paths


def _run_ocr_text(image_paths: list) -> dict:
    """Run text OCR on page images.

    Returns data in the ``{"results": [{"page_number", "model_output"}]}``
    format expected by ``format_ocr_for_agent``.
    """
    from ocr import ocr_images_with_chat_model, _maybe_parse_json

    user_prompt = (
        "Perform OCR on the image. Output only valid JSON (no markdown, no extra text). "
        "Follow the JSON schema described in the instructions and set confidence values realistically."
    )
    content = ocr_images_with_chat_model(image_paths=image_paths, user_prompt=user_prompt)
    parsed = _maybe_parse_json(content)

    # Build per-page "results" list that format_ocr_for_agent expects
    results = []
    if isinstance(parsed, dict) and "pages" in parsed:
        for page_data in parsed["pages"]:
            pn = page_data.get("page_number", len(results) + 1)
            idx = min(pn - 1, len(image_paths) - 1)
            results.append({
                "page_number": pn,
                "file": image_paths[idx].name if image_paths else "",
                "model_output": {"pages": [page_data]},
            })
    else:
        # Fallback: wrap entire output as a single result
        results.append({
            "page_number": 1,
            "file": image_paths[0].name if image_paths else "",
            "model_output": parsed if isinstance(parsed, dict) else {"raw": content},
        })

    return {"mode": "batch", "results": results}


def _run_ocr_table(image_paths: list) -> dict:
    """Run table OCR on page images.

    Returns data in the ``{"results": [{"page_number", "model_output"}]}``
    format expected by ``format_ocr_for_agent``.  ``model_output`` is kept
    as a **raw string** because the formatter parses it itself.
    """
    from ocrtable import ocr_images_with_chat_model as ocr_table_batch

    user_prompt = (
        "You are a TABLE-ONLY OCR and DOCUMENT STRUCTURE engine.\n"
        "Your role is STRICTLY LIMITED to tables extraction.\n"
        "Return valid JSON only. Detect all tables in the document."
    )
    content = ocr_table_batch(image_paths=image_paths, user_prompt=user_prompt)

    # format_ocr_for_agent expects model_output as a raw *string* for tables.
    # Batch mode returns one response covering all pages; wrap as single result.
    return {
        "mode": "batch",
        "results": [{
            "page_number": 1,
            "file": ", ".join(p.name for p in image_paths),
            "model_output": content,  # keep raw string – formatter parses it
        }],
    }


def _run_rule_extraction(text_data: dict, table_data: dict) -> dict:
    """Run the rule extraction agent on OCR outputs."""
    from rule import format_ocr_for_agent, extract_rules
    ocr_content = format_ocr_for_agent(text_data, table_data)
    return extract_rules(ocr_content)


def _save_new_memo(rules, image_paths, pdf_name, memo_ref, project_name, start_date, end_date, status):
    """Persist a new memo: save rules JSON + add entry to memo_store."""
    memos = _load_memo_store()
    memo_id = _next_memo_id(memos)

    # Save rules JSON
    rules_filename = f"extracted-rules-{memo_id.lower()}.json"
    (ARTIFACT_DIR / rules_filename).write_text(
        json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Copy images to central memo folder
    image_filenames = []
    for img in image_paths:
        target = MEMO_IMG_DIR / img.name
        if not target.exists():
            shutil.copy2(img, target)
        image_filenames.append(img.name)

    # Rule counts
    rs = rules.get("rules", {})
    rule_count = {
        k: len(rs.get(k, []))
        for k in ["commission_rules", "rebate_rules", "referral_rules", "price_adjustment_rules", "package_rules"]
    }

    entry = {
        "memo_id": memo_id,
        "memo_reference": memo_ref or rules.get("memo_reference", memo_id),
        "project_name": project_name or rules.get("project_name", ""),
        "effective_period": {"start_date": start_date, "end_date": end_date},
        "upload_date": datetime.now().strftime("%Y-%m-%d"),
        "status": status,
        "pdf_filename": pdf_name,
        "image_folder": Path(pdf_name).stem,
        "image_files": image_filenames,
        "rules_file": rules_filename,
        "extraction_confidence": rules.get("extraction_confidence"),
        "reviewer_notes": "",
        "rule_count": rule_count,
    }
    memos.append(entry)
    _save_memo_store(memos)


def _reset_upload_state():
    """Clear upload-related session state."""
    for k in ["upload_step", "upload_images", "upload_rules", "upload_pdf_name",
              "upload_text_ocr", "upload_table_ocr"]:
        st.session_state.pop(k, None)


# ---------------------------------------------------------------------------
# MEMO SECTION META (for rule display)
# ---------------------------------------------------------------------------

_MEMO_SECTION_META = {
    "commission_rules":       ("💰", "Commission Rules"),
    "rebate_rules":           ("🏷️", "Rebate Rules"),
    "referral_rules":         ("🤝", "Referral Rules"),
    "price_adjustment_rules": ("📐", "Price Adjustments"),
    "package_rules":          ("📦", "Packages"),
}


# ---------------------------------------------------------------------------
# MEMO RENDER: extracted rules summary
# ---------------------------------------------------------------------------

def _render_memo_rules_summary(rules: dict):
    """Compact display of all rules inside a memo (for inbox expanders)."""
    if not rules or "rules" not in rules:
        st.info("No extracted rules available for this memo.")
        return

    rule_sections = rules["rules"]
    for key, (icon, title) in _MEMO_SECTION_META.items():
        items = rule_sections.get(key, [])
        if not items:
            continue
        st.markdown(f'<div class="memo-section-header">{icon} {title} ({len(items)})</div>', unsafe_allow_html=True)
        for rule in items:
            rid = rule.get("rule_id", "")
            rname = rule.get("rule_name", "Untitled")
            with st.container():
                st.markdown(f"**{rid}** — {rname}")
                conditions = rule.get("conditions", [])
                if conditions and isinstance(conditions[0], dict):
                    rows = []
                    for c in conditions:
                        rows.append({
                            "Condition": c.get("condition", ""),
                            "Value": str(
                                c.get("commission_percentage",
                                c.get("rebate_percentage",
                                c.get("adjustment_amount", "")))
                            ) + ("%" if "percentage" in str(c) else ""),
                            "Description": c.get("description", ""),
                        })
                    st.table(rows)
                elif conditions:
                    for c in conditions:
                        st.markdown(f"- {c}")
                notes = rule.get("notes", [])
                if notes:
                    st.caption("Notes: " + " · ".join(notes))
                st.markdown("---")


# ---------------------------------------------------------------------------
# MEMO RENDER: extracted rules with flag controls (review panel)
# ---------------------------------------------------------------------------

def _render_memo_rules_panel(rules: dict | None, memo_id: str):
    """Right-panel rules display with per-rule flag/unflag toggle."""
    if not rules or "rules" not in rules:
        st.info("No extracted rules available.")
        return

    flag_key = f"flagged_{memo_id}"
    if flag_key not in st.session_state:
        st.session_state[flag_key] = set()

    rule_sections = rules["rules"]
    for section_key, (icon, title) in _MEMO_SECTION_META.items():
        items = rule_sections.get(section_key, [])
        if not items:
            continue

        st.markdown(f'<div class="memo-section-header">{icon} {title} ({len(items)})</div>', unsafe_allow_html=True)
        for rule in items:
            rid = rule.get("rule_id", "?")
            rname = rule.get("rule_name", "Untitled")
            is_flagged = rid in st.session_state[flag_key]

            card_cls = "memo-rule-card-flagged" if is_flagged else "memo-rule-card"
            st.markdown(f'<div class="{card_cls}"><strong>{rid}</strong> — {rname}</div>', unsafe_allow_html=True)

            conditions = rule.get("conditions", [])
            if conditions:
                if isinstance(conditions[0], dict):
                    for c in conditions:
                        cond = c.get("condition", "")
                        desc = c.get("description", "")
                        val = c.get("commission_percentage",
                              c.get("rebate_percentage",
                              c.get("adjustment_amount", "")))
                        st.markdown(f"&nbsp;&nbsp;&nbsp;`{cond}` → **{val}** — {desc}")
                else:
                    for c in conditions:
                        st.markdown(f"&nbsp;&nbsp;&nbsp;• {c}")

            notes = rule.get("notes", [])
            if notes:
                st.caption("Notes: " + " · ".join(notes))

            btn_label = "🚩 Unflag" if is_flagged else "🏳️ Flag mismatch"
            if st.button(btn_label, key=f"flag_{memo_id}_{rid}"):
                if is_flagged:
                    st.session_state[flag_key].discard(rid)
                else:
                    st.session_state[flag_key].add(rid)
                st.rerun()

    flagged = st.session_state[flag_key]
    if flagged:
        st.warning(f"⚠️ {len(flagged)} rule(s) flagged: {', '.join(sorted(flagged))}")


# ---------------------------------------------------------------------------
# MEMO RENDER: extracted rules for upload review step
# ---------------------------------------------------------------------------

def _render_extracted_rules_upload(rules: dict):
    """Display extracted rules during the upload review step."""
    if not rules or "rules" not in rules:
        st.warning("No rules could be extracted.")
        if "raw_response" in rules:
            with st.expander("Raw model response"):
                st.code(rules["raw_response"])
        return

    rule_sections = rules["rules"]
    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    mc1.metric("Commission", len(rule_sections.get("commission_rules", [])))
    mc2.metric("Rebate", len(rule_sections.get("rebate_rules", [])))
    mc3.metric("Referral", len(rule_sections.get("referral_rules", [])))
    mc4.metric("Price Adj.", len(rule_sections.get("price_adjustment_rules", [])))
    mc5.metric("Package", len(rule_sections.get("package_rules", [])))

    conf = rules.get("extraction_confidence")
    if conf is not None:
        st.progress(conf, text=f"Extraction confidence: {conf:.0%}")

    for w in rules.get("warnings", []):
        st.warning(f"⚠️ {w}")

    for section_key, (icon, title) in _MEMO_SECTION_META.items():
        items = rule_sections.get(section_key, [])
        if not items:
            continue
        st.markdown(f'<div class="memo-section-header">{icon} {title} ({len(items)})</div>', unsafe_allow_html=True)
        for rule in items:
            rid = rule.get("rule_id", "?")
            rname = rule.get("rule_name", "Untitled")
            st.markdown(f"**{rid}** — {rname}")
            conditions = rule.get("conditions", [])
            if conditions and isinstance(conditions[0], dict):
                rows = [{
                    "Condition": c.get("condition", ""),
                    "Value": str(c.get("commission_percentage", c.get("rebate_percentage", c.get("adjustment_amount", "")))),
                    "Description": c.get("description", ""),
                } for c in conditions]
                st.table(rows)
            elif conditions:
                for c in conditions:
                    st.markdown(f"- {c}")
            notes = rule.get("notes", [])
            if notes:
                st.caption("Notes: " + " · ".join(notes))
            st.markdown("---")

    pseudo = rules.get("pseudo_code", {})
    if pseudo:
        with st.expander("📝 Generated Pseudo-code"):
            for name, code in pseudo.items():
                st.markdown(f"**{name}**")
                st.code(code, language="python")


# ---------------------------------------------------------------------------
# MEMO PAGE: Upload Sub-View
# ---------------------------------------------------------------------------

def render_memo_upload():
    """3-step wizard: Upload PDF → OCR + Extract → Review & Save."""

    # Back button
    if st.button("← Back to Memorandums", key="upload_back"):
        _reset_upload_state()
        st.session_state["memo_sub_view"] = "list"
        st.rerun()

    # Session state init
    if "upload_step" not in st.session_state:
        st.session_state.upload_step = "upload"
    if "upload_images" not in st.session_state:
        st.session_state.upload_images = []
    if "upload_rules" not in st.session_state:
        st.session_state.upload_rules = None
    if "upload_pdf_name" not in st.session_state:
        st.session_state.upload_pdf_name = ""

    # Progress indicator
    steps = ["Upload PDF", "Extract Rules", "Review & Save"]
    current = {"upload": 0, "extracting": 1, "review": 2}.get(st.session_state.upload_step, 0)
    cols = st.columns(len(steps))
    for i, (col, label) in enumerate(zip(cols, steps)):
        if i < current:
            col.markdown(f'<span class="memo-step-badge memo-step-badge-done">✓</span> **{label}**', unsafe_allow_html=True)
        elif i == current:
            col.markdown(f'<span class="memo-step-badge memo-step-badge-active">{i+1}</span> **{label}**', unsafe_allow_html=True)
        else:
            col.markdown(f'<span class="memo-step-badge">{i+1}</span> {label}', unsafe_allow_html=True)

    st.markdown("---")

    # ── STEP 1 – Upload ──
    if st.session_state.upload_step == "upload":
        st.subheader("Step 1: Upload Memorandum PDF")
        uploaded = st.file_uploader("Choose a PDF file", type=["pdf"], key="memo_pdf_uploader")

        if uploaded is not None:
            st.success(f"Uploaded: **{uploaded.name}** ({uploaded.size / 1024:.1f} KB)")

            with st.spinner("Converting PDF to page images…"):
                pdf_bytes = uploaded.read()
                image_paths = _convert_pdf_to_images(pdf_bytes, uploaded.name)
                st.session_state.upload_images = image_paths
                st.session_state.upload_pdf_name = uploaded.name

            st.markdown(f"**{len(image_paths)} page(s) detected.**")

            thumb_cols = st.columns(min(len(image_paths), 5))
            for i, (col, img) in enumerate(zip(thumb_cols, image_paths)):
                col.image(str(img), caption=f"Page {i+1}", use_container_width=True)

            st.markdown("---")
            if st.button("🚀 Extract Rules", type="primary", use_container_width=True):
                st.session_state.upload_step = "extracting"
                st.rerun()

    # ── STEP 2 – Extraction ──
    elif st.session_state.upload_step == "extracting":
        st.subheader("Step 2: Extracting Rules")
        image_paths = st.session_state.upload_images

        if not image_paths:
            st.error("No images found. Please go back and upload a PDF.")
            if st.button("← Back"):
                st.session_state.upload_step = "upload"
                st.rerun()
            return

        progress = st.progress(0, text="Starting extraction pipeline…")

        progress.progress(10, text="Running text OCR…")
        with st.spinner("Running text OCR on all pages…"):
            text_ocr = _run_ocr_text(image_paths)
            st.session_state["upload_text_ocr"] = text_ocr

        progress.progress(40, text="Text OCR complete. Running table OCR…")
        with st.spinner("Running table OCR on all pages…"):
            table_ocr = _run_ocr_table(image_paths)
            st.session_state["upload_table_ocr"] = table_ocr

        progress.progress(70, text="Table OCR complete. Extracting rules…")
        with st.spinner("Rule Extraction Agent is analysing OCR output…"):
            rules = _run_rule_extraction(text_ocr, table_ocr)
            st.session_state.upload_rules = rules

        progress.progress(100, text="Extraction complete!")
        st.session_state.upload_step = "review"
        st.rerun()

    # ── STEP 3 – Review & Save ──
    elif st.session_state.upload_step == "review":
        st.subheader("Step 3: Review Extracted Rules")

        rules = st.session_state.upload_rules
        image_paths = st.session_state.upload_images
        pdf_name = st.session_state.upload_pdf_name

        if rules is None:
            st.error("No extraction results found.")
            if st.button("← Start over"):
                _reset_upload_state()
                st.rerun()
            return

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown('<div class="memo-section-header">📄 Original Memo Pages</div>', unsafe_allow_html=True)
            if image_paths:
                scroll_html = '<div style="max-height:75vh; overflow-y:auto; border:1px solid #e2e8f0; border-radius:8px; padding:8px; background:#f8fafc;">'
                for i, img in enumerate(image_paths):
                    import base64 as _b64
                    img_bytes = Path(img).read_bytes()
                    b64 = _b64.b64encode(img_bytes).decode()
                    scroll_html += (
                        f'<div style="margin-bottom:12px;">'
                        f'<div style="font-size:0.8rem;font-weight:600;color:#475569;margin-bottom:4px;">Page {i+1}</div>'
                        f'<img src="data:image/jpeg;base64,{b64}" style="width:100%;border-radius:4px;"/>'
                        f'</div>'
                    )
                scroll_html += '</div>'
                st.markdown(scroll_html, unsafe_allow_html=True)

        with col_right:
            st.markdown('<div class="memo-section-header">📋 Extracted Rules</div>', unsafe_allow_html=True)
            _render_extracted_rules_upload(rules)

        st.markdown("---")

        # Metadata form
        st.subheader("Save Memorandum")
        fc1, fc2 = st.columns(2)
        with fc1:
            memo_ref = st.text_input("Memo Reference", value=rules.get("memo_reference", ""), key="upload_memo_ref")
            project_name = st.text_input("Project Name", value=rules.get("project_name", ""), key="upload_proj_name")
        with fc2:
            eff = rules.get("effective_period", {})
            start_date = st.text_input("Effective Start Date", value=eff.get("start_date", ""), key="upload_start")
            end_date = st.text_input("Effective End Date", value=eff.get("end_date", ""), key="upload_end")

        st.markdown("---")
        btn1, btn2, btn3 = st.columns([1, 1, 2])

        with btn1:
            if st.button("💾 Save as Pending", type="primary", use_container_width=True, key="upload_save_pending"):
                _save_new_memo(rules, image_paths, pdf_name, memo_ref, project_name, start_date, end_date, "pending")
                st.success("Memo saved as **Pending**!")
                _reset_upload_state()
                st.session_state["memo_sub_view"] = "list"
                st.rerun()

        with btn2:
            if st.button("✅ Save & Approve", use_container_width=True, key="upload_save_approved"):
                _save_new_memo(rules, image_paths, pdf_name, memo_ref, project_name, start_date, end_date, "approved")
                st.success("Memo saved as **Approved**!")
                _reset_upload_state()
                st.session_state["memo_sub_view"] = "list"
                st.rerun()

        with btn3:
            if st.button("🗑️ Discard & Start Over", use_container_width=True, key="upload_discard"):
                _reset_upload_state()
                st.rerun()


# ---------------------------------------------------------------------------
# MEMO PAGE: Review Sub-View (side-by-side comparison)
# ---------------------------------------------------------------------------

def render_memo_review(memo_id: str):
    """Full-screen side-by-side review for a specific memo."""
    memos = _load_memo_store()
    memo = next((m for m in memos if m["memo_id"] == memo_id), None)
    if not memo:
        st.error(f"Memo {memo_id} not found.")
        return

    # Back button
    if st.button("← Back to Memorandums", key="review_back"):
        st.session_state["memo_sub_view"] = "list"
        st.session_state.pop("memo_review_id", None)
        st.rerun()

    # Meta strip
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Reference", memo["memo_reference"])
    mc2.metric("Project", memo["project_name"])
    mc3.metric("Status", memo["status"].upper())
    conf = memo.get("extraction_confidence")
    mc4.metric("Confidence", f"{conf:.0%}" if conf else "—")

    st.markdown("---")

    # Side-by-side
    col_left, col_right = st.columns([1, 1])

    _SCROLL_H = 700  # shared height so both panels match

    with col_left:
        st.markdown('<div class="memo-section-header">📄 Original Memo</div>', unsafe_allow_html=True)
        paths = _get_memo_images(memo.get("image_files", []))
        if paths:
            img_container = st.container(height=_SCROLL_H)
            with img_container:
                for i, p in enumerate(paths):
                    st.caption(f"Page {i+1} of {len(paths)}")
                    st.image(str(p), use_container_width=True)
        else:
            st.warning("No original memo images found.")

    with col_right:
        st.markdown('<div class="memo-section-header">📋 Extracted Rules</div>', unsafe_allow_html=True)
        rules = _load_memo_rules(memo.get("rules_file"))
        rules_container = st.container(height=_SCROLL_H)
        with rules_container:
            _render_memo_rules_panel(rules, memo["memo_id"])

    # Action buttons
    st.markdown("---")
    acol1, acol2, acol3 = st.columns([1, 1, 3])

    with acol1:
        if st.button("✅ Approve Memo", type="primary", disabled=memo["status"] == "approved", key="review_approve"):
            for m in memos:
                if m["memo_id"] == memo["memo_id"]:
                    m["status"] = "approved"
            _save_memo_store(memos)
            st.success("Memo approved.")
            st.rerun()

    with acol2:
        flagged = st.session_state.get(f"flagged_{memo['memo_id']}", set())
        if st.button("❌ Reject Memo", disabled=memo["status"] == "rejected", key="review_reject"):
            note = f"Rejected with {len(flagged)} flagged rule(s): {', '.join(sorted(flagged))}" if flagged else "Rejected by reviewer."
            for m in memos:
                if m["memo_id"] == memo["memo_id"]:
                    m["status"] = "rejected"
                    m["reviewer_notes"] = note
            _save_memo_store(memos)
            st.warning("Memo rejected.")
            st.rerun()


# ---------------------------------------------------------------------------
# MEMO PAGE: List Sub-View (main inbox table)
# ---------------------------------------------------------------------------

def render_memo_list():
    """Main memorandums list with KPIs, filters, and expandable rows."""
    memos = _load_memo_store()

    # KPI cards
    approved = sum(1 for m in memos if m["status"] == "approved")
    pending  = sum(1 for m in memos if m["status"] == "pending")
    rejected = sum(1 for m in memos if m["status"] == "rejected")
    total    = len(memos)

    c1, c2, c3, c4 = st.columns(4)
    for col, val, label, color in [
        (c1, total,    "Total Memos",    "#0f172a"),
        (c2, approved, "Approved",       "#059669"),
        (c3, pending,  "Pending Review", "#d97706"),
        (c4, rejected, "Rejected",       "#dc2626"),
    ]:
        col.markdown(f"""
        <div class="memo-kpi-card">
            <div class="memo-kpi-value" style="color:{color}">{val}</div>
            <div class="memo-kpi-label">{label}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Filter tabs
    filter_tab = st.radio(
        "Filter",
        ["All", "Pending", "Approved", "Rejected"],
        horizontal=True,
        label_visibility="collapsed",
        key="memo_filter_tab",
    )

    if filter_tab != "All":
        filtered = [m for m in memos if m["status"] == filter_tab.lower()]
    else:
        filtered = memos

    if not filtered:
        st.info("No memos match the selected filter.")
        return

    # Table header
    st.markdown(
        '<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr;padding:0.5rem 1.5rem;'
        'color:#94a3b8;font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">'
        '<span>Title</span><span>Submitted By</span><span>Date</span><span>Status</span><span>Action</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Memo rows
    for memo in filtered:
        ref = memo["memo_reference"]
        proj = memo["project_name"]
        badge = _memo_status_badge(memo["status"])
        conf = _memo_confidence_span(memo.get("extraction_confidence"))
        period = f'{memo["effective_period"]["start_date"]} → {memo["effective_period"]["end_date"]}'
        upload_date = memo.get("upload_date", "—")

        rc = memo.get("rule_count") or {}
        total_rules = sum(rc.values()) if rc else 0

        # Row card
        st.markdown(f"""
        <div class="memo-table-row">
            <div>
                <div style="font-weight:600;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{ref}</div>
                <div style="color:#64748b;font-size:0.82rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{proj}</div>
            </div>
            <div style="color:#475569;font-size:0.88rem;">Admin</div>
            <div style="color:#475569;font-size:0.88rem;">{upload_date}</div>
            <div>{badge}</div>
            <div style="font-size:0.82rem;color:#64748b;white-space:nowrap;">
                {total_rules} rules · Conf: {conf}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Expandable detail
        with st.expander(f"View details — {ref}", expanded=False):
            # Meta row
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.markdown(f"**Status:** {badge}", unsafe_allow_html=True)
            mc2.markdown(f"**Period:** {period}")
            mc3.markdown(f"**Confidence:** {conf}", unsafe_allow_html=True)
            mc4.markdown(f"**Rules extracted:** {total_rules}")

            st.markdown(f"**Uploaded:** {upload_date}  ·  **PDF:** `{memo.get('pdf_filename', '—')}`")

            if memo.get("reviewer_notes"):
                st.info(f"📝 Reviewer note: {memo['reviewer_notes']}")

            # Side-by-side comparison
            col_img, col_rules = st.columns([1, 1])
            with col_img:
                st.markdown('<div class="memo-section-header">📄 Original Memo</div>', unsafe_allow_html=True)
                paths = _get_memo_images(memo.get("image_files", []))
                if paths:
                    import base64 as _b64
                    img_container = st.container(height=600)
                    with img_container:
                        for idx, img_path in enumerate(paths):
                            st.caption(f"Page {idx+1} of {len(paths)}")
                            st.image(str(img_path), use_container_width=True)
                else:
                    st.warning("Original memo images not found.")

            with col_rules:
                st.markdown('<div class="memo-section-header">📋 Extracted Rules</div>', unsafe_allow_html=True)
                rules = _load_memo_rules(memo.get("rules_file"))
                if rules:
                    # Scrollable container for rules
                    rules_container = st.container(height=600)
                    with rules_container:
                        _render_memo_rules_summary(rules)
                else:
                    st.info("Rules have not been extracted yet.")

            # Approve / Reject
            if memo["status"] == "pending":
                st.markdown("---")
                st.subheader("Review Actions")
                note = st.text_area("Reviewer notes", key=f"note_{memo['memo_id']}")
                act1, act2, act3, _ = st.columns([1, 1, 1, 2])
                with act1:
                    if st.button("✅ Approve", key=f"approve_{memo['memo_id']}", type="primary"):
                        for m in memos:
                            if m["memo_id"] == memo["memo_id"]:
                                m["status"] = "approved"
                                m["reviewer_notes"] = note
                        _save_memo_store(memos)
                        st.success("Memo approved!")
                        st.rerun()
                with act2:
                    if st.button("❌ Reject", key=f"reject_{memo['memo_id']}"):
                        for m in memos:
                            if m["memo_id"] == memo["memo_id"]:
                                m["status"] = "rejected"
                                m["reviewer_notes"] = note
                        _save_memo_store(memos)
                        st.warning("Memo rejected.")
                        st.rerun()
                with act3:
                    if st.button("🔍 Full Review", key=f"fullreview_{memo['memo_id']}"):
                        st.session_state["memo_sub_view"] = "review"
                        st.session_state["memo_review_id"] = memo["memo_id"]
                        st.rerun()

            if memo["status"] in ("approved", "rejected"):
                st.markdown("---")
                rev1, rev2, _ = st.columns([1, 1, 3])
                with rev1:
                    if st.button("🔄 Move to Pending", key=f"reopen_{memo['memo_id']}"):
                        for m in memos:
                            if m["memo_id"] == memo["memo_id"]:
                                m["status"] = "pending"
                        _save_memo_store(memos)
                        st.rerun()
                with rev2:
                    if st.button("🔍 Full Review", key=f"fullreview2_{memo['memo_id']}"):
                        st.session_state["memo_sub_view"] = "review"
                        st.session_state["memo_review_id"] = memo["memo_id"]
                        st.rerun()


# ---------------------------------------------------------------------------
# MEMORANDUMS PAGE (Router)
# ---------------------------------------------------------------------------

def render_memorandums_page():
    """Top-level Memorandums page with sub-view routing."""
    st.markdown(MEMO_CSS, unsafe_allow_html=True)

    # Determine sub-view
    sub_view = st.session_state.get("memo_sub_view", "list")

    if sub_view == "upload":
        # Header
        st.markdown("""
        <div class="page-header-wrap">
            <div class="page-header-title">📤 Add New Memorandum</div>
            <div class="page-header-subtitle">Upload a memo PDF to extract commission rules automatically</div>
        </div>
        """, unsafe_allow_html=True)
        render_memo_upload()

    elif sub_view == "review":
        memo_id = st.session_state.get("memo_review_id")
        if memo_id:
            st.markdown("""
            <div class="page-header-wrap">
                <div class="page-header-title">🔍 Memorandum Review</div>
                <div class="page-header-subtitle">Review extracted rules and approve or reject this memorandum</div>
            </div>
            """, unsafe_allow_html=True)
            render_memo_review(memo_id)
        else:
            st.session_state["memo_sub_view"] = "list"
            st.rerun()

    else:
        # Default: list view
        # Header with "New Memorandum" button
        col_title, col_btn = st.columns([4, 1])
        with col_title:
            st.markdown("""
            <div class="page-header-wrap">
                <div class="page-header-title">📋 Memorandums</div>
                <div class="page-header-subtitle">
                    Manage uploaded memorandums — review extracted rules, approve or reject
                </div>
                <div class="page-header-badge">📝 Document Pipeline</div>
            </div>
            """, unsafe_allow_html=True)
        with col_btn:
            if st.button("➕  New Memorandum", type="primary", use_container_width=True, key="new_memo_btn"):
                st.session_state["memo_sub_view"] = "upload"
                st.rerun()

        render_memo_list()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def render_dashboard():
    """Original Commission Management dashboard (untouched logic)."""

    # ---- Header ----
    st.markdown("""
    <div class="page-header-wrap">
        <div style="display:flex; align-items:center; justify-content:space-between;">
            <div>
                <div class="page-header-title">📊 Commission Management</div>
                <div class="page-header-subtitle">
                    Overview of agent commissions, payment tracking &amp; performance analytics &mdash; Aetas Seputeh
                </div>
                <div class="page-header-badge">✨ Avaland Property Group</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ---- Load demo data ----
    try:
        metadata, all_agents = load_demo_data()
    except FileNotFoundError:
        st.error(f"Demo data file not found at `{DEMO_DATA_PATH}`. Please ensure the file exists.")
        return
    except json.JSONDecodeError as e:
        st.error(f"Error parsing demo data JSON: {e}")
        return

    # ---- Filter bar ----
    filters = render_filter_bar(metadata)

    # ---- Apply filters / cache ----
    if "mgmt_agents" not in st.session_state or filters["run_clicked"]:
        agents = all_agents[:]
        if filters["project"]:
            agents = [a for a in agents if a.project == filters["project"]]
        st.session_state["mgmt_agents"] = agents
        st.session_state["mgmt_scheme"] = filters["scheme"]
        st.session_state["mgmt_calculated"] = True

    if not st.session_state.get("mgmt_calculated"):
        st.info("👆 Select your filters and click **Run Calculation** to begin.")
        return

    agents: List[Agent] = st.session_state["mgmt_agents"]
    scheme: str = st.session_state["mgmt_scheme"]

    # ---- Summary Metrics ----
    st.markdown("<br>", unsafe_allow_html=True)
    render_summary_metrics(agents)

    # ---- Tabs ----
    tab_breakdown, tab_entitlement, tab_teams, tab_analytics = st.tabs([
        "📋 Commission Breakdown",
        "💳 Entitlement Tracking",
        "👥 Team Overview",
        "📈 Analytics",
    ])

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 1 – Commission Breakdown (main view)
    # ═══════════════════════════════════════════════════════════════════════
    with tab_breakdown:
        # Section header + Add Entry + Export
        col_h, col_add, col_e = st.columns([4, 1, 1])
        with col_h:
            st.markdown("""
            <div class="section-header">
                <div>
                    <div class="section-title">Commission Breakdown</div>
                    <div class="section-subtitle">Click on a row to see detailed calculation with rule traceability</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        with col_add:
            # Load raw agents data from JSON for the dialog's agent dropdown
            try:
                with open(DEMO_DATA_PATH, "r", encoding="utf-8") as _f:
                    _raw = json.load(_f)
                _agents_data = _raw.get("agents", [])
            except Exception:
                _agents_data = []

            if st.button("➕  Add Entry", use_container_width=True):
                add_entry_dialog(_agents_data)
        with col_e:
            csv_data = export_csv(agents)
            st.download_button(
                label="⬇  Export CSV",
                data=csv_data,
                file_name=f"commission_report_{filters['period'].replace(' ', '_')}.csv",
                mime="text/csv",
                width="stretch",
            )

        # Agent rows with expandable detail
        for agent in agents:
            render_agent_row(agent)

            with st.expander(f"View details for {agent.name}", expanded=False):
                detail_tab1, detail_tab2 = st.tabs([
                    "💰 Per-Unit Commission & Rebate",
                    "📋 Summary Table",
                ])

                with detail_tab1:
                    render_agent_breakdown(agent, scheme)

                with detail_tab2:
                    render_agent_unit_details(agent)

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 2 – Entitlement Tracking
    # ═══════════════════════════════════════════════════════════════════════
    with tab_entitlement:
        # --- section header + quick stats ---
        num_fully = sum(1 for a in agents if a.status == "Paid")
        num_partial = sum(1 for a in agents if a.status == "Partial")
        num_pending = sum(1 for a in agents if a.status == "Pending")

        st.markdown(
            '<div class="section-header">'
            '<div>'
            '<div class="section-title">Commission Entitlement Tracking</div>'
            '<div class="section-subtitle">Track entitlements, claims, balances, and partial payouts for all sellers</div>'
            '</div>'
            '<div style="display:flex;gap:0.75rem;align-items:center;">'
            '<span style="background:#d1fae5;color:#059669;padding:0.3rem 0.75rem;border-radius:8px;font-size:0.78rem;font-weight:600;">' + str(num_fully) + ' Paid</span>'
            '<span style="background:#e0e7ff;color:#4338ca;padding:0.3rem 0.75rem;border-radius:8px;font-size:0.78rem;font-weight:600;">' + str(num_partial) + ' Partial</span>'
            '<span style="background:#fef3c7;color:#d97706;padding:0.3rem 0.75rem;border-radius:8px;font-size:0.78rem;font-weight:600;">' + str(num_pending) + ' Pending</span>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        # ---- Entitlement Summary Metrics ----
        render_entitlement_metrics(agents)

        st.markdown("<br>", unsafe_allow_html=True)

        # ---- Search & Filter bar ----
        ent_col1, ent_col2, ent_col3 = st.columns([3, 2, 2])
        with ent_col1:
            ent_search = st.text_input(
                "🔍 Search sellers, projects...",
                key="ent_search",
                placeholder="Search sellers, projects...",
                label_visibility="collapsed",
            )
        with ent_col2:
            ent_status = st.selectbox(
                "Status",
                ["All Status", "Fully Paid", "Partial", "Pending"],
                key="ent_status",
                label_visibility="collapsed",
            )
        with ent_col3:
            ent_project = st.selectbox(
                "Project",
                ["All Projects", metadata["project"]],
                key="ent_project",
                label_visibility="collapsed",
            )

        # ---- Filter agents ----
        ent_agents = agents[:]
        if ent_search:
            q = ent_search.lower()
            ent_agents = [a for a in ent_agents if q in a.name.lower() or q in a.project.lower() or q in a.team.lower()]
        if ent_status != "All Status":
            status_map = {"Fully Paid": "Paid", "Partial": "Partial", "Pending": "Pending"}
            ent_agents = [a for a in ent_agents if a.status == status_map.get(ent_status, ent_status)]
        if ent_project != "All Projects":
            ent_agents = [a for a in ent_agents if a.project == ent_project]

        st.markdown("<br>", unsafe_allow_html=True)

        # ---- Agent rows with expandable detail ----
        if not ent_agents:
            st.info("No agents match the current filters.")
        else:
            for agent in ent_agents:
                render_entitlement_agent_row(agent)
                with st.expander(f"View payment details for {agent.name}", expanded=False):
                    render_entitlement_detail(agent)

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 3 – Team Overview
    # ═══════════════════════════════════════════════════════════════════════
    with tab_teams:
        render_team_overview(agents)

    # ═══════════════════════════════════════════════════════════════════════
    # TAB 4 – Analytics
    # ═══════════════════════════════════════════════════════════════════════
    with tab_analytics:
        render_performance_charts(agents)


# ---------------------------------------------------------------------------
# EXTRACTED RULES PAGE (wraps render_memo_library with header)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# RULE-ORIENTED EXTRACTED RULES PAGE  (replaces old memo-oriented view)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# PROJECT DASHBOARD  (POC with mock data)
# ---------------------------------------------------------------------------
import random as _rng
import hashlib as _hl
from datetime import date as _date, timedelta as _td


def _generate_mock_projects() -> list[dict]:
    """Generate deterministic mock project data for the POC dashboard."""
    if "mock_projects" in st.session_state:
        return st.session_state["mock_projects"]

    _rng.seed(42)  # deterministic

    _PROJECT_NAMES = [
        "Aetas Seputeh", "Legasi Kampung Bharu", "Serai Bukit Bandaraya",
        "Adora Trails Alam Impian", "Kalista Park Homes", "Astrea Mont Kiara",
        "Elysium Damansara", "Verdana Prestige Cyberjaya",
    ]
    _AGENT_NAMES = [
        "Ahmad Faizal", "Tan Wei Ling", "Rajesh Kumar", "Nurul Aisyah",
        "David Lim", "Siti Aminah", "Jason Ong", "Priya Nair",
        "Wong Kah Mun", "Mohamed Hafiz", "Lee Sook Yin", "Ravi Chandran",
        "Farah Nabila", "Kevin Yeoh", "Amirah Zulkifli",
    ]
    _MEMO_TEMPLATES = [
        "Commission Structure {q}",
        "Sales Package & Rebate Scheme {q}",
        "REA Commission & Referral {q}",
        "Special Agent Bonus Program {q}",
        "Price Adjustment & Package {q}",
        "Early Bird Incentive {q}",
    ]
    _STATUSES = ["Active", "Active", "Active", "Completed", "Upcoming"]

    projects: list[dict] = []
    real_memos = _load_memo_store()
    real_approved = [m for m in real_memos if m.get("status") == "approved"]

    for i, pname in enumerate(_PROJECT_NAMES):
        pid = f"PRJ-{i+1:03d}"
        status = _STATUSES[i % len(_STATUSES)]
        start = _date(2025, 1 + (i * 2) % 12, 1)
        end = start + _td(days=_rng.randint(150, 365))

        # Memos
        n_memos = _rng.randint(3, 6)
        memos = []
        total_rules = 0
        for mi in range(n_memos):
            q = f"Q{(mi % 4) + 1} {start.year + mi // 4}"
            n_rules = _rng.randint(8, 22)
            total_rules += n_rules
            memo_date = start + _td(days=mi * _rng.randint(25, 60))
            memos.append({
                "name": _rng.choice(_MEMO_TEMPLATES).format(q=q),
                "effective_date": memo_date.isoformat(),
                "rules": n_rules,
                "status": _rng.choice(["approved", "approved", "approved", "pending"]),
            })

        # Agents for this project
        n_agents = _rng.randint(8, 25)
        agents_pool = _rng.sample(_AGENT_NAMES, min(n_agents, len(_AGENT_NAMES)))
        while len(agents_pool) < n_agents:
            agents_pool.append(f"Agent-{_rng.randint(100,999)}")

        # Sales & commission
        total_sales = _rng.randint(800_000, 8_000_000)
        total_units = _rng.randint(40, 600)
        avg_rate = round(_rng.uniform(2.5, 12.0), 1)
        total_commission = int(total_sales * avg_rate / 100)
        target_sales = int(total_sales * _rng.uniform(0.8, 1.4))

        # Agent breakdown
        agent_sales = []
        remaining = total_sales
        for ai, aname in enumerate(agents_pool):
            if ai == len(agents_pool) - 1:
                a_sales = remaining
            else:
                a_sales = int(remaining * _rng.uniform(0.05, 0.25))
                remaining -= a_sales
            a_comm = int(a_sales * avg_rate / 100)
            a_units = max(1, int(total_units * a_sales / max(total_sales, 1)))
            agent_sales.append({"name": aname, "sales": a_sales, "commission": a_comm, "units": a_units})
        agent_sales.sort(key=lambda x: x["sales"], reverse=True)

        # Monthly sales (last 6 months)
        monthly = []
        for mi in range(6):
            m_date = _date(2025, 7 + mi, 1) if 7 + mi <= 12 else _date(2026, (7 + mi) - 12, 1)
            m_sales = int(total_sales / 6 * _rng.uniform(0.6, 1.5))
            monthly.append({"month": m_date.strftime("%b %Y"), "sales": m_sales})

        # Health indicator
        ratio = total_sales / max(target_sales, 1)
        if ratio >= 0.9:
            health = "green"
        elif ratio >= 0.65:
            health = "yellow"
        else:
            health = "red"

        efficiency = round(total_sales / max(total_commission, 1), 1)

        projects.append({
            "project_id": pid,
            "project_name": pname,
            "status": status,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "description": f"Sales commission program for {pname}",
            "memos": memos,
            "n_memos": n_memos,
            "total_rules": total_rules,
            "n_agents": n_agents,
            "agents": agent_sales,
            "total_sales": total_sales,
            "total_units": total_units,
            "total_commission": total_commission,
            "avg_rate": avg_rate,
            "target_sales": target_sales,
            "monthly_sales": monthly,
            "health": health,
            "efficiency": efficiency,
        })

    # Merge real memo data into first project
    if real_approved and projects:
        p0 = projects[0]
        for rm in real_approved:
            rc = rm.get("rule_count") or {}
            p0["memos"].insert(0, {
                "name": rm.get("memo_reference", "Real Memo"),
                "effective_date": rm.get("upload_date", ""),
                "rules": sum(rc.values()) if rc else 0,
                "status": rm.get("status", "approved"),
            })
            p0["n_memos"] = len(p0["memos"])
            p0["total_rules"] += sum(rc.values()) if rc else 0

    st.session_state["mock_projects"] = projects
    return projects


def _health_icon(h: str) -> str:
    return {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(h, "⚪")


def _health_label(h: str) -> str:
    return {"green": "Performing Well", "yellow": "Moderate", "red": "Underperforming"}.get(h, "Unknown")


def _prj_status_cls(s: str) -> str:
    return {"Active": "prj-status-active", "Completed": "prj-status-completed", "Upcoming": "prj-status-upcoming"}.get(s, "prj-status-active")


def _fmt_rm(v: int | float) -> str:
    return f"RM {v:,.0f}"


def render_projects_page():
    """Project Overview Dashboard with mock data."""
    st.markdown(MEMO_CSS, unsafe_allow_html=True)

    projects = _generate_mock_projects()

    # == HEADER ==
    hc1, hc2 = st.columns([3, 1])
    with hc1:
        st.markdown("""
        <div class="page-header-wrap">
            <div class="page-header-title">📊 Projects</div>
            <div class="page-header-subtitle">Overview of sales programs, memos, and commission performance</div>
            <div class="page-header-badge">🏢 Property Portfolio</div>
        </div>
        """, unsafe_allow_html=True)
    with hc2:
        st.markdown("""
        <style>
        /* Right-align the New Project button */
        [data-testid="stHorizontalBlock"]:first-child [data-testid="stColumn"]:last-child [data-testid="stElementContainer"]:has(button) {
            display: flex;
            justify-content: flex-end;
        }
        </style>
        <div style='padding-top:0.6rem;'></div>
        """, unsafe_allow_html=True)
        add_btn = st.button("➕ New Project", type="primary", key="prj_add_btn")

    # ── New Project form ──
    if add_btn:
        st.session_state["prj_show_form"] = True

    if st.session_state.get("prj_show_form", False):
        st.markdown("---")
        st.markdown("### Create New Project")
        with st.form("new_project_form", clear_on_submit=True):
            fc1, fc2 = st.columns(2)
            with fc1:
                new_name = st.text_input("Project Name *")
                new_desc = st.text_area("Description", height=80)
                new_status = st.selectbox("Status", ["Active", "Upcoming", "Completed"])
            with fc2:
                new_start = st.date_input("Start Date", value=_date.today())
                new_end = st.date_input("End Date", value=_date.today() + _td(days=180))
                new_target = st.number_input("Target Sales (RM)", min_value=0, value=1_000_000, step=100_000)
            submitted = st.form_submit_button("🚀 Create Project", type="primary")
            cancel = st.form_submit_button("Cancel")
            if submitted and new_name:
                # Generate a new mock project
                _rng.seed(None)  # random for new projects
                pid = f"PRJ-{len(projects)+1:03d}"
                n_agents = _rng.randint(5, 15)
                projects.append({
                    "project_id": pid,
                    "project_name": new_name,
                    "status": new_status,
                    "start_date": new_start.isoformat(),
                    "end_date": new_end.isoformat(),
                    "description": new_desc or f"Sales commission program for {new_name}",
                    "memos": [
                        {"name": f"Initial Commission Structure Q1 {new_start.year}", "effective_date": new_start.isoformat(), "rules": _rng.randint(8, 16), "status": "approved"},
                        {"name": f"Sales Package & Rebate {new_start.year}", "effective_date": (new_start + _td(days=30)).isoformat(), "rules": _rng.randint(6, 12), "status": "pending"},
                    ],
                    "n_memos": 2,
                    "total_rules": 0,
                    "n_agents": n_agents,
                    "agents": [{"name": f"Agent-{_rng.randint(100,999)}", "sales": _rng.randint(50000, 300000), "commission": _rng.randint(2000, 30000), "units": _rng.randint(2, 30)} for _ in range(min(5, n_agents))],
                    "total_sales": int(new_target * _rng.uniform(0.1, 0.4)),
                    "total_units": _rng.randint(10, 80),
                    "total_commission": 0,
                    "avg_rate": round(_rng.uniform(3, 8), 1),
                    "target_sales": new_target,
                    "monthly_sales": [{"month": "Jan 2026", "sales": _rng.randint(50000, 300000)}],
                    "health": "yellow",
                    "efficiency": 0,
                })
                projects[-1]["total_rules"] = sum(m["rules"] for m in projects[-1]["memos"])
                projects[-1]["total_commission"] = int(projects[-1]["total_sales"] * projects[-1]["avg_rate"] / 100)
                projects[-1]["efficiency"] = round(projects[-1]["total_sales"] / max(projects[-1]["total_commission"], 1), 1)
                st.session_state["mock_projects"] = projects
                st.session_state["prj_show_form"] = False
                st.rerun()
            if cancel:
                st.session_state["prj_show_form"] = False
                st.rerun()

    # == GLOBAL KPIs ==
    st.markdown("<div style='margin-top:0.75rem;'></div>", unsafe_allow_html=True)
    tot_projects = len(projects)
    tot_memos = sum(p["n_memos"] for p in projects)
    tot_sales = sum(p["total_sales"] for p in projects)
    tot_comm = sum(p["total_commission"] for p in projects)
    tot_agents = sum(p["n_agents"] for p in projects)

    k1, k2, k3, k4, k5 = st.columns(5)
    for col, label, val, color in [
        (k1, "Total Projects", str(tot_projects), "#0f172a"),
        (k2, "Active Memos", str(tot_memos), "#2563eb"),
        (k3, "Total Sales", _fmt_rm(tot_sales), "#16a34a"),
        (k4, "Total Commission", _fmt_rm(tot_comm), "#d97706"),
        (k5, "Active Agents", str(tot_agents), "#7c3aed"),
    ]:
        col.markdown(f"""
        <div class="memo-kpi-card">
            <div class="memo-kpi-value" style="color:{color};">{val}</div>
            <div class="memo-kpi-label">{label}</div>
        </div>
        """, unsafe_allow_html=True)

    # == FILTERS ==
    st.markdown("---")
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    with f1:
        search_q = st.text_input("🔍 Search Projects", placeholder="Project name or ID…", key="prj_search")
    with f2:
        filt_status = st.selectbox("Status", ["All", "Active", "Completed", "Upcoming"], key="prj_filt_status")
    with f3:
        sort_by = st.selectbox("Sort by", ["Name", "Sales ↓", "Commission ↓", "Agents ↓", "Health"], key="prj_sort")
    with f4:
        filt_health = st.selectbox("Health", ["All", "🟢 Performing", "🟡 Moderate", "🔴 Underperforming"], key="prj_filt_health")

    filtered = list(projects)
    if search_q:
        q = search_q.lower()
        filtered = [p for p in filtered if q in p["project_name"].lower() or q in p["project_id"].lower()]
    if filt_status != "All":
        filtered = [p for p in filtered if p["status"] == filt_status]
    if filt_health != "All":
        h_map = {"🟢 Performing": "green", "🟡 Moderate": "yellow", "🔴 Underperforming": "red"}
        filtered = [p for p in filtered if p["health"] == h_map.get(filt_health, "")]

    if sort_by == "Sales ↓":
        filtered.sort(key=lambda p: p["total_sales"], reverse=True)
    elif sort_by == "Commission ↓":
        filtered.sort(key=lambda p: p["total_commission"], reverse=True)
    elif sort_by == "Agents ↓":
        filtered.sort(key=lambda p: p["n_agents"], reverse=True)
    elif sort_by == "Health":
        order = {"red": 0, "yellow": 1, "green": 2}
        filtered.sort(key=lambda p: order.get(p["health"], 1))
    else:
        filtered.sort(key=lambda p: p["project_name"])

    st.markdown(f"<div style='color:#64748b;font-size:0.85rem;margin-bottom:0.75rem;'>Showing <strong>{len(filtered)}</strong> of {len(projects)} projects</div>", unsafe_allow_html=True)

    # == PROJECT CARDS ==
    if not filtered:
        st.info("No projects match the current filters.")
        return

    for pi, p in enumerate(filtered):
        pid = p["project_id"]
        pname = p["project_name"]
        status = p["status"]
        health = p["health"]

        # Build efficiency display with color
        eff_val = p['efficiency']
        eff_color = '#16A34A' if eff_val >= 15 else ('#D97706' if eff_val >= 8 else '#DC2626')

        st.markdown(f"""
        <div class="prj-card">
            <div class="prj-card-header">
                <div>
                    <div class="prj-name">{pname}</div>
                    <div class="prj-id">{pid} · {p['start_date']} → {p['end_date']}</div>
                </div>
                <div style="display:flex;align-items:center;gap:0.5rem;">
                    <span class="prj-health-{health}" style="font-size:0.78rem;font-weight:600;">{_health_icon(health)} {_health_label(health)}</span>
                    <span class="{_prj_status_cls(status)}">{status}</span>
                </div>
            </div>
            <div class="prj-metrics">
                <div class="prj-metric">
                    <div class="prj-metric-label">Memos</div>
                    <div class="prj-metric-value">{p['n_memos']}</div>
                </div>
                <div class="prj-metric">
                    <div class="prj-metric-label">Active Rules</div>
                    <div class="prj-metric-value">{p['total_rules']}</div>
                </div>
                <div class="prj-metric">
                    <div class="prj-metric-label">Total Sales</div>
                    <div class="prj-metric-value">{_fmt_rm(p['total_sales'])}</div>
                </div>
                <div class="prj-metric">
                    <div class="prj-metric-label">Units Sold</div>
                    <div class="prj-metric-value">{p['total_units']:,}</div>
                </div>
                <div class="prj-metric">
                    <div class="prj-metric-label">Commission Paid</div>
                    <div class="prj-metric-value">{_fmt_rm(p['total_commission'])}</div>
                </div>
                <div class="prj-metric">
                    <div class="prj-metric-label">Avg Rate</div>
                    <div class="prj-metric-value">{p['avg_rate']}%</div>
                </div>
                <div class="prj-metric">
                    <div class="prj-metric-label">Agents</div>
                    <div class="prj-metric-value">{p['n_agents']}</div>
                </div>
                <div class="prj-metric">
                    <div class="prj-metric-label">Efficiency</div>
                    <div class="prj-metric-value" style="color:{eff_color}">{eff_val}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Expandable Details ──
        with st.expander(f"View Details — {pname}", expanded=False):
            # -- Quick Actions --
            ac1, ac2, ac3, ac4 = st.columns(4)
            with ac1:
                if st.button("📝 View Memos", key=f"prj_memos_{pi}"):
                    st.session_state["nav_page"] = "📝  Memorandums"
                    st.rerun()
            with ac2:
                if st.button("📖 View Rules", key=f"prj_rules_{pi}"):
                    st.session_state["nav_page"] = "📚  Extracted Rules"
                    st.rerun()
            with ac3:
                if st.button("💰 Analyze Commission", key=f"prj_comm_{pi}"):
                    st.session_state["nav_page"] = "💰  Agent Commissions"
                    st.rerun()
            with ac4:
                st.markdown(f"<div style='padding-top:0.4rem;font-size:0.82rem;color:#64748b;'>Target: {_fmt_rm(p['target_sales'])}</div>", unsafe_allow_html=True)

            # -- Memo List --
            st.markdown("#### 📝 Memo List")
            memo_rows = []
            for m in p["memos"]:
                s_badge = "🟢" if m["status"] == "approved" else "🟡"
                memo_rows.append({
                    "Memo": m["name"],
                    "Effective Date": m["effective_date"],
                    "Rules": m["rules"],
                    "Status": f"{s_badge} {m['status'].title()}",
                })
            st.table(memo_rows)

            # -- Sales Performance --
            det1, det2 = st.columns(2)

            with det1:
                st.markdown("#### 📈 Monthly Sales")
                chart_data = {m["month"]: m["sales"] for m in p["monthly_sales"]}
                st.bar_chart(chart_data, height=220)

            with det2:
                st.markdown("#### 🏆 Top 5 Agents by Sales")
                top5 = p["agents"][:5]
                agent_rows = []
                for rank, a in enumerate(top5, 1):
                    agent_rows.append({
                        "#": rank,
                        "Agent": a["name"],
                        "Sales": _fmt_rm(a["sales"]),
                        "Commission": _fmt_rm(a["commission"]),
                        "Units": a["units"],
                    })
                st.table(agent_rows)

            # -- Commission Distribution --
            st.markdown("#### 📊 Commission Summary")
            cs1, cs2, cs3, cs4 = st.columns(4)
            cs1.metric("Total Commission", _fmt_rm(p["total_commission"]))
            cs2.metric("Average Rate", f"{p['avg_rate']}%")
            highest_comm = max((a["commission"] for a in p["agents"]), default=0)
            cs3.metric("Highest Agent Commission", _fmt_rm(highest_comm))
            cs4.metric("Efficiency Score", p["efficiency"])



def _aggregate_all_rules() -> list[dict]:
    """Load all memos from memo_store and flatten every rule into a single list.

    Each item is a dict with:
        rule_id, rule_name, rule_type, category_key, conditions, notes,
        memo_id, memo_reference, project_name, effective_period,
        extraction_confidence, memo_status, image_files, rate_value,
        rate_type, calculation_method, status (Active/Flagged/Invalid)
    """
    memos = _load_memo_store()
    all_rules: list[dict] = []
    flagged_store = st.session_state.get("flagged_rules", {})

    for memo in memos:
        # Only include rules from approved memos
        if memo.get("status") != "approved":
            continue
        rules_data = _load_memo_rules(memo.get("rules_file"))
        if not rules_data or "rules" not in rules_data:
            continue

        for cat_key, (icon, cat_title) in _MEMO_SECTION_META.items():
            items = rules_data["rules"].get(cat_key, [])
            for rule in items:
                rid = rule.get("rule_id", "")

                # Determine rate value / type
                rate_val = ""
                rate_type = "Conditional"
                calc_method = ""
                conds = rule.get("conditions", [])
                if conds and isinstance(conds[0], dict):
                    first = conds[0]
                    for pct_key in ("commission_percentage", "rebate_percentage"):
                        if pct_key in first:
                            rate_val = f"{first[pct_key]}%"
                            rate_type = "Percentage"
                            break
                    if not rate_val and "adjustment_amount" in first:
                        try:
                            rate_val = f"RM {float(first['adjustment_amount']):,.0f}"
                        except (ValueError, TypeError):
                            rate_val = str(first['adjustment_amount'])
                        rate_type = "Fixed"
                    calc_method = first.get("description", "")
                elif conds and isinstance(conds[0], str):
                    calc_method = conds[0] if conds else ""

                # Referral rules special handling
                if "reward_amount" in rule:
                    try:
                        amt = float(rule["reward_amount"])
                    except (ValueError, TypeError):
                        amt = 0
                    rtype = rule.get("reward_type", "fixed")
                    rate_type = rtype.title()
                    rate_val = f"RM {amt:,.0f}" if rtype == "fixed" else f"{amt}%"
                    calc_method = rule.get("referrer_category", "").replace("_", " ").title()

                # Package rules special handling
                if "value" in rule and cat_key == "package_rules":
                    rate_val = str(rule["value"])
                    rate_type = "Package"
                    calc_method = rule.get("package_type", "").replace("_", " ").title()

                # Multi-tier detection
                if conds and isinstance(conds[0], dict) and len(conds) > 1:
                    rate_type = "Tiered"
                    vals = []
                    for c in conds:
                        for k in ("commission_percentage", "rebate_percentage", "adjustment_amount"):
                            if k in c:
                                vals.append(str(c[k]))
                    if vals:
                        try:
                            fvals = [float(v) for v in vals]
                            rate_val = f"{min(fvals)}–{max(fvals)}"
                            if any("percentage" in str(c) for c in conds):
                                rate_val += "%"
                        except (ValueError, TypeError):
                            rate_val = " / ".join(vals)

                # Determine status
                flag_info = flagged_store.get(rid)
                if flag_info:
                    status = "Flagged"
                else:
                    status = "Active"

                all_rules.append({
                    "rule_id": rid,
                    "rule_name": rule.get("rule_name", "Untitled"),
                    "rule_type": cat_title.replace(" Rules", "").replace(" Adjustments", " Adj."),
                    "category_key": cat_key,
                    "icon": icon,
                    "conditions": conds,
                    "notes": rule.get("notes", []),
                    "raw_rule": rule,
                    # Memo context
                    "memo_id": memo["memo_id"],
                    "memo_reference": memo.get("memo_reference", ""),
                    "project_name": memo.get("project_name", ""),
                    "effective_period": memo.get("effective_period", {}),
                    "extraction_confidence": memo.get("extraction_confidence") or rules_data.get("extraction_confidence"),
                    "memo_status": memo.get("status", ""),
                    "image_files": memo.get("image_files", []),
                    # Computed
                    "rate_value": rate_val,
                    "rate_type": rate_type,
                    "calculation_method": calc_method,
                    "status": status,
                })

    return all_rules


def _validate_rule(rule: dict) -> list[dict]:
    """Run validation checks on a single rule.  Returns list of {level, message}."""
    issues: list[dict] = []
    conds = rule.get("conditions", [])

    # Missing fields
    if not rule.get("rule_name"):
        issues.append({"level": "error", "message": "Missing rule name"})
    if not rule.get("rule_id"):
        issues.append({"level": "error", "message": "Missing rule ID"})
    if not conds:
        issues.append({"level": "warning", "message": "No conditions defined"})

    # Rate value check
    if not rule.get("rate_value"):
        issues.append({"level": "warning", "message": "Rate value could not be determined"})

    # Condition quality
    if conds and isinstance(conds[0], dict):
        for c in conds:
            cond_str = c.get("condition", "")
            if not cond_str:
                issues.append({"level": "error", "message": "Empty condition expression"})
            if "_ _" in cond_str or "__" in cond_str:
                issues.append({"level": "warning", "message": f"Possible OCR artefact in condition: {cond_str[:60]}"})

    # Extraction confidence
    conf = rule.get("extraction_confidence")
    if conf is not None:
        if conf < 0.6:
            issues.append({"level": "error", "message": f"Low extraction confidence ({conf:.0%})"})
        elif conf < 0.8:
            issues.append({"level": "warning", "message": f"Moderate extraction confidence ({conf:.0%})"})

    # Effective period
    ep = rule.get("effective_period", {})
    if not ep.get("start_date") or not ep.get("end_date"):
        issues.append({"level": "warning", "message": "Effective period incomplete"})

    if not issues:
        issues.append({"level": "success", "message": "All checks passed — rule is valid"})

    return issues


def _render_rule_card(rule: dict, idx: int):
    """Render a single rule as a styled card with expandable details."""
    rid = rule["rule_id"]
    rname = rule["rule_name"]
    rtype = rule["rule_type"]
    icon = rule["icon"]
    status = rule["status"]
    memo_ref = rule["memo_reference"]
    project = rule["project_name"]
    rate_val = rule["rate_value"] or "—"
    rate_type = rule["rate_type"]
    calc_method = rule["calculation_method"] or "—"
    conf = rule.get("extraction_confidence")

    # Status badge
    badge_cls = {"Active": "rule-badge-active", "Flagged": "rule-badge-flagged", "Invalid": "rule-badge-invalid"}.get(status, "rule-badge-active")
    card_extra = " rule-card-flagged" if status == "Flagged" else (" rule-card-invalid" if status == "Invalid" else "")

    # Validation status badge
    v_status = st.session_state.get("rule_validation_status", {}).get(rid, "Pending")
    v_badge_cls = {"Validated": "vbadge-validated", "Not Validated": "vbadge-not-validated", "Pending": "vbadge-pending"}.get(v_status, "vbadge-pending")
    v_icon = {"Validated": "✓", "Not Validated": "✗", "Pending": "◌"}.get(v_status, "◌")

    # Confidence color
    conf_pct = int((conf or 0) * 100)
    conf_color = "#059669" if conf_pct >= 80 else ("#d97706" if conf_pct >= 60 else "#dc2626")

    # Card header HTML
    st.markdown(f"""
    <div class="rule-card{card_extra}">
        <div class="rule-card-header">
            <div style="display:flex;align-items:center;">
                <div class="rule-card-icon">{icon}</div>
                <div>
                    <div class="rule-card-title">{rname}</div>
                    <div class="rule-card-subtitle">{rid} · from {memo_ref}</div>
                </div>
            </div>
            <div style="display:flex;align-items:center;gap:0.3rem;">
                <span class="{v_badge_cls}">{v_icon} {v_status}</span>
                <span class="{badge_cls}">{status}</span>
            </div>
        </div>
        <div style="display:flex; gap:0.75rem; flex-wrap:wrap;">
            <div class="rule-info-block">
                <div class="rule-info-label">Calculation Method</div>
                <div class="rule-info-value">{calc_method}</div>
            </div>
            <div class="rule-info-block">
                <div class="rule-info-label">Rate Type</div>
                <div class="rule-info-value"><span style="background:#e0f2fe;color:#0369a1;padding:0.15rem 0.5rem;border-radius:12px;font-size:0.78rem;font-weight:600;">{rate_type}</span></div>
            </div>
            <div class="rule-info-block">
                <div class="rule-info-label">Rate Value</div>
                <div class="rule-info-value">{rate_val}</div>
            </div>
            <div class="rule-info-block">
                <div class="rule-info-label">Category</div>
                <div class="rule-info-value">{rtype}</div>
            </div>
        </div>
        <div style="margin-top:0.5rem;display:flex;align-items:center;gap:0.5rem;">
            <span style="font-size:0.75rem;color:#64748b;">Extraction confidence: {conf_pct}%</span>
            <div class="rule-confidence-bar" style="flex:1;max-width:200px;">
                <div class="rule-confidence-fill" style="width:{conf_pct}%;background:{conf_color};"></div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Expandable details
    with st.expander(f"📋 Details — {rid}", expanded=False):
        # ---- Conditions ----
        st.markdown("**Rule Conditions**")
        conds = rule["conditions"]
        if conds and isinstance(conds[0], dict):
            rows = []
            for c in conds:
                val = c.get("commission_percentage",
                      c.get("rebate_percentage",
                      c.get("adjustment_amount", "")))
                rows.append({
                    "Condition": c.get("condition", ""),
                    "Value": str(val),
                    "Description": c.get("description", ""),
                })
            st.table(rows)
        elif conds:
            for c in conds:
                st.markdown(f"- {c}")
        else:
            st.info("No conditions defined.")

        # Notes
        notes = rule.get("notes", [])
        if notes:
            st.markdown("**Notes:** " + " · ".join(notes))

        # ---- Source Information ----
        st.markdown("---")
        st.markdown("**Source Information**")
        ep = rule.get("effective_period", {})
        sc1, sc2, sc3 = st.columns(3)
        sc1.markdown(f"**Memo:** {memo_ref}")
        sc2.markdown(f"**Effective:** {ep.get('start_date', '—')} → {ep.get('end_date', '—')}")
        sc3.markdown(f"**Project:** {project}")

        # ---- Document Verification ----
        st.markdown("---")
        st.markdown("**Document Verification**")
        img_files = rule.get("image_files", [])
        if img_files:
            if st.button("📄 View Original Memo", key=f"view_memo_{rid}_{idx}"):
                st.session_state[f"show_memo_{rid}"] = not st.session_state.get(f"show_memo_{rid}", False)

            if st.session_state.get(f"show_memo_{rid}", False):
                paths = _get_memo_images(img_files)
                if paths:
                    memo_container = st.container(height=400)
                    with memo_container:
                        for pi, p in enumerate(paths):
                            st.caption(f"Page {pi+1} of {len(paths)}")
                            st.image(str(p), use_container_width=True)
                else:
                    st.warning("Original memo images not found.")
        else:
            st.info("No memo images available for verification.")

        # ---- Validation ----
        st.markdown("---")
        current_v_status = st.session_state.get("rule_validation_status", {}).get(rid, "Pending")
        act1, act2, act3, act4 = st.columns([1, 1, 1, 1])
        with act1:
            if st.button("✅ Validate Rule", key=f"validate_{rid}_{idx}"):
                issues = _validate_rule(rule)
                st.session_state[f"validation_{rid}"] = issues
                # Auto-set validation status based on results
                has_error = any(i["level"] == "error" for i in issues)
                vs = st.session_state.get("rule_validation_status", {})
                vs[rid] = "Not Validated" if has_error else "Validated"
                st.session_state["rule_validation_status"] = vs
                st.rerun()

        with act2:
            flag_info = st.session_state.get("flagged_rules", {}).get(rid)
            if flag_info:
                if st.button("🔓 Unflag Rule", key=f"unflag_{rid}_{idx}"):
                    flagged = st.session_state.get("flagged_rules", {})
                    flagged.pop(rid, None)
                    st.session_state["flagged_rules"] = flagged
                    st.rerun()
            else:
                if st.button("🚩 Flag Rule", key=f"flag_{rid}_{idx}"):
                    st.session_state[f"show_flag_form_{rid}"] = True

        with act4:
            if current_v_status != "Pending":
                if st.button("↩ Reset Validation", key=f"reset_val_{rid}_{idx}"):
                    vs = st.session_state.get("rule_validation_status", {})
                    vs[rid] = "Pending"
                    st.session_state["rule_validation_status"] = vs
                    st.session_state.pop(f"validation_{rid}", None)
                    st.rerun()

        # Flag form
        if st.session_state.get(f"show_flag_form_{rid}", False):
            st.markdown(
                '<div class="flag-form-container">'
                '<div class="flag-form-header">'
                '<span class="flag-form-icon">🚩</span> Flag This Rule'
                '</div>',
                unsafe_allow_html=True,
            )
            reason = st.selectbox("Reason", [
                "Incorrect extraction",
                "Missing condition",
                "Wrong rate value",
                "Ambiguous rule",
                "Other",
            ], key=f"flag_reason_{rid}_{idx}")
            flag_note = st.text_input("Additional note (optional)", key=f"flag_note_{rid}_{idx}")
            fc1, fc2, _ = st.columns([1, 1, 3])
            with fc1:
                if st.button("Submit Flag", key=f"submit_flag_{rid}_{idx}", type="primary"):
                    flagged = st.session_state.get("flagged_rules", {})
                    flagged[rid] = {"reason": reason, "note": flag_note}
                    st.session_state["flagged_rules"] = flagged
                    st.session_state.pop(f"show_flag_form_{rid}", None)
                    st.success(f"Rule {rid} flagged: {reason}")
                    st.rerun()
            with fc2:
                if st.button("Cancel", key=f"cancel_flag_{rid}_{idx}"):
                    st.session_state.pop(f"show_flag_form_{rid}", None)
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # Show validation results
        val_results = st.session_state.get(f"validation_{rid}")
        if val_results:
            st.markdown("**Validation Results:**")
            for v in val_results:
                if v["level"] == "success":
                    st.success(f"✔ {v['message']}")
                elif v["level"] == "warning":
                    st.warning(f"⚠ {v['message']}")
                else:
                    st.error(f"✖ {v['message']}")

        # Flag info display
        flag_info = st.session_state.get("flagged_rules", {}).get(rid)
        if flag_info:
            st.warning(f"🚩 **Flagged** — {flag_info['reason']}" + (f" ({flag_info['note']})" if flag_info.get('note') else ""))


def render_extracted_rules_page():
    """Rule-oriented Extracted Rules page with filters, cards, validation & flagging."""
    st.markdown(MEMO_CSS, unsafe_allow_html=True)

    # ---- Header ----
    st.markdown("""
    <div class="page-header-wrap">
        <div class="page-header-title">📚 Extracted Rules</div>
        <div class="page-header-subtitle">Commission calculation rules extracted from approved memorandums</div>
        <div class="page-header-badge">⚙️ Rule Engine</div>
    </div>
    """, unsafe_allow_html=True)

    # ---- Init session state ----
    if "flagged_rules" not in st.session_state:
        st.session_state["flagged_rules"] = {}
    if "rule_validation_status" not in st.session_state:
        st.session_state["rule_validation_status"] = {}

    # ---- Aggregate rules ----
    all_rules = _aggregate_all_rules()

    if not all_rules:
        st.info("No rules have been extracted yet. Upload and approve memos first.")
        return

    # ---- Filter Panel ----
    st.markdown("<div style='margin-top:0.75rem;'></div>", unsafe_allow_html=True)
    fc1, fc2, fc3, fc4, fc5, fc6 = st.columns([1.1, 1.1, 1, 1, 1, 1.3])

    projects = sorted(set(r["project_name"] for r in all_rules if r["project_name"]))
    memos_refs = sorted(set(r["memo_reference"] for r in all_rules if r["memo_reference"]))
    rule_types = sorted(set(r["rule_type"] for r in all_rules))

    with fc1:
        sel_project = st.selectbox("Project", ["All"] + projects, key="rules_filter_project")
    with fc2:
        sel_memo = st.selectbox("Memo", ["All"] + memos_refs, key="rules_filter_memo")
    with fc3:
        sel_type = st.selectbox("Rule Type", ["All"] + rule_types, key="rules_filter_type")
    with fc4:
        sel_status = st.selectbox("Status", ["All", "Active", "Flagged"], key="rules_filter_status")
    with fc5:
        sel_validation = st.selectbox("Validation", ["All", "Validated", "Flagged", "Pending"], key="rules_filter_validation")
    with fc6:
        search_q = st.text_input("🔍 Search", placeholder="Rule ID or keyword…", key="rules_search")

    # ---- Apply Filters ----
    filtered = all_rules
    if sel_project != "All":
        filtered = [r for r in filtered if r["project_name"] == sel_project]
    if sel_memo != "All":
        filtered = [r for r in filtered if r["memo_reference"] == sel_memo]
    if sel_type != "All":
        filtered = [r for r in filtered if r["rule_type"] == sel_type]
    if sel_status != "All":
        filtered = [r for r in filtered if r["status"] == sel_status]
    if sel_validation != "All":
        v_store = st.session_state.get("rule_validation_status", {})
        flagged_store = st.session_state.get("flagged_rules", {})
        if sel_validation == "Flagged":
            filtered = [r for r in filtered if r["rule_id"] in flagged_store]
        else:
            filtered = [r for r in filtered if v_store.get(r["rule_id"], "Pending") == sel_validation and r["rule_id"] not in flagged_store]
    if search_q:
        q = search_q.lower()
        filtered = [r for r in filtered if q in r["rule_id"].lower() or q in r["rule_name"].lower() or q in r.get("calculation_method", "").lower()]

    # ---- Sort ----
    sort_col, count_col = st.columns([2, 3])
    with sort_col:
        sort_by = st.selectbox("Sort by", ["Rule ID", "Rule Type", "Memo", "Confidence"], key="rules_sort")
    with count_col:
        st.markdown(f"<div style='padding-top:1.6rem;color:#64748b;font-size:0.85rem;'>Showing <strong>{len(filtered)}</strong> of {len(all_rules)} rules</div>", unsafe_allow_html=True)

    if sort_by == "Rule ID":
        filtered.sort(key=lambda r: r["rule_id"])
    elif sort_by == "Rule Type":
        filtered.sort(key=lambda r: r["rule_type"])
    elif sort_by == "Memo":
        filtered.sort(key=lambda r: r["memo_reference"])
    elif sort_by == "Confidence":
        filtered.sort(key=lambda r: r.get("extraction_confidence") or 0, reverse=True)

    st.markdown("---")

    # ---- KPI Strip ----
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    total = len(all_rules)
    total_active = sum(1 for r in all_rules if r["status"] == "Active")
    total_flagged = sum(1 for r in all_rules if r["status"] == "Flagged")
    v_store = st.session_state.get("rule_validation_status", {})
    total_validated = sum(1 for r in all_rules if v_store.get(r["rule_id"], "Pending") == "Validated")
    avg_conf = sum((r.get("extraction_confidence") or 0) for r in all_rules) / max(total, 1)
    n_memos = len(set(r["memo_reference"] for r in all_rules))

    for col, label, value, color in [
        (k1, "Total Rules", str(total), "#0f172a"),
        (k2, "Active", str(total_active), "#16a34a"),
        (k3, "Flagged", str(total_flagged), "#d97706"),
        (k4, "Validated", str(total_validated), "#059669"),
        (k5, "Avg Confidence", f"{avg_conf:.0%}", "#2563eb"),
        (k6, "Source Memos", str(n_memos), "#7c3aed"),
    ]:
        col.markdown(f"""
        <div class="memo-kpi-card">
            <div class="memo-kpi-value" style="color:{color};">{value}</div>
            <div class="memo-kpi-label">{label}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)

    # ---- Rule Cards ----
    if not filtered:
        st.info("No rules match the current filters.")
        return

    # Pagination
    PAGE_SIZE = 10
    total_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)
    if "rules_page" not in st.session_state:
        st.session_state["rules_page"] = 1
    current_page = st.session_state["rules_page"]
    current_page = min(current_page, total_pages)
    start_idx = (current_page - 1) * PAGE_SIZE
    page_rules = filtered[start_idx : start_idx + PAGE_SIZE]

    for i, rule in enumerate(page_rules):
        _render_rule_card(rule, start_idx + i)

    # Pagination controls
    if total_pages > 1:
        st.markdown("---")
        pcol1, pcol2, pcol3 = st.columns([1, 2, 1])
        with pcol1:
            if st.button("← Previous", disabled=current_page <= 1, key="rules_prev"):
                st.session_state["rules_page"] = current_page - 1
                st.rerun()
        with pcol2:
            st.markdown(f"<div style='text-align:center;padding-top:0.5rem;color:#64748b;'>Page {current_page} of {total_pages}</div>", unsafe_allow_html=True)
        with pcol3:
            if st.button("Next →", disabled=current_page >= total_pages, key="rules_next"):
                st.session_state["rules_page"] = current_page + 1
                st.rerun()


# ---------------------------------------------------------------------------
# MAIN — Sidebar Navigation Router
# ---------------------------------------------------------------------------

def main():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # ── Sidebar Navigation ──
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; padding:1.8rem 0 1rem 0;">
            <div style="
                display:inline-flex; align-items:center; justify-content:center;
                width:52px; height:52px; border-radius:16px;
                background: linear-gradient(135deg, #6366F1 0%, #4F46E5 50%, #4338CA 100%);
                margin-bottom:0.75rem;
                box-shadow: 0 6px 20px rgba(79,70,229,0.35), 0 0 0 4px rgba(99,102,241,0.1);
                animation: pulseGlow 3s ease-in-out infinite;
            ">
                <span style="color:white; font-size:1.3rem; font-weight:800; font-family:'DM Sans',sans-serif;">A</span>
            </div>
            <div style="font-size:1.25rem; font-weight:800; color:#F1F5F9; letter-spacing:0.12em;
                         font-family:'DM Sans',sans-serif;">AVALAND</div>
            <div style="font-size:0.6rem; color:#64748B; letter-spacing:2.5px; margin-top:0.2rem;
                         font-weight:500;">PROPERTY GROUP</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("---")

        # Section label
        st.markdown(
            '<div style="font-size:0.6rem; color:#475569; letter-spacing:1.8px; '
            'font-weight:600; padding:0 1.2rem; margin-bottom:0.3rem;">NAVIGATION</div>',
            unsafe_allow_html=True,
        )

        nav_options = [
            "📊  Projects",
            "📝  Memorandums",
            "📚  Extracted Rules",
            "💰  Agent Commissions",
        ]

        # Preserve navigation across reruns
        if "nav_page" not in st.session_state:
            st.session_state["nav_page"] = nav_options[0]

        selected = st.radio(
            "Navigation",
            nav_options,
            index=nav_options.index(st.session_state["nav_page"]) if st.session_state["nav_page"] in nav_options else 0,
            label_visibility="collapsed",
            key="nav_radio",
        )
        st.session_state["nav_page"] = selected

        st.markdown("---")
        st.markdown(
            '<div style="text-align:center; padding:0.5rem 0;">'
            '<div style="font-size:0.62rem;color:#475569;letter-spacing:0.3px;">'
            'Avaland Commission Suite</div>'
            '<div style="font-size:0.55rem;color:#334155;margin-top:2px;opacity:0.5;">'
            'v1.0 &middot; 2025</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    # ── Page Router ──
    if selected == "📊  Projects":
        render_projects_page()

    elif selected == "📝  Memorandums":
        render_memorandums_page()

    elif selected == "📚  Extracted Rules":
        render_extracted_rules_page()

    elif selected == "💰  Agent Commissions":
        render_dashboard()


if __name__ == "__main__":
    main()
