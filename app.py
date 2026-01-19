#!/usr/bin/env python3
import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = "jyotish_bp.sqlite"

@st.cache_resource
def get_conn():
    # read-only is ideal, but SQLite URI read-only requires file path exactly; keep simple for now
    return sqlite3.connect(DB_PATH, check_same_thread=False)

@st.cache_data
def load_metadata():
    con = get_conn()
    cats = pd.read_sql_query("SELECT DISTINCT category FROM docs WHERE category IS NOT NULL ORDER BY category", con)["category"].tolist()
    planets = pd.read_sql_query("SELECT DISTINCT planet FROM docs WHERE planet IS NOT NULL ORDER BY planet", con)["planet"].tolist()
    signs = pd.read_sql_query("SELECT DISTINCT sign FROM docs WHERE sign IS NOT NULL ORDER BY sign", con)["sign"].tolist()
    houses = pd.read_sql_query("SELECT DISTINCT house FROM docs WHERE house IS NOT NULL ORDER BY house", con)["house"].tolist()
    naks = pd.read_sql_query("SELECT DISTINCT nakshatra_name FROM docs WHERE nakshatra_name IS NOT NULL ORDER BY nakshatra_name", con)["nakshatra_name"].tolist()
    return cats, planets, signs, houses, naks

def search_docs(category, planet, sign, house, nakshatra_name, q, conj_a, conj_b, limit, offset):
    con = get_conn()
    where = []
    params = []

    if category:
        where.append("category = ?")
        params.append(category)

    if planet:
        where.append("planet = ?")
        params.append(planet)

    if sign:
        where.append("sign = ?")
        params.append(sign)

    if house is not None:
        where.append("house = ?")
        params.append(house)

    if nakshatra_name:
        where.append("lower(nakshatra_name) = lower(?)")
        params.append(nakshatra_name)

    # Conjunction filter: stored via URL patterns in your dataset
    # Example URL contains: Chandra_yuti_Shani OR Shani_yuti_Chandra
    if conj_a and conj_b:
        where.append(
            "(url LIKE ? OR url LIKE ?)"
        )
        params.append(f"%{conj_a}_yuti_{conj_b}%")
        params.append(f"%{conj_b}_yuti_{conj_a}%")

    # free-text search
    if q:
        where.append("(title LIKE ? OR summary_text LIKE ? OR full_text LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    sql = """
    SELECT id, url, title, category, planet, sign, house, nakshatra_name, summary_text, full_text
    FROM docs
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    return pd.read_sql_query(sql, con, params=params)

def fmt_label(s):
    # make lowercase DB values nicer in UI
    return s.title() if isinstance(s, str) else s

st.set_page_config(page_title="Jyotish DB Query", layout="wide")
st.title("Jyotish Knowledge Base")

cats, planets, signs, houses, naks = load_metadata()

with st.sidebar:
    st.header("Filters")

    category = st.selectbox("Category", [""] + cats, format_func=lambda x: x or "(any)")
    planet = st.selectbox("Planet", [""] + planets, format_func=lambda x: fmt_label(x) if x else "(any)")

    sign = st.selectbox("Sign", [""] + signs, format_func=lambda x: fmt_label(x) if x else "(any)")
    house = st.selectbox("House", [""] + houses, format_func=lambda x: x if x != "" else "(any)")

    # Moon nakshatra filter (works even if user uses it for others)
    nak = st.selectbox("Nakshatra", [""] + naks, format_func=lambda x: x or "(any)")

    st.subheader("Conjunction (via URL)")
    conj_a = st.selectbox("Planet A", [""] + planets, key="conj_a", format_func=lambda x: fmt_label(x) if x else "(none)")
    conj_b = st.selectbox("Planet B", [""] + planets, key="conj_b", format_func=lambda x: fmt_label(x) if x else "(none)")

    q = st.text_input("Search text (title/summary/full)", "")

    limit = st.slider("Results per page", 10, 100, 25, 5)
    page = st.number_input("Page", min_value=1, value=1, step=1)

offset = (page - 1) * limit
house_val = None if house == "" else int(house)

df = search_docs(
    category=category or None,
    planet=planet or None,
    sign=sign or None,
    house=house_val,
    nakshatra_name=nak or None,
    q=q.strip() or None,
    conj_a=conj_a or None,
    conj_b=conj_b or None,
    limit=limit,
    offset=offset,
)

st.write(f"Showing {len(df)} result(s).")

for _, r in df.iterrows():
    title = r["title"] or "(no title)"
    meta = []
    if r["category"]: meta.append(r["category"])
    if r["planet"]: meta.append(r["planet"])
    if r["sign"]: meta.append(r["sign"])
    if pd.notna(r["house"]): meta.append(f"house={int(r['house'])}")
    if r["nakshatra_name"]: meta.append(r["nakshatra_name"])
    meta_str = " • ".join(meta)

    with st.expander(f"{title}  —  {meta_str}"):
        if r["summary_text"]:
            st.markdown("**Summary**")
            st.write(r["summary_text"])
        if r["full_text"]:
            st.markdown("**Full text**")
            st.write(r["full_text"])
        if r["url"]:
            st.markdown(f"**Source:** {r['url']}")
