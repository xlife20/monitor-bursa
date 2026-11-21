import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path

st.set_page_config(page_title="Portfolio Dashboard", layout="wide")
st.title("📊 Stock Portfolio Dashboard")
st.caption("Starter template — edit portfolio.csv with your own holdings. Example prices are illustrative, not live quotes.")

CSV_PATH = Path(__file__).with_name("portfolio.csv")

@st.cache_data
def load_data():
    return pd.read_csv(CSV_PATH)

df = load_data()
required = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency"]
for col in required:
    if col not in df.columns:
        st.error(f"Missing column: {col}")
        st.stop()

df["Shares"] = pd.to_numeric(df["Shares"], errors="coerce").fillna(0)
df["Buy Price"] = pd.to_numeric(df["Buy Price"], errors="coerce").fillna(0)
df["Current Price"] = pd.to_numeric(df["Current Price"], errors="coerce").fillna(0)
df["Invested Value"] = df["Shares"] * df["Buy Price"]
df["Market Value"] = df["Shares"] * df["Current Price"]
df["Profit/Loss"] = df["Market Value"] - df["Invested Value"]
df["Return %"] = np.where(df["Invested Value"] != 0, df["Profit/Loss"] / df["Invested Value"] * 100, 0)

currency = st.sidebar.selectbox("Currency displayed", sorted(df["Currency"].dropna().unique().tolist()) or ["USD"])
view = df[df["Currency"] == currency].copy()
st.sidebar.info("Prices in this template are manual/example values. Replace them in portfolio.csv or connect a market-data provider.")

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
    # Preserve the displayed currency-filtered portfolio as the saved file.
    edited.to_csv(CSV_PATH, index=False)
    st.cache_data.clear()
    st.success("Saved. Refresh the page to recalculate metrics.")

st.download_button("Download displayed holdings as CSV", view[display_cols].to_csv(index=False), "portfolio_export.csv", "text/csv")
st.caption("For accurate live valuation, use a market-data API and account for exchange, currency, fees, dividends, and split adjustments.")
