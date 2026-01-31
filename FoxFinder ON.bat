@echo off
REM ExecutionPolicy Bypass allows running unsigned PowerShell scripts on Windows
title FoxFinder - Starting...
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "FoxFinder ON.ps1"
