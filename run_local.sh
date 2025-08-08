#!/bin/bash

# =====================================================
# Run PixelTalk Service Locally for Testing
# =====================================================

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}    Starting PixelTalk Service (Local Test)     ${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo -e "${YELLOW}Please create a .env file with your credentials.${NC}"
    echo "You can copy .env.example as a template:"
    echo "  cp .env.example .env"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv .venv
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source .venv/bin/activate

# Install/update dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
if command -v uv &> /dev/null; then
    uv sync
else
    pip install -r requirements.txt
fi

# Create necessary directories
echo -e "${YELLOW}Creating directories...${NC}"
mkdir -p logs
mkdir -p generated_images
mkdir -p generated_videos

# Kill any existing process on port 8000
echo -e "${YELLOW}Checking for existing processes on port 8000...${NC}"
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# Start the backend service
echo -e "${GREEN}Starting backend service...${NC}"
echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}Service starting at: http://localhost:8000      ${NC}"
echo -e "${GREEN}API Docs: http://localhost:8000/docs            ${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the service${NC}"
echo ""

# Run the service
python main.py