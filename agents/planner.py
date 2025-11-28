"""
PlannerAgent: Creates execution plan for tasks.
"""

from agents.base import BaseAgent, AgentContext, AgentResult, Step
from agents.prompts import (
    SYSTEM_IDENTITY,
    PLANNER_GENERATE_PLAN,
    PLANNER_INTRO,
    format_prompt,
)


class PlannerAgent(BaseAgent):
    """Generates an execution plan with shell commands."""
    
    name = "PlannerAgent"
    
    async def run(self, ctx: AgentContext) -> AgentResult:
        self.logger.info(f"Planning for goal: {ctx.goal[:50]}...")
        
        try:
            # Start shell if needed
            ctx.shell.start()
            self.logger.debug("Shell started")
            
            # Generate plan (let LLM infer system type from first step)
            steps = await self._generate_plan(ctx)
            ctx.steps = steps
            self.logger.info(f"Generated {len(steps)} steps")
            
            for i, step in enumerate(steps):
                self.logger.debug(f"  Step {i+1}: {step.title} -> {step.command}")
            
            # Generate and send plan introduction
            intro = await self._generate_intro(ctx)
            await self.emit(ctx, "reply", intro)
            
            # 将 AI 的回复添加到 memory，供后续对话使用
            ctx.memory.append({"role": "assistant", "content": intro})
            
            # Send initial task list
            await self.emit_tasks(ctx)
            
            return AgentResult(
                success=True,
                next_agent="ExecutorAgent",
                message=f"Plan created with {len(steps)} steps"
            )
            
        except Exception as e:
            self.logger.error(f"Planning failed: {e}")
            await self.emit(ctx, "error", f"规划失败: {e}")
            return AgentResult(
                success=False,
                next_agent=None,
                message=str(e)
            )
    
    async def _generate_plan(self, ctx: AgentContext) -> list:
        """Use LLM to create execution plan."""
        prompt = format_prompt(
            PLANNER_GENERATE_PLAN,
            goal=ctx.goal
        )
        
        # 添加系统身份到上下文
        enhanced_memory = [{"role": "system", "content": SYSTEM_IDENTITY}] + ctx.memory
        
        plan_text = await ctx.llm.complete_async(prompt, enhanced_memory, temperature=0.2)
        self.logger.debug(f"LLM plan response:\n{plan_text}")
        
        steps = []
        for line in plan_text.splitlines():
            line = line.strip()
            if "::" not in line:
                continue
            # Handle markdown formatting
            line = line.lstrip('0123456789.-) *').strip()
            if "::" not in line:
                continue
                
            parts = line.split("::", 1)
            if len(parts) != 2:
                continue
                
            title, cmd = parts
            cmd = cmd.strip().strip('`').strip()
            
            # Skip invalid commands with placeholders
            if not cmd:
                continue
            
            # 检测各种占位符模式
            placeholder_patterns = [
                "/path/to",
                "xxx",
                "用户名",
                "文件名",
                "目录名",
                "服务名",
                "包名",
                "your_",
                "YOUR_",
                "[name]",
                "{name}",
            ]
            
            has_placeholder = any(p in cmd for p in placeholder_patterns)
            if has_placeholder:
                self.logger.warning(f"Skipping command with placeholder: {cmd}")
                continue
            
            # 检测极度危险的命令
            dangerous_patterns = [
                "rm -rf /",
                "rm -rf /*",
                "rm -fr /",
                "rm -fr /*",
                "> /dev/sda",
                "mkfs.",
                "dd if=",
                ":(){:|:&};:",  # fork bomb
            ]
            
            is_dangerous = any(p in cmd for p in dangerous_patterns)
            if is_dangerous:
                self.logger.warning(f"Blocking dangerous command: {cmd}")
                continue
                
            steps.append(Step(title=title.strip(), command=cmd))
        
        if not steps:
            # 不要把用户的中文目标当作命令,返回一个安全的错误信息
            self.logger.error("No valid steps parsed from LLM response")
            raise ValueError(f"无法为任务 '{ctx.goal[:50]}' 生成有效的执行计划，请尝试更具体的描述")
            
        return steps
    
    async def _generate_intro(self, ctx: AgentContext) -> str:
        """Generate brief plan introduction."""
        step_list = "\n".join([f"{i+1}. {s.title}" for i, s in enumerate(ctx.steps)])
        prompt = format_prompt(
            PLANNER_INTRO,
            goal=ctx.goal,
            step_list=step_list
        )
        try:
            return await ctx.llm.complete_async(prompt, ctx.memory, temperature=0.5)
        except Exception as e:
            self.logger.error(f"Intro generation failed: {e}")
            return f"好的，我将分 {len(ctx.steps)} 步来完成这个任务。"


__all__ = ["PlannerAgent"]
