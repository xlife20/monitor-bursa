import streamlit as st
import pandas as pd
import numpy as np
import csv, io, json
from pathlib import Path
from utils import save_csv_permanent, fetch_data

st.set_page_config(page_title="XTB + Kraken", layout="wide")
BASE = Path(__file__).resolve().parent.parent
XTB_CSV = BASE / "portfolio.csv"
KRK_CSV = BASE / "portfolio_kraken.csv"
STATS_CSV = BASE / "summary_stats.csv"

def load_stats():
    defs = {"xtb_cash": 164.22, "xtb_closed_pnl": 0.0, "xtb_closed_divs": 18.24, "krk_cash": 0.0}
    if STATS_CSV.exists():
        try:
            sdf = pd.read_csv(STATS_CSV)
            for _, r in sdf.iterrows():
                k = str(r.get("key", ""))
                if k in defs: defs[k] = float(r.get("val", defs[k]))
        except Exception: pass
    return defs

def save_stats(d):
    sdf = pd.DataFrame([{"key": k, "val": round(float(v), 4)} for k, v in d.items()])
    return save_csv_permanent(sdf, STATS_CSV)

def parse_xtb_extra(up_f):
    raw = up_f.getvalue().decode("utf-8", errors="ignore")
    closed_pnl, closed_divs, free_funds = 0.0, 0.0, None
    mode = ""
    open_tks = set()
    for r in csv.reader(io.StringIO(raw)):
        if not r: continue
        c0 = str(list(r)[0]).strip()
        c2 = str(list(r)[2]).strip() if len(r) > 2 else ""
        c5 = str(list(r)[5]).strip() if len(r) > 5 else ""
        if c0 == "Free funds" and len(r) > 1:
            try: free_funds = float(str(list(r)[1]).strip())
            except ValueError: pass
        if c0 == "Product" and len(r) >= 9 and str(list(r)[8]).strip() == "Open price":
            mode = "open"; continue
        if c0 == "Type" and len(r) >= 6 and c5 == "Amount":
            mode = "cash"; continue
        if c0 in ("Total", "Account number", "Note"):
            mode = ""; continue
        if mode == "open" and c0 in ("My Trades", "Investment Plan") and c2:
            open_tks.add(c2.replace(".US", "").replace(".UK", ".L").replace(".ES", ".MC").replace(".IT", ".MI"))
        elif mode == "cash" and c2:
            tk = c2.replace(".US", "").replace(".UK", ".L").replace(".ES", ".MC").replace(".IT", ".MI")
            try: amt = float(c5)
            except ValueError: continue
            if c0 == "close trade":
                closed_pnl += amt
            elif c0 in ("Dividend", "Withholding tax") and tk not in open_tks:
                closed_divs += amt
    return free_funds, round(closed_pnl, 2), round(max(closed_divs, 0.0), 2)

def parse_krk_cash(up_f):
    kdf = pd.read_csv(up_f)
    kdf.columns = kdf.columns.str.lower().str.strip()
    if {"asset", "amount", "type"}.issubset(set(kdf.columns)):
        kdf["amount"] = pd.to_numeric(kdf["amount"], errors="coerce").fillna(0.0)
        kdf["fee"] = pd.to_numeric(kdf.get("fee", 0.0), errors="coerce").fillna(0.0)
        eur_rows = kdf[kdf["asset"].astype(str).str.upper().isin(("EUR", "ZEUR"))]
        if not eur_rows.empty:
            if "balance" in kdf.columns:
                try: return round(float(pd.to_numeric(eur_rows["balance"], errors="coerce").dropna().iloc[-1]), 2)
                except Exception: pass
            return round(float((eur_rows["amount"] - eur_rows["fee"]).sum()), 2)
    return None

if st.button("⬅️ Meniu Principal"): st.switch_page("app.py")
if st.sidebar.button("🔄 Actualizează prețurile live"): st.cache_data.clear(); st.rerun()

st.title("📊 Sinteză Completă: XTB + Kraken")
tc = st.sidebar.selectbox("Monedă raportare", ("EUR", "USD", "GBP"))
stats = load_stats()

with st.expander("📥 Actualizează automat sumele nealocate și pozițiile închise din CSV", expanded=False):
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        f_xtb = st.file_uploader("Raport CSV XTB (pentru Cash + Profit vânzări):", type="csv", key="s_xtb")
        if f_xtb is not None and st.button("Extrage date XTB", type="primary"):
            ff, cpnl, cdiv = parse_xtb_extra(f_xtb)
            if ff is not None: stats["xtb_cash"] = ff
            stats["xtb_closed_pnl"] = cpnl
            stats["xtb_closed_divs"] = cdiv
            ok = save_stats(stats)
            st.success("Date XTB actualizate permanent!" if ok else "Date XTB actualizate!")
            st.rerun()
    with col_u2:
        f_krk = st.file_uploader("Raport CSV Kraken Libro mayor (pentru Cash EUR):", type="csv", key="s_krk")
        if f_krk is not None and st.button("Extrage Cash Kraken", type="primary"):
            kc = parse_krk_cash(f_krk)
            if kc is not None:
                stats["krk_cash"] = kc
                ok = save_stats(stats)
                st.success("Cash Kraken actualizat permanent!" if ok else "Cash Kraken actualizat!")
                st.rerun()

def read_port(csv_p):
    if not csv_p.exists(): return 0.0, 0.0, 0.0, {"EUR": 1.08, "USD": 1.0, "GBP": 1.27}
    df = pd.read_csv(csv_p).fillna("")
    df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
    if df.empty: return 0.0, 0.0, 0.0, {"EUR": 1.08, "USD": 1.0, "GBP": 1.27}
    tks = df["Ticker"].astype(str).unique().tolist()
    currs = list(set(df["Currency"].astype(str).unique().tolist() + ["EUR", "USD", "GBP"]))
    prices, _, _, _, fx = fetch_data(tks, currs)
    for c in ("Shares", "Buy Price", "Current Price", "Dividends EUR"):
        df[c] = pd.to_numeric(df.get(c, 0.0), errors="coerce").fillna(0.0).astype(float)
    df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
    tr = fx.get(tc, 1.0)
    er = fx.get("EUR", 1.08) / tr
    mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / tr
    inv = float((df["Shares"] * df["Buy Price"] * mult).sum())
    mkt = float((df["Shares"] * df["Current Price"] * mult).sum())
    divs = float((df["Dividends EUR"] * er).sum())
    return inv, mkt, divs, fx

x_inv, x_mkt, x_open_divs, fx = read_port(XTB_CSV)
k_inv, k_mkt, k_earn, _ = read_port(KRK_CSV)

tr = fx.get(tc, 1.0)
er = fx.get("EUR", 1.08) / tr

x_cash = stats["xtb_cash"] * er
x_closed_pnl = stats["xtb_closed_pnl"] * er
x_tot_divs = x_open_divs + (stats["xtb_closed_divs"] * er)
x_unrealized = x_mkt - x_inv
x_net_total = x_unrealized + x_closed_pnl + x_tot_divs

k_cash = stats["krk_cash"] * er
k_profit_live = (k_mkt - k_inv) + k_earn

st.subheader("📈 Portofoliu XTB")
x1, x2, x3, x4, x5 = st.columns(5)
x1.metric("Suma investită (Activă)", f"{x_inv:,.2f} {tc}", f"Piață: {x_mkt:,.2f} {tc}")
x2.metric("Suma nealocată (Cash)", f"{x_cash:,.2f} {tc}")
x3.metric("Profit din vânzări acțiuni", f"{x_closed_pnl:+,.2f} {tc}", "Poziții închise (net)")
x4.metric("Profit dividende", f"+{x_tot_divs:,.2f} {tc}", "Net încasate")
x5.metric("Profit / Pierdere Total XTB", f"{x_net_total:+,.2f} {tc}", f"Deschise: {x_unrealized:+,.2f} {tc}")

st.divider()
st.subheader("🪙 Portofoliu Kraken")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Suma investită", f"{k_inv:,.2f} {tc}", f"Piață: {k_mkt:,.2f} {tc}")
k2.metric("Suma nealocată (Cash)", f"{k_cash:,.2f} {tc}")
k3.metric("Câștig din Earn", f"+{k_earn:,.4f} {tc}")
k4.metric("Profit actualizat Kraken", f"{k_profit_live:+,.2f} {tc}", f"{((k_profit_live / k_inv * 100) if k_inv > 0 else 0.0):+.2f}%")

st.divider()
st.subheader("🌐 Total General (XTB + Kraken)")
g1, g2, g3, g4 = st.columns(4)
g1.metric("Total Investit", f"{(x_inv + k_inv):,.2f} {tc}")
g2.metric("Total Cash Nealocat", f"{(x_cash + k_cash):,.2f} {tc}")
g3.metric("Valoare Totală Conturi", f"{(x_mkt + x_cash + k_mkt + k_cash):,.2f} {tc}")
g4.metric("Profit Net Cumulat", f"{(x_net_total + k_profit_live):+,.2f} {tc}")

with st.expander("✏️ Ajustare manuală rapidă (Cash / Profit vânzări)", expanded=False):
    c_e1, c_e2, c_e3, c_e4 = st.columns(4)
    nx_cash = c_e1.number_input("Cash XTB (EUR)", value=float(stats["xtb_cash"]), step=1.0)
    nx_cpnl = c_e2.number_input("Profit vânzări XTB (EUR)", value=float(stats["xtb_closed_pnl"]), step=1.0)
    nx_cdiv = c_e3.number_input("Dividende poziții închise XTB (EUR)", value=float(stats["xtb_closed_divs"]), step=1.0)
    nk_cash = c_e4.number_input("Cash Kraken (EUR)", value=float(stats["krk_cash"]), step=1.0)
    if st.button("Salvează valorile manual"):
        ok = save_stats({"xtb_cash": nx_cash, "xtb_closed_pnl": nx_cpnl, "xtb_closed_divs": nx_cdiv, "krk_cash": nk_cash})
        st.success("Salvat permanent pe GitHub!" if ok else "Salvat local!")
        st.rerun()
