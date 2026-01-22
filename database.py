import logging
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 统一日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ArxivMind")

Base = declarative_base()

class Paper(Base):
    __tablename__ = 'papers'
    id = Column(Integer, primary_key=True)
    title = Column(String)
    url = Column(String, unique=True)
    publish_date = Column(DateTime)
    category = Column(String)
    popular_science = Column(Text)
    analysis_json = Column(JSON)
    keywords = Column(String)
    citation_count = Column(Integer, default=0) # 语义学者提供的总引用
    influential_citation_count = Column(Integer, default=0) # 有影响力引用
    batch_status = Column(String, default="pending")
    full_text_tmp = Column(Text)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    subscribed_categories = Column(String, default="")
    is_subscribed = Column(Boolean, default=True)

engine = create_engine('sqlite:///arxiv_mind_qwen.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
logger.info("Database & Models initialized.")