"""Helper functions for file I/O, Git operations, and installation."""
import os
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Tuple
import git

from .config import (
    WORK_DIR, GAME_CODE_FILE, CONFIG_FILE, README_FILE, INSTALL_FILE,
    CIRCLE_BRANCH_PREFIX
)

# -----------------------------------------------------------------------------
# Definition loading and parsing
# -----------------------------------------------------------------------------

def load_all_definitions() -> Tuple[int, Dict[str, Any], List[Dict[str, Any]]]:
    """Scan WORK_DIR for game_v*.md files, parse them, return (latest_version, latest_def, all_defs)."""
    pattern = "game_v*.md"
    files = list(WORK_DIR.glob(pattern))
    if not files:
        return 0, {}, []
    
    versions = []
    for f in files:
        try:
            num = int(f.stem.split('_v')[1])
            versions.append((num, f))
        except:
            continue
    versions.sort(key=lambda x: x[0])
    
    all_parsed = []
    for num, f in versions:
        content = f.read_text(encoding='utf-8')
        parsed = parse_definition(content)
        parsed['version'] = num
        all_parsed.append(parsed)
    
    latest = all_parsed[-1] if all_parsed else {}
    return latest.get('version', 0), latest, all_parsed

def parse_definition(content: str) -> Dict[str, Any]:
    """Parse markdown definition into {name, role, rules}."""
    lines = content.splitlines()
    name = ""
    role = ""
    rules = []
    current_section = None
    for line in lines:
        if line.startswith("# "):
            name = line[2:].strip()
        elif line.startswith("## Role"):
            current_section = "role"
        elif line.startswith("## Rules"):
            current_section = "rules"
        elif current_section == "role" and line.strip():
            role = line.strip()
            current_section = None
        elif current_section == "rules" and line.strip():
            rules.append(line.strip())
    return {"name": name, "role": role, "rules": rules}

def save_definition(version: int, content: str):
    """Write markdown definition to game_v<version>.md."""
    filename = f"game_v{version}.md"
    (WORK_DIR / filename).write_text(content, encoding='utf-8')

def load_controller_config() -> Dict[str, str]:
    """Load configure.json."""
    config_path = WORK_DIR / CONFIG_FILE
    if config_path.exists():
        return json.loads(config_path.read_text(encoding='utf-8'))
    return {}

def save_controller_config(config: Dict[str, str]):
    """Save controller configuration."""
    (WORK_DIR / CONFIG_FILE).write_text(json.dumps(config, indent=2), encoding='utf-8')

# -----------------------------------------------------------------------------
# Git operations
# -----------------------------------------------------------------------------

def get_git_repo() -> git.Repo:
    """Get or initialize Git repository in WORK_DIR."""
    try:
        repo = git.Repo(WORK_DIR)
    except git.exc.InvalidGitRepositoryError:
        repo = git.Repo.init(WORK_DIR)
    return repo

def checkout_last_circle(repo: git.Repo, version: int):
    """Checkout branch circle_v<version> if it exists."""
    branch_name = f"{CIRCLE_BRANCH_PREFIX}{version}"
    if branch_name in repo.branches:
        repo.git.checkout(branch_name)

def commit_circle(repo: git.Repo, version: int):
    """Commit all relevant files and create branch/tag for finished circle."""
    repo.git.add("game_v*.md")
    repo.git.add(GAME_CODE_FILE)
    repo.git.add(CONFIG_FILE)
    repo.git.add(README_FILE)
    repo.git.add(INSTALL_FILE)
    commit_msg = f"Evolution circle v{version} completed"
    repo.index.commit(commit_msg)
    branch_name = f"{CIRCLE_BRANCH_PREFIX}{version}"
    if branch_name not in repo.branches:
        repo.create_head(branch_name)
    else:
        repo.git.branch("-D", branch_name)
        repo.create_head(branch_name)

# -----------------------------------------------------------------------------
# Installation helpers
# -----------------------------------------------------------------------------

def ensure_install_script():
    """Ensure install.sh exists and contains pygame installation."""
    install_path = WORK_DIR / INSTALL_FILE
    if not install_path.exists():
        content = """#!/bin/bash
# Install dependencies for the game on macOS Intel
set -e

if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Please install Homebrew first: https://brew.sh/"
    exit 1
fi

brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf
pip3 install --user pygame

echo "All dependencies installed. Run 'python3 game.py' to start the game."
"""
        install_path.write_text(content, encoding='utf-8')
        os.chmod(install_path, 0o755)
        return True
    return False

def auto_install_pygame() -> bool:
    """Try to install pygame automatically using install.sh or pip."""
    print("[Auto-fix] Attempting to install pygame automatically...")
    install_path = WORK_DIR / INSTALL_FILE
    if install_path.exists():
        try:
            subprocess.run([str(install_path)], cwd=WORK_DIR, check=True)
            print("[Auto-fix] install.sh completed.")
            return True
        except Exception as e:
            print(f"[Auto-fix] install.sh failed: {e}")
    # Fallback to pip
    try:
        subprocess.run(["pip3", "install", "--user", "pygame"], check=True)
        print("[Auto-fix] pygame installed via pip.")
        return True
    except Exception as e:
        print(f"[Auto-fix] pip install failed: {e}")
        return False
