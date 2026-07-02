# backend/main.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import init_db, get_db, ChatLog
from agent import trade_buddy_agent

app = FastAPI(title="TradeBuddy AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_db()

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
def handle_chat(request: ChatRequest, db: Session = Depends(get_db)):
    try:
        inputs = {"user_message": request.message}
        output = trade_buddy_agent.invoke(inputs)
        ai_response_text = output.get("ai_response", "Sorry, I couldn't process that.")
        
        # Log to MySQL
        new_log = ChatLog(user_message=request.message, ai_response=ai_response_text)
        db.add(new_log)
        db.commit()
        
        return {
            "status": "success",
            "ticker_detected": output.get("ticker", "NONE"),
            "response": ai_response_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))