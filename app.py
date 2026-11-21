import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path

st.set_page_config(page_title="Portfolio Dashboard", layout="wide")
st.title("📊 Stock Portfolio Dashboard")
st.caption("Live market prices powered by Yahoo Finance (fallback to CSV prices if unavailable).")

CSV_PATH = Path(__file__).with_name("portfolio.csv")

@st.cache_data
def load_data():
    return pd.read_csv(CSV_PATH)

@st.cache_data(ttl=300)
def fetch_live_prices(tickers):
    prices = {}
    if not tickers:
        return prices
    try:
        data = yf.download(tickers, period="5d", progress=False)["Close"]
        if isinstance(data, pd.Series):
            prices[tickers[0]] = float(data.dropna().iloc[-1])
        else:
            for t in tickers:
                if t in data.columns and not data[t].dropna().empty:
                    prices[t] = float(data[t].dropna().iloc[-1])
    except Exception:
        pass
    return prices

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
live_prices = fetch_live_prices(tickers)

df["Shares"] = pd.to_numeric(df["Shares"], errors="coerce").fillna(0)
df["Buy Price"] = pd.to_numeric(df["Buy Price"], errors="coerce").fillna(0)
df["Current Price"] = pd.to_numeric(df["Current Price"], errors="coerce").fillna(0)

# Actualizare cu preturile live acolo unde sunt disponibile
df["Live Price"] = df["Ticker"].map(live_prices)
df["Current Price"] = np.where(df["Live Price"].notna(), df["Live Price"], df["Current Price"])

df["Invested Value"] = df["Shares"] * df["Buy Price"]
df["Market Value"] = df["Shares"] * df["Current Price"]
df["Profit/Loss"] = df["Market Value"] - df["Invested Value"]
df["Return %"] = np.where(df["Invested Value"] != 0, df["Profit/Loss"] / df["Invested Value"] * 100, 0)

currencies = sorted(df["Currency"].dropna().unique().tolist()) or ["USD"]
currency = st.sidebar.selectbox("Currency displayed", currencies)
view = df[df["Currency"] == currency].copy()

st.sidebar.info(f"Prețuri live preluate pentru {len(live_prices)} din {len(tickers)} simboluri.")

invested = view["Invested Value"].sum()
market = view["Market Value"].sum()
pnl = view["Profit/Loss"].sum()
ret = pnl / invested * 100 if invested else 0
total_shares = view["Shares"].sum()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Number of shares", f"{total_shares:,.4g}")
c2.metric("Holdings", f"{len(view)}")
c3.metric("Invested capital", f"{invested:,.2f} {currency}")
c4.metric("Market value", f"{market:,.2f} {currency}")
c5.metric("Profit / loss", f"{pnl:,.2f} {currency}", f"{ret:.2f}%")

st.subheader("Holdings")
display_cols = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price",
                "Invested Value", "Market Value", "Profit/Loss", "Return %", "Currency"]
st.dataframe(view[display_cols].style.format({
    "Shares": "{:,.4g}", "Buy Price": "{:,.2f}", "Current Price": "{:,.2f}",
    "Invested Value": "{:,.2f}", "Market Value": "{:,.2f}",
    "Profit/Loss": "{:,.2f}", "Return %": "{:.2f}%"
}), use_container_width=True, hide_index=True)

left, right = st.columns(2)
with left:
    st.subheader("Market value by ticker")
    if not view.empty:
        st.bar_chart(view.set_index("Ticker")["Market Value"])
with right:
    st.subheader("Portfolio allocation by sector")
    sector_values = view.groupby("Sector")["Market Value"].sum()
    if not sector_values.empty:
        st.bar_chart(sector_values)

st.subheader("Edit holdings")
edited = st.data_editor(view[required], num_rows="dynamic", use_container_width=True, key="portfolio_editor")
if st.button("Save changes to portfolio.csv"):
    other_currencies = df[df["Currency"] != currency][required]
    updated_df = pd.concat([other_currencies, edited], ignore_index=True)
    updated_df.to_csv(CSV_PATH, index=False)
    st.cache_data.clear()
    st.success("Saved. Refresh the page to recalculate metrics.")

st.download_button("Download displayed holdings as CSV", view[display_cols].to_csv(index=False), "portfolio_export.csv", "text/csv")
