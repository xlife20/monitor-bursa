import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import load_csv, get_meta, fetch_data, c_pnl, c_rsi, f_price, f_rsi, f_sma, quick_del

st.set_page_config(page_title="Urmărește", layout="wide")
CSV_PATH = Path(__file__).resolve().parent.parent / "watchlist.csv"
XTB_CSV = Path(__file__).resolve().parent.parent / "portfolio.csv"

if st.button("⬅️ Meniu Principal"):
    st.switch_page("app.py")
if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.cache_data.clear()
    st.rerun()

st.title("👁️ Listă de Urmărire (Watchlist)")
w_cols = ["Ticker", "Company", "Currency", "Sector"]
df = load_csv(CSV_PATH, w_cols).copy()

for c in w_cols:
    if c not in df.columns:
        df[c] = ""

xtb_df = load_csv(XTB_CSV, ["Ticker", "Company", "Currency", "Sector", "Buy Price"]).copy()
avg_price_map = dict()
if not xtb_df.empty and "Buy Price" in xtb_df.columns:
    xtb_df["Buy Price"] = pd.to_numeric(xtb_df["Buy Price"], errors="coerce")
    avg_price_map = xtb_df.dropna(subset=["Ticker", "Buy Price"]).set_index("Ticker")["Buy Price"].to_dict()

col_imp, _ = st.columns([1.4, 2.6])
with col_imp:
    if st.button("📥 Importă companiile din Portofoliu XTB", use_container_width=True):
        if not xtb_df.empty:
            ex = set(df["Ticker"].astype(str).str.upper().tolist())
            new_from_xtb = xtb_df[~xtb_df["Ticker"].astype(str).str.upper().isin(ex)][w_cols]
            if not new_from_xtb.empty:
                pd.concat([df[w_cols], new_from_xtb], ignore_index=True).to_csv(CSV_PATH, index=False)
                st.cache_data.clear()
                st.rerun()
            else:
                st.info("Toate companiile din XTB sunt deja în listă.")

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
                rows.append(dict(Ticker=t, Company=comp, Currency=curr, Sector=sec))
            add_df = pd.DataFrame(rows)
            pd.concat([df[w_cols], add_df], ignore_index=True).to_csv(CSV_PATH, index=False)
            st.cache_data.clear()
            st.rerun()

quick_del(df, w_cols, CSV_PATH, "watch")

tickers = df["Ticker"].dropna().unique().tolist()
prices, _, rsi_m, sma_m, _ = fetch_data(tickers, ["EUR", "USD", "GBP"])
df["Avg_Price"] = pd.to_numeric(df["Ticker"].map(avg_price_map), errors="coerce").astype(float)
df["Current"] = pd.to_numeric(df["Ticker"].map(prices), errors="coerce").astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsi_m), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(sma_m), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)

def f_avg_blank(v):
    return "" if pd.isna(v) else (f"{v:,.4f}" if abs(v) < 2 else f"{v:,.2f}")

if not df.empty:
    disp = df[["Ticker", "Company", "Currency", "Sector", "Avg_Price", "Current", "RSI", "SMA_Pct"]].copy()
    disp.columns = ["Tiker", "Companie", "Monedă", "Sector", "Preț mediu", "Preț curent", "RSI (14)", "vs SMA 200 %"]
    fmt = dict([("Preț mediu", f_avg_blank), ("Preț curent", f_price), ("RSI (14)", f_rsi), ("vs SMA 200 %", f_sma)])
    styler = disp.style.map(c_pnl, subset=["vs SMA 200 %"]).map(c_rsi, subset=["RSI (14)"]).format(fmt)
    st.dataframe(styler, use_container_width=True, hide_index=True, height=450, column_config=dict(Tiker=st.column_config.TextColumn("Tiker", pinned=True)))

st.subheader("Editare listă (watchlist.csv)")
edited = st.data_editor(df[w_cols], num_rows="dynamic", use_container_width=True, key="ed_watch")
if st.button("Salvează modificările în watchlist.csv"):
    edited.to_csv(CSV_PATH, index=False)
    st.cache_data.clear()
    st.success("Salvat!")
