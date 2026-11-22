import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from utils import save_csv_permanent, get_meta, fetch_data, fetch_annual_dividends, fetch_fundamentals, c_pnl, c_rsi, f_price, f_rsi, f_sma, f_pct, clean_table

st.set_page_config(page_title="Watchlist", layout="wide")
BASE = Path(__file__).resolve().parent.parent
CSV_PATH, XTB_PATH = BASE / "watchlist.csv", BASE / "portfolio.csv"

st.markdown("<style>div[data-testid='stButton'] button p {font-size: 15px !important; font-weight: 700 !important;}</style>", unsafe_allow_html=True)
for k_ss in ("w_add", "w_del"):
    if k_ss not in st.session_state: st.session_state[k_ss] = False

@st.cache_data(ttl=3600, show_spinner=False)
def get_company_details(tk):
    try:
        t_obj = yf.Ticker(tk)
        hist = t_obj.history(period="5d")
        if hist is None or hist.empty:
            return False, {}
        info = t_obj.info or {}
        comp, sec, curr = get_meta(tk)
        mcap = info.get("marketCap")
        if mcap and mcap >= 1e9: mcap_s = f"{mcap/1e9:,.2f} B {curr}"
        elif mcap and mcap >= 1e6: mcap_s = f"{mcap/1e6:,.1f} M {curr}"
        else: mcap_s = "-"
        dy = info.get("dividendYield")
        dy_s = f"{dy*100:.2f}%" if isinstance(dy, (int, float)) and dy > 0 else "-"
        pe = info.get("trailingPE")
        pe_s = f"{pe:.2f}" if isinstance(pe, (int, float)) and pe > 0 else "-"
        lo52, hi52 = info.get("fiftyTwoWeekLow"), info.get("fiftyTwoWeekHigh")
        rng_s = f"{lo52:,.2f} - {hi52:,.2f} {curr}" if (lo52 and hi52) else "-"
        return True, {
            "Ticker": tk, "Name": comp, "Sector": sec, "Currency": curr,
            "Industry": info.get("industry") or "-", "Country": info.get("country") or "-",
            "MarketCap": mcap_s, "PE": pe_s, "DivYield": dy_s, "Range52": rng_s,
            "Summary": info.get("longBusinessSummary") or "Nu există descriere disponibilă."
        }
    except Exception:
        return False, {}

def render_company_card(d):
    with st.container(border=True):
        st.markdown(f"### 🏢 {d['Name']} (`{d['Ticker']}`)")
        st.caption(f"**Sector:** {d['Sector']}  |  **Industrie:** {d['Industry']}  |  **Țară:** {d['Country']}  |  **Monedă:** {d['Currency']}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Capitalizare Piață", d["MarketCap"])
        m2.metric("P/E Ratio", d["PE"])
        m3.metric("Randament Dividend", d["DivYield"])
        m4.metric("Interval 52 Săptămâni", d["Range52"])
        st.write(d["Summary"])
n1, n2, n3, n4, n5 = st.columns(5)
if n1.button("⬅️ Meniu Principal", use_container_width=True): st.switch_page("app.py")
if n2.button("📈 Portofoliu XTB", use_container_width=True): st.switch_page("pages/1_Portofoliu_XTB.py")
if n3.button("🪙 Portofoliu Kraken", use_container_width=True): st.switch_page("pages/2_Portofoliu_Kraken.py")
if n4.button("📊 XTB   Kraken", use_container_width=True): st.switch_page("pages/4_XTB_Kraken.py")
if n5.button("🔍 Analiză", use_container_width=True): st.switch_page("pages/5_Analiza.py")

if st.sidebar.button("🔄 Actualizează prețurile live"): st.cache_data.clear(); st.rerun()

if "w_msg" in st.session_state and st.session_state.w_msg:
    m_type, m_txt = st.session_state.pop("w_msg")
    if m_type == "ok": st.success(m_txt)
    else: st.error(m_txt)

df = pd.read_csv(CSV_PATH).fillna("") if CSV_PATH.exists() else pd.DataFrame(columns=["Ticker", "Company", "Sector", "Avg Price", "Currency"])
t_col = "Avg Price" if "Avg Price" in df.columns else "Target Price"
req = ["Ticker", "Company", "Sector", t_col, "Currency"]
for c in req:
    if c not in df.columns: df[c] = 0.0 if c == t_col else ""

xtb_avg = {}
if XTB_PATH.exists():
    try:
        for _, r in pd.read_csv(XTB_PATH).fillna("").iterrows():
            tk = str(r.get("Ticker", "")).strip().upper()
            bp = pd.to_numeric(r.get("Buy Price", 0.0), errors="coerce")
            if tk and pd.notna(bp) and bp > 0: xtb_avg[tk] = float(bp)
    except Exception: pass

h1, h2, h3 = st.columns((1.6, 4.8, 1.6))
if h1.button("➕ Adaugă tiker", use_container_width=True): st.session_state.w_add = not st.session_state.w_add; st.session_state.w_del = False
h2.markdown("<h1 style='text-align:center;margin:0;padding:0;'>👁️ Watchlist</h1>", unsafe_allow_html=True)
if h3.button("🗑️ Șterge tiker", use_container_width=True): st.session_state.w_del = not st.session_state.w_del; st.session_state.w_add = False

if st.session_state.w_add:
    with st.container(border=True):
        raw_tks = st.text_input("Scrie tikerul sau tikerele separate prin virgulă (ex: EPD, AAPL, VWCE.DE) și apasă Enter:", key="w_in_tks")
        typed_list = list(dict.fromkeys([x.strip().upper() for x in raw_tks.split(",") if x.strip()]))
        ex_set = set(df["Ticker"].astype(str).str.upper().tolist())
        if typed_list:
            for tk in typed_list:
                found, info_d = get_company_details(tk)
                if found:
                    if tk in ex_set:
                        st.warning(f"⚠️ **{tk}** există deja în Watchlist.")
                    else:
                        st.success(f"✅ Recunoscut: **{tk}** — {info_d['Name']} ({info_d['Sector']} • {info_d['Currency']})")
                    render_company_card(info_d)
                else:
                    st.error(f"❌ Nerecunscut pe bursă: **{tk}** (verifică simbolul sau sufixul, ex: `.DE`, `.L`, `.MC`)")

        if st.button("Salvează tikerele", type="primary"):
            if not typed_list:
                st.error("❌ Nu ai introdus niciun simbol. Scrie cel puțin un tiker și apasă pe Salvează tikerele.")
            else:
                added, errs = [], []
                for tk in typed_list:
                    if tk in ex_set:
                        errs.append(f"'{tk}' există deja în Watchlist")
                        continue
                    found, info_d = get_company_details(tk)
                    if not found:
                        errs.append(f"'{tk}' nu a fost recunoscut pe bursă")
                        continue
                    added.append({"Ticker": tk, "Company": info_d["Name"], "Sector": info_d["Sector"], t_col: xtb_avg.get(tk, 0.0), "Currency": info_d["Currency"]})
                    ex_set.add(tk)
                if added:
                    ndf = pd.concat([df.reindex(columns=req), pd.DataFrame(added)], ignore_index=True)
                    ok = save_csv_permanent(ndf, CSV_PATH)
                    tks_str = ", ".join([x["Ticker"] for x in added])
                    if ok:
                        msg = f"✅ Adăugat în Watchlist (salvat pe GitHub): {tks_str}"
                        if errs: msg += f" | ⚠️ Ignorate: {'; '.join(errs)}"
                        st.session_state.w_msg = ("ok", msg)
                    else:
                        st.session_state.w_msg = ("err", f"❌ Eroare la salvarea pe GitHub pentru: {tks_str} (verifică GITHUB_TOKEN / GITHUB_REPO în Secrets)")
                    st.session_state.w_add = False; st.cache_data.clear(); st.rerun()
                else:
                    st.error(f"❌ Nu s-a putut adăuga nimic — Motiv: {'; '.join(errs)}.")
if st.session_state.w_del:
    with st.container(border=True):
        tks_del = df["Ticker"].astype(str).tolist() if not df.empty else []
        if tks_del:
            c_d1, c_d2 = st.columns((3, 1))
            sel_d = c_d1.selectbox("Alege tikerul de șters:", tks_del, key="w_sel_del")
            if c_d2.button("Confirmă ștergerea", type="primary"):
                ndf = df[df["Ticker"].astype(str) != sel_d].reindex(columns=req)
                ok = save_csv_permanent(ndf, CSV_PATH)
                st.session_state.w_msg = ("ok" if ok else "err", f"✅ Tikerul {sel_d} a fost șters din Watchlist!" if ok else f"❌ Eroare la ștergerea tikerului {sel_d} pe GitHub!")
                st.session_state.w_del = False; st.cache_data.clear(); st.rerun()
        else:
            st.error("❌ Lista Watchlist este deja goală.")

df = df[df["Ticker"].astype(str).str.strip() != ""].copy()
tks = df["Ticker"].astype(str).unique().tolist()
acurr = sorted([x for x in df["Currency"].astype(str).unique().tolist() if x.strip()]) or ["EUR", "USD"]
prices, changes, rsim, smam, _ = fetch_data(tks, list(set(acurr + ["EUR", "USD", "GBP"])))
adiv = fetch_annual_dividends(tks)
pe_map, rng_map = fetch_fundamentals(tks)

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
df["Range_52W"] = df["Ticker"].map(rng_map).fillna("")

v = df.sort_values(by="Ticker", ascending=True)
fyoc = lambda x: "" if (pd.isna(x) or x == "" or float(x) <= 0) else f"{float(x):.2f}%"
f_avg = lambda x: "" if (pd.isna(x) or x == "" or float(x) <= 0) else f_price(x)

if not v.empty:
    cols = ["Ticker", "Company", "Currency", "Sector", "vs_Target", t_col, "Current Price", "Range_52W", "PE_Ratio", "Div_Y", "RSI", "SMA_Pct", "Day_Pct"]
    disp = v.reindex(columns=cols).copy()
    disp.columns = ["Tiker", "Companie", "Monedă", "Sector", "vs Preț mediu %", "Preț mediu", "Preț curent", "Min / Max 52 săpt.", "P/E Ratio", "Dividend AN%", "RSI (14)", "vs SMA 200 %", "Variație azi %"]
    fmt = {"Preț mediu": f_avg, "Preț curent": f_price, "Dividend AN%": fyoc, "RSI (14)": f_rsi, "vs SMA 200 %": f_sma, "vs Preț mediu %": f_pct, "Variație azi %": f_pct}
    styler = clean_table(disp, fmt).style.map(c_pnl, subset=["vs Preț mediu %", "vs SMA 200 %", "Variație azi %"]).map(c_rsi, subset=["RSI (14)"])
    st.dataframe(styler, use_container_width=True, hide_index=True, height=580, column_config={"Tiker": st.column_config.TextColumn("Tiker", pinned=True)})

    sel_info = st.selectbox("🏢 Vezi detalii despre o companie din Watchlist:", ["Alege un tiker..."] + v["Ticker"].astype(str).tolist(), key="w_info_sel")
    if sel_info != "Alege un tiker...":
        ok_i, det_i = get_company_details(sel_info)
        if ok_i: render_company_card(det_i)
