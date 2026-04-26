#!/bin/bash

# ETI SENTINEL Universal Agent (Shell Edition)
# Uso: ./nexuswatch_agent.sh <URL_API> <TOKEN_OU_MAC> [INTERVALO_SEGUNDOS]

API_URL=$1
TOKEN=$2
INTERVAL=${3:-60}

if [ -z "$API_URL" ] || [ -z "$TOKEN" ]; then
    echo "Uso: $0 <URL_API> <TOKEN_OU_MAC> [INTERVALO_SEGUNDOS]"
    echo "Exemplo: $0 https://sua-api.railway.app/push 00:11:22:33:44:55 60"
    exit 1
fi

echo "🚀 ETI SENTINEL Agent Iniciado..."
echo "📡 Alvo: $API_URL"
echo "🔑 ID: $TOKEN"
echo "⏱️ Intervalo: ${INTERVAL}s"

while true; do
    # Tenta enviar via curl (silencioso)
    # Enviamos o token tanto no header quanto no body para garantir
    RESPONSE=$(curl -s -X POST "$API_URL" \
        -H "Content-Type: application/json" \
        -H "x-device-token: $TOKEN" \
        -d "{\"token\":\"$TOKEN\", \"status\":\"online\", \"type\":\"heartbeat\"}")
    
    if [[ $RESPONSE == *"\"ok\":true"* ]]; then
        echo "[$(date +'%H:%M:%S')] ✅ Heartbeat enviado com sucesso."
    else
        echo "[$(date +'%H:%M:%S')] ❌ Erro ao enviar sinal: $RESPONSE"
    fi
    
    sleep $INTERVAL
done
