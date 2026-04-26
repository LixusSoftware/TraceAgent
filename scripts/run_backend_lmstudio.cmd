@echo off
setlocal

set LM_BASE_URL=%~1
if "%LM_BASE_URL%"=="" set LM_BASE_URL=http://localhost:4321/v1

set VISOR_OPENAI_BASE_URL=%LM_BASE_URL%

echo Starting backend with LM Studio base URL: %VISOR_OPENAI_BASE_URL%
python -m uvicorn visor_agentico.main:app --reload

