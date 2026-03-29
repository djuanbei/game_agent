#!/usr/bin/env python3
"""
LangGraph Agent for Evolving Game Definitions (8BitDo Pro 3) with Git Integration

This agent manages the iterative evolution of a game defined in markdown files.
It integrates with Git to version both the game definitions and the implementation.
"""

import os
import sys
import json
import subprocess
import time
import signal
from pathlib import Path
from typing import Dict, List, Any, Optional, TypedDict, Annotated

import git
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

WORK_DIR = Path.cwd()  # The directory where the game lives
GAME_CODE_FILE = "game.py"  # Generated game implementation
CONFIG_FILE = "configure.json"  # Controller mapping
README_FILE = "README.md"
INSTALL_FILE = "install.sh"

# LLM settings (DeepSeek via OpenAI-compatible endpoint)
LLM_MODEL = "deepseek-chat"  # or "deepseek-coder"
LLM_BASE_URL = "https://api.deepseek.com/v1"
LLM_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "your-api-key-here")

# Git branch/tag prefix for circles
CIRCLE_BRANCH_PREFIX = "circle_v"


# -----------------------------------------------------------------------------
# State definition for LangGraph
# -----------------------------------------------------------------------------

class AgentState(TypedDict):
    """State of the agent across nodes."""
    latest_version: int
    latest_definition: Dict[str, Any]  # parsed from game_vn.md
    all_definitions: List[Dict[str, Any]]  # list of parsed definitions
    user_suggestions: str
    next_version_definition: str  # raw markdown of new version
    build_retry_allowed: bool
    build_success: bool
    game_running: bool
    manual_reload_requested: bool
    git_repo: Optional[git.Repo]


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

def load_all_definitions() -> tuple[int, Dict[str, Any], List[Dict[str, Any]]]:
    """
    Scan WORK_DIR for game_v*.md files, parse them, and return:
    - highest version number
    - parsed dict of the latest version
    - list of all parsed definitions (ordered by version)
    """
    pattern = "game_v*.md"
    files = list(WORK_DIR.glob(pattern))
    if not files:
        # No definitions exist – create initial v0
        return 0, {}, []

    versions = []
    for f in files:
        # Extract number from filename
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
    """Parse a markdown definition into a dict with name, role, rules."""
    # Simple parsing: look for headings
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


def load_controller_config() -> Dict[str, str]:
    """Load configure.json, which maps logical actions to physical buttons."""
    config_path = WORK_DIR / CONFIG_FILE
    if config_path.exists():
        return json.loads(config_path.read_text(encoding='utf-8'))
    else:
        # Default config (empty)
        return {}


def save_controller_config(config: Dict[str, str]):
    """Save controller configuration."""
    (WORK_DIR / CONFIG_FILE).write_text(json.dumps(config, indent=2), encoding='utf-8')


def save_definition(version: int, content: str):
    """Write markdown definition to game_v<version>.md."""
    filename = f"game_v{version}.md"
    (WORK_DIR / filename).write_text(content, encoding='utf-8')


def get_git_repo() -> git.Repo:
    """Get or initialize Git repository in WORK_DIR."""
    try:
        repo = git.Repo(WORK_DIR)
    except git.exc.InvalidGitRepositoryError:
        repo = git.Repo.init(WORK_DIR)
    return repo


def checkout_last_circle(repo: git.Repo, version: int):
    """Checkout the branch circle_v<version> if it exists."""
    branch_name = f"{CIRCLE_BRANCH_PREFIX}{version}"
    if branch_name in repo.branches:
        repo.git.checkout(branch_name)
    else:
        # If no branch, stay as is (first run)
        pass


def commit_circle(repo: git.Repo, version: int):
    """Commit all relevant files and create a branch/tag for the finished circle."""
    # Add all relevant files (ignore anything not under version control)
    repo.git.add("game_v*.md")
    repo.git.add(GAME_CODE_FILE)
    repo.git.add(CONFIG_FILE)
    repo.git.add(README_FILE)
    repo.git.add(INSTALL_FILE)
    # Commit
    commit_msg = f"Evolution circle v{version} completed"
    repo.index.commit(commit_msg)
    # Create branch
    branch_name = f"{CIRCLE_BRANCH_PREFIX}{version}"
    if branch_name not in repo.branches:
        repo.create_head(branch_name)
    else:
        # If branch already exists, force update (should not happen)
        repo.git.branch("-D", branch_name)
        repo.create_head(branch_name)


# -----------------------------------------------------------------------------
# LangGraph nodes
# -----------------------------------------------------------------------------

def load_versions(state: AgentState) -> AgentState:
    """Load existing definition files."""
    version, latest, all_defs = load_all_definitions()
    state['latest_version'] = version
    state['latest_definition'] = latest
    state['all_definitions'] = all_defs
    state['manual_reload_requested'] = False
    return state


def git_checkout_last_circle(state: AgentState) -> AgentState:
    """Checkout the branch of the last completed circle."""
    repo = get_git_repo()
    state['git_repo'] = repo
    # Determine last finished version: from branch tags? For simplicity, use latest_version.
    # In practice you might have a file that records last circle.
    # We'll assume that the latest definition corresponds to the last circle.
    if state['latest_version'] > 0:
        checkout_last_circle(repo, state['latest_version'])
    return state


def get_user_input(state: AgentState) -> AgentState:
    """Prompt user for suggestions or reload command."""
    print("\n" + "=" * 60)
    print(f"Current game definition (v{state['latest_version']}):")
    print(f"Name: {state['latest_definition'].get('name', 'N/A')}")
    print(f"Role: {state['latest_definition'].get('role', 'N/A')}")
    print("Rules:")
    for rule in state['latest_definition'].get('rules', []):
        print(f"  - {rule}")
    print("=" * 60)
    user = input("\nEnter suggestions for next version (or 'skip', 'reload', 'quit'): ").strip()
    if user.lower() == 'quit':
        sys.exit(0)
    elif user.lower() == 'reload':
        state['manual_reload_requested'] = True
    else:
        state['user_suggestions'] = user
        state['manual_reload_requested'] = False
    return state


def generate_next_version(state: AgentState) -> AgentState:
    """Use LLM to generate the next version definition."""
    if state['manual_reload_requested']:
        return state

    print("\n[Progress] Generating next version definition using LLM...")
    # Build prompt
    previous_defs_text = "\n\n".join(
        f"# Version {d['version']}\n"
        f"Name: {d.get('name')}\n"
        f"Role: {d.get('role')}\n"
        f"Rules: {', '.join(d.get('rules', []))}"
        for d in state['all_definitions']
    )
    config = load_controller_config()
    prompt = f"""You are evolving a game definition. Here is the history:

{previous_defs_text}

Current controller configuration (logical actions to physical buttons):
{json.dumps(config, indent=2)}

User suggestions: {state['user_suggestions'] if state['user_suggestions'] else 'None'}

Generate the next version (v{state['latest_version'] + 1}) in markdown format with sections:
# Game Name
## Role
## Rules (list each rule as a bullet point)
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
    state['next_version_definition'] = response_content
    return state


def save_next_version(state: AgentState) -> AgentState:
    """Write the new definition to disk."""
    if state['manual_reload_requested']:
        return state
    new_version = state['latest_version'] + 1
    save_definition(new_version, state['next_version_definition'])
    # Update latest info
    state['latest_version'] = new_version
    state['latest_definition'] = parse_definition(state['next_version_definition'])
    state['all_definitions'].append(state['latest_definition'])
    return state


def generate_game_code(state: AgentState) -> AgentState:
    """Generate/update game.py based on latest definition and controller config."""
    print("\n[Progress] Generating game code using LLM...")
    latest = state['latest_definition']
    config = load_controller_config()
    prompt = f"""You are a game developer. Based on the following game definition and controller configuration, generate a complete Python game using Pygame that can be played with an 8BitDo Pro 3 controller.

Game definition:
Name: {latest.get('name')}
Role: {latest.get('role')}
Rules: {', '.join(latest.get('rules', []))}

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
    # Remove any markdown code fences if present
    if code.startswith("```python"):
        code = code[9:]
    if code.endswith("```"):
        code = code[:-3]
    (WORK_DIR / GAME_CODE_FILE).write_text(code.strip(), encoding='utf-8')
    return state


def update_documentation(state: AgentState) -> AgentState:
    """Generate README.md and install.sh."""
    latest = state['latest_definition']
    config = load_controller_config()
    # README
    readme_content = f"""# {latest.get('name')}

## Description
{latest.get('role')}

## How to Play
{', '.join(latest.get('rules', []))}

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
    (WORK_DIR / README_FILE).write_text(readme_content, encoding='utf-8')

    # install.sh
    install_content = """#!/bin/bash
# Install dependencies for the game on macOS Intel
set -e

# Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Please install Homebrew first: https://brew.sh/"
    exit 1
fi

# Install Pygame dependencies via Homebrew
brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf

# Install Python dependencies
pip3 install --user pygame

echo "All dependencies installed. Run 'python3 game.py' to start the game."
"""
    (WORK_DIR / INSTALL_FILE).write_text(install_content, encoding='utf-8')
    os.chmod(WORK_DIR / INSTALL_FILE, 0o755)
    return state


def build_and_run(state: AgentState) -> AgentState:
    """Attempt to run the game. If error, ask user once for fix and retry."""
    # We'll simply run game.py in a subprocess and check if it starts without error.
    # For simplicity, we'll run with a timeout to catch immediate errors.
    try:
        # Run with a short timeout to see if it starts properly
        result = subprocess.run(
            ["python3", GAME_CODE_FILE],
            cwd=WORK_DIR,
            timeout=5,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise Exception(result.stderr)
        state['build_success'] = True
        print("Build successful.")
    except Exception as e:
        print(f"Build error: {e}")
        state['build_success'] = False
        if state['build_retry_allowed']:
            # Ask user once
            fix = input("Enter fix suggestion (or 'skip'): ").strip()
            if fix.lower() != 'skip':
                # For simplicity, we assume the fix is applied manually by the user.
                # In a more advanced version, the agent would try to incorporate the fix.
                print("Please apply the fix manually and press Enter when done.")
                input()
                # Retry build
                try:
                    subprocess.run(["python3", GAME_CODE_FILE], cwd=WORK_DIR, timeout=5, check=True)
                    state['build_success'] = True
                except:
                    state['build_success'] = False
            state['build_retry_allowed'] = False
        else:
            print("Build failed and no retry allowed. Exiting cycle.")
    return state


def play_game(state: AgentState) -> AgentState:
    """Launch the game and wait for it to exit (Esc three times)."""
    if not state['build_success']:
        return state
    print("Starting game...")
    # Run game in a subprocess and wait for it to finish.
    # The game should exit on its own after Esc three times.
    try:
        subprocess.run(["python3", GAME_CODE_FILE], cwd=WORK_DIR, check=True)
    except subprocess.CalledProcessError:
        pass  # Game might exit with error, but we'll continue
    print("Game ended.")
    return state


def user_approval(state: AgentState) -> AgentState:
    """Ask user if satisfied; if yes, commit to Git and finish; else continue."""
    if not state['build_success']:
        # If build failed, don't ask for approval; just continue?
        return state
    ans = input("\nIs this version satisfactory? (yes/no): ").strip().lower()
    if ans == 'yes':
        # Commit and tag
        repo = state['git_repo']
        commit_circle(repo, state['latest_version'])
        print(f"Committed circle v{state['latest_version']} to Git.")
        state['game_running'] = False
        # End the graph
        return state
    else:
        # Continue loop: reset suggestions, increment build_retry_allowed flag for next build
        state['build_retry_allowed'] = True
        return state


# -----------------------------------------------------------------------------
# Graph construction
# -----------------------------------------------------------------------------

def should_continue_after_user_input(state: AgentState) -> str:
    """Decide next node after get_user_input."""
    if state['manual_reload_requested']:
        return "load_versions"
    else:
        return "generate_next_version"


def should_continue_after_build(state: AgentState) -> str:
    """If build failed and retry not allowed, go to END; else continue."""
    if not state['build_success'] and not state['build_retry_allowed']:
        return END
    else:
        return "play_game"


def should_continue_after_approval(state: AgentState) -> str:
    """If approved, end; else go to get_user_input to continue."""
    if state['game_running'] is False:
        return END
    else:
        return "get_user_input"


def build_graph() -> StateGraph:
    """Create and compile the LangGraph."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("load_versions", load_versions)
    graph.add_node("git_checkout_last_circle", git_checkout_last_circle)
    graph.add_node("get_user_input", get_user_input)
    graph.add_node("generate_next_version", generate_next_version)
    graph.add_node("save_next_version", save_next_version)
    graph.add_node("generate_game_code", generate_game_code)
    graph.add_node("update_documentation", update_documentation)
    graph.add_node("build_and_run", build_and_run)
    graph.add_node("play_game", play_game)
    graph.add_node("user_approval", user_approval)

    # Set entry point
    graph.set_entry_point("load_versions")

    # Define edges
    graph.add_edge("load_versions", "git_checkout_last_circle")
    graph.add_edge("git_checkout_last_circle", "get_user_input")

    graph.add_conditional_edges(
        "get_user_input",
        should_continue_after_user_input,
        {
            "load_versions": "load_versions",
            "generate_next_version": "generate_next_version",
        }
    )

    graph.add_edge("generate_next_version", "save_next_version")
    graph.add_edge("save_next_version", "generate_game_code")
    graph.add_edge("generate_game_code", "update_documentation")
    graph.add_edge("update_documentation", "build_and_run")

    graph.add_conditional_edges(
        "build_and_run",
        should_continue_after_build,
        {
            "play_game": "play_game",
            END: END,
        }
    )

    graph.add_edge("play_game", "user_approval")

    graph.add_conditional_edges(
        "user_approval",
        should_continue_after_approval,
        {
            END: END,
            "get_user_input": "get_user_input",
        }
    )

    return graph.compile()


# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------

def main():
    """Run the agent."""
    # Initial state
    initial_state: AgentState = {
        'latest_version': 0,
        'latest_definition': {},
        'all_definitions': [],
        'user_suggestions': "",
        'next_version_definition': "",
        'build_retry_allowed': True,
        'build_success': False,
        'game_running': True,
        'manual_reload_requested': False,
        'git_repo': None,
    }
    app = build_graph()
    # Run the graph
    final_state = app.invoke(initial_state)
    print("Agent finished.")


if __name__ == "__main__":
    main()