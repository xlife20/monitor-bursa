import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import save_csv_permanent, fetch_data, c_pnl, c_rsi, f_price, f_shares, f_num2, f_rsi, f_sma, f_pct, clean_table, quick_del

st.set_page_config(page_title="Portofoliu Kraken", layout="wide")
CSV_PATH = Path(__file__).resolve().parent.parent / "portfolio_kraken.csv"

st.markdown("<style>div[data-testid='stButton'] button p {font-size: 16px !important; font-weight: 700 !important;}</style>", unsafe_allow_html=True)

n1, n2, n3, n4 = st.columns(4)
if n1.button("⬅️ Meniu Principal", use_container_width=True): st.switch_page("app.py")
if n2.button("📈 Portofoliu XTB", use_container_width=True): st.switch_page("pages/1_Portofoliu_XTB.py")
if n3.button("👁️ Urmărește", use_container_width=True): st.switch_page("pages/3_Urmareste.py")
if n4.button("📊 XTB   Kraken", use_container_width=True): st.switch_page("pages/4_XTB_Kraken.py")

if st.sidebar.button("🔄 Actualizează prețurile live"): st.cache_data.clear(); st.rerun()

req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]
df = pd.read_csv(CSV_PATH).fillna("") if CSV_PATH.exists() else pd.DataFrame(columns=req)
for c in req:
    if c not in df.columns: df[c] = 0.0 if c in ("Shares", "Buy Price", "Current Price", "Dividends EUR") else ""
st.title("🪙 Portofoliu Kraken")
df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
tks = df["Ticker"].astype(str).unique().tolist()
acurr = sorted([x for x in df["Currency"].astype(str).unique().tolist() if x.strip()]) or ["EUR", "USD"]
prices, _, rsim, smam, fx = fetch_data(tks, list(set(acurr + ["EUR", "USD", "GBP"])))

for c in ("Shares", "Buy Price", "Current Price", "Dividends EUR"):
    df[c] = pd.to_numeric(df.get(c, 0.0), errors="coerce").fillna(0.0).astype(float)

df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsim), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(smam), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current Price"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)

tc = st.sidebar.selectbox("Monedă raportare", ("EUR", "USD", "GBP"))
cf = st.sidebar.selectbox("Filtrare monedă", ["Toate (Consolidat)"] + acurr)
sb = st.sidebar.selectbox("Ordonează după", ("Valoare piață", "Profit Total", "Recompense Earn", "Randament %", "RSI", "vs SMA 200 %", "Tiker"))

tr, er = fx.get(tc, 1.0), fx.get("EUR", 1.08) / fx.get(tc, 1.0)
mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / tr
df["Inv"] = df["Shares"] * df["Buy Price"] * mult
df["Mkt"] = df["Shares"] * df["Current Price"] * mult
df["Div"] = df["Dividends EUR"] * er
df["PnL"] = (df["Mkt"] - df["Inv"]) + df["Div"]
df["Ret"] = np.where(df["Inv"] != 0, df["PnL"] / df["Inv"] * 100, 0.0).astype(float)

v = df.copy() if cf == "Toate (Consolidat)" else df[df["Currency"] == cf].copy()
tmkt = v["Mkt"].sum()
v["Wgt"] = np.where(tmkt != 0, v["Mkt"] / tmkt * 100, 0.0).astype(float)

smap = {"Valoare piață": ("Mkt", False), "Profit Total": ("PnL", False), "Recompense Earn": ("Div", False), "Randament %": ("Ret", False), "RSI": ("RSI", True), "vs SMA 200 %": ("SMA_Pct", True), "Tiker": ("Ticker", True)}
cs, ascs = smap.get(sb)
v = v.sort_values(by=cs, ascending=ascs, na_position="last")

invs, mkts, divs = float(v["Inv"].sum()), float(v["Mkt"].sum()), float(v["Div"].sum())
net_pnl = (mkts - invs) + divs
net_ret = (net_pnl / invs * 100) if invs > 0 else 0.0
gp, gl = float(v[v["PnL"] > 0]["PnL"].sum()), float(v[v["PnL"] < 0]["PnL"].sum())

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
c1.metric("Monede", f"{len(v)}")
c2.metric("Capital investit", f"{invs:,.2f} {tc}")
c3.metric("Valoare piață", f"{mkts:,.2f} {tc}")
c4.metric("Randament Net Total", f"{net_pnl:+,.2f} {tc}", f"{net_ret:+.2f}%")
c5.metric("Recompense Earn", f"{divs:,.4f} {tc}")
c6.metric("Profit Total (Poz.)", f"+{gp:,.2f} {tc}", f"{len(v[v['PnL'] > 0])} pe plus", delta_color="normal")
c7.metric("Pierdere Totală (Neg.)", f"{gl:,.2f} {tc}", f"-{len(v[v['PnL'] < 0])} pe minus", delta_color="normal")

f_earn = lambda x: "" if (pd.isna(x) or x == "") else f"{float(x):,.4f}"

if not v.empty:
    cols = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "RSI", "SMA_Pct", "Current Price", "Currency", "Inv", "Mkt", "Div", "PnL", "Ret", "Wgt"]
    disp = v.reindex(columns=cols).copy()
    disp.columns = ["Tiker", "Monedă / Activ", "Categorie", "Cantitate", "Preț mediu", "RSI (14)", "vs SMA 200 %", "Preț curent", "Monedă", "Valoare investită", "Valoare piață", "Recompense Earn", "Profit / Pierdere", "Randament %", "Pondere %"]
    fmt = {"Cantitate": f_shares, "Preț mediu": f_price, "RSI (14)": f_rsi, "vs SMA 200 %": f_sma, "Preț curent": f_price, "Valoare investită": f_num2, "Valoare piață": f_num2, "Recompense Earn": f_earn, "Profit / Pierdere": f_num2, "Randament %": f_pct, "Pondere %": f_pct}
    styler = clean_table(disp, fmt).style.map(c_pnl, subset=["Profit / Pierdere", "Randament %", "vs SMA 200 %"]).map(c_rsi, subset=["RSI (14)"])
    st.dataframe(styler, use_container_width=True, hide_index=True, height=400, column_config={"Tiker": st.column_config.TextColumn("Tiker", pinned=True)})
    quick_del(df, req, CSV_PATH, "krk")
    l1, r1 = st.columns(2)
    with l1:
        st.subheader(f"Profit / Pierdere Total ({tc})")
        st.bar_chart(v.set_index("Ticker")[["PnL"]].assign(Color=np.where(v["PnL"] >= 0, "#00e676", "#ff5252")), y="PnL", color="Color")
    with r1:
        st.subheader(f"Valoare de piață ({tc})")
        st.bar_chart(v.set_index("Ticker")["Mkt"], color="#29b6f6")

st.subheader("Editare poziții (portfolio_kraken.csv)")
ed = st.data_editor(v.reindex(columns=req), num_rows="dynamic", use_container_width=True, key="ed_krk")
if st.button("Salvează modificările în portfolio_kraken.csv"):
    up = ed if cf == "Toate (Consolidat)" else pd.concat([df[df["Currency"] != cf].reindex(columns=req), ed], ignore_index=True)
    if not up.empty:
        ok = save_csv_permanent(up, CSV_PATH)
        st.cache_data.clear()
        st.success("Salvat permanent pe GitHub!" if ok else "Salvat local!")
