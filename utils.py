import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

@st.cache_data
def load_csv(csv_path, cols):
    if not csv_path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(csv_path)
    return df.fillna("")

def get_meta(symbol):
    comp, sec, curr = symbol, "Acțiuni", "USD"
    if symbol.endswith(("-EUR", ".DE", ".MI", ".MC")): curr = "EUR"
    elif symbol.endswith(".L"): curr = "GBP"
    if "-USD" in symbol or "-EUR" in symbol: sec = "Crypto"
    try:
        res = yf.Search(symbol, max_results=1).quotes
        if res:
            q = res[0]
            comp = q.get("shortname") or q.get("longname") or comp
            sec = q.get("sector") or ("ETF" if q.get("quoteType") == "ETF" else sec)
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

@st.cache_data(ttl=3600)
def fetch_annual_dividends(tickers):
    div_rate = dict()
    uk = ["DGE.L", "BATS.L", "ABF.L"]
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=365)
    for t in tickers:
        try:
            divs = yf.Ticker(t).dividends
            if divs is not None and not divs.empty:
                recent = divs[divs.index >= cutoff]
                if not recent.empty:
                    sc = 0.01 if t in uk else 1.0
                    div_rate[t] = float(recent.sum()) * sc
        except Exception:
            pass
    return div_rate

def c_pnl(v):
    if pd.isna(v) or str(v).strip() == "": return ""
    try:
        num = float(str(v).replace(",", "").replace("%", "").replace("+", ""))
        return "color: #00e676; font-weight: bold;" if num > 0 else ("color: #ff5252; font-weight: bold;" if num < 0 else "")
    except:
        return ""

def c_rsi(v):
    if pd.isna(v) or str(v).strip() == "": return ""
    try:
        num = float(str(v).replace("%", ""))
        return "color: #00e676; font-weight: bold;" if num <= 30 else ("color: #ff5252; font-weight: bold;" if num >= 70 else "")
    except:
        return ""

def f_price(v):
    return "" if (pd.isna(v) or v == "") else (f"{float(v):,.4f}" if abs(float(v)) < 2 else f"{float(v):,.2f}")

def f_shares(v):
    if pd.isna(v) or v == "": return ""
    s = f"{float(v):,.6f}".rstrip("0").rstrip(".")
    return s if s else "0"

def f_num2(v): return "" if (pd.isna(v) or v == "") else f"{float(v):,.2f}"
def f_rsi(v): return "" if (pd.isna(v) or v == "") else f"{float(v):.1f}%"
def f_sma(v): return "" if (pd.isna(v) or v == "") else f"{float(v):+.2f}%"
def f_pct(v): return "" if (pd.isna(v) or v == "") else f"{float(v):.2f}%"

def clean_table(df, fmt_dict):
    out = df.copy()
    for col, func in fmt_dict.items():
        if col in out.columns:
            out[col] = out[col].apply(func)
    return out.fillna("")

def quick_del(df_orig, cols, csv_path, kp):
    if df_orig.empty: return
    with st.expander("🗑️ Șterge rapid tikere din listă", expanded=False):
        opts = [x for x in df_orig["Ticker"].dropna().unique().tolist() if str(x).strip() != ""]
        to_del = st.multiselect("Selectează tikerele de șters:", opts, key=f"ds_{kp}")
        if st.button("Șterge selectate", key=f"db_{kp}") and to_del:
            df_orig[~df_orig["Ticker"].isin(to_del)][cols].to_csv(csv_path, index=False)
            st.cache_data.clear()
            st.rerun()
