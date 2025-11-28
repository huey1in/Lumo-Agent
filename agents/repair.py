"""
RepairAgent: Analyzes failures and generates fix steps.
"""

from agents.base import BaseAgent, AgentContext, AgentResult, Step
from agents.prompts import REPAIR_GENERATE_FIX, SYSTEM_IDENTITY, format_prompt


class RepairAgent(BaseAgent):
    """Analyzes failed steps and generates repair commands."""
    
    name = "RepairAgent"
    
    async def run(self, ctx: AgentContext) -> AgentResult:
        failed_step = ctx.get_current_step()
        if not failed_step:
            self.logger.error("No current step to repair")
            return AgentResult(
                success=False,
                next_agent="SummaryAgent",
                message="No step to repair"
            )
        
        self.logger.info(f"Repairing failed step: {failed_step.title}")
        self.logger.debug(f"Error: {failed_step.error}")
        
        ctx.retry_count += 1
        
        try:
            # Generate repair steps
            repair_steps = await self._generate_repair(ctx, failed_step)
            
            if not repair_steps:
                self.logger.warning("No repair steps generated, skipping to next step")
                ctx.current_step_idx += 1
                ctx.retry_count = 0
                return AgentResult(
                    success=False,
                    next_agent="ExecutorAgent",
                    message="No repair possible, skipping step"
                )
            
            self.logger.info(f"Generated {len(repair_steps)} repair steps")
            
            # Insert repair steps after current step
            insert_idx = ctx.current_step_idx + 1
            for i, step in enumerate(repair_steps):
                ctx.steps.insert(insert_idx + i, step)
                self.logger.debug(f"  Repair step: {step.title} -> {step.command}")
            
            # Move to first repair step
            ctx.current_step_idx += 1
            
            # Update UI
            await self.emit_tasks(ctx)
            await self.emit(ctx, "log", f"生成 {len(repair_steps)} 个修复步骤")
            
            return AgentResult(
                success=True,
                next_agent="ExecutorAgent",
                message=f"Generated {len(repair_steps)} repair steps"
            )
            
        except Exception as e:
            self.logger.error(f"Repair generation failed: {e}")
            ctx.current_step_idx += 1
            ctx.retry_count = 0
            return AgentResult(
                success=False,
                next_agent="ExecutorAgent",
                message=str(e)
            )
    
    async def _generate_repair(self, ctx: AgentContext, failed_step) -> list:
        """Use LLM to generate repair commands."""
        # 收集系统信息帮助修复
        system_context = "\n".join(ctx.outputs[-5:]) if ctx.outputs else "无之前输出"
        
        prompt = format_prompt(
            REPAIR_GENERATE_FIX,
            step_title=failed_step.title,
            command=failed_step.command,
            error=failed_step.error[:500] if failed_step.error else "未知错误",
            context=system_context[:800]
        )
        
        # 添加系统身份
        enhanced_memory = [{"role": "system", "content": SYSTEM_IDENTITY}]
        
        suggestion = await ctx.llm.complete_async(prompt, enhanced_memory, temperature=0.2)
        self.logger.debug(f"LLM repair response:\n{suggestion}")
        
        steps = []
        for line in suggestion.splitlines():
            line = line.strip()
            if "::" not in line:
                continue
            line = line.lstrip('0123456789.-) ').strip()
            if "::" not in line:
                continue
                
            parts = line.split("::", 1)
            if len(parts) != 2:
                continue
                
            title, cmd = parts
            cmd = cmd.strip().strip('`')
            
            if not cmd or "/path/to" in cmd:
                continue
                
            steps.append(Step(title=f"[修复] {title.strip()}", command=cmd))
        
        return steps[:2]  # Max 2 repair steps


__all__ = ["RepairAgent"]
