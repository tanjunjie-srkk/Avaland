"""
Memo Inbox – Memorandum Summary Dashboard
Lists every uploaded memo with status badges (Pending / Approved / Rejected).
Expandable rows show:
  • Extracted rules (from JSON)
  • Original memo page images (side-by-side comparison)
  • Approve / Reject controls
"""

import streamlit as st
import json
import sys
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
CURRENT_DIR = Path(__file__).parent
ARTIFACT_DIR = CURRENT_DIR.parent.parent / "artifact"
MEMO_IMG_DIR = CURRENT_DIR.parent.parent.parent / "memo"
STORE_PATH = CURRENT_DIR / "memo_store.json"

sys.path.insert(0, str(CURRENT_DIR))

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Avaland · Memorandum Inbox",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header {
        font-size: 2.4rem; font-weight: bold; color: #1E3A5F;
        text-align: center; padding: 1.2rem;
        border-bottom: 4px solid #E8B54B; margin-bottom: 1rem;
        background: linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%);
    }
    .status-approved {
        background: #28a745; color: white; padding: 0.25rem 0.9rem;
        border-radius: 20px; font-size: 0.8rem; font-weight: 600;
        display: inline-block;
    }
    .status-pending {
        background: #ffc107; color: #333; padding: 0.25rem 0.9rem;
        border-radius: 20px; font-size: 0.8rem; font-weight: 600;
        display: inline-block;
    }
    .status-rejected {
        background: #dc3545; color: white; padding: 0.25rem 0.9rem;
        border-radius: 20px; font-size: 0.8rem; font-weight: 600;
        display: inline-block;
    }
    .memo-card {
        background: #ffffff; border: 1px solid #e0e0e0;
        border-radius: 12px; padding: 1.2rem; margin: 0.6rem 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .rule-chip {
        display: inline-block; background: #e7f3ff;
        border: 1px solid #b3d7ff; border-radius: 6px;
        padding: 0.2rem 0.6rem; margin: 0.15rem; font-size: 0.78rem;
    }
    .confidence-high { color: #28a745; font-weight: bold; }
    .confidence-med  { color: #ffc107; font-weight: bold; }
    .confidence-low  { color: #dc3545; font-weight: bold; }
    .kpi-box {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        color: white; padding: 1.5rem; border-radius: 14px;
        text-align: center; box-shadow: 0 6px 24px rgba(0,0,0,0.15);
    }
    .kpi-value { font-size: 2.2rem; font-weight: bold; color: #4ade80; }
    .kpi-label { font-size: 0.85rem; color: rgba(255,255,255,0.75); margin-top: 0.3rem; }
    .section-header {
        background: linear-gradient(90deg, #1E3A5F 0%, #2E5A8F 100%);
        color: white; padding: 0.6rem 1rem; border-radius: 8px;
        font-size: 1rem; font-weight: 600; margin: 0.8rem 0 0.4rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_store() -> list[dict]:
    if STORE_PATH.exists():
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    return []


def save_store(data: list[dict]):
    STORE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_rules(rules_filename: str | None) -> dict | None:
    if not rules_filename:
        return None
    p = ARTIFACT_DIR / rules_filename
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def get_memo_images(image_files: list[str]) -> list[Path]:
    """Return list of existing image paths in the memo folder."""
    paths = []
    for fname in image_files:
        p = MEMO_IMG_DIR / fname
        if p.exists():
            paths.append(p)
    return paths


def status_badge(status: str) -> str:
    cls = f"status-{status}"
    label = status.capitalize()
    return f'<span class="{cls}">{label}</span>'


def confidence_span(conf: float | None) -> str:
    if conf is None:
        return "—"
    cls = "confidence-high" if conf >= 0.8 else ("confidence-med" if conf >= 0.6 else "confidence-low")
    return f'<span class="{cls}">{conf:.0%}</span>'

# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

def render_kpis(memos: list[dict]):
    approved = sum(1 for m in memos if m["status"] == "approved")
    pending  = sum(1 for m in memos if m["status"] == "pending")
    rejected = sum(1 for m in memos if m["status"] == "rejected")
    total    = len(memos)

    c1, c2, c3, c4 = st.columns(4)
    for col, val, label in [
        (c1, total,    "Total Memos"),
        (c2, approved, "Approved"),
        (c3, pending,  "Pending Review"),
        (c4, rejected, "Rejected"),
    ]:
        col.markdown(f"""
        <div class="kpi-box">
            <div class="kpi-value">{val}</div>
            <div class="kpi-label">{label}</div>
        </div>""", unsafe_allow_html=True)


def render_rules_summary(rules: dict):
    """Compact tabular display of all rules inside a memo."""
    if not rules or "rules" not in rules:
        st.info("No extracted rules available for this memo.")
        return

    rule_sections = rules["rules"]
    section_icons = {
        "commission_rules": ("💰", "Commission Rules"),
        "rebate_rules": ("🏷️", "Rebate Rules"),
        "referral_rules": ("🤝", "Referral Rules"),
        "price_adjustment_rules": ("📐", "Price Adjustment Rules"),
        "package_rules": ("📦", "Package Rules"),
    }

    for key, (icon, title) in section_icons.items():
        items = rule_sections.get(key, [])
        if not items:
            continue
        st.markdown(f'<div class="section-header">{icon} {title} ({len(items)})</div>', unsafe_allow_html=True)

        for rule in items:
            rule_id = rule.get("rule_id", "")
            rule_name = rule.get("rule_name", "Untitled")
            conditions = rule.get("conditions", [])

            with st.container():
                st.markdown(f"**{rule_id}** — {rule_name}")
                # Show conditions as table
                if conditions:
                    if isinstance(conditions[0], dict):
                        rows = []
                        for c in conditions:
                            rows.append({
                                "Condition": c.get("condition", ""),
                                "Value": (
                                    f'{c.get("commission_percentage", c.get("rebate_percentage", c.get("adjustment_amount", "")))}' 
                                    + ("%" if "percentage" in str(c) else "")
                                ),
                                "Description": c.get("description", ""),
                            })
                        st.table(rows)
                    else:
                        # Simple list (e.g. referral conditions)
                        for c in conditions:
                            st.markdown(f"- {c}")

                notes = rule.get("notes", [])
                if notes:
                    st.caption("Notes: " + " · ".join(notes))
                st.markdown("---")


def render_original_memo_images(image_files: list[str]):
    """Display original memo page images."""
    paths = get_memo_images(image_files)
    if not paths:
        st.warning("Original memo images not found.")
        return

    for idx, img_path in enumerate(paths):
        st.image(str(img_path), caption=f"Page {idx + 1}", use_container_width=True)  # noqa: deprecation


def render_side_by_side(memo: dict, rules: dict | None):
    """Side-by-side: original images (left) vs extracted rules (right)."""
    col_img, col_rules = st.columns([1, 1])

    with col_img:
        st.markdown('<div class="section-header">📄 Original Memo</div>', unsafe_allow_html=True)
        render_original_memo_images(memo.get("image_files", []))

    with col_rules:
        st.markdown('<div class="section-header">📋 Extracted Rules</div>', unsafe_allow_html=True)
        if rules:
            render_rules_summary(rules)
        else:
            st.info("Rules have not been extracted yet for this memo.")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.markdown('<div class="main-header">📋 Memorandum Inbox</div>', unsafe_allow_html=True)

    memos = load_store()

    # --- KPI strip ---
    render_kpis(memos)
    st.markdown("<br>", unsafe_allow_html=True)

    # --- Filter bar ---
    col_filter, col_btn = st.columns([3, 1])
    with col_filter:
        filter_status = st.multiselect(
            "Filter by status",
            ["approved", "pending", "rejected"],
            default=["approved", "pending", "rejected"],
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        st.info("To add a new memo, run: `streamlit run app_memo_upload.py --server.port 8505`")

    filtered = [m for m in memos if m["status"] in filter_status]

    if not filtered:
        st.info("No memos match the selected filters.")
        return

    # --- Memo list ---
    for memo in filtered:
        badge = status_badge(memo["status"])
        conf  = confidence_span(memo.get("extraction_confidence"))
        ref   = memo["memo_reference"]
        proj  = memo["project_name"]
        period = f'{memo["effective_period"]["start_date"]} → {memo["effective_period"]["end_date"]}'
        upload = memo.get("upload_date", "—")

        rc = memo.get("rule_count") or {}
        total_rules = sum(rc.values()) if rc else 0

        # Card header
        header_text = f"{ref} · {proj}"
        with st.expander(f"{'🟢' if memo['status']=='approved' else '🟡' if memo['status']=='pending' else '🔴'} {header_text}   |   {memo['status'].upper()}", expanded=False):
            # Meta row
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.markdown(f"**Status:** {badge}", unsafe_allow_html=True)
            mc2.markdown(f"**Period:** {period}")
            mc3.markdown(f"**Confidence:** {conf}", unsafe_allow_html=True)
            mc4.markdown(f"**Rules extracted:** {total_rules}")

            st.markdown(f"**Uploaded:** {upload}  ·  **PDF:** `{memo.get('pdf_filename', '—')}`")

            if memo.get("reviewer_notes"):
                st.info(f"📝 Reviewer note: {memo['reviewer_notes']}")

            # Side-by-side comparison
            rules = load_rules(memo.get("rules_file"))
            render_side_by_side(memo, rules)

            # Approve / Reject controls (only for pending)
            if memo["status"] == "pending":
                st.markdown("---")
                st.subheader("Review Actions")
                note = st.text_area("Reviewer notes", key=f"note_{memo['memo_id']}")
                act1, act2, _ = st.columns([1, 1, 3])
                with act1:
                    if st.button("✅ Approve", key=f"approve_{memo['memo_id']}", type="primary"):
                        for m in memos:
                            if m["memo_id"] == memo["memo_id"]:
                                m["status"] = "approved"
                                m["reviewer_notes"] = note
                        save_store(memos)
                        st.success("Memo approved!")
                        st.rerun()
                with act2:
                    if st.button("❌ Reject", key=f"reject_{memo['memo_id']}"):
                        for m in memos:
                            if m["memo_id"] == memo["memo_id"]:
                                m["status"] = "rejected"
                                m["reviewer_notes"] = note
                        save_store(memos)
                        st.warning("Memo rejected.")
                        st.rerun()

            # Re-review for approved / rejected
            if memo["status"] in ("approved", "rejected"):
                st.markdown("---")
                rev1, rev2, _ = st.columns([1, 1, 3])
                with rev1:
                    if st.button("🔄 Move to Pending", key=f"reopen_{memo['memo_id']}"):
                        for m in memos:
                            if m["memo_id"] == memo["memo_id"]:
                                m["status"] = "pending"
                        save_store(memos)
                        st.rerun()


if __name__ == "__main__":
    main()
