#!/usr/bin/env python
"""
CITADEL Blinded Validation Review — Railway Deployment

Three reviewers independently classify 200 stratified references as
Fabricated / Citation Error / Correct / Unsure. No system verdicts shown — fully blinded.

Persistence: SQLite on Railway's persistent disk. Verdicts survive restarts.
"""

import streamlit as st
import sqlite3
import json
import os
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
VERDICTS_DIR = os.path.join(BASE_DIR, "data", "verdicts")
os.makedirs(VERDICTS_DIR, exist_ok=True)

# ─── CSS ──────────────────────────────────────────────────────────────────

st.html("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
    .block-container { padding-top: 0.5rem !important; padding-bottom: 0 !important; max-width: 1400px !important; }
    section[data-testid="stSidebar"] { display: none; }
    header[data-testid="stHeader"] { display: none; }
    footer { display: none; }
    .stDeployButton { display: none; }

    .topbar {
        display: flex; align-items: center; justify-content: space-between;
        padding: 6px 0; margin-bottom: 8px;
        border-bottom: 1px solid #e0ddd5;
    }
    .topbar-left { display: flex; align-items: center; gap: 16px; }
    .logo {
        font-family: 'DM Mono', monospace; font-size: 14px; font-weight: 500;
        letter-spacing: 3px; color: #8b6914; text-transform: uppercase;
    }
    .logo-sub {
        font-size: 11px; color: #918e85; font-weight: 400; letter-spacing: 1px;
        padding-left: 16px; border-left: 1px solid #e0ddd5;
    }
    .progress-pill {
        display: flex; align-items: center; gap: 8px;
        font-family: 'DM Mono', monospace; font-size: 12px; color: #555550;
    }
    .progress-bar-bg {
        width: 100px; height: 3px; background: #e0ddd5;
        border-radius: 2px; overflow: hidden;
    }
    .progress-bar-fill { height: 100%; background: #8b6914; border-radius: 2px; }

    .section-label {
        font-family: 'DM Mono', monospace; font-size: 9px; letter-spacing: 2px;
        text-transform: uppercase; color: #918e85; margin-bottom: 6px; margin-top: 10px;
    }

    .source-banner {
        background: #f5f4f0; border: 1px solid #e0ddd5; border-radius: 6px;
        padding: 8px 14px; margin-bottom: 8px;
        font-family: 'DM Sans', sans-serif; font-size: 12px; color: #555550;
    }
    .source-banner a { color: #2b6cb0; text-decoration: none; }
    .source-banner a:hover { text-decoration: underline; }
    .source-banner .source-label {
        font-family: 'DM Mono', monospace; font-size: 9px; color: #918e85;
        text-transform: uppercase; letter-spacing: 1px; margin-right: 8px;
    }

    .citation-card {
        background: #ffffff; border: 1px solid #e0ddd5; border-radius: 8px;
        padding: 14px 18px; margin-bottom: 8px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    .citation-title {
        font-family: 'DM Sans', sans-serif; font-size: 15px; font-weight: 600;
        line-height: 1.4; color: #1a1a1a; margin-bottom: 8px;
    }
    .meta-row {
        display: flex; align-items: baseline; gap: 8px;
        font-size: 12px; padding: 2px 0;
    }
    .meta-label {
        font-family: 'DM Mono', monospace; font-size: 10px; color: #918e85;
        min-width: 60px; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .meta-value { color: #555550; }
    .meta-value a { color: #2b6cb0; text-decoration: none; }

    .actual-card {
        background: #fff9ef; border: 1px solid #e0ddd5;
        border-left: 3px solid #c8891f; border-radius: 6px;
        padding: 10px 14px; margin-bottom: 8px;
    }
    .actual-title {
        font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 500;
        color: #555550; line-height: 1.4;
    }
    .actual-note {
        margin-top: 4px; font-size: 11px; color: #918e85; font-style: italic;
    }

    .search-btn {
        display: inline-flex; align-items: center; gap: 4px;
        padding: 5px 10px; background: #ffffff; border: 1px solid #e0ddd5;
        border-radius: 5px; color: #555550; font-family: 'DM Sans', sans-serif;
        font-size: 12px; font-weight: 500; cursor: pointer; text-decoration: none;
        transition: all 0.15s ease; box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        margin: 2px;
    }
    .search-btn:hover {
        border-color: #c8c4ba; color: #1a1a1a;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
    }
</style>
""")


# ─── Data & DB functions ──────────────────────────────────────────────────

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
            pmc_id TEXT, ref_number INTEGER,
            verdict TEXT, notes TEXT, reviewed_at TEXT
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
    verdicts = load_verdicts(reviewer_id)
    export = {
        "reviewer": reviewer_id,
        "exported_at": datetime.now().isoformat(),
        "total_reviewed": len(verdicts),
        "verdicts": [{"review_id": rid, **data} for rid, data in sorted(verdicts.items())]
    }
    return json.dumps(export, indent=2)

def get_next_unreviewed(verdicts, total):
    for i in range(1, total + 1):
        if i not in verdicts:
            return i
    return None


# ─── Login ────────────────────────────────────────────────────────────────

# ─── Admin page (?admin=1) ───────────────────────────────────────────────

def admin_page():
    """Admin dashboard: shows all reviewers' progress + full backup download."""
    st.html("""
    <div style="max-width:800px; margin:20px auto;">
        <div style="font-family:'DM Mono',monospace; font-size:15px; font-weight:500;
                    letter-spacing:3px; color:#8b6914; text-transform:uppercase; margin-bottom:20px;">
            Citadel — Admin Dashboard
        </div>
    </div>
    """)

    # Find all reviewer DBs
    all_reviewers = {}
    if os.path.exists(VERDICTS_DIR):
        for fname in sorted(os.listdir(VERDICTS_DIR)):
            if fname.startswith("reviewer_") and fname.endswith(".db"):
                rid = fname.replace("reviewer_", "").replace(".db", "")
                db_path = os.path.join(VERDICTS_DIR, fname)
                try:
                    conn = sqlite3.connect(db_path)
                    rows = conn.execute("SELECT review_id, pmc_id, ref_number, verdict, notes, reviewed_at FROM verdicts ORDER BY review_id").fetchall()
                    conn.close()
                    all_reviewers[rid] = rows
                except Exception as e:
                    all_reviewers[rid] = f"ERROR: {e}"

    if not all_reviewers:
        st.warning("No reviewer verdict files found yet.")
        return

    # Summary table
    st.subheader("Reviewer Progress")
    for rid, rows in all_reviewers.items():
        if isinstance(rows, str):
            st.error(f"**{rid}**: {rows}")
            continue
        v_counts = {}
        for r in rows:
            v_counts[r[3]] = v_counts.get(r[3], 0) + 1
        summary = " · ".join(f"{k}: {v}" for k, v in sorted(v_counts.items()))
        st.write(f"**{rid}**: {len(rows)}/200 reviewed — {summary}")

    # Full backup as JSON
    st.subheader("Full Backup")
    backup = {
        "exported_at": datetime.now().isoformat(),
        "reviewers": {}
    }
    for rid, rows in all_reviewers.items():
        if isinstance(rows, str):
            backup["reviewers"][rid] = {"error": rows}
        else:
            backup["reviewers"][rid] = {
                "total_reviewed": len(rows),
                "verdicts": [
                    {"review_id": r[0], "pmc_id": r[1], "ref_number": r[2],
                     "verdict": r[3], "notes": r[4], "reviewed_at": r[5]}
                    for r in rows
                ]
            }

    backup_json = json.dumps(backup, indent=2, ensure_ascii=False)
    st.download_button(
        f"Download Full Backup ({sum(len(r) for r in all_reviewers.values() if isinstance(r, list))} verdicts)",
        data=backup_json,
        file_name=f"citadel_verdicts_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
        mime="application/json",
        use_container_width=True,
    )

    # Show raw data per reviewer
    for rid, rows in all_reviewers.items():
        if isinstance(rows, str):
            continue
        with st.expander(f"{rid} — {len(rows)} verdicts"):
            for r in rows:
                st.text(f"  #{r[0]:3d} | {r[1]} ref {r[2]} | {r[3]:20s} | {r[5]}")


# ─── Main app ────────────────────────────────────────────────────────────

sample = load_sample()
total = len(sample)

# Admin mode
params = st.query_params
if params.get("admin") == "1":
    admin_page()
    st.stop()

reviewer_id = get_reviewer_id()

if reviewer_id is None:
    st.html("""
    <div style="max-width:480px; margin:60px auto; text-align:center;">
        <div style="font-family:'DM Mono',monospace; font-size:15px; font-weight:500;
                    letter-spacing:3px; color:#8b6914; text-transform:uppercase; margin-bottom:20px;">
            Citadel
        </div>
        <div style="font-family:'DM Sans',sans-serif; font-size:22px; font-weight:600; margin-bottom:6px;">
            Blinded Validation Review
        </div>
        <div style="font-family:'DM Sans',sans-serif; font-size:14px; color:#918e85; margin-bottom:28px;">
            200 references to classify &middot; 3 independent reviewers
        </div>
    </div>
    """)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        name = st.text_input("Your name (first name is fine)", key="reviewer_name")
        if st.button("Start Review", type="primary", use_container_width=True):
            if name.strip():
                rid = name.strip().lower().replace(" ", "_")
                st.session_state.reviewer_id = rid
                init_verdicts_db(rid)
                st.rerun()
            else:
                st.warning("Please enter your name")
    st.html("""
    <div style="max-width:480px; margin:20px auto; font-family:'DM Sans',sans-serif;
                font-size:13px; color:#918e85; line-height:1.7;">
        <b>Instructions:</b> For each reference, determine whether the cited paper exists.
        Use the search links to verify.<br><br>
        <b style="color:#c23030;">Fabricated Citation</b> &mdash; Paper does not exist anywhere<br>
        <b style="color:#a06b1a;">Citation Error</b> &mdash; Paper exists but PMID/DOI are wrong<br>
        <b style="color:#2d8a52;">Correct Citation</b> &mdash; Paper exists and identifiers match<br>
        <b style="color:#555550;">Unsure</b> &mdash; Cannot determine
    </div>
    """)
    st.stop()


# ─── Main review interface ────────────────────────────────────────────────

init_verdicts_db(reviewer_id)
verdicts = load_verdicts(reviewer_id)
reviewed_count = len(verdicts)

if "current_idx" not in st.session_state:
    next_unrev = get_next_unreviewed(verdicts, total)
    st.session_state.current_idx = (next_unrev or 1) - 1

idx = st.session_state.current_idx
entry = sample[idx]
review_id = entry["review_id"]
existing = verdicts.get(review_id)

pct_done = reviewed_count / total * 100

# ── Top bar ──
st.html(f"""
<div class="topbar">
    <div class="topbar-left">
        <div class="logo">Citadel</div>
        <div class="logo-sub">Blinded Review</div>
    </div>
    <div style="font-family:'DM Mono',monospace; font-size:12px; color:#555550;">
        {reviewer_id} &middot; #{review_id}/{total}
    </div>
    <div class="progress-pill">
        <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:{pct_done:.1f}%;"></div></div>
        <span>{reviewed_count}/{total}</span>
    </div>
</div>
""")

# ── Source paper banner (top, before anything) ──
source_title = entry.get("paper_title", "")
source_journal = entry.get("journal", "")
pmc_id = entry.get("pmc_id", "")

if source_title:
    pmc_link = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
    st.html(f"""
    <div class="source-banner">
        <span class="source-label">Citing Article</span>
        <a href="{pmc_link}" target="_blank">{source_title[:120]}{'...' if len(source_title) > 120 else ''}</a>
        <span style="color:#918e85;"> &middot; {source_journal} &middot; {pmc_id}</span>
    </div>
    """)

# ── Two-column layout ──
left, right = st.columns([3, 2], gap="large")

with left:
    # Claimed citation
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

    # What PMID actually resolves to
    actual_pmid = entry.get("actual_title_pmid", "")
    actual_doi = entry.get("actual_title_doi", "")
    actual = actual_pmid or actual_doi or ""

    if actual and actual != title:
        st.html(f"""
        <div class="actual-card">
            <div style="font-family:'DM Mono',monospace; font-size:9px; color:#918e85; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">PMID actually resolves to</div>
            <div class="actual-title">{actual[:300]}</div>
            <div class="actual-note">The paper at PMID {pmid} is a different paper than claimed above</div>
        </div>
        """)


with right:
    # Search links
    encoded_title = urllib.parse.quote(title[:200])
    first_author = (authors.split(";")[0].split(",")[0].strip() if authors else "").replace(" ", "+")
    year_int = int(year) if year and str(year).isdigit() else 2024
    year_lo = year_int - 1
    year_hi = year_int + 1

    st.html(f"""
    <div class="section-label">Search Title</div>
    <div style="display:flex; flex-wrap:wrap; margin-bottom:4px;">
        <a class="search-btn" href="https://pubmed.ncbi.nlm.nih.gov/?term={encoded_title}" target="_blank">PubMed</a>
        <a class="search-btn" href="https://scholar.google.com/scholar?q={encoded_title}" target="_blank">Google Scholar</a>
        <a class="search-btn" href="https://search.crossref.org/?q={encoded_title}&from_ui=yes" target="_blank">CrossRef</a>
        <a class="search-btn" href="https://openalex.org/works?page=1&filter=title.search%3A{encoded_title}" target="_blank">OpenAlex</a>
    </div>
    """)

    if first_author:
        st.html(f"""
        <div style="margin-bottom:6px;">
            <a class="search-btn" href="https://pubmed.ncbi.nlm.nih.gov/?term={first_author}%5Bfirst+author%5D+AND+{year_lo}%3A{year_hi}%5Bdp%5D" target="_blank">
                PubMed: {first_author.replace('+', ' ')} [{year_lo}-{year_hi}]
            </a>
        </div>
        """)

    # Verdict
    st.html('<div class="section-label">Your Verdict</div>')

    verdict_options = {
        "fabricated": "Fabricated Citation \u2014 Does not exist anywhere",
        "citation_error": "Citation Error \u2014 Exists but PMID/DOI wrong",
        "correct": "Correct Citation \u2014 Exists and identifiers match",
        "unsure": "Unsure \u2014 Cannot determine",
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
        placeholder="Optional notes...",
        height=60,
        key=f"notes_{review_id}",
    )

    # Action buttons
    col_prev, col_save, col_skip = st.columns([1, 2, 1])
    with col_prev:
        if st.button("< Prev", use_container_width=True, disabled=(idx == 0)):
            st.session_state.current_idx = max(0, idx - 1)
            st.rerun()
    with col_save:
        if st.button("Save & Next >", type="primary", use_container_width=True):
            save_verdict(reviewer_id, review_id, entry["pmc_id"], entry["ref_number"], verdict, notes)
            if idx < total - 1:
                st.session_state.current_idx = idx + 1
            st.rerun()
    with col_skip:
        if st.button("Skip >", use_container_width=True):
            if idx < total - 1:
                st.session_state.current_idx = idx + 1
            st.rerun()

    if existing:
        st.success(f"Previously: **{existing['verdict']}**")

    # Navigation row
    nav1, nav2, nav3 = st.columns([1, 1, 1])
    with nav1:
        jump = st.number_input("Go to #", min_value=1, max_value=total, value=idx + 1, key="jump_to", label_visibility="collapsed")
    with nav2:
        if st.button("Go", key="go_btn", use_container_width=True):
            st.session_state.current_idx = jump - 1
            st.rerun()
    with nav3:
        next_unrev = get_next_unreviewed(verdicts, total)
        if next_unrev:
            if st.button(f"Next unreviewed (#{next_unrev})", key="jump_unrev", use_container_width=True):
                st.session_state.current_idx = next_unrev - 1
                st.rerun()

    # Compact progress + export
    if reviewed_count > 0:
        v_counts = {}
        for v in verdicts.values():
            v_counts[v["verdict"]] = v_counts.get(v["verdict"], 0) + 1

        st.html(f"""
        <div style="font-family:'DM Mono',monospace; font-size:11px; margin-top:8px;">
            <span style="color:#c23030;">Fab: {v_counts.get('fabricated', 0)}</span> &middot;
            <span style="color:#a06b1a;">Err: {v_counts.get('citation_error', 0)}</span> &middot;
            <span style="color:#2d8a52;">OK: {v_counts.get('correct', 0)}</span> &middot;
            <span style="color:#555550;">?: {v_counts.get('unsure', 0)}</span> &middot;
            <span>{reviewed_count}/{total}</span>
        </div>
        """)

        json_export = export_verdicts_json(reviewer_id)
        col_exp, col_logout = st.columns(2)
        with col_exp:
            st.download_button(
                f"Export ({reviewed_count})",
                data=json_export,
                file_name=f"citadel_verdicts_{reviewer_id}_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json",
                use_container_width=True,
            )
        with col_logout:
            if st.button("Logout", key="logout", use_container_width=True):
                st.session_state.reviewer_id = None
                if "current_idx" in st.session_state:
                    del st.session_state.current_idx
                st.rerun()
    else:
        if st.button("Logout", key="logout"):
            st.session_state.reviewer_id = None
            if "current_idx" in st.session_state:
                del st.session_state.current_idx
            st.rerun()
