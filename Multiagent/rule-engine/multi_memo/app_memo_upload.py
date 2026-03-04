"""
Add New Memorandum – Upload, Extract, Review
1. User uploads a PDF.
2. PDF is converted to page images (via PyMuPDF / fitz).
3. OCR is run on each page image (text + table).
4. The Rule Extraction agent converts OCR output into structured rules JSON.
5. Extracted rules are displayed for the user to review before saving.

All heavy work (OCR + extraction) runs behind a spinner so the user sees progress.
"""

import streamlit as st
import json
import sys
import uuid
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CURRENT_DIR = Path(__file__).parent
ARTIFACT_DIR = CURRENT_DIR.parent.parent / "artifact"
MEMO_IMG_DIR = CURRENT_DIR.parent.parent.parent / "memo"
STORE_PATH = CURRENT_DIR / "memo_store.json"

# Ensure the OCR & rule-extract modules are importable
OCR_DIR = CURRENT_DIR.parent.parent / "ocr"
RULE_EXTRACT_DIR = CURRENT_DIR.parent.parent / "rule-extract"
sys.path.insert(0, str(OCR_DIR))
sys.path.insert(0, str(RULE_EXTRACT_DIR))
sys.path.insert(0, str(CURRENT_DIR))

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Avaland · Add New Memorandum",
    page_icon="📤",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem; font-weight: bold; color: #1E3A5F;
        text-align: center; padding: 1rem;
        border-bottom: 3px solid #E8B54B; margin-bottom: 1rem;
    }
    .step-badge {
        display: inline-flex; align-items: center; justify-content: center;
        width: 36px; height: 36px; border-radius: 50%;
        background: #1E3A5F; color: white; font-weight: bold;
        margin-right: 0.6rem; font-size: 1rem;
    }
    .step-badge-done {
        background: #28a745;
    }
    .step-badge-active {
        background: #ffc107; color: #333;
    }
    .step-header {
        background: linear-gradient(90deg, #1E3A5F 0%, #2E5A8F 100%);
        color: white; padding: 0.6rem 1rem; border-radius: 8px;
        font-size: 1rem; font-weight: 600; margin: 0.8rem 0 0.4rem 0;
    }
    .section-header {
        background: linear-gradient(90deg, #1E3A5F 0%, #2E5A8F 100%);
        color: white; padding: 0.6rem 1rem; border-radius: 8px;
        font-weight: 600; margin-bottom: 0.4rem;
    }
    .progress-card {
        background: #f8f9fa; border: 1px solid #dee2e6;
        border-radius: 10px; padding: 1rem; margin: 0.5rem 0;
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


def next_memo_id(memos: list[dict]) -> str:
    existing_nums = []
    for m in memos:
        mid = m.get("memo_id", "")
        if mid.startswith("MEMO_"):
            try:
                existing_nums.append(int(mid.split("_")[1]))
            except ValueError:
                pass
    next_num = max(existing_nums, default=0) + 1
    return f"MEMO_{next_num:03d}"

# ---------------------------------------------------------------------------
# Pipeline functions
# ---------------------------------------------------------------------------

def convert_pdf_to_images(pdf_bytes: bytes, pdf_name: str) -> list[Path]:
    """Convert uploaded PDF bytes to images using PyMuPDF."""
    import fitz  # PyMuPDF

    stem = Path(pdf_name).stem
    output_dir = MEMO_IMG_DIR / f"{stem}_upload"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write bytes to a temp file for fitz
    tmp = output_dir / f"_tmp_{pdf_name}"
    tmp.write_bytes(pdf_bytes)

    doc = fitz.open(str(tmp))
    image_paths: list[Path] = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=300)
        out = output_dir / f"{stem}_page-{i+1:04d}.jpg"
        pix.save(str(out))
        image_paths.append(out)
    doc.close()
    tmp.unlink(missing_ok=True)

    return image_paths


def run_ocr_text(image_paths: list[Path]) -> dict:
    """Run text OCR on page images (calls ocr.py functions)."""
    from ocr import ocr_images_with_chat_model, _maybe_parse_json

    user_prompt = (
        "Perform OCR on the image. Output only valid JSON (no markdown, no extra text). "
        "Follow the JSON schema described in the instructions and set confidence values realistically."
    )

    content = ocr_images_with_chat_model(image_paths=image_paths, user_prompt=user_prompt)
    return {
        "mode": "batch",
        "files": [p.name for p in image_paths],
        "model_output": _maybe_parse_json(content),
    }


def run_ocr_table(image_paths: list[Path]) -> dict:
    """Run table OCR on page images (calls ocrtable.py functions)."""
    from ocrtable import ocr_images_with_chat_model as ocr_table_batch, _maybe_parse_json

    user_prompt = (
        "You are a TABLE-ONLY OCR and DOCUMENT STRUCTURE engine.\n"
        "Your role is STRICTLY LIMITED to tables extraction.\n"
        "Return valid JSON only. Detect all tables in the document."
    )

    content = ocr_table_batch(image_paths=image_paths, user_prompt=user_prompt)
    return {
        "mode": "batch",
        "files": [p.name for p in image_paths],
        "model_output": _maybe_parse_json(content),
    }


def run_rule_extraction(text_data: dict, table_data: dict) -> dict:
    """Run the rule extraction agent on OCR outputs."""
    from rule import format_ocr_for_agent, extract_rules
    ocr_content = format_ocr_for_agent(text_data, table_data)
    return extract_rules(ocr_content)

# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

SECTION_META = {
    "commission_rules":       ("💰", "Commission Rules"),
    "rebate_rules":           ("🏷️", "Rebate Rules"),
    "referral_rules":         ("🤝", "Referral Rules"),
    "price_adjustment_rules": ("📐", "Price Adjustments"),
    "package_rules":          ("📦", "Packages"),
}


def render_extracted_rules(rules: dict):
    """Display extracted rules in a readable format."""
    if not rules or "rules" not in rules:
        st.warning("No rules could be extracted. The extraction may have failed or the document format is not recognized.")
        if "raw_response" in rules:
            with st.expander("Raw model response"):
                st.code(rules["raw_response"])
        return

    # Summary metrics
    rule_sections = rules["rules"]
    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    mc1.metric("Commission", len(rule_sections.get("commission_rules", [])))
    mc2.metric("Rebate", len(rule_sections.get("rebate_rules", [])))
    mc3.metric("Referral", len(rule_sections.get("referral_rules", [])))
    mc4.metric("Price Adj.", len(rule_sections.get("price_adjustment_rules", [])))
    mc5.metric("Package", len(rule_sections.get("package_rules", [])))

    # Confidence
    conf = rules.get("extraction_confidence")
    if conf is not None:
        st.progress(conf, text=f"Extraction confidence: {conf:.0%}")

    # Warnings
    for w in rules.get("warnings", []):
        st.warning(f"⚠️ {w}")

    # Detailed rules
    for section_key, (icon, title) in SECTION_META.items():
        items = rule_sections.get(section_key, [])
        if not items:
            continue
        st.markdown(f'<div class="section-header">{icon} {title} ({len(items)})</div>', unsafe_allow_html=True)
        for rule in items:
            rid = rule.get("rule_id", "?")
            rname = rule.get("rule_name", "Untitled")
            st.markdown(f"**{rid}** — {rname}")
            conditions = rule.get("conditions", [])
            if conditions:
                if isinstance(conditions[0], dict):
                    rows = []
                    for c in conditions:
                        rows.append({
                            "Condition": c.get("condition", ""),
                            "Value": str(
                                c.get("commission_percentage",
                                c.get("rebate_percentage",
                                c.get("adjustment_amount", "")))
                            ),
                            "Description": c.get("description", ""),
                        })
                    st.table(rows)
                else:
                    for c in conditions:
                        st.markdown(f"- {c}")
            notes = rule.get("notes", [])
            if notes:
                st.caption("Notes: " + " · ".join(notes))
            st.markdown("---")

    # Pseudo-code preview
    pseudo = rules.get("pseudo_code", {})
    if pseudo:
        with st.expander("📝 Generated Pseudo-code"):
            for name, code in pseudo.items():
                st.markdown(f"**{name}**")
                st.code(code, language="python")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.markdown('<div class="main-header">📤 Add New Memorandum</div>', unsafe_allow_html=True)

    # ── Session state initialisation ──
    if "upload_step" not in st.session_state:
        st.session_state.upload_step = "upload"        # upload | extracting | review
    if "upload_images" not in st.session_state:
        st.session_state.upload_images = []
    if "upload_rules" not in st.session_state:
        st.session_state.upload_rules = None
    if "upload_pdf_name" not in st.session_state:
        st.session_state.upload_pdf_name = ""
    if "upload_text_ocr" not in st.session_state:
        st.session_state.upload_text_ocr = None
    if "upload_table_ocr" not in st.session_state:
        st.session_state.upload_table_ocr = None

    # ── Progress indicator ──
    steps = ["Upload PDF", "Extract Rules", "Review & Save"]
    current = {"upload": 0, "extracting": 1, "review": 2}.get(st.session_state.upload_step, 0)
    cols = st.columns(len(steps))
    for i, (col, label) in enumerate(zip(cols, steps)):
        if i < current:
            col.markdown(f'<span class="step-badge step-badge-done">✓</span> **{label}**', unsafe_allow_html=True)
        elif i == current:
            col.markdown(f'<span class="step-badge step-badge-active">{i+1}</span> **{label}**', unsafe_allow_html=True)
        else:
            col.markdown(f'<span class="step-badge">{i+1}</span> {label}', unsafe_allow_html=True)

    st.markdown("---")

    # =====================================================================
    # STEP 1 – Upload
    # =====================================================================
    if st.session_state.upload_step == "upload":
        st.subheader("Step 1: Upload Memorandum PDF")
        uploaded = st.file_uploader("Choose a PDF file", type=["pdf"], key="pdf_uploader")

        if uploaded is not None:
            st.success(f"Uploaded: **{uploaded.name}** ({uploaded.size / 1024:.1f} KB)")

            # Convert to images immediately for preview
            with st.spinner("Converting PDF to page images…"):
                pdf_bytes = uploaded.read()
                image_paths = convert_pdf_to_images(pdf_bytes, uploaded.name)
                st.session_state.upload_images = image_paths
                st.session_state.upload_pdf_name = uploaded.name

            st.markdown(f"**{len(image_paths)} page(s) detected.**")

            # Preview thumbnails
            thumb_cols = st.columns(min(len(image_paths), 5))
            for i, (col, img) in enumerate(zip(thumb_cols, image_paths)):
                col.image(str(img), caption=f"Page {i+1}", use_container_width=True)

            st.markdown("---")
            if st.button("🚀 Extract Rules", type="primary", use_container_width=True):
                st.session_state.upload_step = "extracting"
                st.rerun()

    # =====================================================================
    # STEP 2 – Extraction pipeline
    # =====================================================================
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

        # 2a – Text OCR
        progress.progress(10, text="Running text OCR…")
        with st.spinner("Running text OCR on all pages…"):
            text_ocr = run_ocr_text(image_paths)
            st.session_state.upload_text_ocr = text_ocr

        progress.progress(40, text="Text OCR complete. Running table OCR…")

        # 2b – Table OCR
        with st.spinner("Running table OCR on all pages…"):
            table_ocr = run_ocr_table(image_paths)
            st.session_state.upload_table_ocr = table_ocr

        progress.progress(70, text="Table OCR complete. Extracting rules…")

        # 2c – Rule extraction
        with st.spinner("Rule Extraction Agent is analysing OCR output…"):
            rules = run_rule_extraction(text_ocr, table_ocr)
            st.session_state.upload_rules = rules

        progress.progress(100, text="Extraction complete!")

        st.session_state.upload_step = "review"
        st.rerun()

    # =====================================================================
    # STEP 3 – Review & Save
    # =====================================================================
    elif st.session_state.upload_step == "review":
        st.subheader("Step 3: Review Extracted Rules")

        rules = st.session_state.upload_rules
        image_paths = st.session_state.upload_images
        pdf_name = st.session_state.upload_pdf_name

        if rules is None:
            st.error("No extraction results found.")
            if st.button("← Start over"):
                st.session_state.upload_step = "upload"
                st.rerun()
            return

        # Side-by-side: images vs rules
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown('<div class="section-header">📄 Original Memo Pages</div>', unsafe_allow_html=True)
            if image_paths:
                page_idx = st.selectbox("Page", range(len(image_paths)),
                                        format_func=lambda i: f"Page {i+1}", key="review_page")
                st.image(str(image_paths[page_idx]), caption=f"Page {page_idx+1}", use_container_width=True)

        with col_right:
            st.markdown('<div class="section-header">📋 Extracted Rules</div>', unsafe_allow_html=True)
            render_extracted_rules(rules)

        st.markdown("---")

        # Metadata form for saving
        st.subheader("Save Memorandum")
        fc1, fc2 = st.columns(2)
        with fc1:
            memo_ref = st.text_input("Memo Reference", value=rules.get("memo_reference", ""))
            project_name = st.text_input("Project Name", value=rules.get("project_name", ""))
        with fc2:
            eff = rules.get("effective_period", {})
            start_date = st.text_input("Effective Start Date", value=eff.get("start_date", ""))
            end_date = st.text_input("Effective End Date", value=eff.get("end_date", ""))

        st.markdown("---")
        btn1, btn2, btn3 = st.columns([1, 1, 2])

        with btn1:
            if st.button("💾 Save as Pending", type="primary", use_container_width=True):
                _save_new_memo(rules, image_paths, pdf_name, memo_ref, project_name, start_date, end_date, "pending")
                st.success("Memo saved as **Pending**! Redirecting to Inbox…")
                _reset_upload_state()
                st.rerun()

        with btn2:
            if st.button("✅ Save & Approve", use_container_width=True):
                _save_new_memo(rules, image_paths, pdf_name, memo_ref, project_name, start_date, end_date, "approved")
                st.success("Memo saved as **Approved**! Redirecting to Inbox…")
                _reset_upload_state()
                st.rerun()

        with btn3:
            if st.button("🗑️ Discard & Start Over", use_container_width=True):
                _reset_upload_state()
                st.rerun()


def _save_new_memo(rules, image_paths, pdf_name, memo_ref, project_name, start_date, end_date, status):
    """Persist the new memo: save rules JSON + add entry to memo_store."""
    memos = load_store()
    memo_id = next_memo_id(memos)

    # Save rules JSON
    rules_filename = f"extracted-rules-{memo_id.lower()}.json"
    rules_path = ARTIFACT_DIR / rules_filename
    rules_path.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")

    # Copy images to central memo folder and record filenames
    image_filenames = []
    for img in image_paths:
        target = MEMO_IMG_DIR / img.name
        if not target.exists():
            shutil.copy2(img, target)
        image_filenames.append(img.name)

    # Rule count
    rs = rules.get("rules", {})
    rule_count = {
        "commission_rules": len(rs.get("commission_rules", [])),
        "rebate_rules": len(rs.get("rebate_rules", [])),
        "referral_rules": len(rs.get("referral_rules", [])),
        "price_adjustment_rules": len(rs.get("price_adjustment_rules", [])),
        "package_rules": len(rs.get("package_rules", [])),
    }

    entry = {
        "memo_id": memo_id,
        "memo_reference": memo_ref or rules.get("memo_reference", memo_id),
        "project_name": project_name or rules.get("project_name", ""),
        "effective_period": {
            "start_date": start_date,
            "end_date": end_date,
        },
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
    save_store(memos)


def _reset_upload_state():
    """Clear upload-related session state."""
    st.session_state.upload_step = "upload"
    st.session_state.upload_images = []
    st.session_state.upload_rules = None
    st.session_state.upload_pdf_name = ""
    st.session_state.upload_text_ocr = None
    st.session_state.upload_table_ocr = None


if __name__ == "__main__":
    main()
