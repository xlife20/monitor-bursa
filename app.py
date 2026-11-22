import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import fetch_data

st.set_page_config(page_title="Investiții", layout="wide")
BASE = Path(__file__).resolve().parent
XTB_CSV = BASE / "portfolio.csv"
KRK_CSV = BASE / "portfolio_kraken.csv"
CLOSED_DIVS_EUR = 18.24

if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.cache_data.clear()
    st.rerun()

st.title("📊 Panou Principal — Investiții")
t_curr = st.sidebar.selectbox("Monedă afișare", ("EUR", "USD", "GBP"))

def calc_port(csv_p, extra_eur=0.0):
    if not csv_p.exists(): return 0.0, 0.0, 0.0, 0.0, 0
    df = pd.read_csv(csv_p).fillna("")
    df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
    if df.empty: return 0.0, 0.0, 0.0, 0.0, 0
    tks = df["Ticker"].astype(str).unique().tolist()
    currs = list(set(df["Currency"].astype(str).unique().tolist() + ["EUR", "USD", "GBP"]))
    prices, _, _, _, fx = fetch_data(tks, currs)
    for c in ("Shares", "Buy Price", "Current Price", "Dividends EUR"):
        df[c] = pd.to_numeric(df.get(c, 0.0), errors="coerce").fillna(0.0).astype(float)
    df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
    tr = fx.get(t_curr, 1.0)
    er = fx.get("EUR", 1.08) / tr
    mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / tr
    inv = float((df["Shares"] * df["Buy Price"] * mult).sum())
    mkt = float((df["Shares"] * df["Current Price"] * mult).sum())
    divs = float((df["Dividends EUR"] * er).sum() + (extra_eur * er))
    pnl = (mkt - inv) + divs
    ret = (pnl / inv * 100) if inv > 0 else 0.0
    return inv, mkt, pnl, ret, len(df)

x_inv, x_mkt, x_pnl, x_ret, x_n = calc_port(XTB_CSV, CLOSED_DIVS_EUR)
k_inv, k_mkt, k_pnl, k_ret, k_n = calc_port(KRK_CSV, 0.0)

tot_inv = x_inv + k_inv
tot_mkt = x_mkt + k_mkt
tot_pnl = x_pnl + k_pnl
tot_ret = (tot_pnl / tot_inv * 100) if tot_inv > 0 else 0.0

st.subheader("🌐 Rezumat Total Consolidat (XTB + Kraken)")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Capital Total Investit", f"{tot_inv:,.2f} {t_curr}")
m2.metric("Valoare Totală Piață", f"{tot_mkt:,.2f} {t_curr}")
m3.metric("Profit / Pierdere Net Total", f"{tot_pnl:+,.2f} {t_curr}", f"{tot_ret:+.2f}%")
m4.metric("Randament XTB", f"{x_pnl:+,.2f} {t_curr}", f"{x_ret:+.2f}%")
m5.metric("Randament Kraken", f"{k_pnl:+,.2f} {t_curr}", f"{k_ret:+.2f}%")

st.divider()
c1, c2, c3, c4 = st.columns(4)

with c1:
    with st.container(border=True):
        st.subheader("📈 Portofoliu XTB")
        st.metric("Valoare piață", f"{x_mkt:,.2f} {t_curr}", f"Randament net: {x_pnl:+,.2f} {t_curr} ({x_ret:+.2f}%)")
        st.caption(f"Capital investit: {x_inv:,.2f} {t_curr} • {x_n} poziții")
        if st.button("Deschide Portofoliu XTB ➡️", use_container_width=True, type="primary"):
            st.switch_page("pages/1_Portofoliu_XTB.py")

with c2:
    with st.container(border=True):
        st.subheader("🪙 Portofoliu Kraken")
        st.metric("Valoare piață", f"{k_mkt:,.2f} {t_curr}", f"Randament net: {k_pnl:+,.2f} {t_curr} ({k_ret:+.2f}%)")
        st.caption(f"Capital investit: {k_inv:,.2f} {t_curr} • {k_n} poziții")
        if st.button("Deschide Portofoliu Kraken ➡️", use_container_width=True, type="primary"):
            st.switch_page("pages/2_Portofoliu_Kraken.py")

with c3:
    with st.container(border=True):
        st.subheader("📊 XTB + Kraken")
        st.metric("Sinteză & Cash", f"{(tot_mkt + 164.22):,.2f} {t_curr}", "Vânzări, Dividende & Earn")
        st.caption("Bani nealocați, profit vânzări & earn")
        if st.button("Deschide XTB + Kraken ➡️", use_container_width=True, type="primary"):
            st.switch_page("pages/4_XTB_Kraken.py")

with c4:
    with st.container(border=True):
        st.subheader("👁️ Listă de Urmărire")
        st.metric("Watchlist & Dividende", "Monitorizare Live", "RSI, SMA 200 & Divident AN%")
        st.caption("Analiză tehnică și alerte de preț")
        if st.button("Deschide Urmărește ➡️", use_container_width=True, type="primary"):
            st.switch_page("pages/3_Urmareste.py")
