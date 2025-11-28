"""
ExecutorAgent: Executes shell commands step by step.
"""

import asyncio
from agents.base import BaseAgent, AgentContext, AgentResult, clean_output
from agents.prompts import check_fatal_error, extract_error_message, GOAL_EVALUATION, format_prompt


class ExecutorAgent(BaseAgent):
    """Executes planned steps one by one."""
    
    name = "ExecutorAgent"
    
    async def run(self, ctx: AgentContext) -> AgentResult:
        self.logger.info(f"Executing steps, starting from index {ctx.current_step_idx}")
        
        while ctx.current_step_idx < len(ctx.steps):
            step = ctx.steps[ctx.current_step_idx]
            self.logger.info(f"Step {ctx.current_step_idx + 1}/{len(ctx.steps)}: {step.title}")
            
            # Update status to running
            step.status = "running"
            await self.emit_tasks(ctx)
            await self.emit(ctx, "log", f"开始: {step.title}")
            
            # Skip if no command
            if not step.command:
                self.logger.warning(f"Step has no command, skipping")
                step.status = "failed"
                step.error = "缺少可执行命令"
                await self.emit_tasks(ctx)
                ctx.current_step_idx += 1
                continue
            
            # 最后一道防线：检测极度危险的命令
            if self._is_catastrophic(step.command):
                self.logger.error(f"BLOCKED catastrophic command: {step.command}")
                step.status = "failed"
                step.error = "系统安全保护：此命令可能导致系统不可恢复，已被阻止"
                await self.emit(ctx, "log", f"安全阻止: {step.command}")
                await self.emit_tasks(ctx)
                ctx.current_step_idx += 1
                continue
            
            # Execute command
            success = await self._execute_step(ctx, step)
            
            if success:
                step.status = "done"
                ctx.outputs.append(f"[{step.title}]\n{step.output}")
                await self.emit_tasks(ctx)
                ctx.current_step_idx += 1
                ctx.retry_count = 0  # 成功后重置重试计数
                self.logger.info(f"Step completed successfully")
            else:
                step.status = "failed"
                await self.emit_tasks(ctx)
                self.logger.warning(f"Step failed: {step.error}")
                
                # Check if we should retry
                if ctx.retry_count < ctx.max_retries:
                    self.logger.info(f"Handing off to RepairAgent (retry {ctx.retry_count + 1}/{ctx.max_retries})")
                    return AgentResult(
                        success=False,
                        next_agent="RepairAgent",
                        message=f"Step failed: {step.error}"
                    )
                else:
                    self.logger.warning(f"Max retries reached, skipping step")
                    ctx.current_step_idx += 1
                    ctx.retry_count = 0
        
        # All steps completed - evaluate if goal is achieved
        self.logger.info("All steps executed, evaluating goal completion...")
        
        # Evaluate goal completion
        evaluation = await self._evaluate_goal_completion(ctx)
        
        if evaluation.startswith("COMPLETED"):
            self.logger.info("Goal completed, handing off to SummaryAgent")
            return AgentResult(
                success=True,
                next_agent="SummaryAgent",
                message="Goal completed"
            )
        
        elif evaluation.startswith("INCOMPLETE"):
            reason = evaluation.split(":", 1)[1] if ":" in evaluation else "目标未完成"
            self.logger.warning(f"Goal incomplete: {reason}")
            
            # Check if we're stuck in a loop (same failure reason)
            if reason == ctx.last_failure_reason:
                ctx.replan_count += 1
                self.logger.warning(f"Same failure reason detected, replan count: {ctx.replan_count}")
            else:
                ctx.last_failure_reason = reason
                ctx.replan_count = 0
            
            # Check if we should retry
            if ctx.replan_count < ctx.max_replans:
                await self.emit(ctx, "log", f"目标未完成: {reason}，尝试重新规划...")
                # Reset for re-planning
                ctx.steps = []  # Clear old steps
                ctx.current_step_idx = 0
                ctx.retry_count = 0
                # Add context about what failed
                ctx.memory.append({"role": "assistant", "content": f"上次执行未能完成目标：{reason}"})
                return AgentResult(
                    success=False,
                    next_agent="PlannerAgent",
                    message=f"Goal incomplete, replanning: {reason}"
                )
            else:
                self.logger.error(f"Max replans reached, giving up")
                await self.emit(ctx, "log", f"已达到最大重试次数，结束执行")
                return AgentResult(
                    success=False,
                    next_agent="SummaryAgent",
                    message="Max replans reached"
                )
        
        else:  # BLOCKED
            reason = evaluation.split(":", 1)[1] if ":" in evaluation else "遇到无法克服的障碍"
            self.logger.error(f"Goal blocked: {reason}")
            await self.emit(ctx, "log", f"无法继续: {reason}")
            return AgentResult(
                success=False,
                next_agent="SummaryAgent",
                message=f"Goal blocked: {reason}"
            )
    
    async def _execute_step(self, ctx: AgentContext, step) -> bool:
        """Execute a single step. Returns True on success."""
        try:
            self.logger.debug(f"Running command: {step.command}")
            
            # Get handlers for interactive prompts
            handlers = self._get_handlers(step.command)
            
            # 根据命令类型设置超时时间
            timeout = self._get_timeout(step.command)
            
            raw_output = await asyncio.to_thread(
                ctx.shell.run_command,
                step.command,
                handlers=handlers,
                timeout=timeout
            )
            
            output = clean_output(raw_output)
            step.output = output
            
            self.logger.debug(f"Command output ({len(output)} chars): {output[:200]}")
            
            # Send output to frontend
            await self.emit(ctx, "terminal", output)
            await self.emit(ctx, "log", f"输出: {output[:300]}")
            
            # Check for error patterns in output
            if check_fatal_error(output):
                step.error = extract_error_message(output)
                self.logger.warning(f"Error detected in output: {step.error}")
                return False
            
            return True
            
        except TimeoutError as e:
            step.error = f"命令超时: {e}"
            self.logger.error(f"Command timeout: {e}")
            await self.emit(ctx, "log", f"超时: {step.command}")
            return False
            
        except Exception as e:
            step.error = str(e)
            self.logger.error(f"Command exception: {e}")
            await self.emit(ctx, "log", f"失败: {e}")
            return False
    
    def _get_timeout(self, command: str) -> float:
        """Get appropriate timeout based on command type."""
        # 包管理命令需要更长时间
        if any(pkg in command for pkg in ["apt", "yum", "dnf", "pip", "npm", "wget", "curl", "git clone"]):
            return 180.0
        # 服务操作
        if "systemctl" in command:
            return 60.0
        # 编译安装
        if any(cmd in command for cmd in ["make", "cmake", "configure", "build"]):
            return 300.0
        # 默认超时
        return 60.0
    
    def _get_handlers(self, command: str) -> list:
        """Get interactive prompt handlers based on command."""
        handlers = []
        
        # 包管理器确认
        if any(pkg in command for pkg in ["apt", "yum", "dnf"]):
            handlers.extend([
                (r"Do you want to continue\? \[Y/n\]", "y"),
                (r"是否继续.*\[Y/n\]", "y"),
                (r"Is this ok \[y/N\]", "y"),
                (r"Is this ok \[y/d/N\]", "y"),
                (r"\[Y/n\]", "y"),
                (r"\[y/N\]", "y"),
            ])
        
        # MySQL/MariaDB
        if any(db in command for db in ["mysql", "mariadb"]):
            handlers.append((r"Enter password:", ""))
            handlers.append((r"Password:", ""))
        
        # 删除确认
        if "rm" in command:
            handlers.append((r"remove.*\?", "y"))
            handlers.append((r"是否删除", "y"))
        
        # SSH/SCP
        if any(ssh in command for ssh in ["ssh", "scp"]):
            handlers.extend([
                (r"Are you sure you want to continue connecting", "yes"),
                (r"password:", ""),
            ])
        
        # Git
        if "git" in command:
            handlers.extend([
                (r"Username for", ""),
                (r"Password for", ""),
            ])
        
        return handlers
    
    def _is_catastrophic(self, command: str) -> bool:
        """
        Check if command could cause catastrophic system damage.
        This is the last line of defense.
        """
        cmd_lower = command.lower().replace(" ", "")
        
        # 删除根目录 - 只有直接删除 / 才算危险
        # 允许 /var/cache/* 等子目录的清理
        if "rm" in cmd_lower and ("-rf" in cmd_lower or "-fr" in cmd_lower or "-r" in cmd_lower):
            # 直接删除根目录
            if "rm-rf/" in cmd_lower.replace(" ", "") or "rm-fr/" in cmd_lower.replace(" ", ""):
                # 检查是否是 "rm -rf /" 而不是 "rm -rf /some/path"
                import re
                if re.search(r'rm\s+(-[rf]+\s+)+/\s*$', command) or re.search(r'rm\s+(-[rf]+\s+)+/\s*&&', command):
                    return True
        
        # 格式化磁盘
        if "mkfs" in cmd_lower and "/dev/" in command:
            return True
        
        # dd 写入磁盘
        if "dd" in cmd_lower and "of=/dev/" in command:
            return True
        
        # 覆写磁盘
        if ">/dev/sd" in cmd_lower or ">/dev/nvme" in cmd_lower:
            return True
        
        # Fork bomb
        if ":(){" in command or ":()" in command:
            return True
        
        # 删除关键系统目录（直接删除，不是子目录）
        critical_paths = ["/bin", "/sbin", "/usr", "/lib", "/lib64", "/boot", "/etc"]
        if "rm" in cmd_lower and ("-rf" in cmd_lower or "-fr" in cmd_lower):
            import re
            for path in critical_paths:
                # 匹配 "rm -rf /bin" 或 "rm -rf /bin/" 但不匹配 "rm -rf /bin/something"
                pattern = rf'rm\s+(-[rf]+\s+)+{re.escape(path)}/?(\s|$|&&|\|)'
                if re.search(pattern, command):
                    return True
        
        return False
    
    async def _evaluate_goal_completion(self, ctx: AgentContext) -> str:
        """
        Use LLM to evaluate if the user's goal has been achieved.
        Returns: COMPLETED | INCOMPLETE:reason | BLOCKED:reason
        """
        # Build execution summary
        summary_parts = []
        done_count = sum(1 for s in ctx.steps if s.status == "done")
        failed_count = sum(1 for s in ctx.steps if s.status == "failed")
        
        summary_parts.append(f"共执行 {len(ctx.steps)} 步，成功 {done_count}，失败 {failed_count}")
        summary_parts.append("")
        
        for i, step in enumerate(ctx.steps):
            status = "✓" if step.status == "done" else "✗"
            summary_parts.append(f"{status} 步骤{i+1}: {step.title}")
            if step.output:
                output_preview = step.output[:150] if len(step.output) > 150 else step.output
                summary_parts.append(f"   输出: {output_preview}")
            if step.error:
                summary_parts.append(f"   错误: {step.error}")
        
        execution_summary = "\n".join(summary_parts)
        
        # Truncate if too long
        if len(execution_summary) > 2000:
            execution_summary = execution_summary[:2000] + "\n...(已截断)"
        
        prompt = format_prompt(GOAL_EVALUATION, goal=ctx.goal, execution_summary=execution_summary)
        
        try:
            result = await ctx.llm.complete_async(prompt, [], temperature=0.1)
            result = result.strip().upper()
            
            self.logger.info(f"Goal evaluation result: {result}")
            
            # Normalize result
            if result.startswith("COMPLETED"):
                return "COMPLETED"
            elif result.startswith("INCOMPLETE"):
                return result
            elif result.startswith("BLOCKED"):
                return result
            else:
                # Default: if mostly successful, consider complete
                if done_count >= len(ctx.steps) * 0.7:
                    return "COMPLETED"
                else:
                    return f"INCOMPLETE:部分步骤失败"
                    
        except Exception as e:
            self.logger.error(f"Goal evaluation failed: {e}")
            # Fallback: use simple heuristic
            if failed_count == 0:
                return "COMPLETED"
            elif done_count > failed_count:
                return "COMPLETED"
            else:
                return f"INCOMPLETE:执行失败"


__all__ = ["ExecutorAgent"]
