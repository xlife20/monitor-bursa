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
    .summary-val { font-size: 1.85rem; font-weight: 700; line-height: 1.2; }
    .summary-sub { font-size: 0.85rem; margin-top: 8px; color: #9e9e9e; }
</style>
""", unsafe_allow_html=True)

XTB_CSV = Path(__file__).with_name("portfolio.csv")
KRAKEN_CSV = Path(__file__).with_name("portfolio_kraken.csv")
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
divs_eur = float(df_all["Dividends EUR"].sum()) + CLOSED_DIVS_EUR
pnl_eur = (mkt_eur - inv_eur) + divs_eur
ret_pct = (pnl_eur / inv_eur * 100) if inv_eur > 0 else 0.0

pnl_color = "#00e676" if pnl_eur >= 0 else "#ff5252"
pnl_sign = "+" if pnl_eur >= 0 else ""

st.markdown("<br><h1 style='text-align: center;'>💼 Investiții</h1><br>", unsafe_allow_html=True)

_, col_s1, col_s2, _ = st.columns([1.1, 1.6, 1.6, 1.1])
with col_s1:
    st.markdown(
        f"<div class='summary-card'>"
        f"<div class='summary-label'>Total Investit (XTB + Kraken)</div>"
        f"<div class='summary-val' style='color:#fafafa;'>{inv_eur:,.2f} EUR</div>"
        f"<div class='summary-sub'>Valoare piață actuală: {mkt_eur:,.2f} EUR</div>"
        f"</div>",
        unsafe_allow_html=True
    )

with col_s2:
    st.markdown(
        f"<div class='summary-card'>"
        f"<div class='summary-label'>Profit / Pierdere Total (+Dividende)</div>"
        f"<div class='summary-val' style='color:{pnl_color};'>{pnl_sign}{pnl_eur:,.2f} EUR</div>"
        f"<div class='summary-sub'>Randament total: {pnl_sign}{ret_pct:.2f}% (incl. {divs_eur:,.2f} EUR div.)</div>"
        f"</div>",
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)

_, c1, c2, c3, _ = st.columns([1.0, 1.2, 1.2, 1.2, 1.0])
if c1.button("📈 Portofoliu XTB", use_container_width=True, type="primary"):
    st.switch_page("pages/1_Portofoliu_XTB.py")
if c2.button("🪙 Portofoliu Kraken", use_container_width=True, type="primary"):
    st.switch_page("pages/2_Portofoliu_Kraken.py")
if c3.button("👁️ Urmărește", use_container_width=True, type="primary"):
    st.switch_page("pages/3_Urmareste.py")
