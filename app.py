import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path

st.set_page_config(page_title="Monitor Investiții", layout="wide")

XTB_CSV = Path(__file__).with_name("portfolio.csv")
KRAKEN_CSV = Path(__file__).with_name("portfolio_kraken.csv")
CLOSED_DIVS_EUR = 18.24

if "view_mode" not in st.session_state:
    st.session_state.view_mode = "home"

if st.session_state.view_mode == "home":
    st.write("")
    st.write("")
    st.title("💼 Monitor Investiții")
    st.write("Alege portofoliul pe care dorești să îl accesezi:")
    st.write("")
    c1, c2, _ = st.columns([1, 1, 2])
    if c1.button("📈 Portofoliu XTB", use_container_width=True, type="primary"):
        st.session_state.view_mode = "xtb"
        st.rerun()
    if c2.button("🪙 Portofoliu Kraken", use_container_width=True, type="primary"):
        st.session_state.view_mode = "kraken"
        st.rerun()
    st.stop()

@st.cache_data
def load_data(csv_path):
    if not csv_path.exists():
        return pd.DataFrame(columns=["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"])
    return pd.read_csv(csv_path)

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

def c_pnl(v):
    if pd.isna(v): return ""
    return "color: #00e676; font-weight: bold;" if v > 0 else ("color: #ff5252; font-weight: bold;" if v < 0 else "")

def c_rsi(v):
    if pd.isna(v): return ""
    return "color: #00e676; font-weight: bold;" if v <= 30 else ("color: #ff5252; font-weight: bold;" if v >= 70 else "")

def f_price(v):
    if pd.isna(v): return "-"
    return f"{v:,.4f}" if abs(v) < 2 else f"{v:,.2f}"

def f_shares(v):
    if pd.isna(v): return "-"
    s = f"{v:,.6f}".rstrip("0").rstrip(".")
    return s if s else "0"

def f_num2(v):
    return "-" if pd.isna(v) else f"{v:,.2f}"

def f_rsi(v):
    return "-" if pd.isna(v) else f"{v:.1f}"

def f_sma(v):
    return "-" if pd.isna(v) else f"{v:+.2f}%"

def f_pct(v):
    return "-" if pd.isna(v) else f"{v:.2f}%"

is_kraken = (st.session_state.view_mode == "kraken")

if st.button("⬅️ Înapoi la Meniul Principal"):
    st.session_state.view_mode = "home"
    st.rerun()

st.title("🪙 Portofoliu Kraken" if is_kraken else "📈 Portofoliu XTB")
csv_path = KRAKEN_CSV if is_kraken else XTB_CSV
df = load_data(csv_path).copy()
if "Dividends EUR" not in df.columns: df["Dividends EUR"] = 0.0
req = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "Current Price", "Currency", "Dividends EUR"]

if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.cache_data.clear()
    st.rerun()

tickers = df["Ticker"].dropna().unique().tolist()
all_curr = sorted(df["Currency"].dropna().unique().tolist()) or ["EUR", "USD"]
prices, rsi_m, sma_m, fx = fetch_data(tickers, list(set(all_curr + ["EUR", "USD", "GBP"])))

for c in ["Shares", "Buy Price", "Current Price", "Dividends EUR"]:
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)

df["Current Price"] = np.where(df["Ticker"].map(prices).notna(), df["Ticker"].map(prices), df["Current Price"]).astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsi_m), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(sma_m), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current Price"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)

t_curr = st.sidebar.selectbox("Monedă raportare (Total)", ["EUR", "USD", "GBP"])
c_filt = st.sidebar.selectbox("Filtrare poziții după monedă", ["Toate (Consolidat)"] + all_curr)
sort_by = st.sidebar.selectbox("Ordonează tabelul după", ["Valoare piață", "Profit Total", "Dividende", "Randament %", "RSI (Crescător)", "vs SMA 200 %", "Tiker"])

t_rate = fx.get(t_curr, 1.0)
eur_rate = fx.get("EUR", 1.08) / t_rate
mult = pd.to_numeric(df["Currency"].map(fx), errors="coerce").fillna(1.0).astype(float) / t_rate

df["Inv"] = df["Shares"] * df["Buy Price"] * mult
df["Mkt"] = df["Shares"] * df["Current Price"] * mult
df["Div"] = df["Dividends EUR"] * eur_rate
df["PnL"] = (df["Mkt"] - df["Inv"]) + df["Div"]
df["Ret"] = np.where(df["Inv"] != 0, df["PnL"] / df["Inv"] * 100, 0.0).astype(float)

view = df.copy() if c_filt == "Toate (Consolidat)" else df[df["Currency"] == c_filt].copy()
extra_div = (CLOSED_DIVS_EUR * eur_rate) if (not is_kraken and c_filt == "Toate (Consolidat)") else 0.0
tot_mkt = view["Mkt"].sum()
view["Wgt"] = np.where(tot_mkt != 0, view["Mkt"] / tot_mkt * 100, 0.0).astype(float)

s_map = dict([("Valoare piață", ("Mkt", False)), ("Profit Total", ("PnL", False)), ("Dividende", ("Div", False)), ("Randament %", ("Ret", False)), ("RSI (Crescător)", ("RSI", True)), ("vs SMA 200 %", ("SMA_Pct", True)), ("Tiker", ("Ticker", True))])
col_s, asc_s = s_map[sort_by]
view = view.sort_values(by=col_s, ascending=asc_s, na_position="last")

st.sidebar.info(f"Fișier: `{csv_path.name}`\n\nPrețuri live: {len(prices)}/{len(tickers)}\n\n1 EUR = {fx.get('EUR', 1.08):.4f} USD")

inv_s, mkt_s, div_s = float(view["Inv"].sum()), float(view["Mkt"].sum()), float(view["Div"].sum() + extra_div)
gross_profit = float(view[view["PnL"] > 0]["PnL"].sum() + extra_div)
gross_loss = float(view[view["PnL"] < 0]["PnL"].sum())

if is_kraken:
    c1, c2, c3, c5, c6 = st.columns(5)
    c1.metric("Poziții", f"{len(view)}")
    c2.metric("Capital investit", f"{inv_s:,.2f} {t_curr}")
    c3.metric("Valoare piață", f"{mkt_s:,.2f} {t_curr}")
else:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Poziții", f"{len(view)}")
    c2.metric("Capital investit", f"{inv_s:,.2f} {t_curr}")
    c3.metric("Valoare piață", f"{mkt_s:,.2f} {t_curr}")
    c4.metric("Dividende nete", f"{div_s:,.2f} {t_curr}")

c5.metric("Profit Total (Poz.)", f"+{gross_profit:,.2f} {t_curr}", f"{len(view[view['PnL'] > 0])} pe plus", delta_color="normal")
c6.metric("Pierdere Totală (Neg.)", f"{gross_loss:,.2f} {t_curr}", f"-{len(view[view['PnL'] < 0])} pe minus", delta_color="normal")

st.subheader(f"Portofoliu (Valori convertite în {t_curr})")

if view.empty:
    st.info(f"Nu există poziții în {csv_path.name}. Adaugă-le mai jos.")
else:
    cols = ["Ticker", "Company", "Sector", "Shares", "Buy Price", "RSI", "SMA_Pct", "Current Price", "Currency", "Inv", "Mkt"] + ([] if is_kraken else ["Div"]) + ["PnL", "Ret", "Wgt"]
    disp = view[cols].copy()
    disp.columns = ["Tiker", "Companie", "Sector", "Acțiuni", "Preț mediu", "RSI (14)", "vs SMA 200 %", "Preț curent", "Monedă", "Valoare investită", "Valoare piață"] + ([] if is_kraken else ["Dividende"]) + ["Profit / Pierdere", "Randament %", "Pondere %"]
    fmt = dict([("Acțiuni", f_shares), ("Preț mediu", f_price), ("RSI (14)", f_rsi), ("vs SMA 200 %", f_sma), ("Preț curent", f_price), ("Valoare investită", f_num2), ("Valoare piață", f_num2), ("Profit / Pierdere", f_num2), ("Randament %", f_pct), ("Pondere %", f_pct)])
    if not is_kraken: fmt["Dividende"] = f_num2
    styler = disp.style.map(c_pnl, subset=["Profit / Pierdere", "Randament %", "vs SMA 200 %"]).map(c_rsi, subset=["RSI (14)"]).format(fmt)
    st.dataframe(styler, use_container_width=True, hide_index=True, height=550, column_config=dict(Tiker=st.column_config.TextColumn("Tiker", pinned=True)))
    l1, r1 = st.columns(2)
    with l1:
        st.subheader(f"Profit / Pierdere Total ({t_curr})")
        st.bar_chart(view.set_index("Ticker")[["PnL"]].assign(Color=np.where(view["PnL"] >= 0, "#00e676", "#ff5252")), y="PnL", color="Color")
    with r1:
        st.subheader(f"Valoare de piață ({t_curr})")
        st.bar_chart(view.set_index("Ticker")["Mkt"], color="#29b6f6")

st.subheader(f"Editare poziții ({csv_path.name})")
edited = st.data_editor(view[req], num_rows="dynamic", use_container_width=True, key=f"ed_{is_kraken}")
if st.button(f"Salvează modificările în {csv_path.name}"):
    up = edited if c_filt == "Toate (Consolidat)" else pd.concat([df[df["Currency"] != c_filt][req], edited], ignore_index=True)
    up.to_csv(csv_path, index=False)
    st.cache_data.clear()
    st.success(f"Salvat în {csv_path.name}! Reîncarcă pagina.")
