@echo off
title FoxFinder - Status Dashboard
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "Status Dashboard.ps1"
