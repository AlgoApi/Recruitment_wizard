from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean, BigInteger
from sqlalchemy import Identity
from sqlalchemy.sql import func

from .db import Base


class FormModel(Base):
    __tablename__ = 'Recruitment_forms'

    id = Column(Integer, Identity(start=1, cycle=False), primary_key=True, index=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    username = Column(String, nullable=False)
    role = Column(String, nullable=False)
    content = Column(JSON, nullable=False, default={})
    status = Column(Boolean, nullable=True, default=None)
    assigned_to = Column(String, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
