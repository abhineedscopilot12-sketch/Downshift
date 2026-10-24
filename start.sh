#!/bin/bash
set -e
pip install -q openai fastapi uvicorn httpx python-dotenv
git clone --depth 1 https://github.com/abhineedscopilot12-sketch/Downshift /app
cd /app
exec uvicorn downshift:app --host 0.0.0.0 --port 8000
