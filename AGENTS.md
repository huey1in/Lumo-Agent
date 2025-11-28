# Repository Guidelines

## Project Structure & Module Organization
- `main.py` hosts the FastAPI app and wires the `AgentOrchestrator`, `LLMClient`, and `ShellManager`.
- `agents/` contains the agent stack: routing, planning, execution, repair, summarization, and shared prompts.
- `llm/client.py` centralizes LLM calls; keep model- or vendor-specific tweaks here.
- `shell/manager.py` wraps PTY/pexpect-style shell interactions; avoid raw subprocess calls for interactive flows.
- `static/index.html` serves the bundled front-end; adjust the FastAPI static mount if paths change.
- `config.py` is the place for shared settings; prefer environment variables over hard-coded secrets.

## Build, Test, and Development Commands
- Create a virtualenv: `python -m venv .venv && .\\.venv\\Scripts\\activate`.
- Install deps (add a `requirements.txt` if missing): `pip install -r requirements.txt`.
- Run the API locally: `uvicorn main:app --reload --host 0.0.0.0 --port 8000` (or `python main.py` during development).
- Static preview: hit `/` after starting the server to serve `static/index.html`.
- Tests (when present): `pytest -q` or `pytest -k <pattern>`; add `-s` when debugging logs.

## Coding Style & Naming Conventions
- Python: 4-space indent; `snake_case` for functions/vars, `PascalCase` for classes; type hints for public interfaces.
- Keep agent/planner logic small and composable; inject dependencies (LLM, shell) rather than instantiating inline.
- Logging: use the module-level logger; avoid leaking secrets or full prompts in logs.
- Formatting/linting: prefer `black` and `ruff`; keep line lengths reasonable and imports organized.

## Testing Guidelines
- Use `pytest`; name files `tests/test_*.py` and mirror module paths (e.g., `tests/agents/test_planner.py`).
- Mock LLM calls and PTY I/O to avoid network and shell flakiness; keep fixtures async where applicable.
- Validate planner transitions, retry/repair paths, and shell timeouts; favor deterministic prompt fixtures.
- Add regression tests before changing prompts or routing logic to guard behavior.

## Commit & Pull Request Guidelines
- Follow Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`); keep subjects ≤72 chars and bodies explaining rationale.
- PRs should outline scope, list test commands run, link related issues, and include screenshots/GIFs for UI changes to `static/`.
- Note breaking changes, config/env updates, and new external service requirements explicitly.
- Keep diffs small and focused; prefer incremental PRs over broad refactors.

## Agent & Shell Notes
- Shell interactions should remain under `ShellManager` to capture logs and manage prompts safely; prefer timeout-aware calls.
- When extending prompts or planner steps, keep responses structured (`{type: "log" | "thought" | "terminal", content}`) to avoid UI regressions.
- Store secrets in environment variables and load them through `config.py`; never hard-code keys or tokens.
