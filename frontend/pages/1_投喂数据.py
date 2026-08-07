import streamlit as st
import httpx
import json

API_BASE = st.secrets.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="投喂数据", layout="wide")
st.title("📂 投喂数据")
st.markdown("向知识库中投喂技术资料，AI 自动抽取知识并写入图谱")

tab1, tab2, tab3, tab4 = st.tabs(["✍️ 手动输入", "📄 文档投喂", "🔗 关联关系", "📡 情报获取"])

with tab1:
    st.subheader("新增技术")

    with st.form("add_technology"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("技术名称 *", placeholder="如：高速端平行制动结构")
            description = st.text_area("技术描述", height=100)
        with col2:
            trl = st.slider("TRL 技术成熟度", 1, 9, 3)
            keywords = st.text_input("关键词", placeholder="逗号分隔")
            category = st.text_input("所属分类", placeholder="如：平行制动")

        if st.form_submit_button("提交技术"):
            try:
                r = httpx.post(f"{API_BASE}/knowledge/technology", json={
                    "name": name, "description": description,
                    "trl": trl, "keywords": keywords, "category": category,
                }, timeout=10)
                if r.status_code == 200:
                    st.success(f"✅ 技术「{name}」已添加")
                else:
                    st.error(f"失败: {r.text}")
            except Exception as e:
                st.error(f"连接失败: {e}")

    st.divider()
    st.subheader("新增标准")
    with st.form("add_standard"):
        col1, col2 = st.columns(2)
        with col1:
            std_name = st.text_input("标准名称")
            std_code = st.text_input("标准号", placeholder="如：GB/T 18488.1-2015")
        with col2:
            org = st.text_input("发布组织")
            std_type = st.selectbox("标准类型", ["国标", "行标", "企标", "国际标准", "国军标"])
        if st.form_submit_button("提交标准"):
            try:
                r = httpx.post(f"{API_BASE}/knowledge/standard", json={
                    "name": std_name, "code": std_code, "organization": org, "type": std_type,
                }, timeout=10)
                if r.status_code == 200:
                    st.success(f"✅ 标准「{std_name}」已添加")
                else:
                    st.error(f"失败: {r.text}")
            except Exception as e:
                st.error(f"连接失败: {e}")

with tab2:
    st.subheader("文档投喂 + AI 知识抽取")
    st.info("上传文档后，AI 自动抽取技术、分类、标准、专利等信息并写入知识图谱")

    doc_title = st.text_input("文档标题", placeholder="如：高速端平行制动结构技术报告")
    doc_source = st.text_input("来源", placeholder="如：内部报告 / 专利 / 文献")
    doc_content = st.text_area("粘贴文档内容", height=200, placeholder="将文档文本粘贴到这里...")

    col1, col2 = st.columns(2)
    with col1:
        target_tech = st.text_input("关联到已有技术（可选）")
    with col2:
        auto_extract = st.checkbox("AI 自动抽取知识", value=True)

    if st.button("🚀 提交并抽取"):
        if not doc_title or not doc_content:
            st.warning("请填写标题和内容")
        else:
            with st.spinner("正在上传并调用 AI 抽取知识..."):
                try:
                    r = httpx.post(f"{API_BASE}/knowledge/document", json={
                        "title": doc_title, "content": doc_content,
                        "source": doc_source, "auto_extract": auto_extract,
                        "target_technology": target_tech,
                    }, timeout=30)
                    st.success("文档已上传")

                    if auto_extract:
                        from openai import OpenAI
                        import os
                        llm_key = os.getenv("LLM_API_KEY", "")
                        if llm_key:
                            st.info("正在调用 AI 抽取结构化知识...")
                            result = _call_extraction(doc_content, doc_title)
                            st.json(result)
                        else:
                            st.warning("未配置 LLM_API_KEY，跳过 AI 抽取")
                except Exception as e:
                    st.error(f"失败: {e}")

with tab3:
    st.subheader("创建关联关系")
    st.markdown("在两个已有节点之间创建关系")

    col1, col2, col3 = st.columns(3)
    with col1:
        src = st.text_input("源节点 ID")
    with col2:
        edge_type = st.selectbox(
            "关系类型",
            ["belongs_to", "relates_to", "has_standard", "has_patent", "references", "depends_on"]
        )
    with col3:
        dst = st.text_input("目标节点 ID")

    if st.button("创建关系"):
        try:
            r = httpx.post(f"{API_BASE}/knowledge/relation", json={
                "edge_type": edge_type, "src_vid": src, "dst_vid": dst,
            }, timeout=10)
            if r.status_code == 200:
                st.success(f"✅ 关系已创建: {src} -[{edge_type}]-> {dst}")
            else:
                st.error(f"失败: {r.text}")
        except Exception as e:
            st.error(f"连接失败: {e}")

with tab4:
    st.subheader("📡 情报自动获取与更新")
    st.markdown("从专利库、新闻源自动获取最新情报，AI 分析后写入知识图谱")

    keywords = st.text_input("搜索关键词", value="驱制一体 轮毂电机 制动", key="intel_keywords")

    if st.button("🔄 执行情报更新"):
        with st.spinner("正在获取并分析情报..."):
            try:
                r = httpx.post(
                    f"{API_BASE}/intelligence/update",
                    params={"keywords": keywords},
                    timeout=120
                )
                if r.status_code == 200:
                    result = r.json()
                    st.success(f"获取到 {result.get('total', 0)} 条情报")
                    for item in result.get("items", []):
                        with st.expander(item["source"]["title"][:50]):
                            st.json(item["analysis"])
                else:
                    st.error(f"失败: {r.text}")
            except Exception as e:
                st.error(f"连接失败: {e}")
