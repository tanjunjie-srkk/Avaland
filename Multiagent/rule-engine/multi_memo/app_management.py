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
    initial_sidebar_state="collapsed",
)


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
/* ---- Global: force light-mode text on light background ---- */
[data-testid="stAppViewContainer"] {
    background: #f5f6fa;
    color: #1e293b;
}
h1, h2, h3, h4, h5, h6 { color: #0f172a !important; }

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
    color: #1a73e8 !important;
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
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    padding: 1.25rem 2rem;
    border-radius: 14px;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: end;
    gap: 1.5rem;
}
.filter-label {
    color: #94a3b8;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.25rem;
}

/* ---- Metric cards (top row) ---- */
.metric-card {
    background: white;
    border-radius: 14px;
    padding: 1.5rem 2rem;
    display: flex;
    align-items: center;
    gap: 1.25rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    border: 1px solid #f1f5f9;
    position: relative;
    overflow: hidden;
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px; height: 100%;
    border-radius: 14px 0 0 14px;
}
.metric-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0,0,0,0.08);
}
.metric-icon {
    width: 52px; height: 52px;
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem;
    flex-shrink: 0;
}
.metric-label { color: #64748b; font-size: 0.78rem; font-weight: 500; letter-spacing: 0.3px; }
.metric-value { font-size: 1.6rem; font-weight: 700; color: #0f172a; line-height: 1.2; }

.metric-card-highlight {
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    border-radius: 14px;
    padding: 1.5rem 2rem;
    display: flex;
    align-items: center;
    gap: 1.25rem;
    box-shadow: 0 4px 20px rgba(13,148,136,0.3);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    border: none;
    position: relative;
    overflow: hidden;
}
.metric-card-highlight:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(13,148,136,0.4);
}
.metric-card-highlight .metric-label { color: rgba(255,255,255,0.85); font-size: 0.78rem; font-weight: 500; }
.metric-card-highlight .metric-value { color: white; }

/* ---- Agent row card ---- */
.agent-row {
    background: white;
    border-radius: 12px;
    padding: 1rem 1.5rem;
    margin: 0.5rem 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    transition: all 0.25s ease;
    border: 1px solid #f1f5f9;
    position: relative;
    overflow: hidden;
}
.agent-row::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px; height: 100%;
    background: #e2e8f0;
    transition: background 0.25s ease;
}
.agent-row:hover {
    box-shadow: 0 6px 20px rgba(0,0,0,0.08);
    transform: translateY(-1px);
    border-color: #e2e8f0;
}
.agent-row:hover::before {
    background: #1a73e8;
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
.agent-metric-value.highlight { color: #0d9488; font-weight: 700; font-size: 1.05rem; }
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
    background: linear-gradient(90deg, #1a73e8, #0d9488);
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
    background: #eff6ff; color: #1d4ed8;
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
    background: #eff6ff; color: #1a73e8;
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
    background: linear-gradient(135deg, #eff6ff 0%, #f0f4ff 100%);
    border: 1px solid #bfdbfe;
    border-radius: 10px;
    padding: 0.75rem 1.25rem;
    font-size: 0.85rem;
    color: #1e40af;
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
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 2px 10px rgba(0,0,0,0.06);
    transition: transform 0.2s, box-shadow 0.2s;
    display: flex;
    flex-direction: column;
    width: 100%;
}
.team-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 25px rgba(0,0,0,0.1);
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
.team-kpi-value.tkv-blue { color: #1a73e8; }
.team-kpi-value.tkv-red { color: #dc2626; }
.team-kpi-value.tkv-teal { color: #0d9488; }
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
.team-overview-kpi-value.tok-blue { color: #1a73e8; }
.team-overview-kpi-value.tok-teal { color: #0d9488; }
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
    border-radius: 14px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    overflow: hidden;
    margin-bottom: 1.5rem;
    border: 1px solid #e2e8f0;
    transition: box-shadow 0.2s ease;
}
.analytics-panel:hover {
    box-shadow: 0 6px 24px rgba(0,0,0,0.09);
}
.analytics-panel-header {
    padding: 1.1rem 1.5rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    border-bottom: 1px solid #f1f5f9;
}
.analytics-panel-icon {
    width: 38px; height: 38px;
    border-radius: 10px;
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
    background: #1a73e8;
    position: absolute;
    top: 0; left: 0;
    transition: width 0.5s cubic-bezier(.4,0,.2,1);
}
.comm-bar-fill-net {
    height: 100%;
    border-radius: 4px;
    background: #0d9488;
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
.comm-bar-val.cv-blue { color: #1a73e8; }
.comm-bar-val.cv-teal { color: #0d9488; }
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
    color: #0d9488;
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
.rule-type-badge.rtb-commission { background: #eff6ff; color: #1d4ed8; }
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
.rule-bar-fill.rbf-commission { background: #1a73e8; }
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
    background: linear-gradient(135deg, #1a73e8, #4f93f8);
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
    color: #1a73e8;
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
    background: linear-gradient(90deg, #1a73e8, #0d9488, #7c3aed);
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
.asm-commission { background: #eff6ff; }
.asm-commission .agent-summary-metric-value { color: #1a73e8; }
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
}
[data-testid="stExpander"] summary span,
[data-testid="stExpander"] summary p {
    color: #475569 !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
}
[data-testid="stExpander"] summary svg {
    color: #94a3b8 !important;
    fill: #94a3b8 !important;
}
[data-testid="stExpander"] summary:hover {
    background: #eff6ff !important;
}
[data-testid="stExpander"] summary:hover span,
[data-testid="stExpander"] summary:hover p {
    color: #1e40af !important;
}
[data-testid="stExpander"] summary:hover svg {
    color: #1e40af !important;
    fill: #1e40af !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    background: white !important;
    padding: 0.75rem 1rem !important;
    color: #334155 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] * {
    color: #334155 !important;
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
    color: #1d4ed8 !important;
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
    background: linear-gradient(180deg, #1a73e8 0%, #0d9488 100%);
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
.entitlement-metric-value.ent-claimed { color: #1a73e8; }
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
    background: linear-gradient(90deg, #1a73e8, #0d9488);
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
    background: linear-gradient(90deg, #0d9488 0%, #14b8a6 100%);
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
.ent-summary-value.ent-blue { color: #1a73e8; }
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
    background: linear-gradient(90deg, #1a73e8 0%, #3b82f6 100%);
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
.breakdown-badge-rule { color: #1d4ed8 !important; }
.breakdown-badge-memo { color: #b45309 !important; }
/* Section subtitle */
.section-subtitle { color: #94a3b8 !important; }
/* Metric card specific label color */
.metric-label { color: #64748b !important; }
.metric-value { color: #0f172a !important; }
/* Agent row metric label */
.agent-metric-label { color: #94a3b8 !important; }
.agent-metric-value.highlight { color: #0d9488 !important; }
/* Entitlement specific */
.entitlement-metric-label { color: #94a3b8 !important; }
.entitlement-metric-value.ent-claimed { color: #1a73e8 !important; }
.entitlement-metric-value.ent-balance { color: #dc2626 !important; }
.ent-progress-text { color: #475569 !important; }
/* Summary panel value colors */
.ent-summary-value.ent-green { color: #059669 !important; }
.ent-summary-value.ent-red { color: #dc2626 !important; }
.ent-summary-value.ent-blue { color: #1a73e8 !important; }
/* Agent summary metric value colors */
.asm-commission .agent-summary-metric-value { color: #1a73e8 !important; }
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
.team-kpi-value.tkv-blue { color: #1a73e8 !important; }
.team-kpi-value.tkv-red { color: #dc2626 !important; }
.team-kpi-value.tkv-teal { color: #0d9488 !important; }
.team-progress-label { color: #64748b !important; }
.team-member-name { color: #334155 !important; }
.team-member-avatar { color: white !important; }
.team-member-leader-tag { color: #d97706 !important; }
.team-member-stat-label { color: #94a3b8 !important; }
.team-member-stat-value { color: #334155 !important; }
/* Overview KPI colors */
.team-overview-kpi-label { color: #94a3b8 !important; }
.team-overview-kpi-value.tok-blue { color: #1a73e8 !important; }
.team-overview-kpi-value.tok-teal { color: #0d9488 !important; }
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
.scheme-info { color: #1e40af !important; }
.scheme-info span { color: #1e40af !important; }
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
        ("📋", "Agents Calculated", str(total_sellers), "#eff6ff", "#1a73e8", "metric-card"),
        ("🏠", "Units Sold", str(total_units), "#faf5ff", "#7c3aed", "metric-card"),
        ("💰", "Total Commission", fmt(total_commission), "#ecfdf5", "#0d9488", "metric-card"),
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
        ("linear-gradient(135deg, #1a73e8 0%, #4f93f8 100%)", "#1a73e8"),
        ("linear-gradient(135deg, #0d9488 0%, #14b8a6 100%)", "#0d9488"),
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
                f'<div class="team-member-stat-value" style="color:#0d9488;">{fmt(m.net_payable)}</div>'
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
            f'<div class="team-lb-value" style="color:#1a73e8;">{fmt(t_comm)}</div>'
            f'<div class="team-lb-value" style="color:#0d9488;">{fmt(t_net)}</div>'
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

    dot_colors = ["#1a73e8", "#0d9488", "#f59e0b", "#7c3aed", "#dc2626", "#ea580c"]
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
                    <div class="unit-subtotal-value" style="color:#1a73e8;">{fmt_full(sale.commission_amount)}</div>
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
        '<div class="analytics-panel-icon" style="background:#eff6ff;color:#1a73e8;">📊</div>'
        '<div>'
        '<div class="analytics-panel-title">Commission Distribution by Agent</div>'
        '<div class="analytics-panel-subtitle">Commission vs Net Payable for each agent</div>'
        '</div>'
        '</div>'
        '<div class="analytics-panel-body">'
        # Legend
        '<div style="display:flex;gap:1.25rem;margin-bottom:0.75rem;">'
        '<span style="display:flex;align-items:center;gap:0.35rem;font-size:0.72rem;color:#64748b;">'
        '<span style="width:10px;height:10px;border-radius:2px;background:#1a73e8;display:inline-block;"></span> Commission</span>'
        '<span style="display:flex;align-items:center;gap:0.35rem;font-size:0.72rem;color:#64748b;">'
        '<span style="width:10px;height:10px;border-radius:2px;background:#0d9488;display:inline-block;"></span> Net Payable</span>'
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
    <div style="background:linear-gradient(135deg,#1e3a5f 0%,#2d5a8e 100%);border-radius:12px;padding:1rem 1.5rem;margin-bottom:1rem;">
        <div style="color:rgba(255,255,255,0.85);font-size:0.8rem;font-weight:600;">📋 {memo_type.upper()}</div>
        <div style="color:white;font-size:1.1rem;font-weight:700;">{metadata.memo_reference} - {metadata.project_name}</div>
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
                                '<div style="background:#eff6ff;padding:0.8rem;margin:0.5rem 0;border-radius:8px;border-left:4px solid #1a73e8;">'
                                '<div style="font-family:monospace;font-size:0.9rem;color:#1e293b;">'
                                f'<strong>IF</strong> {condition.replace("IF ", "")}'
                                '</div>'
                                '<div style="margin-top:0.5rem;">'
                                f'<span style="background:#1a73e8;color:white;padding:0.2rem 0.6rem;border-radius:4px;font-weight:bold;">Rebate: {rate}%</span>'
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
            '<div class="metric-card" style="border-left:4px solid #1a73e8;">'
            '<div class="metric-icon" style="background:#eff6ff; color:#1a73e8;">💰</div>'
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
        ring_color = '#059669' if progress >= 100 else ('#1a73e8' if progress > 0 else '#e2e8f0')
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
# MAIN
# ---------------------------------------------------------------------------

def main():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # ---- Header ----
    st.markdown("""
    <div style="display:flex; align-items:center; gap:1rem; margin-bottom:0.5rem;">
        <div style="font-size:1.8rem; font-weight:800; color:#0f172a;">📊 Commission Management</div>
        <div style="flex:1;"></div>
        <div style="color:#94a3b8; font-size:0.85rem;">Avaland Property Group</div>
    </div>
    <div style="color:#64748b; font-size:0.9rem; margin-bottom:1.5rem;">
        Overview of agent commissions, payment tracking &amp; performance analytics &mdash; Aetas Seputeh
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


if __name__ == "__main__":
    main()
