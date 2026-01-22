import time
from database import logger
from services import send_daily_emails
# 引入新的并发处理函数
from core_batch import fetch_new_papers, process_pending_papers_parallel

def run_daily_pipeline():
    """运行每日情报采集流水线"""
    logger.info("=" * 60)
    logger.info(">>> 启动每日情报采集流水线 (并发版) <<<")
    logger.info("=" * 60)

    # 1. 抓取与同步引用量
    # 这一步会将新论文存入数据库，并设置 batch_status='pending'
    logger.info("[Step 1/3] 开始抓取 Arxiv 论文...")
    try:
        fetch_new_papers()
    except Exception as e:
        logger.error(f"抓取阶段发生致命错误: {e}")
        return

    # 2. 执行并发 AI 分析
    # 这一步会查询 batch_status='pending' 的论文进行分析，并更新为 'completed'
    logger.info("[Step 2/3] 开始 AI 并发分析...")
    try:
        process_pending_papers_parallel()
    except Exception as e:
        logger.error(f"分析阶段发生致命错误: {e}")
        # 如果分析失败，可以选择是否继续发邮件（发旧数据），这里选择中止
        return

    # 3. 推送邮件
    # 此时数据库中应该已经有了分析好的数据
    logger.info("[Step 3/3] 情报准备就绪，开始推送邮件...")
    try:
        send_daily_emails()
    except Exception as e:
        logger.error(f"邮件发送阶段发生致命错误: {e}")

    logger.info("=" * 60)
    logger.info(">>> 每日流水线执行完毕 <<<")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_daily_pipeline()