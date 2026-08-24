#!/bin/bash
set -e

# Arbiter startup script — one command to run everything locally.

cd "$(dirname "$0")"
echo "🔧 Arbiter startup"
echo "---"

# Backend
echo "→ Backend dependencies..."
pip3 install --quiet --break-system-packages fastapi uvicorn httpx 2>/dev/null || true

# Frontend
echo "→ Frontend dependencies..."
cd frontend
npm install --quiet 2>/dev/null || true
echo "→ Building frontend..."
npm run build 2>/dev/null || true
cd ..

# Server
echo "→ Starting Arbiter on http://localhost:8000"
echo "---"
cd backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
