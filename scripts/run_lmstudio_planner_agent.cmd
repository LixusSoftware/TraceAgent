@echo off
setlocal

set SCENARIO=%~1
set PROXY_URL=%~2

if "%SCENARIO%"=="" set SCENARIO=meetup_plan
if "%PROXY_URL%"=="" set PROXY_URL=http://127.0.0.1:8000

set VISOR_PROXY_URL=%PROXY_URL%

echo Running complex LM Studio planner with scenario: %SCENARIO%
python examples\lm_studio_planner_agent.py --scenario %SCENARIO%

