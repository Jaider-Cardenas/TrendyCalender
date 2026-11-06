@echo off
title Trendy Shop Monitor
cd /d "%~dp0"

echo ===================================================
echo     Iniciando Trendy Shop Monitor (Adviento / 1016)
echo ===================================================
echo.

:: Verificar si python esta instalado
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] No se encontro Python en el sistema.
    echo Por favor instala Python desde https://www.python.org o con:
    echo winget install Python.Python.3.12
    pause
    exit /b 1
)

:: Ejecutar el script (agrega --once si quieres que corra solo una vez y salga)
python trendy_monitor.py %*

if "%1"=="--once" (
    echo.
    echo Revision unica completada.
) else (
    pause
)
