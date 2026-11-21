import streamlit as st
import pandas as pd
import numpy as np
import csv, io
from pathlib import Path
from utils import save_csv_permanent, get_meta, fetch_data, fetch_annual_dividends, c_pnl, c_rsi, f_price, f_shares, f_num2, f_rsi, f_sma, f_pct, clean_table, quick_del

st.set_page_config(page_title="Portofoliu XTB", layout="wide")
CSV_PATH = Path(__file__).resolve().parent.parent / "portfolio.csv"
CLOSED_DIVS_EUR = 18.24

def clean_tk(t):
    return str(t).replace(".US", "").replace(".UK", ".L").replace(".ES", ".MC").replace(".IT", ".MI").strip()

def gcol(r, i):
    return str(list(r)[i]).strip() if len(r) > i else ""

def parse_xtb(up_f, old_df):
    raw = up_f.getvalue().decode("utf-8", errors="ignore")
    divs, rows, mode = {}, [], ""
    for r in csv.reader(io.StringIO(raw)):
        if not r: continue
        f = gcol(r, 0)
        if f == "Type" and gcol(r, 5) == "Amount": mode = "cash"; continue
        if f == "Product" and gcol(r, 8) == "Open price": mode = "open"; continue
        if f in ("Total", "Account number", "Note"): mode = ""; continue
        if mode == "cash" and gcol(r, 0) in ("Dividend", "Withholding tax") and gcol(r, 2):
            tk = clean_tk(gcol(r, 2))
            try: divs[tk] = divs.get(tk, 0.0) + float(gcol(r, 5))
            except ValueError: pass
        elif mode == "open" and gcol(r, 0) in ("My Trades", "Investment Plan") and gcol(r, 2) and gcol(r, 3):
            rtk = gcol(r, 2)
            tk = clean_tk(rtk)
            if "CVR" in tk or "US931" in tk: continue
            try: vol, bp = float(gcol(r, 5)), float(gcol(r, 8))
            except ValueError: continue
            m = old_df[old_df["Ticker"].astype(str) == tk] if not old_df.empty else pd.DataFrame()
            if not m.empty:
                comp, sec, curr = str(next(iter(m["Company"]))), str(next(iter(m["Sector"]))), str(next(iter(m["Currency"])))
            else:
                comp, sec, curr = get_meta(tk)
                if rtk.endswith(".UK"): curr = "USD" if any(x in tk for x in ("ISLN", "EGLN", "SGLD", "COPX")) else "GBP"
            rows.append(dict(Ticker=tk, Company=comp, Sector=sec, Shares=vol, Buy=bp, Cur=bp, Currency=curr, Div=round(max(divs.get(tk, 0.0), 0.0), 2)))
    if not rows: return pd.DataFrame()
    rdf = pd.DataFrame(rows)
    out = []
    for tk, g in rdf.groupby("Ticker", sort=False):
        sh = g["Shares"].sum()
        ab = (g["Shares"] * g["Buy"]).sum() / sh if sh > 0 else 0.0
        out.append({"Ticker": str(tk), "Company": str(next(iter(g["Company"]))), "Sector": str(next(iter(g["Sector"]))), "Shares": round(float(sh), 6), "Buy Price": round(float(ab), 4), "Current Price": round(float(ab), 4), "Currency": str(next(iter(g["Currency"]))), "Dividends EUR": float(next(iter(g["Div"])))})
    return pd.DataFrame(out)

if "imp_xtb" not in st.session_state: st.session_state.imp_xtb = False
n1, n2, _ = st.columns((1.2, 1.2, 5.6))
if n1.button("⬅️ Meniu Principal", use_container_width=True): st.switch_page("app.py")
if n2.button("📥 Importă XTB", use_container_width=True): st.session_state.imp_xtb = not st.session_state.imp_xtb
if st.sidebar.button("🔄 Actualizează prețurile live"): st.cache_data.clear(); st.rerun()

req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]
df = pd.read_csv(CSV_PATH).fillna("") if CSV_PATH.exists() else pd.DataFrame(columns=req)
for c in req:
    if c not in df.columns: df[c] = 0.0 if c in ("Shares", "Buy Price", "Current Price", "Dividends EUR") else ""

if st.session_state.imp_xtb:
    with st.container(border=True):
        up_f = st.file_uploader("Încarcă raportul CSV din XTB:", type="csv", key="up_xtb")
        if up_f is not None and st.button("Procesează și Salvează Permanent", type="primary"):
            ndf = parse_xtb(up_f, df)
            if not ndf.empty:
                ok = save_csv_permanent(ndf.reindex(columns=req), CSV_PATH)
                st.session_state.imp_xtb = False
                st.cache_data.clear()
                st.success("Salvat permanent!" if ok else "Salvat local!")
                st.rerun()
            else: st.error("Nu am găsit poziții deschise valide.")

st.title("📈 Portofoliu XTB")
df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
tks = df["Ticker"].astype(str).unique().tolist()
acurr = sorted([x for x in df["Currency"].astype(str).unique().tolist() if x.strip()]) or ["EUR", "USD"]
prices, _, rsim, smam, fx = fetch_data(tks, list(set(acurr + ["EUR", "USD", "GBP"])))
adiv = fetch_annual_dividends(tks)

for c in ("Shares", "Buy Price", "Current Price", "Dividends EUR"):
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)

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
ediv = (CLOSED_DIVS_EUR * er) if cf == "Toate (Consolidat)" else 0.0
tmkt = v["Mkt"].sum()
v["Wgt"] = np.where(tmkt != 0, v["Mkt"] / tmkt * 100, 0.0).astype(float)

smap = {"Valoare piață": ("Mkt", False), "Profit Total": ("PnL", False), "Dividende": ("Div", False), "Dividende / an (Est.)": ("Ann_Div", False), "Dividend %": ("Div_Y", False), "YoC %": ("YoC", False), "Randament %": ("Ret", False), "RSI": ("RSI", True), "vs SMA 200 %": ("SMA_Pct", True), "Tiker": ("Ticker", True)}
cs, ascs = smap.get(sb)
v = v.sort_values(by=cs, ascending=ascs, na_position="last")

invs, mkts, divs = float(v["Inv"].sum()), float(v["Mkt"].sum()), float(v["Div"].sum() + ediv)
adivs = float(v["Ann_Div"].sum())
pyoc = (adivs / invs * 100) if invs > 0 else 0.0
gp = float(v[v["PnL"] > 0]["PnL"].sum() + ediv)
gl = float(v[v["PnL"] < 0]["PnL"].sum())

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Poziții", f"{len(v)}")
c2.metric("Capital investit", f"{invs:,.2f} {tc}")
c3.metric("Valoare piață", f"{mkts:,.2f} {tc}")
c4.metric("Dividende nete", f"{divs:,.2f} {tc}", f"~{adivs:,.2f} {tc}/an (YoC {pyoc:.2f}%)")
c5.metric("Profit Total (Poz.)", f"+{gp:,.2f} {tc}", f"{len(v[v['PnL'] > 0])} pe plus", delta_color="normal")
c6.metric("Pierdere Totală (Neg.)", f"{gl:,.2f} {tc}", f"-{len(v[v['PnL'] < 0])} pe minus", delta_color="normal")

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
