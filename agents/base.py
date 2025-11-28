"""
Base Agent class and shared data structures.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)

# Regex to strip ANSI escape codes
ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\]0;[^\x07\n]*')


def clean_output(text: str) -> str:
    """Remove ANSI escape codes and terminal control sequences."""
    cleaned = ANSI_ESCAPE_RE.sub('', text)
    cleaned = cleaned.replace('\x1b', '').replace('\x07', '')
    return cleaned.strip()


# Stream callback type
StreamCallback = Callable[[str, str], Union[None, Awaitable[None]]]


@dataclass
class Step:
    """Represents a single execution step."""
    title: str
    command: Optional[str] = None
    status: str = "pending"  # pending | running | done | failed
    output: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "command": self.command or "",
            "status": self.status,
            "output": self.output[:200] if self.output else "",
            "error": self.error,
        }


@dataclass
class AgentContext:
    """Shared context passed between agents."""
    goal: str
    memory: List[Dict[str, str]] = field(default_factory=list)
    steps: List[Step] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    current_step_idx: int = 0
    retry_count: int = 0
    max_retries: int = 2
    replan_count: int = 0  # 重新规划次数
    max_replans: int = 3   # 最大重新规划次数
    last_failure_reason: str = ""  # 上次失败原因，用于检测重复失败
    
    # Injected dependencies
    llm: Any = None
    shell: Any = None
    emit: Optional[StreamCallback] = None

    def add_step(self, step: Step) -> None:
        self.steps.append(step)

    def get_current_step(self) -> Optional[Step]:
        if 0 <= self.current_step_idx < len(self.steps):
            return self.steps[self.current_step_idx]
        return None


@dataclass  
class AgentResult:
    """Result returned by an agent."""
    success: bool
    next_agent: Optional[str] = None  # Name of next agent to call
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""


class BaseAgent(ABC):
    """Abstract base class for all agents."""
    
    name: str = "BaseAgent"
    
    def __init__(self):
        self.logger = logging.getLogger(self.name)
    
    @abstractmethod
    async def run(self, ctx: AgentContext) -> AgentResult:
        """Execute the agent's logic."""
        pass
    
    async def emit(self, ctx: AgentContext, kind: str, content: str) -> None:
        """Send a message to the frontend."""
        if ctx.emit:
            try:
                self.logger.debug(f"Emit [{kind}]: {content[:100]}...")
                result = ctx.emit(kind, content)
                if asyncio.iscoroutine(result):
                    await result
                # Yield to event loop to ensure message is flushed immediately
                await asyncio.sleep(0)
            except Exception as e:
                self.logger.error(f"Emit error: {e}")

    async def emit_tasks(self, ctx: AgentContext) -> None:
        """Send current task list to frontend."""
        import json
        tasks_data = json.dumps([s.to_dict() for s in ctx.steps], ensure_ascii=False)
        await self.emit(ctx, "tasks", tasks_data)


__all__ = ["BaseAgent", "AgentContext", "AgentResult", "Step", "StreamCallback", "clean_output"]
