@echo off
setlocal enabledelayedexpansion
title ETI SENTINEL - Verificador de Status
mode con: cols=70 lines=30
color 0a

set "DESTINO=C:\ProgramData\ETI-SENTINEL"
set "SVC_NAME=ETI_SENTINEL_EDGE_AGENT"

echo.
echo  ========================================================
echo    ETI SENTINEL EDGE - Verificador de Status
echo  ========================================================
echo.

:: Verifica se a pasta existe
if exist "!DESTINO!" (
    echo  [OK] Pasta de instalacao: !DESTINO!
) else (
    echo  [X] Agente NAO instalado. Execute o INSTALAR.bat primeiro.
    goto :fim
)

:: Verifica o executavel
if exist "!DESTINO!\ETI_SENTINEL_Edge.exe" (
    echo  [OK] Executavel encontrado.
) else (
    echo  [X] Executavel nao encontrado!
)

:: Verifica o .env
if exist "!DESTINO!\.env" (
    echo  [OK] Configuracao (.env) encontrada.
) else (
    echo  [X] Configuracao (.env) ausente!
)

:: Verifica ffmpeg
if exist "!DESTINO!\bin\ffmpeg.exe" (
    echo  [OK] FFmpeg encontrado.
) else (
    echo  [!] FFmpeg nao encontrado em bin\
)

:: Verifica NSSM
if exist "!DESTINO!\bin\nssm.exe" (
    echo  [OK] NSSM encontrado.
) else (
    echo  [!] NSSM nao encontrado. Modo: Agendador de Tarefas.
)

echo.
echo  Status do Servico/Tarefa:
echo  --------------------------------------------------------

:: Verifica servico Windows
sc query "!SVC_NAME!" >nul 2>&1
if !errorLevel! EQU 0 (
    for /f "tokens=3" %%s in ('sc query "!SVC_NAME!" ^| findstr "STATE"') do (
        echo  Servico Windows: %%s
    )
) else (
    :: Verifica tarefa agendada
    schtasks /query /tn "!SVC_NAME!" >nul 2>&1
    if !errorLevel! EQU 0 (
        echo  Tarefa Agendada: REGISTRADA
    ) else (
        echo  [X] Nenhum servico ou tarefa registrada!
        echo      Execute o INSTALAR.bat como Administrador.
    )
)

:: Verifica se a porta esta em uso (agente respondendo)
echo.
echo  Verificando Dashboard local (http://localhost:8808)...
powershell -NoProfile -Command ^
    "try { $r = Invoke-WebRequest 'http://localhost:8808/health' -TimeoutSec 3 -UseBasicParsing; Write-Host '  [OK] Dashboard ativo! Status:' $r.StatusCode } catch { Write-Host '  [!] Dashboard nao respondeu (agente pode estar iniciando).' }" 2>nul

:fim
echo.
echo  ========================================================
echo.
pause
endlocal
