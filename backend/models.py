from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)  # Used as client email in 3X-UI
    subscription_active = Column(Boolean, default=False)
    subscription_end_date = Column(DateTime, nullable=True)
    total_purchases = Column(Float, default=0.0)
    renewal_count = Column(Integer, default=0)
    config_links = Column(Text, nullable=True)  # JSON string of config links
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    yookassa_payment_id = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    currency = Column(String, default="RUB")
    status = Column(String)  # pending, succeeded, canceled
    tariff_id = Column(Integer, ForeignKey("tariffs.id"))
    created_at = Column(DateTime, server_default=func.now())
    paid_at = Column(DateTime, nullable=True)

    user = relationship("User")
    tariff = relationship("Tariff")

class Tariff(Base):
    __tablename__ = "tariffs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    price = Column(Float)
    duration_days = Column(Integer)
    inbound_ids = Column(String)  # Comma-separated inbound IDs
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String)  # INFO, ERROR, WARNING
    message = Column(Text)
    source = Column(String)  # API, WEBHOOK, BOT, etc.
    created_at = Column(DateTime, server_default=func.now())

class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True)
    value = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())