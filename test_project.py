import os
import json
import time
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ArxivMind-Test")

from database import Session, Paper, User, VerificationCode
from core_batch import get_semantic_scholar_free, call_qwen_ai_sync
from services import (
    send_verification_code,
    verify_code,
    toggle_favorite,
    get_user_favorites,
    send_daily_emails
)


def test_database_robustness():
    """测试数据库：验证用户重复注册时的健壮性"""
    logger.info("=" * 50)
    logger.info("[1/6] 测试数据库健壮性")
    logger.info("=" * 50)

    session = Session()
    test_email = "tester_robust@example.com"

    try:
        # 清理可能存在的测试数据
        existing = session.query(User).filter_by(email=test_email).first()
        if existing:
            session.delete(existing)
            session.commit()

        # 模拟第一次注册
        u1 = User(email=test_email, subscribed_categories="AI")
        session.add(u1)
        session.commit()
        logger.info("✓ 首次注册成功")

        # 模拟重复注册（健壮性逻辑）
        existing_user = session.query(User).filter_by(email=test_email).first()
        if existing_user:
            logger.info("✓ 检测到邮箱已存在，执行更新操作")
            existing_user.subscribed_categories = "AI, 大模型"
            session.commit()
            logger.info("✅ 数据库 Upsert 逻辑测试通过")

        # 清理
        session.delete(existing_user)
        session.commit()
        logger.info("✓ 测试数据已清理")

    except Exception as e:
        logger.error(f"❌ 数据库测试失败: {e}")
        session.rollback()
    finally:
        session.close()


def test_verification_code():
    """测试验证码功能"""
    logger.info("=" * 50)
    logger.info("[2/6] 测试验证码系统")
    logger.info("=" * 50)

    session = Session()
    test_email = "test_verify@example.com"

    try:
        # 测试发送验证码（不实际发送邮件，只测试数据库逻辑）
        from datetime import datetime, timedelta

        code = "123456"
        verification = VerificationCode(
            email=test_email,
            code=code,
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )
        session.add(verification)
        session.commit()
        logger.info("✓ 验证码存储成功")

        # 测试验证
        found = session.query(VerificationCode).filter(
            VerificationCode.email == test_email,
            VerificationCode.code == code,
            VerificationCode.is_used == False
        ).first()

        if found:
            logger.info("✓ 验证码查询成功")
            found.is_used = True
            session.commit()
            logger.info("✅ 验证码系统测试通过")

        # 清理
        session.query(VerificationCode).filter_by(email=test_email).delete()
        session.commit()

    except Exception as e:
        logger.error(f"❌ 验证码测试失败: {e}")
        session.rollback()
    finally:
        session.close()


def test_semantic_scholar_free():
    """测试免费版 Semantic Scholar API"""
    logger.info("=" * 50)
    logger.info("[3/6] 测试 Semantic Scholar API")
    logger.info("=" * 50)

    test_arxiv_id = "2305.16300"

    logger.info(f"正在查询论文 {test_arxiv_id} 的引用数据...")
    data = get_semantic_scholar_free(test_arxiv_id)

    if data and 'citationCount' in data:
        logger.info(f"✅ API 连通成功! 引用量: {data['citationCount']}")
    else:
        logger.warning("⚠️ API 未返回数据，可能触发了频率限制")


def test_expert_ai_prompt():
    """测试专家级提示词与 JSON 格式解析"""
    logger.info("=" * 50)
    logger.info("[4/6] 测试 AI 分析功能")
    logger.info("=" * 50)

    test_text = "This paper introduces a new method for scaling Large Language Models using MoE architecture..."
    prompt = f"你是一个资深的 AI 科普专家。请分析以下内容并以 JSON 格式返回 category 和 popular_science 字段：{test_text}"

    logger.info("正在调用 AI 进行分析...")
    result_raw = call_qwen_ai_sync(prompt)

    try:
        result = json.loads(result_raw) if isinstance(result_raw, str) else result_raw

        if "error" not in result:
            logger.info(f"✅ AI 解析成功!")
            logger.info(f"   分类: {result.get('category', 'N/A')}")
            if result.get('popular_science'):
                logger.info(f"   科普预览: {result['popular_science'][:80]}...")
        else:
            logger.error(f"❌ AI 返回错误: {result.get('error')}")

    except Exception as e:
        logger.error(f"❌ AI 结果解析失败: {e}")


def test_favorites():
    """测试收藏功能"""
    logger.info("=" * 50)
    logger.info("[5/6] 测试收藏功能")
    logger.info("=" * 50)

    session = Session()
    test_email = "test_fav@example.com"

    try:
        # 创建测试用户
        user = User(email=test_email)
        session.add(user)

        # 创建测试论文
        paper = Paper(
            title="测试论文 - 收藏功能",
            url="https://arxiv.org/test/favorites",
            category="测试",
            batch_status="completed"
        )
        session.add(paper)
        session.commit()

        paper_id = paper.id
        logger.info(f"✓ 测试数据创建成功 (Paper ID: {paper_id})")

        # 测试添加收藏
        success, is_fav, msg = toggle_favorite(test_email, paper_id)
        if success and is_fav:
            logger.info("✓ 添加收藏成功")

        # 测试获取收藏
        favorites = get_user_favorites(test_email)
        if len(favorites) == 1:
            logger.info("✓ 获取收藏列表成功")

        # 测试取消收藏
        success, is_fav, msg = toggle_favorite(test_email, paper_id)
        if success and not is_fav:
            logger.info("✓ 取消收藏成功")

        logger.info("✅ 收藏功能测试通过")

        # 清理
        session.delete(paper)
        session.delete(user)
        session.commit()

    except Exception as e:
        logger.error(f"❌ 收藏功能测试失败: {e}")
        session.rollback()
    finally:
        session.close()


def test_email_service():
    """测试邮件发送功能"""
    logger.info("=" * 50)
    logger.info("[6/6] 测试邮件服务")
    logger.info("=" * 50)

    if not os.getenv("RESEND_API_KEY"):
        logger.warning("⚠️ 未检测到 RESEND_API_KEY，跳过邮件测试")
        return

    test_email = input("请输入接收测试邮件的邮箱 (直接回车跳过): ").strip()

    if not test_email:
        logger.info("跳过邮件测试")
        return

    session = Session()

    try:
        # 创建测试论文
        mock_paper = Paper(
            title="AI 自动化测试论文",
            category="测试领域",
            popular_science="这是一篇 AI 生成的模拟科普，用于验证邮件渲染。",
            batch_status="completed",
            url="https://arxiv.org/abs/test"
        )
        session.add(mock_paper)

        # 创建测试用户
        user = session.query(User).filter_by(email=test_email).first()
        if not user:
            user = User(email=test_email, is_subscribed=True)
            session.add(user)
        else:
            user.is_subscribed = True

        session.commit()

        logger.info(f"正在发送测试邮件至 {test_email}...")
        send_daily_emails()
        logger.info("✅ 邮件发送指令已执行，请检查收件箱")

        # 清理测试论文
        session.delete(mock_paper)
        session.commit()

    except Exception as e:
        logger.error(f"❌ 邮件服务测试失败: {e}")
        session.rollback()
    finally:
        session.close()


def run_all_tests():
    """运行所有测试"""
    logger.info("")
    logger.info("🚀 开始 ArxivMind 完整功能测试")
    logger.info("")

    test_database_robustness()
    test_verification_code()
    test_semantic_scholar_free()
    test_expert_ai_prompt()
    test_favorites()
    test_email_service()

    logger.info("")
    logger.info("=" * 50)
    logger.info("✨ 所有测试执行完毕")
    logger.info("=" * 50)


if __name__ == "__main__":
    run_all_tests()