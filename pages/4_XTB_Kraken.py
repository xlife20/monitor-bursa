import streamlit as st
import pandas as pd
import numpy as np
import csv, io
from pathlib import Path
from utils import save_csv_permanent, get_meta, fetch_data

st.set_page_config(page_title="XTB + Kraken", layout="wide")
BASE = Path(__file__).resolve().parent.parent
XTB_CSV, KRK_CSV, STATS_CSV = BASE / "portfolio.csv", BASE / "portfolio_kraken.csv", BASE / "summary_stats.csv"

def gcol(r, i):
    return str(list(r)[i]).strip() if len(r) > i else ""

def clean_tk(t):
    return str(t).replace(".US", "").replace(".UK", ".L").replace(".ES", ".MC").replace(".IT", ".MI").strip()

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

def parse_xtb_complete(up_f, old_df):
    rows = []
    if up_f.name.lower().endswith(".xlsx"):
        xl = pd.ExcelFile(up_f)
        for sh in xl.sheet_names:
            for _, r in xl.parse(sh, header=None).fillna("").iterrows():
                rows.append([str(x).strip() for x in r.tolist()])
    else:
        for r in csv.reader(io.StringIO(up_f.getvalue().decode("utf-8", errors="ignore"))):
            rows.append([str(x).strip() for x in r])

    divs, open_rows, mode = {}, [], ""
    cpnl, ff = 0.0, None
    pidx, tidx, vidx, oidx, aidx, yidx = -1, 2, 5, 8, 5, 0

    for r in rows:
        if not r or all(x == "" for x in r): continue
        low = [x.lower() for x in r]
        for i, c in enumerate(low):
            if any(k in c for k in ("free funds", "fondos libres", "saldo libre", "margen libre")):
                for nxt in r[i + 1:]:
                    v = to_num(nxt)
                    if v is not None: ff = v; break
        if any(k in low for k in ("hora de cierre", "close time")) and any(k in low for k in ("beneficio bruto", "beneficio neto", "beneficio/pérdida", "gross p/l", "net p/l", "profit/loss")):
            mode, pidx = "closed", -1
            for i, cn in enumerate(low):
                if cn in ("beneficio neto", "net p/l", "beneficio bruto", "gross p/l", "beneficio/pérdida", "profit/loss"): pidx = i; break
            continue
        if any(k in low for k in ("precio de apertura", "open price")) and any(k in low for k in ("producto", "product")):
            mode = "open"
            for i, cn in enumerate(low):
                if cn in ("símbolo", "simbolo", "ticker"): tidx = i
                elif cn in ("volumen", "volume"): vidx = i
                elif cn in ("precio de apertura", "open price"): oidx = i
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
        elif mode == "cash":
            ot, amt = gcol(r, yidx).lower(), to_num(gcol(r, aidx))
            tk = clean_tk(gcol(r, tidx))
            if amt is None: continue
            if ot in ("close trade", "cierre de operación", "cierre de operacion") and pidx < 0: cpnl += amt
            elif any(k in ot for k in ("dividend", "dividendo", "withholding", "retención", "retencion")) and tk:
                divs[tk] = divs.get(tk, 0.0) + amt
        elif mode == "open" and gcol(r, 0) in ("My Trades", "Investment Plan", "Mis operaciones", "Planes de inversión"):
            rtk = gcol(r, tidx)
            tk = clean_tk(rtk)
            if not tk or "CVR" in tk or "US931" in tk: continue
            vol, bp = to_num(gcol(r, vidx)), to_num(gcol(r, oidx))
            if vol is None or bp is None or vol <= 0: continue
            m = old_df[old_df["Ticker"].astype(str) == tk] if not old_df.empty else pd.DataFrame()
            if not m.empty: comp, sec, curr = str(next(iter(m["Company"]))), str(next(iter(m["Sector"]))), str(next(iter(m["Currency"])))
            else:
                comp, sec, curr = get_meta(tk)
                if rtk.endswith(".UK"): curr = "USD" if any(x in tk for x in ("ISLN", "EGLN", "SGLD", "COPX")) else "GBP"
            open_rows.append(dict(Ticker=tk, Company=comp, Sector=sec, Shares=vol, Buy=bp, Currency=curr))

    out, oset = [], set()
    if open_rows:
        for tk, g in pd.DataFrame(open_rows).groupby("Ticker", sort=False):
            oset.add(tk)
            sh = g["Shares"].sum()
            ab = (g["Shares"] * g["Buy"]).sum() / sh if sh > 0 else 0.0
            out.append({"Ticker": str(tk), "Company": str(next(iter(g["Company"]))), "Sector": str(next(iter(g["Sector"]))), "Shares": round(float(sh), 6), "Buy Price": round(float(ab), 4), "Current Price": round(float(ab), 4), "Currency": str(next(iter(g["Currency"]))), "Dividends EUR": round(max(divs.get(tk, 0.0), 0.0), 2)})
    cdivs = sum(max(v, 0.0) for k, v in divs.items() if k not in oset)
    return pd.DataFrame(out), ff, round(cpnl, 2), round(cdivs, 2)

def parse_krk_complete(up_f):
    kdf = pd.read_csv(up_f)
    kdf.columns = kdf.columns.str.lower().str.strip()
    if not {"asset", "amount", "type"}.issubset(set(kdf.columns)): return pd.DataFrame(), None
    kdf["amount"], kdf["fee"] = pd.to_numeric(kdf["amount"], errors="coerce").fillna(0.0), pd.to_numeric(kdf.get("fee", 0.0), errors="coerce").fillna(0.0)
    kdf["amountusd"] = pd.to_numeric(kdf.get("amountusd", 0.0), errors="coerce").fillna(0.0)
    kdf["type"] = kdf["type"].astype(str).str.lower().str.strip()
    m = {"XXBT": "BTC", "XBT": "BTC", "XETH": "ETH", "XXRP": "XRP", "XLTC": "LTC", "XXLM": "XLM", "XDOGE": "DOGE", "ZEUR": "EUR", "ZUSD": "USD", "ZGBP": "GBP"}
    kdf["norm"] = kdf["asset"].apply(lambda a: m.get(str(next(iter(str(a).strip().upper().split(".")))), str(next(iter(str(a).strip().upper().split("."))))))
    fiat = {"EUR", "USD", "GBP"}
    skip = {"transfer", "rollover", "margin", "settle", "hybridearnwithdrawal", "hybridearndeposit"}
    hold, cost, rew = {}, {}, {}
    ref = "refid" if "refid" in kdf.columns else ("txid" if "txid" in kdf.columns else None)

    for _, r in kdf.iterrows():
        a, t, amt, fee = r["norm"], r["type"], float(r["amount"]), float(r["fee"])
        if a in fiat or t in skip: continue
        net = amt - fee
        hold[a] = hold.get(a, 0.0) + net
        uv = abs(float(r["amountusd"]))
        if t == "deposit" and amt > 0 and uv > 0: cost[a] = cost.get(a, 0.0) + (uv / 1.168)
        if t in ("reward", "staking", "earn", "airdrop", "dividend") and net > 0: rew[a] = rew.get(a, 0.0) + (uv / 1.10 if uv > 0 else 0.0)

    if ref:
        for _, g in kdf.groupby(ref):
            cr = g[~g["norm"].isin(fiat) & g["type"].isin(("trade", "spend", "receive"))]
            fr = g[g["norm"].isin(fiat) & g["type"].isin(("trade", "spend", "receive"))]
            if not cr.empty and not fr.empty:
                ca, camt = str(next(iter(cr["norm"]))), float(cr["amount"].sum())
                fsp = abs(float(fr["amount"].sum())) + float(fr["fee"].sum())
                if camt > 0: cost[ca] = cost.get(ca, 0.0) + fsp

    rows = []
    for a, sh in hold.items():
        if sh <= 1e-7: continue
        tk = f"{a}-EUR"
        comp, _, _ = get_meta(tk)
        ap = (cost.get(a, 0.0) / sh) if (cost.get(a, 0.0) > 0 and sh > 0) else 0.0
        rows.append({"Ticker": tk, "Company": comp, "Sector": "Crypto", "Shares": round(sh, 8), "Buy Price": round(ap, 4), "Current Price": round(ap, 4), "Currency": "EUR", "Dividends EUR": round(rew.get(a, 0.0), 4)})

    er = kdf[kdf["norm"] == "EUR"]
    kcash = round(float((er["amount"] - er["fee"]).sum()), 2) if not er.empty else None
    return pd.DataFrame(rows), kcash

if st.button("⬅️ Meniu Principal"): st.switch_page("app.py")
if st.sidebar.button("🔄 Actualizează prețurile live"): st.cache_data.clear(); st.rerun()

st.title("📊 Sinteză Completă: XTB + Kraken")
tc = st.sidebar.selectbox("Monedă raportare", ("EUR", "USD", "GBP"))
stats = load_stats()
req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]

with st.container(border=True):
    st.subheader("📤 Încarcă rapoartele (Actualizează automat tot)")
    u1, u2 = st.columns(2)
    with u1:
        f_xtb = st.file_uploader("Raport XTB (.xlsx sau .csv):", type=["xlsx", "csv"], key="s_xtb")
        if f_xtb is not None and st.button("Actualizează Tot XTB", type="primary"):
            old_x = pd.read_csv(XTB_CSV).fillna("") if XTB_CSV.exists() else pd.DataFrame(columns=req)
            ndf, ff, cpnl, cdiv = parse_xtb_complete(f_xtb, old_x)
            if not ndf.empty: save_csv_permanent(ndf.reindex(columns=req), XTB_CSV)
            if ff is not None: stats["xtb_cash"] = ff
            stats["xtb_closed_pnl"] = cpnl
            if cdiv > 0: stats["xtb_closed_divs"] = cdiv
            ok = save_stats(stats)
            st.cache_data.clear()
