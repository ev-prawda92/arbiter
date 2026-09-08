#!/bin/bash
set -euo pipefail

# Arbiter local startup script.
cd "$(dirname "$0")"
echo "🔧 Arbiter startup"
echo "---"

echo "→ Backend dependencies..."
python3 -m pip install --quiet -r backend/requirements.txt

echo "→ Frontend dependencies..."
cd frontend
npm install
echo "→ Building frontend..."
npm run build
cd ..

echo "→ Starting Arbiter on http://localhost:8000"
echo "---"
cd backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
