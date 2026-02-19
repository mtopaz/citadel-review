#!/usr/bin/env python
"""
CITADEL Blinded Validation Review — Streamlit Cloud Version

Three reviewers independently classify 200 stratified references as
Fabricated / Citation Error / Unsure. No system verdicts shown — fully blinded.

Persistence: SQLite in /tmp (ephemeral) + JSON download/upload for backup.
Each reviewer's verdicts are auto-saved and can be exported/imported.
"""

import streamlit as st
import sqlite3
import json
import os
import io
import urllib.parse
from datetime import datetime

st.set_page_config(
    page_title="CITADEL Blinded Review",
    page_icon="C",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_PATH = os.path.join(BASE_DIR, "data", "review_sample_200.json")
# Use /tmp on Streamlit Cloud (writable), fallback to local for dev
VERDICTS_DIR = "/tmp/citadel_verdicts" if os.path.exists("/tmp") and not os.name == 'nt' else os.path.join(BASE_DIR, "data", "verdicts")
os.makedirs(VERDICTS_DIR, exist_ok=True)

# ─── CSS (based on Nir's design) ──────────────────────────────────────────

st.html("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
    .block-container { padding-top: 1rem !important; max-width: 1400px !important; }
    section[data-testid="stSidebar"] { display: none; }

    .topbar {
        display: flex; align-items: center; justify-content: space-between;
        padding: 10px 0; margin-bottom: 16px;
        border-bottom: 1px solid #e0ddd5;
    }
    .topbar-left {
        display: flex; align-items: center; gap: 16px;
    }
    .logo {
        font-family: 'DM Mono', monospace; font-size: 15px; font-weight: 500;
        letter-spacing: 3px; color: #8b6914; text-transform: uppercase;
    }
    .logo-sub {
        font-size: 12px; color: #918e85; font-weight: 400; letter-spacing: 1px;
        padding-left: 16px; border-left: 1px solid #e0ddd5;
    }
    .progress-pill {
        display: flex; align-items: center; gap: 8px;
        font-family: 'DM Mono', monospace; font-size: 13px; color: #555550;
    }
    .progress-bar-bg {
        width: 120px; height: 4px; background: #e0ddd5;
        border-radius: 2px; overflow: hidden;
    }
    .progress-bar-fill {
        height: 100%; background: #8b6914; border-radius: 2px;
    }

    .section-label {
        font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 2px;
        text-transform: uppercase; color: #918e85; margin-bottom: 10px; margin-top: 18px;
    }

    .citation-card {
        background: #ffffff; border: 1px solid #e0ddd5; border-radius: 8px;
        padding: 20px; margin-bottom: 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    .citation-title {
        font-family: 'DM Sans', sans-serif; font-size: 16px; font-weight: 600;
        line-height: 1.45; color: #1a1a1a; margin-bottom: 12px;
    }
    .meta-row {
        display: flex; align-items: baseline; gap: 10px;
        font-size: 13px; padding: 3px 0;
    }
    .meta-label {
        font-family: 'DM Mono', monospace; font-size: 11px; color: #918e85;
        min-width: 70px; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .meta-value { color: #555550; }
    .meta-value a { color: #2b6cb0; text-decoration: none; }
    .meta-value a:hover { text-decoration: underline; }

    .divider {
        display: flex; align-items: center; gap: 12px; margin: 18px 0;
    }
    .divider-line { flex: 1; height: 1px; background: #e0ddd5; }
    .divider-text {
        font-family: 'DM Mono', monospace; font-size: 10px; letter-spacing: 2px;
        text-transform: uppercase; color: #918e85;
    }

    .actual-card {
        background: #ffffff; border: 1px solid #e0ddd5;
        border-left: 3px solid #c8891f; border-radius: 8px;
        padding: 20px; margin-bottom: 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    .actual-title {
        font-family: 'DM Sans', sans-serif; font-size: 14px; font-weight: 500;
        color: #555550; line-height: 1.45;
    }
    .actual-note {
        margin-top: 8px; font-size: 12px; color: #918e85; font-style: italic;
    }

    .source-card {
        background: #fafaf7; border: 1px solid #e0ddd5; border-radius: 8px;
        padding: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    .source-title {
        font-family: 'DM Sans', sans-serif; font-size: 13px;
        color: #555550; line-height: 1.4;
    }
    .source-meta {
        font-size: 12px; color: #918e85; margin-top: 6px;
    }

    .search-btn {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 8px 14px; background: #ffffff; border: 1px solid #e0ddd5;
        border-radius: 6px; color: #555550; font-family: 'DM Sans', sans-serif;
        font-size: 13px; font-weight: 500; cursor: pointer; text-decoration: none;
        transition: all 0.15s ease; box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        margin: 3px;
    }
    .search-btn:hover {
        border-color: #c8c4ba; color: #1a1a1a;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }

    .keyboard-hint {
        font-size: 11px; color: #918e85; text-align: center; margin-top: 8px;
        font-family: 'DM Mono', monospace;
    }
    kbd {
        display: inline-block; padding: 1px 6px; background: #fff;
        border: 1px solid #e0ddd5; border-radius: 3px; font-size: 10px;
        font-family: 'DM Mono', monospace; box-shadow: 0 1px 0 #e0ddd5;
    }
</style>
""")


# ─── Load data ─────────────────────────────────────────────────────────────

@st.cache_data
def load_sample():
    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_reviewer_id():
    if "reviewer_id" not in st.session_state:
        st.session_state.reviewer_id = None
    return st.session_state.reviewer_id


def get_verdicts_db(reviewer_id):
    return os.path.join(VERDICTS_DIR, f"reviewer_{reviewer_id}.db")


def init_verdicts_db(reviewer_id):
    db_path = get_verdicts_db(reviewer_id)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS verdicts (
            review_id INTEGER PRIMARY KEY,
            pmc_id TEXT,
            ref_number INTEGER,
            verdict TEXT,
            notes TEXT,
            reviewed_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_verdict(reviewer_id, review_id, pmc_id, ref_number, verdict, notes=""):
    db_path = get_verdicts_db(reviewer_id)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT OR REPLACE INTO verdicts (review_id, pmc_id, ref_number, verdict, notes, reviewed_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (review_id, pmc_id, ref_number, verdict, notes, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def load_verdicts(reviewer_id):
    db_path = get_verdicts_db(reviewer_id)
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT review_id, verdict, notes, reviewed_at FROM verdicts").fetchall()
    conn.close()
    return {r[0]: {"verdict": r[1], "notes": r[2], "reviewed_at": r[3]} for r in rows}


def export_verdicts_json(reviewer_id):
    """Export all verdicts as JSON for backup/download."""
    verdicts = load_verdicts(reviewer_id)
    export = {
        "reviewer": reviewer_id,
        "exported_at": datetime.now().isoformat(),
        "total_reviewed": len(verdicts),
        "verdicts": [
            {"review_id": rid, **data}
            for rid, data in sorted(verdicts.items())
        ]
    }
    return json.dumps(export, indent=2)


def import_verdicts_json(reviewer_id, json_data):
    """Import verdicts from JSON backup."""
    data = json.loads(json_data)
    db_path = get_verdicts_db(reviewer_id)
    conn = sqlite3.connect(db_path)
    count = 0
    for v in data.get("verdicts", []):
        conn.execute("""
            INSERT OR REPLACE INTO verdicts (review_id, pmc_id, ref_number, verdict, notes, reviewed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (v["review_id"], v.get("pmc_id", ""), v.get("ref_number", 0),
              v["verdict"], v.get("notes", ""), v.get("reviewed_at", "")))
        count += 1
    conn.commit()
    conn.close()
    return count


def get_next_unreviewed(verdicts, total):
    for i in range(1, total + 1):
        if i not in verdicts:
            return i
    return None


# ─── Reviewer login ─────────────────────────────────────────────────────

sample = load_sample()
total = len(sample)

reviewer_id = get_reviewer_id()

if reviewer_id is None:
    st.html("""
    <div style="max-width:480px; margin:80px auto; text-align:center;">
        <div style="font-family:'DM Mono',monospace; font-size:15px; font-weight:500;
                    letter-spacing:3px; color:#8b6914; text-transform:uppercase; margin-bottom:24px;">
            Citadel
        </div>
        <div style="font-family:'DM Sans',sans-serif; font-size:22px; font-weight:600; margin-bottom:8px;">
            Blinded Validation Review
        </div>
        <div style="font-family:'DM Sans',sans-serif; font-size:14px; color:#918e85; margin-bottom:32px;">
            200 references to classify &middot; 3 independent reviewers
        </div>
    </div>
    """)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        name = st.text_input("Your name (first name is fine)", key="reviewer_name")

        # Import previous session
        uploaded = st.file_uploader("Resume previous session (optional)", type=["json"], key="import_file")

        if st.button("Start Review", type="primary", use_container_width=True):
            if name.strip():
                rid = name.strip().lower().replace(" ", "_")
                st.session_state.reviewer_id = rid
                init_verdicts_db(rid)
                # Import if file uploaded
                if uploaded is not None:
                    json_data = uploaded.read().decode("utf-8")
                    count = import_verdicts_json(rid, json_data)
                    st.session_state.import_msg = f"Imported {count} verdicts from backup"
                st.rerun()
            else:
                st.warning("Please enter your name")

    st.html("""
    <div style="max-width:480px; margin:24px auto; font-family:'DM Sans',sans-serif;
                font-size:13px; color:#918e85; line-height:1.7;">
        <b>Instructions:</b><br>
        For each reference, determine whether the cited paper exists.<br>
        Use the search links to check PubMed, Google Scholar, CrossRef, and OpenAlex.<br><br>
        <b>Verdicts:</b><br>
        <b style="color:#c23030;">Fabricated Citation</b> &mdash; Paper does not exist anywhere<br>
        <b style="color:#a06b1a;">Citation Error</b> &mdash; Paper exists but identifiers (PMID/DOI) are wrong<br>
        <b style="color:#555550;">Unsure</b> &mdash; Cannot determine with available evidence<br><br>
        <b>Persistence:</b><br>
        Verdicts are saved during your session. Use the <b>Export</b> button regularly<br>
        to download a backup JSON. If the app restarts, upload it on login to resume.
    </div>
    """)
    st.stop()


# ─── Main review interface ────────────────────────────────────────────────

init_verdicts_db(reviewer_id)
verdicts = load_verdicts(reviewer_id)
reviewed_count = len(verdicts)

# Show import message if any
if "import_msg" in st.session_state:
    st.success(st.session_state.import_msg)
    del st.session_state.import_msg
    verdicts = load_verdicts(reviewer_id)
    reviewed_count = len(verdicts)

# Navigation
if "current_idx" not in st.session_state:
    next_unrev = get_next_unreviewed(verdicts, total)
    st.session_state.current_idx = (next_unrev or 1) - 1

idx = st.session_state.current_idx
entry = sample[idx]
review_id = entry["review_id"]
existing = verdicts.get(review_id)

# Top bar
pct_done = reviewed_count / total * 100

st.html(f"""
<div class="topbar">
    <div class="topbar-left">
        <div class="logo">Citadel</div>
        <div class="logo-sub">Blinded Review</div>
    </div>
    <div style="font-family:'DM Mono',monospace; font-size:13px; color:#555550;">
        Reviewer: {reviewer_id} &middot; #{review_id} of {total}
    </div>
    <div class="progress-pill">
        <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:{pct_done:.1f}%;"></div></div>
        <span>{reviewed_count} / {total}</span>
    </div>
</div>
""")

# Two-column layout
left, right = st.columns([1, 1], gap="large")

with left:
    # ── Claimed Citation ──
    title = entry.get("claimed_title", "N/A")
    pmid = entry.get("claimed_pmid", "")
    doi = entry.get("claimed_doi", "")
    authors = entry.get("claimed_authors", "")
    venue = entry.get("claimed_venue", "")
    year = entry.get("claimed_year", "")

    pmid_link = f'<a href="https://pubmed.ncbi.nlm.nih.gov/{pmid}/" target="_blank">{pmid}</a>' if pmid else "N/A"
    doi_link = f'<a href="https://doi.org/{doi}" target="_blank">{doi}</a>' if doi else "N/A"

    st.html(f"""
    <div class="section-label">Claimed Citation &mdash; Ref #{entry.get('ref_number', '?')}</div>
    <div class="citation-card">
        <div class="citation-title">{title}</div>
        <div>
            <div class="meta-row"><span class="meta-label">Authors</span><span class="meta-value">{authors or 'N/A'}</span></div>
            <div class="meta-row"><span class="meta-label">Journal</span><span class="meta-value">{venue or 'N/A'} {year or ''}</span></div>
            <div class="meta-row"><span class="meta-label">PMID</span><span class="meta-value">{pmid_link}</span></div>
            <div class="meta-row"><span class="meta-label">DOI</span><span class="meta-value">{doi_link}</span></div>
        </div>
    </div>
    """)

    # ── What PMID actually resolves to ──
    actual_pmid = entry.get("actual_title_pmid", "")
    actual_doi = entry.get("actual_title_doi", "")
    actual = actual_pmid or actual_doi or ""

    if actual and actual != title:
        st.html(f"""
        <div class="divider">
            <div class="divider-line"></div>
            <div class="divider-text">PMID resolves to</div>
            <div class="divider-line"></div>
        </div>
        <div class="actual-card">
            <div class="actual-title">{actual[:300]}</div>
            <div class="actual-note">This is the paper that actually lives at PMID {pmid}</div>
        </div>
        """)

    # ── Source paper ──
    source_title = entry.get("paper_title", "")
    source_journal = entry.get("journal", "")
    pmc_id = entry.get("pmc_id", "")

    if source_title:
        pmc_link = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
        st.html(f"""
        <div class="divider">
            <div class="divider-line"></div>
            <div class="divider-text">Source paper (citing article)</div>
            <div class="divider-line"></div>
        </div>
        <div class="source-card">
            <div class="source-title"><a href="{pmc_link}" target="_blank" style="color:#555550; text-decoration:none;">{source_title}</a></div>
            <div class="source-meta">{source_journal} &middot; {pmc_id}</div>
        </div>
        """)


with right:
    # ── Search links ──
    encoded_title = urllib.parse.quote(title[:200])
    first_author = (authors.split(";")[0].split(",")[0].strip() if authors else "").replace(" ", "+")
    year_int = int(year) if year and str(year).isdigit() else 2024
    year_range_lo = year_int - 1
    year_range_hi = year_int + 1

    st.html(f"""
    <div class="section-label">Search &mdash; Title</div>
    <div style="display:flex; flex-wrap:wrap; margin-bottom:8px;">
        <a class="search-btn" href="https://pubmed.ncbi.nlm.nih.gov/?term={encoded_title}" target="_blank">PubMed</a>
        <a class="search-btn" href="https://scholar.google.com/scholar?q={encoded_title}" target="_blank">Google Scholar</a>
        <a class="search-btn" href="https://search.crossref.org/?q={encoded_title}&from_ui=yes" target="_blank">CrossRef</a>
        <a class="search-btn" href="https://api.openalex.org/works?search={encoded_title}" target="_blank">OpenAlex</a>
    </div>
    """)

    if first_author:
        st.html(f"""
        <div class="section-label">Search &mdash; Author + Year</div>
        <div style="margin-bottom:16px;">
            <a class="search-btn" href="https://pubmed.ncbi.nlm.nih.gov/?term={first_author}%5Bfirst+author%5D+AND+{year_range_lo}%3A{year_range_hi}%5Bdp%5D" target="_blank">
                PubMed &mdash; {first_author.replace('+', ' ')} [{year_range_lo}-{year_range_hi}]
            </a>
        </div>
        """)

    # ── Verdict buttons ──
    st.html('<div class="section-label">Your Verdict</div>')

    verdict_options = {
        "fabricated": "Fabricated Citation \u2014 Paper does not exist anywhere",
        "citation_error": "Citation Error \u2014 Paper exists but PMID/DOI are wrong",
        "unsure": "Unsure \u2014 Cannot determine with available evidence",
    }

    default_idx = 0
    if existing:
        v = existing["verdict"]
        keys = list(verdict_options.keys())
        if v in keys:
            default_idx = keys.index(v)

    verdict = st.radio(
        "Verdict",
        options=list(verdict_options.keys()),
        format_func=lambda x: verdict_options[x],
        index=default_idx,
        label_visibility="collapsed",
        key=f"verdict_{review_id}",
    )

    notes = st.text_area(
        "Notes (optional)",
        value=existing["notes"] if existing else "",
        placeholder="e.g., Title appears to be mashup of keywords. Found similar paper by same author but different title.",
        height=80,
        key=f"notes_{review_id}",
    )

    # ── Action buttons ──
    col_prev, col_save, col_skip = st.columns([1, 2, 1])

    with col_prev:
        if st.button("< Prev", use_container_width=True, disabled=(idx == 0)):
            st.session_state.current_idx = max(0, idx - 1)
            st.rerun()

    with col_save:
        if st.button("Save & Next >", type="primary", use_container_width=True):
            save_verdict(
                reviewer_id, review_id,
                entry["pmc_id"], entry["ref_number"],
                verdict, notes,
            )
            if idx < total - 1:
                st.session_state.current_idx = idx + 1
            st.rerun()

    with col_skip:
        if st.button("Skip >", use_container_width=True):
            if idx < total - 1:
                st.session_state.current_idx = idx + 1
            st.rerun()

    # Status indicator
    if existing:
        st.success(f"Previously marked: **{existing['verdict']}**")

    st.html("""
    <div class="keyboard-hint" style="margin-top:16px;">
        Use <kbd>Tab</kbd> to navigate &middot; <kbd>Enter</kbd> to submit
    </div>
    """)

    # ── Jump to entry ──
    st.html('<div class="section-label" style="margin-top:24px;">Navigation</div>')

    jump_col1, jump_col2 = st.columns(2)
    with jump_col1:
        jump = st.number_input("Go to entry #", min_value=1, max_value=total, value=idx + 1, key="jump_to")
        if st.button("Go", key="go_btn"):
            st.session_state.current_idx = jump - 1
            st.rerun()
    with jump_col2:
        next_unrev = get_next_unreviewed(verdicts, total)
        if next_unrev:
            st.html(f'<div style="font-size:13px; color:#918e85; margin-top:8px;">Next unreviewed: #{next_unrev}</div>')
            if st.button("Jump to next unreviewed", key="jump_unrev"):
                st.session_state.current_idx = next_unrev - 1
                st.rerun()
        else:
            st.html('<div style="font-size:13px; color:#2d8a52; margin-top:8px;">All 200 reviewed!</div>')

    # ── Summary stats ──
    if reviewed_count > 0:
        st.html('<div class="section-label" style="margin-top:24px;">Your Progress</div>')
        v_counts = {}
        for v in verdicts.values():
            v_counts[v["verdict"]] = v_counts.get(v["verdict"], 0) + 1

        stats_html = f"""
        <div style="font-family:'DM Mono',monospace; font-size:13px;">
            <span style="color:#c23030;">Fabricated: {v_counts.get('fabricated', 0)}</span> &middot;
            <span style="color:#a06b1a;">Citation Error: {v_counts.get('citation_error', 0)}</span> &middot;
            <span style="color:#555550;">Unsure: {v_counts.get('unsure', 0)}</span> &middot;
            <span>Total: {reviewed_count}/{total}</span>
        </div>
        """
        st.html(stats_html)

    # ── Export / Import verdicts ──
    st.html('<div class="section-label" style="margin-top:24px;">Backup &amp; Export</div>')

    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        if reviewed_count > 0:
            json_export = export_verdicts_json(reviewer_id)
            st.download_button(
                f"Export verdicts ({reviewed_count})",
                data=json_export,
                file_name=f"citadel_verdicts_{reviewer_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json",
                use_container_width=True,
            )
    with exp_col2:
        st.html(f'<div style="font-size:11px; color:#918e85; margin-top:10px;">Export regularly to avoid data loss if the app restarts.</div>')

    # Logout
    st.html('<div style="margin-top:24px;"></div>')
    if st.button("Logout", key="logout"):
        st.session_state.reviewer_id = None
        if "current_idx" in st.session_state:
            del st.session_state.current_idx
        st.rerun()
