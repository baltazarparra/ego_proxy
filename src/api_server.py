"""
FastAPI HTTP server for LLM inference.

Provides REST API endpoints for:
- Text generation
- Chat completion
- Model information
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import config
from .generator import TextGenerator
from .model_loader import get_model_info, load_tokenizer_and_model

logger = logging.getLogger(__name__)

# Global model and tokenizer (loaded at startup)
model = None
tokenizer = None
generator = None


class GenerateRequest(BaseModel):
    """Request model for /generate endpoint."""

    prompt: str = Field(..., description="The input prompt")
    system_prompt: Optional[str] = Field(
        None, description="Optional system instruction"
    )
    max_new_tokens: Optional[int] = Field(
        None, description="Maximum tokens to generate"
    )
    temperature: Optional[float] = Field(
        None, description="Sampling temperature", ge=0.0, le=2.0
    )
    top_p: Optional[float] = Field(
        None, description="Nucleus sampling probability", ge=0.0, le=1.0
    )
    top_k: Optional[int] = Field(None, description="Top-k sampling", ge=0)
    do_sample: Optional[bool] = Field(None, description="Whether to use sampling")


class GenerateResponse(BaseModel):
    """Response model for /generate endpoint."""

    output_text: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    elapsed_seconds: float


class ChatMessage(BaseModel):
    """Single message in a conversation."""

    role: str = Field(..., description="Message role (system, user, assistant)")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Request model for /chat endpoint."""

    messages: List[ChatMessage] = Field(..., description="Conversation history")
    max_new_tokens: Optional[int] = Field(
        None, description="Maximum tokens to generate"
    )
    temperature: Optional[float] = Field(
        None, description="Sampling temperature", ge=0.0, le=2.0
    )
    top_p: Optional[float] = Field(
        None, description="Nucleus sampling probability", ge=0.0, le=1.0
    )


class ChatResponse(BaseModel):
    """Response model for /chat endpoint."""

    role: str = "assistant"
    content: str
    elapsed_seconds: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for model loading/unloading."""
    global model, tokenizer, generator

    # Startup: Load model
    logger.info("Starting up: Loading model...")
    try:
        tokenizer, model = load_tokenizer_and_model()
        generator = TextGenerator(model, tokenizer)
        logger.info("Model loaded successfully")

        # Log model info
        info = get_model_info(model)
        logger.info(f"Model info: {info}")

    except Exception as e:
        logger.error(f"Failed to load model: {e}", exc_info=True)
        raise

    yield

    # Shutdown: Cleanup
    logger.info("Shutting down...")
    model = None
    tokenizer = None
    generator = None


# Create FastAPI app
app = FastAPI(
    title="Ego Proxy API",
    description="REST API for local language model inference",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "name": "Ego Proxy API",
        "version": "0.1.0",
        "model": config.MODEL_ID,
        "status": "running" if model is not None else "not loaded",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    if model is None or generator is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    return {"status": "healthy", "model_loaded": True}


@app.get("/info")
async def info():
    """Get model information."""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    model_info = get_model_info(model)
    return {
        "model_id": config.MODEL_ID,
        "device": config.get_device(),
        **model_info,
        "config": config.summary(),
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    """
    Generate text completion for a prompt.

    Args:
        request: GenerateRequest with prompt and generation parameters

    Returns:
        GenerateResponse with generated text and metadata
    """
    if generator is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        start_time = time.time()

        # Generate text
        output_text = generator.generate_text(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            max_new_tokens=request.max_new_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k,
            do_sample=request.do_sample,
            return_full_text=False,
        )

        elapsed = time.time() - start_time

        # Calculate actual token counts using tokenizer
        prompt_text = request.prompt
        if request.system_prompt:
            prompt_text = f"{request.system_prompt}\n{request.prompt}"

        prompt_tokens = len(tokenizer.encode(prompt_text))
        completion_tokens = len(tokenizer.encode(output_text))

        return GenerateResponse(
            output_text=output_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            elapsed_seconds=round(elapsed, 3),
        )

    except Exception as e:
        logger.error(f"Generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Generate a chat completion for a conversation.

    Args:
        request: ChatRequest with message history and parameters

    Returns:
        ChatResponse with assistant reply
    """
    if generator is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        start_time = time.time()

        # Convert Pydantic models to dicts
        messages = [
            {"role": msg.role, "content": msg.content} for msg in request.messages
        ]

        # Generate response
        response_text = generator.generate_chat(
            messages=messages,
            max_new_tokens=request.max_new_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )

        elapsed = time.time() - start_time

        return ChatResponse(content=response_text, elapsed_seconds=round(elapsed, 3))

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


def main():
    """Main entry point for running the server."""
    import uvicorn

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run server
    uvicorn.run(
        "src.api_server:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=False,
        log_level=config.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
