from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import os
import json
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext
from loguru import logger

from database import get_db, engine
from models import Base, User, Payment, Tariff, Log, Setting
from xui_client import XUIClient
from yookassa_client import YookassaClient

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="VPN Bot API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
ALGORITHM = "HS256"

# Admin credentials
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "123456")

# External services
XUI_URL = os.getenv("XUI_URL")
XUI_TOKEN = os.getenv("XUI_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")

# Initialize clients
yookassa_client = YookassaClient(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY) if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY else None

# Pydantic models
class UserResponse(BaseModel):
    id: int
    telegram_id: str
    email: str
    subscription_active: bool
    subscription_end_date: Optional[datetime]
    total_purchases: float
    renewal_count: int
    config_links: Optional[str]
    created_at: datetime

class PaymentResponse(BaseModel):
    id: int
    yookassa_payment_id: str
    user_id: int
    amount: float
    currency: str
    status: str
    tariff_id: int
    created_at: datetime
    paid_at: Optional[datetime]

class TariffResponse(BaseModel):
    id: int
    name: str
    price: float
    duration_days: int
    inbound_ids: str
    active: bool

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

# Utility functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

def authenticate_user(username: str, password: str):
    if username == ADMIN_LOGIN and password == ADMIN_PASSWORD:
        return {"username": username}
    return False

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return username

def log_action(level: str, message: str, source: str, db: Session):
    log_entry = Log(level=level, message=message, source=source)
    db.add(log_entry)
    db.commit()
    logger.log(level.lower(), f"{source}: {message}")

# Routes
@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(request.username, request.password)
    if not user:
        log_action("WARNING", f"Failed login attempt for user: {request.username}", "AUTH", db)
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": user["username"]})
    log_action("INFO", f"User {request.username} logged in", "AUTH", db)
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users", response_model=List[UserResponse])
async def get_users(
    current_user: str = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.put("/users/{user_id}/extend")
async def extend_user_subscription(
    user_id: int,
    days: int,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.subscription_end_date and user.subscription_end_date > datetime.utcnow():
        user.subscription_end_date += timedelta(days=days)
    else:
        user.subscription_end_date = datetime.utcnow() + timedelta(days=days)
    
    user.subscription_active = True
    user.renewal_count += 1
    db.commit()
    
    log_action("INFO", f"Extended subscription for user {user.telegram_id} by {days} days", "ADMIN", db)
    return {"message": "Subscription extended"}

@app.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    
    log_action("INFO", f"Deleted user {user.telegram_id}", "ADMIN", db)
    return {"message": "User deleted"}

@app.get("/payments", response_model=List[PaymentResponse])
async def get_payments(
    current_user: str = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    payments = db.query(Payment).offset(skip).limit(limit).all()
    return payments

@app.get("/tariffs", response_model=List[TariffResponse])
async def get_tariffs(
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tariffs = db.query(Tariff).filter(Tariff.active == True).all()
    return tariffs

@app.post("/tariffs")
async def create_tariff(
    name: str,
    price: float,
    duration_days: int,
    inbound_ids: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tariff = Tariff(
        name=name,
        price=price,
        duration_days=duration_days,
        inbound_ids=inbound_ids,
        active=True
    )
    db.add(tariff)
    db.commit()
    db.refresh(tariff)
    
    log_action("INFO", f"Created tariff {name}", "ADMIN", db)
    return tariff

@app.get("/logs")
async def get_logs(
    current_user: str = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    logs = db.query(Log).order_by(Log.created_at.desc()).offset(skip).limit(limit).all()
    return logs

@app.get("/dashboard/stats")
async def get_dashboard_stats(
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Today's revenue
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_revenue = db.query(Payment).filter(
        Payment.status == "succeeded",
        Payment.paid_at >= today_start
    ).with_entities(db.func.sum(Payment.amount)).scalar() or 0

    # Active users
    active_users = db.query(User).filter(User.subscription_active == True).count()

    # Total payments
    total_payments = db.query(Payment).filter(Payment.status == "succeeded").count()

    return {
        "today_revenue": today_revenue,
        "active_users": active_users,
        "total_payments": total_payments
    }

# Payment routes
@app.post("/payments/create")
async def create_payment(
    tariff_id: int,
    telegram_id: str,
    db: Session = Depends(get_db)
):
    if not yookassa_client:
        raise HTTPException(status_code=500, detail="Yookassa not configured")

    # Get tariff
    tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
    if not tariff:
        raise HTTPException(status_code=404, detail="Tariff not found")

    # Get or create user
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, email=f"{telegram_id}@vpn.local")
        db.add(user)
        db.commit()
        db.refresh(user)

    # Create payment in Yookassa
    payment_data = yookassa_client.create_payment(tariff.price, description=f"VPN Subscription - {tariff.name}")

    # Save payment in DB
    payment = Payment(
        yookassa_payment_id=payment_data["payment_id"],
        user_id=user.id,
        amount=tariff.price,
        status="pending",
        tariff_id=tariff_id
    )
    db.add(payment)
    db.commit()

    log_action("INFO", f"Created payment {payment_data['payment_id']} for user {telegram_id}", "PAYMENT", db)

    return {
        "payment_id": payment_data["payment_id"],
        "confirmation_url": payment_data["confirmation_url"],
        "amount": payment_data["amount"]
    }

@app.post("/payments/yookassa/webhook")
async def yookassa_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        payment_id = data.get("object", {}).get("id")
        status = data.get("object", {}).get("status")

        if not payment_id or not status:
            raise HTTPException(status_code=400, detail="Invalid webhook data")

        # Update payment status
        payment = db.query(Payment).filter(Payment.yookassa_payment_id == payment_id).first()
        if not payment:
            log_action("WARNING", f"Received webhook for unknown payment {payment_id}", "WEBHOOK", db)
            return {"status": "ok"}

        old_status = payment.status
        payment.status = status
        if status == "succeeded":
            payment.paid_at = datetime.utcnow()

            # Activate subscription
            user = db.query(User).filter(User.id == payment.user_id).first()
            tariff = db.query(Tariff).filter(Tariff.id == payment.tariff_id).first()

            if user and tariff:
                # Calculate expiry date
                if user.subscription_end_date and user.subscription_end_date > datetime.utcnow():
                    user.subscription_end_date += timedelta(days=tariff.duration_days)
                else:
                    user.subscription_end_date = datetime.utcnow() + timedelta(days=tariff.duration_days)

                user.subscription_active = True
                user.total_purchases += tariff.price
                user.renewal_count += 1

                # Create client in 3X-UI
                if XUI_URL and XUI_TOKEN:
                    inbound_ids = [int(x.strip()) for x in tariff.inbound_ids.split(',') if x.strip()]
                    async with XUIClient(XUI_URL, XUI_TOKEN) as xui:
                        result = await xui.create_or_update_client(inbound_ids, user.email, tariff.duration_days)
                        user.config_links = json.dumps(result)

                db.commit()

                log_action("INFO", f"Activated subscription for user {user.telegram_id}, payment {payment_id}", "WEBHOOK", db)

        db.commit()

        log_action("INFO", f"Payment {payment_id} status changed from {old_status} to {status}", "WEBHOOK", db)

        return {"status": "ok"}

    except Exception as e:
        log_action("ERROR", f"Webhook processing failed: {str(e)}", "WEBHOOK", db)
        raise HTTPException(status_code=500, detail="Webhook processing failed")

@app.post("/bot/webhook")
async def bot_webhook(request: Request):
    # This will be handled by the bot service
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)