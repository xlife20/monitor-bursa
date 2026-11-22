import streamlit as st
import pandas as pd
import numpy as np
import csv, io
from pathlib import Path
from utils import save_csv_permanent, get_meta, fetch_data

st.set_page_config(page_title="XTB + Kraken", layout="wide")
BASE = Path(__file__).resolve().parent.parent
XTB_CSV, KRK_CSV, STATS_CSV = BASE / "portfolio.csv", BASE / "portfolio_kraken.csv", BASE / "summary_stats.csv"

def gcol(r, i): return str(list(r)[i]).strip() if len(r) > i else ""
def clean_tk(t): return str(t).replace(".US", "").replace(".UK", ".L").replace(".ES", ".MC").replace(".IT", ".MI").strip()

def to_num(val):
    s = str(val).strip().replace(" ", "").replace("€", "").replace("$", "")
    if "," in s and "." in s: s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s: s = s.replace(",", ".")
    try: return float(s)
    except ValueError: return None

def load_stats():
    d = {"xtb_cash": 164.59, "xtb_closed_pnl": 186.81, "xtb_closed_divs": 18.24, "krk_cash": 0.0}
    if STATS_CSV.exists():
        try:
            for _, r in pd.read_csv(STATS_CSV).iterrows():
                if str(r.get("key", "")) in d: d[str(r.get("key"))] = float(r.get("val", 0.0))
        except Exception: pass
    return d

def save_stats(d): return save_csv_permanent(pd.DataFrame([{"key": k, "val": round(float(v), 4)} for k, v in d.items()]), STATS_CSV)

def parse_xtb_all(up_f, old_df):
    rows = []
    if up_f.name.lower().endswith(".xlsx"):
        xl = pd.ExcelFile(up_f)
        for sh in xl.sheet_names:
            for _, r in xl.parse(sh, header=None).fillna("").iterrows(): rows.append([str(x).strip() for x in r.tolist()])
    else:
        for r in csv.reader(io.StringIO(up_f.getvalue().decode("utf-8", errors="ignore"))): rows.append([str(x).strip() for x in r])

    divs, open_rows, mode, cpnl, ff = {}, [], "", 0.0, None
    pidx, tidx, vidx, oidx, aidx, yidx = 10, 2, 5, 8, 5, 0
    for r in rows:
        if not r or all(x == "" for x in r): continue
        low = [x.lower() for x in r]
        c0 = gcol(r, 0).lower()

        if "instrument" in low and "profit/loss" in low and "close time (utc)" in low:
            mode = "closed"
            for i, cn in enumerate(low):
                if cn == "profit/loss": pidx = i; break
            continue
        if "type" in low and "amount" in low and "comment" in low:
            mode = "cash"
            for i, cn in enumerate(low):
                if cn == "type": yidx = i
                elif cn == "ticker": tidx = i
                elif cn == "amount": aidx = i
            continue
        if "product" in low and "open price" in low and "volume" in low:
            mode = "open"
            for i, cn in enumerate(low):
                if cn == "ticker": tidx = i
                elif cn == "volume": vidx = i
                elif cn == "open price": oidx = i
            continue

        if mode == "closed":
            if c0.startswith("profit/loss") or c0.startswith("total"):
                v = to_num(gcol(r, pidx))
                if v is not None and v != 0: cpnl = v
                mode = ""; continue
            if c0 not in ("", "instrument"):
                v = to_num(gcol(r, pidx))
                if v is not None: cpnl += v

        elif mode == "cash":
            if c0 == "total":
                v = to_num(gcol(r, aidx))
                if v is not None: ff = v
                mode = ""; continue
            ot, amt, tk = gcol(r, yidx).lower(), to_num(gcol(r, aidx)), clean_tk(gcol(r, tidx))
            if amt is not None and tk and any(k in ot for k in ("dividend", "withholding")):
                divs[tk] = divs.get(tk, 0.0) + amt

        elif mode == "open":
            if c0 in ("account number", "total", "note"): mode = ""; continue
            if gcol(r, 0) in ("My Trades", "Investment Plan", "Investment Plans") and gcol(r, 3) != "":
                rtk = gcol(r, tidx); tk = clean_tk(rtk)
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
            oset.add(tk); sh = g["Shares"].sum(); ab = (g["Shares"] * g["Buy"]).sum() / sh if sh > 0 else 0.0
            out.append({"Ticker": str(tk), "Company": str(next(iter(g["Company"]))), "Sector": str(next(iter(g["Sector"]))), "Shares": round(float(sh), 6), "Buy Price": round(float(ab), 4), "Current Price": round(float(ab), 4), "Currency": str(next(iter(g["Currency"]))), "Dividends EUR": round(max(divs.get(tk, 0.0), 0.0), 2)})
    return pd.DataFrame(out), ff, round(cpnl, 2), round(sum(max(v, 0.0) for k, v in divs.items() if k not in oset), 2)
def parse_krk_all(up_f):
    kdf = pd.read_csv(up_f); kdf.columns = kdf.columns.str.lower().str.strip()
    if not {"asset", "amount", "type"}.issubset(set(kdf.columns)): return pd.DataFrame(), None
    kdf["amount"], kdf["fee"] = pd.to_numeric(kdf["amount"], errors="coerce").fillna(0.0), pd.to_numeric(kdf.get("fee", 0.0), errors="coerce").fillna(0.0)
    kdf["amountusd"], kdf["type"] = pd.to_numeric(kdf.get("amountusd", 0.0), errors="coerce").fillna(0.0), kdf["type"].astype(str).str.lower().str.strip()
    m = {"XXBT": "BTC", "XBT": "BTC", "XETH": "ETH", "XXRP": "XRP", "XLTC": "LTC", "XXLM": "XLM", "XDOGE": "DOGE", "ZEUR": "EUR", "ZUSD": "USD", "ZGBP": "GBP"}
    kdf["norm"] = kdf["asset"].apply(lambda a: m.get(str(next(iter(str(a).strip().upper().split(".")))), str(next(iter(str(a).strip().upper().split("."))))))
    hold, cost, rew = {}, {}, {}
    ref = "refid" if "refid" in kdf.columns else ("txid" if "txid" in kdf.columns else None)
    for _, r in kdf.iterrows():
        a, t, amt, fee, uv = r["norm"], r["type"], float(r["amount"]), float(r["fee"]), abs(float(r["amountusd"]))
        if a in {"EUR", "USD", "GBP"} or t in {"transfer", "rollover", "margin", "settle", "hybridearnwithdrawal", "hybridearndeposit"}: continue
        net = amt - fee; hold[a] = hold.get(a, 0.0) + net
        if t == "deposit" and amt > 0 and uv > 0: cost[a] = cost.get(a, 0.0) + (uv / 1.168)
        if t in ("reward", "staking", "earn", "airdrop", "dividend") and net > 0: rew[a] = rew.get(a, 0.0) + (uv / 1.10 if uv > 0 else 0.0)
    if ref:
        for _, g in kdf.groupby(ref):
            cr, fr = g[~g["norm"].isin({"EUR", "USD", "GBP"}) & g["type"].isin(("trade", "spend", "receive"))], g[g["norm"].isin({"EUR", "USD", "GBP"}) & g["type"].isin(("trade", "spend", "receive"))]
            if not cr.empty and not fr.empty and float(cr["amount"].sum()) > 0:
                ca = str(next(iter(cr["norm"]))); cost[ca] = cost.get(ca, 0.0) + abs(float(fr["amount"].sum())) + float(fr["fee"].sum())
    rows = [{"Ticker": f"{a}-EUR", "Company": get_meta(f"{a}-EUR"), "Sector": "Crypto", "Shares": round(sh, 8), "Buy Price": round((cost.get(a, 0.0) / sh) if cost.get(a, 0.0) > 0 else 0.0, 4), "Current Price": round((cost.get(a, 0.0) / sh) if cost.get(a, 0.0) > 0 else 0.0, 4), "Currency": "EUR", "Dividends EUR": round(rew.get(a, 0.0), 4)} for a, sh in hold.items() if sh > 1e-7]
    er = kdf[kdf["norm"] == "EUR"]
    return pd.DataFrame(rows), (round(float((er["amount"] - er["fee"]).sum()), 2) if not er.empty else None)

if st.button("⬅️ Meniu Principal"): st.switch_page("app.py")
if st.sidebar.button("🔄 Actualizează prețurile live"): st.cache_data.clear(); st.rerun()
st.title("📊 Sinteză Completă: XTB + Kraken")
tc, stats = st.sidebar.selectbox("Monedă raportare", ("EUR", "USD", "GBP")), load_stats()
req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]

with st.container(border=True):
    st.subheader("📤 Încarcă rapoartele (Actualizează automat tot)")
    u1, u2 = st.columns(2)
    with u1:
        f_xtb = st.file_uploader("Raport XTB (.xlsx sau .csv):", type=["xlsx", "csv"], key="s_xtb")
        if f_xtb is not None and st.button("Actualizează Tot XTB", type="primary"):
            old_x = pd.read_csv(XTB_CSV).fillna("") if XTB_CSV.exists() else pd.DataFrame(columns=req)
            ndf, ff, cpnl, cdiv = parse_xtb_all(f_xtb, old_x)
            if not ndf.empty: save_csv_permanent(ndf.reindex(columns=req), XTB_CSV)
            if ff is not None: stats["xtb_cash"] = ff
            if cpnl != 0: stats["xtb_closed_pnl"] = cpnl
            if cdiv > 0: stats["xtb_closed_divs"] = cdiv
            save_stats(stats); st.cache_data.clear(); st.rerun()
    with u2:
        f_krk = st.file_uploader("Raport Kraken Libro mayor (.csv):", type="csv", key="s_krk")
        if f_krk is not None and st.button("Actualizează Tot Kraken", type="primary"):
            kdf_n, kc = parse_krk_all(f_krk)
            if not kdf_n.empty: save_csv_permanent(kdf_n.reindex(columns=req), KRK_CSV)
            if kc is not None: stats["krk_cash"] = kc
            save_stats(stats); st.cache_data.clear(); st.rerun()

def read_port(csv_p):
    if not csv_p.exists(): return 0.0, 0.0, 0.0, {"EUR": 1.08, "USD": 1.0, "GBP": 1.27}
    df = pd.read_csv(csv_p).fillna("")
    df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
    if df.empty: return 0.0, 0.0, 0.0, {"EUR": 1.08, "USD": 1.0, "GBP": 1.27}
    prices, _, _, _, fx = fetch_data(df["Ticker"].astype(str).unique().tolist(), list(set(df["Currency"].astype(str).unique().tolist() + ["EUR", "USD", "GBP"])))
    for c in ("Shares", "Buy Price", "Current Price", "Dividends EUR"): df[c] = pd.to_numeric(df.get(c, 0.0), errors="coerce").fillna(0.0).astype(float)
    df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
    tr = fx.get(tc, 1.0); mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / tr
    return float((df["Shares"] * df["Buy Price"] * mult).sum()), float((df["Shares"] * df["Current Price"] * mult).sum()), float((df["Dividends EUR"] * (fx.get("EUR", 1.08) / tr)).sum()), fx

x_inv, x_mkt, x_odivs, fx = read_port(XTB_CSV); k_inv, k_mkt, k_earn, _ = read_port(KRK_CSV)
er = fx.get("EUR", 1.08) / fx.get(tc, 1.0)
x_cash, x_cpnl, x_tdivs, x_unr = stats["xtb_cash"] * er, stats["xtb_closed_pnl"] * er, x_odivs + stats["xtb_closed_divs"] * er, x_mkt - x_inv
x_net, k_cash, k_prof = x_unr + x_cpnl + x_tdivs, stats["krk_cash"] * er, (k_mkt - k_inv) + k_earn

st.subheader("📈 Portofoliu XTB")
x1, x2, x3, x4, x5 = st.columns(5)
x1.metric("Suma investită (Activă)", f"{x_inv:,.2f} {tc}", f"Piață: {x_mkt:,.2f} {tc}")
x2.metric("Suma nealocată (Cash)", f"{x_cash:,.2f} {tc}")
x3.metric("Profit din vânzări acțiuni", f"{x_cpnl:+,.2f} {tc}", "Poziții închise (net)")
x4.metric("Profit dividende", f"+{x_tdivs:,.2f} {tc}", "Net încasate")
x5.metric("Profit / Pierdere Total XTB", f"{x_net:+,.2f} {tc}", f"Deschise: {x_unr:+,.2f} {tc}")

st.divider(); st.subheader("🪙 Portofoliu Kraken")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Suma investită", f"{k_inv:,.2f} {tc}", f"Piață: {k_mkt:,.2f} {tc}")
k2.metric("Suma nealocată (Cash)", f"{k_cash:,.2f} {tc}")
k3.metric("Câștig din Earn", f"+{k_earn:,.4f} {tc}")
k4.metric("Profit actualizat Kraken", f"{k_prof:+,.2f} {tc}", f"{((k_prof / k_inv * 100) if k_inv > 0 else 0.0):+.2f}%")

st.divider(); st.subheader("🌐 Total General (XTB + Kraken)")
g1, g2, g3, g4 = st.columns(4)
g1.metric("Total Investit", f"{(x_inv + k_inv):,.2f} {tc}")
g2.metric("Total Cash Nealocat", f"{(x_cash + k_cash):,.2f} {tc}")
g3.metric("Valoare Totală Conturi", f"{(x_mkt + x_cash + k_mkt + k_cash):,.2f} {tc}")
g4.metric("Profit Net Cumulat", f"{(x_net + k_prof):+,.2f} {tc}")
