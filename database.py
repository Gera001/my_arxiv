import logging
import os
import streamlit as st 
# 1. 引入 timezone
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ArxivMind")

Base = declarative_base()

# 2. 定义一个获取当前 UTC 时间的辅助函数
def get_utc_now():
    # 创建一个 UTC+8 的时区对象
    beijing_tz = timezone(timedelta(hours=8))
    return datetime.now(beijing_tz)

user_favorites = Table(
    'user_favorites',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('paper_id', Integer, ForeignKey('papers.id'), primary_key=True),
    # 3. 修改 default
    Column('created_at', DateTime, default=get_utc_now)
)


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
    citation_count = Column(Integer, default=0)
    influential_citation_count = Column(Integer, default=0)
    batch_status = Column(String, default="pending")
    full_text_tmp = Column(Text)
    # 修改 default
    created_at = Column(DateTime, default=get_utc_now)
    chinese_title = Column(String)  # 新增字段
    favorited_by = relationship("User", secondary=user_favorites, back_populates="favorite_papers")


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    subscribed_categories = Column(String, default="")
    is_subscribed = Column(Boolean, default=True)
    # 修改 default
    created_at = Column(DateTime, default=get_utc_now)
    last_login = Column(DateTime)

    favorite_papers = relationship("Paper", secondary=user_favorites, back_populates="favorited_by")


class VerificationCode(Base):
    __tablename__ = 'verification_codes'
    id = Column(Integer, primary_key=True)
    email = Column(String, index=True)
    code = Column(String)
    # 修改 default
    created_at = Column(DateTime, default=get_utc_now)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime)


class Donation(Base):
    __tablename__ = 'donations'
    id = Column(Integer, primary_key=True)
    email = Column(String)
    amount = Column(String)
    message = Column(Text)
    # 修改 default
    created_at = Column(DateTime, default=get_utc_now)


class Comment(Base):
    __tablename__ = 'comments'
    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)  # 评论内容
    created_at = Column(DateTime, default=get_utc_now)  # 评论时间

    # 外键关联
    user_id = Column(Integer, ForeignKey('users.id'))
    paper_id = Column(Integer, ForeignKey('papers.id'))

    # 关系属性 (方便查询)
    user = relationship("User", backref="comments")
    paper = relationship("Paper", backref="comments")


# engine = create_engine('sqlite:///arxiv_mind_qwen.db')
# Base.metadata.create_all(engine)
# Session = sessionmaker(bind=engine)
# logger.info("Database & Models initialized.")
# 优先读取环境变量中的 DATABASE_URL，如果没有则回退到本地 SQLite (方便本地测试)
DATABASE_URL = os.getenv("DATABASE_URL")

@st.cache_resource  # <--- 关键：告诉 Streamlit 把这个连接缓存起来，不要每次都重建
def get_db_engine():
    url = os.getenv("DATABASE_URL")
    if url and url.startswith("postgres"):
        url = url.replace("postgres://", "postgresql://")
        # 加上 pool_pre_ping=True 防止连接因为长时间空闲断开
        return create_engine(url, pool_pre_ping=True)
    else:
        print("⚠️ 使用本地 SQLite 模式")
        return create_engine('sqlite:///arxiv_mind_qwen.db')

# 获取全局唯一的 engine
engine = get_db_engine()

# 确保表存在
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
logger.info("Database & Models initialized.")
