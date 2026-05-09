#!/usr/bin/env bash
# Boots a llama.cpp OpenAI-compatible server for Mem0 fact extraction.
# Uses the Qwen3-4B tool model (best for structured extraction tasks).
# Port 8181 — separate from any existing llama.cpp usage.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="$SCRIPT_DIR/models/mlabonne_Qwen3-4B-abliterated-Q4_K_M.gguf"

if [ ! -f "$MODEL" ]; then
    echo "ERROR: Model not found at $MODEL"
    exit 1
fi

echo "Starting Mem0 extraction server on port 8181..."
"$SCRIPT_DIR/.venv/bin/python3" -m llama_cpp.server \
    --model "$MODEL" \
    --n_ctx 1024 \
    --n_batch 128 \
    --port 8181 \
    --host 127.0.0.1 \
    --verbose false &

SERVER_PID=$!
echo "Extraction server PID: $SERVER_PID"
echo $SERVER_PID > "$SCRIPT_DIR/data/mem0_server.pid"
