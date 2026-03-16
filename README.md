# Ukr War Bot (Telegram)

## Quick start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set environment variables:
   ```bash
   set BOT_TOKEN=your_token_here
   set ADMIN_ID=123456789
   ```
   For PowerShell:
   ```powershell
   $env:BOT_TOKEN="your_token_here"
   $env:ADMIN_ID="123456789"
   ```

3. Run:
   ```bash
   python bot.py
   ```

## Files

- `bot.py` - Telegram handlers and commands.
- `game_engine.py` - battle logic, morale, logistics, passive income.
- `map_generator.py` - battle and territory image generation (AI + fallback).
- `database.py` - SQLite tables and persistence.
- `config.py` - app settings and game constants.
