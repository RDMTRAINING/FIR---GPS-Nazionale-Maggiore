#!/bin/bash
cd "$(dirname "$0")/.."
echo "🏉 Avvio Piattaforma FIR GPS Analytics sulla porta 8502..."
echo "👉 Apri nel browser: http://localhost:8502"
./venv/bin/streamlit run rugby_fir_app/app.py --server.port 8502
