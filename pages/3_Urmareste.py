import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import load_csv, get_meta, fetch_data, c_pnl, c_target, c_rsi, f_price, f_rsi, f_sma, quick_del

st.set_page_config(page_title="Urmărește", layout="wide")
CSV_PATH = Path(__file__).resolve().parent.parent / "watchlist.csv"

if st.button("⬅️ Meniu Principal"):
    st.switch_page("app.py")
if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.cache_data.clear()
    st.rerun()

st.title("👁️ Listă de Urmărire (Watchlist)")
w_cols = ["Ticker", "Company", "Sector", "Target Price", "Currency"]
df = load_csv(CSV_PATH, w_cols).copy()

with st.expander("➕ Adaugă rapid mai multe tikere odată", expanded=False):
    raw = st.text_area("Introdu simbolurile separate prin virgulă sau spațiu:", placeholder="Ex: TSLA, KO, O, NVDA, NKE, BTC-EUR", height=70)
    if st.button("Adaugă în listă", type="primary"):
        new_l = [t.strip().upper() for t in raw.replace(",", " ").replace("\n", " ").split(" ") if t.strip()]
        ex = set(df["Ticker"].astype(str).str.upper().tolist())
        to_add = [t for t in dict.fromkeys(new_l) if t not in ex]
        if to_add:
            rows = []
            for t in to_add:
                comp, sec, curr = get_meta(t)
                rows.append(dict(Ticker=t, Company=comp, Sector=sec, Target_Price=0.0, Currency=curr))
            add_df = pd.DataFrame(rows).rename(columns=dict(Target_Price="Target Price"))
            pd.concat([df, add_df], ignore_index=True).to_csv(CSV_PATH, index=False)
            st.cache_data.clear()
            st.rerun()

quick_del(df, w_cols, CSV_PATH, "watch")

tickers = df["Ticker"].dropna().unique().tolist()
prices, prev_p, rsi_m, sma_m, _ = fetch_data(tickers, ["EUR", "USD", "GBP"])
df["Target Price"] = pd.to_numeric(df["Target Price"], errors="coerce").fillna(0.0).astype(float)
df["Current"] = pd.to_numeric(df["Ticker"].map(prices), errors="coerce").astype(float)
df["Prev"] = pd.to_numeric(df["Ticker"].map(prev_p), errors="coerce").astype(float)
df["Day_Pct"] = np.where(df["Prev"].notna() & (df["Prev"] != 0), (df["Current"] - df["Prev"]) / df["Prev"] * 100, np.nan).astype(float)
df["Diff_Target"] = np.where((df["Target Price"] > 0) & df["Current"].notna(), (df["Current"] - df["Target Price"]) / df["Target Price"] * 100, np.nan).astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsi_m), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(sma_m), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)

if not df.empty:
    disp = df[["Ticker", "Company", "Sector", "Current", "Day_Pct", "Target Price", "Diff_Target", "RSI", "SMA_Pct", "Currency"]].copy()
    disp.columns = ["Tiker", "Companie", "Sector", "Preț curent", "Variație Azi %", "Preț Țintă", "vs Țintă %", "RSI (14)", "vs SMA 200 %", "Monedă"]
    fmt = dict([("Preț curent", f_price), ("Variație Azi %", f_sma), ("Preț Țintă", f_price), ("vs Țintă %", f_sma), ("RSI (14)", f_rsi), ("vs SMA 200 %", f_sma)])
    styler = disp.style.map(c_pnl, subset=["Variație Azi %", "vs SMA 200 %"]).map(c_target, subset=["vs Țintă %"]).map(c_rsi, subset=["RSI (14)"]).format(fmt)
    st.dataframe(styler, use_container_width=True, hide_index=True, height=450, column_config=dict(Tiker=st.column_config.TextColumn("Tiker", pinned=True)))

st.subheader("Editare prețuri țintă (watchlist.csv)")
edited = st.data_editor(df[w_cols], num_rows="dynamic", use_container_width=True, key="ed_watch")
if st.button("Salvează modificările în watchlist.csv"):
    edited.to_csv(CSV_PATH, index=False)
    st.cache_data.clear()
    st.success("Salvat!")
