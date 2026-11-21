import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import load_csv, save_csv_permanent, get_meta, fetch_data, c_pnl, c_rsi, f_price, f_shares, f_num2, f_rsi, f_sma, f_pct, clean_table, quick_del

st.set_page_config(page_title="Portofoliu Kraken", layout="wide")
CSV_PATH = Path(__file__).resolve().parent.parent / "portfolio_kraken.csv"

def parse_kraken_trades(uploaded_file):
    kdf = pd.read_csv(uploaded_file)
    if "pair" not in kdf.columns or "vol" not in kdf.columns or "cost" not in kdf.columns:
        return pd.DataFrame()
    kdf["vol"] = pd.to_numeric(kdf["vol"], errors="coerce").fillna(0.0)
    kdf["cost"] = pd.to_numeric(kdf["cost"], errors="coerce").fillna(0.0)
    kdf["fee"] = pd.to_numeric(kdf.get("fee", 0.0), errors="coerce").fillna(0.0)
    kdf["type"] = kdf.get("type", "buy").astype(str).str.lower()

    rows = []
    for pair, grp in kdf.groupby("pair"):
        clean_pair = str(pair).replace("/", "-").replace("XBT", "BTC").upper()
        curr = clean_pair.split("-")[-1] if "-" in clean_pair else "EUR"
        buys = grp[grp["type"] == "buy"]
        sells = grp[grp["type"] == "sell"]
        net_vol = buys["vol"].sum() - sells["vol"].sum()
        if net_vol <= 1e-8:
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

if "show_imp_krk" not in st.session_state:
    st.session_state.show_imp_krk = False

nav1, nav2, _ = st.columns([1.2, 1.3, 5.5])
if nav1.button("⬅️ Meniu Principal", use_container_width=True):
    st.switch_page("app.py")
if nav2.button("📥 Importă Kraken", use_container_width=True):
    st.session_state.show_imp_krk = not st.session_state.show_imp_krk

if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.cache_data.clear()
    st.rerun()

req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]
df = load_csv(CSV_PATH, req).copy()

if st.session_state.show_imp_krk:
    with st.container(border=True):
        up_krk = st.file_uploader("Încarcă fișierul CSV 'Trades' descărcat din Kraken:", type=["csv"], key="up_krk")
        if up_krk is not None and st.button("Procesează și Salvează Permanent", type="primary", key="btn_imp_krk"):
            new_kdf = parse_kraken_trades(up_krk)
            if not new_kdf.empty:
                ok = save_csv_permanent(new_kdf[req], CSV_PATH)
                st.session_state.show_imp_krk = False
                st.cache_data.clear()
                st.success("Importat și salvat permanent pe GitHub!" if ok else "Importat local!")
                st.rerun()
            else:
                st.error("Fișierul nu conține tranzacții Kraken valide.")

st.title("🪙 Portofoliu Kraken")

tickers = [x for x in df["Ticker"].dropna().unique().tolist() if str(x).strip() != ""]
all_curr = sorted([x for x in df["Currency"].dropna().unique().tolist() if str(x).strip() != ""]) or ["EUR", "USD"]
prices, _, rsi_m, sma_m, fx = fetch_data(tickers, list(set(all_curr + ["EUR", "USD", "GBP"])))

for c in ["Shares", "Buy Price", "Current Price"]:
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)

df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsi_m), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(sma_m), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current Price"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)

t_curr = st.sidebar.selectbox("Monedă raportare", ["EUR", "USD", "GBP"])
sort_by = st.sidebar.selectbox("Ordonează după", ["Valoare piață", "Profit Total", "Randament %", "RSI (Crescător)", "vs SMA 200 %", "Tiker"])

t_rate = fx.get(t_curr, 1.0)
mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / t_rate

df["Inv"] = df["Shares"] * df["Buy Price"] * mult
df["Mkt"] = df["Shares"] * df["Current Price"] * mult
df["PnL"] = df["Mkt"] - df["Inv"]
df["Ret"] = np.where(df["Inv"] != 0, df["PnL"] / df["Inv"] * 100, 0.0).astype(float)

tot_mkt = df["Mkt"].sum()
df["Wgt"] = np.where(tot_mkt != 0, df["Mkt"] / tot_mkt * 100, 0.0).astype(float)

s_map = dict([("Valoare piață", ("Mkt", False)), ("Profit Total", ("PnL", False)), ("Randament %", ("Ret", False)), ("RSI (Crescător)", ("RSI", True)), ("vs SMA 200 %", ("SMA_Pct", True)), ("Tiker", ("Ticker", True))])
col_s, asc_s = s_map[sort_by]
view = df.sort_values(by=col_s, ascending=asc_s, na_position="last")

inv_s, mkt_s = float(view["Inv"].sum()), float(view["Mkt"].sum())
gross_profit = float(view[view["PnL"] > 0]["PnL"].sum())
gross_loss = float(view[view["PnL"] < 0]["PnL"].sum())

c1, c2, c3, c5, c6 = st.columns(5)
c1.metric("Poziții", f"{len(view)}")
c2.metric("Capital investit", f"{inv_s:,.2f} {t_curr}")
c3.metric("Valoare piață", f"{mkt_s:,.2f} {t_curr}")
c5.metric("Profit Total (Poz.)", f"+{gross_profit:,.2f} {t_curr}", f"{len(view[view['PnL'] > 0])} pe plus", delta_color="normal")
c6.metric("Pierdere Totală (Neg.)", f"{gross_loss:,.2f} {t_curr}", f"-{len(view[view['PnL'] < 0])} pe minus", delta_color="normal")

if not view.empty:
    cols = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "RSI", "SMA_Pct", "Current Price", "Currency", "Inv", "Mkt", "PnL", "Ret", "Wgt"]
    disp = view[cols].copy()
    disp.columns = ["Tiker", "Companie", "Sector", "Acțiuni", "Preț mediu", "RSI (14)", "vs SMA 200 %", "Preț curent", "Monedă", "Valoare investită", "Valoare piață", "Profit / Pierdere", "Randament %", "Pondere %"]
    fmt = dict([("Acțiuni", f_shares), ("Preț mediu", f_price), ("RSI (14)", f_rsi), ("vs SMA 200 %", f_sma), ("Preț curent", f_price), ("Valoare investită", f_num2), ("Valoare piață", f_num2), ("Profit / Pierdere", f_num2), ("Randament %", f_pct), ("Pondere %", f_pct)])
    disp_clean = clean_table(disp, fmt)
    styler = disp_clean.style.map(c_pnl, subset=["Profit / Pierdere", "Randament %", "vs SMA 200 %"]).map(c_rsi, subset=["RSI (14)"])
    st.dataframe(styler, use_container_width=True, hide_index=True, height=400, column_config=dict(Tiker=st.column_config.TextColumn("Tiker", pinned=True)))
    quick_del(df, req, CSV_PATH, "kraken")
    l1, r1 = st.columns(2)
    with l1:
        st.subheader(f"Profit / Pierdere Total ({t_curr})")
        st.bar_chart(view.set_index("Ticker")[["PnL"]].assign(Color=np.where(view["PnL"] >= 0, "#00e676", "#ff5252")), y="PnL", color="Color")
    with r1:
        st.subheader(f"Valoare de piață ({t_curr})")
        st.bar_chart(view.set_index("Ticker")["Mkt"], color="#29b6f6")

st.subheader("Editare poziții (portfolio_kraken.csv)")
edited = st.data_editor(view[req], num_rows="dynamic", use_container_width=True, key="ed_kraken")
if st.button("Salvează modificările în portfolio_kraken.csv"):
    ok = save_csv_permanent(edited, CSV_PATH)
    st.cache_data.clear()
    st.success("Salvat permanent pe GitHub!" if ok else "Salvat local!")
