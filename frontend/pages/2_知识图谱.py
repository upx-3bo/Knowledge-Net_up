import streamlit as st
import httpx
import json

API_BASE = st.secrets.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="知识图谱", layout="wide")
st.title("🕸️ 知识图谱")
st.markdown("浏览技术分类树和知识图谱")

tab1, tab2 = st.tabs(["🏷️ 分类树", "🔍 图谱查询"])

with tab1:
    st.subheader("技术分类树")

    try:
        r = httpx.get(f"{API_BASE}/classification/tree", timeout=10)
        if r.status_code == 200:
            tree_data = r.json()
            if isinstance(tree_data, list):
                parents = set()
                for item in tree_data:
                    if isinstance(item, dict) and "parent" in item:
                        parent = item["parent"]
                        children = item.get("children", [])
                        if isinstance(children, list):
                            parents.add(parent)
                            st.markdown(f"**📁 {parent}**")
                            for child in children:
                                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;├ 📂 {child}")
                if not parents:
                    st.info("分类树为空，请先投喂数据")
            else:
                st.info("分类树为空")
    except Exception as e:
        st.warning(f"无法连接后端: {e}")

    st.divider()
    st.subheader("技术列表")
    try:
        r = httpx.get(f"{API_BASE}/knowledge/technology", timeout=10)
        if r.status_code == 200:
            techs = r.json()
            if isinstance(techs, list):
                for t in techs:
                    name = t.get("name", "")
                    trl = t.get("trl", "")
                    desc = t.get("description", "")[:80]
                    st.markdown(f"**🔬 {name}** (TRL {trl}) - {desc}")
            else:
                st.info("暂无技术数据")
    except Exception as e:
        st.warning(f"连接失败: {e}")

with tab2:
    st.subheader("图谱关联查询")

    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input("搜索技术/标准/专利关键词")
    with col2:
        depth = st.number_input("关联深度", 1, 3, 1)

    if st.button("🔍 查询图谱"):
        if not search_term:
            st.warning("请输入关键词")
        else:
            try:
                r = httpx.get(
                    f"{API_BASE}/search/graph",
                    params={"keyword": search_term, "depth": depth},
                    timeout=30
                )
                if r.status_code == 200:
                    data = r.json()
                    st.success(f"查询到 {len(data) if isinstance(data, list) else 0} 条结果")
                    st.json(data)
                else:
                    st.error(f"查询失败: {r.text}")
            except Exception as e:
                st.error(f"连接失败: {e}")

    st.divider()
    st.subheader("技术-标准对照")
    tech_name = st.text_input("查询技术名称", key="tech_std_query")
    if st.button("查标准"):
        try:
            r = httpx.get(
                f"{API_BASE}/classification/technology-standards",
                params={"tech_name": tech_name},
                timeout=10
            )
            if r.status_code == 200:
                st.table(r.json() if isinstance(r.json(), list) else [])
            else:
                st.error(f"失败: {r.text}")
        except Exception as e:
            st.error(f"连接失败: {e}")

    st.subheader("资源池查询")
    res_tech = st.text_input("按技术查询资源", key="res_tech_query")
    if st.button("查资源"):
        try:
            r = httpx.get(
                f"{API_BASE}/classification/resource-pool",
                params={"tech_name": res_tech},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    for res in data:
                        st.markdown(f"👤 **{res.get('name', '')}** ({res.get('type', '')}) - {res.get('department', '')}")
                else:
                    st.info("暂无资源")
        except Exception as e:
            st.error(f"连接失败: {e}")
