import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import save_csv_permanent, fetch_data, fetch_annual_dividends, c_pnl, c_rsi, f_price, f_shares, f_num2, f_rsi, f_sma, f_pct, clean_table, quick_del

st.set_page_config(page_title="Portofoliu XTB", layout="wide")
BASE = Path(__file__).resolve().parent.parent
CSV_PATH, STATS_CSV = BASE / "portfolio.csv", BASE / "summary_stats.csv"

st.markdown("<style>div[data-testid='stButton'] button p {font-size: 16px !important; font-weight: 700 !important;}</style>", unsafe_allow_html=True)

n1, n2, n3, n4, n5 = st.columns(5)
if n1.button("⬅️ Meniu Principal", use_container_width=True): st.switch_page("app.py")
if n2.button("🪙 Portofoliu Kraken", use_container_width=True): st.switch_page("pages/2_Portofoliu_Kraken.py")
if n3.button("👁️ Watchlist", use_container_width=True): st.switch_page("pages/3_Urmareste.py")
if n4.button("📊 XTB   Kraken", use_container_width=True): st.switch_page("pages/4_XTB_Kraken.py")
if n5.button("🔍 Analiză", use_container_width=True): st.switch_page("pages/5_Analiza.py")

if st.sidebar.button("🔄 Actualizează prețurile live"): st.cache_data.clear(); st.rerun()

req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]
df = pd.read_csv(CSV_PATH).fillna("") if CSV_PATH.exists() else pd.DataFrame(columns=req)
for c in req:
    if c not in df.columns: df[c] = 0.0 if c in ("Shares", "Buy Price", "Current Price", "Dividends EUR") else ""

ediv_eur = 23.99
if STATS_CSV.exists():
    try:
        for _, r in pd.read_csv(STATS_CSV).iterrows():
            if str(r.get("key", "")) == "xtb_closed_divs": ediv_eur = float(r.get("val", 23.99))
    except Exception: pass
st.title("📈 Portofoliu XTB")
df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
tks = df["Ticker"].astype(str).unique().tolist()
acurr = sorted([x for x in df["Currency"].astype(str).unique().tolist() if x.strip()]) or ["EUR", "USD"]
prices, _, rsim, smam, fx = fetch_data(tks, list(set(acurr + ["EUR", "USD", "GBP"])))
adiv = fetch_annual_dividends(tks)

for c in ("Shares", "Buy Price", "Current Price", "Dividends EUR"):
    df[c] = pd.to_numeric(df.get(c, 0.0), errors="coerce").fillna(0.0).astype(float)

df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsim), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(smam), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current Price"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)

tc = st.sidebar.selectbox("Monedă raportare", ("EUR", "USD", "GBP"))
cf = st.sidebar.selectbox("Filtrare monedă", ["Toate (Consolidat)"] + acurr)
sb = st.sidebar.selectbox("Ordonează după", ("Valoare piață", "Profit Total", "Dividende", "Dividende / an (Est.)", "Dividend %", "YoC %", "Randament %", "RSI", "vs SMA 200 %", "Tiker"))

tr, er = fx.get(tc, 1.0), fx.get("EUR", 1.08) / fx.get(tc, 1.0)
mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / tr
df["Div_Sh"] = pd.to_numeric(df["Ticker"].map(adiv), errors="coerce").fillna(0.0).astype(float)
df["Div_Y"] = np.where((df["Current Price"] > 0) & (df["Div_Sh"] > 0), (df["Div_Sh"] / df["Current Price"]) * 100, np.nan).astype(float)
df["YoC"] = np.where((df["Buy Price"] > 0) & (df["Div_Sh"] > 0), (df["Div_Sh"] / df["Buy Price"]) * 100, np.nan).astype(float)
df["Inv"] = df["Shares"] * df["Buy Price"] * mult
df["Mkt"] = df["Shares"] * df["Current Price"] * mult
df["Div"] = df["Dividends EUR"] * er
df["Ann_Div"] = df["Shares"] * df["Div_Sh"] * mult
df["PnL"] = (df["Mkt"] - df["Inv"]) + df["Div"]
df["Ret"] = np.where(df["Inv"] != 0, df["PnL"] / df["Inv"] * 100, 0.0).astype(float)

v = df.copy() if cf == "Toate (Consolidat)" else df[df["Currency"] == cf].copy()
ediv = (ediv_eur * er) if cf == "Toate (Consolidat)" else 0.0
tmkt = v["Mkt"].sum()
v["Wgt"] = np.where(tmkt != 0, v["Mkt"] / tmkt * 100, 0.0).astype(float)

smap = {"Valoare piață": ("Mkt", False), "Profit Total": ("PnL", False), "Dividende": ("Div", False), "Dividende / an (Est.)": ("Ann_Div", False), "Dividend %": ("Div_Y", False), "YoC %": ("YoC", False), "Randament %": ("Ret", False), "RSI": ("RSI", True), "vs SMA 200 %": ("SMA_Pct", True), "Tiker": ("Ticker", True)}
cs, ascs = smap.get(sb)
v = v.sort_values(by=cs, ascending=ascs, na_position="last")

invs, mkts, divs = float(v["Inv"].sum()), float(v["Mkt"].sum()), float(v["Div"].sum() + ediv)
adivs = float(v["Ann_Div"].sum())
pyoc = (adivs / invs * 100) if invs > 0 else 0.0
net_pnl = (mkts - invs) + divs
net_ret = (net_pnl / invs * 100) if invs > 0 else 0.0
gp, gl = float(v[v["PnL"] > 0]["PnL"].sum() + ediv), float(v[v["PnL"] < 0]["PnL"].sum())

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
c1.metric("Poziții", f"{len(v)}")
c2.metric("Capital investit", f"{invs:,.2f} {tc}")
c3.metric("Valoare piață", f"{mkts:,.2f} {tc}")
c4.metric("Randament Net Total", f"{net_pnl:+,.2f} {tc}", f"{net_ret:+.2f}%")
c5.metric("Dividende nete", f"{divs:,.2f} {tc}", f"~{adivs:,.2f} {tc}/an (YoC {pyoc:.2f}%)")
c6.metric("Profit Total (Poz.)", f"+{gp:,.2f} {tc}", f"{len(v[v['PnL'] > 0])} pe plus", delta_color="normal")
c7.metric("Pierdere Totală (Neg.)", f"{gl:,.2f} {tc}", f"-{len(v[v['PnL'] < 0])} pe minus", delta_color="normal")

fyoc = lambda x: "" if (pd.isna(x) or x == "" or float(x) <= 0) else f"{float(x):.2f}%"

if not v.empty:
    cols = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "RSI", "SMA_Pct", "Current Price", "Currency", "Inv", "Mkt", "Div", "Ann_Div", "Div_Y", "YoC", "PnL", "Ret", "Wgt"]
    disp = v.reindex(columns=cols).copy()
    disp.columns = ["Tiker", "Companie", "Sector", "Acțiuni", "Preț mediu", "RSI (14)", "vs SMA 200 %", "Preț curent", "Monedă", "Valoare investită", "Valoare piață", "Dividende", "Dividende / an (Est.)", "Dividend %", "YoC %", "Profit / Pierdere", "Randament %", "Pondere %"]
    fmt = {"Acțiuni": f_shares, "Preț mediu": f_price, "RSI (14)": f_rsi, "vs SMA 200 %": f_sma, "Preț curent": f_price, "Valoare investită": f_num2, "Valoare piață": f_num2, "Dividende": f_num2, "Dividende / an (Est.)": f_num2, "Dividend %": fyoc, "YoC %": fyoc, "Profit / Pierdere": f_num2, "Randament %": f_pct, "Pondere %": f_pct}
    styler = clean_table(disp, fmt).style.map(c_pnl, subset=["Profit / Pierdere", "Randament %", "vs SMA 200 %"]).map(c_rsi, subset=["RSI (14)"])
    st.dataframe(styler, use_container_width=True, hide_index=True, height=550, column_config={"Tiker": st.column_config.TextColumn("Tiker", pinned=True)})
    quick_del(df, req, CSV_PATH, "xtb")
    l1, r1 = st.columns(2)
    with l1:
        st.subheader(f"Profit / Pierdere Total ({tc})")
        st.bar_chart(v.set_index("Ticker")[["PnL"]].assign(Color=np.where(v["PnL"] >= 0, "#00e676", "#ff5252")), y="PnL", color="Color")
    with r1:
        st.subheader(f"Valoare de piață ({tc})")
        st.bar_chart(v.set_index("Ticker")["Mkt"], color="#29b6f6")

st.subheader("Editare poziții (portfolio.csv)")
ed = st.data_editor(v.reindex(columns=req), num_rows="dynamic", use_container_width=True, key="ed_xtb")
if st.button("Salvează modificările în portfolio.csv"):
    up = ed if cf == "Toate (Consolidat)" else pd.concat([df[df["Currency"] != cf].reindex(columns=req), ed], ignore_index=True)
    if not up.empty:
        ok = save_csv_permanent(up, CSV_PATH)
        st.cache_data.clear()
        st.success("Salvat permanent pe GitHub!" if ok else "Salvat local!")
