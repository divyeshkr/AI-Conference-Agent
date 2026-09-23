#!/bin/bash
# Azure App Service (Linux) startup command.
# App Service terminates TLS and proxies to $PORT, so CORS/XSRF checks on the
# origin have to be relaxed or the WebSocket handshake is rejected.
python -m streamlit run app.py \
  --server.port "${PORT:-8000}" \
  --server.address 0.0.0.0 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --browser.gatherUsageStats false
