import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import yfinance as yf
import base64, json, urllib.request
from pathlib import Path

def enable_auto_refresh(sec=60):
    on = st.sidebar.toggle("🔄 Auto-Refresh 1 min", value=True, key="auto_ref_1m")
    st.sidebar.caption(f"Ultima actualizare: {pd.Timestamp.now(tz='Europe/Madrid').strftime('%H:%M:%S')}")
    if on:
        components.html(f"<script>setTimeout(function(){{window.parent.location.reload();}}, {sec * 1000});</script>", height=0, width=0)

def save_csv_permanent(df, csv_path):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    try:
        tok = st.secrets.get("GITHUB_TOKEN", "")
        repo = st.secrets.get("GITHUB_REPO", "")
        if not tok or not repo:
            return False
        base_dir = Path(__file__).resolve().parent
        rel_path = csv_path.resolve().relative_to(base_dir).as_posix()
        url = f"https://github.com{repo}/contents/{rel_path}"
        hdrs = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "User-Agent": "StreamlitApp"}
        sha = ""
        try:
            req_get = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req_get, timeout=10) as resp:
                sha = json.loads(resp.read().decode("utf-8")).get("sha", "")
        except Exception:
            pass
        b64 = base64.b64encode(csv_path.read_bytes()).decode("ascii")
        body = {"message": f"Update {rel_path}", "content": b64}
        if sha:
            body["sha"] = sha
        req_put = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=hdrs, method="PUT")
        with urllib.request.urlopen(req_put, timeout=10):
            return True
    except Exception:
        return False

def load_csv(csv_path, cols):
    if not csv_path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(csv_path).fillna("")
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df
@st.cache_data(ttl=86400, show_spinner=False)
def get_meta(t):
    try:
        info = yf.Ticker(t).info or {}
        comp = info.get("shortName") or info.get("longName") or t
        sec = info.get("sector") or ("Crypto" if "-EUR" in t or "-USD" in t else "ETF / Altele")
        curr = info.get("currency") or ("EUR" if t.endswith(".DE") or t.endswith(".MC") or "-EUR" in t else ("GBP" if t.endswith(".L") else "USD"))
        return str(comp), str(sec), str(curr).upper()
    except Exception:
        return t, "Altele", "EUR" if t.endswith(".DE") or "-EUR" in t else "USD"

@st.cache_data(ttl=60, show_spinner=False)
def _fetch_cached(tks_tuple, curr_tuple):
    prices, changes, rsim, smam = {}, {}, {}, {}
    uk_p = {"DGE.L", "BATS.L", "ABF.L"}
    clean_tks = [str(t).strip() for t in tks_tuple if str(t).strip()]
    if clean_tks:
        try:
            data = yf.download(clean_tks, period="1y", interval="1d", group_by="ticker", progress=False, threads=True)
            for t in clean_tks:
                try:
                    s = data[t]["Close"].dropna() if len(clean_tks) > 1 else data["Close"].dropna()
                    if s.empty:
                        continue
                    sc = 0.01 if t in uk_p else 1.0
                    p_cur = float(s.iloc[-1]) * sc
                    prices[t] = p_cur
                    if len(s) >= 2:
                        p_prev = float(s.iloc[-2]) * sc
                        if p_prev > 0:
                            changes[t] = (p_cur - p_prev) / p_prev * 100.0
                    if len(s) >= 15:
                        d = s.diff()
                        g = d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
                        l = (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
                        rs = g.iloc[-1] / l.iloc[-1] if l.iloc[-1] != 0 else 100.0
                        rsim[t] = 100.0 - (100.0 / (1.0 + rs))
                    if len(s) >= 200:
                        smam[t] = float(s.tail(200).mean()) * sc
                except Exception:
                    pass
        except Exception:
            pass
    fx = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27}
    for c in curr_tuple:
        cu = str(c).strip().upper()
        if not cu or cu == "USD":
            continue
        try:
            h = yf.Ticker(f"{cu}USD=X").history(period="5d")
            if not h.empty:
                fx[cu] = float(h["Close"].dropna().iloc[-1])
        except Exception:
            pass
    return prices, changes, rsim, smam, fx

def fetch_data(tickers, currencies):
    if not st.session_state.get("_ar_init"):
        st.session_state["_ar_init"] = True
        enable_auto_refresh(60)
    return _fetch_cached(tuple(tickers), tuple(currencies))

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_annual_dividends(tickers):
    res = {}
    uk_p = {"DGE.L", "BATS.L", "ABF.L"}
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=365)
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            sc = 0.01 if t in uk_p else 1.0
            divs = tk.dividends
            if divs is not None and not divs.empty:
                rec = divs[divs.index >= cutoff]
                if not rec.empty:
                    res[t] = float(rec.sum()) * sc
        except Exception:
            pass
    return res

def c_pnl(v):
    if pd.isna(v) or str(v).strip() == "": return ""
    try:
        n = float(str(v).replace("%", "").replace("+", "").replace(",", ""))
        return "color: #00e676; font-weight: bold;" if n > 0 else ("color: #ff5252; font-weight: bold;" if n < 0 else "")
    except Exception: return ""

def c_rsi(v):
    if pd.isna(v) or str(v).strip() == "": return ""
    try:
        n = float(str(v).replace("%", ""))
        return "color: #00e676; font-weight: bold;" if n <= 30 else ("color: #ff5252; font-weight: bold;" if n >= 70 else "")
    except Exception: return ""

f_price = lambda x: "" if (pd.isna(x) or x == "") else (f"{float(x):,.4f}" if abs(float(x)) < 2 else f"{float(x):,.2f}")
f_shares = lambda x: "" if (pd.isna(x) or x == "") else f"{float(x):,.6f}".rstrip("0").rstrip(".")
f_num2 = lambda x: "" if (pd.isna(x) or x == "") else f"{float(x):,.2f}"
f_rsi = lambda x: "" if (pd.isna(x) or x == "") else f"{float(x):.1f}"
f_sma = lambda x: "" if (pd.isna(x) or x == "") else f"{float(x):+.2f}%"
f_pct = lambda x: "" if (pd.isna(x) or x == "") else f"{float(x):+.2f}%"

def clean_table(df, fmt_map):
    out = df.copy()
    for col, fn in fmt_map.items():
        if col in out.columns:
            out[col] = out[col].apply(fn)
    return out

def quick_del(df, req_cols, csv_path, key_prefix):
    with st.expander("🗑️ Șterge o poziție rapid", expanded=False):
        tks = df["Ticker"].astype(str).tolist() if not df.empty else []
        if tks:
            c1, c2 = st.columns((3, 1))
            sel = c1.selectbox("Alege simbolul de șters:", tks, key=f"del_s_{key_prefix}")
            if c2.button("Șterge", key=f"del_b_{key_prefix}", type="primary"):
                ndf = df[df["Ticker"].astype(str) != sel].reindex(columns=req_cols)
                save_csv_permanent(ndf, csv_path)
                st.cache_data.clear()
                st.rerun()
