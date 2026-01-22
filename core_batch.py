import os, json, arxiv, requests, fitz, backoff, logging, time
from pathlib import Path
from openai import OpenAI
from database import Session, Paper, logger
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


@backoff.on_exception(backoff.expo, requests.exceptions.RequestException, max_tries=3)
def get_semantic_scholar_free(arxiv_id):
    """
    免费版 Semantic Scholar 调用逻辑
    无需 API Key，通过 arxiv_id 直接获取引用元数据
    """
    # 构造 Semantic Scholar 识别的 Arxiv 资源 ID
    paper_id = f"ArXiv:{arxiv_id}"
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
    params = {'fields': 'citationCount,influentialCitationCount'}

    try:
        # 免费版建议增加短延迟，防止请求过快被封 IP
        time.sleep(15)
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            logger.warning(f"Semantic Scholar 触发频率限制，跳过引用抓取。")
    except Exception as e:
        logger.error(f"Semantic Scholar 数据同步异常: {e}")
    return None


def fetch_new_papers():
    session = Session()
    arxiv_client = arxiv.Client()
    # 每次抓取 5-10 篇，保证免费 API 稳定性
    search = arxiv.Search(query="cat:cs.AI", max_results=8, sort_by=arxiv.SortCriterion.SubmittedDate)

    logger.info(">>> 开始抓取 Arxiv 最新论文...")
    new_count = 0
    for result in arxiv_client.results(search):
        if session.query(Paper).filter(Paper.url == result.pdf_url).first():
            continue

        try:
            logger.info(f"处理中: {result.title}")
            # 1. 抓取正文
            resp = requests.get(result.pdf_url, timeout=30)
            with fitz.open(stream=resp.content, filetype="pdf") as doc:
                text = "".join([p.get_text() for p in doc[:8]])

            # 2. 调用免费版 SS 获取引用
            arxiv_id = result.entry_id.split('/')[-1]
            ss_data = get_semantic_scholar_free(arxiv_id) or {}

            new_p = Paper(
                title=result.title,
                url=result.pdf_url,
                publish_date=result.published,
                full_text_tmp=text,
                citation_count=ss_data.get('citationCount', 0),
                influential_citation_count=ss_data.get('influentialCitationCount', 0)
            )
            session.add(new_p)
            session.commit()
            new_count += 1
        except Exception as e:
            logger.error(f"论文 {result.title} 处理失败: {e}")
            session.rollback()

    logger.info(f"本次成功入库 {new_count} 篇论文。")
    session.close()


def submit_batch_job():
    session = Session()
    papers = session.query(Paper).filter(Paper.batch_status == "pending").all()
    if not papers:
        logger.info("没有待处理的 pending 任务。")
        return None

    jsonl_path = "batch_input.jsonl"
    logger.info(f"正在为 {len(papers)} 篇论文生成 AI 任务清单...")

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for p in papers[:1]:
            # 使用用户要求的资深专家 Prompt
            line = {
                "custom_id": str(p.id),
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": "qwen-plus",
                    "messages": [{"role": "user", "content": f"""你是一个资深的 AI 科普专家。请输出一份详细的 JSON 报告。

1. category: 5字以内的研究领域分类。
2. motivation: 详细说明研究动机，解决了什么痛点？
3. method: 深入浅出描述研究方法。
4. result: 列出关键实验结果和性能指标。
5. implementation_example: 【具体实现思路举例】。请用一个简单的例子说明论文的方法是如何一步步实现的，就像向开发者演示 Demo 逻辑一样。
6. popular_science: 论文科普】。请用非常通俗易懂的语言（例如：打比方）向非专业人士解释这篇论文到底做了什么，它的意义在哪里。
7. keywords: 3-5个英文关键词(逗号分隔)。

论文标题: {p.title}
内容正文: {p.full_text_tmp[:28000]}
"""}],
                    "response_format": {"type": "json_object"}
                }
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    file_obj = client.files.create(file=Path(jsonl_path), purpose="batch")
    batch = client.batches.create(input_file_id=file_obj.id, endpoint="/v1/chat/completions", completion_window="24h")

    for p in papers: p.batch_status = "processing"
    session.commit()
    logger.info(f"通义千问 Batch 任务已提交: {batch.id}")
    session.close()
    return batch.id


def poll_and_save_batch(batch_id):
    logger.info(f"检查 Batch 任务状态: {batch_id}")
    try:
        batch = client.batches.retrieve(batch_id)
        if batch.status == "completed":
            content = client.files.content(batch.output_file_id)
            session = Session()
            for line in content.text.strip().split('\n'):
                res = json.loads(line)
                data = json.loads(res['response']['body']['choices'][0]['message']['content'])
                p = session.query(Paper).get(int(res['custom_id']))
                if p:
                    p.category = data.get('category', 'AI')
                    p.popular_science = data.get('popular_science', '')
                    p.keywords = data.get('keywords', '')
                    p.analysis_json = data
                    p.batch_status, p.full_text_tmp = "completed", None
            session.commit()
            session.close()
            logger.info("Batch 数据同步回数据库成功。")
            return True
        logger.info(f"任务尚未完成，状态: {batch.status}")
    except Exception as e:
        logger.error(f"同步 Batch 结果失败: {e}")
    return False


def call_qwen_ai_sync(prompt):
    """用于趋势分析的即时同步调用"""
    try:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt + " (请以 JSON 格式输出结果)"}],
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"即时分析失败: {e}")
        return "分析服务暂时不可用。"