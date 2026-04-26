#!/bin/sh

# Iniciar o Tailscale em background se a AuthKey estiver presente
if [ -n "$TAILSCALE_AUTHKEY" ]; then
    echo "Iniciando Tailscale (userspace-networking) no Monitor Processor..."
    tailscaled --state=/tmp/tailscaled.state --socket=/tmp/tailscaled.sock --tun=userspace-networking &
    
    (
      sleep 5
      echo "Autenticando no Tailscale (Processor) em background..."
      tailscale --socket=/tmp/tailscaled.sock up --authkey=$TAILSCALE_AUTHKEY --hostname=eti-sentinel-processor --accept-routes
      echo "Processor Conectado à Rede Privada Tailscale!"
    ) &
else
    echo "Aviso: TAILSCALE_AUTHKEY não definida no Processor. Rodando sem VPN..."
fi

# Inicia o monitor principal e o monitor solar em paralelo
echo "Iniciando Monitores..."
python main.py &
python solar_monitor.py &
wait
