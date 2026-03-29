"""LangGraph node functions for game evolution."""

import sys
import subprocess
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from .config import (
    WORK_DIR,
    GAME_CODE_FILE,
    CONFIG_FILE,
    INSTALL_FILE,
    LLM_MODEL,
    LLM_BASE_URL,
    LLM_API_KEY,
)
from .state import AgentState
from .utils import (
    load_all_definitions,
    load_controller_config,
    save_definition,
    get_git_repo,
    checkout_last_circle,
    commit_circle,
    ensure_install_script,
    auto_install_pygame,
    auto_fix_code,
    parse_definition,
    auto_install_missing_module,
    ensure_controller_config,
    is_file_tracked,
)


# ... (keep all other node functions unchanged: load_versions, git_checkout_last_circle,
#      get_user_input, generate_next_version, save_next_version, generate_game_code,
#      update_documentation, play_game, user_approval)


# Replace ONLY build_and_run with the enhanced version below
def build_and_run(state: AgentState) -> AgentState:
    """Attempt to run the game. Auto-install missing modules, then auto-fix any error using LLM."""
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
            # Game started and is still running (waiting for user input) – treat as success
            print("Game started successfully (no immediate errors).")
            return True, None
        except Exception as e:
            return False, str(e)

    # First attempt
    success, error = try_run()
    if success:
        state["build_success"] = True
        return state

    print(f"Build error: {error}")

    # ----- AUTO-INSTALL MISSING MODULES -----
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

    # ----- GENERIC AUTO-FIX USING LLM (for any error) -----
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

    # ----- FALLBACK: ask user once -----
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


# -----------------------------------------------------------------------------
# Node implementations
# -----------------------------------------------------------------------------


def load_versions(state: AgentState) -> AgentState:
    """Load existing definition files."""
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
    """Checkout the branch of the last completed circle."""
    repo = get_git_repo()
    state["git_repo"] = repo
    if state["latest_version"] > 0:
        checkout_last_circle(repo, state["latest_version"])
    return state


def get_user_input(state: AgentState) -> AgentState:
    """Prompt user for suggestions or reload/play/quit commands."""
    print("\n" + "=" * 60)
    print(f"Current game definition (v{state['latest_version']}):")
    print(f"Name: {state['latest_definition'].get('name', 'N/A')}")
    print(f"Role: {state['latest_definition'].get('role', 'N/A')}")
    print("Rules:")
    for rule in state["latest_definition"].get("rules", []):
        print(f"  - {rule}")
    print("=" * 60)
    user = (
        input(
            "\nEnter suggestions for next version (or 'skip', 'reload', 'play', 'quit'): "
        )
        .strip()
        .lower()
    )
    if user == "quit":
        sys.exit(0)
    elif user == "reload":
        state["manual_reload_requested"] = True
        state["play_requested"] = False
    elif user == "play":
        state["play_requested"] = True
        state["manual_reload_requested"] = False
        state["user_suggestions"] = ""  # clear any previous suggestions
    else:
        state["user_suggestions"] = user
        state["manual_reload_requested"] = False
        state["play_requested"] = False
    return state


def generate_next_version(state: AgentState) -> AgentState:
    """Generate the next version definition in memory (do NOT save to disk)."""
    if state["manual_reload_requested"]:
        return state

    print("\n[Progress] Generating next version definition using LLM...")
    # Build prompt (same as before)
    previous_defs_text = "\n\n".join(
        f"# Version {d['version']}\n"
        f"Name: {d.get('name')}\n"
        f"Role: {d.get('role')}\n"
        f"Rules: {', '.join(d.get('rules', []))}"
        for d in state["all_definitions"]
    )
    config = load_controller_config()
    prompt = f"""You are evolving a game definition. Here is the history:

{previous_defs_text}

Current controller configuration (logical actions to physical buttons):
{json.dumps(config, indent=2)}

User suggestions: {state["user_suggestions"] if state["user_suggestions"] else "None"}

Generate the next version (v{state["latest_version"] + 1}) in markdown format with sections:
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
    state["next_version_definition"] = response_content
    # Note: we do NOT increment latest_version or save to disk here.
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

    # Commit all changes to Git
    commit_circle(repo, new_version)
    print(f"Committed circle v{new_version} to Git.")
    return state


def generate_game_code(state: AgentState) -> AgentState:
    """Generate/update game.py based on latest definition and controller config."""
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
    # Remove any markdown code fences if present
    if code.startswith("```python"):
        code = code[9:]
    if code.endswith("```"):
        code = code[:-3]
    (WORK_DIR / GAME_CODE_FILE).write_text(code.strip(), encoding="utf-8")
    return state


def update_documentation(state: AgentState) -> AgentState:
    """Generate README.md and install.sh."""
    latest = state["latest_definition"]
    config = load_controller_config()
    # README
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
    (WORK_DIR / "README.md").write_text(readme_content, encoding="utf-8")
    ensure_install_script()
    return state


def play_game(state: AgentState) -> AgentState:
    """Launch the game and wait for it to exit (Esc three times)."""
    if not state["build_success"]:
        return state
    print("Starting game...")
    try:
        subprocess.run(["python3", GAME_CODE_FILE], cwd=WORK_DIR, check=True)
    except subprocess.CalledProcessError:
        pass  # Game might exit with error, but we'll continue
    print("Game ended.")
    return state


def user_approval(state: AgentState) -> AgentState:
    """Ask user if satisfied; set game_running flag accordingly."""
    if not state["build_success"]:
        return state
    ans = input("\nIs this version satisfactory? (yes/no): ").strip().lower()
    if ans == "yes":
        state["game_running"] = False  # signals approval
    else:
        state["game_running"] = True  # not approved, continue
        state["build_retry_allowed"] = True
    return state
