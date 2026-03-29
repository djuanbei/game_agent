"""LangGraph node functions for game evolution."""
import sys
import subprocess
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from .config import (
    WORK_DIR, GAME_CODE_FILE, INSTALL_FILE,
    LLM_MODEL, LLM_BASE_URL, LLM_API_KEY
)
from .state import AgentState
from .utils import (
    load_all_definitions, load_controller_config, save_definition,
    get_git_repo, checkout_last_circle, commit_circle,
    ensure_install_script, auto_install_pygame, auto_fix_code, parse_definition
)

# -----------------------------------------------------------------------------
# Node implementations
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
    if state['latest_version'] > 0:
        checkout_last_circle(repo, state['latest_version'])
    return state

def get_user_input(state: AgentState) -> AgentState:
    """Prompt user for suggestions or reload command."""
    print("\n" + "="*60)
    print(f"Current game definition (v{state['latest_version']}):")
    print(f"Name: {state['latest_definition'].get('name', 'N/A')}")
    print(f"Role: {state['latest_definition'].get('role', 'N/A')}")
    print("Rules:")
    for rule in state['latest_definition'].get('rules', []):
        print(f"  - {rule}")
    print("="*60)
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

Generate the next version (v{state['latest_version']+1}) in markdown format with sections:
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
    (WORK_DIR / "README.md").write_text(readme_content, encoding='utf-8')
    ensure_install_script()
    return state

def build_and_run(state: AgentState) -> AgentState:
    """Attempt to run the game. Auto-fix missing pygame AND syntax errors."""
    if not (WORK_DIR / GAME_CODE_FILE).exists():
        state['build_success'] = False
        return state

    def try_run():
        try:
            result = subprocess.run(
                ["python3", GAME_CODE_FILE],
                cwd=WORK_DIR,
                timeout=5,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise Exception(result.stderr)
            return True, ""
        except subprocess.TimeoutExpired:
            return True, ""
        except Exception as e:
            return False, str(e)

    # First attempt
    success, error = try_run()
    if success:
        state['build_success'] = True
        print("Build successful.")
        return state

    print(f"Build error: {error}")

    # Auto-fix for missing pygame
    if "No module named 'pygame'" in error and state['build_retry_allowed']:
        print("[Auto-fix] Missing pygame detected. Attempting automatic installation...")
        if auto_install_pygame():
            print("[Auto-fix] Installation completed. Retrying build...")
            success2, error2 = try_run()
            if success2:
                state['build_success'] = True
                print("Build successful after pygame installation.")
                state['build_retry_allowed'] = False
                return state
            else:
                error = error2
        else:
            print("[Auto-fix] Automatic pygame installation failed.")

    # Auto-fix for syntax errors
    if "SyntaxError" in error and state['build_retry_allowed']:
        for attempt in range(2):  # max 2 fix attempts
            print(f"[Auto-fix] Syntax error detected. Attempt {attempt+1} to fix...")
            if auto_fix_code(error):
                success2, error2 = try_run()
                if success2:
                    state['build_success'] = True
                    print("Build successful after syntax fix.")
                    state['build_retry_allowed'] = False
                    return state
                else:
                    error = error2
            else:
                print("[Auto-fix] Could not automatically fix syntax error.")
                break
        # If we get here, auto-fix failed
        if not state['build_success']:
            print("[Auto-fix] Syntax error could not be resolved automatically.")

    # If auto-fix not applicable or failed, ask user once
    if state['build_retry_allowed']:
        fix = input("Enter fix suggestion (or 'skip'): ").strip()
        if fix.lower() != 'skip':
            print("Please apply the fix manually and press Enter when done.")
            input()
            success2, _ = try_run()
            state['build_success'] = success2
        state['build_retry_allowed'] = False
    else:
        print("Build failed and no retry allowed. Exiting cycle.")
    return state

def play_game(state: AgentState) -> AgentState:
    """Launch the game and wait for it to exit (Esc three times)."""
    if not state['build_success']:
        return state
    print("Starting game...")
    try:
        subprocess.run(["python3", GAME_CODE_FILE], cwd=WORK_DIR, check=True)
    except subprocess.CalledProcessError:
        pass  # Game might exit with error, but we'll continue
    print("Game ended.")
    return state

def user_approval(state: AgentState) -> AgentState:
    """Ask user if satisfied; if yes, commit to Git and finish; else continue."""
    if not state['build_success']:
        return state
    ans = input("\nIs this version satisfactory? (yes/no): ").strip().lower()
    if ans == 'yes':
        repo = state['git_repo']
        commit_circle(repo, state['latest_version'])
        print(f"Committed circle v{state['latest_version']} to Git.")
        state['game_running'] = False
        return state
    else:
        state['build_retry_allowed'] = True
        return state