@echo off
TITLE ETI SENTINEL - Debug Agent
SET INGEST_URL=https://monitoring-system-production-1e5a.up.railway.app/metrics

echo ==========================================
echo    ETI SENTINEL - Diagnostico do Agent
echo ==========================================
echo.

:: 1. Tenta encontrar o Python
echo [1/4] Verificando Python...
python --version >nul 2>&1
if %errorlevel% == 0 (
    set PY_CMD=python
) else (
    py --version >nul 2>&1
    if %errorlevel% == 0 (
        set PY_CMD=py
    ) else (
        echo [ERRO] Python nao encontrado! 
        echo Por favor, instale o Python em: https://www.python.org/downloads/
        echo Marque a opcao "Add Python to PATH" na instalacao.
        echo.
        echo Se ja instalou, feche esta janela e abra novamente.
        pause
        exit /b
    )
)
echo Python detectado como: %PY_CMD%

:: 2. Instala dependencias
echo.
echo [2/4] Instalando bibliotecas necessarias...
%PY_CMD% -m pip install --upgrade pip >nul 2>&1
%PY_CMD% -m pip install requests psutil
if %errorlevel% neq 0 (
    echo [AVISO] Falha ao instalar dependencias automaticamente. 
    echo Tentando rodar mesmo assim...
)

:: 3. Pede a URL da API (Se nao estiver definida)
echo.
if "%INGEST_URL%"=="https://monitoring-system-production-1e5a.up.railway.app/metrics" (
    echo [INFO] URL da API atual: %INGEST_URL%
    set /p CHANGE_URL="Deseja alterar a URL da API? (s/N): "
    if /i "%CHANGE_URL%"=="s" (
        set /p INGEST_URL="Digite a nova URL da API (ex: https://api.up.railway.app/metrics): "
    )
)

:: 4. Pede o Token
echo.
if "%DEVICE_TOKEN%"=="" (
    echo [!] Voce precisa do TOKEN do dispositivo.
    echo [!] No Painel Web: Menu Lateral -> Dispositivos -> Novo Dispositivo.
    echo [!] Depois de criar, clique no icone de 'Chave' para copiar o Token.
    echo.
    set /p TOKEN="[3/4] Cole o TOKEN do dispositivo aqui: "
) else (
    set TOKEN=%DEVICE_TOKEN%
)

if "%TOKEN%"=="" (
    echo [ERRO] Voce precisa colar o Token que pegou no Painel Web!
    pause
    exit /b
)

:: 5. Inicia
echo.
echo [4/4] Iniciando Local Agent...
echo Encontrando CAMERA em 192.168.0.102...
echo.
set DEVICE_TOKEN=%TOKEN%
%PY_CMD% local_agent.py

echo.
echo [INFO] O Agent parou de rodar. Verifique se ha erros acima.
pause
