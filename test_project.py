import os
import json
import time
import logging
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ArxivMind-Test")

from database import Session, Paper, User
from core_batch import get_semantic_scholar_free, call_qwen_ai_sync
from services import send_daily_emails


def test_database_robustness():
    """测试数据库：验证用户重复注册时的健壮性"""
    logger.info("--- [1/5] 测试数据库健壮性 ---")
    session = Session()
    test_email = "tester_robust@example.com"
    try:
        # 模拟第一次注册
        u1 = User(email=test_email, subscribed_categories="AI")
        session.add(u1)
        session.commit()
        logger.info("首次注册成功")

        # 模拟重复注册（健壮性逻辑）
        existing_user = session.query(User).filter_by(email=test_email).first()
        if existing_user:
            logger.info("检测到邮箱已存在，正在执行更新而非插入...")
            existing_user.subscribed_categories = "AI, 大模型"
            session.commit()
            logger.info("✅ 数据库 Upsert 逻辑通过")

        # 清理
        session.delete(existing_user)
        session.commit()
    except Exception as e:
        logger.error(f"❌ 数据库测试失败: {e}")
        session.rollback()
    finally:
        session.close()


def test_semantic_scholar_free():
    """测试免费版 Semantic Scholar API"""
    logger.info("\n--- [2/5] 测试免费版 Semantic Scholar API ---")
    test_arxiv_id = "2305.16300"  # 这是一个经典的论文 ID
    data = get_semantic_scholar_free(test_arxiv_id)
    if data and 'citationCount' in data:
        logger.info(f"✅ API 连通成功! 论文 {test_arxiv_id} 的引用量为: {data['citationCount']}")
    else:
        logger.warning("❓ API 未返回数据，可能是触发了频率限制或 ID 错误")


def test_expert_ai_prompt():
    """测试专家级提示词与 JSON 格式解析"""
    logger.info("\n--- [3/5] 测试专家级 AI 提示词 ---")
    test_text = "This paper introduces a new method for scaling Large Language Models using MoE architecture..."
    # 模拟 core_batch 中的专家 Prompt
    prompt = f"你是一个资深的 AI 科普专家。请分析以下内容并以 JSON 格式返回：{test_text}"

    result_raw = call_qwen_ai_sync(prompt)
    try:
        if isinstance(result_raw, str):
            result = json.loads(result_raw)
        else:
            result = result_raw

        if "popular_science" in result:
            logger.info(f"✅ AI 解析成功! 分类: {result.get('category')}")
            logger.info(f"科普摘要预览: {result.get('popular_science')[:50]}...")
        else:
            logger.error("❌ AI 返回格式不完整")
    except Exception as e:
        logger.error(f"❌ AI 解析失败: {e}")


def test_email_service():
    """测试邮件发送功能"""
    logger.info("\n--- [4/5] 测试邮件推送服务 ---")
    if not os.getenv("RESEND_API_KEY"):
        logger.error("未检测到 RESEND_API_KEY")
        return

    session = Session()
    test_email = input("请输入用于接收测试邮件的真实邮箱: ")
    try:
        # 1. 创建模拟论文
        mock_p = Paper(
            title="AI 自动化测试论文",
            category="测试领域",
            popular_science="这是一篇 AI 生成的模拟科普，用于验证邮件渲染。",
            batch_status="completed",
            url="https://arxiv.org/abs/test"
        )
        session.add(mock_p)

        # 2. 创建/更新测试用户
        u = session.query(User).filter_by(email=test_email).first()
        if not u:
            u = User(email=test_email, is_subscribed=True)
            session.add(u)
        else:
            u.is_subscribed = True

        session.commit()

        logger.info(f"正在发送邮件至 {test_email}...")
        send_daily_emails()
        logger.info("✅ 邮件指令已发出，请检查收件箱")

        # 清理
        session.delete(mock_p)
        session.commit()
    except Exception as e:
        logger.error(f"❌ 邮件服务测试失败: {e}")
    finally:
        session.close()


def test_full_integrated_flow():
    """全流程冒烟测试：从模拟入库到 AI 同步处理到邮件"""
    logger.info("\n--- [5/5] 全流程集成测试 (集成所有新逻辑) ---")
    session = Session()
    try:
        # 1. 模拟论文入库
        paper_title = "集成测试论文_" + str(int(time.time()))
        new_paper = Paper(
            title=paper_title,
            url="https://arxiv.org/test/" + paper_title,
            full_text_tmp="这是模拟的论文正文内容，关于 AI 智能体（Agent）的最新研究。",
            batch_status="pending"
        )
        session.add(new_paper)
        session.commit()
        logger.info(f"模拟论文 {paper_title} 已存入")

        # 2. 调用同步 AI 处理 (专家 Prompt)
        logger.info("正在调用 AI 进行深度分析...")
        res = call_qwen_ai_sync(f"标题: {new_paper.title}\n内容: {new_paper.full_text_tmp}")

        if res:
            data = json.loads(res) if isinstance(res, str) else res
            new_paper.category = data.get('category', 'AI')
            new_paper.popular_science = data.get('popular_science', '')
            new_paper.analysis_json = data
            new_paper.batch_status = "completed"
            session.commit()
            logger.info("✅ AI 处理完成并回填数据库")

            # 3. 触发邮件
            send_daily_emails()
            logger.info("✅ 全流程集成测试指令完成")

        # 清理测试数据
        session.delete(new_paper)
        session.commit()
    except Exception as e:
        logger.error(f"❌ 集成测试失败: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    logger.info("🚀 开始 ArxivMind 健壮性全套测试")

    # 你可以根据需要注释掉部分测试
    test_database_robustness()
    test_semantic_scholar_free()
    test_expert_ai_prompt()
    test_email_service()
    test_full_integrated_flow()

    logger.info("\n✨ 所有测试执行完毕")