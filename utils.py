"""Utility functions for file I/O, Git operations, installation, and code fixing."""

import os
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Tuple

import git
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from .config import (
    WORK_DIR,
    GAME_CODE_FILE,
    CONFIG_FILE,
    README_FILE,
    INSTALL_FILE,
    CIRCLE_BRANCH_PREFIX,
    LLM_MODEL,
    LLM_BASE_URL,
    LLM_API_KEY,
)


# -----------------------------------------------------------------------------
# Definition loading and parsing
# -----------------------------------------------------------------------------


def load_all_definitions() -> Tuple[int, Dict[str, Any], List[Dict[str, Any]]]:
    """
    Scan WORK_DIR for game_v*.md files, parse them, and return:
    - highest version number
    - parsed dict of the latest version
    - list of all parsed definitions (ordered by version)
    """
    pattern = "game_v*.md"
    files = list(WORK_DIR.glob(pattern))
    if not files:
        return 0, {}, []

    versions = []
    for f in files:
        try:
            num = int(f.stem.split("_v")[1])
            versions.append((num, f))
        except:
            continue
    versions.sort(key=lambda x: x[0])

    all_parsed = []
    for num, f in versions:
        content = f.read_text(encoding="utf-8")
        parsed = parse_definition(content)
        parsed["version"] = num
        all_parsed.append(parsed)

    latest = all_parsed[-1] if all_parsed else {}
    return latest.get("version", 0), latest, all_parsed


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
    (WORK_DIR / filename).write_text(content, encoding="utf-8")


def load_controller_config() -> Dict[str, str]:
    """Load configure.json."""
    config_path = WORK_DIR / CONFIG_FILE
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


def save_controller_config(config: Dict[str, str]):
    """Save controller configuration."""
    (WORK_DIR / CONFIG_FILE).write_text(json.dumps(config, indent=2), encoding="utf-8")


def ensure_controller_config():
    """Create default configure.json if missing."""
    config_path = WORK_DIR / CONFIG_FILE
    if not config_path.exists():
        default_config = {
            "select": "A",
            "cancel": "B",
            "shuffle": "Start",
            "rotate_left": "L1",
            "rotate_right": "R1",
        }
        save_controller_config(default_config)
        print(f"Created default {CONFIG_FILE}")
        return True
    return False


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


def is_file_tracked(repo: git.Repo, filepath: str) -> bool:
    """Check if a file is tracked by git (committed)."""
    try:
        # Check if file is in git index
        result = repo.git.ls_files(filepath)
        return bool(result.strip())
    except git.exc.GitCommandError:
        # File not tracked
        return False


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
# Installation and code fixing helpers
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
        install_path.write_text(content, encoding="utf-8")
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


def auto_install_missing_module(module_name: str) -> bool:
    """Install any missing Python module using pip."""
    print(f"[Auto-fix] Installing missing module '{module_name}'...")
    try:
        subprocess.run(
            ["pip3", "install", module_name], check=True, capture_output=True
        )
        print(f"[Auto-fix] Successfully installed {module_name}.")
        return True
    except:
        try:
            subprocess.run(
                ["pip3", "install", "--user", module_name],
                check=True,
                capture_output=True,
            )
            print(f"[Auto-fix] Successfully installed {module_name} (user install).")
            return True
        except Exception as e:
            print(f"[Auto-fix] Failed to install {module_name}: {e}")
            return False


def auto_fix_code(error_msg: str, code: str = None) -> bool:
    """
    Attempt to fix the game code by sending the error back to the LLM.
    Returns True if a fix was applied and the code now passes a quick check.
    """
    if code is None:
        code_path = WORK_DIR / GAME_CODE_FILE
        if not code_path.exists():
            return False
        code = code_path.read_text(encoding="utf-8")
    print(f"[Auto-fix] Attempting to fix code (error: {error_msg[:200]}...)")

    # Build prompt using simple string concatenation (no triple quotes)
    prompt = (
        "The following Python game code has an error. Please fix the error and return the **entire corrected code**.\n\n"
        "Error message:\n"
        f"{error_msg}\n\n"
        "Broken code:\n"
        "```python\n"
        f"{code}\n"
        "```\n\n"
        "Requirements:\n"
        "- Keep all functionality and game rules exactly the same.\n"
        "- Only fix the specific error shown above. Ensure the code is syntactically correct and runs without this error.\n"
        "- Output only the corrected Python code, no extra text.\n"
    )

    llm = ChatOpenAI(
        model=LLM_MODEL,
        openai_api_base=LLM_BASE_URL,
        openai_api_key=LLM_API_KEY,
        temperature=0.3,
        streaming=True,
    )
    print("[Auto-fix] Requesting corrected code from LLM...")
    fixed_code = ""
    for chunk in llm.stream([HumanMessage(content=prompt)]):
        if chunk.content:
            print(chunk.content, end="", flush=True)
            fixed_code += chunk.content
    print("\n[Auto-fix] Received response.")

    if fixed_code.startswith("```python"):
        fixed_code = fixed_code[9:]
    if fixed_code.endswith("```"):
        fixed_code = fixed_code[:-3]
    fixed_code = fixed_code.strip()

    (WORK_DIR / GAME_CODE_FILE).write_text(fixed_code, encoding="utf-8")

    try:
        compile(fixed_code, "<string>", "exec")
        print("[Auto-fix] Compilation check passed.")
        return True
    except Exception as e:
        print(f"[Auto-fix] Error still present: {e}")
        return False
