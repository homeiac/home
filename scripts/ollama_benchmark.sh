#!/bin/bash

# Ollama Performance Benchmark Script
# Tests generation speed, GPU utilization, and response quality

OLLAMA_URL="http://localhost:11434"
MODEL="gemma3:4b"
LOG_FILE="/tmp/ollama_benchmark_$(date +%Y%m%d_%H%M%S).log"

echo "=== Ollama Performance Benchmark ===" | tee $LOG_FILE
echo "Timestamp: $(date)" | tee -a $LOG_FILE
echo "Model: $MODEL" | tee -a $LOG_FILE
echo "URL: $OLLAMA_URL" | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Test cases with different complexity levels
declare -a test_prompts=(
    "Hello"
    "Explain quantum computing in one sentence"
    "Write a detailed analysis of machine learning algorithms"
    "Create a comprehensive guide to Kubernetes networking with examples and best practices"
)

declare -a prompt_names=(
    "Simple_Greeting"
    "Medium_Technical" 
    "Complex_Analysis"
    "Long_Technical_Guide"
)

# Function to run single test
run_test() {
    local prompt="$1"
    local name="$2"
    local iteration="$3"
    
    echo "--- Test: $name (Iteration $iteration) ---" | tee -a $LOG_FILE
    echo "Prompt: $prompt" | tee -a $LOG_FILE
    
    # Record start time and GPU memory
    local start_time=$(date +%s.%3N)
    local gpu_mem_start=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    
    # Run inference with timing
    local response=$(curl -s -X POST "$OLLAMA_URL/api/generate" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"$MODEL\",\"prompt\":\"$prompt\",\"stream\":false}")
    
    local end_time=$(date +%s.%3N)
    local gpu_mem_end=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    
    # Parse response timing
    local total_duration=$(echo "$response" | jq -r '.total_duration // 0')
    local load_duration=$(echo "$response" | jq -r '.load_duration // 0')
    local prompt_eval_duration=$(echo "$response" | jq -r '.prompt_eval_duration // 0')  
    local eval_duration=$(echo "$response" | jq -r '.eval_duration // 0')
    local eval_count=$(echo "$response" | jq -r '.eval_count // 0')
    
    # Calculate metrics
    local wall_clock_time=$(echo "$end_time - $start_time" | bc)
    local tokens_per_second=$(echo "scale=2; $eval_count * 1000000000 / $eval_duration" | bc 2>/dev/null || echo "0")
    
    # Log results
    echo "Wall Clock Time: ${wall_clock_time}s" | tee -a $LOG_FILE
    echo "Total Duration: $(echo "scale=3; $total_duration / 1000000000" | bc)s" | tee -a $LOG_FILE
    echo "Load Duration: $(echo "scale=3; $load_duration / 1000000000" | bc)s" | tee -a $LOG_FILE
    echo "Prompt Eval Duration: $(echo "scale=3; $prompt_eval_duration / 1000000000" | bc)s" | tee -a $LOG_FILE
    echo "Eval Duration: $(echo "scale=3; $eval_duration / 1000000000" | bc)s" | tee -a $LOG_FILE
    echo "Tokens Generated: $eval_count" | tee -a $LOG_FILE
    echo "Tokens/Second: $tokens_per_second" | tee -a $LOG_FILE
    echo "GPU Memory Start: ${gpu_mem_start}MB" | tee -a $LOG_FILE
    echo "GPU Memory End: ${gpu_mem_end}MB" | tee -a $LOG_FILE
    echo "" | tee -a $LOG_FILE
    
    # Return key metrics for summary
    echo "$name,$iteration,$wall_clock_time,$tokens_per_second,$eval_count"
}

# GPU baseline check
echo "=== GPU Baseline ===" | tee -a $LOG_FILE
nvidia-smi | tee -a $LOG_FILE
echo "" | tee -a $LOG_FILE

# Run benchmark tests
echo "CSV_HEADER: Test_Name,Iteration,Wall_Clock_Time,Tokens_Per_Second,Token_Count" | tee -a $LOG_FILE

for i in "${!test_prompts[@]}"; do
    prompt="${test_prompts[$i]}"
    name="${prompt_names[$i]}"
    
    # Run 3 iterations of each test
    for iter in {1..3}; do
        result=$(run_test "$prompt" "$name" "$iter")
        echo "CSV_DATA: $result" | tee -a $LOG_FILE
        sleep 2  # Brief pause between tests
    done
done

# Calculate averages
echo "" | tee -a $LOG_FILE
echo "=== Performance Summary ===" | tee -a $LOG_FILE

for name in "${prompt_names[@]}"; do
    avg_time=$(grep "CSV_DATA.*$name" $LOG_FILE | cut -d',' -f3 | awk '{sum+=$1} END {printf "%.3f", sum/NR}')
    avg_tps=$(grep "CSV_DATA.*$name" $LOG_FILE | cut -d',' -f4 | awk '{sum+=$1} END {printf "%.2f", sum/NR}')
    echo "$name Average - Time: ${avg_time}s, Tokens/sec: $avg_tps" | tee -a $LOG_FILE
done

echo "" | tee -a $LOG_FILE
echo "Benchmark completed. Log saved to: $LOG_FILE" | tee -a $LOG_FILE