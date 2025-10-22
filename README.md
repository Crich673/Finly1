# Finly1

## Getting started

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r finance_bot/requirements.txt
   ```
3. Copy `.env.example` to `.env` (or create `.env`) and provide values for the required API keys (e.g., `OPENAI_API_KEY`).
4. Initialize the SQLite database (tables are created automatically on first launch).

## Running the bot

```bash
python -m finance_bot.main
```

Make sure the `TELEGRAM_BOT_TOKEN` environment variable is set before running the bot.

## Testing the project

The project does not have automated tests yet, but you can perform a quick smoke check that all modules compile with:

```bash
python -m compileall finance_bot
```

To test the bot manually:

1. Start the bot locally (`python -m finance_bot.main`).
2. Open Telegram and send `/start` to the bot to ensure it responds.
3. Use `/income 50000` (replace with your desired number) and confirm the bot stores the income and returns a generated budget suggestion.
4. Send a receipt photo; the bot should OCR the image, categorize the items, and ask whether you want to adjust categories via inline buttons.
5. Use the inline buttons to edit categories and ensure the feedback is saved.

Monitor the console logs for any errors while running these steps.
