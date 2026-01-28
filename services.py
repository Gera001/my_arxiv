import os
import random
from collections import defaultdict

import resend
from database import Session, Paper, User, VerificationCode, Donation, Comment, logger, user_favorites
from sqlalchemy import func
from datetime import datetime, timedelta, date, timezone  # 确保导入了 date
from dotenv import load_dotenv

load_dotenv()
resend.api_key = os.getenv("RESEND_API_KEY")

# 可配置的领域列表
AVAILABLE_CATEGORIES = [
    "语言模型/推理模型",
    "视觉模型/多模态",
    "AI Agent/智能体",
    "推荐搜索",
    "自动驾驶",
    "传统机器学习",
    "其他"
]


def send_verification_code(email: str) -> tuple[bool, str]:
    """
    发送验证码邮件
    返回: (是否成功, 消息或验证码)
    """
    session = Session()
    try:
        # 生成6位验证码
        code = str(random.randint(100000, 999999))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        # 存储验证码
        verification = VerificationCode(
            email=email,
            code=code,
            expires_at=expires_at
        )
        session.add(verification)
        session.commit()

        # 发送邮件
        html = f"""
        <div style='background:#fdfcf0; padding:30px; border:1px solid #ddd; font-family:serif; max-width:400px; margin:0 auto;'>
            <h1 style='text-align:center; color:#1a1a1a; margin-bottom:20px;'>ArxivMind AI</h1>
            <div style='background:#fff; padding:20px; border-left:3px solid #D4A373;'>
                <p style='color:#666; margin-bottom:10px;'>您的验证码是：</p>
                <h2 style='color:#D4A373; font-size:32px; letter-spacing:5px; text-align:center;'>{code}</h2>
                <p style='color:#999; font-size:12px; margin-top:15px;'>验证码有效期10分钟，请尽快使用。</p>
            </div>
        </div>
        """

        resend.Emails.send({
            "from": "ArxivMind <onboarding@resend.dev>",
            "to": email,
            "subject": "【ArxivMind】登录验证码",
            "html": html
        })

        logger.info(f"验证码已发送至: {email}")
        return True, "验证码已发送，请查收邮件"

    except Exception as e:
        logger.error(f"发送验证码失败 ({email}): {e}")
        session.rollback()
        return False, f"发送失败: {str(e)}"
    finally:
        session.close()


def verify_code(email: str, code: str) -> tuple[bool, str]:
    session = Session()
    try:
        # 获取当前 UTC 时间
        now = datetime.now(timezone.utc)

        # 3. 修改查询逻辑
        # 注意：SQLAlchemy 从 SQLite 取出的 datetime 可能是 naive 的 (不带时区)
        # 所以我们在 Python 层面做比较比较稳妥，或者在这里直接用 naive 对比
        # 最简单的修复：先取出记录，再在 Python 里比较时间

        verification = session.query(VerificationCode).filter(
            VerificationCode.email == email,
            VerificationCode.is_used == False
        ).order_by(VerificationCode.created_at.desc()).first()

        if not verification:
            return False, "验证码不存在"

        # 4. 关键：处理时区对比
        # 数据库里的 expires_at 可能是 naive 的，需要加上 utc 时区才能和 now 对比
        db_expire = verification.expires_at
        if db_expire.tzinfo is None:
            db_expire = db_expire.replace(tzinfo=timezone.utc)

        if db_expire < now:
            return False, "验证码已过期"

        if verification.code != code:
            return False, "验证码错误"

        verification.is_used = True

        user = session.query(User).filter_by(email=email).first()
        if not user:
            user = User(email=email)
            session.add(user)

        # 5. 更新最后登录时间
        user.last_login = datetime.now(timezone.utc)
        session.commit()

        return True, "登录成功"

    except Exception as e:
        logger.error(f"验证失败 ({email}): {e}")
        session.rollback()
        return False, f"验证失败: {str(e)}"
    finally:
        session.close()


def get_user_by_email(email: str) -> User | None:
    """获取用户信息"""
    session = Session()
    try:
        user = session.query(User).filter_by(email=email).first()
        if user:
            # 将对象从 session 中分离，以便在 session 关闭后仍可使用
            session.expunge(user)
        return user
    finally:
        session.close()


def update_user_subscription(email: str, categories: list[str]) -> tuple[bool, str]:
    """更新用户订阅"""
    session = Session()
    try:
        user = session.query(User).filter_by(email=email).first()
        if not user:
            return False, "用户不存在"

        user.subscribed_categories = ",".join(categories)
        user.is_subscribed = True
        session.commit()

        logger.info(f"用户订阅更新: {email} -> {categories}")
        return True, "订阅更新成功"

    except Exception as e:
        logger.error(f"更新订阅失败 ({email}): {e}")
        session.rollback()
        return False, str(e)
    finally:
        session.close()


def toggle_favorite(email: str, paper_id: int) -> tuple[bool, bool, str]:
    """
    切换收藏状态
    返回: (操作是否成功, 当前是否已收藏, 消息)
    """
    session = Session()
    try:
        user = session.query(User).filter_by(email=email).first()
        paper = session.query(Paper).get(paper_id)

        if not user or not paper:
            return False, False, "用户或论文不存在"

        if paper in user.favorite_papers:
            user.favorite_papers.remove(paper)
            session.commit()
            logger.info(f"取消收藏: {email} -> Paper {paper_id}")
            return True, False, "已取消收藏"
        else:
            user.favorite_papers.append(paper)
            session.commit()
            logger.info(f"添加收藏: {email} -> Paper {paper_id}")
            return True, True, "已添加收藏"

    except Exception as e:
        logger.error(f"收藏操作失败: {e}")
        session.rollback()
        return False, False, str(e)
    finally:
        session.close()


def get_user_favorites(email: str) -> list[Paper]:
    """获取用户收藏的论文"""
    session = Session()
    try:
        user = session.query(User).filter_by(email=email).first()
        if not user:
            return []

        papers = list(user.favorite_papers)
        for p in papers:
            session.expunge(p)
        return papers

    finally:
        session.close()


def is_paper_favorited(email: str, paper_id: int) -> bool:
    """检查论文是否被用户收藏"""
    session = Session()
    try:
        user = session.query(User).filter_by(email=email).first()
        if not user:
            return False

        paper = session.query(Paper).get(paper_id)
        return paper in user.favorite_papers if paper else False

    finally:
        session.close()


def get_papers_by_category(category: str = None) -> list[Paper]:
    """
    根据分类获取论文
    category 为 None 或空字符串时返回所有论文
    """
    session = Session()
    try:
        query = session.query(Paper).filter(Paper.batch_status == "completed")

        if category and category != "全部":
            query = query.filter(Paper.category == category)

        papers = query.order_by(Paper.publish_date.desc()).all()

        for p in papers:
            session.expunge(p)

        return papers

    finally:
        session.close()


def get_all_categories() -> list[str]:
    """获取所有已有论文的分类"""
    session = Session()
    try:
        categories = session.query(Paper.category).filter(
            Paper.batch_status == "completed",
            Paper.category.isnot(None)
        ).distinct().all()

        return [c[0] for c in categories if c[0]]

    finally:
        session.close()


def send_daily_emails():
    """
    发送每日订阅邮件
    修改点：按Category分类发送，展示中文名，移除引用量
    """
    session = Session()
    try:
        users = session.query(User).filter(User.is_subscribed == True).all()
        new_papers = session.query(Paper).filter(Paper.batch_status == "completed").all()

        if not new_papers:
            logger.info("无新完成论文，跳过邮件发送。")
            return

        logger.info(f"准备为 {len(users)} 位用户发送订阅邮件...")

        for user in users:
            # 1. 筛选用户感兴趣的论文
            interest_list = [c.strip() for c in user.subscribed_categories.split(",") if c.strip()]

            if interest_list:
                target_papers = [p for p in new_papers if p.category in interest_list]
            else:
                target_papers = new_papers

            if not target_papers:
                logger.info(f"用户 {user.email} 无匹配论文，跳过")
                continue

            # 2. 按分类对论文进行分组 (Group by Category)
            papers_by_category = defaultdict(list)
            for p in target_papers:
                cat = p.category if p.category else "其他"
                papers_by_category[cat].append(p)

            # 3. 构建邮件 HTML
            html = """
            <div style='background:#fdfcf0; padding:20px; font-family:serif;'>
                <h1 style='text-align:center; color:#1a1a1a; border-bottom:2px solid #D4A373; padding-bottom:15px;'>
                    ArxivMind 每日精选
                </h1>
                <p style='text-align:center; color:#666; font-size:14px;'>今天为您精选了以下论文</p>
            """

            # 遍历分类字典生成内容
            for category, papers in papers_by_category.items():
                html += f"""
                <div style='margin-top: 30px;'>
                    <h2 style='color:#D4A373; font-size:18px; border-bottom:1px dashed #D4A373; padding-bottom:5px; margin-bottom:15px;'>
                        📂 {category}
                    </h2>
                """

                for p in papers:
                    # 处理标题显示：优先中文，其次英文
                    display_title = p.chinese_title if p.chinese_title else p.title
                    subtitle = p.title if p.chinese_title else ""

                    html += f"""
                    <div style='padding: 15px; margin: 15px 0; background: rgba(255,255,255,0.8); border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);'>
                        <h3 style='margin:0 0 5px 0; color:#1a1a1a; font-size: 16px;'>{display_title}</h3>
                        """

                    if subtitle:
                        html += f"<p style='margin:0 0 10px 0; color:#888; font-size:12px; font-style:italic;'>{subtitle}</p>"

                    html += f"""
                        <p style='color:#333; line-height:1.6; font-size:14px; margin-bottom:10px;'>{p.popular_science}</p>
                        <div style='text-align:right;'>
                            <a href='{p.url}' style='color:#fff; background:#D4A373; text-decoration:none; padding:4px 12px; border-radius:4px; font-size:12px;'>阅读原文 →</a>
                        </div>
                    </div>
                    """

                html += "</div>"  # 结束分类div

            html += """
                <div style='text-align:center; margin-top:40px; border-top:1px solid #ddd; padding-top:20px;'>
                    <p style='color:#999; font-size:12px;'>ArxivMind AI Daily</p>
                </div>
            </div>
            """

            try:
                resend.Emails.send({
                    "from": "ArxivMind <onboarding@resend.dev>",
                    "to": user.email,
                    "subject": f"【ArxivMind】每日精选 - {len(target_papers)}篇新论文",
                    "html": html
                })
                logger.info(f"邮件已发送至: {user.email}")
            except Exception as e:
                logger.error(f"邮件发送失败 ({user.email}): {e}")

    except Exception as e:
        logger.error(f"发送每日邮件异常: {e}")
    finally:
        session.close()

def get_papers_by_category(category: str = None, target_date: date = None) -> list[Paper]:
    """
    根据分类和日期获取论文
    category: 领域分类
    target_date: 具体日期 (datetime.date 对象)
    """
    session = Session()
    try:
        query = session.query(Paper).filter(Paper.batch_status == "completed")

        # 领域筛选
        if category and category != "全部":
            query = query.filter(Paper.category == category)

        # 日期筛选
        if target_date:
            # SQLite 中存储的是 datetime，这里转换一下进行比较
            # 方法：筛选 publish_date 在当天的 00:00:00 到 23:59:59 之间
            start_of_day = datetime.combine(target_date, datetime.min.time())
            end_of_day = datetime.combine(target_date, datetime.max.time())
            query = query.filter(Paper.created_at >= start_of_day, Paper.created_at <= end_of_day)

        # 默认按发布时间降序
        papers = query.order_by(Paper.publish_date.desc()).all()

        for p in papers:
            session.expunge(p)

        return papers

    finally:
        session.close()


def get_earliest_paper_date() -> date:
    """获取数据库中最早的一篇论文日期"""
    session = Session()
    try:
        # 获取最早的 publish_date
        min_date = session.query(func.min(Paper.created_at)).scalar()
        if min_date:
            return min_date.date()
        # 如果数据库为空，默认返回今天
        return datetime.now(timezone.utc).date()
    finally:
        session.close()


def get_recent_donations(limit: int = 50) -> list[Donation]:
    """获取最近的打赏记录"""
    session = Session()
    try:
        # 按时间倒序排列
        donations = session.query(Donation).order_by(Donation.created_at.desc()).limit(limit).all()

        # 脱离 session 以便在前端使用
        for d in donations:
            session.expunge(d)
        return donations
    finally:
        session.close()


def add_donation_record(email: str, amount: str, message: str = None, date_time: datetime = None) -> bool:
    """
    添加一条打赏记录 (管理员用)
    如果不传 date_time，默认使用当前时间
    """
    session = Session()
    try:
        new_donation = Donation(
            email=email,
            amount=amount,
            message=message,
            created_at=date_time if date_time else datetime.now(timezone.utc)
        )
        session.add(new_donation)
        session.commit()
        logger.info(f"新增打赏记录: {email} - {amount}")
        return True
    except Exception as e:
        logger.error(f"添加打赏失败: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def add_comment(user_email: str, paper_id: int, content: str) -> tuple[bool, str]:
    """添加评论"""
    if not content or not content.strip():
        return False, "评论内容不能为空"

    session = Session()
    try:
        user = session.query(User).filter_by(email=user_email).first()
        if not user:
            return False, "用户未找到"

        new_comment = Comment(
            user_id=user.id,
            paper_id=paper_id,
            content=content.strip()
        )
        session.add(new_comment)
        session.commit()
        logger.info(f"用户 {user_email} 评论了论文 {paper_id}")
        return True, "评论发布成功"
    except Exception as e:
        logger.error(f"评论失败: {e}")
        session.rollback()
        return False, "评论发布失败"
    finally:
        session.close()


def get_paper_comments(paper_id: int) -> list[dict]:
    """获取指定论文的评论列表 (按时间倒序)"""
    session = Session()
    try:
        # 预加载 user 信息以避免 N+1 查询问题
        from sqlalchemy.orm import joinedload
        comments = session.query(Comment) \
            .options(joinedload(Comment.user)) \
            .filter(Comment.paper_id == paper_id) \
            .order_by(Comment.created_at.desc()) \
            .all()

        # 转换为字典列表返回，避免 session 关闭后无法访问
        result = []
        for c in comments:
            result.append({
                'user_email': c.user.email if c.user else 'Unknown',
                'content': c.content,
                'created_at': c.created_at
            })
        return result
    finally:
        session.close()


def get_trending_papers(limit: int = 5) -> list[Paper]:
    """
    获取热门论文排行榜
    算法：热度 = 收藏数 * 2 + 评论数 * 1
    """
    session = Session()
    try:
        # 子查询：统计评论数
        comment_counts = session.query(
            Comment.paper_id,
            func.count(Comment.id).label('c_count')
        ).group_by(Comment.paper_id).subquery()

        # 子查询：统计收藏数
        fav_counts = session.query(
            user_favorites.c.paper_id,
            func.count(user_favorites.c.user_id).label('f_count')
        ).group_by(user_favorites.c.paper_id).subquery()

        # 关联查询并排序
        # 注意：这里使用 outerjoin 因为有的论文可能没有评论或收藏
        papers = session.query(Paper) \
            .outerjoin(comment_counts, Paper.id == comment_counts.c.paper_id) \
            .outerjoin(fav_counts, Paper.id == fav_counts.c.paper_id) \
            .filter(Paper.batch_status == 'completed') \
            .order_by((func.coalesce(fav_counts.c.f_count, 0) * 2 + func.coalesce(comment_counts.c.c_count, 0)).desc()) \
            .limit(limit) \
            .all()

        for p in papers:
            session.expunge(p)
        return papers
    finally:
        session.close()

def get_user_favorite_ids(email: str) -> set[int]:
    """一次性获取用户收藏的所有论文 ID"""
    session = Session()
    try:
        user = session.query(User).filter_by(email=email).first()
        if user:
            return {p.id for p in user.favorite_papers} # 返回 ID 集合
        return set()
    finally:
        session.close()
