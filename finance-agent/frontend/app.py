"""Streamlit MVP frontend for the Market Intelligence Agent."""

import httpx
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Finance Agent", page_icon="📈", layout="wide")
st.title("📈 Finance Agent — Market Intelligence")

with st.sidebar:
    st.header("Settings")
    ticker = st.text_input("Ticker Symbol", value="AAPL", max_chars=10).upper().strip()
    limit = st.slider("Number of filings", min_value=1, max_value=5, value=1)
    analyze_btn = st.button("Analyze", type="primary")

if analyze_btn and ticker:
    with st.spinner(f"Downloading and analyzing {ticker} transcript(s)…"):
        try:
            resp = httpx.post(
                f"{API_BASE}/api/v1/intelligence/analyze",
                json={"ticker": ticker, "filing_type": "8-K", "limit": limit},
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            st.error(f"API error {exc.response.status_code}: {exc.response.text}")
            st.stop()
        except Exception as exc:
            st.error(f"Request failed: {exc}")
            st.stop()

    # --- Summary card -------------------------------------------------------
    col1, col2, col3 = st.columns(3)
    col1.metric("Overall Tone", data["overall_tone"].capitalize())
    col2.metric("Guidance", data["guidance_revision"].capitalize())
    col3.metric("Chunks Analyzed", data["chunk_count"])

    st.subheader("Summary")
    st.write(data["human_readable_summary"])

    if data.get("guidance_summary"):
        st.info(f"**Guidance:** {data['guidance_summary']}")

    # --- Themes & risks -----------------------------------------------------
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Top Themes")
        for theme in data["top_themes"]:
            st.markdown(f"- {theme}")
    with col_r:
        st.subheader("Risk Flags")
        if data["risk_flags"]:
            for flag in data["risk_flags"]:
                st.markdown(f"- {flag}")
        else:
            st.write("No significant risk flags identified.")

    # --- Per-chunk detail ---------------------------------------------------
    with st.expander("Per-chunk analysis"):
        for chunk in data["chunk_summaries"]:
            st.markdown(f"**Chunk {chunk['chunk_index']}** — Tone: `{chunk['tone']}`")
            st.markdown("Themes: " + ", ".join(chunk["key_themes"]))
            if chunk["forward_guidance_mentions"]:
                st.markdown("Guidance mentions: " + "; ".join(chunk["forward_guidance_mentions"]))
            st.divider()
