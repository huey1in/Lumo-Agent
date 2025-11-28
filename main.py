import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Main")

# Ensure package imports work when running as a script (python main.py)
CURRENT_DIR = Path(__file__).resolve().parent
STATIC_DIR = CURRENT_DIR / "static"
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from agents.orchestrator import AgentOrchestrator
from llm.client import LLMClient
from shell.manager import ShellManager


app = FastAPI(title="Lumo Agent")

# Singleton-like components
shell_manager = ShellManager()
llm_client = LLMClient()
orchestrator = AgentOrchestrator(llm=llm_client, shell=shell_manager)

# Shared conversation memory (per-session in production)
conversation_memory: List[Dict[str, str]] = []

logger.info("Lumo Agent initialized")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    steps: List[Dict[str, Any]]


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    logger.info(f"POST /api/chat: {req.message[:50]}...")
    steps = await orchestrator.run(req.message, memory=conversation_memory)
    return ChatResponse(steps=[step.to_dict() for step in steps])


@app.get("/")
async def root() -> Dict[str, str]:
    return {
        "message": "Lumo Agent is running.",
        "chat": "/api/chat",
        "ws": "/ws/agent",
        "docs": "/docs",
        "ui": "/ui",
    }


@app.get("/ui")
async def serve_ui() -> FileResponse:
    """Serve the frontend demo page."""
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/agent")
async def ws_agent(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("WebSocket connected")
    
    # Per-connection memory
    session_memory: List[Dict[str, str]] = []
    
    try:
        # Long-running conversation loop
        while True:
            try:
                raw = await websocket.receive_text()
                logger.debug(f"WebSocket received: {raw[:100]}")
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                break

            try:
                payload = json.loads(raw)
                goal = payload.get("goal") or payload.get("message") or ""
            except json.JSONDecodeError:
                goal = raw

            if not goal.strip():
                continue

            logger.info(f"Processing goal: {goal[:50]}...")

            async def stream(kind: str, content: str) -> None:
                logger.debug(f"Stream [{kind}]: {content[:50]}...")
                await websocket.send_json({"type": kind, "content": content})
                # Force flush - yield to event loop to ensure message is sent immediately
                await asyncio.sleep(0)

            try:
                steps = await orchestrator.run(goal, stream=stream, memory=session_memory)
                await websocket.send_json({"type": "done", "content": f"完成，共 {len(steps)} 步"})
                logger.info(f"Goal completed with {len(steps)} steps")
            except Exception as e:
                logger.error(f"Orchestrator error: {e}", exc_info=True)
                await websocket.send_json({"type": "error", "content": str(e)})

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
