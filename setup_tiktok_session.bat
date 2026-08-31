@echo off
title TikTok Session Setup (One-Time Login)
echo ========================================================
echo   TikTok Persistent Browser Session Setup
echo ========================================================
echo.
cd /d "%~dp0"
py tools\setup_tiktok_session.py
echo.
echo Process finished.
pause
