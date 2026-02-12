from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean, BigInteger
from sqlalchemy import Identity
from sqlalchemy.sql import func

from .db import Base


class FormModel(Base):
    __tablename__ = 'Recruitment_forms'

    id = Column(Integer, Identity(start=1, cycle=False), primary_key=True, index=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    username = Column(String(64), nullable=False)
    role = Column(String(32), nullable=False)
    content = Column(JSON, nullable=False, default=dict)
    status = Column(Boolean, nullable=True, default=None)
    cooldown = Column(Boolean, default=True)
    assigned_to = Column(String(64), default='', nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserModel(Base):
    __tablename__ = 'Users'

    id = Column(Integer, Identity(start=1, cycle=False), primary_key=True, index=True)
    user_id = Column(BigInteger, index=True, nullable=False, unique=True)
    username = Column(String(64), nullable=False)
    role = Column(String(32), nullable=True)
    assigned_to = Column(String(64), default='', nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class StaffModel(Base):
    __tablename__ = 'Staff'

    id = Column(Integer, Identity(start=1, cycle=False), primary_key=True, index=True)
    username = Column(String(64), nullable=False)
    role = Column(String(32), nullable=False)
    agent_need = Column(Boolean, default=True, nullable=False)
    operator_need = Column(Boolean, default=True, nullable=False)
    assigned_to = Column(String(64), default='', nullable=False, index=True)
    actual = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

