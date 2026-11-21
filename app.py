import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path

st.set_page_config(page_title="Portfolio Dashboard", layout="wide")
st.title("📊 Stock Portfolio Dashboard")
st.caption("Prețuri și cursuri valutare live prin Yahoo Finance (cu rezervă din CSV).")

CSV_PATH = Path(__file__).with_name("portfolio.csv")

@st.cache_data
def load_data():
    return pd.read_csv(CSV_PATH)

@st.cache_data(ttl=300)
def fetch_live_market_data(tickers, currencies):
    prices = {}
    fx_rates = {"USD": 1.0}

    # Simbolurile de pe bursa din Londra cotate în pence (GBX) în loc de lire (GBP)
    uk_pence_tickers = {"DGE.L", "BATS.L", "ABF.L"}

    # 1. Prețuri acțiuni
    if tickers:
        try:
            data = yf.download(tickers, period="5d", progress=False)["Close"]
            if isinstance(data, pd.Series):
                t = tickers
                if not data.dropna().empty:
                    val = float(data.dropna().iloc[-1])
                    prices[t] = val / 100.0 if t in uk_pence_tickers else val
            else:
                for t in tickers:
                    if t in data.columns and not data[t].dropna().empty:
                        val = float(data[t].dropna().iloc[-1])
                        prices[t] = val / 100.0 if t in uk_pence_tickers else val
        except Exception:
            pass

    # 2. Cursuri valutare live față de USD
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

    return prices, fx_rates

df = load_data()
required = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency"]
for col in required:
    if col not in df.columns:
        st.error(f"Missing column: {col}")
        st.stop()

if st.sidebar.button("🔄 Refresh Live Prices"):
    st.cache_data.clear()
    st.rerun()

tickers = df["Ticker"].dropna().unique().tolist()
all_currencies = sorted(df["Currency"].dropna().unique().tolist()) or ["EUR", "USD"]
live_prices, fx_to_usd = fetch_live_market_data(tickers, list(set(all_currencies + ["EUR", "USD", "GBP"])))

df["Shares"] = pd.to_numeric(df["Shares"], errors="coerce").fillna(0)
df["Buy Price"] = pd.to_numeric(df["Buy Price"], errors="coerce").fillna(0)
df["Current Price"] = pd.to_numeric(df["Current Price"], errors="coerce").fillna(0)

# Actualizare prețuri live
df["Live Price"] = df["Ticker"].map(live_prices)
df["Current Price"] = np.where(df["Live Price"].notna(), df["Live Price"], df["Current Price"])

# Filtre în bara laterală
st.sidebar.header("Setări afișare")
target_currency = st.sidebar.selectbox("Monedă raportare (Total)", ["EUR", "USD", "GBP"])
filter_options = ["Toate (Consolidat)"] + all_currencies
currency_filter = st.sidebar.selectbox("Filtrare poziții după monedă", filter_options)

# Conversie în moneda aleasă
df["Rate_to_USD"] = df["Currency"].map(fx_to_usd).fillna(1.0)
target_rate_to_usd = fx_to_usd.get(target_currency, 1.0)
df["FX_Multiplier"] = df["Rate_to_USD"] / target_rate_to_usd

df["Invested Value"] = df["Shares"] * df["Buy Price"] * df["FX_Multiplier"]
df["Market Value"] = df["Shares"] * df["Current Price"] * df["FX_Multiplier"]
df["Profit/Loss"] = df["Market Value"] - df["Invested Value"]
df["Return %"] = np.where(df["Invested Value"] != 0, df["Profit/Loss"] / df["Invested Value"] * 100, 0)

if currency_filter == "Toate (Consolidat)":
    view = df.copy()
else:
    view = df[df["Currency"] == currency_filter].copy()

eur_usd = fx_to_usd.get("EUR", 1.08)
gbp_eur = fx_to_usd.get("GBP", 1.27) / eur_usd
st.sidebar.info(
    f"Prețuri live: {len(live_prices)}/{len(tickers)} simboluri\n\n"
    f"**Cursuri live:**\n"
    f"- 1 EUR = {eur_usd:.4f} USD\n"
    f"- 1 GBP = {gbp_eur:.4f} EUR"
)

# Metrici generale
invested = view["Invested Value"].sum()
market = view["Market Value"].sum()
pnl = view["Profit/Loss"].sum()
ret = pnl / invested * 100 if invested else 0
total_shares = view["Shares"].sum()

c1, c2, c3, c4, c5 = st.columns([1, 1, 1.3, 1.3, 1.3])
c1.metric("Acțiuni / Unități", f"{total_shares:,.4g}")
c2.metric("Poziții deschise", f"{len(view)}")
c3.metric("Capital investit", f"{invested:,.2f} {target_currency}")
c4.metric("Valoare piață", f"{market:,.2f} {target_currency}")
c5.metric("Profit / Pierdere", f"{pnl:,.2f} {target_currency}", f"{ret:.2f}%")

st.subheader(f"Portofoliu (Valori convertite în {target_currency})")
display_cols = [
    "Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency",
    "Invested Value", "Market Value", "Profit/Loss", "Return %"
]
st.dataframe(view[display_cols].style.format({
    "Shares": "{:,.4g}",
    "Buy Price": "{:,.2f}",
    "Current Price": "{:,.2f}",
    "Invested Value": "{:,.2f}",
    "Market Value": "{:,.2f}",
    "Profit/Loss": "{:,.2f}",
    "Return %": "{:.2f}%"
}), use_container_width=True, hide_index=True)

left, right = st.columns(2)
with left:
    st.subheader(f"Valoare de piață per simbol ({target_currency})")
    if not view.empty:
        st.bar_chart(view.set_index("Ticker")["Market Value"])
with right:
    st.subheader(f"Alocare pe sectoare ({target_currency})")
    sector_values = view.groupby("Sector")["Market Value"].sum()
    if not sector_values.empty:
        st.bar_chart(sector_values)

st.subheader("Editare poziții (în moneda originală)")
edited = st.data_editor(view[required], num_rows="dynamic", use_container_width=True, key="portfolio_editor")
if st.button("Save changes to portfolio.csv"):
    if currency_filter == "Toate (Consolidat)":
        updated_df = edited
    else:
        other_currencies = df[df["Currency"] != currency_filter][required]
        updated_df = pd.concat([other_currencies, edited], ignore_index=True)
    updated_df.to_csv(CSV_PATH, index=False)
    st.cache_data.clear()
    st.success("Salvat! Reîncarcă pagina pentru a recalcula.")

st.download_button(
    f"Descarcă portofoliul ({target_currency}) ca CSV",
    view[display_cols].to_csv(index=False),
    f"portfolio_{target_currency}.csv",
    "text/csv"
)
