import os
import json
import time
import arxiv
import requests
import fitz
import backoff
from pathlib import Path
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from database import Session, Paper, logger
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 控制并发线程数，建议根据 DashScope 的 TPM/RPM 限制调整
MAX_WORKERS = 3


@backoff.on_exception(backoff.expo, requests.exceptions.RequestException, max_tries=3)
def get_semantic_scholar_free(arxiv_id: str) -> dict | None:
    """
    免费版 Semantic Scholar 调用逻辑
    """
    paper_id = f"ArXiv:{arxiv_id}"
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
    params = {'fields': 'citationCount,influentialCitationCount'}

    try:
        # 适当降低休眠时间，因为这通常是在单独的抓取流程中
        time.sleep(20)
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            logger.info(f"Semantic Scholar 数据获取成功: {arxiv_id}")
            return response.json()
        elif response.status_code == 429:
            logger.warning(f"Semantic Scholar 触发频率限制，跳过引用抓取: {arxiv_id}")
        else:
            logger.warning(f"Semantic Scholar 返回状态码 {response.status_code}: {arxiv_id}")
    except Exception as e:
        logger.error(f"Semantic Scholar 数据同步异常 ({arxiv_id}): {e}")
    return None

def clean_text_for_db(text: str) -> str:
    """清洗文本，移除 PostgreSQL 不支持的 NUL 字符"""
    if not text:
        return text
    return text.replace("\x00", "")

def fetch_new_papers():
    """抓取 Arxiv 最新论文"""
    session = Session()
    arxiv_client = arxiv.Client()
    search = arxiv.Search(
        query="cat:cs.AI",
        max_results=50,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )

    logger.info(">>> 开始抓取 Arxiv 最新论文...")
    new_count = 0

    for result in arxiv_client.results(search):
        if session.query(Paper).filter(Paper.url == result.pdf_url).first():
            logger.debug(f"论文已存在，跳过: {result.title[:50]}...")
            continue

        try:
            logger.info(f"处理中: {result.title[:60]}...")

            # 1. 抓取正文
            resp = requests.get(result.pdf_url, timeout=60)
            with fitz.open(stream=resp.content, filetype="pdf") as doc:
                text = "".join([p.get_text() for p in doc[:8]])

            # 2. 调用免费版 SS 获取引用
            arxiv_id = result.entry_id.split('/')[-1]
            # ss_data = get_semantic_scholar_free(arxiv_id) or {}
            ss_data = {}

            new_p = Paper(
                title=result.title,
                url=result.pdf_url,
                publish_date=result.published,
                full_text_tmp=clean_text_for_db(text),
                citation_count=ss_data.get('citationCount', 0),
                influential_citation_count=ss_data.get('influentialCitationCount', 0),
                # 标记该字段为空，表示待分析（或者你可以保留 batch_status 字段并设为 pending）
                batch_status="pending",
                analysis_json=None
            )
            session.add(new_p)
            session.commit()
            new_count += 1
            logger.info(f"论文入库成功: {result.title[:50]}...")

        except Exception as e:
            logger.error(f"论文处理失败 ({result.title[:30]}...): {e}")
            session.rollback()

    logger.info(f">>> 本次成功入库 {new_count} 篇论文")
    session.close()


@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def analyze_single_paper(paper_id: int, title: str, text: str) -> dict:
    """
    单篇论文分析逻辑 (LLM 调用)
    """
    logger.info(f"正在分析论文 [ID:{paper_id}]: {title[:30]}...")

    prompt = f"""你是一个资深的 AI 领域科普专家。请阅读论文全文，输出一份详细的 JSON 报告。
要求：内容完整详细，使用中文。

1. category: 从以下选项中选择最匹配的领域（只能选一个）：语言模型/推理模型、视觉模型/多模态、AI Agent/智能体、推荐搜索、自动驾驶、传统机器学习、其他
2. motivation: 详细说明研究动机，解决了什么痛点？
3. method: 深入浅出描述研究方法。
4. result: 列出关键实验结果和性能指标。
5. implementation_example: 【具体实现思路举例】请用一个简单的例子说明论文的方法是如何一步步实现的，就像向开发者演示 Demo 逻辑一样。
6. popular_science: 【论文科普】请用非常通俗易懂的语言（例如：打比方）向非专业人士解释这篇论文到底做了什么，它的意义在哪里。
7. keywords: 3-5个英文关键词(逗号分隔)。

论文标题: {title}
内容正文: {text[:30000]}
"""

    response = client.chat.completions.create(
        model="qwen-plus",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        # 可以适当增加 temperature 让解释更生动
        temperature=0.3
    )

    result_text = response.choices[0].message.content
    try:
        return json.loads(result_text)
    except json.JSONDecodeError:
        logger.error(f"JSON 解析失败 [ID:{paper_id}]")
        raise Exception("LLM output is not valid JSON")


def process_pending_papers_parallel():
    """并发处理 Pending 状态的论文"""
    session = Session()

    # --- 关键修改：直接使用 batch_status 字段过滤 ---
    # 这样能 100% 确保抓取进来状态为 pending 的论文被选中
    papers = session.query(Paper).filter(Paper.batch_status == "pending").all()

    if not papers:
        logger.info("当前没有 batch_status='pending' 的任务")
        session.close()
        return

    logger.info(f">>> [Step 2] 开始并发分析，待处理: {len(papers)} 篇")

    # 提取数据到内存，与 Session 解绑
    tasks = []
    for p in papers:
        # 只有当有文本时才分析
        if p.full_text_tmp:
            tasks.append({"id": p.id, "title": p.title, "text": p.full_text_tmp})
        else:
            # 如果没有文本但状态是 pending，标记为 failed 防止死循环
            p.batch_status = "failed_no_text"
            session.commit()

    session.close()  # 关闭主 Session

    success_count = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_id = {
            executor.submit(analyze_single_paper, t["id"], t["title"], t["text"]): t["id"]
            for t in tasks
        }

        for future in as_completed(future_to_id):
            p_id = future_to_id[future]
            try:
                data = future.result()

                # 独立 Session 更新，避免 SQLite 锁冲突
                update_session = Session()
                p = update_session.query(Paper).get(p_id)
                if p:
                    p.category = data.get('category', 'AI')
                    p.popular_science = data.get('popular_science', '')
                    p.keywords = data.get('keywords', '')
                    p.analysis_json = data
                    # 完成后状态流转
                    p.batch_status = "completed"
                    # 清空临时大文本
                    p.full_text_tmp = None

                    update_session.commit()
                    success_count += 1
                    logger.info(f"分析完成 [ID:{p_id}]")
                update_session.close()

            except Exception as e:
                logger.error(f"分析失败 [ID:{p_id}]: {e}")
                # 可选：记录错误状态
                err_session = Session()
                p_err = err_session.query(Paper).get(p_id)
                if p_err:
                    p_err.batch_status = "failed"
                    err_session.commit()
                err_session.close()

    logger.info(f">>> 分析流程结束，成功: {success_count}/{len(tasks)}")

def call_qwen_ai_sync(prompt: str) -> str:
    """用于趋势分析的即时同步调用"""
    try:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt + " (请以 JSON 格式输出结果)"}],
            response_format={"type": "json_object"}
        )
        logger.info("即时 AI 分析完成")
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"即时分析失败: {e}")
        return '{"error": "分析服务暂时不可用"}'


# 示例调用逻辑
if __name__ == "__main__":
    # 1. 抓取
    fetch_new_papers()
    # 2. 并发分析
    process_pending_papers_parallel()
