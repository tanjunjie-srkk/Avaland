"""
Memo Review – Full-Screen Side-by-Side Comparison
Dedicated page for reviewing a specific memo.
Left panel: original memo page images.
Right panel: extracted rules with per-rule accept/flag controls.

The page reads a query-param  ?memo_id=MEMO_001  to know which memo to show.
If launched without a param it falls back to the first approved memo as demo.
"""

import streamlit as st
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CURRENT_DIR = Path(__file__).parent
ARTIFACT_DIR = CURRENT_DIR.parent.parent / "artifact"
MEMO_IMG_DIR = CURRENT_DIR.parent.parent.parent / "memo"
STORE_PATH   = CURRENT_DIR / "memo_store.json"

sys.path.insert(0, str(CURRENT_DIR))

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Avaland · Memo Review",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header {
        font-size: 2rem; font-weight: bold; color: #1E3A5F;
        text-align: center; padding: 1rem;
        border-bottom: 3px solid #E8B54B; margin-bottom: 0.8rem;
    }
    .section-header {
        background: linear-gradient(90deg, #1E3A5F 0%, #2E5A8F 100%);
        color: white; padding: 0.6rem 1rem; border-radius: 8px;
        font-weight: 600; margin-bottom: 0.4rem;
    }
    .rule-card {
        background: #f8f9fa; border-left: 4px solid #28a745;
        padding: 0.8rem; margin: 0.4rem 0; border-radius: 0 8px 8px 0;
    }
    .rule-card-flagged {
        background: #fff3cd; border-left: 4px solid #dc3545;
        padding: 0.8rem; margin: 0.4rem 0; border-radius: 0 8px 8px 0;
    }
    .confidence-bar { height: 8px; border-radius: 4px; background: #e9ecef; }
    .confidence-fill-high { height: 100%; border-radius: 4px; background: #28a745; }
    .confidence-fill-med  { height: 100%; border-radius: 4px; background: #ffc107; }
    .confidence-fill-low  { height: 100%; border-radius: 4px; background: #dc3545; }
    .meta-pill {
        display: inline-block; background: #e7f3ff;
        border: 1px solid #b3d7ff; border-radius: 6px;
        padding: 0.2rem 0.6rem; margin: 0.1rem; font-size: 0.78rem;
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


def load_rules(filename: str | None) -> dict | None:
    if not filename:
        return None
    p = ARTIFACT_DIR / filename
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def get_image_paths(image_files: list[str]) -> list[Path]:
    return [MEMO_IMG_DIR / f for f in image_files if (MEMO_IMG_DIR / f).exists()]

# ---------------------------------------------------------------------------
# Render – left panel (original images)
# ---------------------------------------------------------------------------

def render_images_panel(image_files: list[str]):
    paths = get_image_paths(image_files)
    if not paths:
        st.warning("No original memo images found for this entry.")
        return

    # Page selector
    page_idx = st.selectbox(
        "Select page",
        range(len(paths)),
        format_func=lambda i: f"Page {i+1} of {len(paths)}",
        key="review_page_selector",
    )
    st.image(str(paths[page_idx]), caption=f"Page {page_idx + 1}", use_container_width=True)  # noqa: deprecation

    # Thumbnail strip
    if len(paths) > 1:
        cols = st.columns(min(len(paths), 5))
        for i, (col, p) in enumerate(zip(cols, paths)):
            col.image(str(p), caption=f"P{i+1}", use_container_width=True)  # noqa: deprecation

# ---------------------------------------------------------------------------
# Render – right panel (extracted rules)
# ---------------------------------------------------------------------------

SECTION_META = {
    "commission_rules":       ("💰", "Commission Rules"),
    "rebate_rules":           ("🏷️", "Rebate Rules"),
    "referral_rules":         ("🤝", "Referral Rules"),
    "price_adjustment_rules": ("📐", "Price Adjustments"),
    "package_rules":          ("📦", "Packages"),
}


def render_rules_panel(rules: dict | None, memo_id: str):
    if not rules or "rules" not in rules:
        st.info("No extracted rules available.")
        return

    # Track flagged rules in session state
    flag_key = f"flagged_{memo_id}"
    if flag_key not in st.session_state:
        st.session_state[flag_key] = set()

    rule_sections = rules["rules"]
    for section_key, (icon, title) in SECTION_META.items():
        items = rule_sections.get(section_key, [])
        if not items:
            continue

        st.markdown(f'<div class="section-header">{icon} {title} ({len(items)})</div>', unsafe_allow_html=True)

        for rule in items:
            rid = rule.get("rule_id", "?")
            rname = rule.get("rule_name", "Untitled")
            is_flagged = rid in st.session_state[flag_key]

            card_cls = "rule-card-flagged" if is_flagged else "rule-card"
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

            # Flag / unflag toggle
            btn_label = "🚩 Unflag" if is_flagged else "🏳️ Flag mismatch"
            if st.button(btn_label, key=f"flag_{memo_id}_{rid}"):
                if is_flagged:
                    st.session_state[flag_key].discard(rid)
                else:
                    st.session_state[flag_key].add(rid)
                st.rerun()

    # Summary of flagged
    flagged = st.session_state[flag_key]
    if flagged:
        st.warning(f"⚠️ {len(flagged)} rule(s) flagged: {', '.join(sorted(flagged))}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.markdown('<div class="main-header">🔍 Memorandum Review</div>', unsafe_allow_html=True)

    memos = load_store()
    if not memos:
        st.error("No memos in the store."); return

    # Pick memo to review
    qp = st.query_params
    target_id = qp.get("memo_id", memos[0]["memo_id"])
    memo = next((m for m in memos if m["memo_id"] == target_id), memos[0])

    # Memo selector (for easy switching)
    options = {m["memo_id"]: f'{m["memo_reference"]} ({m["status"].upper()})' for m in memos}
    selected_id = st.selectbox("Select memo", list(options.keys()), format_func=lambda k: options[k],
                               index=list(options.keys()).index(memo["memo_id"]))
    if selected_id != target_id:
        st.query_params["memo_id"] = selected_id
        st.rerun()

    memo = next(m for m in memos if m["memo_id"] == selected_id)

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

    with col_left:
        st.markdown('<div class="section-header">📄 Original Memo</div>', unsafe_allow_html=True)
        render_images_panel(memo.get("image_files", []))

    with col_right:
        st.markdown('<div class="section-header">📋 Extracted Rules</div>', unsafe_allow_html=True)
        rules = load_rules(memo.get("rules_file"))
        render_rules_panel(rules, memo["memo_id"])

    # Action buttons
    st.markdown("---")

    flagged_key = f"flagged_{memo['memo_id']}"
    flagged = st.session_state.get(flagged_key, set())

    acol1, acol2, acol3, _ = st.columns([1, 1, 1, 2])
    with acol1:
        if st.button("✅ Approve Memo", type="primary", disabled=memo["status"] == "approved"):
            for m in memos:
                if m["memo_id"] == memo["memo_id"]:
                    m["status"] = "approved"
            save_store(memos)
            st.success("Memo approved."); st.rerun()
    with acol2:
        if st.button("❌ Reject Memo", disabled=memo["status"] == "rejected"):
            note = f"Rejected with {len(flagged)} flagged rule(s): {', '.join(sorted(flagged))}" if flagged else "Rejected by reviewer."
            for m in memos:
                if m["memo_id"] == memo["memo_id"]:
                    m["status"] = "rejected"
                    m["reviewer_notes"] = note
            save_store(memos)
            st.warning("Memo rejected."); st.rerun()
    with acol3:
        st.info("Inbox: `streamlit run app_memo_inbox.py --server.port 8503`")


if __name__ == "__main__":
    main()
