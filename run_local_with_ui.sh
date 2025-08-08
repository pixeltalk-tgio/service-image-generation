#!/bin/bash

# =====================================================
# Run PixelTalk Service + Streamlit UI Locally
# =====================================================

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}   Starting PixelTalk Complete Stack (Local)    ${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo -e "${YELLOW}Please create a .env file with your credentials.${NC}"
    exit 1
fi

# Check if app.py exists (Streamlit)
if [ ! -f "app.py" ]; then
    echo -e "${RED}Warning: app.py not found!${NC}"
    echo -e "${YELLOW}Streamlit UI has been removed or moved to another repo.${NC}"
    echo -e "${YELLOW}Running backend service only...${NC}"
    echo ""
    ./run_local.sh
    exit 0
fi

# Create necessary directories
mkdir -p logs
mkdir -p generated_images
mkdir -p generated_videos

# Kill any existing processes
echo -e "${YELLOW}Cleaning up existing processes...${NC}"
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:8501 | xargs kill -9 2>/dev/null || true
sleep 1

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down services...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    echo -e "${GREEN}Services stopped.${NC}"
    exit 0
}

# Set up trap for cleanup
trap cleanup INT TERM

# Start backend service
echo -e "${BLUE}Starting backend service...${NC}"
python main.py > logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for backend to start
echo -e "${YELLOW}Waiting for backend to start...${NC}"
for i in {1..10}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend is ready!${NC}"
        break
    fi
    sleep 1
done

# Start Streamlit UI
echo -e "${BLUE}Starting Streamlit UI...${NC}"
streamlit run app.py --server.address localhost > logs/streamlit.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

# Display access information
echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}         PixelTalk Stack Running!               ${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""
echo -e "${BLUE}🌐 Streamlit UI:${NC} http://localhost:8501"
echo -e "${BLUE}🔧 Backend API:${NC} http://localhost:8000"
echo -e "${BLUE}📚 API Docs:${NC}    http://localhost:8000/docs"
echo ""
echo -e "${YELLOW}Logs:${NC}"
echo "  - Backend: tail -f logs/backend.log"
echo "  - Frontend: tail -f logs/streamlit.log"
echo ""
echo -e "${RED}Press Ctrl+C to stop all services${NC}"
echo ""

# Keep script running and show logs
tail -f logs/backend.log