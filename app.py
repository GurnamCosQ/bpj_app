#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


# -----------------------------
# Config
# -----------------------------
DB_PATH = "jyotish_bp.sqlite"

PLANETS = ["sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu"]
SIGNS = [
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
]
HOUSES = list(range(1, 13))

PLANET_URL_TOKEN = {
    "sun": "Surya",
    "moon": "Chandra",
    "mars": "Mangala",
    "mercury": "Budha",
    "jupiter": "Guru",
    "venus": "Zukra",
    "saturn": "Shani",
    "rahu": "Rahu",
    "ketu": "Ketu",
}

st.set_page_config(page_title="Jyotish Reading Tool", layout="wide")


# -----------------------------
# Utilities
# -----------------------------
def title_case(s: Optional[str]) -> str:
    if not s:
        return ""
    return s.strip().title()


def norm(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s2 = s.strip()
    return s2.lower() if s2 else None


def safe_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        return int(x)
    except Exception:
        return None


def now_utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@st.cache_resource
def get_conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


@st.cache_data
def get_distinct(col: str) -> List[Any]:
    con = get_conn()
    q = f"SELECT DISTINCT {col} AS v FROM docs WHERE {col} IS NOT NULL ORDER BY {col}"
    rows = con.execute(q).fetchall()
    return [r["v"] for r in rows]


@st.cache_data
def get_metadata() -> Dict[str, Any]:
    return {
        "nakshatras": [str(x) for x in get_distinct("nakshatra_name")],
        "row_count": int(get_conn().execute("SELECT COUNT(*) AS n FROM docs").fetchone()["n"]),
    }


def db_one(sql: str, params: Tuple[Any, ...]) -> Optional[sqlite3.Row]:
    con = get_conn()
    cur = con.execute(sql, params)
    return cur.fetchone()


@dataclass(frozen=True)
class Doc:
    id: int
    url: str
    title: str
    category: str
    planet: Optional[str]
    sign: Optional[str]
    house: Optional[int]
    nakshatra_name: Optional[str]
    summary_text: Optional[str]
    full_text: Optional[str]

    @staticmethod
    def from_row(r: sqlite3.Row) -> "Doc":
        return Doc(
            id=int(r["id"]),
            url=r["url"] or "",
            title=r["title"] or "",
            category=r["category"] or "",
            planet=r["planet"],
            sign=r["sign"],
            house=safe_int(r["house"]),
            nakshatra_name=r["nakshatra_name"],
            summary_text=r["summary_text"],
            full_text=r["full_text"],
        )


def find_planet_in_sign(planet: str, sign: str) -> Optional[Doc]:
    sql = """
    SELECT id, url, title, category, planet, sign, house, nakshatra_name, summary_text, full_text
    FROM docs
    WHERE category='planet_in_sign' AND planet=? AND sign=?
    LIMIT 1
    """
    r = db_one(sql, (planet, sign))
    return Doc.from_row(r) if r else None


def find_planet_in_house(planet: str, house: int) -> Optional[Doc]:
    sql = """
    SELECT id, url, title, category, planet, sign, house, nakshatra_name, summary_text, full_text
    FROM docs
    WHERE category='planet_in_house' AND planet=? AND house=?
    LIMIT 1
    """
    r = db_one(sql, (planet, house))
    return Doc.from_row(r) if r else None


def find_moon_in_nakshatra(nakshatra_name: str) -> Optional[Doc]:
    sql = """
    SELECT id, url, title, category, planet, sign, house, nakshatra_name, summary_text, full_text
    FROM docs
    WHERE category='planet_in_nakshatra' AND planet='moon'
      AND lower(nakshatra_name)=lower(?)
    LIMIT 1
    """
    r = db_one(sql, (nakshatra_name,))
    return Doc.from_row(r) if r else None


def find_conjunction(planet_a: str, planet_b: str) -> Optional[Doc]:
    tok_a = PLANET_URL_TOKEN.get(planet_a)
    tok_b = PLANET_URL_TOKEN.get(planet_b)

    if tok_a and tok_b:
        sql = """
        SELECT id, url, title, category, planet, sign, house, nakshatra_name, summary_text, full_text
        FROM docs
        WHERE category='conjunction'
          AND (url LIKE ? OR url LIKE ?)
        LIMIT 1
        """
        p1 = f"%{tok_a}_yuti_{tok_b}%"
        p2 = f"%{tok_b}_yuti_{tok_a}%"
        r = db_one(sql, (p1, p2))
        if r:
            return Doc.from_row(r)

    # fallback by title contains both names
    sql2 = """
    SELECT id, url, title, category, planet, sign, house, nakshatra_name, summary_text, full_text
    FROM docs
    WHERE category='conjunction'
      AND lower(title) LIKE ?
      AND lower(title) LIKE ?
    LIMIT 1
    """
    r2 = db_one(sql2, (f"%{planet_a}%", f"%{planet_b}%"))
    return Doc.from_row(r2) if r2 else None


def doc_display_title(d: Doc) -> str:
    p = title_case(d.planet) if d.planet else ""
    if d.category == "planet_in_sign" and d.sign:
        return f"{p} in {title_case(d.sign)}"
    if d.category == "planet_in_house" and d.house:
        suf = "th"
        if d.house in (1, 21, 31):
            suf = "st"
        elif d.house in (2, 22, 32):
            suf = "nd"
        elif d.house in (3, 23, 33):
            suf = "rd"
        return f"{p} in {d.house}{suf} House"
    if d.category == "planet_in_nakshatra" and d.nakshatra_name:
        return f"{p} in {d.nakshatra_name} Nakshatra"
    if d.category == "conjunction":
        return d.title or "Conjunction"
    return d.title or f"Doc #{d.id}"


def copy_button(text: str, key: str) -> None:
    esc = json.dumps(text)
    html = f"""
    <div style="margin: 6px 0;">
      <button id="btn_{key}" style="
        padding: 6px 10px; border-radius: 8px; border: 1px solid #bbb;
        background: white; cursor: pointer; font-size: 0.9rem;">
        Copy to clipboard
      </button>
      <span id="msg_{key}" style="margin-left: 10px; font-size: 0.85rem; color: #444;"></span>
    </div>
    <script>
      const btn = document.getElementById("btn_{key}");
      const msg = document.getElementById("msg_{key}");
      btn.addEventListener("click", async () => {{
        try {{
          await navigator.clipboard.writeText({esc});
          msg.textContent = "Copied.";
          setTimeout(() => msg.textContent = "", 1200);
        }} catch (e) {{
          msg.textContent = "Copy failed.";
          setTimeout(() => msg.textContent = "", 2000);
        }}
      }});
    </script>
    """
    components.html(html, height=50)


def init_state() -> None:
    if "results" not in st.session_state:
        st.session_state["results"] = []  # List[Doc]
    if "report_ids" not in st.session_state:
        st.session_state["report_ids"] = []  # List[int]
    if "report_notes" not in st.session_state:
        st.session_state["report_notes"] = ""


def clear_results() -> None:
    st.session_state["results"] = []


def add_result(doc: Optional[Doc]) -> None:
    if not doc:
        return
    existing = {d.id for d in st.session_state["results"]}
    if doc.id not in existing:
        st.session_state["results"].append(doc)


def add_to_report(doc: Doc) -> None:
    if doc.id not in st.session_state["report_ids"]:
        st.session_state["report_ids"].append(doc.id)


def get_doc_by_id(doc_id: int) -> Optional[Doc]:
    sql = """
    SELECT id, url, title, category, planet, sign, house, nakshatra_name, summary_text, full_text
    FROM docs
    WHERE id=?
    LIMIT 1
    """
    r = db_one(sql, (doc_id,))
    return Doc.from_row(r) if r else None


def export_report_text() -> str:
    lines: List[str] = []
    lines.append("Jyotish Reading Report")
    lines.append(f"Generated: {now_utc_iso()}")
    lines.append("")
    notes = st.session_state.get("report_notes", "").strip()
    if notes:
        lines.append("Notes:")
        lines.append(notes)
        lines.append("")
    for i, doc_id in enumerate(st.session_state["report_ids"], start=1):
        d = get_doc_by_id(doc_id)
        if not d:
            continue
        lines.append(f"{i}. {doc_display_title(d)}")
        lines.append(f"Source: {d.url}")
        lines.append("")
        lines.append("Summary:")
        lines.append((d.summary_text or "(no summary_text)").strip())
        lines.append("")
        lines.append("-" * 60)
        lines.append("")
    return "\n".join(lines)


def export_report_pdf_bytes(text: str) -> Optional[bytes]:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception:
        return None

    import io

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    left = 40
    top = height - 40
    y = top
    line_h = 12

    def draw_line(s: str) -> None:
        nonlocal y
        max_chars = 95
        parts = [s[i : i + max_chars] for i in range(0, len(s), max_chars)] or [""]
        for p in parts:
            if y < 50:
                c.showPage()
                y = top
            c.drawString(left, y, p)
            y -= line_h

    for line in text.splitlines():
        draw_line(line)

    c.save()
    buf.seek(0)
    return buf.read()


def render_results_panel() -> None:
    st.subheader("Results")
    if not st.session_state["results"]:
        st.info("No results yet.")
        return

    labels = [doc_display_title(d) for d in st.session_state["results"]]
    st.write("Selections:")
    st.write("\n".join([f"• {x}" for x in labels]))

    st.divider()

    for idx, d in enumerate(st.session_state["results"]):
        header = doc_display_title(d)
        meta_bits = []
        if d.category:
            meta_bits.append(d.category)
        if d.planet:
            meta_bits.append(d.planet)
        if d.sign:
            meta_bits.append(d.sign)
        if d.house:
            meta_bits.append(f"house={d.house}")
        if d.nakshatra_name:
            meta_bits.append(d.nakshatra_name)

        with st.expander(f"{header}  —  {' • '.join(meta_bits)}", expanded=False):
            cols = st.columns([1, 1, 1])
            with cols[0]:
                if st.button("Add to report", key=f"addrep_{d.id}_{idx}"):
                    add_to_report(d)
                    st.success("Added.")
            with cols[1]:
                copy_text = (d.summary_text or "").strip() or (d.full_text or "")
                copy_button(copy_text or "(empty)", key=f"copy_{d.id}_{idx}")
            with cols[2]:
                if d.url:
                    st.link_button("Open source", d.url)

            t1, t2 = st.tabs(["Summary", "Full text"])
            with t1:
                st.write(d.summary_text or "(no summary_text)")
            with t2:
                st.write(d.full_text or "(no full_text)")


# -----------------------------
# App
# -----------------------------
init_state()
meta = get_metadata()

st.markdown("## 🌟 Jyotish Reading Tool")
st.caption(f"Docs in DB: {meta['row_count']}")

tabs = st.tabs(["Simple mode", "Chart mode", "Aspect mode", "Report builder"])


# -----------------------------
# Simple mode
# -----------------------------
with tabs[0]:
    left, right = st.columns([1.4, 1])

    with right:
        st.subheader("Quick Query Builder")

        with st.form("simple_form", clear_on_submit=False):
            planet_ui = st.selectbox(
                "Planet",
                options=PLANETS,
                format_func=title_case,
                key="simple_planet",
            )

            sign_ui = st.selectbox(
                "Sign (optional)",
                options=["(none)"] + SIGNS,
                format_func=lambda x: "(none)" if x == "(none)" else title_case(x),
                key="simple_sign",
            )

            house_ui = st.selectbox(
                "House (optional)",
                options=["(none)"] + [str(h) for h in HOUSES],
                key="simple_house",
            )

            nak_ui = st.selectbox(
                "Moon Nakshatra (optional)",
                options=["(none)"] + meta["nakshatras"],
                key="simple_nak",
            )

            st.caption("Conjunction (optional)")
            conj_a = st.selectbox(
                "Conjunction planet A",
                options=["(none)"] + PLANETS,
                format_func=lambda x: "(none)" if x == "(none)" else title_case(x),
                key="simple_conj_a",
            )
            conj_b = st.selectbox(
                "Conjunction planet B",
                options=["(none)"] + PLANETS,
                format_func=lambda x: "(none)" if x == "(none)" else title_case(x),
                key="simple_conj_b",
            )

            c1, c2 = st.columns(2)
            do_search = c1.form_submit_button("Search", use_container_width=True)
            do_clear = c2.form_submit_button("Clear", use_container_width=True)

        if do_clear:
            clear_results()

        if do_search:
            clear_results()

            p = norm(planet_ui) or ""
            if sign_ui != "(none)":
                add_result(find_planet_in_sign(p, norm(sign_ui) or ""))
            if house_ui != "(none)":
                add_result(find_planet_in_house(p, int(house_ui)))

            if nak_ui != "(none)":
                add_result(find_moon_in_nakshatra(nak_ui))

            if conj_a != "(none)" and conj_b != "(none)" and conj_a != conj_b:
                add_result(find_conjunction(norm(conj_a) or "", norm(conj_b) or ""))

    with left:
        render_results_panel()


# -----------------------------
# Chart mode
# -----------------------------
with tabs[1]:
    left, right = st.columns([1.4, 1])

    with right:
        st.subheader("Input Chart Data")
        st.caption("Enter sign/house for planets you know. Then generate a combined reading.")

        with st.form("chart_form", clear_on_submit=False):
            planet_inputs: Dict[str, Dict[str, Optional[str]]] = {}

            for p in PLANETS:
                with st.expander(title_case(p), expanded=(p == "moon")):
                    sign_sel = st.selectbox(
                        f"{title_case(p)} sign",
                        options=["(none)"] + SIGNS,
                        format_func=lambda x: "(none)" if x == "(none)" else title_case(x),
                        key=f"chart_sign_{p}",
                    )
                    house_sel = st.selectbox(
                        f"{title_case(p)} house",
                        options=["(none)"] + [str(h) for h in HOUSES],
                        key=f"chart_house_{p}",
                    )
                    planet_inputs[p] = {
                        "sign": None if sign_sel == "(none)" else norm(sign_sel),
                        "house": None if house_sel == "(none)" else house_sel,
                    }

            st.divider()
            moon_nak = st.selectbox(
                "Moon nakshatra (optional)",
                options=["(none)"] + meta["nakshatras"],
                key="chart_moon_nak",
            )

            st.divider()
            st.subheader("Conjunctions (optional)")
            st.caption("Add up to 6 conjunction pairs.")

            conj_pairs: List[Tuple[str, str]] = []
            for i in range(1, 7):
                ccols = st.columns(2)
                a = ccols[0].selectbox(
                    f"Pair {i} - A",
                    options=["(none)"] + PLANETS,
                    format_func=lambda x: "(none)" if x == "(none)" else title_case(x),
                    key=f"chart_conj_a_{i}",
                )
                b = ccols[1].selectbox(
                    f"Pair {i} - B",
                    options=["(none)"] + PLANETS,
                    format_func=lambda x: "(none)" if x == "(none)" else title_case(x),
                    key=f"chart_conj_b_{i}",
                )
                if a != "(none)" and b != "(none)" and a != b:
                    conj_pairs.append((norm(a) or "", norm(b) or ""))

            c1, c2 = st.columns(2)
            do_gen = c1.form_submit_button("Generate Reading", use_container_width=True)
            do_clear = c2.form_submit_button("Clear", use_container_width=True)

        if do_clear:
            clear_results()

        if do_gen:
            clear_results()

            # Add sign/house docs only for selected planets
            for p in PLANETS:
                s = planet_inputs[p]["sign"]
                h_str = planet_inputs[p]["house"]
                if s:
                    add_result(find_planet_in_sign(p, s))
                if h_str:
                    add_result(find_planet_in_house(p, int(h_str)))

            if moon_nak != "(none)":
                add_result(find_moon_in_nakshatra(moon_nak))

            for a, b in conj_pairs:
                add_result(find_conjunction(a, b))

    with left:
        render_results_panel()


# -----------------------------
# Aspect mode
# -----------------------------
with tabs[2]:
    left, right = st.columns([1.4, 1])

    with right:
        st.subheader("Conjunction Finder")

        with st.form("aspect_form", clear_on_submit=False):
            a = st.selectbox("Planet A", options=PLANETS, format_func=title_case, key="aspect_a")
            b = st.selectbox("Planet B", options=PLANETS, format_func=title_case, key="aspect_b")

            c1, c2 = st.columns(2)
            do_find = c1.form_submit_button("Find conjunction", use_container_width=True)
            do_clear = c2.form_submit_button("Clear", use_container_width=True)

        if do_clear:
            clear_results()

        if do_find:
            clear_results()
            if a != b:
                add_result(find_conjunction(norm(a) or "", norm(b) or ""))

        st.caption("Conjunction lookup uses URL token patterns and title fallback.")

    with left:
        render_results_panel()


# -----------------------------
# Report builder
# -----------------------------
with tabs[3]:
    st.subheader("Reading Builder")

    if not st.session_state["report_ids"]:
        st.info("No items in report. Use 'Add to report' from Results.")
    else:
        for i, doc_id in enumerate(st.session_state["report_ids"], start=1):
            d = get_doc_by_id(doc_id)
            if not d:
                continue
            cols = st.columns([0.85, 0.15])
            with cols[0]:
                st.write(f"{i}. {doc_display_title(d)}")
            with cols[1]:
                if st.button("Remove", key=f"rm_{doc_id}_{i}"):
                    st.session_state["report_ids"] = [x for x in st.session_state["report_ids"] if x != doc_id]
                    st.rerun()

    st.divider()
    st.subheader("Notes (optional)")
    st.session_state["report_notes"] = st.text_area(
        "Add any notes to prepend to the report",
        value=st.session_state.get("report_notes", ""),
        height=120,
        key="report_notes_area",
    )

    st.divider()
    st.subheader("Export")
    report_text = export_report_text()
    st.download_button(
        "Download TXT",
        data=report_text.encode("utf-8"),
        file_name="jyotish_reading_report.txt",
        mime="text/plain",
        use_container_width=True,
        key="dl_txt",
    )

    pdf_bytes = export_report_pdf_bytes(report_text)
    if pdf_bytes:
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="jyotish_reading_report.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="dl_pdf",
        )
    else:
        st.caption("PDF export requires `reportlab`. Add it to requirements.txt if you want PDF downloads.")


with st.expander("Diagnostics", expanded=False):
    st.write(f"DB_PATH: {DB_PATH}")
    st.write(f"Results: {len(st.session_state['results'])}")
    st.write(f"Report items: {len(st.session_state['report_ids'])}")
