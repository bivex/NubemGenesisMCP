#!/usr/bin/env python3
"""
Chat API Endpoint - Main interface for AI persona interactions
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import time
import json
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(prefix="/api", tags=["chat"])

class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str = Field(..., description="User message to process")
    persona_id: Optional[str] = Field(None, description="Specific persona to use")
    model: Optional[str] = Field("claude-3-opus-20240229", description="LLM model to use")
    stream: Optional[bool] = Field(False, description="Enable streaming response")
    context: Optional[List[Dict[str, str]]] = Field(None, description="Conversation context")
    temperature: Optional[float] = Field(0.7, ge=0, le=2, description="Model temperature")
    max_tokens: Optional[int] = Field(4096, description="Maximum tokens in response")

class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    response: str
    persona_used: str
    model_used: str
    tokens_used: int
    latency_ms: float
    timestamp: str
    session_id: Optional[str] = None

class PersonaInfo(BaseModel):
    """Information about an AI persona"""
    id: str
    name: str
    category: str
    description: str
    capabilities: List[str]
    specialties: List[str]

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint for interacting with AI personas
    
    This endpoint:
    1. Selects the best persona if not specified
    2. Processes the message through the selected persona
    3. Returns the response with metadata
    """
    try:
        # Import here to avoid circular dependencies
        from core.unified_orchestrator import UnifiedOrchestrator
        from core.multi_llm_verifier import MultiLLMVerifier
        
        # Initialize orchestrator
        orchestrator = UnifiedOrchestrator()
        
        # Record start time
        start_time = time.time()
        
        # Select persona if not specified
        if not request.persona_id:
            # Auto-select best persona based on message content
            persona_id = orchestrator.select_best_agent(
                task=request.message,
                context={"history": request.context or []}
            )
            if not persona_id:
                persona_id = "assistant"  # Default fallback
            logger.info(f"Auto-selected persona: {persona_id}")
        else:
            persona_id = request.persona_id
            logger.info(f"Using requested persona: {persona_id}")
        
        # Process message through orchestrator
        response = await orchestrator.process_with_agent(
            agent_id=persona_id,
            task=request.message,
            context={
                "model": request.model,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "conversation_history": request.context or []
            }
        )
        
        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000
        
        # Extract response content
        if isinstance(response, dict):
            content = response.get('content', response.get('response', str(response)))
            tokens = response.get('tokens_used', 0)
        else:
            content = str(response)
            tokens = len(content.split())  # Rough estimate
        
        return ChatResponse(
            response=content,
            persona_used=persona_id,
            model_used=request.model,
            tokens_used=tokens,
            latency_ms=round(latency_ms, 2),
            timestamp=datetime.now().isoformat(),
            session_id=response.get('session_id') if isinstance(response, dict) else None
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing chat: {str(e)}")

@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    Streaming chat endpoint for real-time responses
    """
    try:
        from core.unified_orchestrator import UnifiedOrchestrator
        
        orchestrator = UnifiedOrchestrator()
        
        async def generate():
            """Generate streaming response"""
            # Send initial metadata
            yield f"data: {json.dumps({'type': 'start', 'persona': request.persona_id or 'auto'})}\n\n"
            
            # Process and stream response
            async for chunk in orchestrator.stream_response(
                agent_id=request.persona_id,
                task=request.message,
                model=request.model
            ):
                yield f"data: {json.dumps({'type': 'content', 'text': chunk})}\n\n"
            
            # Send completion signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        
    except Exception as e:
        logger.error(f"Stream endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/personas", response_model=List[PersonaInfo])
async def list_personas():
    """
    List all available AI personas with their capabilities
    """
    try:
        from core.personas_unified import UnifiedPersonaManager
        
        manager = UnifiedPersonaManager()
        personas = []
        
        for persona_id, persona_data in manager.personas.items():
            # Handle both dict and object formats
            if hasattr(persona_data, '__dict__'):
                data = persona_data.__dict__
            else:
                data = persona_data
            
            personas.append(PersonaInfo(
                id=persona_id,
                name=data.get('name', persona_id),
                category=data.get('category', 'general'),
                description=data.get('description', 'AI Assistant'),
                capabilities=data.get('capabilities', []),
                specialties=data.get('specialties', [])
            ))
        
        return personas
        
    except Exception as e:
        logger.error(f"List personas error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/personas/{persona_id}", response_model=PersonaInfo)
async def get_persona_details(persona_id: str):
    """
    Get detailed information about a specific persona
    """
    try:
        from core.personas_unified import UnifiedPersonaManager
        
        manager = UnifiedPersonaManager()
        persona = manager.get_persona(persona_id)
        
        if not persona:
            raise HTTPException(status_code=404, detail=f"Persona '{persona_id}' not found")
        
        # Handle both dict and object formats
        if hasattr(persona, '__dict__'):
            data = persona.__dict__
        else:
            data = persona
        
        return PersonaInfo(
            id=persona_id,
            name=data.get('name', persona_id),
            category=data.get('category', 'general'),
            description=data.get('description', 'AI Assistant'),
            capabilities=data.get('capabilities', []),
            specialties=data.get('specialties', [])
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get persona error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat/multi-llm")
async def multi_llm_chat(request: ChatRequest):
    """
    Query multiple LLMs simultaneously and return all responses
    """
    try:
        from core.multi_llm_verifier import MultiLLMVerifier
        
        verifier = MultiLLMVerifier()
        
        # Query all configured LLMs
        responses = await verifier.query_all_models(request.message)
        
        return {
            "query": request.message,
            "responses": responses,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Multi-LLM error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chat/history/{session_id}")
async def get_chat_history(session_id: str, limit: int = 50):
    """
    Retrieve chat history for a session
    """
    try:
        # This would connect to your session storage
        # For now, return placeholder
        return {
            "session_id": session_id,
            "messages": [],
            "message": "History retrieval not yet implemented"
        }
        
    except Exception as e:
        logger.error(f"History retrieval error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))