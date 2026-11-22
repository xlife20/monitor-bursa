import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import fetch_data, fetch_annual_dividends, c_pnl, c_rsi, f_price, f_rsi, f_sma, f_pct, clean_table

st.set_page_config(page_title="Analiză", layout="wide")
BASE = Path(__file__).resolve().parent.parent
CSV_PATH, XTB_PATH = BASE / "watchlist.csv", BASE / "portfolio.csv"

st.markdown("<style>div[data-testid='stButton'] button p {font-size: 15px !important; font-weight: 700 !important;}</style>", unsafe_allow_html=True)
if "an_flt" not in st.session_state: st.session_state.an_flt = "rsi"

n1, n2, n3, n4, n5 = st.columns(5)
if n1.button("⬅️ Meniu Principal", use_container_width=True): st.switch_page("app.py")
if n2.button("📈 Portofoliu XTB", use_container_width=True): st.switch_page("pages/1_Portofoliu_XTB.py")
if n3.button("🪙 Portofoliu Kraken", use_container_width=True): st.switch_page("pages/2_Portofoliu_Kraken.py")
if n4.button("👁️ Watchlist", use_container_width=True): st.switch_page("pages/3_Urmareste.py")
if n5.button("📊 XTB   Kraken", use_container_width=True): st.switch_page("pages/4_XTB_Kraken.py")

if st.sidebar.button("🔄 Actualizează prețurile live"): st.cache_data.clear(); st.rerun()

st.markdown("<h1 style='text-align:center;margin-top:4px;margin-bottom:0;'>🔍 Analiză</h1>", unsafe_allow_html=True)
st.markdown("<br><br>", unsafe_allow_html=True)

_, b_rsi, b_sma, _ = st.columns((2.5, 1.5, 1.5, 2.5))
if b_rsi.button("📉 RSI < 30", use_container_width=True): st.session_state.an_flt = "rsi"
if b_sma.button("📊 SMA200 <", use_container_width=True): st.session_state.an_flt = "sma"

df = pd.read_csv(CSV_PATH).fillna("") if CSV_PATH.exists() else pd.DataFrame(columns=["Ticker", "Company", "Sector", "Avg Price", "Currency"])
t_col = "Avg Price" if "Avg Price" in df.columns else "Target Price"
for c in ("Ticker", "Company", "Sector", t_col, "Currency"):
    if c not in df.columns: df[c] = 0.0 if c == t_col else ""

xtb_avg = {}
if XTB_PATH.exists():
    try:
        for _, r in pd.read_csv(XTB_PATH).fillna("").iterrows():
            tk = str(r.get("Ticker", "")).strip().upper()
            bp = pd.to_numeric(r.get("Buy Price", 0.0), errors="coerce")
            if tk and pd.notna(bp) and bp > 0: xtb_avg[tk] = float(bp)
    except Exception: pass

df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
tks = df["Ticker"].astype(str).unique().tolist()
acurr = sorted([x for x in df["Currency"].astype(str).unique().tolist() if x.strip()]) or ["EUR", "USD"]
prices, changes, rsim, smam, _ = fetch_data(tks, list(set(acurr + ["EUR", "USD", "GBP"])))
adiv = fetch_annual_dividends(tks)

df[t_col] = pd.to_numeric(df.get(t_col, 0.0), errors="coerce").fillna(0.0).astype(float)
df["XTB_P"] = df["Ticker"].astype(str).str.upper().map(xtb_avg)
df[t_col] = np.where(df["XTB_P"].notna(), df["XTB_P"], df[t_col]).astype(float)
df["Current Price"] = pd.to_numeric(df["Ticker"].map(prices), errors="coerce").astype(float)
df["Day_Pct"] = pd.to_numeric(df["Ticker"].map(changes), errors="coerce").astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsim), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(smam), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current Price"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)
df["vs_Target"] = np.where((df[t_col] > 0) & df["Current Price"].notna(), (df["Current Price"] - df[t_col]) / df[t_col] * 100, np.nan).astype(float)
df["Div_Sh"] = pd.to_numeric(df["Ticker"].map(adiv), errors="coerce").fillna(0.0).astype(float)
df["Div_Y"] = np.where((df["Current Price"] > 0) & (df["Div_Sh"] > 0), (df["Div_Sh"] / df["Current Price"]) * 100, np.nan).astype(float)

fyoc = lambda x: "" if (pd.isna(x) or x == "" or float(x) <= 0) else f"{float(x):.2f}%"
f_avg = lambda x: "" if (pd.isna(x) or x == "" or float(x) <= 0) else f_price(x)

if st.session_state.an_flt == "sma":
    sub = df[df["SMA_Pct"].notna() & (df["SMA_Pct"] < 0)].sort_values(by="SMA_Pct", ascending=True).head(5)
    st.subheader("📊 Top 5 Acțiuni sub SMA 200 (De la cea mai mare scădere)")
else:
    sub = df[df["RSI"].notna() & (df["RSI"] < 30)].sort_values(by="RSI", ascending=True).head(5)
    st.subheader("📉 Top 5 Acțiuni cu RSI < 30 (Crescător)")

if sub.empty:
    st.info("Nicio acțiune nu îndeplinește criteriul selectat în acest moment.")
else:
    cols = ["Ticker", "Company", "Currency", "Sector", "vs_Target", t_col, "Current Price", "Div_Y", "RSI", "SMA_Pct", "Day_Pct"]
    disp = sub.reindex(columns=cols).copy()
    disp.columns = ["Tiker", "Companie", "Monedă", "Sector", "vs Preț mediu %", "Preț mediu", "Preț curent", "Dividend AN%", "RSI (14)", "vs SMA 200 %", "Variație azi %"]
    fmt = {"Preț mediu": f_avg, "Preț curent": f_price, "Dividend AN%": fyoc, "RSI (14)": f_rsi, "vs SMA 200 %": f_sma, "vs Preț mediu %": f_pct, "Variație azi %": f_pct}
    styler = clean_table(disp, fmt).style.map(c_pnl, subset=["vs Preț mediu %", "vs SMA 200 %", "Variație azi %"]).map(c_rsi, subset=["RSI (14)"])
    st.dataframe(styler, use_container_width=True, hide_index=True, height=230, column_config={"Tiker": st.column_config.TextColumn("Tiker", pinned=True)})
