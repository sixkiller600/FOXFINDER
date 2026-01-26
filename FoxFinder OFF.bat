@echo off
title FoxFinder - Stopping...
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "FoxFinder OFF.ps1"
