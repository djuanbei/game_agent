"""Configuration constants."""
from pathlib import Path

WORK_DIR = Path.cwd()  # The directory where the game lives
GAME_CODE_FILE = "game.py"
CONFIG_FILE = "configure.json"
README_FILE = "README.md"
INSTALL_FILE = "install.sh"

# LLM settings (DeepSeek via OpenAI-compatible endpoint)
LLM_MODEL = "deepseek-chat"
LLM_BASE_URL = "https://api.deepseek.com/v1"
LLM_API_KEY = "your-api-key-here"  # Override with env var

# Git branch/tag prefix for circles
CIRCLE_BRANCH_PREFIX = "circle_v"
