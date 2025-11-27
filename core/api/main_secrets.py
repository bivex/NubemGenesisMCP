from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
from datetime import datetime
import json
import redis
from contextlib import asynccontextmanager
from pathlib import Path

# Initialize Redis
redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "nubemsuper-redis"), port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=True)

# API Keys
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")

# Initialize OpenAI client
openai_client = None
if OPENAI_KEY:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_KEY)
    except Exception as e:
        print(f"Error initializing OpenAI: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 NubemSuperFClaude API starting...")
    yield
    print("👋 NubemSuperFClaude API shutting down...")

app = FastAPI(
    title="NubemSuperFClaude API",
    version="3.0.0",
    description="Production AI Framework",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = "gpt-3.5-turbo"
    persona: Optional[str] = "assistant"
    context: Optional[List[Dict]] = []
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000

class ChatResponse(BaseModel):
    response: str
    model: str
    tokens_used: Optional[int] = None
    timestamp: str
    cache_hit: bool = False

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "3.0.0",
        "services": {
            "redis": "healthy" if redis_client.ping() else "unhealthy",
            "openai": "configured" if OPENAI_KEY else "not configured",
        },
        "models_available": ["gpt-3.5-turbo", "gpt-4"] if OPENAI_KEY else []
    }

@app.post("/api/chat", response_model=ChatResponse)
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        response_text = ""
        tokens_used = 0
        
        if openai_client and "gpt" in request.model:
            # Use OpenAI
            completion = openai_client.chat.completions.create(
                model=request.model,
                messages=[{"role": "user", "content": request.message}],
                temperature=request.temperature,
                max_tokens=request.max_tokens
            )
            response_text = completion.choices[0].message.content
            if completion.usage:
                tokens_used = completion.usage.total_tokens
        else:
            # Fallback
            response_text = f"Procesando: {request.message[:50]}... [Modo simulación]"
            tokens_used = len(request.message.split())
        
        return ChatResponse(
            response=response_text,
            model=request.model,
            tokens_used=tokens_used,
            timestamp=datetime.utcnow().isoformat(),
            cache_hit=False
        )
        
    except Exception as e:
        print(f"Error in chat: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/personas")
async def list_personas():
    personas_dir = Path("/app/personas")
    personas = []
    
    if personas_dir.exists():
        for file in personas_dir.glob("*.py"):
            if file.name != "__init__.py":
                personas.append({
                    "id": file.stem.replace("persona_", ""),
                    "name": file.stem.replace("_", " ").title()
                })
    
    return {"count": len(personas), "personas": personas}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
