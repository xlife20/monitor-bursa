import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import json, re, urllib.request, urllib.parse
from pathlib import Path
from utils import get_meta, fetch_data, fetch_annual_dividends, fetch_fundamentals, c_pnl, c_rsi, f_price, f_rsi, f_sma, f_pct, clean_table

st.set_page_config(page_title="Analiză", layout="wide")
BASE = Path(__file__).resolve().parent.parent
CSV_PATH, XTB_PATH = BASE / "watchlist.csv", BASE / "portfolio.csv"

st.markdown("<style>div[data-testid='stButton'] button p {font-size: 15px !important; font-weight: 700 !important;}</style>", unsafe_allow_html=True)
if "an_flt" not in st.session_state: st.session_state.an_flt = "rsi"

def _tr_chunk(ch):
    q = urllib.parse.quote(ch)
    for base_u in ("https://lingva.ml", "https://lunar.icu"):
        try:
            req = urllib.request.Request(base_u + q, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=7) as r:
                t = json.loads(r.read().decode("utf-8")).get("translation", "").strip()
                if t and t.lower() != ch.lower():
                    return t
        except Exception:
            pass
    try:
        from deep_translator import GoogleTranslator
        t = (GoogleTranslator(source="en", target="ro").translate(ch) or "").strip()
        if t and t.lower() != ch.lower():
            return t
    except Exception:
        pass
    try:
        req = urllib.request.Request(f"https://translated.net{q}&langpair=en|ro&de=monitorbursa@gmail.com", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=7) as r:
            t = json.loads(r.read().decode("utf-8")).get("responseData", {}).get("translatedText", "").strip()
            if t and "MYMEMORY" not in t.upper() and t.lower() != ch.lower():
                return t
    except Exception:
        pass
    return ch

def tr_ro(txt):
    s = str(txt or "").strip()
    if not s or s == "-": return s
    if "tr_mem" not in st.session_state: st.session_state.tr_mem = {}
    if s in st.session_state.tr_mem: return st.session_state.tr_mem[s]
    chunks = [s[i:i+450] for i in range(0, min(len(s), 2250), 450)]
    res = " ".join([_tr_chunk(c) for c in chunks]).strip()
    if res and res != s:
        st.session_state.tr_mem[s] = res
    return res or s
@st.cache_data(ttl=3600, show_spinner=False)
def get_company_raw(tk, fallback_name="", fallback_sec="", fallback_curr="USD", lo52=None, hi52=None, pe_val="-"):
    t_obj = yf.Ticker(tk)
    info = {}
    try: info = t_obj.info or {}
    except Exception: info = {}
    comp = info.get("shortName") or info.get("longName") or fallback_name or tk
    sec = info.get("sector") or fallback_sec or "-"
    curr = (info.get("currency") or fallback_curr or "USD").upper()
    ind = info.get("industry") or "-"
    ctry = info.get("country") or "-"
    raw_sum = info.get("longBusinessSummary") or ""
    mcap = info.get("marketCap")
    mcap_s = f"{mcap/1e9:,.2f} mld. {curr}" if (mcap and mcap >= 1e9) else (f"{mcap/1e6:,.1f} mil. {curr}" if (mcap and mcap >= 1e6) else "-")
    dy = info.get("dividendYield")
    if isinstance(dy, (int, float)) and dy > 0:
        dy_val = dy if dy >= 0.1 else dy * 100.0
        dy_s = f"{dy_val:.2f}%"
    else:
        dy_s = "-"
    pe = info.get("trailingPE")
    pe_s = f"{pe:.2f}" if isinstance(pe, (int, float)) and pe > 0 else (pe_val or "-")

    if not raw_sum and "." not in tk and "-" not in tk:
        try:
            req = urllib.request.Request(f"https://finviz.com{tk}", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as r:
                html = r.read().decode("utf-8", errors="ignore")
                m_sum = re.search(r'class="fullview-profile"[^>]*>(.*?)</td>', html, re.S)
                if m_sum: raw_sum = re.sub(r'<[^>]+>', '', m_sum.group(1)).strip()
                m_cap = re.search(r'>Market Cap</td><td[^>]*><b>([^<]+)</b>', html)
                if m_cap and mcap_s == "-": mcap_s = m_cap.group(1)
                m_sec = re.findall(r'class="tab-link"[^>]*>([^<]+)</a>', html)
                it_s = iter(m_sec)
                s1, s2, s3 = next(it_s, ""), next(it_s, ""), next(it_s, "")
                if sec == "-" and s1: sec = s1
                if ind == "-" and s2: ind = s2
                if ctry == "-" and s3: ctry = s3
        except Exception: pass

    rng_s = f"{lo52:,.2f} - {hi52:,.2f} {curr}" if (pd.notna(lo52) and pd.notna(hi52)) else "-"
    return {
        "Ticker": tk, "Name": comp, "Sector": sec, "Currency": curr,
        "Industry": ind, "Country": ctry,
        "MarketCap": mcap_s, "PE": pe_s, "DivYield": dy_s, "Range52": rng_s,
        "Summary": raw_sum or "No description available for this instrument."
    }

def render_company_card(raw_d):
    with st.container(border=True):
        st.markdown(f"### 🏢 {raw_d['Name']} (`{raw_d['Ticker']}`)")
        st.caption(f"**Sector:** {tr_ro(raw_d['Sector'])}  |  **Industrie:** {tr_ro(raw_d['Industry'])}  |  **Țară:** {tr_ro(raw_d['Country'])}  |  **Monedă:** {raw_d['Currency']}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Capitalizare Piață", raw_d["MarketCap"])
        m2.metric("P/E Ratio", raw_d["PE"])
        m3.metric("Randament Dividend", raw_d["DivYield"])
        m4.metric("Min / Max 52 Săptămâni", raw_d["Range52"])
        st.write(tr_ro(raw_d["Summary"]))
n1, n2, n3, n4, n5 = st.columns(5)
if n1.button("⬅️ Meniu Principal", use_container_width=True): st.switch_page("app.py")
if n2.button("📈 Portofoliu XTB", use_container_width=True): st.switch_page("pages/1_Portofoliu_XTB.py")
if n3.button("🪙 Portofoliu Kraken", use_container_width=True): st.switch_page("pages/2_Portofoliu_Kraken.py")
if n4.button("👁️ Watchlist", use_container_width=True): st.switch_page("pages/3_Urmareste.py")
if n5.button("📊 XTB   Kraken", use_container_width=True): st.switch_page("pages/4_XTB_Kraken.py")

if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.session_state.tr_mem = {}
    st.cache_data.clear()
    st.rerun()

st.markdown("<h1 style='text-align:center;margin-top:4px;margin-bottom:0;'>🔍 Analiză</h1>", unsafe_allow_html=True)
st.markdown("<br><br>", unsafe_allow_html=True)

_, b_rsi, b_sma, _ = st.columns((2.5, 1.5, 1.5, 2.5))
if b_rsi.button("📉 RSI < 30", use_container_width=True): st.session_state.an_flt = "rsi"
if b_sma.button("📊 SMA200 <", use_container_width=True): st.session_state.an_flt = "sma"

df = pd.read_csv(CSV_PATH).fillna("") if CSV_PATH.exists() else pd.DataFrame(columns=["Ticker", "Company", "Sector", "Avg Price", "Currency"])
t_col = "Avg Price" if "Avg Price" in df.columns else "Target Price"
for c in ("Ticker", "Company", "Sector", t_col, "Currency"):
    if c not in df.columns: df[c] = 0.0 if c == t_col else ""

xtb_avg = {}
if XTB_PATH.exists():
    try:
        for _, r in pd.read_csv(XTB_PATH).fillna("").iterrows():
            tk = str(r.get("Ticker", "")).strip().upper()
            bp = pd.to_numeric(r.get("Buy Price", 0.0), errors="coerce")
            if tk and pd.notna(bp) and bp > 0: xtb_avg[tk] = float(bp)
    except Exception: pass

df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
tks = df["Ticker"].astype(str).unique().tolist()
acurr = sorted([x for x in df["Currency"].astype(str).unique().tolist() if x.strip()]) or ["EUR", "USD"]
prices, changes, rsim, smam, _ = fetch_data(tks, list(set(acurr + ["EUR", "USD", "GBP"])))
adiv = fetch_annual_dividends(tks)
pe_map, lo_map, hi_map = fetch_fundamentals(tks)

df[t_col] = pd.to_numeric(df.get(t_col, 0.0), errors="coerce").fillna(0.0).astype(float)
df["XTB_P"] = df["Ticker"].astype(str).str.upper().map(xtb_avg)
df[t_col] = np.where(df["XTB_P"].notna(), df["XTB_P"], df[t_col]).astype(float)
df["Current Price"] = pd.to_numeric(df["Ticker"].map(prices), errors="coerce").astype(float)
df["Day_Pct"] = pd.to_numeric(df["Ticker"].map(changes), errors="coerce").astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsim), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(smam), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current Price"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)
df["vs_Target"] = np.where((df[t_col] > 0) & df["Current Price"].notna(), (df["Current Price"] - df[t_col]) / df[t_col] * 100, np.nan).astype(float)
df["Div_Sh"] = pd.to_numeric(df["Ticker"].map(adiv), errors="coerce").fillna(0.0).astype(float)
df["Div_Y"] = np.where((df["Current Price"] > 0) & (df["Div_Sh"] > 0), (df["Div_Sh"] / df["Current Price"]) * 100, np.nan).astype(float)
df["PE_Ratio"] = df["Ticker"].map(pe_map).fillna("")
df["Low_52W"] = pd.to_numeric(df["Ticker"].map(lo_map), errors="coerce")
df["High_52W"] = pd.to_numeric(df["Ticker"].map(hi_map), errors="coerce")

fyoc = lambda x: "" if (pd.isna(x) or x == "" or float(x) <= 0) else f"{float(x):.2f}%"
f_avg = lambda x: "" if (pd.isna(x) or x == "" or float(x) <= 0) else f_price(x)

if st.session_state.an_flt == "sma":
    sub = df[df["SMA_Pct"].notna() & (df["SMA_Pct"] < 0)].sort_values(by="SMA_Pct", ascending=True).head(5).reset_index(drop=True)
    st.subheader("📊 Top 5 Acțiuni sub SMA 200 (De la cea mai mare scădere)")
else:
    sub = df[df["RSI"].notna() & (df["RSI"] < 30)].sort_values(by="RSI", ascending=True).head(5).reset_index(drop=True)
    st.subheader("📉 Top 5 Acțiuni cu RSI < 30 (Crescător)")

clicked_tk = None
if sub.empty:
    st.info("Nicio acțiune nu îndeplinește criteriul selectat în acest moment.")
else:
    cols = ["Ticker", "Company", "Currency", "Sector", "vs_Target", t_col, "Current Price", "Low_52W", "High_52W", "PE_Ratio", "Div_Y", "RSI", "SMA_Pct", "Day_Pct"]
    disp = sub.reindex(columns=cols).copy()
    disp.columns = ["Tiker", "Companie", "Monedă", "Sector", "vs Preț mediu %", "Preț mediu", "Preț curent", "Min 52 săpt.", "Max 52 săpt.", "P/E Ratio", "Dividend AN%", "RSI (14)", "vs SMA 200 %", "Variație azi %"]
    fmt = {"Preț mediu": f_avg, "Preț curent": f_price, "Min 52 săpt.": f_price, "Max 52 săpt.": f_price, "Dividend AN%": fyoc, "RSI (14)": f_rsi, "vs SMA 200 %": f_sma, "vs Preț mediu %": f_pct, "Variație azi %": f_pct}
    styler = clean_table(disp, fmt).style.map(c_pnl, subset=["vs Preț mediu %", "vs SMA 200 %", "Variație azi %"]).map(c_rsi, subset=["RSI (14)"])
    ev = st.dataframe(styler, use_container_width=True, hide_index=True, height=230, on_select="rerun", selection_mode="single-row", column_config={"Tiker": st.column_config.TextColumn("Tiker", pinned=True)})
    if ev and ev.selection and ev.selection.rows:
        r_idx = next(iter(ev.selection.rows))
        if r_idx < len(sub):
            clicked_tk = str(sub.iloc[r_idx]["Ticker"])

st.divider()
v_sorted = df.sort_values(by="Ticker", ascending=True)
all_tks = v_sorted["Ticker"].astype(str).tolist()
if all_tks:
    opts = ["Alege un tiker..."] + all_tks
    def_idx = opts.index(clicked_tk) if (clicked_tk and clicked_tk in opts) else 0
    sel_info = st.selectbox("🏢 Detalii companie (dă clic pe un rând din tabel sau alege din listă):", opts, index=def_idx, key="an_info_sel")
    target_tk = clicked_tk or (sel_info if sel_info != "Alege un tiker..." else None)
    if target_tk:
        _, r_m = next(v_sorted[v_sorted["Ticker"].astype(str) == target_tk].iterrows())
        det_raw = get_company_raw(target_tk, str(r_m["Company"]), str(r_m["Sector"]), str(r_m["Currency"]), r_m["Low_52W"], r_m["High_52W"], str(r_m["PE_Ratio"] or "-"))
        render_company_card(det_raw)
