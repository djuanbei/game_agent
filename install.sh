#!/bin/bash
# install.sh – Install dependencies for the LangGraph agent (not the game)
# This script sets up a Python virtual environment and installs the required packages.
# It is intended to be run on macOS Intel (x86_64) or any Linux system.

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Setting up LangGraph agent environment...${NC}"

# Check for Python 3.8+
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed. Please install Python 3.8 or higher.${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Upgrade pip
echo -e "${YELLOW}Upgrading pip...${NC}"
pip install --upgrade pip

# Install required packages
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install langgraph langchain langchain-openai gitpython pyyaml

# Optional: Install pygame for local testing of generated games
echo -e "${YELLOW}Installing optional pygame for local game testing...${NC}"
pip install pygame 2>/dev/null || echo -e "${YELLOW}pygame installation skipped (optional).${NC}"

# Verify critical packages are installed
echo -e "${YELLOW}Verifying installation...${NC}"
if ! python -c "import git" 2>/dev/null; then
    echo -e "${RED}ERROR: gitpython is not installed. Attempting to install again...${NC}"
    pip install gitpython --force-reinstall
fi

if ! python -c "import langchain" 2>/dev/null; then
    echo -e "${RED}ERROR: langchain is not installed. Attempting to install again...${NC}"
    pip install langchain --force-reinstall
fi

echo -e "${GREEN}All dependencies installed successfully.${NC}"
echo ""
echo -e "${GREEN}To activate the environment, run:${NC}"
echo "  source venv/bin/activate"
echo -e "${GREEN}Then run the agent with:${NC}"
echo "  python agent.py"
echo ""
echo -e "${YELLOW}Note: If you encounter any issues, ensure you are in the correct virtual environment (prompt should show '(venv)').${NC}"