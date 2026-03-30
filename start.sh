#!/bin/bash
# Start backend + frontend
PROJ="$(cd "$(dirname "$0")" && pwd)"

fuser -k 8000/tcp 2>/dev/null
fuser -k 3000/tcp 2>/dev/null
sleep 1

# Backend — must use ocr_env so deepdoctection is available
cd "$PROJ/backend" && PYTHONPATH="$PROJ/backend" \
  TRANSFORMERS_VERBOSITY=error \
  HF_HUB_DISABLE_PROGRESS_BARS=1 \
  TOKENIZERS_PARALLELISM=false \
  HF_HUB_DISABLE_SYMLINKS_WARNING=1 \
  uvicorn main:app --reload --port 8000 &

# Frontend
cd "$PROJ/Frontend/react-app" && npm run dev &

echo "✅ Backend: http://localhost:8000"
echo "✅ Frontend: http://localhost:3000"
wait
