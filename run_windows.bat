@echo off
REM Быстрый запуск в Windows
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
if not exist .env copy .env.example .env
python bot.py
