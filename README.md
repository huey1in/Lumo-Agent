# Lumo Agent

**Linux 系统自动化 AI 助手**

Lumo Agent 是一个基于多智能体架构的 Linux 运维自动化工具，通过自然语言交互实现系统管理任务的智能执行。

## 特性

- **多智能体协作** - Router、Planner、Executor、Repair、Summary 多个专业智能体协同工作
- **智能错误修复** - 自动检测失败并尝试修复，支持多次重试
- **目标驱动执行** - 自动评估任务完成度，未完成时重新规划
- **实时交互** - WebSocket 实时推送执行状态和输出

## 架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Router    │ ──▶ │   Planner  │ ──▶ │  Executor   │
│  (意图分类) │     │  (任务规划)  │     │  (命令执行)  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                    ┌─────────────┐     ┌──────▼──────┐
                    │   Summary   │ ◀── │  Repair    │
                    │  (结果总结)  │    │  (错误修复) │
                    └─────────────┘     └─────────────┘
```

## 快速开始

### 环境要求

- Python 3.10+
- Linux 服务器（用于执行命令）
- OpenAi API Key

### 安装

```bash
# 克隆项目
git clone https://github.com/huey1in/Lumo-Agent.git
cd Lumo-Agent

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 配置

设置环境变量或修改 `config.py`：

```bash
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_API_KEY="your-api-key"
export LLM_MODEL="Pro/deepseek-ai/DeepSeek-R1"
```

### 运行

```bash
# 启动服务
python main.py

# 或使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000` 打开 Web 界面。

## 使用示例

```
用户: 帮我安装 nginx 并启动
AI: 我将帮你完成 nginx 的安装和启动...

用户: 查看系统内存使用情况
AI: 正在检查系统内存...

用户: 创建一个名为 devuser 的用户
AI: 正在创建用户 devuser...
```

## 项目结构

```
lumo-agent/
├── main.py              # FastAPI 入口
├── config.py            # 配置文件
├── agents/              # 智能体模块
│   ├── base.py          # 基础类定义
│   ├── router.py        # 意图路由
│   ├── planner.py       # 任务规划
│   ├── executor.py      # 命令执行
│   ├── repair.py        # 错误修复
│   ├── summary.py       # 结果总结
│   ├── chat.py          # 闲聊处理
│   ├── orchestrator.py  # 智能体编排
│   └── prompts.py       # Prompt 模板
├── llm/
│   └── client.py        # LLM 客户端
├── shell/
│   └── manager.py       # Shell 管理器
└── static/
    └── index.html       # Web 界面
```

## 安全说明

Lumo Agent 具有 root 权限执行系统命令的能力，内置了多层安全防护：

1. **Planner 层** - 检测并阻止危险命令模式
2. **Executor 层** - 最后一道防线，阻止灾难性命令
3. **阻止的危险操作**：
   - `rm -rf /` 删除根目录
   - `mkfs` 格式化磁盘
   - `dd of=/dev/` 覆写磁盘
   - Fork bomb 等

**请在测试/开发环境中使用，生产环境请谨慎评估风险。**

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

---

Made with by 1in
