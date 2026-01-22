import os, resend
from database import Session, Paper, User, logger

resend.api_key = os.getenv("RESEND_API_KEY")


def send_daily_emails():
    session = Session()
    users = session.query(User).filter(User.is_subscribed == True).all()
    new_papers = session.query(Paper).filter(Paper.batch_status == "completed").all()

    if not new_papers:
        logger.info("无新完成论文，跳过邮件发送。")
        return

    logger.info(f"准备为 {len(users)} 位用户发送订阅邮件...")
    for user in users:
        # 订阅逻辑筛选
        target_papers = new_papers
        if user.subscribed_categories:
            user_cats = [c.strip() for c in user.subscribed_categories.split(",")]
            target_papers = [p for p in new_papers if p.category in user_cats]

        if target_papers:
            html = "<h2>ArxivMind 每日精选</h2>"
            for p in target_papers:
                html += f"""
                <div style='border-left: 4px solid #4a90e2; padding-left: 10px; margin-bottom: 20px;'>
                    <h4>{p.title}</h4>
                    <p><b>领域:</b> {p.category} | <b>引用量:</b> {p.citation_count}</p>
                    <p>{p.popular_science}</p>
                    <a href='{p.url}'>查看论文原文</a>
                </div><hr>"""
            try:
                resend.Emails.send({
                    "from": "ArxivMind <onboarding@resend.dev>",
                    "to": user.email,
                    "subject": "您的 ArxivMind 每日 AI 简报",
                    "html": html
                })
                logger.info(f"邮件已发送至: {user.email}")
            except Exception as e:
                logger.error(f"邮件发送失败 ({user.email}): {e}")
    session.close()