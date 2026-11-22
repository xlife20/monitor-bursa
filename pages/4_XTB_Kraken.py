import streamlit as st
import pandas as pd
import numpy as np
import csv, io
from pathlib import Path
from utils import save_csv_permanent, fetch_data

st.set_page_config(page_title="XTB + Kraken", layout="wide")
BASE = Path(__file__).resolve().parent.parent
XTB_CSV, KRK_CSV, STATS_CSV = BASE / "portfolio.csv", BASE / "portfolio_kraken.csv", BASE / "summary_stats.csv"

def gcol(r, i):
    return str(list(r)[i]).strip() if len(r) > i else ""

def to_num(val):
    s = str(val).strip().replace(" ", "").replace("€", "").replace("$", "")
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try: return float(s)
    except ValueError: return None

def load_stats():
    d = {"xtb_cash": 164.22, "xtb_closed_pnl": 0.0, "xtb_closed_divs": 18.24, "krk_cash": 0.0}
    if STATS_CSV.exists():
        try:
            for _, r in pd.read_csv(STATS_CSV).iterrows():
                k = str(r.get("key", ""))
                if k in d: d[k] = float(r.get("val", d[k]))
        except Exception: pass
    return d

def save_stats(d):
    return save_csv_permanent(pd.DataFrame([{"key": k, "val": round(float(v), 4)} for k, v in d.items()]), STATS_CSV)

def parse_xtb_any(up_f):
    cpnl, cdivs, ff, otks, rows, shs = 0.0, 0.0, None, set(), [], []
    if up_f.name.lower().endswith(".xlsx"):
        xl = pd.ExcelFile(up_f)
        shs = xl.sheet_names
        if "Tranzactii_XTB" in shs:
            tdf = xl.parse("Tranzactii_XTB").fillna("")
            iq, ic = {}, {}
            for _, r in tdf.iterrows():
                tk, tip = str(r.get("Simbol XTB", "")).strip(), str(r.get("Tip (BUY / SELL)", "")).strip().upper()
                q, p = to_num(r.get("Cantitate", "")), to_num(r.get("Preț Achiziție / Vânzare", ""))
                if not tk or q is None or p is None: continue
                if tip == "BUY": iq[tk], ic[tk] = iq.get(tk, 0.0) + q, ic.get(tk, 0.0) + q * p
                elif tip == "SELL" and iq.get(tk, 0.0) > 0:
                    ac = ic[tk] / iq[tk]
                    cpnl += (p - ac) * q
                    iq[tk] = max(iq[tk] - q, 0.0)
                    ic[tk] = iq[tk] * ac
            return ff, round(cpnl, 2), round(cdivs, 2), "Tranzactii_XTB"
        for sh in shs:
            for _, r in xl.parse(sh, header=None).fillna("").iterrows():
                rows.append([str(x).strip() for x in r.tolist()])
    else:
        shs = ["CSV"]
        for r in csv.reader(io.StringIO(up_f.getvalue().decode("utf-8", errors="ignore"))):
            rows.append([str(x).strip() for x in r])

    mode, pidx, tidx, aidx, yidx = "", -1, 2, 5, 0
    for r in rows:
        if not r or all(x == "" for x in r): continue
        low = [x.lower() for x in r]
        for i, c in enumerate(low):
            if any(k in c for k in ("free funds", "fondos libres", "saldo libre")):
                for nxt in r[i + 1:]:
                    v = to_num(nxt)
                    if v is not None: ff = v; break
        if any(k in low for k in ("hora de cierre", "close time")) and any(k in low for k in ("beneficio bruto", "beneficio neto", "beneficio/pérdida", "gross p/l", "net p/l", "profit/loss")):
            mode, pidx = "closed", -1
            for i, cn in enumerate(low):
                if cn in ("beneficio neto", "net p/l", "beneficio bruto", "gross p/l", "beneficio/pérdida", "profit/loss"): pidx = i; break
            continue
        if any(k in low for k in ("precio de apertura", "open price")):
            mode = "open"
            for i, cn in enumerate(low):
                if cn in ("símbolo", "simbolo", "ticker"): tidx = i
            continue
        if any(k in low for k in ("tipo", "type")) and any(k in low for k in ("importe", "cantidad", "amount")):
            mode = "cash"
            for i, cn in enumerate(low):
                if cn in ("tipo", "type"): yidx = i
                elif cn in ("símbolo", "simbolo", "ticker", "instrumento", "instrument"): tidx = i
                elif cn in ("importe", "amount"): aidx = i
            continue
        if gcol(r, 0).lower() in ("total", "número de cuenta", "account number", "nota", "note"): mode = ""; continue

        if mode == "closed" and pidx >= 0:
            if not gcol(r, 0).lower().startswith(("total", "producto", "product", "")):
                v = to_num(gcol(r, pidx))
                if v is not None: cpnl += v
        elif mode == "open" and "." in gcol(r, tidx):
            otks.add(gcol(r, tidx).replace(".US", "").replace(".UK", ".L").replace(".ES", ".MC").replace(".IT", ".MI"))
        elif mode == "cash":
            ot, amt = gcol(r, yidx).lower(), to_num(gcol(r, aidx))
            tk = gcol(r, tidx).replace(".US", "").replace(".UK", ".L").replace(".ES", ".MC").replace(".IT", ".MI")
            if amt is None: continue
            if ot in ("close trade", "cierre de operación", "cierre de operacion") and pidx < 0: cpnl += amt
            elif any(k in ot for k in ("dividend", "dividendo", "withholding", "retención", "retencion")) and tk and tk not in otks: cdivs += amt
    return ff, round(cpnl, 2), round(max(cdivs, 0.0), 2), ", ".join(shs)

def parse_krk_cash(up_f):
    kdf = pd.read_csv(up_f)
    kdf.columns = kdf.columns.str.lower().str.strip()
    if {"asset", "amount", "type"}.issubset(set(kdf.columns)):
        kdf["amount"], kdf["fee"] = pd.to_numeric(kdf["amount"], errors="coerce").fillna(0.0), pd.to_numeric(kdf.get("fee", 0.0), errors="coerce").fillna(0.0)
        er = kdf[kdf["asset"].astype(str).str.upper().isin(("EUR", "ZEUR"))]
        if not er.empty:
            if "balance" in kdf.columns:
                try: return round(float(pd.to_numeric(er["balance"], errors="coerce").dropna().iloc[-1]), 2)
                except Exception: pass
            return round(float((er["amount"] - er["fee"]).sum()), 2)
    return None

if st.button("⬅️ Meniu Principal"): st.switch_page("app.py")
if st.sidebar.button("🔄 Actualizează prețurile live"): st.cache_data.clear(); st.rerun()

st.title("📊 Sinteză Completă: XTB + Kraken")
tc = st.sidebar.selectbox("Monedă raportare", ("EUR", "USD", "GBP"))
stats = load_stats()

with st.expander("📥 Actualizează automat sumele nealocate și pozițiile închise din raport", expanded=False):
    u1, u2 = st.columns(2)
    with u1:
        f_xtb = st.file_uploader("Raport XTB (.xlsx sau .csv):", type=["xlsx", "csv"], key="s_xtb")
        if f_xtb is not None and st.button("Extrage date XTB", type="primary"):
            ff, cpnl, cdiv, ish = parse_xtb_any(f_xtb)
            if ff is not None: stats["xtb_cash"] = ff
            stats["xtb_closed_pnl"] = cpnl
            if cdiv > 0: stats["xtb_closed_divs"] = cdiv
            save_stats(stats)
            st.rerun()
    with u2:
        f_krk = st.file_uploader("Raport CSV Kraken Libro mayor:", type="csv", key="s_krk")
        if f_krk is not None and st.button("Extrage Cash Kraken", type="primary"):
            kc = parse_krk_cash(f_krk)
            if kc is not None: stats["krk_cash"] = kc; save_stats(stats); st.rerun()

def read_port(csv_p):
    if not csv_p.exists(): return 0.0, 0.0, 0.0, {"EUR": 1.08, "USD": 1.0, "GBP": 1.27}
    df = pd.read_csv(csv_p).fillna("")
    df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
    if df.empty: return 0.0, 0.0, 0.0, {"EUR": 1.08, "USD": 1.0, "GBP": 1.27}
    tks = df["Ticker"].astype(str).unique().tolist()
    prices, _, _, _, fx = fetch_data(tks, list(set(df["Currency"].astype(str).unique().tolist() + ["EUR", "USD", "GBP"])))
    for c in ("Shares", "Buy Price", "Current Price", "Dividends EUR"): df[c] = pd.to_numeric(df.get(c, 0.0), errors="coerce").fillna(0.0).astype(float)
    df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
    tr = fx.get(tc, 1.0)
    mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / tr
    return float((df["Shares"] * df["Buy Price"] * mult).sum()), float((df["Shares"] * df["Current Price"] * mult).sum()), float((df["Dividends EUR"] * (fx.get("EUR", 1.08) / tr)).sum()), fx

x_inv, x_mkt, x_odivs, fx = read_port(XTB_CSV)
k_inv, k_mkt, k_earn, _ = read_port(KRK_CSV)
er = fx.get("EUR", 1.08) / fx.get(tc, 1.0)

x_cash, x_cpnl, x_tdivs, x_unr = stats["xtb_cash"] * er, stats["xtb_closed_pnl"] * er, x_odivs + stats["xtb_closed_divs"] * er, x_mkt - x_inv
x_net = x_unr + x_cpnl + x_tdivs
k_cash, k_prof = stats["krk_cash"] * er, (k_mkt - k_inv) + k_earn

st.subheader("📈 Portofoliu XTB")
x1, x2, x3, x4, x5 = st.columns(5)
x1.metric("Suma investită (Activă)", f"{x_inv:,.2f} {tc}", f"Piață: {x_mkt:,.2f} {tc}")
x2.metric("Suma nealocată (Cash)", f"{x_cash:,.2f} {tc}")
x3.metric("Profit din vânzări acțiuni", f"{x_cpnl:+,.2f} {tc}", "Poziții închise (net)")
x4.metric("Profit dividende", f"+{x_tdivs:,.2f} {tc}", "Net încasate")
x5.metric("Profit / Pierdere Total XTB", f"{x_net:+,.2f} {tc}", f"Deschise: {x_unr:+,.2f} {tc}")

st.divider()
st.subheader("🪙 Portofoliu Kraken")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Suma investită", f"{k_inv:,.2f} {tc}", f"Piață: {k_mkt:,.2f} {tc}")
k2.metric("Suma nealocată (Cash)", f"{k_cash:,.2f} {tc}")
k3.metric("Câștig din Earn", f"+{k_earn:,.4f} {tc}")
k4.metric("Profit actualizat Kraken", f"{k_prof:+,.2f} {tc}", f"{((k_prof / k_inv * 100) if k_inv > 0 else 0.0):+.2f}%")

st.divider()
st.subheader("🌐 Total General (XTB + Kraken)")
g1, g2, g3, g4 = st.columns(4)
g1.metric("Total Investit", f"{(x_inv + k_inv):,.2f} {tc}")
g2.metric("Total Cash Nealocat", f"{(x_cash + k_cash):,.2f} {tc}")
g3.metric("Valoare Totală Conturi", f"{(x_mkt + x_cash + k_mkt + k_cash):,.2f} {tc}")
g4.metric("Profit Net Cumulat", f"{(x_net + k_prof):+,.2f} {tc}")

with st.expander("✏️ Ajustare manuală rapidă (Cash / Profit vânzări)", expanded=False):
    e1, e2, e3, e4 = st.columns(4)
