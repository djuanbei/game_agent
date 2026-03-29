#!/usr/bin/env python3
"""
LangGraph Agent for Evolving Game Definitions (8BitDo Pro 3) with Git Integration
Enhanced version: auto-install missing modules, LLM auto-fix, play command, delayed saving.
"""

import os
import sys

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

# Configuration constants (duplicated for standalone script)
import os
from pathlib import Path

WORK_DIR = Path.cwd()  # The directory where the game lives
GAME_CODE_FILE = "game.py"
CONFIG_FILE = "configure.json"
README_FILE = "README.md"
INSTALL_FILE = "install.sh"

# LLM settings (DeepSeek via OpenAI-compatible endpoint)
LLM_MODEL = "deepseek-chat"
LLM_BASE_URL = "https://api.deepseek.com/v1"
BASE_LLM_API_KEY = "your-api-key-here"  # Override with env var

# Git branch/tag prefix for circles
CIRCLE_BRANCH_PREFIX = "circle_v"

# Override API key from environment
LLM_API_KEY = os.environ.get("DEEPSEEK_API_KEY", BASE_LLM_API_KEY)

# -----------------------------------------------------------------------------
# State definition
# -----------------------------------------------------------------------------


# State definition
from typing import Dict, List, Any, Optional, TypedDict
import git


class AgentState(TypedDict):
    latest_version: int
    latest_definition: Dict[str, Any]
    all_definitions: List[Dict[str, Any]]
    user_suggestions: str
    accumulated_suggestions: str  # <-- NEW: accumulate suggestions within a circle
    next_version_definition: str
    build_retry_allowed: bool
    build_success: bool
    game_running: bool
    manual_reload_requested: bool
    play_requested: bool
    git_repo: Optional[git.Repo]


# -----------------------------------------------------------------------------
# Helper functions (file I/O, Git, installation, code fixing)
# -----------------------------------------------------------------------------

import json
import subprocess
import re
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END


def load_all_definitions():
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
    filename = f"game_v{version}.md"
    (WORK_DIR / filename).write_text(content, encoding="utf-8")


def load_controller_config() -> Dict[str, str]:
    config_path = WORK_DIR / CONFIG_FILE
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


def save_controller_config(config: Dict[str, str]):
    (WORK_DIR / CONFIG_FILE).write_text(json.dumps(config, indent=2), encoding="utf-8")


def ensure_controller_config():
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


def get_git_repo() -> git.Repo:
    try:
        repo = git.Repo(WORK_DIR)
    except git.exc.InvalidGitRepositoryError:
        repo = git.Repo.init(WORK_DIR)
    return repo


def is_file_tracked(repo: git.Repo, filepath: str) -> bool:
    try:
        result = repo.git.ls_files(filepath)
        return bool(result.strip())
    except git.exc.GitCommandError:
        return False


def checkout_last_circle(repo: git.Repo, version: int):
    branch_name = f"{CIRCLE_BRANCH_PREFIX}{version}"
    if branch_name in repo.branches:
        repo.git.checkout(branch_name)


def commit_circle(repo: git.Repo, version: int):
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


def ensure_install_script():
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
    print("[Auto-fix] Attempting to install pygame automatically...")
    install_path = WORK_DIR / INSTALL_FILE
    if install_path.exists():
        try:
            subprocess.run([str(install_path)], cwd=WORK_DIR, check=True)
            print("[Auto-fix] install.sh completed.")
            return True
        except Exception as e:
            print(f"[Auto-fix] install.sh failed: {e}")
    try:
        subprocess.run(["pip3", "install", "--user", "pygame"], check=True)
        print("[Auto-fix] pygame installed via pip.")
        return True
    except Exception as e:
        print(f"[Auto-fix] pip install failed: {e}")
        return False


def auto_install_missing_module(module_name: str) -> bool:
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
    if code is None:
        code_path = WORK_DIR / GAME_CODE_FILE
        if not code_path.exists():
            return False
        code = code_path.read_text(encoding="utf-8")
    print(f"[Auto-fix] Attempting to fix code (error: {error_msg[:200]}...)")

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


# -----------------------------------------------------------------------------
# LangGraph nodes
# -----------------------------------------------------------------------------


def load_versions(state: AgentState) -> AgentState:
    version, latest, all_defs = load_all_definitions()
    state["latest_version"] = version
    state["latest_definition"] = latest
    state["all_definitions"] = all_defs
    state["manual_reload_requested"] = False
    return state


def initialize_game(state: AgentState) -> AgentState:
    """Check if required files exist, exit with error if missing."""
    if state["latest_version"] != 0 or state["latest_definition"]:
        # Already have definitions, skip
        return state

    # Check for required files
    game_files = list(WORK_DIR.glob("game_v*.md"))
    config_exists = (WORK_DIR / CONFIG_FILE).exists()

    if not game_files or not config_exists:
        print("\n" + "=" * 60)
        print("ERROR: Required files missing.")
        if not game_files:
            print("- No game_v*.md files found.")
        if not config_exists:
            print(f"- {CONFIG_FILE} not found.")
        print("\nPlease create:")
        print("1. game_v0.md - initial game definition in markdown format")
        print(f"2. {CONFIG_FILE} - controller configuration")
        print("\nExample game_v0.md:")
        print("# Game Name")
        print("## Role")
        print("## Rules")
        print("- Rule 1")
        print("- Rule 2")
        print(f"\nExample {CONFIG_FILE}:")
        print(
            '{"select": "A", "cancel": "B", "shuffle": "Start", "rotate_left": "L1", "rotate_right": "R1"}'
        )
        print("=" * 60)
        sys.exit(1)

    # Ensure controller config exists (should already exist)
    ensure_controller_config()

    # Load the existing latest version
    version, latest, all_defs = load_all_definitions()
    state["latest_version"] = version
    state["latest_definition"] = latest
    state["all_definitions"] = all_defs

    print(f"\nInitialized with game definition v{version}: {latest.get('name', 'N/A')}")
    return state


def git_checkout_last_circle(state: AgentState) -> AgentState:
    repo = get_git_repo()
    state["git_repo"] = repo
    if state["latest_version"] > 0:
        checkout_last_circle(repo, state["latest_version"])
    return state


def get_user_input(state: AgentState) -> AgentState:
    print("\n" + "=" * 60)
    print(f"Current game definition (v{state['latest_version']}):")
    print(f"Name: {state['latest_definition'].get('name', 'N/A')}")
    print(f"Role: {state['latest_definition'].get('role', 'N/A')}")
    print("Rules:")
    for rule in state["latest_definition"].get("rules", []):
        print(f"  - {rule}")

    # Show accumulated suggestions from current evolution circle
    if state.get("accumulated_suggestions"):
        print(
            f"\nAccumulated suggestions in this circle: {state['accumulated_suggestions']}"
        )

    print("=" * 60)
    user = input(
        "\nEnter suggestions for next version (or 'skip', 'reload', 'play', 'quit'): "
    ).strip()
    if user.lower() == "quit":
        sys.exit(0)
    elif user.lower() == "reload":
        state["manual_reload_requested"] = True
        state["play_requested"] = False
    elif user.lower() == "play":
        state["play_requested"] = True
        state["manual_reload_requested"] = False
        state["user_suggestions"] = ""
    else:
        # Accumulate suggestions within the same evolution circle
        if state.get("accumulated_suggestions"):
            if user:  # Only add if user provided new suggestion
                state["accumulated_suggestions"] += f"; {user}"
        else:
            state["accumulated_suggestions"] = user

        # Current suggestion is the latest one
        state["user_suggestions"] = user
        state["manual_reload_requested"] = False
        state["play_requested"] = False
    return state


def generate_next_version(state: AgentState) -> AgentState:
    if state["manual_reload_requested"]:
        return state
    print("\n[Progress] Generating next version definition using LLM...")
    previous_defs_text = "\n\n".join(
        f"# Version {d['version']}\n"
        f"Name: {d.get('name')}\n"
        f"Role: {d.get('role')}\n"
        f"Rules: {', '.join(d.get('rules', []))}"
        for d in state["all_definitions"]
    )
    config = load_controller_config()

    # Use accumulated suggestions if available, otherwise use current suggestion
    suggestions_to_use = state.get("accumulated_suggestions", "")
    if not suggestions_to_use and state.get("user_suggestions"):
        suggestions_to_use = state["user_suggestions"]

    prompt = f"""You are evolving a game definition. Here is the history:

{previous_defs_text}

Current controller configuration (logical actions to physical buttons):
{json.dumps(config, indent=2)}

User suggestions (accumulated in this evolution circle): {suggestions_to_use if suggestions_to_use else "None"}

Generate the next version (v{state["latest_version"] + 1}) in markdown format with sections:
# Game Name
## Role
## Rules (list each rule as a bullet point)

Important: Consider ALL accumulated suggestions from this evolution circle, not just the latest one.
Only output the markdown, no extra commentary.
"""
    llm = ChatOpenAI(
        model=LLM_MODEL,
        openai_api_base=LLM_BASE_URL,
        openai_api_key=LLM_API_KEY,
        temperature=0.7,
        streaming=True,
    )
    print("[Progress] Receiving response from LLM:\n")
    response_content = ""
    for chunk in llm.stream([HumanMessage(content=prompt)]):
        if chunk.content:
            print(chunk.content, end="", flush=True)
            response_content += chunk.content
    print("\n\n[Progress] Generation complete.")
    state["next_version_definition"] = response_content
    return state


def save_approved_version(state: AgentState) -> AgentState:
    """Save the approved next version definition to disk, update version, and commit to Git."""
    current_version = state["latest_version"]
    repo = state["git_repo"]
    current_file = f"game_v{current_version}.md"

    # Check if current version file is already tracked in git
    tracked = is_file_tracked(repo, current_file)

    if tracked:
        # File already committed, create new version
        new_version = current_version + 1
        save_definition(new_version, state["next_version_definition"])
        state["latest_version"] = new_version
        parsed = parse_definition(state["next_version_definition"])
        parsed["version"] = new_version
        state["latest_definition"] = parsed
        state["all_definitions"].append(parsed)
        print(
            f"Created new version v{new_version} (previous v{current_version} was committed)."
        )
    else:
        # File not committed yet, update existing version
        new_version = current_version
        save_definition(current_version, state["next_version_definition"])
        parsed = parse_definition(state["next_version_definition"])
        parsed["version"] = current_version
        state["latest_definition"] = parsed
        # Replace the last definition in all_definitions
        if state["all_definitions"]:
            state["all_definitions"][-1] = parsed
        else:
            state["all_definitions"].append(parsed)
        print(f"Updated existing version v{current_version} (not yet committed).")

    # Reset accumulated suggestions for next evolution circle
    state["accumulated_suggestions"] = ""

    # Commit all changes to Git
    commit_circle(repo, new_version)
    print(f"Committed circle v{new_version} to Git.")
    return state


def generate_game_code(state: AgentState) -> AgentState:
    print("\n[Progress] Generating game code using LLM...")
    latest = state["latest_definition"]
    config = load_controller_config()
    prompt = f"""You are a game developer. Based on the following game definition and controller configuration, generate a complete Python game using Pygame that can be played with an 8BitDo Pro 3 controller.

Game definition:
Name: {latest.get("name")}
Role: {latest.get("role")}
Rules: {", ".join(latest.get("rules", []))}

Controller configuration (logical action -> physical button):
{json.dumps(config, indent=2)}

Requirements:
- The game must read the controller configuration from configure.json at runtime.
- It must map physical buttons to logical actions using the config.
- It must exit when the user presses the Escape key three times within a short time (e.g., 0.5s). Implement a counter to detect three consecutive presses.
- The game should be self-contained in one file (game.py) and run on macOS Intel.
- Use Pygame. Include error handling and proper cleanup.
- Add a brief comment at the top explaining how to run it.

Output only the Python code, no extra text.
"""
    llm = ChatOpenAI(
        model=LLM_MODEL,
        openai_api_base=LLM_BASE_URL,
        openai_api_key=LLM_API_KEY,
        temperature=0.5,
        streaming=True,
    )
    print("[Progress] Receiving game code from LLM:\n")
    code = ""
    for chunk in llm.stream([HumanMessage(content=prompt)]):
        if chunk.content:
            print(chunk.content, end="", flush=True)
            code += chunk.content
    print("\n\n[Progress] Game code generation complete.")
    if code.startswith("```python"):
        code = code[9:]
    if code.endswith("```"):
        code = code[:-3]
    (WORK_DIR / GAME_CODE_FILE).write_text(code.strip(), encoding="utf-8")
    return state


def update_documentation(state: AgentState) -> AgentState:
    latest = state["latest_definition"]
    config = load_controller_config()
    readme_content = f"""# {latest.get("name")}

## Description
{latest.get("role")}

## How to Play
{", ".join(latest.get("rules", []))}

### Controls
The game uses logical actions mapped to your 8BitDo Pro 3 controller buttons:
{json.dumps(config, indent=2)}

Press **Escape three times** to exit the game.

## Installation
Run `./install.sh` to install dependencies, then run `python3 game.py`.

## Requirements
- macOS Intel (x86_64)
- Python 3.8+
- Pygame
- 8BitDo Pro 3 controller connected

## License
This game is open source under the MIT License.
"""
    (WORK_DIR / README_FILE).write_text(readme_content, encoding="utf-8")
    ensure_install_script()
    return state


def build_and_run(state: AgentState) -> AgentState:
    if not (WORK_DIR / GAME_CODE_FILE).exists():
        state["build_success"] = False
        return state

    def try_run(timeout_sec=5):
        try:
            result = subprocess.run(
                ["python3", GAME_CODE_FILE],
                cwd=WORK_DIR,
                timeout=timeout_sec,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise Exception(result.stderr)
            return True, None
        except subprocess.TimeoutExpired:
            print("Game started successfully (no immediate errors).")
            return True, None
        except Exception as e:
            return False, str(e)

    success, error = try_run()
    if success:
        state["build_success"] = True
        return state

    print(f"Build error: {error}")

    # Auto-install missing modules
    if "ModuleNotFoundError: No module named" in error:
        match = re.search(r"ModuleNotFoundError: No module named '(\w+)'", error)
        if match:
            missing_module = match.group(1)
            print(f"[Auto-fix] Missing module '{missing_module}'. Installing...")
            if missing_module == "pygame":
                installed = auto_install_pygame()
            else:
                installed = auto_install_missing_module(missing_module)
            if installed:
                print("[Auto-fix] Retrying build after installation...")
                success2, error2 = try_run()
                if success2:
                    state["build_success"] = True
                    print("Build successful after module installation.")
                    return state
                else:
                    error = error2
                    print(f"Build still failing: {error[:200]}")
            else:
                print("[Auto-fix] Could not install missing module.")
        else:
            print("[Auto-fix] Could not extract module name.")

    # Generic LLM auto-fix (up to 2 attempts)
    max_fix_attempts = 2
    for attempt in range(max_fix_attempts):
        print(f"[Auto-fix] Attempt {attempt + 1} to fix error using LLM...")
        if auto_fix_code(error):
            success2, error2 = try_run()
            if success2:
                state["build_success"] = True
                print("Build successful after auto-fix.")
                return state
            else:
                error = error2
                print(f"Auto-fix applied but error persists: {error[:200]}")
        else:
            print("[Auto-fix] LLM could not fix the error.")
            break

    # Fallback to user
    print("Automatic fixes exhausted. Please help fix the error.")
    fix = input("Enter fix suggestion (or 'skip'): ").strip()
    if fix.lower() != "skip":
        print("Please apply the fix manually and press Enter when done.")
        input()
        success2, _ = try_run()
        state["build_success"] = success2
    else:
        state["build_success"] = False
    return state


def play_game(state: AgentState) -> AgentState:
    if not state["build_success"]:
        return state
    print("Starting game...")
    try:
        subprocess.run(["python3", GAME_CODE_FILE], cwd=WORK_DIR, check=True)
    except subprocess.CalledProcessError:
        pass
    print("Game ended.")
    return state


def user_approval(state: AgentState) -> AgentState:
    if not state["build_success"]:
        return state
    ans = input("\nIs this version satisfactory? (yes/no): ").strip().lower()
    if ans == "yes":
        state["game_running"] = False
        # Reset accumulated suggestions when user approves
        state["accumulated_suggestions"] = ""
    else:
        state["game_running"] = True
        state["build_retry_allowed"] = True
        # Keep accumulated suggestions for next iteration in same circle
        print(
            f"Suggestions will be accumulated: {state.get('accumulated_suggestions', '')}"
        )
    return state


# -----------------------------------------------------------------------------
# Graph construction and routing
# -----------------------------------------------------------------------------


def should_continue_after_user_input(state: AgentState) -> str:
    if state.get("play_requested", False):
        return "play_game"
    elif state.get("manual_reload_requested", False):
        return "load_versions"
    else:
        return "generate_next_version"


def should_continue_after_build(state: AgentState) -> str:
    if not state["build_success"] and not state["build_retry_allowed"]:
        return END
    else:
        return "play_game"


def after_play(state: AgentState) -> str:
    if state.get("play_requested", False):
        state["play_requested"] = False
        return "get_user_input"
    else:
        return "user_approval"


def after_approval(state: AgentState) -> str:
    if state["game_running"] is False:
        return "save_approved_version"
    else:
        return "get_user_input"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("load_versions", load_versions)
    graph.add_node("initialize_game", initialize_game)
    graph.add_node("git_checkout_last_circle", git_checkout_last_circle)
    graph.add_node("get_user_input", get_user_input)
    graph.add_node("generate_next_version", generate_next_version)
    graph.add_node("generate_game_code", generate_game_code)
    graph.add_node("update_documentation", update_documentation)
    graph.add_node("build_and_run", build_and_run)
    graph.add_node("play_game", play_game)
    graph.add_node("user_approval", user_approval)
    graph.add_node("save_approved_version", save_approved_version)

    graph.set_entry_point("load_versions")
    graph.add_edge("load_versions", "initialize_game")
    graph.add_edge("initialize_game", "git_checkout_last_circle")
    graph.add_edge("git_checkout_last_circle", "get_user_input")

    graph.add_conditional_edges(
        "get_user_input",
        should_continue_after_user_input,
        {
            "play_game": "play_game",
            "load_versions": "load_versions",
            "generate_next_version": "generate_next_version",
        },
    )

    graph.add_edge("generate_next_version", "generate_game_code")
    graph.add_edge("generate_game_code", "update_documentation")
    graph.add_edge("update_documentation", "build_and_run")

    graph.add_conditional_edges(
        "build_and_run",
        should_continue_after_build,
        {
            "play_game": "play_game",
            END: END,
        },
    )

    graph.add_conditional_edges(
        "play_game",
        after_play,
        {
            "user_approval": "user_approval",
            "get_user_input": "get_user_input",
        },
    )

    graph.add_conditional_edges(
        "user_approval",
        after_approval,
        {
            "save_approved_version": "save_approved_version",
            "get_user_input": "get_user_input",
        },
    )

    graph.add_edge("save_approved_version", END)
    return graph.compile()


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main():
    initial_state: AgentState = {
        "latest_version": 0,
        "latest_definition": {},
        "all_definitions": [],
        "user_suggestions": "",
        "accumulated_suggestions": "",  # <-- NEW
        "next_version_definition": "",
        "build_retry_allowed": True,
        "build_success": False,
        "game_running": True,
        "manual_reload_requested": False,
        "play_requested": False,
        "git_repo": None,
    }
    app = build_graph()
    app.invoke(initial_state)
    print("Agent finished.")


if __name__ == "__main__":
    main()
