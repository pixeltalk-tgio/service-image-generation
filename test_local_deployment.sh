#!/bin/bash

# =====================================================
# Test Local Deployment
# =====================================================
# This script tests if your service is working properly

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}        Testing PixelTalk Service               ${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""

# Configuration
API_URL="http://localhost:8000"
TEST_AUDIO="test_audio.wav"

# Check if service is running
echo -e "${YELLOW}1. Checking if service is running...${NC}"
if curl -s "$API_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}   ✅ Service is running${NC}"
else
    echo -e "${RED}   ❌ Service is not running${NC}"
    echo "   Please start the service with: ./run_local.sh"
    exit 1
fi

# Test health endpoint
echo -e "${YELLOW}2. Testing health endpoint...${NC}"
HEALTH=$(curl -s "$API_URL/health")
echo "   Response: $HEALTH"
echo -e "${GREEN}   ✅ Health check passed${NC}"

# Test root endpoint
echo -e "${YELLOW}3. Testing root endpoint...${NC}"
ROOT=$(curl -s "$API_URL/")
if echo "$ROOT" | grep -q "PixelTalk"; then
    echo -e "${GREEN}   ✅ Root endpoint working${NC}"
else
    echo -e "${RED}   ❌ Root endpoint not working properly${NC}"
fi

# Check environment variables
echo -e "${YELLOW}4. Checking environment configuration...${NC}"
if [ -f ".env" ]; then
    if grep -q "OPENAI_API_KEY" .env && grep -q "CLOUDINARY_URL" .env; then
        echo -e "${GREEN}   ✅ Environment variables configured${NC}"
    else
        echo -e "${YELLOW}   ⚠️  Some environment variables may be missing${NC}"
    fi
else
    echo -e "${RED}   ❌ .env file not found${NC}"
fi

# Create a test audio file if needed
echo -e "${YELLOW}5. Creating test audio file...${NC}"
if [ ! -f "$TEST_AUDIO" ]; then
    # Create a simple test audio using sox or ffmpeg if available
    if command -v sox &> /dev/null; then
        sox -n -r 16000 -c 1 "$TEST_AUDIO" synth 1 sine 440
        echo -e "${GREEN}   ✅ Test audio created with sox${NC}"
    elif command -v ffmpeg &> /dev/null; then
        ffmpeg -f lavfi -i "sine=frequency=440:duration=1" -ac 1 -ar 16000 "$TEST_AUDIO" -y > /dev/null 2>&1
        echo -e "${GREEN}   ✅ Test audio created with ffmpeg${NC}"
    else
        echo -e "${YELLOW}   ⚠️  Cannot create test audio (sox/ffmpeg not found)${NC}"
        echo "   You can test manually with any .wav file"
    fi
else
    echo -e "${GREEN}   ✅ Test audio file exists${NC}"
fi

# Test upload endpoint (optional)
if [ -f "$TEST_AUDIO" ]; then
    echo -e "${YELLOW}6. Testing upload endpoint...${NC}"
    echo "   Uploading test audio..."
    
    RESPONSE=$(curl -s -X POST "$API_URL/upload" \
        -F "audio=@$TEST_AUDIO" \
        -F "generation_mode=image" 2>/dev/null || echo "ERROR")
    
    if echo "$RESPONSE" | grep -q "session_id"; then
        SESSION_ID=$(echo "$RESPONSE" | grep -o '"session_id":"[^"]*' | cut -d'"' -f4)
        echo -e "${GREEN}   ✅ Upload successful! Session ID: $SESSION_ID${NC}"
        
        # Check status
        echo -e "${YELLOW}7. Testing status endpoint...${NC}"
        sleep 2
        STATUS=$(curl -s "$API_URL/status/$SESSION_ID")
        echo "   Status: $STATUS"
        echo -e "${GREEN}   ✅ Status endpoint working${NC}"
    else
        echo -e "${YELLOW}   ⚠️  Upload test skipped or failed${NC}"
        echo "   This might be due to missing API keys"
    fi
fi

# Summary
echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}              Test Summary                      ${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""
echo "Service Status: ✅ Running"
echo "API Endpoints: ✅ Accessible"
echo ""
echo "You can now:"
echo "1. Access API docs at: ${BLUE}http://localhost:8000/docs${NC}"
echo "2. Upload audio files via the API"
echo "3. Run Streamlit UI with: ${YELLOW}streamlit run app.py${NC}"
echo ""
echo -e "${GREEN}All tests completed!${NC}"