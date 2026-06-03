@echo off
setlocal enabledelayedexpansion
title ETI SENTINEL - Instalador v2.1
mode con: cols=70 lines=40
color 0b

:: ========================================================
::  ETI SENTINEL EDGE - Instalador Profissional v2.1
:: ========================================================

:: ---- Verificacao de Administrador ----------------------
net session >nul 2>&1
if !errorLevel! NEQ 0 (
    echo.
    echo  [!] PERMISSAO DE ADMINISTRADOR NECESSARIA
    echo.
    echo  Feche esta janela.
    echo  Clique com o botao direito em INSTALAR.bat
    echo  e selecione "Executar como administrador".
    echo.
    pause
    exit /b 1
)

echo.
echo  ========================================================
echo    ETI SENTINEL EDGE - Instalador v2.1
echo  ========================================================
echo.

:: ---- Verifica se o executavel existe --------------------
set "PASTA_ORIGEM=%~dp0"
if not exist "!PASTA_ORIGEM!ETI_SENTINEL_Edge.exe" (
    echo  [ERRO] ETI_SENTINEL_Edge.exe nao encontrado!
    echo  Execute o instalador dentro da pasta correta.
    echo.
    pause
    exit /b 1
)

:: ---- Aviso sobre FFmpeg (necessario para streaming) -----
if not exist "!PASTA_ORIGEM!bin\ffmpeg.exe" (
    echo  [AVISO] bin\ffmpeg.exe nao encontrado.
    echo  O streaming de cameras pode nao funcionar.
    echo  Adicione o ffmpeg.exe na pasta bin\ para ativar cameras.
    echo.
)

:: ---- Verifica o NSSM (gerenciador de servico) ----------
set "NSSM_BIN=!PASTA_ORIGEM!bin\nssm.exe"
set "USAR_NSSM=0"
if exist "!NSSM_BIN!" set "USAR_NSSM=1"

if "!USAR_NSSM!"=="0" (
    echo  [AVISO] bin\nssm.exe nao encontrado.
    echo  Modo alternativo: Agendador de Tarefas do Windows.
    echo  Para servico mais robusto, adicione nssm.exe em bin\.
    echo.
)

:: ========================================================
::  DADOS DO CLIENTE
:: ========================================================
echo  [1/5] Configuracao
echo  --------------------------------------------------------
echo.
set /p "CID=  ID do Cliente (numero, ex: 5): "
set /p "CKEY=  Chave Coletora (Collector Key): "
echo.

if "!CID!"=="" (
    echo  [ERRO] ID do Cliente obrigatorio!
    pause
    exit /b 1
)
if "!CKEY!"=="" (
    echo  [ERRO] Chave Coletora obrigatoria!
    pause
    exit /b 1
)

:: ========================================================
::  PREPARACAO DA PASTA
:: ========================================================
set "DESTINO=C:\ProgramData\ETI-SENTINEL"
set "SVC_NAME=ETI_SENTINEL_EDGE_AGENT"
set "EXE_DEST=!DESTINO!\ETI_SENTINEL_Edge.exe"

echo  [2/5] Preparando pasta de instalacao...
if not exist "!DESTINO!" mkdir "!DESTINO!" >nul 2>&1
if not exist "!DESTINO!\bin" mkdir "!DESTINO!\bin" >nul 2>&1
if not exist "!DESTINO!\.state" mkdir "!DESTINO!\.state" >nul 2>&1

if not exist "!DESTINO!" (
    echo  [ERRO] Nao foi possivel criar !DESTINO!
    pause
    exit /b 1
)
echo       OK: Pasta pronta em !DESTINO!

:: ========================================================
::  COPIA DE ARQUIVOS
:: ========================================================
echo  [3/5] Copiando arquivos (aguarde)...
copy /Y "!PASTA_ORIGEM!ETI_SENTINEL_Edge.exe" "!EXE_DEST!" >nul 2>&1
if !errorLevel! NEQ 0 (
    echo  [ERRO] Falha ao copiar o executavel!
    pause
    exit /b 1
)
if exist "!PASTA_ORIGEM!bin\" (
    xcopy /Y /I /E "!PASTA_ORIGEM!bin\*" "!DESTINO!\bin\" >nul 2>&1
)
echo       OK: Arquivos copiados.

:: ========================================================
::  CRIACAO DO .ENV (via PowerShell para caracteres especiais)
:: ========================================================
echo  [4/5] Criando configuracao...
set "PS_TMP=%TEMP%\eti_setup_%RANDOM%.ps1"

(
    echo param^($Key, $Cid, $Dest^)
    echo $content = @^(
    echo     'INGEST_API_URL=https://eti-sentinel-production.up.railway.app',
    echo     "COLLECTOR_KEY=$Key",
    echo     "CLIENT_ID=$Cid",
    echo     'AGENT_API_PORT=8808',
    echo     'AGENT_API_BIND=0.0.0.0',
    echo     'ENABLE_STREAMING=1',
    echo     'ENABLE_DEVICE_MONITOR=1',
    echo     'ENABLE_ONVIF_COLLECTOR=0',
    echo     'ENABLE_DISCOVERY=0',
    echo     'ENABLE_TRAY=0',
    echo     'ENABLE_RECORDING=0',
    echo     'LOG_LEVEL=INFO',
    echo     'EDGE_SUPPRESS_EVENT_TYPES=edge_heartbeat,gateway_heartbeat',
    echo     'EDGE_FORWARD_SUPPRESS_EVENT_TYPES=edge_heartbeat,gateway_heartbeat',
    echo     '# --- Analiticos de Video (requer ENABLE_AI_ANALYTICS=1) ---',
    echo     'ENABLE_AI_ANALYTICS=0',
    echo     'AI_STARTUP_DELAY_SECONDS=20',
    echo     'AI_CLASSES=person,car,motorcycle',
    echo     'AI_PEOPLE_MAX_COUNT=0',
    echo     '# AI_ZONES=[[0.0,0.0,1.0,1.0]]',
    echo     '# AI_CROSSING_LINES=[[0.5,0.0,0.5,1.0]]',
    echo     '# --- Features Avancadas (ativar com =1) ---',
    echo     '# ENABLE_DIRECTIONAL_COUNTER=1   # F7: Contador entrada/saida',
    echo     '# ENABLE_LOITERING=1             # F8: Permanencia prolongada',
    echo     '# ENABLE_HEATMAP=1               # F9: Mapa de calor',
    echo     '# ENABLE_FALL_DETECTION=1        # F10: Queda de pessoa',
    echo     '# ENABLE_FIRE_DETECTION=1        # F11: Fogo e fumaca',
    echo     '# ENABLE_TAMPER_DETECTION=1      # F12: Camera sabotada/coberta',
    echo     '# --- Gravacao e Relatorios ---',
    echo     '# ENABLE_CLIP_RECORDING=1        # Grava clip MP4 de 12s antes de cada alerta',
    echo     '# ENABLE_DAILY_REPORT=1          # Relatorio diario via Telegram as 23h',
    echo     '# --- Atualizacao automatica (OTA) ---',
    echo     'ENABLE_OTA=0',
    echo     'AGENT_VERSION=2.1.0'
    echo ^)
    echo [System.IO.File]::WriteAllLines^($Dest, $content, [System.Text.UTF8Encoding]::new^($false^)^)
) > "!PS_TMP!"

powershell -NoProfile -ExecutionPolicy Bypass -File "!PS_TMP!" ^
    -Key "!CKEY!" -Cid "!CID!" -Dest "!DESTINO!\.env" >nul 2>&1
del "!PS_TMP!" >nul 2>&1

if not exist "!DESTINO!\.env" (
    echo  [ERRO] Falha ao criar o arquivo de configuracao!
    pause
    exit /b 1
)
echo       OK: Configuracao salva.

:: ========================================================
::  REGISTRO DO SERVICO
:: ========================================================
echo  [5/5] Registrando no Windows...

if "!USAR_NSSM!"=="1" (

    :: Para e remove instalacao anterior
    "!NSSM_BIN!" stop "!SVC_NAME!" >nul 2>&1
    "!NSSM_BIN!" remove "!SVC_NAME!" confirm >nul 2>&1

    :: Registra como Servico real do Windows
    "!NSSM_BIN!" install "!SVC_NAME!" "!EXE_DEST!" >nul 2>&1
    if !errorLevel! NEQ 0 (
        echo  [ERRO] Falha ao registrar o servico Windows!
        pause
        exit /b 1
    )

    :: Configura comportamento do servico
    "!NSSM_BIN!" set "!SVC_NAME!" AppDirectory "!DESTINO!" >nul 2>&1
    "!NSSM_BIN!" set "!SVC_NAME!" AppRestartDelay 5000 >nul 2>&1
    "!NSSM_BIN!" set "!SVC_NAME!" AppStdout "!DESTINO!\.state\agent.log" >nul 2>&1
    "!NSSM_BIN!" set "!SVC_NAME!" AppStderr "!DESTINO!\.state\agent_error.log" >nul 2>&1
    "!NSSM_BIN!" set "!SVC_NAME!" Description "ETI SENTINEL Edge Agent" >nul 2>&1
    "!NSSM_BIN!" set "!SVC_NAME!" Start SERVICE_AUTO_START >nul 2>&1

    :: Inicia o servico agora
    "!NSSM_BIN!" start "!SVC_NAME!" >nul 2>&1
    echo       OK: Servico Windows instalado (inicia automatico com o PC).

) else (

    :: Modo alternativo: Agendador de Tarefas
    schtasks /delete /tn "!SVC_NAME!" /f >nul 2>&1
    schtasks /create /tn "!SVC_NAME!" /tr "\"!EXE_DEST!\"" ^
        /sc onstart /ru SYSTEM /rl HIGHEST /f >nul 2>&1
    if !errorLevel! NEQ 0 (
        echo  [ERRO] Falha ao criar tarefa agendada!
        pause
        exit /b 1
    )
    schtasks /run /tn "!SVC_NAME!" >nul 2>&1
    echo       OK: Tarefa agendada criada (inicia com o Windows).

)

:: ========================================================
::  SUCESSO
:: ========================================================
echo.
echo  ========================================================
echo.
echo    INSTALACAO CONCLUIDA!
echo.
echo    O agente esta rodando em segundo plano.
echo    Ele iniciara AUTOMATICAMENTE toda vez que
echo    este computador for ligado.
echo.
echo    Dashboard:    http://localhost:8808
echo    Logs:         !DESTINO!\.state\
echo    Config:       !DESTINO!\.env
echo.
echo  ========================================================
echo.
pause
endlocal
