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
    s = str(val).strip().replace(" ", "").replace("€", "").replace("$", "").replace("+", "")
    if "," in s and "." in s: s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s: s = s.replace(",", ".")
    try: return float(s)
    except ValueError: return None

def load_stats():
    d = {"xtb_cash": 164.22, "xtb_closed_pnl": 186.81, "xtb_closed_divs": 23.99, "xtb_dep": 3151.0, "xtb_with": 376.0, "xtb_inv_eur": 2914.35, "xtb_base_mkt": 2856.71, "krk_cash": 0.0}
    if STATS_CSV.exists():
        try:
            for _, r in pd.read_csv(STATS_CSV).iterrows():
                if str(r.get("key", "")) in d: d[str(r.get("key"))] = float(r.get("val", 0.0))
        except Exception: pass
    return d

def save_stats(d): return save_csv_permanent(pd.DataFrame([{"key": k, "val": round(float(v), 4)} for k, v in d.items()]), STATS_CSV)

def parse_xtb_files(files_list, old_df):
    divs, open_rows, tot_cpnl, tot_ff, has_ff, tot_dep, tot_with = {}, [], 0.0, 0.0, False, 0.0, 0.0
    ov_mkt, ov_unr, has_ov = 0.0, 0.0, False
    for up_f in files_list:
        rows = []
        if up_f.name.lower().endswith(".xlsx"):
            xl = pd.ExcelFile(up_f)
            for sh in xl.sheet_names:
                for _, r in xl.parse(sh, header=None).fillna("").iterrows(): rows.append([str(x).strip() for x in r.tolist()])
        else:
            for r in csv.reader(io.StringIO(up_f.getvalue().decode("utf-8", errors="ignore"))): rows.append([str(x).strip() for x in r])

        mode, file_cpnl, pidx, tidx, vidx, cidx, oidx, aidx, yidx = "", 0.0, 10, 2, 5, 7, 8, 5, 0
        for r in rows:
            if not r or all(x == "" for x in r): continue
            low, c0 = [x.lower() for x in r], gcol(r, 0).lower()
            for i, c in enumerate(low):
                if any(k in c for k in ("free funds", "fondos libres", "saldo libre", "margen libre")):
                    for nxt in r[i + 1:]:
                        v = to_num(nxt)
                        if v is not None: tot_ff += v; has_ff = True; break
            if len(r) > 2 and "open position value" in low:
                v = to_num(gcol(r, 2))
                if v is not None: ov_mkt += v; has_ov = True
            if len(r) > 2 and "open position profit" in low:
                v = to_num(gcol(r, 2))
                if v is not None: ov_unr += v; has_ov = True

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
                    elif cn == "current price": cidx = i
                    elif cn == "open price": oidx = i
                continue

            if mode == "closed":
                if c0.startswith("profit/loss") or c0.startswith("total"):
                    v = to_num(gcol(r, pidx))
                    if v is not None and v != 0: file_cpnl = v
                    mode = ""; continue
                if c0 not in ("", "instrument"):
                    v = to_num(gcol(r, pidx))
                    if v is not None: file_cpnl += v
            elif mode == "cash":
                if c0 == "total":
                    v = to_num(gcol(r, aidx))
                    if v is not None: tot_ff += v; has_ff = True
                    mode = ""; continue
                ot, amt, tk = gcol(r, yidx).lower(), to_num(gcol(r, aidx)), clean_tk(gcol(r, tidx))
                if amt is None: continue
                if ot in ("deposit", "depósito", "deposito") and amt > 0: tot_dep += amt
                elif ot in ("withdrawal", "retirada", "retragere"): tot_with += abs(amt)
                elif tk and any(k in ot for k in ("dividend", "withholding")): divs[tk] = divs.get(tk, 0.0) + amt
            elif mode == "open":
                if c0 in ("account number", "total", "note"): mode = ""; continue
                if gcol(r, 0) in ("My Trades", "Investment Plan", "Investment Plans") and gcol(r, 3) != "":
                    rtk = gcol(r, tidx); tk = clean_tk(rtk)
                    if not tk or "CVR" in tk or "US931" in tk: continue
                    vol, bp = to_num(gcol(r, vidx)), to_num(gcol(r, oidx))
                    cp = to_num(gcol(r, cidx)) or bp
                    if vol is None or bp is None or vol <= 0: continue
                    m = old_df[old_df["Ticker"].astype(str) == tk] if not old_df.empty else pd.DataFrame()
                    if not m.empty: comp, sec, curr = str(next(iter(m["Company"]))), str(next(iter(m["Sector"]))), str(next(iter(m["Currency"])))
                    else:
                        comp, sec, curr = get_meta(tk)
                        if rtk.endswith(".UK"): curr = "USD" if any(x in tk for x in ("ISLN", "EGLN", "SGLD", "COPX")) else "GBP"
                    open_rows.append(dict(Ticker=tk, Company=comp, Sector=sec, Shares=vol, Buy=bp, Cur=cp, Currency=curr))
        tot_cpnl += file_cpnl

    out, oset = [], set()
    if open_rows:
        for tk, g in pd.DataFrame(open_rows).groupby("Ticker", sort=False):
            oset.add(tk); sh = g["Shares"].sum()
            ab = (g["Shares"] * g["Buy"]).sum() / sh if sh > 0 else 0.0
            ac = float(next(iter(g["Cur"])))
            out.append({"Ticker": str(tk), "Company": str(next(iter(g["Company"]))), "Sector": str(next(iter(g["Sector"]))), "Shares": round(float(sh), 6), "Buy Price": round(float(ab), 4), "Current Price": round(float(ac), 4), "Currency": str(next(iter(g["Currency"]))), "Dividends EUR": round(max(divs.get(tk, 0.0), 0.0), 2)})
    inv_eur = round(ov_mkt - ov_unr, 2) if has_ov else None
    return pd.DataFrame(out), (round(tot_ff, 2) if has_ff else None), round(tot_cpnl, 2), round(sum(max(v, 0.0) for k, v in divs.items() if k not in oset), 2), round(tot_dep, 2), round(tot_with, 2), inv_eur, (round(ov_mkt, 2) if has_ov else None)
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
    st.subheader("📤 Încarcă rapoartele (Poți selecta mai multe fișiere XTB odată)")
    u1, u2 = st.columns(2)
    with u1:
        f_xtb = st.file_uploader("Rapoarte XTB (.xlsx sau .csv):", type=["xlsx", "csv"], accept_multiple_files=True, key="s_xtb")
        if f_xtb and st.button("Actualizează Tot XTB", type="primary"):
            old_x = pd.read_csv(XTB_CSV).fillna("") if XTB_CSV.exists() else pd.DataFrame(columns=req)
            ndf, ff, cpnl, cdiv, dep, wth, inve, bmkt = parse_xtb_files(f_xtb, old_x)
            if not ndf.empty: save_csv_permanent(ndf.reindex(columns=req), XTB_CSV)
            if ff is not None: stats["xtb_cash"] = ff
            if cpnl != 0: stats["xtb_closed_pnl"] = cpnl
            if cdiv > 0: stats["xtb_closed_divs"] = cdiv
            if dep > 0: stats["xtb_dep"] = dep
            if wth > 0: stats["xtb_with"] = wth
            if inve is not None: stats["xtb_inv_eur"] = inve
            if bmkt is not None: stats["xtb_base_mkt"] = bmkt
            save_stats(stats); st.cache_data.clear(); st.rerun()
    with u2:
        f_krk = st.file_uploader("Rapoarte Kraken Libro mayor (.csv):", type="csv", accept_multiple_files=True, key="s_krk")
        if f_krk and st.button("Actualizează Tot Kraken", type="primary"):
            for fk in f_krk:
                kdf_n, kc = parse_krk_all(fk)
                if not kdf_n.empty: save_csv_permanent(kdf_n.reindex(columns=req), KRK_CSV)
                if kc is not None: stats["krk_cash"] = kc
            save_stats(stats); st.cache_data.clear(); st.rerun()

def read_port(csv_p):
    if not csv_p.exists(): return 0.0, 0.0, 0.0, 0.0, {"EUR": 1.08, "USD": 1.0, "GBP": 1.27}
    df = pd.read_csv(csv_p).fillna("")
    df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
    if df.empty: return 0.0, 0.0, 0.0, 0.0, {"EUR": 1.08, "USD": 1.0, "GBP": 1.27}
    prices, _, _, _, fx = fetch_data(df["Ticker"].astype(str).unique().tolist(), list(set(df["Currency"].astype(str).unique().tolist() + ["EUR", "USD", "GBP"])))
    for c in ("Shares", "Buy Price", "Current Price", "Dividends EUR"): df[c] = pd.to_numeric(df.get(c, 0.0), errors="coerce").fillna(0.0).astype(float)
    df["Live_P"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
    tr = fx.get(tc, 1.0); mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / tr
    inv = float((df["Shares"] * df["Buy Price"] * mult).sum())
    base_m = float((df["Shares"] * df["Current Price"] * mult).sum())
    live_m = float((df["Shares"] * df["Live_P"] * mult).sum())
    divs = float((df["Dividends EUR"] * (fx.get("EUR", 1.08) / tr)).sum())
    return inv, base_m, live_m, divs, fx

_, x_csv_base, x_csv_live, x_odivs, fx = read_port(XTB_CSV)
k_inv, _, k_mkt, k_earn, _ = read_port(KRK_CSV)
er = fx.get("EUR", 1.08) / fx.get(tc, 1.0)
ratio = (x_csv_live / x_csv_base) if x_csv_base > 0 else 1.0
x_inv = stats["xtb_inv_eur"] * er
x_mkt = (stats["xtb_base_mkt"] * er) * ratio
x_unr = x_mkt - x_inv
x_cash, x_cpnl, x_tdivs = stats["xtb_cash"] * er, stats["xtb_closed_pnl"] * er, x_odivs + stats["xtb_closed_divs"] * er
x_dep, x_with = stats["xtb_dep"] * er, stats["xtb_with"] * er
x_net_dep = x_dep - x_with
x_reinv = max(x_inv - x_net_dep, 0.0)
x_val_cont = x_mkt + x_cash
x_net_real = (x_val_cont + x_with) - x_dep
k_cash, k_prof = stats["krk_cash"] * er, (k_mkt - k_inv) + k_earn

st.subheader(f"📈 Portofoliu XTB — Reconciliere Live ({tc})")
cols_info = [
    ("1. Total<br>Depus", f"{x_dep:,.2f}", "Toate depunerile efectuate în contul XTB"),
    ("2. Total<br>Retras", f"-{x_with:,.2f}", "Bani scoși deja din contul XTB în bancă"),
    ("3. Capital<br>Net", f"{x_net_dep:,.2f}", "Depuneri minus retrageri (banii tăi rămași activi)"),
    ("4. Profit<br>Vânzări", f"{x_cpnl:+,.2f}", "Diferența netă dintre prețul de vânzare și cost (poziții închise)"),
    ("5. Dividende<br>& Dobânzi", f"+{x_tdivs:,.2f}", "Dividende nete încasate + dobânda la fondurile libere"),
    ("6. Profit<br>Reinvestit", f"+{x_reinv:,.2f}", "Câștig din vânzări și dividende folosit pentru a cumpăra acțiuni noi"),
    ("7. Valoare<br>Cont XTB", f"{x_val_cont:,.2f}", "Valoare Piață + Fonduri Libere (sincronizat exact cu XTB)"),
    ("8. Fonduri<br>Libere", f"{x_cash:,.2f}", "Suma nealocată (Cash lichid disponibil în contul XTB)"),
    ("9. Total<br>Investit", f"{x_inv:,.2f}", "Costul exact în EUR al acțiunilor deținute (Capital Net + Reinvestit)"),
    ("10. Profit", f"{x_unr:+,.2f}", "Profitul sau pierderea pe pozițiile deschise (Valoare Piață minus Total Investit)"),
    ("11. Valoare<br>Piață", f"{x_mkt:,.2f}", "Valoarea actuală pe bursă a acțiunilor și ETF-urilor din XTB")
]
ths = "".join([f"<th title='{tip}' style='border:1px solid #333;padding:6px 3px;text-align:center;font-weight:bold;background:#1e222d;color:#fff;font-size:12px;line-height:1.25;cursor:help;'>{lbl}</th>" for lbl, _, tip in cols_info])
tds = "".join([f"<td title='{tip}' style='border:1px solid #333;padding:8px 3px;text-align:center;font-weight:bold;font-size:13px;color:{('#00e676' if str(val).startswith('+') else ('#ff5252' if str(val).startswith('-') else '#e0e0e0'))};'>{val}</td>" for _, val, tip in cols_info])
st.markdown(f"<table style='width:100%;border-collapse:collapse;table-layout:fixed;margin-bottom:10px;'><thead><tr>{ths}</tr></thead><tbody><tr>{tds}</tr></tbody></table>", unsafe_allow_html=True)

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
g3.metric("Valoare Totală Conturi", f"{(x_val_cont + k_mkt + k_cash):,.2f} {tc}")
g4.metric("Profit Net Cumulat", f"{(x_net_real + k_prof):+,.2f} {tc}")
