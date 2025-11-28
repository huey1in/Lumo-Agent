"""
AgentOrchestrator: Manages the agent chain and handoffs.
"""

import logging
from typing import Dict, List, Optional, Type

from agents.base import BaseAgent, AgentContext, AgentResult, Step, StreamCallback
from agents.router import RouterAgent
from agents.chat import ChatAgent
from agents.planner import PlannerAgent
from agents.executor import ExecutorAgent
from agents.repair import RepairAgent
from agents.summary import SummaryAgent


class AgentOrchestrator:
    """
    Orchestrates the multi-agent workflow.
    
    Flow:
        RouterAgent → ChatAgent (chat) or PlannerAgent (task)
        PlannerAgent → ExecutorAgent
        ExecutorAgent → RepairAgent (on failure) or SummaryAgent (on complete)
        RepairAgent → ExecutorAgent (retry)
        SummaryAgent → End
    """
    
    def __init__(self, llm, shell):
        self.logger = logging.getLogger("Orchestrator")
        self.llm = llm
        self.shell = shell
        
        # Register all agents
        self.agents: Dict[str, BaseAgent] = {
            "RouterAgent": RouterAgent(),
            "ChatAgent": ChatAgent(),
            "PlannerAgent": PlannerAgent(),
            "ExecutorAgent": ExecutorAgent(),
            "RepairAgent": RepairAgent(),
            "SummaryAgent": SummaryAgent(),
        }
        
        self.logger.info(f"Orchestrator initialized with {len(self.agents)} agents")
    
    async def run(
        self, 
        goal: str, 
        stream: Optional[StreamCallback] = None,
        memory: Optional[List[Dict]] = None
    ) -> List[Step]:
        """
        Run the agent chain for a given goal.
        
        Args:
            goal: User's goal/message
            stream: Callback for streaming updates to frontend
            memory: Conversation history
            
        Returns:
            List of executed steps
        """
        self.logger.info(f"Starting orchestration for goal: {goal[:50]}...")
        
        # Create context
        ctx = AgentContext(
            goal=goal,
            memory=memory or [],
            llm=self.llm,
            shell=self.shell,
            emit=stream,
            max_retries=3,  # 增加重试次数
        )
        
        # Start with RouterAgent
        current_agent = "RouterAgent"
        max_iterations = 20  # Safety limit
        iteration = 0
        
        while current_agent and iteration < max_iterations:
            iteration += 1
            self.logger.info(f"[Iteration {iteration}] Running {current_agent}")
            
            agent = self.agents.get(current_agent)
            if not agent:
                self.logger.error(f"Unknown agent: {current_agent}")
                break
            
            try:
                result = await agent.run(ctx)
                self.logger.debug(f"{current_agent} result: success={result.success}, next={result.next_agent}")
                
                # Move to next agent
                current_agent = result.next_agent
                
            except Exception as e:
                self.logger.error(f"{current_agent} crashed: {e}", exc_info=True)
                # Try to recover by sending error and stopping
                if ctx.emit:
                    try:
                        await ctx.emit("error", f"Agent 错误: {e}")
                    except:
                        pass
                break
        
        if iteration >= max_iterations:
            self.logger.error("Max iterations reached, stopping")
        
        self.logger.info(f"Orchestration complete. Executed {len(ctx.steps)} steps")
        return ctx.steps


__all__ = ["AgentOrchestrator"]
