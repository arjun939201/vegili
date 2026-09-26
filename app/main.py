import os, secrets, smtplib, hashlib, hmac
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, String, Text, DateTime, ForeignKey, Boolean, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vegili.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(os.getenv("SECRET_KEY", "dev-only-change-me"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
OTP_DEV = os.getenv("EMAIL_OTP_DEV_MODE", "false").lower() == "true"
otp_store = {}

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    vegili_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("requester_id", "receiver_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    receiver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    receiver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(String(4000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)
app = FastAPI(title="Vegili", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

def db_session():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def user_from_cookie(request: Request, db: Session):
    token = request.cookies.get("vegili_session")
    if not token: return None
    try:
        data = serializer.loads(token, max_age=60*60*24*14)
        return db.get(User, int(data["uid"]))
    except (BadSignature, SignatureExpired, ValueError, KeyError, TypeError):
        return None

def current_user(request: Request, db: Session = Depends(db_session)):
    user = user_from_cookie(request, db)
    if not user or not user.verified: raise HTTPException(401, "Please sign in")
    return user

def public_user(u):
    return {"id": u.id, "vegili_id": u.vegili_id, "name": u.name, "email": u.email}

def send_otp(email, code):
    host = os.getenv("SMTP_HOST")
    if not host:
        if OTP_DEV:
            print(f"[VEGILI DEV OTP] {email}: {code}")
            return
        raise HTTPException(503, "Email service is not configured")
    msg = EmailMessage()
    msg["Subject"] = "Your Vegili verification code"
    msg["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", ""))
    msg["To"] = email
    msg.set_content(f"Your Vegili verification code is {code}. It expires in 10 minutes.")
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as server:
            server.starttls()
            server.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            server.send_message(msg)
    except Exception:
        raise HTTPException(503, "Could not send verification email")

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
class VerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
class LoginIn(BaseModel):
    email: EmailStr
    password: str
class PostIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
class EmailIn(BaseModel):
    email: EmailStr
class ProfileIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)
class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def home(): return FileResponse("app/static/index.html")

@app.post("/api/auth/register")
def register(data: RegisterIn, db: Session = Depends(db_session)):
    email = str(data.email).lower().strip()
    if db.query(User).filter(func.lower(User.email) == email).first(): raise HTTPException(409, "Email already registered")
    code = f"{secrets.randbelow(1000000):06d}"
    otp_store[email] = {"code_hash": hashlib.sha256(code.encode()).hexdigest(), "name": data.name.strip(), "password_hash": pwd.hash(data.password), "expires": datetime.now(timezone.utc)+timedelta(minutes=10)}
    send_otp(email, code)
    return {"message": "Verification code sent. Check your email.", "dev_code": code if OTP_DEV and not os.getenv("SMTP_HOST") else None}

@app.post("/api/auth/verify")
def verify(data: VerifyIn, response: Response, db: Session = Depends(db_session)):
    email = str(data.email).lower().strip()
    record = otp_store.get(email)
    if not record or record["expires"] < datetime.now(timezone.utc): raise HTTPException(400, "Code expired or not found. Register again.")
    if not hmac.compare_digest(record["code_hash"], hashlib.sha256(data.code.encode()).hexdigest()): raise HTTPException(400, "Incorrect verification code")
    if db.query(User).filter(func.lower(User.email) == email).first(): raise HTTPException(409, "Email already registered")
    u = User(name=record["name"], email=email, password_hash=record["password_hash"], vegili_id="VGL-"+secrets.token_hex(4).upper(), verified=True)
    db.add(u); db.commit(); db.refresh(u); otp_store.pop(email, None)
    response.set_cookie("vegili_session", serializer.dumps({"uid": u.id}), httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=60*60*24*14)
    return {"user": public_user(u)}

@app.post("/api/auth/login")
def login(data: LoginIn, response: Response, db: Session = Depends(db_session)):
    u = db.query(User).filter(func.lower(User.email) == str(data.email).lower().strip()).first()
    if not u or not pwd.verify(data.password, u.password_hash): raise HTTPException(401, "Email or password is incorrect")
    if not u.verified: raise HTTPException(403, "Verify your email first")
    response.set_cookie("vegili_session", serializer.dumps({"uid": u.id}), httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=60*60*24*14)
    return {"user": public_user(u)}
@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("vegili_session", httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return {"ok": True}
@app.get("/api/me")
def me(user: User = Depends(current_user)): return {"user": public_user(user)}

@app.get("/api/feed")
def feed(db: Session = Depends(db_session), user: User = Depends(current_user)):
    rows = db.query(Post, User).join(User, User.id == Post.user_id).order_by(Post.created_at.desc()).limit(100).all()
    out=[]
    for p, author in rows:
        out.append({"id":p.id,"body":p.body,"created_at":p.created_at.isoformat(),"author":public_user(author),"likes":db.query(Like).filter_by(post_id=p.id).count(),"liked":db.query(Like).filter_by(post_id=p.id,user_id=user.id).first() is not None,"comments":[{"id":c.id,"body":c.body,"author":db.get(User,c.user_id).name} for c in db.query(Comment).filter_by(post_id=p.id).order_by(Comment.created_at.asc()).all()]})
    return {"posts":out}
@app.post("/api/posts")
def create_post(data: PostIn, db: Session = Depends(db_session), user: User = Depends(current_user)):
    p=Post(user_id=user.id,body=data.body.strip())
    db.add(p); db.commit(); db.refresh(p)
    return {"id":p.id}
@app.post("/api/posts/{post_id}/like")
def like(post_id:int, db:Session=Depends(db_session), user:User=Depends(current_user)):
    p=db.get(Post,post_id)
    if not p: raise HTTPException(404,"Post not found")
    existing=db.query(Like).filter_by(post_id=post_id,user_id=user.id).first()
    if existing: db.delete(existing); liked=False
    else: db.add(Like(post_id=post_id,user_id=user.id)); liked=True
    db.commit()
    return {"liked":liked,"likes":db.query(Like).filter_by(post_id=post_id).count()}
@app.post("/api/posts/{post_id}/comments")
def comment(post_id:int,data:CommentIn,db:Session=Depends(db_session),user:User=Depends(current_user)):
    if not db.get(Post,post_id): raise HTTPException(404,"Post not found")
    c=Comment(post_id=post_id,user_id=user.id,body=data.body.strip()); db.add(c); db.commit()
    return {"ok":True}

@app.get("/api/users/search")
def search_users(email:str,db:Session=Depends(db_session),user:User=Depends(current_user)):
    if len(email.strip())<3: return {"users":[]}
    rows=db.query(User).filter(func.lower(User.email).like("%"+email.lower().strip()+"%"),User.id!=user.id,User.verified==True).limit(10).all()
    return {"users":[public_user(u) for u in rows]}
@app.post("/api/contacts/request")
def contact_request(data:EmailIn,db:Session=Depends(db_session),user:User=Depends(current_user)):
    target=db.query(User).filter(func.lower(User.email)==str(data.email).lower().strip(),User.verified==True).first()
    if not target: raise HTTPException(404,"No verified user found for that email")
    if target.id==user.id: raise HTTPException(400,"You cannot add yourself")
    existing=db.query(Contact).filter(((Contact.requester_id==user.id)&(Contact.receiver_id==target.id))|((Contact.requester_id==target.id)&(Contact.receiver_id==user.id))).first()
    if existing: raise HTTPException(409,"Request or contact already exists")
    db.add(Contact(requester_id=user.id,receiver_id=target.id)); db.commit()
    return {"ok":True}
@app.get("/api/contacts")
def contacts(db:Session=Depends(db_session),user:User=Depends(current_user)):
    rows=db.query(Contact).filter((Contact.requester_id==user.id)|(Contact.receiver_id==user.id)).all()
    return {"contacts":[{"id":r.id,"accepted":r.accepted,"incoming":r.receiver_id==user.id,"user":public_user(db.get(User,r.requester_id if r.receiver_id==user.id else r.receiver_id))} for r in rows]}
@app.post("/api/contacts/{contact_id}/accept")
def accept(contact_id:int,db:Session=Depends(db_session),user:User=Depends(current_user)):
    c=db.get(Contact,contact_id)
    if not c or c.receiver_id!=user.id: raise HTTPException(404,"Request not found")
    c.accepted=True; db.commit(); return {"ok":True}

def are_contacts(db,a,b):
    return db.query(Contact).filter(Contact.accepted==True,((Contact.requester_id==a)&(Contact.receiver_id==b))|((Contact.requester_id==b)&(Contact.receiver_id==a))).first() is not None
@app.get("/api/messages/{other_id}")
def get_messages(other_id:int,db:Session=Depends(db_session),user:User=Depends(current_user)):
    if not are_contacts(db,user.id,other_id): raise HTTPException(403,"You must be connected to chat")
    rows=db.query(Message).filter(((Message.sender_id==user.id)&(Message.receiver_id==other_id))|((Message.sender_id==other_id)&(Message.receiver_id==user.id))).order_by(Message.created_at.asc()).limit(200).all()
    return {"messages":[{"id":m.id,"sender_id":m.sender_id,"receiver_id":m.receiver_id,"body":m.body,"created_at":m.created_at.isoformat()} for m in rows]}
@app.post("/api/messages/{other_id}")
def send_message(other_id:int,data:MessageIn,db:Session=Depends(db_session),user:User=Depends(current_user)):
    if not are_contacts(db,user.id,other_id): raise HTTPException(403,"You must be connected to chat")
    m=Message(sender_id=user.id,receiver_id=other_id,body=data.body.strip()); db.add(m); db.commit(); db.refresh(m)
    return {"id":m.id,"created_at":m.created_at.isoformat()}

@app.patch("/api/settings/name")
def update_name(data:ProfileIn,db:Session=Depends(db_session),user:User=Depends(current_user)):
    user.name=data.name.strip(); db.commit(); return {"user":public_user(user)}
@app.patch("/api/settings/email")
def update_email(data:EmailIn,db:Session=Depends(db_session),user:User=Depends(current_user)):
    raise HTTPException(501,"Email change verification is not enabled yet")
@app.patch("/api/settings/password")
def update_password(data:PasswordIn,db:Session=Depends(db_session),user:User=Depends(current_user)):
    if not pwd.verify(data.current_password,user.password_hash): raise HTTPException(400,"Current password is incorrect")
    user.password_hash=pwd.hash(data.new_password); db.commit(); return {"ok":True}

live_sockets = {}

@app.websocket("/ws/chat/{other_id}")
async def websocket_chat(ws: WebSocket, other_id: int):
    token = ws.cookies.get("vegili_session")
    try:
        data = serializer.loads(token or "", max_age=60*60*24*14)
        uid = int(data["uid"])
    except Exception:
        await ws.close(code=4401)
        return
    db = SessionLocal()
    try:
        if not are_contacts(db, uid, other_id):
            await ws.close(code=4403)
            return
        await ws.accept()
        live_sockets.setdefault(uid, set()).add(ws)
        await ws.send_json({"type": "ready"})
        while True:
            incoming = await ws.receive_json()
            if not isinstance(incoming, dict):
                continue
            body = str(incoming.get("body", "")).strip()
            if not body or len(body) > 4000:
                continue
            msg = Message(sender_id=uid, receiver_id=other_id, body=body)
            db.add(msg)
            db.commit()
            db.refresh(msg)
            payload = {"type": "message", "id": msg.id, "sender_id": uid, "receiver_id": other_id, "body": msg.body, "created_at": msg.created_at.isoformat()}
            for peer in list(live_sockets.get(uid, set()) | live_sockets.get(other_id, set())):
                try:
                    await peer.send_json(payload)
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        live_sockets.get(uid, set()).discard(ws)
        if not live_sockets.get(uid):
            live_sockets.pop(uid, None)
        db.close()
