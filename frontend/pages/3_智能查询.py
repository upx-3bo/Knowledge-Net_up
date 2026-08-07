import streamlit as st
import httpx
import json

API_BASE = st.secrets.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="智能查询", layout="wide")
st.title("🔍 智能查询")
st.markdown("基于知识图谱的智能检索与分析")

tab1, tab2 = st.tabs(["💬 自然语言查询", "📊 标准化分析"])

with tab1:
    st.subheader("知识图谱检索")

    query = st.text_area("输入查询", placeholder="如：查询高速端制动的技术有哪些？", height=80)

    if st.button("🔍 查询", type="primary"):
        if not query:
            st.warning("请输入查询内容")
        else:
            with st.spinner("正在查询知识图谱..."):
                try:
                    r = httpx.get(
                        f"{API_BASE}/search/full-text",
                        params={"query": query},
                        timeout=30
                    )
                    if r.status_code == 200:
                        result = r.json()
                        if isinstance(result, list) and len(result) > 0:
                            st.success(f"找到 {len(result)} 条结果")
                            for item in result:
                                tag = item.get("_tag", "?")
                                name = item.get("name", "?")
                                vid = item.get("vid", "?")
                                icons = {
                                    "technology": "🔬",
                                    "standard": "📋",
                                    "patent": "📜",
                                    "document": "📄",
                                    "component": "⚙️",
                                    "resource": "👤",
                                }
                                icon = icons.get(tag, "📌")
                                st.markdown(f"{icon} **[{tag}]** {name}  `{vid}`")
                        else:
                            st.info("未找到结果，请换个关键词试试")
                    else:
                        st.error(f"查询失败: {r.text}")
                except Exception as e:
                    st.warning(f"后端未连接: {e}")
                    st.info("图谱数据示例（本地缓存）")
                    st.json([
                        {"_tag": "technology", "name": "高速端平行制动结构", "vid": "高速端平行制动结构"},
                        {"_tag": "technology", "name": "高速端正交制动结构", "vid": "高速端正交制动结构"},
                        {"_tag": "standard", "name": "机动车运行安全技术条件", "vid": "GB_7258_2017"},
                    ])

with tab2:
    st.subheader("标准化分析")
    st.markdown("查看标准关联的技术矩阵")

    try:
        r = httpx.get(f"{API_BASE}/knowledge/standard", timeout=10)
        if r.status_code == 200:
            standards = r.json()
            if isinstance(standards, list):
                selected_std = st.selectbox(
                    "选择标准",
                    options=[s.get("name", "") for s in standards if isinstance(s, dict)],
                )
                if selected_std:
                    std_code = ""
                    for s in standards:
                        if isinstance(s, dict) and s.get("name") == selected_std:
                            std_code = s.get("code", "")
                            break
                    if std_code:
                        r2 = httpx.get(
                            f"{API_BASE}/classification/standard-analysis",
                            params={"standard_code": std_code},
                            timeout=10
                        )
                        if r2.status_code == 200:
                            data = r2.json()
                            if isinstance(data, list) and len(data) > 0:
                                st.subheader("适用技术")
                                st.table(data)
                            else:
                                st.info("该标准暂无关联技术")
        else:
            st.info("暂无标准数据")
    except Exception as e:
        st.warning(f"连接失败: {e}")
