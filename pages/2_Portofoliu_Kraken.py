import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import save_csv_permanent, get_meta, fetch_data, c_pnl, c_rsi, f_price, f_shares, f_num2, f_rsi, f_sma, f_pct, clean_table, quick_del

st.set_page_config(page_title="Portofoliu Kraken", layout="wide")
CSV_PATH = Path(__file__).resolve().parent.parent / "portfolio_kraken.csv"

def norm_a(a):
    s = str(next(iter(str(a).strip().upper().split("."))))
    if s.endswith(("21", "28")) and len(s) > 4: s = s[:-2]
    m = {"XXBT": "BTC", "XBT": "BTC", "XETH": "ETH", "XXRP": "XRP", "XLTC": "LTC", "XXLM": "XLM", "XDOGE": "DOGE", "ZEUR": "EUR", "ZUSD": "USD", "ZGBP": "GBP"}
    return m.get(s, s)

def parse_kraken(up_f):
    kdf = pd.read_csv(up_f)
    kdf.columns = kdf.columns.str.lower().str.strip()
    cols = set(kdf.columns)
    fiat = {"EUR", "USD", "GBP"}
    skip_types = {"transfer", "rollover", "margin", "settle", "hybridearnwithdrawal", "hybridearndeposit"}

    if {"asset", "amount", "type"}.issubset(cols):
        kdf["amount"] = pd.to_numeric(kdf["amount"], errors="coerce").fillna(0.0)
        kdf["fee"] = pd.to_numeric(kdf.get("fee", 0.0), errors="coerce").fillna(0.0)
        kdf["amountusd"] = pd.to_numeric(kdf.get("amountusd", 0.0), errors="coerce").fillna(0.0)
        kdf["type"] = kdf["type"].astype(str).str.lower().str.strip()
        kdf["norm"] = kdf["asset"].apply(norm_a)
        hold, cost, rew_eur = {}, {}, {}
        ref = "refid" if "refid" in cols else ("txid" if "txid" in cols else None)

        for _, r in kdf.iterrows():
            a, t, amt, fee = r["norm"], r["type"], float(r["amount"]), float(r["fee"])
            if a in fiat or t in skip_types: continue
            net = amt - fee
            hold[a] = hold.get(a, 0.0) + net
            usd_v = abs(float(r["amountusd"]))
            if t == "deposit" and amt > 0 and usd_v > 0:
                cost[a] = cost.get(a, 0.0) + (usd_v / 1.168)
            if t in ("reward", "staking", "earn", "airdrop", "dividend") and net > 0:
                rew_eur[a] = rew_eur.get(a, 0.0) + (usd_v / 1.10 if usd_v > 0 else 0.0)

        if ref:
            for _, g in kdf.groupby(ref):
                cr = g[~g["norm"].isin(fiat) & g["type"].isin(("trade", "spend", "receive"))]
                fr = g[g["norm"].isin(fiat) & g["type"].isin(("trade", "spend", "receive"))]
                if not cr.empty and not fr.empty:
                    ca = str(next(iter(cr["norm"])))
                    camt = float(cr["amount"].sum())
                    fsp = abs(float(fr["amount"].sum())) + float(fr["fee"].sum())
                    if camt > 0: cost[ca] = cost.get(ca, 0.0) + fsp

        rows = []
        for a, sh in hold.items():
            if sh <= 1e-7: continue
            tk = f"{a}-EUR"
            comp, _, _ = get_meta(tk)
            tc = cost.get(a, 0.0)
            ap = (tc / sh) if (tc > 0 and sh > 0) else 0.0
            rows.append({"Ticker": tk, "Company": comp, "Sector": "Crypto", "Shares": round(sh, 8), "Buy Price": round(ap, 4), "Current Price": round(ap, 4), "Currency": "EUR", "Dividends EUR": round(rew_eur.get(a, 0.0), 4)})
        return pd.DataFrame(rows)
    return pd.DataFrame()

if "imp_krk" not in st.session_state: st.session_state.imp_krk = False
n1, n2, _ = st.columns((1.2, 1.3, 5.5))
if n1.button("⬅️ Meniu Principal", use_container_width=True): st.switch_page("app.py")
if n2.button("📥 Importă Kraken", use_container_width=True): st.session_state.imp_krk = not st.session_state.imp_krk
if st.sidebar.button("🔄 Actualizează prețurile live"): st.cache_data.clear(); st.rerun()

req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]
df = pd.read_csv(CSV_PATH).fillna("") if CSV_PATH.exists() else pd.DataFrame(columns=req)
for c in req:
    if c not in df.columns: df[c] = 0.0 if c in ("Shares", "Buy Price", "Current Price", "Dividends EUR") else ""

if st.session_state.imp_krk:
    with st.container(border=True):
        up_f = st.file_uploader("Încarcă raportul CSV Kraken (Libro mayor / Ledgers):", type="csv", key="up_krk")
        if up_f is not None and st.button("Procesează și Salvează Permanent", type="primary"):
            ndf = parse_kraken(up_f)
            if not ndf.empty:
                ok = save_csv_permanent(ndf.reindex(columns=req), CSV_PATH)
                st.session_state.imp_krk = False
                st.cache_data.clear()
                st.success("Salvat permanent!" if ok else "Salvat local!")
                st.rerun()
            else: st.error("Fișierul nu conține date valide Kraken.")

st.title("🪙 Portofoliu Kraken")
df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
tks = df["Ticker"].astype(str).unique().tolist()
acurr = sorted([x for x in df["Currency"].astype(str).unique().tolist() if x.strip()]) or ["EUR", "USD"]
prices, _, rsim, smam, fx = fetch_data(tks, list(set(acurr + ["EUR", "USD", "GBP"])))

for c in ("Shares", "Buy Price", "Current Price", "Dividends EUR"):
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)

df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsim), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(smam), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current Price"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)

tc = st.sidebar.selectbox("Monedă raportare", ("EUR", "USD", "GBP"))
sb = st.sidebar.selectbox("Ordonează după", ("Valoare piață", "Profit Total", "Earn", "Randament %", "RSI", "vs SMA 200 %", "Tiker"))
tr = fx.get(tc, 1.0)
er = fx.get("EUR", 1.08) / tr
mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / tr

df["Inv"] = df["Shares"] * df["Buy Price"] * mult
df["Mkt"] = df["Shares"] * df["Current Price"] * mult
df["Earn"] = df["Dividends EUR"] * er
df["PnL"] = (df["Mkt"] - df["Inv"]) + df["Earn"]
df["Ret"] = np.where(df["Inv"] != 0, df["PnL"] / df["Inv"] * 100, 0.0).astype(float)
tmkt = df["Mkt"].sum()
df["Wgt"] = np.where(tmkt != 0, df["Mkt"] / tmkt * 100, 0.0).astype(float)

smap = {"Valoare piață": ("Mkt", False), "Profit Total": ("PnL", False), "Earn": ("Earn", False), "Randament %": ("Ret", False), "RSI": ("RSI", True), "vs SMA 200 %": ("SMA_Pct", True), "Tiker": ("Ticker", True)}
cs, ascs = smap.get(sb)
v = df.sort_values(by=cs, ascending=ascs, na_position="last")

invs, mkts, earns = float(v["Inv"].sum()), float(v["Mkt"].sum()), float(v["Earn"].sum())
gp, gl = float(v[v["PnL"] > 0]["PnL"].sum()), float(v[v["PnL"] < 0]["PnL"].sum())

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Poziții", f"{len(v)}")
c2.metric("Capital investit", f"{invs:,.2f} {tc}")
c3.metric("Valoare piață", f"{mkts:,.2f} {tc}")
c4.metric("Câștig Earn", f"{earns:,.4f} {tc}")
c5.metric("Profit Total (Poz.)", f"+{gp:,.2f} {tc}", f"{len(v[v['PnL'] > 0])} pe plus", delta_color="normal")
c6.metric("Pierdere Totală (Neg.)", f"{gl:,.2f} {tc}", f"-{len(v[v['PnL'] < 0])} pe minus", delta_color="normal")

f_earn = lambda x: "" if (pd.isna(x) or x == "" or float(x) <= 0) else f"{float(x):,.4f}"

if not v.empty:
    cols = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "RSI", "SMA_Pct", "Current Price", "Currency", "Inv", "Mkt", "Earn", "PnL", "Ret", "Wgt"]
    disp = v.reindex(columns=cols).copy()
    disp.columns = ["Tiker", "Companie", "Sector", "Acțiuni", "Preț mediu", "RSI (14)", "vs SMA 200 %", "Preț curent", "Monedă", "Valoare investită", "Valoare piață", "Earn", "Profit / Pierdere", "Randament %", "Pondere %"]
    fmt = {"Acțiuni": f_shares, "Preț mediu": f_price, "RSI (14)": f_rsi, "vs SMA 200 %": f_sma, "Preț curent": f_price, "Valoare investită": f_num2, "Valoare piață": f_num2, "Earn": f_earn, "Profit / Pierdere": f_num2, "Randament %": f_pct, "Pondere %": f_pct}
    styler = clean_table(disp, fmt).style.map(c_pnl, subset=["Profit / Pierdere", "Randament %", "vs SMA 200 %"]).map(c_rsi, subset=["RSI (14)"])
    st.dataframe(styler, use_container_width=True, hide_index=True, height=400, column_config={"Tiker": st.column_config.TextColumn("Tiker", pinned=True)})
    quick_del(df, req, CSV_PATH, "kraken")
    l1, r1 = st.columns(2)
    with l1:
        st.subheader(f"Profit / Pierdere Total ({tc})")
        st.bar_chart(v.set_index("Ticker")[["PnL"]].assign(Color=np.where(v["PnL"] >= 0, "#00e676", "#ff5252")), y="PnL", color="Color")
    with r1:
        st.subheader(f"Valoare de piață ({tc})")
        st.bar_chart(v.set_index("Ticker")["Mkt"], color="#29b6f6")

st.subheader("Editare poziții (portfolio_kraken.csv)")
ed = st.data_editor(v.reindex(columns=req), num_rows="dynamic", use_container_width=True, key="ed_kraken")
if st.button("Salvează modificările în portfolio_kraken.csv"):
    if not ed.empty:
        ok = save_csv_permanent(ed, CSV_PATH)
        st.cache_data.clear()
        st.success("Salvat permanent pe GitHub!" if ok else "Salvat local!")
