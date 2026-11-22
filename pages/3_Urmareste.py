import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import save_csv_permanent, get_meta, fetch_data, fetch_annual_dividends, c_pnl, c_rsi, f_price, f_rsi, f_sma, f_pct, clean_table

st.set_page_config(page_title="Watchlist", layout="wide")
CSV_PATH = Path(__file__).resolve().parent.parent / "watchlist.csv"

st.markdown("<style>div[data-testid='stButton'] button p {font-size: 16px !important; font-weight: 700 !important;}</style>", unsafe_allow_html=True)

for k_ss in ("w_add", "w_del"):
    if k_ss not in st.session_state: st.session_state[k_ss] = False

n1, n2, n3, n4 = st.columns(4)
if n1.button("⬅️ Meniu Principal", use_container_width=True): st.switch_page("app.py")
if n2.button("📈 Portofoliu XTB", use_container_width=True): st.switch_page("pages/1_Portofoliu_XTB.py")
if n3.button("🪙 Portofoliu Kraken", use_container_width=True): st.switch_page("pages/2_Portofoliu_Kraken.py")
if n4.button("📊 XTB   Kraken", use_container_width=True): st.switch_page("pages/4_XTB_Kraken.py")

if st.sidebar.button("🔄 Actualizează prețurile live"): st.cache_data.clear(); st.rerun()

df = pd.read_csv(CSV_PATH).fillna("") if CSV_PATH.exists() else pd.DataFrame(columns=["Ticker", "Company", "Sector", "Avg Price", "Currency"])
t_col = "Avg Price" if "Avg Price" in df.columns else "Target Price"
req = ["Ticker", "Company", "Sector", t_col, "Currency"]
for c in req:
    if c not in df.columns: df[c] = 0.0 if c == t_col else ""

h1, h2, h3 = st.columns((1.6, 4.8, 1.6))
if h1.button("➕ Adaugă tiker", use_container_width=True): st.session_state.w_add = not st.session_state.w_add; st.session_state.w_del = False
h2.markdown("<h1 style='text-align:center;margin:0;padding:0;'>👁️ Watchlist</h1>", unsafe_allow_html=True)
if h3.button("🗑️ Șterge tiker", use_container_width=True): st.session_state.w_del = not st.session_state.w_del; st.session_state.w_add = False

if st.session_state.w_add:
    with st.container(border=True):
        raw_tks = st.text_input("Introdu tikere separate prin virgulă (ex: AAPL, MSFT, O, SCHD):", key="w_in_tks")
        if st.button("Salvează tikerele", type="primary") and raw_tks.strip():
            new_list = [x.strip().upper() for x in raw_tks.split(",") if x.strip()]
            ex_set = set(df["Ticker"].astype(str).str.upper().tolist())
            added = []
            for tk in new_list:
                if tk not in ex_set:
                    comp, sec, curr = get_meta(tk)
                    added.append({"Ticker": tk, "Company": comp, "Sector": sec, t_col: 0.0, "Currency": curr})
                    ex_set.add(tk)
            if added:
                ndf = pd.concat([df.reindex(columns=req), pd.DataFrame(added)], ignore_index=True)
                save_csv_permanent(ndf, CSV_PATH)
                st.session_state.w_add = False
                st.cache_data.clear()
                st.rerun()

if st.session_state.w_del:
    with st.container(border=True):
        tks_del = df["Ticker"].astype(str).tolist() if not df.empty else []
        if tks_del:
            c_d1, c_d2 = st.columns((3, 1))
            sel_d = c_d1.selectbox("Alege tikerul de șters:", tks_del, key="w_sel_del")
            if c_d2.button("Confirmă ștergerea", type="primary"):
                ndf = df[df["Ticker"].astype(str) != sel_d].reindex(columns=req)
                save_csv_permanent(ndf, CSV_PATH)
                st.session_state.w_del = False
                st.cache_data.clear()
                st.rerun()
df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
tks = df["Ticker"].astype(str).unique().tolist()
acurr = sorted([x for x in df["Currency"].astype(str).unique().tolist() if x.strip()]) or ["EUR", "USD"]
prices, changes, rsim, smam, fx = fetch_data(tks, list(set(acurr + ["EUR", "USD", "GBP"])))
adiv = fetch_annual_dividends(tks)

df[t_col] = pd.to_numeric(df.get(t_col, 0.0), errors="coerce").fillna(0.0).astype(float)
df["Current Price"] = pd.to_numeric(df["Ticker"].map(prices), errors="coerce").astype(float)
df["Day_Pct"] = pd.to_numeric(df["Ticker"].map(changes), errors="coerce").astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsim), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(smam), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current Price"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)
df["vs_Target"] = np.where((df[t_col] > 0) & df["Current Price"].notna(), (df["Current Price"] - df[t_col]) / df[t_col] * 100, np.nan).astype(float)
df["Div_Sh"] = pd.to_numeric(df["Ticker"].map(adiv), errors="coerce").fillna(0.0).astype(float)
df["Div_Y"] = np.where((df["Current Price"] > 0) & (df["Div_Sh"] > 0), (df["Div_Sh"] / df["Current Price"]) * 100, np.nan).astype(float)

v = df.sort_values(by="Ticker", ascending=True)
fyoc = lambda x: "" if (pd.isna(x) or x == "" or float(x) <= 0) else f"{float(x):.2f}%"

if not v.empty:
    cols = ["Ticker", "Company", "Currency", "Sector", "vs_Target", t_col, "Current Price", "Div_Y", "RSI", "SMA_Pct", "Day_Pct"]
    disp = v.reindex(columns=cols).copy()
    disp.columns = ["Tiker", "Companie", "Monedă", "Sector", "vs Preț mediu %", "Preț mediu", "Preț curent", "Dividend AN%", "RSI (14)", "vs SMA 200 %", "Variație azi %"]
    fmt = {"Preț mediu": f_price, "Preț curent": f_price, "Dividend AN%": fyoc, "RSI (14)": f_rsi, "vs SMA 200 %": f_sma, "vs Preț mediu %": f_pct, "Variație azi %": f_pct}
    styler = clean_table(disp, fmt).style.map(c_pnl, subset=["vs Preț mediu %", "vs SMA 200 %", "Variație azi %"]).map(c_rsi, subset=["RSI (14)"])
    st.dataframe(styler, use_container_width=True, hide_index=True, height=580, column_config={"Tiker": st.column_config.TextColumn("Tiker", pinned=True)})

st.subheader("Editare listă urmărire (watchlist.csv)")
ed = st.data_editor(v.reindex(columns=req), num_rows="dynamic", use_container_width=True, key="ed_wl")
if st.button("Salvează modificările în watchlist.csv"):
    if not ed.empty:
        ok = save_csv_permanent(ed, CSV_PATH)
        st.cache_data.clear()
        st.success("Salvat permanent pe GitHub!" if ok else "Salvat local!")
