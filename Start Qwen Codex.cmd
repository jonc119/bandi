@echo off
setlocal
cd /d "%~dp0"

where codex >nul 2>nul
if errorlevel 1 (
  echo Codex CLI was not found on PATH.
  pause
  exit /b 1
)

curl.exe --silent --fail --max-time 5 http://127.0.0.1:11434/api/tags >nul
if errorlevel 1 (
  echo Ollama is not reachable at http://127.0.0.1:11434.
  pause
  exit /b 1
)

if exist "%USERPROFILE%\.codex\qwen.config.toml" (
  codex -p qwen --oss --local-provider ollama -m qwen3.8:latest --strict-config -C "%~dp0" "Read AGENTS.md and HANDOFF.md. Inspect git status, git diff, and the last 10 commits. Do not modify anything yet. First explain the current state, unfinished changes, and your intended next action. Then continue the current task under AGENTS.md. Before stopping, run validation, review the diff, and update HANDOFF.md."
) else (
  codex --oss --local-provider ollama -m qwen3.8:latest -s workspace-write -a on-request -C "%~dp0" "Read AGENTS.md and HANDOFF.md. Inspect git status, git diff, and the last 10 commits. Do not modify anything yet. First explain the current state, unfinished changes, and your intended next action. Then continue the current task under AGENTS.md. Before stopping, run validation, review the diff, and update HANDOFF.md."
)

pause
