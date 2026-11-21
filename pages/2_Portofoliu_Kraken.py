import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import save_csv_permanent, get_meta, fetch_data, c_pnl, c_rsi, f_price, f_shares, f_num2, f_rsi, f_sma, f_pct, clean_table, quick_del

st.set_page_config(page_title="Portofoliu Kraken", layout="wide")
CSV_PATH = Path(__file__).resolve().parent.parent / "portfolio_kraken.csv"

def norm_asset(a):
    s = str(a).strip().upper()
    s = s.split(".")[0]
    for suf in ("21", "28"):
        if s.endswith(suf) and len(s) > 4:
            s = s[:-2]
    if s in ("XXBT", "XBT"): return "BTC"
    if s == "XETH": return "ETH"
    if s == "XXRP": return "XRP"
    if s == "XLTC": return "LTC"
    if s == "XXLM": return "XLM"
    if s == "XDOGE": return "DOGE"
    if s in ("ZEUR", "EUR"): return "EUR"
    if s in ("ZUSD", "USD"): return "USD"
    if s in ("ZGBP", "GBP"): return "GBP"
    return s

def parse_kraken_file(uploaded_file):
    kdf = pd.read_csv(uploaded_file)
    cols = set(kdf.columns.str.lower())

    # 1. Format LEDGERS (include Spot + Earn + Recompense Staking/Earn)
    if {"asset", "amount", "type"}.issubset(cols):
        kdf.columns = kdf.columns.str.lower()
        kdf["amount"] = pd.to_numeric(kdf["amount"], errors="coerce").fillna(0.0)
        kdf["fee"] = pd.to_numeric(kdf.get("fee", 0.0), errors="coerce").fillna(0.0)
        kdf["type"] = kdf["type"].astype(str).str.lower().str.strip()
        kdf["norm"] = kdf["asset"].apply(norm_asset)

        fiat = {"EUR", "USD", "GBP"}
        holdings = {}
        cost_eur = {}
        earn_rewards = {}

        # Grupam pe txid / refid pentru a lega plata in EUR/USD de cantitatea de crypto cumparata
        ref_col = "refid" if "refid" in kdf.columns else ("txid" if "txid" in kdf.columns else None)

        for _, r in kdf.iterrows():
            a = r["norm"]
            t = r["type"]
            amt = float(r["amount"])
            fee = float(r["fee"])
            if a in fiat:
                continue
            if t in ("transfer", "rollover", "margin", "settle"):
                continue
            net = amt - fee
            holdings[a] = holdings.get(a, 0.0) + net
            if t in ("reward", "staking", "earn", "airdrop", "dividend"):
                earn_rewards[a] = earn_rewards.get(a, 0.0) + max(net, 0.0)

        # Estimam costul de achizitie din tranzactiile trade / spend
        if ref_col:
            for _, grp in kdf.groupby(ref_col):
                crypto_rows = grp[~grp["norm"].isin(fiat) & grp["type"].isin(["trade", "spend", "receive"])]
                fiat_rows = grp[grp["norm"].isin(fiat) & grp["type"].isin(["trade", "spend", "receive"])]
                if not crypto_rows.empty and not fiat_rows.empty:
                    c_asset = crypto_rows["norm"].iloc[0]
                    c_amt = float(crypto_rows["amount"].sum())
                    f_spent = abs(float(fiat_rows["amount"].sum())) + float(fiat_rows["fee"].sum())
                    if c_amt > 0:
                        cost_eur[c_asset] = cost_eur.get(c_asset, 0.0) + f_spent

        rows = []
        for a, sh in holdings.items():
            if sh <= 1e-7:
                continue
            tk = f"{a}-EUR"
            comp, _, _ = get_meta(tk)
            tot_c = cost_eur.get(a, 0.0)
            avg_p = (tot_c / sh) if (tot_c > 0 and sh > 0) else 0.0
            rew_coins = earn_rewards.get(a, 0.0)
            rows.append({
                "Ticker": tk,
                "Company": f"{comp} (incl. Earn: {rew_coins:.6f})" if rew_coins > 0 else comp,
                "Sector": "Crypto",
                "Shares": round(sh, 8),
                "Buy Price": round(avg_p, 4),
                "Current Price": round(avg_p, 4),
                "Currency": "EUR",
                "Dividends EUR": 0.0
            })
        return pd.DataFrame(rows)

    # 2. Format TRADES clasic
    if {"pair", "vol", "cost"}.issubset(cols):
        kdf.columns = kdf.columns.str.lower()
        kdf["vol"] = pd.to_numeric(kdf["vol"], errors="coerce").fillna(0.0)
        kdf["cost"] = pd.to_numeric(kdf["cost"], errors="coerce").fillna(0.0)
        kdf["fee"] = pd.to_numeric(kdf.get("fee", 0.0), errors="coerce").fillna(0.0)
        kdf["type"] = kdf.get("type", "buy").astype(str).str.lower()

        rows = []
        for pair, grp in kdf.groupby("pair"):
            clean_pair = str(pair).replace("/", "-").replace("XXBT", "BTC").replace("XBT", "BTC").upper()
            curr = clean_pair.split("-")[-1] if "-" in clean_pair else "EUR"
            buys = grp[grp["type"] == "buy"]
            sells = grp[grp["type"] == "sell"]
            net_vol = buys["vol"].sum() - sells["vol"].sum()
            if net_vol <= 1e-7:
                continue
            total_buy_cost = (buys["cost"] + buys["fee"]).sum()
            total_buy_vol = buys["vol"].sum()
            avg_price = (total_buy_cost / total_buy_vol) if total_buy_vol > 0 else 0.0
            comp, _, _ = get_meta(clean_pair)
            rows.append({
                "Ticker": clean_pair, "Company": comp, "Sector": "Crypto",
                "Shares": round(net_vol, 8), "Buy Price": round(avg_price, 4), "Current Price": round(avg_price, 4),
                "Currency": curr, "Dividends EUR": 0.0
            })
        return pd.DataFrame(rows)

    return pd.DataFrame()

if "imp_krk" not in st.session_state:
    st.session_state.imp_krk = False

n1, n2, _ = st.columns((1.2, 1.3, 5.5))
if n1.button("⬅️ Meniu Principal", use_container_width=True):
    st.switch_page("app.py")
if n2.button("📥 Importă Kraken", use_container_width=True):
    st.session_state.imp_krk = not st.session_state.imp_krk

if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.cache_data.clear()
    st.rerun()

req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]
df = pd.read_csv(CSV_PATH).fillna("") if CSV_PATH.exists() else pd.DataFrame(columns=req)
for c in req:
    if c not in df.columns:
        df[c] = 0.0 if c in ("Shares", "Buy Price", "Current Price", "Dividends EUR") else ""

if st.session_state.imp_krk:
    with st.container(border=True):
        up_f = st.file_uploader("Încarcă raportul CSV din Kraken (Ledgers pentru Spot + Earn, sau Trades):", type="csv", key="up_krk")
        if up_f is not None and st.button("Procesează și Salvează Permanent", type="primary"):
            ndf = parse_kraken_file(up_f)
            if not ndf.empty:
                ok = save_csv_permanent(ndf.reindex(columns=req), CSV_PATH)
                st.session_state.imp_krk = False
                st.cache_data.clear()
                st.success("Importat (inclusiv Earn) și salvat permanent!" if ok else "Importat local!")
                st.rerun()
            else:
                st.error("Fișierul nu conține date valide Kraken (Ledgers sau Trades).")

st.title("🪙 Portofoliu Kraken")
df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
tks = df["Ticker"].astype(str).unique().tolist()
acurr = sorted([x for x in df["Currency"].astype(str).unique().tolist() if x.strip()]) or ["EUR", "USD"]
prices, _, rsim, smam, fx = fetch_data(tks, list(set(acurr + ["EUR", "USD", "GBP"])))

for c in ("Shares", "Buy Price", "Current Price"):
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)

df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsim), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(smam), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current Price"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)

tc = st.sidebar.selectbox("Monedă raportare", ("EUR", "USD", "GBP"))
sb = st.sidebar.selectbox("Ordonează după", ("Valoare piață", "Profit Total", "Randament %", "RSI", "vs SMA 200 %", "Tiker"))

tr = fx.get(tc, 1.0)
mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / tr

df["Inv"] = df["Shares"] * df["Buy Price"] * mult
df["Mkt"] = df["Shares"] * df["Current Price"] * mult
df["PnL"] = df["Mkt"] - df["Inv"]
df["Ret"] = np.where(df["Inv"] != 0, df["PnL"] / df["Inv"] * 100, 0.0).astype(float)

tmkt = df["Mkt"].sum()
df["Wgt"] = np.where(tmkt != 0, df["Mkt"] / tmkt * 100, 0.0).astype(float)

smap = {"Valoare piață": ("Mkt", False), "Profit Total": ("PnL", False), "Randament %": ("Ret", False), "RSI": ("RSI", True), "vs SMA 200 %": ("SMA_Pct", True), "Tiker": ("Ticker", True)}
cs, ascs = smap.get(sb)
v = df.sort_values(by=cs, ascending=ascs, na_position="last")

invs, mkts = float(v["Inv"].sum()), float(v["Mkt"].sum())
gp = float(v[v["PnL"] > 0]["PnL"].sum())
gl = float(v[v["PnL"] < 0]["PnL"].sum())

c1, c2, c3, c5, c6 = st.columns(5)
c1.metric("Poziții", f"{len(v)}")
c2.metric("Capital investit", f"{invs:,.2f} {tc}")
c3.metric("Valoare piață", f"{mkts:,.2f} {tc}")
c5.metric("Profit Total (Poz.)", f"+{gp:,.2f} {tc}", f"{len(v[v['PnL'] > 0])} pe plus", delta_color="normal")
c6.metric("Pierdere Totală (Neg.)", f"{gl:,.2f} {tc}", f"-{len(v[v['PnL'] < 0])} pe minus", delta_color="normal")

if not v.empty:
    cols = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "RSI", "SMA_Pct", "Current Price", "Currency", "Inv", "Mkt", "PnL", "Ret", "Wgt"]
    disp = v.reindex(columns=cols).copy()
    disp.columns = ["Tiker", "Companie", "Sector", "Acțiuni", "Preț mediu", "RSI (14)", "vs SMA 200 %", "Preț curent", "Monedă", "Valoare investită", "Valoare piață", "Profit / Pierdere", "Randament %", "Pondere %"]
    fmt = {"Acțiuni": f_shares, "Preț mediu": f_price, "RSI (14)": f_rsi, "vs SMA 200 %": f_sma, "Preț curent": f_price, "Valoare investită": f_num2, "Valoare piață": f_num2, "Profit / Pierdere": f_num2, "Randament %": f_pct, "Pondere %": f_pct}
