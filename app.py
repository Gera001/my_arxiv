import streamlit as st
import pandas as pd
import plotly.express as px
from database import Session, Paper, User
from core_batch import call_qwen_ai_sync

st.set_page_config(page_title="ArxivMind AI", layout="wide")
st.title("🤖 ArxivMind AI 智能监控看板")

# --- 1. 健壮的订阅系统 ---
with st.sidebar:
    st.header("📬 订阅设置")
    email = st.text_input("邮箱地址")
    cats = st.multiselect("感兴趣领域", ["大语言模型", "多模态", "Agent", "计算机视觉", "强化学习"])
    if st.button("更新订阅"):
        if not email: st.warning("请填写邮箱")
        else:
            session = Session()
            user = session.query(User).filter_by(email=email).first()
            if user:
                user.subscribed_categories = ",".join(cats)
                user.is_subscribed = True
            else:
                session.add(User(email=email, subscribed_categories=",".join(cats)))
            session.commit(); session.close()
            st.success("订阅配置成功！")

# --- 2. 可视化趋势 ---
session = Session()
papers = session.query(Paper).filter(Paper.batch_status == "completed").all()
if papers:
    df = pd.DataFrame([{
        'category': p.category,
        'citation': p.citation_count,
        'title': p.title,
        'keywords': p.keywords
    } for p in papers])

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(px.pie(df, names='category', title="论文领域分布"), use_container_width=True)
    with col2:
        # 关键词频次统计
        kw_counts = df['keywords'].str.split(',').explode().str.strip().value_counts().head(12)
        st.plotly_chart(px.bar(kw_counts, title="热点技术词云(词频)"), use_container_width=True)

    # --- 3. 领域 Top 20 月度趋势总结 ---
    st.divider()
    st.subheader("🔥 领域 Top 20 核心趋势研判")
    sel_cat = st.selectbox("选择要分析的领域", df['category'].unique())
    if st.button("生成趋势深度总结"):
        top_20 = session.query(Paper).filter(Paper.category == sel_cat)\
                 .order_by(Paper.citation_count.desc()).limit(20).all()
        paper_list = "\n".join([f"- {p.title} (引用: {p.citation_count})" for p in top_20])
        with st.spinner("AI 正在深度阅读并总结趋势..."):
            trend_summary = call_qwen_ai_sync(f"分析以下{sel_cat}领域的Top20论文标题，给出三个该领域最近的研究风向：\n{paper_list}")
            st.info(f"**{sel_cat} 趋势总结报告：**\n\n{trend_summary}")

    # --- 4. 论文流展示 ---
    st.divider()
    st.subheader("📑 论文精选流")
    for p in papers[::-1]:
        with st.expander(f"[{p.category}] {p.title} (引用: {p.citation_count})"):
            st.write(p.popular_science)
            if p.analysis_json:
                st.write("**具体实现举例：**")
                st.write(p.analysis_json.get('implementation_example', '无'))
            st.link_button("阅读 PDF原文", p.url)
else:
    st.info("目前没有已完成分析的论文数据。")
session.close()