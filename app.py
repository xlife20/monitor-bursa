import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import urllib.request
import json
from pathlib import Path

st.set_page_config(page_title="Monitor Investiții", layout="wide")

XTB_CSV = Path(__file__).with_name("portfolio.csv")
KRAKEN_CSV = Path(__file__).with_name("portfolio_kraken.csv")
WATCH_CSV = Path(__file__).with_name("watchlist.csv")
CLOSED_DIVS_EUR = 18.24

if "view_mode" not in st.session_state:
    st.session_state.view_mode = "home"

if st.session_state.view_mode == "home":
    st.write("")
    st.write("")
    st.title("💼 Monitor Investiții")
    st.write("Alege secțiunea pe care dorești să o accesezi:")
    st.write("")
    c1, c2, c3, _ = st.columns([1.2, 1.2, 1.2, 1.4])
    if c1.button("📈 Portofoliu XTB", use_container_width=True, type="primary"):
        st.session_state.view_mode = "xtb"
        st.rerun()
    if c2.button("🪙 Portofoliu Kraken", use_container_width=True, type="primary"):
        st.session_state.view_mode = "kraken"
        st.rerun()
    if c3.button("👁️ Urmărește", use_container_width=True, type="primary"):
        st.session_state.view_mode = "watch"
        st.rerun()
    st.stop()

@st.cache_data
def load_data(csv_path, cols):
    if not csv_path.exists():
        return pd.DataFrame(columns=cols)
    return pd.read_csv(csv_path)

def get_ticker_meta(symbol):
    comp, sec, curr = symbol, "Altele", "USD"
    if symbol.endswith("-EUR") or symbol.endswith(".DE") or symbol.endswith(".MI") or symbol.endswith(".MC"):
        curr = "EUR"
    elif symbol.endswith(".L"):
        curr = "GBP"
    if "-USD" in symbol or "-EUR" in symbol:
        sec = "Crypto"
    try:
        url = f"https://yahoo.com{symbol}&quotesCount=1&newsCount=0"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            quotes = data.get("quotes", [])
            if quotes:
                q = quotes
                comp = q.get("shortname") or q.get("longname") or comp
                if q.get("sector"):
                    sec = q.get("sector")
                elif q.get("quoteType") == "ETF":
                    sec = "ETF"
                elif q.get("quoteType") == "CRYPTOCURRENCY":
                    sec = "Crypto"
    except Exception:
        pass
    try:
        fi = yf.Ticker(symbol).fast_info
        if fi and fi.get("currency"):
            c_raw = str(fi["currency"]).upper()
            curr = "GBP" if c_raw == "GBP" else c_raw
    except Exception:
        pass
    return comp, sec, curr

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
    prices, prev_p, rsi_m, sma_m = dict(), dict(), dict(), dict()
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
                    prev_p[t] = float(s.iloc[-2]) * sc if len(s) >= 2 else prices[t]
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
    return prices, prev_p, rsi_m, sma_m, fx

def c_pnl(v):
    if pd.isna(v): return ""
    return "color: #00e676; font-weight: bold;" if v > 0 else ("color: #ff5252; font-weight: bold;" if v < 0 else "")

def c_target(v):
    if pd.isna(v): return ""
    return "color: #00e676; font-weight: bold;" if v <= 0 else "color: #ffab40;"

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

def quick_delete_widget(df_orig, cols, csv_path, key_prefix):
    if df_orig.empty:
        return
    with st.expander("🗑️ Șterge rapid tikere din listă", expanded=False):
        options = df_orig["Ticker"].dropna().unique().tolist()
        to_del = st.multiselect("Selectează unul sau mai multe tikere de șters:", options, key=f"del_sel_{key_prefix}")
        if st.button("Șterge tikerele selectate", type="secondary", key=f"del_btn_{key_prefix}"):
            if to_del:
                cleaned = df_orig[~df_orig["Ticker"].isin(to_del)][cols]
                cleaned.to_csv(csv_path, index=False)
                st.cache_data.clear()
                st.success(f"S-au șters: {', '.join(to_del)}")
                st.rerun()
            else:
                st.warning("Selectează cel puțin un tiker din listă.")

if st.button("⬅️ Înapoi la Meniul Principal"):
    st.session_state.view_mode = "home"
    st.rerun()

if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.cache_data.clear()
    st.rerun()

if st.session_state.view_mode == "watch":
    st.title("👁️ Listă de Urmărire (Watchlist)")
    w_cols = ["Ticker", "Company", "Sector", "Target Price", "Currency"]
    df = load_data(WATCH_CSV, w_cols).copy()

    with st.expander("➕ Adaugă rapid mai multe tikere odată", expanded=False):
        raw_tickers = st.text_area("Introdu simbolurile Yahoo Finance separate prin virgulă, spațiu sau pe rânduri noi:", placeholder="Ex: TSLA, KO, O, NVDA, NKE, BTC-EUR, RHM.DE, BATS.L", height=80)
        if st.button("Adaugă în listă", type="primary"):
            new_list = [t.strip().upper() for t in raw_tickers.replace(",", " ").replace("\n", " ").split(" ") if t.strip()]
            existing = set(df["Ticker"].astype(str).str.upper().tolist())
            to_add = [t for t in dict.fromkeys(new_list) if t not in existing]
            if to_add:
                new_rows = []
                with st.spinner("Se preiau numele companiilor și sectoarele..."):
                    for t in to_add:
                        comp, sec, curr = get_ticker_meta(t)
                        new_rows.append(dict(Ticker=t, Company=comp, Sector=sec, Target_Price=0.0, Currency=curr))
                add_df = pd.DataFrame(new_rows).rename(columns=dict(Target_Price="Target Price"))
                df = pd.concat([df, add_df], ignore_index=True)
                df.to_csv(WATCH_CSV, index=False)
                st.cache_data.clear()
                st.success(f"S-au adăugat {len(to_add)} tikere noi!")
                st.rerun()
            else:
                st.warning("Nu s-au găsit tikere noi de adăugat (sau există deja în listă).")

    quick_delete_widget(df, w_cols, WATCH_CSV, "watch")

    if not df.empty and st.button("🔄 Actualizează automat numele și sectoarele lipsă"):
        with st.spinner("Se actualizează denumirile companiilor..."):
            for idx, r in df.iterrows():
                if str(r["Sector"]) in ["Watchlist", "Altele", "nan", ""] or str(r["Company"]) == str(r["Ticker"]):
                    comp, sec, curr = get_ticker_meta(str(r["Ticker"]))
                    df.at[idx, "Company"] = comp
                    df.at[idx, "Sector"] = sec
                    df.at[idx, "Currency"] = curr
            df[w_cols].to_csv(WATCH_CSV, index=False)
            st.cache_data.clear()
            st.rerun()

    tickers = df["Ticker"].dropna().unique().tolist()
    prices, prev_p, rsi_m, sma_m, _ = fetch_data(tickers, ["EUR", "USD", "GBP"])
    df["Target Price"] = pd.to_numeric(df["Target Price"], errors="coerce").fillna(0.0).astype(float)
    df["Current"] = pd.to_numeric(df["Ticker"].map(prices), errors="coerce").astype(float)
    df["Prev"] = pd.to_numeric(df["Ticker"].map(prev_p), errors="coerce").astype(float)
    df["Day_Pct"] = np.where(df["Prev"].notna() & (df["Prev"] != 0), (df["Current"] - df["Prev"]) / df["Prev"] * 100, np.nan).astype(float)
    df["Diff_Target"] = np.where((df["Target Price"] > 0) & df["Current"].notna(), (df["Current"] - df["Target Price"]) / df["Target Price"] * 100, np.nan).astype(float)
    df["RSI"] = pd.to_numeric(df["Ticker"].map(rsi_m), errors="coerce").astype(float)
    df["SMA200"] = pd.to_numeric(df["Ticker"].map(sma_m), errors="coerce").astype(float)
    df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)
    st.sidebar.info(f"Fișier: `{WATCH_CSV.name}`\n\nSimboluri urmărite: {len(df)}")
