"""
ShellManager: Robust PTY shell management with reliable command completion detection.

Key design decisions:
1. Use a unique end-marker instead of relying on PS1 prompt matching
2. Append `echo MARKER` after each command to detect completion reliably
3. Set TERM=dumb to disable colors and special formatting
4. Clean ANSI escape codes from all output
"""

import os
import re
import threading
import time
from collections import deque
from typing import Callable, Iterable, List, Optional, Pattern, Tuple, Union

import pexpect


PromptType = Union[str, Pattern[str]]
Handler = Tuple[PromptType, str]

# 使用极其独特的标记，绝不可能出现在正常命令输出中
END_MARKER = "<<::CMD_DONE_7f3e9a::>>"


class ShellManager:
    """
    Maintains a persistent interactive shell using pexpect.
    Uses end-marker technique for reliable command completion detection.
    """

    def __init__(
        self,
        shell: str = "/bin/bash",
        encoding: str = "utf-8",
        default_timeout: float = 60.0,
        history_limit: int = 2000,
    ) -> None:
        self.shell_cmd = shell
        self.encoding = encoding
        self.default_timeout = default_timeout
        self.history: deque[str] = deque(maxlen=history_limit)
        self.child: Optional[pexpect.spawn] = None
        self._lock = threading.Lock()
        self._started = False
        
        # 编译正则表达式
        self._end_pattern = re.compile(re.escape(END_MARKER))
        self._ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def start(self) -> None:
        """Start the shell session."""
        if self._started and self.child and self.child.isalive():
            return
        
        # 继承当前环境，只修改必要的变量
        env = os.environ.copy()
        env["TERM"] = "dumb"
        env["LC_ALL"] = "C"  # 统一语言环境，避免本地化问题
        
        self.child = pexpect.spawn(
            self.shell_cmd,
            encoding=self.encoding,
            echo=False,
            timeout=self.default_timeout,
            env=env,
        )
        
        # 等待 shell 初始化
        time.sleep(0.2)
        
        # 禁用各种可能干扰的 shell 特性
        init_commands = [
            'export TERM=dumb',
            'export PS1=""',
            'export PS2=""', 
            'export PROMPT_COMMAND=""',
            'unset MAILCHECK',
            'set +o history',  # 禁用历史记录
        ]
        
        for cmd in init_commands:
            self.child.sendline(cmd)
            time.sleep(0.05)
        
        # 清空缓冲区
        time.sleep(0.3)
        self._drain_buffer()
        
        self._started = True

    def _drain_buffer(self) -> str:
        """读取并丢弃缓冲区中的所有数据"""
        chunks = []
        try:
            while True:
                chunk = self.child.read_nonblocking(size=4096, timeout=0.1)
                if chunk:
                    chunks.append(chunk)
        except (pexpect.TIMEOUT, pexpect.EOF):
            pass
        return "".join(chunks)

    def close(self) -> None:
        """Close the shell session."""
        if self.child and self.child.isalive():
            try:
                self.child.sendline("exit")
                self.child.close(force=True)
            except:
                pass
        self._started = False

    def _push_history(self, chunk: str) -> None:
        if chunk:
            self.history.append(chunk)

    def run_command(
        self,
        command: str,
        handlers: Optional[Iterable[Handler]] = None,
        timeout: Optional[float] = None,
        on_stream: Optional[Callable[[str, str], None]] = None,
    ) -> str:
        """
        Run a command and wait for completion.

        Uses end-marker technique: appends `echo END_MARKER` after the command
        and waits for the marker to appear in output.

        Args:
            command: Shell command to execute
            handlers: List of (pattern, response) pairs for interactive prompts
            timeout: Command timeout in seconds
            on_stream: Callback for streaming output

        Returns:
            Command output (cleaned)
        """
        if not self.child or not self.child.isalive():
            raise RuntimeError("Shell not started")

        eff_timeout = timeout or self.default_timeout
        handler_list: List[Handler] = list(handlers or [])
        
        with self._lock:
            # 清空之前的缓冲区
            self._drain_buffer()
            
            # 发送命令，然后发送 echo 标记
            # 使用 ; 确保即使命令失败也会打印标记
            full_command = f"{command}; echo '{END_MARKER}'"
            self.child.sendline(full_command)
        
        # 收集输出直到看到结束标记
        output_chunks: List[str] = []
        start = time.time()
        
        while True:
            elapsed = time.time() - start
            if elapsed >= eff_timeout:
                raise TimeoutError(f"Command timeout after {eff_timeout}s: {command}")
            
            remaining = max(0.1, eff_timeout - elapsed)
            
            # 构建匹配模式：handlers + end marker + timeout + eof
            patterns = [h[0] for h in handler_list] + [self._end_pattern, pexpect.TIMEOUT, pexpect.EOF]
            
            try:
                idx = self.child.expect(patterns, timeout=min(remaining, 2.0))
            except pexpect.TIMEOUT:
                continue
            except pexpect.EOF:
                if self.child.before:
                    output_chunks.append(self.child.before)
                break
            
            # 检查匹配结果
            before_text = self.child.before or ""
            
            if idx < len(handler_list):
                # 匹配到交互提示，发送响应
                output_chunks.append(before_text)
                if on_stream and before_text:
                    on_stream("terminal", before_text)
                response = handler_list[idx][1]
                with self._lock:
                    self.child.sendline(response)
                continue
            
            if patterns[idx] is pexpect.TIMEOUT:
                continue
            
            if patterns[idx] is pexpect.EOF:
                output_chunks.append(before_text)
                break
            
            # 匹配到结束标记 - 命令完成
            output_chunks.append(before_text)
            break
        
        # 合并并清理输出
        full_output = "".join(output_chunks)
        cleaned = self._clean_output(full_output, command)
        
        self._push_history(cleaned)
        return cleaned

    def _clean_output(self, text: str, command: str) -> str:
        """
        Clean command output:
        1. Remove ANSI escape sequences
        2. Remove command echo
        3. Remove end marker
        4. Strip whitespace
        """
        # 移除 ANSI 转义序列
        text = self._ansi_escape.sub('', text)
        
        # 移除结束标记
        text = text.replace(END_MARKER, '')
        
        # 按行处理
        lines = text.splitlines()
        cleaned_lines = []
        
        for i, line in enumerate(lines):
            # 跳过包含完整命令的行（命令回显）
            if i == 0 and command in line:
                continue
            # 跳过只有 echo 命令的行
            if f"echo '{END_MARKER}'" in line or f'echo "{END_MARKER}"' in line:
                continue
            cleaned_lines.append(line)
        
        return "\n".join(cleaned_lines).strip()

    def run_command_simple(self, command: str, timeout: float = 30.0) -> str:
        """
        Simple synchronous command execution.
        Convenience wrapper for run_command.
        """
        return self.run_command(command, timeout=timeout)


__all__ = ["ShellManager"]
