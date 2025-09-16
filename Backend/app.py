import os
from uuid import uuid4
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session as SASession
from dotenv import load_dotenv

# --- Env ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./feedback.db")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

# Force SQLAlchemy to use psycopg v3 if we're on Postgres (Render)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# SQLite needs this arg; Postgres does not
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# --- DB setup ---
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    consented = Column(Boolean, default=False)
    research_version = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    feedback = relationship("FeedbackResponse", back_populates="session", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    role = Column(String)   # "user" | "assistant" | "system"
    content = Column(Text)
    ts = Column(DateTime, default=datetime.utcnow)
    session = relationship("Session", back_populates="messages")

class FeedbackResponse(Base):
    __tablename__ = "feedback_responses"
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), index=True)
    q_key = Column(String)            # e.g., "believability"
    answer_numeric = Column(Integer)  # 1-5 if Likert, else null
    answer_text = Column(Text)        # open text, else null
    ts = Column(DateTime, default=datetime.utcnow)
    session = relationship("Session", back_populates="feedback")

Base.metadata.create_all(engine)

def db() -> SASession:
    d = SessionLocal()
    try:
        yield d
    finally:
        d.close()

# --- App & CORS ---
app = FastAPI(title="Feedback Chatbot API")
allow_origins = [o.strip() for o in CORS_ORIGINS.split(",")] if CORS_ORIGINS else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# --- Schemas ---
class StartSessionReq(BaseModel):
    consented: bool = False
    research_version: Optional[str] = None
    user_agent: Optional[str] = None

class StartSessionResp(BaseModel):
    session_id: str

class ChatMessageReq(BaseModel):
    session_id: str
    role: str
    content: str

class EndSessionReq(BaseModel):
    session_id: str

class FeedbackStartReq(BaseModel):
    session_id: str

class FeedbackAnswerReq(BaseModel):
    session_id: str
    q_key: str
    answer_numeric: Optional[int] = None
    answer_text: Optional[str] = None

# --- Endpoints ---
@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/session/start", response_model=StartSessionResp)
def start_session(req: StartSessionReq, s: SASession = Depends(db)):
    sess = Session(consented=req.consented, research_version=req.research_version, user_agent=req.user_agent)
    s.add(sess); s.commit()
    return StartSessionResp(session_id=sess.id)

@app.post("/chat/message")
def save_message(req: ChatMessageReq, s: SASession = Depends(db)):
    if req.role not in ("user","assistant","system"):
        raise HTTPException(400, "Invalid role")
    m = Message(session_id=req.session_id, role=req.role, content=req.content)
    s.add(m); s.commit()
    return {"ok": True}

@app.post("/session/end")
def end_session(req: EndSessionReq, s: SASession = Depends(db)):
    sess = s.get(Session, req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    sess.ended_at = datetime.utcnow()
    s.commit()
    return {"ok": True}

@app.post("/feedback/start")
def feedback_start(req: FeedbackStartReq):
    return {
        "session_id": req.session_id,
        "questions": [
            {"key":"believability", "type":"likert", "label":"Is the environment believable?", "scale_min":1, "scale_max":5},
            {"key":"realism", "type":"likert", "label":"Is it realistic?", "scale_min":1, "scale_max":5},
            {"key":"design_opt", "type":"likert", "label":"Is this design optimized for your task?", "scale_min":1, "scale_max":5},
            {"key":"ease_use", "type":"likert", "label":"How easy was it to use?", "scale_min":1, "scale_max":5},
            {"key":"trust", "type":"likert", "label":"How much did you trust the responses?", "scale_min":1, "scale_max":5},
            {"key":"task_success", "type":"likert", "label":"Were you able to complete the intended task?", "scale_min":1, "scale_max":5},
            {"key":"free_text", "type":"text", "label":"Any suggestions to improve realism or usefulness?"}
        ]
    }

@app.post("/feedback/answer")
def feedback_answer(req: FeedbackAnswerReq, s: SASession = Depends(db)):
    row = FeedbackResponse(
        session_id=req.session_id,
        q_key=req.q_key,
        answer_numeric=req.answer_numeric,
        answer_text=req.answer_text
    )
    s.add(row); s.commit()
    return {"ok": True}

@app.get("/feedback/export.csv")
def export_feedback_csv(s: SASession = Depends(db)):
    import csv, io
    buf = io.StringIO()
    # UTF-8 BOM so Excel on Windows opens cleanly
    buf.write('\ufeff')
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(["session_id","q_key","answer_numeric","answer_text","ts"])
    for r in s.query(FeedbackResponse).order_by(FeedbackResponse.ts.asc()).all():
        w.writerow([
            r.session_id,
            r.q_key,
            "" if r.answer_numeric is None else r.answer_numeric,
            (r.answer_text or "").replace("\n"," "),
            r.ts.isoformat()
        ])
    buf.seek(0)
    headers = {
        "Content-Disposition": f'attachment; filename="feedback_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv"'
    }
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8", headers=headers)

@app.get("/feedback/export.json")
def export_feedback_json(s: SASession = Depends(db)):
    rows = []
    for r in s.query(FeedbackResponse).order_by(FeedbackResponse.ts.asc()).all():
        rows.append({
            "session_id": r.session_id,
            "q_key": r.q_key,
            "answer_numeric": r.answer_numeric,
            "answer_text": r.answer_text,
            "ts": r.ts.isoformat()
        })
    return JSONResponse(rows)


















