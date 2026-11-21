import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path

st.set_page_config(page_title="Panou Portofoliu", layout="wide")

st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 10px 12px;
        border-radius: 8px;
    }
    div[data-testid="stMetricValue"] { font-size: 1.35rem !important; }
    .custom-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 10px 12px;
        border-radius: 8px;
        height: 100%;
    }
    .custom-card-label { font-size: 0.875rem; color: #fafafa; margin-bottom: 4px; }
    .custom-card-val { font-size: 1.35rem; font-weight: 600; line-height: 1.2; }
    .custom-card-sub { font-size: 0.8rem; margin-top: 4px; color: #9e9e9e; }
    .tbl-box {
        height: 550px;
        overflow: auto;
        border: 1px solid #30363d;
        border-radius: 8px;
        background: #0e1117;
    }
    .tbl-box table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        font-size: 14px;
        color: #fafafa;
    }
    .tbl-box thead th {
        position: sticky;
        top: 0;
        background: #161b22;
        z-index: 2;
        padding: 10px 8px;
        text-align: left;
        border-bottom: 2px solid #30363d;
        white-space: nowrap;
    }
    .tbl-box tbody td {
        padding: 8px;
        border-bottom: 1px solid #21262d;
        white-space: nowrap;
        background: #0e1117;
    }
    .tbl-box tbody tr:hover td { background: #1c2128; }
    .tbl-box thead th:first-child {
        position: sticky;
        left: 0;
        z-index: 4;
        border-right: 1px solid #30363d;
    }
    .tbl-box tbody td:first-child {
        position: sticky;
        left: 0;
        z-index: 3;
        background: #161b22;
        border-right: 1px solid #30363d;
    }
    .tbl-box tbody tr:hover td:first-child { background: #1c2128; }
    .tbl-box::-webkit-scrollbar { width: 12px; height: 12px; }
    .tbl-box::-webkit-scrollbar-track { background: #0e1117; }
    .tbl-box::-webkit-scrollbar-thumb { background: #30363d; border-radius: 6px; }
    .tbl-box::-webkit-scrollbar-thumb:hover { background: #58a6ff; }
</style>
""", unsafe_allow_html=True)

st.title("📊 Panou de Control Portofoliu")
st.caption("Prețuri, indicatori tehnici (RSI 14, vs SMA 200 %), cursuri valutare live și dividende nete din XTB.")

CSV_PATH = Path(__file__).with_name("portfolio.csv")
CLOSED_DIVS_EUR = 18.24

@st.cache_data
def load_data():
    return pd.read_csv(CSV_PATH)

def calc_rsi(s, p=14):
    s = s.dropna()
    if len(s) < p + 1: return np.nan
    d = s.diff()
    ag = d.clip(lower=0).ewm(alpha=1/p, min_periods=p, adjust=False).mean()
    al = (-d.clip(upper=0)).ewm(alpha=1/p, min_periods=p, adjust=False).mean()
    return float((100 - (100 / (1 + ag / al))).iloc[-1])

def calc_sma(s, sc=1.0):
    s = s.dropna()
    return float(s.iloc[-200:].mean()) * sc if len(s) >= 200 else np.nan

@st.cache_data(ttl=300)
def fetch_data(tickers, currencies):
    prices, rsi_m, sma_m = dict(), dict(), dict()
    fx = dict(USD=1.0)
    uk = ["DGE.L", "BATS.L", "ABF.L"]
    if tickers:
        try:
            data = yf.download(tickers, period="1y", progress=False)["Close"]
            for t in ([tickers] if isinstance(tickers, str) else tickers):
                s = data.dropna() if isinstance(data, pd.Series) else (data[t].dropna() if t in data.columns else pd.Series())
                if not s.empty:
                    sc = 0.01 if t in uk else 1.0
                    prices[t] = float(s.iloc[-1]) * sc
                    rsi_m[t] = calc_rsi(s)
                    sma_m[t] = calc_sma(s, sc)
        except Exception:
            pass
    other = [c for c in currencies if c != "USD"]
    fb = dict(EUR=1.08, GBP=1.27, RON=0.22)
    if other:
        try:
            fxd = yf.download([c + "USD=X" for c in other], period="5d", progress=False)["Close"]
            for c in other:
                ft = c + "USD=X"
                s = fxd.dropna() if isinstance(fxd, pd.Series) else (fxd[ft].dropna() if ft in fxd.columns else pd.Series())
                if not s.empty: fx[c] = float(s.iloc[-1])
        except Exception:
            pass
    for c in other:
        fx[c] = fx.get(c, fb.get(c, 1.0))
    return prices, rsi_m, sma_m, fx

df = load_data()
if "Dividends EUR" not in df.columns: df["Dividends EUR"] = 0.0
req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]

if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.cache_data.clear()
    st.rerun()

tickers = df["Ticker"].dropna().unique().tolist()
all_curr = sorted(df["Currency"].dropna().unique().tolist()) or ["EUR", "USD"]
prices, rsi_m, sma_m, fx = fetch_data(tickers, list(set(all_curr + ["EUR", "USD", "GBP"])))

for c in ["Shares", "Buy Price", "Current Price", "Dividends EUR"]:
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"])
df["RSI"] = df["Ticker"].map(rsi_m)
df["SMA200"] = df["Ticker"].map(sma_m)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current Price"] - df["SMA200"]) / df["SMA200"] * 100, np.nan)

st.sidebar.header("Setări afișare")
t_curr = st.sidebar.selectbox("Monedă raportare (Total)", ["EUR", "USD", "GBP"])
c_filt = st.sidebar.selectbox("Filtrare poziții după monedă", ["Toate (Consolidat)"] + all_curr)
sort_by = st.sidebar.selectbox("Ordonează tabelul după", ["Valoare piață", "Profit Total", "Dividende", "Randament %", "RSI (Crescător)", "vs SMA 200 %", "Tiker"])

t_rate = fx.get(t_curr, 1.0)
eur_rate = fx.get("EUR", 1.08) / t_rate
mult = df["Currency"].map(fx).fillna(1.0) / t_rate

df["Inv"] = df["Shares"] * df["Buy Price"] * mult
df["Mkt"] = df["Shares"] * df["Current Price"] * mult
df["Div"] = df["Dividends EUR"] * eur_rate
df["PnL"] = (df["Mkt"] - df["Inv"]) + df["Div"]
df["Ret"] = np.where(df["Inv"] != 0, df["PnL"] / df["Inv"] * 100, 0)

view = df.copy() if c_filt == "Toate (Consolidat)" else df[df["Currency"] == c_filt].copy()
extra_div = CLOSED_DIVS_EUR * eur_rate if c_filt == "Toate (Consolidat)" else 0.0
tot_mkt = view["Mkt"].sum()
view["Wgt"] = np.where(tot_mkt != 0, view["Mkt"] / tot_mkt * 100, 0)

s_map = {"Valoare piață": ("Mkt", False), "Profit Total": ("PnL", False), "Dividende": ("Div", False), "Randament %": ("Ret", False), "RSI (Crescător)": ("RSI", True), "vs SMA 200 %": ("SMA_Pct", True), "Tiker": ("Ticker", True)}
col_s, asc_s = s_map[sort_by]
view = view.sort_values(by=col_s, ascending=asc_s, na_position="last")

st.sidebar.info(f"Prețuri live: {len(prices)}/{len(tickers)}\n\n1 EUR = {fx.get('EUR', 1.08):.4f} USD\n\n1 GBP = {fx.get('GBP', 1.27)/fx.get('EUR', 1.08):.4f} EUR")

inv_s, mkt_s, div_s = view["Inv"].sum(), view["Mkt"].sum(), view["Div"].sum() + extra_div
gross_profit = view[view["PnL"] > 0]["PnL"].sum() + extra_div
gross_loss = view[view["PnL"] < 0]["PnL"].sum()
net_pnl = gross_profit + gross_loss

c1, c2, c3, c4, c5, c6 = st.columns([0.7, 1.15, 1.15, 1.15, 1.15, 1.15])
c1.metric("Poziții", f"{len(view)}")
c2.metric("Capital investit", f"{inv_s:,.2f} {t_curr}")
c3.metric("Valoare piață", f"{mkt_s:,.2f} {t_curr}")
c4.metric("Dividende nete", f"{div_s:,.2f} {t_curr}", f"+{extra_div:,.2f} închise" if extra_div > 0 else None)

with c5:
    st.markdown(
        f"<div class='custom-card'>"
        f"<div class='custom-card-label'>Profit Total (Poz.)</div>"
        f"<div class='custom-card-val' style='color:#00e676;'>+{gross_profit:,.2f} {t_curr}</div>"
        f"<div class='custom-card-sub'>Net: {net_pnl:+.2f} {t_curr}</div>"
        f"</div>",
        unsafe_allow_html=True
    )

with c6:
    st.markdown(
        f"<div class='custom-card'>"
        f"<div class='custom-card-label'>Pierdere Totală (Neg.)</div>"
        f"<div class='custom-card-val' style='color:#ff5252;'>{gross_loss:,.2f} {t_curr}</div>"
        f"<div class='custom-card-sub'>{len(view[view['PnL'] < 0])} poziții pe minus</div>"
        f"</div>",
        unsafe_allow_html=True
    )

st.subheader(f"Portofoliu (Valori convertite în {t_curr})")

t_df = pd.DataFrame()
t_df["Tiker"] = "<b>" + view["Ticker"] + "</b>"
t_df["Companie"] = view["Company"]
t_df["Sector"] = view["Sector"]
t_df["Acțiuni"] = view["Shares"].map(lambda x: f"{x:,.4g}")
t_df["Preț mediu"] = view["Buy Price"].map(lambda x: f"{x:,.2f}")
t_df["RSI (14)"] = view["RSI"].map(lambda x: "-" if pd.isna(x) else f"<span style='color:{'#00e676' if x<=30 else ('#ff5252' if x>=70 else '#fafafa')};font-weight:bold'>{x:.1f}</span>")
t_df["vs SMA 200 %"] = view["SMA_Pct"].map(lambda x: "-" if pd.isna(x) else f"<span style='color:{'#00e676' if x>0 else '#ff5252'};font-weight:bold'>{x:+.2f}%</span>")
t_df["Preț curent"] = view["Current Price"].map(lambda x: f"{x:,.2f}")
t_df["Monedă"] = view["Currency"]
t_df["Valoare investită"] = view["Inv"].map(lambda x: f"{x:,.2f}")
t_df["Valoare piață"] = view["Mkt"].map(lambda x: f"{x:,.2f}")
t_df["Dividende"] = view["Div"].map(lambda x: f"{x:,.2f}")
t_df["Profit / Pierdere"] = view["PnL"].map(lambda x: f"<span style='color:{'#00e676' if x>0 else ('#ff5252' if x<0 else '#fafafa')};font-weight:bold'>{x:,.2f}</span>")
t_df["Randament %"] = view["Ret"].map(lambda x: f"<span style='color:{'#00e676' if x>0 else ('#ff5252' if x<0 else '#fafafa')};font-weight:bold'>{x:.2f}%</span>")
t_df["Pondere %"] = view["Wgt"].map(lambda x: f"{x:.2f}%")

st.markdown(f"<div class='tbl-box'>{t_df.to_html(escape=False, index=False)}</div>", unsafe_allow_html=True)

st.write("")
l1, r1 = st.columns(2)
with l1:
    st.subheader(f"Profit / Pierdere Total ({t_curr})")
    if not view.empty:
        p_df = view.set_index("Ticker")[["PnL"]].assign(Color=np.where(view["PnL"] >= 0, "#00e676", "#ff5252"))
        st.bar_chart(p_df, y="PnL", color="Color")
