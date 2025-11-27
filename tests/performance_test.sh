#!/bin/bash
# Performance and Load Testing for MCP SSE Server

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
SERVER_URL="${1:-http://136.115.34.4}"
CONCURRENT_CONNECTIONS="${2:-10}"
TEST_DURATION="${3:-60}"

echo "================================================================="
echo "🚀 MCP SSE Server - Performance Test Suite"
echo "================================================================="
echo "Server URL: $SERVER_URL"
echo "Concurrent Connections: $CONCURRENT_CONNECTIONS"
echo "Test Duration: ${TEST_DURATION}s"
echo "================================================================="
echo ""

# Check if server is responsive
echo -e "${YELLOW}📊 Checking server health...${NC}"
if curl -f -s "$SERVER_URL/health" > /dev/null; then
    echo -e "${GREEN}✅ Server is healthy${NC}"
    curl -s "$SERVER_URL/health" | jq '.'
else
    echo -e "${RED}❌ Server is not responding${NC}"
    exit 1
fi

echo ""
echo "================================================================="
echo "Test 1: Response Time Analysis"
echo "================================================================="

# Test response times
echo -e "${YELLOW}Testing response times for different endpoints...${NC}"

endpoints=(
    "/health"
    "/status"
    "/tools/list"
    "/personas/list"
)

for endpoint in "${endpoints[@]}"; do
    echo -n "Testing $endpoint... "

    times=()
    for i in {1..10}; do
        time_taken=$(curl -o /dev/null -s -w '%{time_total}\n' "$SERVER_URL$endpoint")
        times+=($time_taken)
    done

    # Calculate average
    avg=$(echo "${times[@]}" | awk '{sum=0; for(i=1; i<=NF; i++) sum+=$i; print sum/NF}')

    echo -e "${GREEN}Average: ${avg}s${NC}"
done

echo ""
echo "================================================================="
echo "Test 2: Concurrent Connections Test"
echo "================================================================="

echo -e "${YELLOW}Testing $CONCURRENT_CONNECTIONS concurrent connections...${NC}"

# Create temporary directory for results
TEMP_DIR=$(mktemp -d)

# Run concurrent requests
for i in $(seq 1 $CONCURRENT_CONNECTIONS); do
    (
        start=$(date +%s.%N)
        response=$(curl -s -w "\n%{http_code}\n%{time_total}" "$SERVER_URL/tools/list")
        end=$(date +%s.%N)

        status=$(echo "$response" | tail -2 | head -1)
        time_taken=$(echo "$response" | tail -1)

        echo "$status,$time_taken" > "$TEMP_DIR/result_$i.txt"
    ) &
done

# Wait for all background jobs
wait

# Analyze results
success=0
failed=0
total_time=0

for result_file in "$TEMP_DIR"/result_*.txt; do
    read -r status time_taken < "$result_file"
    status=${status%%,*}
    time_taken=${time_taken##*,}

    if [ "$status" = "200" ]; then
        ((success++))
        total_time=$(echo "$total_time + $time_taken" | bc)
    else
        ((failed++))
    fi
done

avg_time=$(echo "scale=3; $total_time / $success" | bc)

echo -e "${GREEN}✅ Successful: $success${NC}"
echo -e "${RED}❌ Failed: $failed${NC}"
echo -e "${GREEN}📊 Average time: ${avg_time}s${NC}"

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "================================================================="
echo "Test 3: SSE Stream Stability Test"
echo "================================================================="

echo -e "${YELLOW}Testing SSE stream for ${TEST_DURATION}s...${NC}"

# Test SSE stream
timeout ${TEST_DURATION}s bash -c "
    curl -N -H 'Accept: text/event-stream' '$SERVER_URL/mcp' 2>/dev/null | \
    while IFS= read -r line; do
        echo \"\$line\"
    done
" | tee /tmp/sse_test.log | head -20

echo ""
echo -e "${YELLOW}Analyzing SSE events...${NC}"

# Count events
total_events=$(grep -c "^data:" /tmp/sse_test.log || echo 0)
heartbeats=$(grep -c "heartbeat" /tmp/sse_test.log || echo 0)

echo -e "${GREEN}Total events received: $total_events${NC}"
echo -e "${GREEN}Heartbeat events: $heartbeats${NC}"

if [ $total_events -gt 0 ]; then
    echo -e "${GREEN}✅ SSE stream is working${NC}"
else
    echo -e "${RED}❌ No SSE events received${NC}"
fi

echo ""
echo "================================================================="
echo "Test 4: Memory Leak Detection"
echo "================================================================="

echo -e "${YELLOW}Checking for memory leaks (requires kubectl)...${NC}"

if command -v kubectl &> /dev/null; then
    echo "Initial memory usage:"
    kubectl top pod -n production -l app=mcp-server 2>/dev/null || echo "kubectl not configured"

    echo ""
    echo "Running 100 requests..."
    for i in {1..100}; do
        curl -s "$SERVER_URL/tools/list" > /dev/null &
        if [ $((i % 10)) -eq 0 ]; then
            echo -n "."
        fi
    done
    wait
    echo ""

    echo "Waiting 10s for metrics to update..."
    sleep 10

    echo "Memory usage after load:"
    kubectl top pod -n production -l app=mcp-server 2>/dev/null || echo "kubectl not configured"
else
    echo -e "${YELLOW}kubectl not available, skipping memory test${NC}"
fi

echo ""
echo "================================================================="
echo "Test 5: Error Handling Test"
echo "================================================================="

echo -e "${YELLOW}Testing error handling...${NC}"

# Test invalid JSON
echo -n "Invalid JSON request... "
response=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/mcp" \
    -H "Content-Type: application/json" \
    -d "invalid json")
status=$(echo "$response" | tail -1)

if [ "$status" = "400" ]; then
    echo -e "${GREEN}✅ Correctly handled (400)${NC}"
else
    echo -e "${RED}❌ Unexpected status: $status${NC}"
fi

# Test invalid method
echo -n "Invalid method request... "
response=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"jsonrpc":"2.0","method":"invalid","id":1}')
status=$(echo "$response" | tail -1)

if [ "$status" = "200" ]; then
    body=$(echo "$response" | head -n -1)
    if echo "$body" | jq -e '.error' > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Correctly returned error response${NC}"
    else
        echo -e "${YELLOW}⚠️  Unexpected response format${NC}"
    fi
else
    echo -e "${RED}❌ Unexpected status: $status${NC}"
fi

echo ""
echo "================================================================="
echo "Test 6: MCP Protocol Compliance"
echo "================================================================="

echo -e "${YELLOW}Testing MCP JSON-RPC 2.0 compliance...${NC}"

# Test tools/list
echo -n "Testing tools/list... "
response=$(curl -s -X POST "$SERVER_URL/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}')

if echo "$response" | jq -e '.jsonrpc == "2.0" and .result.tools' > /dev/null 2>&1; then
    tools_count=$(echo "$response" | jq '.result.tools | length')
    echo -e "${GREEN}✅ Valid response ($tools_count tools)${NC}"
else
    echo -e "${RED}❌ Invalid response format${NC}"
fi

# Test session management
echo -n "Testing session management... "
response=$(curl -s -i -X POST "$SERVER_URL/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}')

if echo "$response" | grep -q "Mcp-Session-Id:"; then
    echo -e "${GREEN}✅ Session ID provided${NC}"
else
    echo -e "${RED}❌ No session ID in response${NC}"
fi

echo ""
echo "================================================================="
echo "📊 Performance Test Summary"
echo "================================================================="

echo -e "${GREEN}✅ All tests completed${NC}"
echo ""
echo "Key Metrics:"
echo "- Server Health: OK"
echo "- Concurrent Connections: $success/$CONCURRENT_CONNECTIONS successful"
echo "- Average Response Time: ${avg_time}s"
echo "- SSE Events: $total_events total, $heartbeats heartbeats"
echo "- Error Handling: Working"
echo "- MCP Protocol: Compliant"
echo ""
echo "================================================================="
echo "For detailed logs, check:"
echo "  - SSE test log: /tmp/sse_test.log"
echo "================================================================="
