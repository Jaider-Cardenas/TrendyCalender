@echo off
title Trendy Shop Monitor
cd /d "%~dp0"

echo ===================================================
echo     Trendy Shop Monitor (Adviento / 1016 / 0..299)
echo ===================================================
echo.

:: 1. Si existe Python, ejecutar con Python
where python >nul 2>nul
if %errorlevel% equ 0 (
    echo [*] Ejecutando con Python...
    python trendy_monitor.py %*
    goto end
)

:: 2. Si existe Node.js, ejecutar con Node
where node >nul 2>nul
if %errorlevel% equ 0 (
    echo [*] Ejecutando con Node.js...
    node trendy_monitor.js %*
    goto end
)

:: 3. Si no tiene Python ni Node, ejecutar con PowerShell nativo de Windows (no requiere instalar nada)
echo [*] Python o Node no detectados. Ejecutando con PowerShell nativo de Windows...
powershell -ExecutionPolicy Bypass -File "%~dp0trendy_monitor.ps1" %*

:end
if "%1"=="--once" (
    echo.
    echo Revision unica completada.
) else if "%1"=="-Once" (
    echo.
    echo Revision unica completada.
) else (
    pause
)
