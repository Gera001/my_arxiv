import os
from database import logger
from core_batch import fetch_new_papers, submit_batch_job, poll_and_save_batch
from services import send_daily_emails


# def run():
#     logger.info("=== ArxivMind 自动化流水线开始运行 ===")
#
#     # 1. 回收旧任务并发邮件
#     if os.path.exists("last_batch_id.txt"):
#         with open("last_batch_id.txt", "r") as f:
#             bid = f.read().strip()
#         if bid:
#             if poll_and_save_batch(bid):
#                 send_daily_emails()
#                 with open("last_batch_id.txt", "w") as f: f.write("")  # 清空
#
#     # 2. 抓取新论文并关联免费 Semantic Scholar 数据
#     fetch_new_papers()
#
#     # 3. 提交新的 Batch 分析
#     new_bid = submit_batch_job()
#     if new_bid:
#         with open("last_batch_id.txt", "w") as f:
#             f.write(new_bid)
#
#     logger.info("=== 流水线执行结束 ===")
#
#
# if __name__ == "__main__":
#     run()
import schedule
import time
import logging
from core_batch import fetch_new_papers, submit_batch_job, poll_and_save_batch
from services import send_daily_emails
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ArxivMind-Scheduler")


def job():
    logger.info("开始执行每日定时任务...")
    # 1. 回收昨天的任务
    if os.path.exists("last_batch_id.txt"):
        with open("last_batch_id.txt", "r") as f:
            bid = f.read().strip()
        if bid and poll_and_save_batch(bid):
            send_daily_emails()
            with open("last_batch_id.txt", "w") as f: f.write("")

    # 2. 抓取新论文
    fetch_new_papers()

    # 3. 提交新任务
    new_bid = submit_batch_job()
    if new_bid:
        with open("last_batch_id.txt", "w") as f:
            f.write(new_bid)
    logger.info("每日任务执行完毕。")


# --- 定时设置 ---
# 设定每天凌晨 00:00 执行
schedule.every().day.at("10:00").do(job)

if __name__ == "__main__":
    logger.info("ArxivMind 定时调度器已启动，等待每天 00:00 执行...")
    # 启动时可以先跑一次，确保逻辑没问题
    # job()

    while True:
        schedule.run_pending()
        time.sleep(60)  # 每分钟检查一次时间