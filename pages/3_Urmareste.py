import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from utils import load_csv, save_csv_permanent, get_meta, fetch_data, c_pnl, c_rsi, f_price, f_rsi, f_sma, clean_table, quick_del

st.set_page_config(page_title="Urmărește", layout="wide")
CSV_PATH = Path(__file__).resolve().parent.parent / "watchlist.csv"
XTB_CSV = Path(__file__).resolve().parent.parent / "portfolio.csv"

@st.cache_data(ttl=1800)
def get_auto_div_yields(tickers):
    res_pct = dict()
    uk = ["DGE.L", "BATS.L", "ABF.L"]
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=365)
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            sc = 0.01 if t in uk else 1.0
            p_now = float(tk.fast_info.get("lastPrice") or 0)
            if p_now <= 0:
                continue
            p_real = p_now * sc
            info = tk.info or {}
            dr = float(info.get("dividendRate") or 0) * sc
            if dr > 0 and (dr / p_real) <= 0.12:
                res_pct[t] = (dr / p_real) * 100.0
                continue
            divs = tk.dividends
            if divs is not None and not divs.empty:
                recent = divs[divs.index >= cutoff]
                if not recent.empty:
                    vals = recent.values * sc
                    vals = vals[(vals / p_real) <= 0.10]
                    ann_div = float(np.sum(vals))
                    if ann_div > 0:
                        res_pct[t] = (ann_div / p_real) * 100.0
        except Exception:
            pass
    return res_pct

if st.button("⬅️ Meniu Principal"):
    st.switch_page("app.py")
if st.sidebar.button("🔄 Actualizează prețurile live"):
    st.cache_data.clear()
    st.rerun()

st.title("👁️ Listă de Urmărire (Watchlist)")
w_cols = ["Ticker", "Company", "Currency", "Sector"]
df = load_csv(CSV_PATH, w_cols).copy()

for c in w_cols:
    if c not in df.columns:
        df[c] = ""

xtb_df = load_csv(XTB_CSV, ["Ticker", "Company", "Currency", "Sector", "Buy Price"]).copy()
avg_price_map = dict()
if not xtb_df.empty and "Buy Price" in xtb_df.columns:
    xtb_df["Buy Price"] = pd.to_numeric(xtb_df["Buy Price"], errors="coerce")
    avg_price_map = xtb_df.dropna(subset=["Ticker", "Buy Price"]).set_index("Ticker")["Buy Price"].to_dict()

with st.expander("➕ Adaugă rapid mai multe tikere odată", expanded=False):
    raw = st.text_area("Introdu simbolurile separate prin virgulă sau spațiu:", placeholder="Ex: TSLA, KO, O, NVDA, NKE, BTC-EUR", height=70)
    if st.button("Adaugă în listă", type="primary"):
        new_l = [t.strip().upper() for t in raw.replace(",", " ").replace("\n", " ").split(" ") if t.strip()]
        ex = set(df["Ticker"].astype(str).str.upper().tolist())
        to_add = [t for t in dict.fromkeys(new_l) if t not in ex]
        if to_add:
            rows = []
            for t in to_add:
                comp, sec, curr = get_meta(t)
                rows.append(dict(Ticker=t, Company=comp, Currency=curr, Sector=sec))
            add_df = pd.DataFrame(rows)
            save_csv_permanent(pd.concat([df[w_cols], add_df], ignore_index=True), CSV_PATH)
            st.cache_data.clear()
            st.rerun()

quick_del(df, w_cols, CSV_PATH, "watch")

tickers = [x for x in df["Ticker"].dropna().unique().tolist() if str(x).strip() != ""]
all_curr = sorted([x for x in df["Currency"].dropna().unique().tolist() if str(x).strip() != ""]) or ["EUR", "USD"]
prices, _, rsi_m, sma_m, _ = fetch_data(tickers, ["EUR", "USD", "GBP"])
auto_yield_map = get_auto_div_yields(tickers)

df["Avg_Price"] = pd.to_numeric(df["Ticker"].map(avg_price_map), errors="coerce").astype(float)
df["Current"] = pd.to_numeric(df["Ticker"].map(prices), errors="coerce").astype(float)
df["Diff_Avg_Pct"] = np.where((df["Avg_Price"] > 0) & df["Current"].notna(), (df["Current"] - df["Avg_Price"]) / df["Avg_Price"] * 100, np.nan).astype(float)
df["Div_Yield"] = pd.to_numeric(df["Ticker"].map(auto_yield_map), errors="coerce").astype(float)
df["RSI"] = pd.to_numeric(df["Ticker"].map(rsi_m), errors="coerce").astype(float)
df["SMA200"] = pd.to_numeric(df["Ticker"].map(sma_m), errors="coerce").astype(float)
df["SMA_Pct"] = np.where(df["SMA200"].notna() & (df["SMA200"] != 0), (df["Current"] - df["SMA200"]) / df["SMA200"] * 100, np.nan).astype(float)

st.sidebar.header("Setări afișare")
c_filt = st.sidebar.selectbox("Filtrare după monedă", ["Toate"] + all_curr)
sort_by = st.sidebar.selectbox(
    "Ordonează tabelul după",
    [
        "vs Preț mediu % (Cele mai scăzute)",
        "Divident AN% (Descrescător)",
        "RSI (Crescător - Supravândute)",
        "RSI (Descrescător - Supracumpărate)",
        "vs SMA 200 % (Crescător)",
        "vs SMA 200 % (Descrescător)",
        "Preț curent (Descrescător)",
        "Sector (A-Z)",
        "Tiker (A-Z)"
    ]
)

view = df.copy() if c_filt == "Toate" else df[df["Currency"] == c_filt].copy()

s_map = dict([
    ("vs Preț mediu % (Cele mai scăzute)", ("Diff_Avg_Pct", True)),
    ("Divident AN% (Descrescător)", ("Div_Yield", False)),
    ("RSI (Crescător - Supravândute)", ("RSI", True)),
    ("RSI (Descrescător - Supracumpărate)", ("RSI", False)),
    ("vs SMA 200 % (Crescător)", ("SMA_Pct", True)),
    ("vs SMA 200 % (Descrescător)", ("SMA_Pct", False)),
    ("Preț curent (Descrescător)", ("Current", False)),
    ("Sector (A-Z)", ("Sector", True)),
    ("Tiker (A-Z)", ("Ticker", True))
])
col_s, asc_s = s_map[sort_by]
view = view.sort_values(by=col_s, ascending=asc_s, na_position="last")

st.sidebar.info(f"Fișier: `{CSV_PATH.name}`\n\nSimboluri afișate: {len(view)}/{len(df)}")

def f_div_yield(v):
    return "" if (pd.isna(v) or v == "" or float(v) <= 0) else f"{float(v):.2f}%"

def fmt_sma_combined(r):
    if pd.isna(r["SMA200"]) or pd.isna(r["SMA_Pct"]):
        return ""
    p_str = f"{r['SMA200']:,.4f}" if abs(r["SMA200"]) < 2 else f"{r['SMA200']:,.2f}"
    return f"{p_str} ({r['SMA_Pct']:+.2f}%)"

def color_sma_combined(v):
    if pd.isna(v) or str(v).strip() == "" or "(" not in str(v):
        return ""
    pct_part = str(v).split("(")[1].replace("%)", "").replace("+", "")
    try:
        num = float(pct_part)
        return "color: #00e676; font-weight: bold;" if num > 0 else ("color: #ff5252; font-weight: bold;" if num < 0 else "")
    except Exception:
        return ""

if not view.empty:
    view["SMA_Disp"] = view.apply(fmt_sma_combined, axis=1)
    disp = view[["Ticker", "Company", "Currency", "Sector", "Diff_Avg_Pct", "Avg_Price", "Current", "Div_Yield", "RSI", "SMA_Disp"]].copy()
    disp.columns = ["Tiker", "Companie", "Monedă", "Sector", "vs Preț mediu %", "Preț mediu", "Preț curent", "Divident AN%", "RSI (14)", "SMA 200"]
    fmt = dict([("vs Preț mediu %", f_sma), ("Preț mediu", f_price), ("Preț curent", f_price), ("Divident AN%", f_div_yield), ("RSI (14)", f_rsi)])
    disp_clean = clean_table(disp, fmt)
    styler = disp_clean.style.map(c_pnl, subset=["vs Preț mediu %"]).map(color_sma_combined, subset=["SMA 200"]).map(c_rsi, subset=["RSI (14)"])
    st.dataframe(styler, use_container_width=True, hide_index=True, height=480, column_config=dict(Tiker=st.column_config.TextColumn("Tiker", pinned=True)))

st.subheader("Editare listă (watchlist.csv)")
edited = st.data_editor(view[w_cols], num_rows="dynamic", use_container_width=True, key="ed_watch")
if st.button("Salvează modificările în watchlist.csv"):
    up = edited if c_filt == "Toate" else pd.concat([df[df["Currency"] != c_filt][w_cols], edited], ignore_index=True)
    ok = save_csv_permanent(up, CSV_PATH)
    st.cache_data.clear()
    st.success("Salvat permanent pe GitHub!" if ok else "Salvat local!")
