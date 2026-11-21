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
        padding: 12px;
        border-radius: 8px;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.55rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 Panou de Control Portofoliu")
st.caption("Prețuri, indicatori tehnici (RSI 14, SMA 200), cursuri valutare live și dividende nete încasate din XTB.")

CSV_PATH = Path(__file__).with_name("portfolio.csv")
CLOSED_POSITIONS_DIVIDENDS_EUR = 18.24

@st.cache_data
def load_data():
    return pd.read_csv(CSV_PATH)

def compute_rsi(series, period=14):
    s = series.dropna()
    if len(s) < period + 1:
        return np.nan
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

def compute_sma200(series, scale=1.0):
    s = series.dropna()
    if len(s) < 200:
        return np.nan
    return float(s.iloc[-200:].mean()) * scale

@st.cache_data(ttl=300)
def fetch_live_market_data(tickers, currencies):
    prices = {}
    rsi_map = {}
    sma200_map = {}
    fx_rates = {"USD": 1.0}
    uk_pence_tickers = {"DGE.L", "BATS.L", "ABF.L"}

    if tickers:
        try:
            data = yf.download(tickers, period="1y", progress=False)["Close"]
            if isinstance(data, pd.Series):
                t = tickers if isinstance(tickers, list) else tickers
                s = data.dropna()
                if not s.empty:
                    scale = 0.01 if t in uk_pence_tickers else 1.0
                    prices[t] = float(s.iloc[-1]) * scale
                    rsi_map[t] = compute_rsi(s)
                    sma200_map[t] = compute_sma200(s, scale)
            else:
                for t in tickers:
                    if t in data.columns:
                        s = data[t].dropna()
                        if not s.empty:
                            scale = 0.01 if t in uk_pence_tickers else 1.0
                            prices[t] = float(s.iloc[-1]) * scale
                            rsi_map[t] = compute_rsi(s)
                            sma200_map[t] = compute_sma200(s, scale)
        except Exception:
            pass

    other_curr = [c for c in currencies if c != "USD"]
    fx_tickers = [f"{c}USD=X" for c in other_curr]
    fallback_to_usd = {"EUR": 1.08, "GBP": 1.27, "RON": 0.22}

    if fx_tickers:
        try:
            fx_data = yf.download(fx_tickers, period="5d", progress=False)["Close"]
            if isinstance(fx_data, pd.Series):
                c = other_curr
                if not fx_data.dropna().empty:
                    fx_rates[c] = float(fx_data.dropna().iloc[-1])
            else:
                for c in other_curr:
                    ft = f"{c}USD=X"
                    if ft in fx_data.columns and not fx_data[ft].dropna().empty:
                        fx_rates[c] = float(fx_data[ft].dropna().iloc[-1])
        except Exception:
            pass

    for c in other_curr:
        if c not in fx_rates:
            fx_rates[c] = fallback_to_usd.get(c, 1.0)

    return prices, rsi_map, sma200_map, fx_rates

df = load_data()
if "Dividends EUR" not in df.columns:
    df["Dividends EUR"] = 0.0

required = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]
for col in ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency"]:
    if col not in df.columns:
        st.error(f"Lipsește coloana: {col}")
        st.stop()

if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.cache_data.clear()
    st.rerun()

tickers = df["Ticker"].dropna().unique().tolist()
all_currencies = sorted(df["Currency"].dropna().unique().tolist()) or ["EUR", "USD"]
live_prices, rsi_map, sma200_map, fx_to_usd = fetch_live_market_data(
    tickers, list(set(all_currencies + ["EUR", "USD", "GBP"]))
)

df["Shares"] = pd.to_numeric(df["Shares"], errors="coerce").fillna(0)
df["Buy Price"] = pd.to_numeric(df["Buy Price"], errors="coerce").fillna(0)
df["Current Price"] = pd.to_numeric(df["Current Price"], errors="coerce").fillna(0)
df["Dividends EUR"] = pd.to_numeric(df["Dividends EUR"], errors="coerce").fillna(0)

df["Live Price"] = df["Ticker"].map(live_prices)
df["Current Price"] = np.where(df["Live Price"].notna(), df["Live Price"], df["Current Price"])
df["RSI"] = df["Ticker"].map(rsi_map)
df["SMA200"] = df["Ticker"].map(sma200_map)

st.sidebar.header("Setări afișare")
target_currency = st.sidebar.selectbox("Monedă raportare (Total)", ["EUR", "USD", "GBP"])
filter_options = ["Toate (Consolidat)"] + all_currencies
currency_filter = st.sidebar.selectbox("Filtrare poziții după monedă", filter_options)
sort_by = st.sidebar.selectbox(
    "Ordonează tabelul după",
    [
        "Valoare piață (Descrescător)",
        "Profit Total (Descrescător)",
        "Dividende (Descrescător)",
        "Randament Total % (Descrescător)",
        "RSI (Crescător - Supravândute)",
        "Simbol (A-Z)"
    ]
)

df["Rate_to_USD"] = df["Currency"].map(fx_to_usd).fillna(1.0)
target_rate_to_usd = fx_to_usd.get(target_currency, 1.0)
eur_to_target = fx_to_usd.get("EUR", 1.08) / target_rate_to_usd
df["FX_Multiplier"] = df["Rate_to_USD"] / target_rate_to_usd

df["Invested Value"] = df["Shares"] * df["Buy Price"] * df["FX_Multiplier"]
df["Market Value"] = df["Shares"] * df["Current Price"] * df["FX_Multiplier"]
df["Dividends"] = df["Dividends EUR"] * eur_to_target
df["Price P/L"] = df["Market Value"] - df["Invested Value"]
df["Total P/L"] = df["Price P/L"] + df["Dividends"]
df["Total Return %"] = np.where(df["Invested Value"] != 0, df["Total P/L"] / df["Invested Value"] * 100, 0)

if currency_filter == "Toate (Consolidat)":
    view = df.copy()
    extra_closed_divs = CLOSED_POSITIONS_DIVIDENDS_EUR * eur_to_target
else:
    view = df[df["Currency"] == currency_filter].copy()
    extra_closed_divs = 0.0

total_market_val = view["Market Value"].sum()
view["Weight %"] = np.where(total_market_val != 0, view["Market Value"] / total_market_val * 100, 0)

if sort_by == "Valoare piață (Descrescător)":
    view = view.sort_values(by="Market Value", ascending=False)
elif sort_by == "Profit Total (Descrescător)":
    view = view.sort_values(by="Total P/L", ascending=False)
elif sort_by == "Dividende (Descrescător)":
    view = view.sort_values(by="Dividends", ascending=False)
elif sort_by == "Randament Total % (Descrescător)":
    view = view.sort_values(by="Total Return %", ascending=False)
elif sort_by == "RSI (Crescător - Supravândute)":
    view = view.sort_values(by="RSI", ascending=True, na_position="last")
else:
    view = view.sort_values(by="Ticker", ascending=True)

eur_usd = fx_to_usd.get("EUR", 1.08)
gbp_eur = fx_to_usd.get("GBP", 1.27) / eur_usd
st.sidebar.info(
    f"Prețuri live: {len(live_prices)}/{len(tickers)} simboluri\n\n"
    f"**Cursuri live:**\n"
    f"- 1 EUR = {eur_usd:.4f} USD\n"
    f"- 1 GBP = {gbp_eur:.4f} EUR"
)

invested = view["Invested Value"].sum()
market = view["Market Value"].sum()
open_divs = view["Dividends"].sum()
total_divs = open_divs + extra_closed_divs
total_pnl = (market - invested) + total_divs
total_ret = total_pnl / invested * 100 if invested else 0

c1, c2, c3, c4, c5 = st.columns([0.8, 1.2, 1.2, 1.2, 1.4])
c1.metric("Poziții", f"{len(view)}")
c2.metric("Capital investit", f"{invested:,.2f} {target_currency}")
c3.metric("Valoare piață", f"{market:,.2f} {target_currency}")
c4.metric("Dividende nete", f"{total_divs:,.2f} {target_currency}", f"+{extra_closed_divs:,.2f} din închise" if extra_closed_divs > 0 else None)
c5.metric("Profit Total (+Div.)", f"{total_pnl:,.2f} {target_currency}", f"{total_ret:.2f}%")

st.subheader(f"Portofoliu (Valori convertite în {target_currency})")

display_df = view[[
    "Ticker", "Company", "Sector", "Shares", "Buy Price", "RSI", "SMA200", "Current Price", "Currency",
    "Invested Value", "Market Value", "Dividends", "Total P/L", "Total Return %", "Weight %"
]].rename(columns={
    "Ticker": "Simbol",
    "Company": "Companie",
    "Sector": "Sector",
    "Shares": "Acțiuni",
    "Buy Price": "Preț mediu",
    "RSI": "RSI (14)",
    "SMA200": "SMA 200",
    "Current Price": "Preț curent",
    "Currency": "Monedă",
    "Invested Value": "Valoare investită",
    "Market Value": "Valoare piață",
    "Dividends": "Dividende",
    "Total P/L": "Profit / Pierdere",
    "Total Return %": "Randament %",
    "Weight %": "Pondere %"
})

def color_pnl_cols(val):
    if pd.isna(val):
        return "color: #fafafa;"
    if val > 0:
        return "color: #00e676; font-weight: bold;"
    elif val < 0:
        return "color: #ff5252; font-weight: bold;"
    return "color: #fafafa;"

def color_rsi_col(val):
    if pd.isna(val):
        return "color: #9e9e9e;"
    if val <= 30:
        return "color: #00e676; font-weight: bold;"
    elif val >= 70:
        return "color: #ff5252; font-weight: bold;"
    return "color: #fafafa;"

def style_sma200_row(row):
    styles = [""] * len(row)
    sma = row["SMA 200"]
    price = row["Preț curent"]
    if pd.notna(sma) and pd.notna(price):
        idx = row.index.get_loc("SMA 200")
        if price > sma:
            styles[idx] = "color: #00e676; font-weight: bold;"
        elif price < sma:
            styles[idx] = "color: #ff5252; font-weight: bold;"
    return styles

fmt_dict = {
    "Acțiuni": "{:,.4g}",
    "Preț mediu": "{:,.2f}",
    "RSI (14)": "{:.1f}",
    "SMA 200": "{:,.2f}",
    "Preț curent": "{:,.2f}",
    "Valoare investită": "{:,.2f}",
    "Valoare piață": "{:,.2f}",
