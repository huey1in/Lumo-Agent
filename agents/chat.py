"""
ChatAgent: Handles conversational messages.
"""

from agents.base import BaseAgent, AgentContext, AgentResult
from agents.prompts import CHAT_RESPONSE, SYSTEM_IDENTITY, format_prompt


class ChatAgent(BaseAgent):
    """Generates conversational replies for non-task messages."""
    
    name = "ChatAgent"
    
    async def run(self, ctx: AgentContext) -> AgentResult:
        self.logger.info("Generating chat reply...")
        
        try:
            prompt = format_prompt(CHAT_RESPONSE, goal=ctx.goal)
            # 添加系统身份到对话历史
            enhanced_memory = [{"role": "system", "content": SYSTEM_IDENTITY}] + ctx.memory
            
            reply = await ctx.llm.complete_async(prompt, enhanced_memory, temperature=0.7)
            self.logger.debug(f"Generated reply: {reply[:100]}...")
            
            # Send reply to frontend
            await self.emit(ctx, "reply", reply)
            
            # Add to memory
            ctx.memory.append({"role": "assistant", "content": reply})
            
            return AgentResult(
                success=True,
                next_agent=None,  # End of chain
                message="Chat reply sent"
            )
            
        except Exception as e:
            self.logger.error(f"Chat reply failed: {e}")
            await self.emit(ctx, "reply", "抱歉，我暂时无法回复，请稍后再试。")
            return AgentResult(
                success=False,
                next_agent=None,
                message=str(e)
            )


__all__ = ["ChatAgent"]
