import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from utils import load_csv, fetch_data, fetch_annual_dividends, c_pnl, c_rsi, f_price, f_shares, f_num2, f_rsi, f_sma, f_pct, clean_table, quick_del

st.set_page_config(page_title="Portofoliu XTB", layout="wide")
CSV_PATH = Path(__file__).resolve().parent.parent / "portfolio.csv"
CLOSED_DIVS_EUR = 18.24

if st.button("⬅️ Meniu Principal"):
    st.switch_page("app.py")
if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.cache_data.clear()
    st.rerun()

st.title("📈 Portofoliu XTB")
req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]
df = load_csv(CSV_PATH, req).copy()
if "Dividends EUR" not in df.columns: df["Dividends EUR"] = 0.0

tickers = [x for x in df["Ticker"].dropna().unique().tolist() if str(x).strip() != ""]
all_curr = sorted([x for x in df["Currency"].dropna().unique().tolist() if str(x).strip() != ""]) or ["EUR", "USD"]
prices, _, rsi_m, sma_m, fx = fetch_data(tickers, list(set(all_curr + ["EUR", "USD", "GBP"])))
ann_div_per_share = fetch_annual_dividends(tickers)

for c in ["Shares", "Buy Price", "Current Price", "Dividends EUR"]:
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)

df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsi_m), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(sma_m), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current Price"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)

t_curr = st.sidebar.selectbox("Monedă raportare", ["EUR", "USD", "GBP"])
c_filt = st.sidebar.selectbox("Filtrare monedă", ["Toate (Consolidat)"] + all_curr)
sort_by = st.sidebar.selectbox("Ordonează după", ["Valoare piață", "Profit Total", "Dividende", "Dividende / an (Est.)", "Dividend % (Descrescător)", "YoC % (Descrescător)", "Randament %", "RSI (Crescător)", "vs SMA 200 %", "Tiker"])

t_rate = fx.get(t_curr, 1.0)
eur_rate = fx.get("EUR", 1.08) / t_rate
mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / t_rate

df["Div_Share"] = pd.to_numeric(df["Ticker"].map(ann_div_per_share), errors="coerce").fillna(0.0).astype(float)
df["Div_Yield"] = np.where((df["Current Price"] > 0) & (df["Div_Share"] > 0), (df["Div_Share"] / df["Current Price"]) * 100, np.nan).astype(float)
df["YoC"] = np.where((df["Buy Price"] > 0) & (df["Div_Share"] > 0), (df["Div_Share"] / df["Buy Price"]) * 100, np.nan).astype(float)

df["Inv"] = df["Shares"] * df["Buy Price"] * mult
df["Mkt"] = df["Shares"] * df["Current Price"] * mult
df["Div"] = df["Dividends EUR"] * eur_rate
df["Ann_Div"] = df["Shares"] * df["Div_Share"] * mult
df["PnL"] = (df["Mkt"] - df["Inv"]) + df["Div"]
df["Ret"] = np.where(df["Inv"] != 0, df["PnL"] / df["Inv"] * 100, 0.0).astype(float)

view = df.copy() if c_filt == "Toate (Consolidat)" else df[df["Currency"] == c_filt].copy()
extra_div = (CLOSED_DIVS_EUR * eur_rate) if c_filt == "Toate (Consolidat)" else 0.0
tot_mkt = view["Mkt"].sum()
view["Wgt"] = np.where(tot_mkt != 0, view["Mkt"] / tot_mkt * 100, 0.0).astype(float)

s_map = dict([
    ("Valoare piață", ("Mkt", False)),
    ("Profit Total", ("PnL", False)),
    ("Dividende", ("Div", False)),
    ("Dividende / an (Est.)", ("Ann_Div", False)),
    ("Dividend % (Descrescător)", ("Div_Yield", False)),
    ("YoC % (Descrescător)", ("YoC", False)),
    ("Randament %", ("Ret", False)),
    ("RSI (Crescător)", ("RSI", True)),
    ("vs SMA 200 %", ("SMA_Pct", True)),
    ("Tiker", ("Ticker", True))
])
col_s, asc_s = s_map[sort_by]
view = view.sort_values(by=col_s, ascending=asc_s, na_position="last")

inv_s, mkt_s, div_s = float(view["Inv"].sum()), float(view["Mkt"].sum()), float(view["Div"].sum() + extra_div)
ann_div_s = float(view["Ann_Div"].sum())
port_yoc = (ann_div_s / inv_s * 100) if inv_s > 0 else 0.0
gross_profit = float(view[view["PnL"] > 0]["PnL"].sum() + extra_div)
gross_loss = float(view[view["PnL"] < 0]["PnL"].sum())

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Poziții", f"{len(view)}")
c2.metric("Capital investit", f"{inv_s:,.2f} {t_curr}")
c3.metric("Valoare piață", f"{mkt_s:,.2f} {t_curr}")
c4.metric("Dividende nete", f"{div_s:,.2f} {t_curr}", f"~{ann_div_s:,.2f} {t_curr}/an (YoC {port_yoc:.2f}%)")
c5.metric("Profit Total (Poz.)", f"+{gross_profit:,.2f} {t_curr}", f"{len(view[view['PnL'] > 0])} pe plus", delta_color="normal")
c6.metric("Pierdere Totală (Neg.)", f"{gross_loss:,.2f} {t_curr}", f"-{len(view[view['PnL'] < 0])} pe minus", delta_color="normal")

def f_yoc(v):
    return "" if (pd.isna(v) or v == "" or float(v) <= 0) else f"{float(v):.2f}%"

if not view.empty:
    cols = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "RSI", "SMA_Pct", "Current Price", "Currency", "Inv", "Mkt", "Div", "Ann_Div", "Div_Yield", "YoC", "PnL", "Ret", "Wgt"]
    disp = view[cols].copy()
    disp.columns = ["Tiker", "Companie", "Sector", "Acțiuni", "Preț mediu", "RSI (14)", "vs SMA 200 %", "Preț curent", "Monedă", "Valoare investită", "Valoare piață", "Dividende", "Dividende / an (Est.)", "Dividend %", "YoC %", "Profit / Pierdere", "Randament %", "Pondere %"]
    fmt = dict([("Acțiuni", f_shares), ("Preț mediu", f_price), ("RSI (14)", f_rsi), ("vs SMA 200 %", f_sma), ("Preț curent", f_price), ("Valoare investită", f_num2), ("Valoare piață", f_num2), ("Dividende", f_num2), ("Dividende / an (Est.)", f_num2), ("Dividend %", f_yoc), ("YoC %", f_yoc), ("Profit / Pierdere", f_num2), ("Randament %", f_pct), ("Pondere %", f_pct)])
    disp_clean = clean_table(disp, fmt)
    styler = disp_clean.style.map(c_pnl, subset=["Profit / Pierdere", "Randament %", "vs SMA 200 %"]).map(c_rsi, subset=["RSI (14)"])
    st.dataframe(styler, use_container_width=True, hide_index=True, height=550, column_config=dict(Tiker=st.column_config.TextColumn("Tiker", pinned=True)))
    quick_del(df, req, CSV_PATH, "xtb")
    l1, r1 = st.columns(2)
    with l1:
        st.subheader(f"Profit / Pierdere Total ({t_curr})")
        st.bar_chart(view.set_index("Ticker")[["PnL"]].assign(Color=np.where(view["PnL"] >= 0, "#00e676", "#ff5252")), y="PnL", color="Color")
    with r1:
        st.subheader(f"Valoare de piață ({t_curr})")
        st.bar_chart(view.set_index("Ticker")["Mkt"], color="#29b6f6")

st.subheader("Editare poziții (portfolio.csv)")
edited = st.data_editor(view[req], num_rows="dynamic", use_container_width=True, key="ed_xtb")
if st.button("Salvează modificările în portfolio.csv"):
    up = edited if c_filt == "Toate (Consolidat)" else pd.concat([df[df["Currency"] != c_filt][req], edited], ignore_index=True)
    up.to_csv(CSV_PATH, index=False)
    st.cache_data.clear()
    st.success("Salvat!")
