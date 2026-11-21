import streamlit as st

st.set_page_config(page_title="Monitor Investiții", layout="wide")

st.write("")
st.write("")
st.title("💼 Monitor Investiții")
st.write("Alege secțiunea pe care dorești să o accesezi:")
st.write("")

c1, c2, c3, _ = st.columns([1.2, 1.2, 1.2, 1.4])
if c1.button("📈 Portofoliu XTB", use_container_width=True, type="primary"):
    st.switch_page("pages/1_Portofoliu_XTB.py")
if c2.button("🪙 Portofoliu Kraken", use_container_width=True, type="primary"):
    st.switch_page("pages/2_Portofoliu_Kraken.py")
if c3.button("👁️ Urmărește", use_container_width=True, type="primary"):
    st.switch_page("pages/3_Urmareste.py")
