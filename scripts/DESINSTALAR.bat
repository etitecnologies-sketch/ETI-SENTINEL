@echo off
setlocal enabledelayedexpansion
title ETI SENTINEL - Desinstalador
mode con: cols=70 lines=20
color 0c

:: ---- Verificacao de Administrador ----------------------
net session >nul 2>&1
if !errorLevel! NEQ 0 (
    echo.
    echo  [!] Execute como Administrador!
    echo  Clique com o botao direito e "Executar como administrador"
    echo.
    pause
    exit /b 1
)

echo.
echo  ========================================================
echo    ETI SENTINEL EDGE - Desinstalador
echo  ========================================================
echo.
echo  Isso vai remover o agente e todos os arquivos.
echo  Tem certeza? (S para confirmar, qualquer outra tecla cancela)
echo.
set /p "CONF=  Confirmar remocao (S/N): "
if /i not "!CONF!"=="S" (
    echo  Desinstalacao cancelada.
    pause
    exit /b 0
)

echo.
set "DESTINO=C:\ProgramData\ETI-SENTINEL"
set "SVC_NAME=ETI_SENTINEL_EDGE_AGENT"
set "NSSM=!DESTINO!\bin\nssm.exe"

echo  Parando o agente...
if exist "!NSSM!" (
    "!NSSM!" stop "!SVC_NAME!" >nul 2>&1
    "!NSSM!" remove "!SVC_NAME!" confirm >nul 2>&1
) else (
    sc stop "!SVC_NAME!" >nul 2>&1
    sc delete "!SVC_NAME!" >nul 2>&1
    schtasks /delete /tn "!SVC_NAME!" /f >nul 2>&1
)
echo  OK: Servico removido.

if exist "!DESTINO!" (
    timeout /t 2 /nobreak >nul
    rmdir /s /q "!DESTINO!" >nul 2>&1
    echo  OK: Arquivos removidos de !DESTINO!
)

echo.
echo  ETI SENTINEL foi removido com sucesso.
echo.
pause
endlocal
