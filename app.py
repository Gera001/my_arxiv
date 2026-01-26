import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, date, timezone
from database import Session, Paper, User, logger
from core_batch import call_qwen_ai_sync
from services import (
    send_verification_code,
    verify_code,
    get_user_by_email,
    update_user_subscription,
    toggle_favorite,
    get_user_favorites,
    is_paper_favorited,
    get_papers_by_category,
    get_all_categories,
    get_earliest_paper_date,
    get_recent_donations,
    add_comment,
    get_paper_comments,
    get_trending_papers,
    get_user_favorite_ids,
    AVAILABLE_CATEGORIES
)

# --- 页面基础配置 ---
st.set_page_config(
    page_title="ArxivMind AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS: 高级黑白暖色调 & UI 优化 ---
st.markdown("""
    <style>
    /* 全局字体与背景 */
    .stApp { 
        background-color: #fdfcf0; 
        color: #1a1a1a; 
    }

    /* 动画定义 */
    @keyframes fadeIn { 
        from { opacity: 0; transform: translateY(10px); } 
        to { opacity: 1; transform: translateY(0); } 
    }

    /* --- 登录页组件 --- */
    /* 呼吸球容器 */
    .blob-container {
        display: flex;
        justify-content: center;
        align-items: center;
        margin-bottom: 20px;
    }

    /* 呼吸球本体 */
    .blob {
        width: 100px;
        height: 100px;
        /* 渐变色：使用你的主题色 #D4A373 搭配浅一点的颜色 */
        background: linear-gradient(135deg, #D4A373 0%, #E6C29F 100%);
        /* 初始形状 */
        border-radius: 30% 70% 70% 30% / 30% 30% 70% 70%;
        /* 阴影让它更有立体感 */
        box-shadow: 0 10px 20px rgba(212, 163, 115, 0.4);
        /* 动画定义：名称 时长 循环 缓动 */
        animation: blob-anim 6s linear infinite; 
        transition: all 0.5s ease;
    }

    /* 鼠标悬停时的互动效果 */
    .blob:hover {
        transform: scale(1.1);
        box-shadow: 0 15px 25px rgba(212, 163, 115, 0.6);
    }

    /* 关键帧动画：控制形状变换和位置微调 */
    @keyframes blob-anim {
        0% {
            border-radius: 30% 70% 70% 30% / 30% 30% 70% 70%;
            transform: translateY(0);
        }
        25% {
            border-radius: 58% 42% 75% 25% / 76% 46% 54% 24%;
            transform: translateY(-5px);
        }
        50% {
            border-radius: 50% 50% 33% 67% / 55% 27% 73% 45%;
            transform: translateY(0);
        }
        75% {
            border-radius: 33% 67% 58% 42% / 63% 68% 32% 37%;
            transform: translateY(5px);
        }
        100% {
            border-radius: 30% 70% 70% 30% / 30% 30% 70% 70%;
            transform: translateY(0);
        }
    }
    .login-wrapper {
        display: flex;
        justify-content: center;
        align-items: center;
        padding-top: 40px;
    }
    .login-card {
        background: #ffffff;
        padding: 40px 40px;
        border-radius: 16px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.06);
        border: 1px solid #f0f0f0;
        text-align: center;
        animation: fadeIn 0.8s ease-out;
    }
    .main-title {
        text-align: center;
        font-size: 52px;
        font-weight: 200;
        letter-spacing: 10px;
        color: #1a1a1a;
        margin-bottom: 5px;
        font-family: 'Garamond', serif;
    }
    .sub-title {
        text-align: center;
        color: #888;
        font-size: 14px;
        margin-bottom: 40px;
        letter-spacing: 3px;
        text-transform: uppercase;
    }

    /* --- 论文卡片组件 --- */
    .paper-card { 
        border-left: 4px solid #D4A373; 
        padding: 24px; 
        margin-bottom: 20px; 
        background: #ffffff; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
        border-radius: 0 12px 12px 0;
        animation: fadeIn 0.5s ease-out;
        transition: transform 0.2s;
    }
    .paper-card:hover {
        transform: translateX(5px);
        box-shadow: 0 6px 16px rgba(0,0,0,0.06);
    }
    .paper-title {
        font-size: 18px;
        font-weight: 700;
        color: #2c3e50;
        margin-bottom: 10px;
        line-height: 1.4;
    }
    .paper-meta {
        color: #7f8c8d;
        font-size: 13px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .category-tag {
        background: #D4A373;
        color: #fff;
        padding: 3px 10px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 500;
    }

    /* --- 打赏页组件 --- */
    .donor-wall {
        background: #fff;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #eee;
        height: 400px;
        overflow-y: auto;
        box-shadow: inset 0 0 10px rgba(0,0,0,0.02);
    }
    .donor-item {
        display: flex;
        justify-content: space-between;
        padding: 12px;
        border-bottom: 1px solid #f9f9f9;
        color: #555;
        font-size: 14px;
    }
    .donor-item:last-child { border-bottom: none; }
    .qr-container {
        text-align: center;
        background: #fff;
        padding: 30px;
        border-radius: 12px;
        border: 2px dashed #D4A373;
        margin-bottom: 20px;
    }

    /* --- 通用组件 --- */
    section[data-testid="stSidebar"] { 
        background-color: #f7f3e3 !important; 
        border-right: 1px solid #e0dbcd;
    }
    .stButton>button { 
        border-radius: 8px; 
        border: 1px solid #1a1a1a; 
        background: transparent; 
        transition: all 0.3s; 
        font-weight: 500;
    }
    .stButton>button:hover { 
        background: #1a1a1a; 
        color: #fdfcf0; 
        border-color: #1a1a1a;
        transform: translateY(-1px);
    }
    .block-container { padding-top: 2rem; }
    </style>
""", unsafe_allow_html=True)


# --- 辅助函数 ---
def mask_email(email: str) -> str:
    """邮箱加密脱敏处理"""
    if not email or "@" not in email:
        return "***"
    try:
        username, domain = email.split('@')
        if len(username) <= 2:
            return f"{username[0]}***@{domain}"
        return f"{username[:2]}****@{domain}"
    except:
        return email


# --- 页面视图函数 ---

def show_login_page():
    """显示登录页面 - 布局优化版"""
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<h1 class='main-title'>ARXIVMIND</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-title'>INTELLIGENT PAPER MONITORING SYSTEM</p>", unsafe_allow_html=True)

    # 1:1.2:1 的比例让中间卡片宽度适中且居中
    col1, col2, col3 = st.columns([1, 1.2, 1])

    with col2:
        # st.markdown("<div class='login-wrapper'><div class='login-card'>", unsafe_allow_html=True)
        st.markdown("""
            <div class='blob-container'>
                <div class='blob'></div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("### 欢迎回来")
        st.markdown("<p style='color:#999; font-size:14px;'>请使用邮箱验证码登录</p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        email = st.text_input("📧 邮箱地址", placeholder="name@example.com")

        # 验证码行
        col_btn, col_input = st.columns([1, 2])
        with col_btn:
            # 这里的 vertical-align 是为了对齐
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📨 获取验证码", width='stretch'):
                if not email or "@" not in email:
                    st.error("邮箱格式错误")
                else:
                    with st.spinner("发送中..."):
                        success, msg = send_verification_code(email)
                        if success:
                            st.session_state.pending_email = email
                            st.success("已发送")
                        else:
                            st.error(msg)
        with col_input:
            code = st.text_input("🔐 验证码", placeholder="6位数字", label_visibility="visible")

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("立即进入系统", type="primary", width='stretch'):
            if not email or not code:
                st.error("请填写完整信息")
            else:
                with st.spinner("验证身份中..."):
                    success, msg = verify_code(email, code)
                    if success:
                        st.session_state.authenticated = True
                        st.session_state.user_email = email
                        st.rerun()
                    else:
                        st.error(msg)

        st.markdown("</div></div>", unsafe_allow_html=True)


def show_sidebar():
    """显示侧边栏"""
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user_email}")
        st.caption("Standard Plan")
        st.divider()

        # 导航菜单
        st.markdown("### 📍 导航")
        page = st.radio(
            "选择页面",
            ["📊 论文看板", "🔥 热门榜单", "📑 论文浏览", "⭐ 我的收藏", "📬 订阅设置", "💰 打赏支持"],
            label_visibility="collapsed"
        )

        st.divider()

        # 快速筛选（仅在论文浏览页显示）
        if page == "📑 论文浏览":
            st.markdown("### 🏷️ 领域筛选")
            categories = ["全部"] + get_all_categories()
            selected_category = st.selectbox(
                "选择领域",
                categories,
                label_visibility="collapsed"
            )
            st.session_state.selected_category = selected_category

        st.divider()

        if st.button("🚪 退出登录", width='stretch'):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

        return page


def show_dashboard():
    """显示论文看板"""
    st.markdown("## 📊 智能监控看板")

    session = Session()
    papers = session.query(Paper).filter(Paper.batch_status == "completed").all()

    if not papers:
        st.info("目前没有已完成分析的论文数据。")
        session.close()
        return

    # 统计卡片
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("论文总数", len(papers), delta=None)
    with col2:
        categories_count = len(set(p.category for p in papers if p.category))
        st.metric("覆盖领域", categories_count)
    with col3:
        total_citations = sum(p.citation_count or 0 for p in papers)
        st.metric("总引用影响力", total_citations)
    with col4:
        favorites_count = len(get_user_favorites(st.session_state.user_email))
        st.metric("我的收藏", favorites_count)

    st.markdown("---")

    # 可视化图表
    df = pd.DataFrame([{
        'category': p.category or '未分类',
        'citation': p.citation_count or 0,
        'title': p.title,
        'keywords': p.keywords or ''
    } for p in papers])

    col1, col2 = st.columns(2)

    with col1:
        fig_pie = px.pie(
            df,
            names='category',
            title="📈 论文领域分布",
            color_discrete_sequence=px.colors.sequential.RdBu
        )
        fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_pie, width='stretch')

    with col2:
        all_keywords = df['keywords'].str.split(',').explode().str.strip()
        kw_counts = all_keywords[all_keywords != ''].value_counts().head(12)
        if not kw_counts.empty:
            fig_bar = px.bar(
                x=kw_counts.values,
                y=kw_counts.index,
                orientation='h',
                title="🔥 热点技术关键词",
                labels={'x': '频次', 'y': '关键词'},
                color=kw_counts.values,
                color_continuous_scale='RdBu'
            )
            fig_bar.update_layout(showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_bar, width='stretch')

    # 趋势分析
    st.divider()
    st.markdown("### 🔥 领域趋势 AI 解读")

    categories_list = df['category'].unique().tolist()
    if categories_list:
        c1, c2 = st.columns([3, 1])
        with c1:
            sel_cat = st.selectbox("选择要分析的领域", categories_list, label_visibility="collapsed")
        with c2:
            analyze_btn = st.button("生成深度报告", type="primary", width='stretch')

        if analyze_btn:
            top_20 = session.query(Paper).filter(Paper.category == sel_cat) \
                .order_by(Paper.citation_count.desc()).limit(20).all()
            if top_20:
                paper_list = "\n".join([f"- {p.title} (引用: {p.citation_count})" for p in top_20])
                with st.spinner(f"AI 正在深度阅读 {len(top_20)} 篇论文并总结趋势..."):
                    trend_summary = call_qwen_ai_sync(
                        f"分析以下{sel_cat}领域的Top论文标题，给出三个该领域最近的研究风向，并简要说明每个趋势的意义：\n{paper_list}"
                    )
                    st.success(f"**{sel_cat} 趋势分析报告**")
                    st.markdown(trend_summary)
            else:
                st.warning("该领域数据不足，无法分析")
    session.close()


def show_paper_list():
    """显示论文列表 - 修复HTML渲染问题"""

    # --- 顶部筛选栏 ---
    c_title, c_date = st.columns([3, 1.5])
    with c_title:
        st.markdown("## 📑 论文浏览")
    with c_date:
        min_date = get_earliest_paper_date()
        today = datetime.now(timezone.utc).date()

        target_date = st.date_input(
            "📅 按日期查看",
            value=None,
            min_value=min_date,
            max_value=today,
            help="选择查看特定日期的论文，留空查看全部"
        )

    selected_category = st.session_state.get('selected_category', '全部')

    # 获取数据
    papers = get_papers_by_category(
        category=None if selected_category == '全部' else selected_category,
        target_date=target_date
    )

    filters = []
    if selected_category != '全部': filters.append(f"领域：{selected_category}")
    if target_date: filters.append(f"日期：{target_date}")
    info_str = f" · {' | '.join(filters)}" if filters else ""

    if not papers:
        st.warning(f"🔍 未找到符合条件的论文 {info_str}")
        return

    st.markdown(f"共找到 **{len(papers)}** 篇论文{info_str}")
    st.divider()

    # --- 渲染列表 ---
    # <span>🔗 引用: {p.citation_count or 0}</span>
    my_fav_ids = get_user_favorite_ids(st.session_state.user_email)
    for p in papers:
        # is_fav = is_paper_favorited(st.session_state.user_email, p.id)
        is_fav = p.id in my_fav_ids 

        # 获取该论文的所有评论
        comments = get_paper_comments(p.id)
        comment_count = len(comments)

        with st.container():
            col1, col2 = st.columns([20, 1.5])

            with col1:
                # 1. 准备科普内容 (注意：去掉了多行字符串的缩进，防止被识别为代码块)
                pop_science_html = ""
                if p.popular_science:
                    # 使用紧凑的 HTML 字符串，避免 Markdown 解析错误
                    pop_science_html = f"""<div style='background:#f9f9f9;padding:12px 15px;border-radius:8px;margin:12px 0;border-left:3px solid #8e44ad;font-size:14px;color:#444;line-height:1.6;'><strong>💡 AI 科普：</strong>{p.popular_science}</div>"""

                # 2. 准备关键词
                keywords_html = ""
                if p.keywords:
                    keywords_html = f"""<div style='margin-top:8px;font-size:13px;color:#888;'>🏷️ {p.keywords}</div>"""

                # 3. 组合卡片 (确保所有 HTML 都在一行或者顶格写，避免缩进)
                # 注意：这里使用 f-string 拼接，但为了安全，外层用 div 包裹
                card_html = f"""
<div class='paper-card'>
    <div class='paper-title'>{p.title}</div>
    <div class='paper-meta'>
        <span class='category-tag'>{p.category or '未分类'}</span>
        <span>📅 {p.created_at.strftime('%Y-%m-%d')}</span>
    </div>
    {pop_science_html}
    {keywords_html}
</div>
"""
                # 关键：unsafe_allow_html=True 必须开启
                st.markdown(card_html, unsafe_allow_html=True)

            with col2:
                # 收藏按钮垂直居中微调
                st.markdown("<br>", unsafe_allow_html=True)
                fav_btn = "⭐" if is_fav else "☆"
                if st.button(fav_btn, key=f"fav_{p.id}", help="收藏"):
                    success, is_now_fav, msg = toggle_favorite(
                        st.session_state.user_email, p.id
                    )
                    if success:
                        st.toast(msg)
                        st.rerun()

            # --- 新增：评论交互区 (放在 expander 里) ---
            # 标题显示评论数量
            with st.expander(f"💬 讨论与评论 ({comment_count})"):

                # 1. 显示历史评论
                if comments:
                    for c in comments:
                        # 简单的头像占位符和脱敏邮箱
                        c_email = mask_email(c['user_email'])
                        c_time = c['created_at'].strftime('%Y-%m-%d %H:%M')

                        st.markdown(f"""
                        <div style='background:#f1f1f1; padding:10px; border-radius:8px; margin-bottom:8px; font-size:14px;'>
                            <div style='color:#D4A373; font-weight:bold; font-size:12px;'>
                                👤 {c_email} <span style='color:#aaa; font-weight:normal; margin-left:8px;'>{c_time}</span>
                            </div>
                            <div style='margin-top:4px; color:#333;'>{c['content']}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.caption("暂无评论，快来抢沙发吧~")

                # 2. 发送新评论
                # 使用 form 可以让用户按回车发送，且避免每个字符输入都刷新页面
                with st.form(key=f"comment_form_{p.id}", clear_on_submit=True):
                    new_comment_text = st.text_area("发表你的观点...", height=60, placeholder="这篇论文的方法很有趣...")
                    submit_col1, submit_col2 = st.columns([5, 1])
                    with submit_col2:
                        submitted = st.form_submit_button("发送 🚀")

                    if submitted:
                        if new_comment_text:
                            success, msg = add_comment(st.session_state.user_email, p.id, new_comment_text)
                            if success:
                                st.toast("评论已发布！")
                                st.rerun()  # 刷新页面显示新评论
                            else:
                                st.error(msg)
                        else:
                            st.warning("写点什么再发送吧")

                # --- 新增功能：学术工具栏 ---
                with st.expander("🤖 AI 论文助手 & 工具"):
                    # 工具 1: BibTeX
                    # st.markdown("#### 📝 引用工具")
                    # bib_code = generate_bibtex(p)
                    # st.code(bib_code, language="latex")
                    #
                    # st.divider()

                    # 工具 2: Paper Chat
                    st.markdown("#### 💬 向 AI 提问")
                    st.caption("基于 AI 对本文的深度分析记录进行回答")

                    # 为每篇论文维护独立的聊天记录
                    chat_key = f"chat_history_{p.id}"
                    if chat_key not in st.session_state:
                        st.session_state[chat_key] = []

                    # 显示历史消息
                    for msg in st.session_state[chat_key]:
                        with st.chat_message(msg["role"]):
                            st.markdown(msg["content"])

                    # 输入框
                    if prompt := st.chat_input(f"关于《{p.title[:10]}...》的问题", key=f"input_{p.id}"):
                        # 1. 显示用户提问
                        st.session_state[chat_key].append({"role": "user", "content": prompt})
                        with st.chat_message("user"):
                            st.markdown(prompt)

                        # 2. 构建上下文并调用 AI
                        with st.chat_message("assistant"):
                            with st.spinner("AI 正在思考..."):
                                # 构建上下文：将论文的已有分析结果喂给 AI
                                context = f"""
                                你是一个学术助手。用户正在阅读论文《{p.title}》。
                                以下是该论文的核心信息：
                                - 领域：{p.category}
                                - 动机：{p.analysis_json.get('motivation', '未知')}
                                - 方法：{p.analysis_json.get('method', '未知')}
                                - 结果：{p.analysis_json.get('result', '未知')}
                                -- 全文内容：{(p.full_text_tmp or "")[:20000]}

                                请基于以上信息回答用户的问题：{prompt}
                                如果问题超出了上述信息范围，请礼貌告知需要阅读原文。
                                """

                                # 调用 core_batch 里的同步调用函数
                                # 注意：call_qwen_ai_sync 原本返回 JSON，我们这里需要它返回普通文本
                                # 建议修改 core_batch.py 或者在这里做一个简单的临时处理
                                # 这里假设我们复用 call_qwen_ai_sync 但它返回的是 JSON 字符串
                                # 为了更自然，建议在 core_batch.py 加一个简单的 call_qwen_chat

                                from core_batch import client  # 直接调用 OpenAI 客户端更灵活

                                try:
                                    resp = client.chat.completions.create(
                                        model="qwen-plus",
                                        messages=[{"role": "user", "content": context}],
                                        # 不强制 JSON，普通对话模式
                                    )
                                    answer = resp.choices[0].message.content
                                    st.markdown(answer)
                                    st.session_state[chat_key].append({"role": "assistant", "content": answer})
                                except Exception as e:
                                    st.error(f"AI 服务繁忙: {e}")

            # 详情折叠栏
            with st.expander("🧐 查看 AI 深度技术分析"):
                if p.analysis_json:
                    analysis = p.analysis_json
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if analysis.get('motivation'):
                            st.markdown("#### 🎯 痛点与动机")
                            st.write(analysis['motivation'])
                        if analysis.get('method'):
                            st.markdown("#### 🔬 核心方法")
                            st.write(analysis['method'])
                    with cc2:
                        if analysis.get('result'):
                            st.markdown("#### 📊 关键结果")
                            st.write(analysis['result'])
                        if analysis.get('implementation_example'):
                            st.markdown("#### 💻 实现思路")
                            st.write(analysis['implementation_example'])
                else:
                    st.info("暂无深度分析数据")

                st.markdown("<br>", unsafe_allow_html=True)
                st.link_button("📄 阅读 Arxiv 原文 PDF", p.url)


def show_favorites():
    """显示收藏页面"""
    st.markdown("## ⭐ 我的收藏")

    favorites = get_user_favorites(st.session_state.user_email)

    if not favorites:
        st.info("您还没有收藏任何论文，去论文浏览页面看看吧！")
        return

    st.markdown(f"共收藏 **{len(favorites)}** 篇论文")
    st.divider()

    for p in favorites:
        with st.container():
            st.markdown(f"""
                <div class='paper-card' style='border-left-color: #e74c3c;'>
                    <div class='paper-title'>{p.title}</div>
                    <div class='paper-meta'>
                        <span class='category-tag'>{p.category or '未分类'}</span>
                        引用量: {p.citation_count or 0}
                    </div>
                </div>
            """, unsafe_allow_html=True)

            c1, c2 = st.columns([1, 8])
            with c1:
                if st.button("💔 移除", key=f"unfav_{p.id}"):
                    success, _, msg = toggle_favorite(st.session_state.user_email, p.id)
                    if success:
                        st.toast(msg)
                        st.rerun()
            with c2:
                st.link_button("📄 原文", p.url)


def show_subscription():
    """显示订阅设置页面"""
    st.markdown("## 📬 订阅设置")

    user = get_user_by_email(st.session_state.user_email)
    if not user:
        return

    st.info("📧 我们将每日为您推送以下领域的最新高分论文摘要。")

    current_subs = [c.strip() for c in user.subscribed_categories.split(",") if c.strip()]

    selected_cats = st.multiselect(
        "定制您的兴趣领域：",
        AVAILABLE_CATEGORIES,
        default=current_subs
    )

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("💾 保存订阅设置", type="primary"):
        success, msg = update_user_subscription(
            st.session_state.user_email,
            selected_cats
        )
        if success:
            st.success("✅ 设置已保存！")
        else:
            st.error(msg)

    st.divider()
    if selected_cats:
        st.write(f"当前已订阅：{', '.join(selected_cats)}")
    else:
        st.write("当前状态：接收全领域推送")


def show_donate_page():
    """显示打赏与致谢页面"""
    st.markdown("## ☕ 赞助与支持")
    st.markdown("ArxivMind 是一个开源项目。如果您觉得它对您的研究有帮助，欢迎请开发者喝杯咖啡，支持服务器与 API 开销！")
    st.divider()

    col1, col2 = st.columns([1, 1.2])

    with col1:
        st.markdown("### ❤️ 打赏方式")
        st.markdown("<div class='qr-container'>", unsafe_allow_html=True)

        tab_wx, tab_ali = st.tabs(["微信支付", "支付宝"])

        with tab_wx:
            # 这里的图片请替换为你自己的
            st.image("https://via.placeholder.com/300x300.png?text=WeChat+Pay", caption="微信扫码支持")

        with tab_ali:
            st.image("https://via.placeholder.com/300x300.png?text=Alipay", caption="支付宝扫码支持")

        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("### 🏆 致谢名单 (Sponsors)")

        # --- 从数据库读取数据 ---
        donors = get_recent_donations(limit=100)

        if not donors:
            st.info("暂无打赏记录，期待您的支持！")
        else:
            st.markdown(f"感谢这 **{len(donors)}** 位朋友的慷慨资助：")
            st.markdown("<div class='donor-wall'>", unsafe_allow_html=True)

            for d in donors:
                masked = mask_email(d.email)
                # 格式化日期
                date_str = d.created_at.strftime("%Y-%m-%d")

                # 如果有留言，显示留言；否则只显示金额
                msg_html = f"<div style='font-size:12px; color:#999; margin-top:2px;'>“{d.message}”</div>" if d.message else ""

                st.markdown(f"""
                    <div class='donor-item' style='display:block;'>
                        <div style='display:flex; justify-content:space-between;'>
                            <span>👤 {masked} <span style='font-size:12px; color:#ccc; margin-left:5px;'>{date_str}</span></span>
                            <span style='color:#D4A373; font-weight:bold;'>❤️ {d.amount}</span>
                        </div>
                        {msg_html}
                    </div>
                """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

        st.caption("注：打赏时备注邮箱即可上榜，数据将定期录入。")


def show_trending():
    """显示热门榜单"""
    st.markdown("## 🔥 本周热门论文 Top 5")
    st.markdown("基于社区收藏量与讨论热度实时生成。")
    st.divider()

    papers = get_trending_papers(limit=5)

    if not papers:
        st.info("数据积累中，暂无榜单。")
        return

    for idx, p in enumerate(papers):
        col_rank, col_content = st.columns([1, 10])
        with col_rank:
            st.markdown(f"<h1 style='color:#D4A373; text-align:center;'>{idx + 1}</h1>", unsafe_allow_html=True)

        with col_content:
            st.markdown(f"### {p.title}")
            st.caption(f"发布日期: {p.created_at.strftime('%Y-%m-%d')} | 领域: {p.category}")
            st.markdown(f"_{p.popular_science[:100]}..._")
            st.link_button("👉 前往阅读", p.url)

        st.markdown("---")

def main():
    """主函数入口"""
    if not st.session_state.get('authenticated', False):
        show_login_page()
        return

    page = show_sidebar()

    if page == "📊 论文看板":
        show_dashboard()
    elif page == "🔥 热门榜单":
        show_trending()
    elif page == "📑 论文浏览":
        show_paper_list()
    elif page == "⭐ 我的收藏":
        show_favorites()
    elif page == "📬 订阅设置":
        show_subscription()
    elif page == "💰 打赏支持":
        show_donate_page()


if __name__ == "__main__":
    main()
