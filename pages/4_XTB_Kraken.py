import streamlit as st
import pandas as pd
import numpy as np
import csv, io
from pathlib import Path
from utils import save_csv_permanent, fetch_data

st.set_page_config(page_title="XTB + Kraken", layout="wide")
BASE = Path(__file__).resolve().parent.parent
XTB_CSV = BASE / "portfolio.csv"
KRK_CSV = BASE / "portfolio_kraken.csv"
STATS_CSV = BASE / "summary_stats.csv"

def gcol(r, i):
    return str(list(r)[i]).strip() if len(r) > i else ""

def to_num(val):
    s = str(val).strip().replace(" ", "").replace("€", "").replace("$", "")
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

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

def parse_xtb_any(up_f):
    closed_pnl, closed_divs, free_funds = 0.0, 0.0, None
    open_tks = set()
    rows_all = []
    sheets_found = []

    if up_f.name.lower().endswith(".xlsx"):
        xl = pd.ExcelFile(up_f)
        sheets_found = xl.sheet_names
        # Daca este fisierul Google Sheets cu Tranzactii_XTB (BUY / SELL)
        if "Tranzactii_XTB" in sheets_found:
            tdf = xl.parse("Tranzactii_XTB").fillna("")
            inv_qty, inv_cost = {}, {}
            for _, r in tdf.iterrows():
                tk = str(r.get("Simbol XTB", "")).strip()
                tip = str(r.get("Tip (BUY / SELL)", "")).strip().upper()
                q = to_num(r.get("Cantitate", ""))
                p = to_num(r.get("Preț Achiziție / Vânzare", ""))
                if not tk or q is None or p is None: continue
                if tip == "BUY":
                    inv_qty[tk] = inv_qty.get(tk, 0.0) + q
                    inv_cost[tk] = inv_cost.get(tk, 0.0) + (q * p)
                elif tip == "SELL" and inv_qty.get(tk, 0.0) > 0:
                    avg_c = inv_cost[tk] / inv_qty[tk]
                    closed_pnl += (p - avg_c) * q
                    inv_qty[tk] = max(inv_qty[tk] - q, 0.0)
                    inv_cost[tk] = inv_qty[tk] * avg_c
            return free_funds, round(closed_pnl, 2), round(closed_divs, 2), f"Tranzactii_XTB ({len(tdf)} rânduri)"

        for sh in sheets_found:
            df_sh = xl.parse(sh, header=None).fillna("")
            for _, r in df_sh.iterrows():
                rows_all.append([str(x).strip() for x in r.tolist()])
    else:
        sheets_found = ["CSV"]
        raw = up_f.getvalue().decode("utf-8", errors="ignore")
        for r in csv.reader(io.StringIO(raw)):
            rows_all.append([str(x).strip() for x in r])

    mode, pnl_idx, tk_idx, amt_idx, type_idx = "", -1, 2, 5, 0
    for r in rows_all:
        if not r or all(x == "" for x in r): continue
        low = [x.lower() for x in r]
        for idx, cell in enumerate(low):
            if any(k in cell for k in ("free funds", "fondos libres", "saldo libre", "margen libre")):
                for nxt in r[idx + 1:]:
                    v = to_num(nxt)
                    if v is not None:
                        free_funds = v
                        break
        if any(k in low for k in ("hora de cierre", "close time")) and any(k in low for k in ("beneficio bruto", "beneficio neto", "beneficio/pérdida", "gross p/l", "net p/l", "profit/loss")):
            mode, pnl_idx = "closed", -1
            for idx, col_n in enumerate(low):
                if col_n in ("beneficio neto", "net p/l", "beneficio bruto", "gross p/l", "beneficio/pérdida", "profit/loss"):
                    pnl_idx = idx; break
            continue
        if any(k in low for k in ("precio de apertura", "open price")) and any(k in low for k in ("producto", "product")):
            mode = "open"
            for idx, col_n in enumerate(low):
                if col_n in ("símbolo", "simbolo", "ticker"): tk_idx = idx
            continue
        if any(k in low for k in ("tipo", "type")) and any(k in low for k in ("importe", "cantidad", "amount")):
            mode = "cash"
            for idx, col_n in enumerate(low):
                if col_n in ("tipo", "type"): type_idx = idx
                elif col_n in ("símbolo", "simbolo", "ticker", "instrumento", "instrument"): tk_idx = idx
                elif col_n in ("importe", "amount"): amt_idx = idx
            continue
        if gcol(r, 0).lower() in ("total", "número de cuenta", "account number", "nota", "note"):
            mode = ""; continue

        if mode == "closed" and pnl_idx >= 0:
            first_c = gcol(r, 0).lower()
            if first_c not in ("", "total", "producto", "product") and not first_c.startswith("total"):
                v = to_num(gcol(r, pnl_idx))
                if v is not None: closed_pnl += v
        elif mode == "open":
            tk_raw = gcol(r, tk_idx)
            if tk_raw and "." in tk_raw:
                open_tks.add(tk_raw.replace(".US", "").replace(".UK", ".L").replace(".ES", ".MC").replace(".IT", ".MI"))
        elif mode == "cash":
            op_t = gcol(r, type_idx).lower()
            tk_raw = gcol(r, tk_idx)
            amt = to_num(gcol(r, amt_idx))
            if amt is None: continue
            tk = tk_raw.replace(".US", "").replace(".UK", ".L").replace(".ES", ".MC").replace(".IT", ".MI")
            if op_t in ("close trade", "cierre de operación", "cierre de operacion") and pnl_idx < 0:
                closed_pnl += amt
            elif any(k in op_t for k in ("dividend", "dividendo", "withholding", "retención", "retencion")) and tk and tk not in open_tks:
                closed_divs += amt

    return free_funds, round(closed_pnl, 2), round(max(closed_divs, 0.0), 2), ", ".join(sheets_found)

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

with st.expander("📥 Actualizează automat sumele nealocate și pozițiile închise din raport", expanded=False):
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        f_xtb = st.file_uploader("Raport XTB (.xlsx sau .csv):", type=["xlsx", "csv"], key="s_xtb")
        if f_xtb is not None and st.button("Extrage date XTB", type="primary"):
            ff, cpnl, cdiv, info_sh = parse_xtb_any(f_xtb)
            if ff is not None: stats["xtb_cash"] = ff
            stats["xtb_closed_pnl"] = cpnl
            if cdiv > 0: stats["xtb_closed_divs"] = cdiv
            ok = save_stats(stats)
            st.info(f"Citit din: {info_sh} | Cash: {ff} | Profit vânzări: {cpnl:+.2f} EUR" + (" (Salvat permanent)" if ok else ""))
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

