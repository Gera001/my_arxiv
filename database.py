import logging
# 1. 引入 timezone
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ArxivMind")

Base = declarative_base()

# 2. 定义一个获取当前 UTC 时间的辅助函数
def get_utc_now():
    return datetime.now(timezone.utc)

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


engine = create_engine('sqlite:///arxiv_mind_qwen.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
logger.info("Database & Models initialized.")