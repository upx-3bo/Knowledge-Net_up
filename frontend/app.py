import streamlit as st
import httpx

st.set_page_config(
    page_title="AI 知识库 - 驱制一体/角模块",
    page_icon="🧠",
    layout="wide",
)

API_BASE = st.secrets.get("API_BASE_URL", "http://localhost:8000")

st.title("🧠 AI 知识库 · 驱制一体 / 角模块")
st.markdown("基于 NebulaGraph 的汽车创新技术知识图谱")
st.divider()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("技术节点", "待连接")
with col2:
    st.metric("标准", "待连接")
with col3:
    st.metric("专利", "待连接")
with col4:
    st.metric("资源", "待连接")

try:
    r = httpx.get(f"{API_BASE}/health", timeout=5)
    if r.status_code == 200:
        st.success("✅ 后端服务已连接")
        techs = httpx.get(f"{API_BASE}/knowledge/technology", timeout=5).json()
        if isinstance(techs, list):
            st.metric("技术节点", len(techs))
except Exception as e:
    st.warning(f"⚠️ 后端未连接: {e}")
    st.info("请先启动后端服务: `uvicorn backend.main:app --reload`")

st.divider()
st.subheader("快速操作")
cols = st.columns(3)
with cols[0]:
    if st.button("📂 投喂数据", use_container_width=True):
        st.switch_page("pages/1_投喂数据.py")
with cols[1]:
    if st.button("🕸️ 查看知识图谱", use_container_width=True):
        st.switch_page("pages/2_知识图谱.py")
with cols[2]:
    if st.button("🔍 智能查询", use_container_width=True):
        st.switch_page("pages/3_智能查询.py")
