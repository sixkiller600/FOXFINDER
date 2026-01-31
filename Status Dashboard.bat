@echo off
REM ExecutionPolicy Bypass allows running unsigned PowerShell scripts on Windows
title FoxFinder - Status Dashboard
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "Status Dashboard.ps1"
