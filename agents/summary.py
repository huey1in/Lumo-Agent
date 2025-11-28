"""
SummaryAgent: Generates final execution report.
"""

from agents.base import BaseAgent, AgentContext, AgentResult
from agents.prompts import SUMMARY_GENERATE, SYSTEM_IDENTITY, format_prompt


class SummaryAgent(BaseAgent):
    """Generates a summary report of the execution."""
    
    name = "SummaryAgent"
    
    async def run(self, ctx: AgentContext) -> AgentResult:
        self.logger.info("Generating execution summary...")
        
        # Calculate stats
        done_count = sum(1 for s in ctx.steps if s.status == "done")
        failed_count = sum(1 for s in ctx.steps if s.status == "failed")
        total_count = len(ctx.steps)
        
        self.logger.info(f"Stats: {done_count}/{total_count} done, {failed_count} failed")
        
        try:
            summary = await self._generate_summary(ctx, done_count, failed_count)
            self.logger.debug(f"Summary: {summary[:100]}...")
            
            # Send summary to frontend
            await self.emit(ctx, "summary", summary)
            
            # Add to memory
            ctx.memory.append({"role": "assistant", "content": summary})
            
            return AgentResult(
                success=True,
                next_agent=None,  # End of chain
                data={
                    "total": total_count,
                    "done": done_count,
                    "failed": failed_count,
                },
                message="Summary generated"
            )
            
        except Exception as e:
            self.logger.error(f"Summary generation failed: {e}")
            fallback = f"执行完成。共 {total_count} 步，成功 {done_count} 步，失败 {failed_count} 步。"
            await self.emit(ctx, "summary", fallback)
            return AgentResult(
                success=False,
                next_agent=None,
                message=str(e)
            )
    
    async def _generate_summary(self, ctx: AgentContext, done_count: int, failed_count: int) -> str:
        """Use LLM to generate a human-readable summary."""
        # Prepare execution log
        execution_log = []
        
        # Add goal
        execution_log.append(f"【用户目标】{ctx.goal}")
        execution_log.append(f"【执行统计】共 {len(ctx.steps)} 步，成功 {done_count}，失败 {failed_count}")
        execution_log.append("")
        
        # Add steps with details
        for i, s in enumerate(ctx.steps):
            status = "✓ 成功" if s.status == "done" else "✗ 失败"
            execution_log.append(f"【步骤 {i+1}】{s.title} - {status}")
            if s.command:
                execution_log.append(f"  命令: {s.command}")
            
            # 始终显示输出内容，但限制长度
            if s.output:
                output_preview = s.output[:300] if len(s.output) > 300 else s.output
                execution_log.append(f"  输出: {output_preview}")
            else:
                execution_log.append(f"  输出: (空)")
            
            if s.error:
                execution_log.append(f"  错误: {s.error}")
        
        log_text = "\n".join(execution_log)
        if len(log_text) > 2500:
            log_text = log_text[:2500] + "\n...(已截断)"
        
        prompt = format_prompt(SUMMARY_GENERATE, execution_log=log_text)
        
        return await ctx.llm.complete_async(prompt, [], temperature=0.3)


__all__ = ["SummaryAgent"]
