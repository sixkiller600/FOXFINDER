@echo off
REM ExecutionPolicy Bypass allows running unsigned PowerShell scripts on Windows
title FoxFinder - Stopping...
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "FoxFinder OFF.ps1"
