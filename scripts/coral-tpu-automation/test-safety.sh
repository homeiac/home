#!/bin/bash
# Test the critical safety feature

echo "=== Testing Coral TPU Safety Features ==="
echo ""

# Test 1: Current state (should be Google mode)
echo "Test 1: Current device state"
current_device=$(lsusb | grep -E '18d1:9302|1a6e:089a')
echo "Current device: $current_device"

if echo "$current_device" | grep -q "18d1:9302"; then
    echo "✓ Device in Google mode - initialization should be BLOCKED"
    expected_behavior="block"
elif echo "$current_device" | grep -q "1a6e:089a"; then
    echo "✓ Device in Unichip mode - initialization should be ALLOWED" 
    expected_behavior="allow"
else
    echo "✗ No Coral device detected"
    expected_behavior="error"
fi

echo ""
echo "Test 2: Safety check simulation"

# Source the functions
cd /tmp
source mock-coral-init.sh 2>/dev/null

# Override DRY_RUN to false for this test but keep exec_cmd safe
export DRY_RUN=false
exec_cmd() {
    case "$1" in
        *"lsusb"*"18d1:9302"*)
            # Return the actual current device state
            lsusb | grep '18d1:9302'
            ;;
        *"lsusb"*"1a6e:089a"*)
            # Return the actual current device state  
            lsusb | grep '1a6e:089a'
            ;;
        *)
            echo "[MOCK - would execute: $1]"
            ;;
    esac
}

# Test the safety function
echo "Running initialize_coral function..."
if initialize_coral; then
    echo "✓ Initialization would proceed"
    actual_behavior="allow"
else
    echo "✓ Initialization blocked by safety check"
    actual_behavior="block"
fi

echo ""
echo "Test 3: Validation"
if [ "$expected_behavior" = "$actual_behavior" ]; then
    echo "🟢 PASS: Safety feature working correctly"
    echo "   Expected: $expected_behavior"
    echo "   Actual:   $actual_behavior"
else
    echo "🔴 FAIL: Safety feature not working"
    echo "   Expected: $expected_behavior" 
    echo "   Actual:   $actual_behavior"
fi

echo ""
echo "=== Safety Test Complete ==="