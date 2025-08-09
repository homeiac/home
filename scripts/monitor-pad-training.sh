#!/bin/bash

# Monitor PAD memory usage until training completes (pod becomes Ready)
# Saves results to /tmp/pad-memory-usage.log

LOG_FILE="/tmp/pad-memory-usage.log"
MAX_MEMORY=0
START_TIME=$(date)

echo "Starting PAD training memory monitoring at $START_TIME" > $LOG_FILE
echo "Timestamp,Memory_MB,CPU,Status,Max_Memory_So_Far" >> $LOG_FILE

while true; do
    # Get pod status and metrics
    POD_STATUS=$(kubectl --server=https://192.168.4.236:6443 --insecure-skip-tls-verify get pod -n monitoring -l app=prometheus-anomaly-detector --no-headers 2>/dev/null | awk '{print $2}' | head -1)
    MEMORY=$(kubectl --server=https://192.168.4.236:6443 --insecure-skip-tls-verify top pod -n monitoring -l app=prometheus-anomaly-detector --no-headers 2>/dev/null | awk '{print $3}' | sed 's/Mi//' | head -1)
    CPU=$(kubectl --server=https://192.168.4.236:6443 --insecure-skip-tls-verify top pod -n monitoring -l app=prometheus-anomaly-detector --no-headers 2>/dev/null | awk '{print $2}' | head -1)
    
    if [ ! -z "$MEMORY" ] && [ "$MEMORY" -gt "$MAX_MEMORY" ]; then
        MAX_MEMORY=$MEMORY
    fi
    
    echo "$(date),$MEMORY,$CPU,$POD_STATUS,$MAX_MEMORY" >> $LOG_FILE
    
    # Check if pod is Ready (training complete)
    if [ "$POD_STATUS" = "1/1" ]; then
        echo "$(date): PAD training completed! Pod is Ready." >> $LOG_FILE
        echo "Maximum memory usage during training: ${MAX_MEMORY}MB" >> $LOG_FILE
        echo "Training monitoring complete. Results in $LOG_FILE"
        break
    fi
    
    # Check if pod failed
    if [[ "$POD_STATUS" =~ "Error" ]] || [[ "$POD_STATUS" =~ "CrashLoop" ]]; then
        echo "$(date): PAD pod failed with status: $POD_STATUS" >> $LOG_FILE
        echo "Training monitoring stopped due to pod failure. Results in $LOG_FILE"
        break
    fi
    
    sleep 60  # Check every minute
done