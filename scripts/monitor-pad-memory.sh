#!/bin/bash

# Monitor PAD memory usage to determine appropriate limits
# Usage: ./monitor-pad-memory.sh

echo "Monitoring PAD memory usage..."
echo "Timestamp,Memory_Usage_MB,CPU_Usage"

while true; do
    # Get PAD pod metrics
    MEMORY=$(kubectl --server=https://192.168.4.236:6443 --insecure-skip-tls-verify top pod -n monitoring -l app=prometheus-anomaly-detector --no-headers 2>/dev/null | awk '{print $3}' | sed 's/Mi//')
    CPU=$(kubectl --server=https://192.168.4.236:6443 --insecure-skip-tls-verify top pod -n monitoring -l app=prometheus-anomaly-detector --no-headers 2>/dev/null | awk '{print $2}')
    
    if [ ! -z "$MEMORY" ]; then
        echo "$(date),${MEMORY},${CPU}"
    else
        echo "$(date),Pod not running,N/A"
    fi
    
    sleep 30
done