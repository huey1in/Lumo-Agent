"""
RouterAgent: Entry point that determines user intent.
Routes to ChatAgent for conversations, PlannerAgent for tasks.
"""

from agents.base import BaseAgent, AgentContext, AgentResult
from agents.prompts import ROUTER_CLASSIFY_INTENT, format_prompt


class RouterAgent(BaseAgent):
    """Determines if user message is chat or task, routes accordingly."""
    
    name = "RouterAgent"
    
    async def run(self, ctx: AgentContext) -> AgentResult:
        self.logger.info(f"Routing goal: {ctx.goal[:50]}...")
        
        # Add user message to memory
        ctx.memory.append({"role": "user", "content": ctx.goal})
        
        # Use LLM to classify intent
        is_chat = await self._classify_intent(ctx)
        
        if is_chat:
            self.logger.info("Intent: CHAT -> ChatAgent")
            return AgentResult(
                success=True,
                next_agent="ChatAgent",
                message="Routing to ChatAgent"
            )
        else:
            self.logger.info("Intent: TASK -> PlannerAgent")
            return AgentResult(
                success=True,
                next_agent="PlannerAgent", 
                message="Routing to PlannerAgent"
            )
    
    async def _classify_intent(self, ctx: AgentContext) -> bool:
        """Returns True if message is conversational chat."""
        try:
            prompt = format_prompt(ROUTER_CLASSIFY_INTENT, goal=ctx.goal)
            # 传递历史对话，让 LLM 能理解上下文（如"启动"指的是什么）
            result = await ctx.llm.complete_async(prompt, ctx.memory, temperature=0.1)
            is_chat = "CHAT" in result.upper()
            self.logger.debug(f"LLM classification: {result.strip()} -> is_chat={is_chat}")
            return is_chat
        except Exception as e:
            self.logger.error(f"Classification failed: {e}, defaulting to TASK")
            return False


__all__ = ["RouterAgent"]
