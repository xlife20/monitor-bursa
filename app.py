import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import load_csv, fetch_data

st.set_page_config(page_title="Investiții", layout="wide")

st.markdown("""
<style>
    .summary-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        min-height: 145px;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    .summary-label { font-size: 0.95rem; color: #9e9e9e; margin-bottom: 8px; }
    .summary-val { font-size: 1.75rem; font-weight: 700; line-height: 1.2; }
    .summary-sub { font-size: 0.85rem; margin-top: 8px; color: #9e9e9e; }
</style>
""", unsafe_allow_html=True)

XTB_CSV = Path(__file__).with_name("portfolio.csv")
KRAKEN_CSV = Path(__file__).with_name("portfolio_kraken.csv")
DIVS_ANNUAL_CSV = Path(__file__).with_name("dividends_annual.csv")
CLOSED_DIVS_EUR = 18.24

req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]
df_xtb = load_csv(XTB_CSV, req).copy()
df_krk = load_csv(KRAKEN_CSV, req).copy()
df_all = pd.concat([df_xtb, df_krk], ignore_index=True)

if "Dividends EUR" not in df_all.columns:
    df_all["Dividends EUR"] = 0.0

for c in ["Shares", "Buy Price", "Current Price", "Dividends EUR"]:
    df_all[c] = pd.to_numeric(df_all[c], errors="coerce").fillna(0.0).astype(float)

tickers = df_all["Ticker"].dropna().unique().tolist()
all_curr = sorted(df_all["Currency"].dropna().unique().tolist()) or ["EUR", "USD"]
prices, _, _, _, fx = fetch_data(tickers, list(set(all_curr + ["EUR", "USD", "GBP"])))

df_all["Current Price"] = np.where(df_all["Ticker"].map(prices).notna(), df_all["Ticker"].map(prices), df_all["Current Price"]).astype(float)

eur_to_usd = fx.get("EUR", 1.08)
mult_to_eur = pd.to_numeric(df_all["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / eur_to_usd

inv_eur = float((df_all["Shares"] * df_all["Buy Price"] * mult_to_eur).sum())
mkt_eur = float((df_all["Shares"] * df_all["Current Price"] * mult_to_eur).sum())
open_divs_eur = float(df_all["Dividends EUR"].sum())
total_divs_eur = open_divs_eur + CLOSED_DIVS_EUR

price_pnl_eur = mkt_eur - inv_eur
price_ret_pct = (price_pnl_eur / inv_eur * 100) if inv_eur > 0 else 0.0

pnl_color = "#00e676" if price_pnl_eur >= 0 else "#ff5252"
pnl_sign = "+" if price_pnl_eur >= 0 else ""

st.markdown("<br><h1 style='text-align: center;'>💼 Investiții</h1><br>", unsafe_allow_html=True)

_, col_s1, col_s2, col_s3, _ = st.columns([0.6, 1.4, 1.4, 1.4, 0.6])
with col_s1:
    st.markdown(
        f"<div class='summary-card'>"
        f"<div class='summary-label'>Total Investit (XTB + Kraken)</div>"
        f"<div class='summary-val' style='color:#fafafa;'>{inv_eur:,.2f} EUR</div>"
        f"<div class='summary-sub'>Valoare piață: {mkt_eur:,.2f} EUR</div>"
        f"</div>",
        unsafe_allow_html=True
    )

with col_s2:
    st.markdown(
        f"<div class='summary-card'>"
        f"<div class='summary-label'>Profit / Pierdere (Preț)</div>"
        f"<div class='summary-val' style='color:{pnl_color};'>{pnl_sign}{price_pnl_eur:,.2f} EUR</div>"
        f"<div class='summary-sub'>Randament preț: {pnl_sign}{price_ret_pct:.2f}%</div>"
        f"</div>",
        unsafe_allow_html=True
    )

with col_s3:
    st.markdown(
        f"<div class='summary-card'>"
        f"<div class='summary-label'>Dividende Nete</div>"
        f"<div class='summary-val' style='color:#ffd54f;'>+{total_divs_eur:,.2f} EUR</div>"
        f"<div class='summary-sub'>Deschise: {open_divs_eur:,.2f} | Închise: {CLOSED_DIVS_EUR:,.2f}</div>"
        f"</div>",
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)

_, c1, c2, c3, _ = st.columns([0.6, 1.4, 1.4, 1.4, 0.6])
if c1.button("📈 Portofoliu XTB", use_container_width=True, type="primary"):
    st.switch_page("pages/1_Portofoliu_XTB.py")
if c2.button("🪙 Portofoliu Kraken", use_container_width=True, type="primary"):
    st.switch_page("pages/2_Portofoliu_Kraken.py")
if c3.button("👁️ Urmărește", use_container_width=True, type="primary"):
    st.switch_page("pages/3_Urmareste.py")

st.markdown("<br><br><h4 style='text-align: center; color: #fafafa;'>💰 Dividende Nete Încasate Anual (EUR)</h4>", unsafe_allow_html=True)

if not DIVS_ANNUAL_CSV.exists():
    init_divs = pd.DataFrame([
        {"An": "2025", "Dividende EUR": 31.61},
        {"An": "2026", "Dividende EUR": 84.14}
    ])
    init_divs.to_csv(DIVS_ANNUAL_CSV, index=False)

df_divs = pd.read_csv(DIVS_ANNUAL_CSV)
df_divs["An"] = df_divs["An"].astype(str)
df_divs["Dividende EUR"] = pd.to_numeric(df_divs["Dividende EUR"], errors="coerce").fillna(0.0)

_, chart_col, _ = st.columns([0.6, 4.2, 0.6])
with chart_col:
    st.bar_chart(df_divs.set_index("An")["Dividende EUR"], color="#ffd54f", height=260)
    with st.expander("✏️ Editează sumele exacte pe fiecare an"):
        ed_divs = st.data_editor(df_divs, num_rows="dynamic", use_container_width=True, key="ed_annual_divs")
        if st.button("Salvează dividendele anuale"):
            ed_divs.to_csv(DIVS_ANNUAL_CSV, index=False)
            st.cache_data.clear()
            st.rerun()
