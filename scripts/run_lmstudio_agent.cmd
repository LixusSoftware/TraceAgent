@echo off
setlocal

set MODEL_ID=%~1
set PROXY_URL=%~2

if "%MODEL_ID%"=="" (
  echo Usage: scripts\run_lmstudio_agent.cmd MODEL_ID [PROXY_URL]
  echo Example: scripts\run_lmstudio_agent.cmd qwen/qwen3-4b-2507
  exit /b 1
)

if "%PROXY_URL%"=="" set PROXY_URL=http://127.0.0.1:8000

set TRACE_AGENT_TEST_MODEL=%MODEL_ID%
set TRACE_AGENT_PROXY_URL=%PROXY_URL%

echo Running LM Studio example with model: %TRACE_AGENT_TEST_MODEL%
python examples\lm_studio_agent.py

