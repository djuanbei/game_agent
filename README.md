Below is a `README.md` file for the LangGraph agent project. It describes the purpose, installation, usage, and the modular project structure.

```markdown
# LangGraph Game Evolution Agent

An intelligent agent that iteratively evolves a game definition and implementation using LangGraph, Git, and an LLM (DeepSeek or OpenAI‑compatible). The agent reads versioned markdown definitions (`game_v*.md`), generates the next version and corresponding Python/Pygame code, manages controller bindings via `configure.json`, and tracks each completed evolution circle with Git.

## Features

- **Evolution workflow** – Loads existing definitions, asks for user suggestions, generates a new definition and game code via LLM.
- **Controller integration** – Logical actions mapped to physical buttons using `configure.json` (8BitDo Pro 3 ready).
- **Automatic dependency handling** – Detects missing `pygame` and runs `install.sh` or `pip` automatically.
- **Git versioning** – Commits each approved evolution as a branch `circle_vX`, ensuring reproducible states.
- **Streaming LLM output** – Shows progress in real time, no long blocks without feedback.
- **Modular codebase** – Separated into configuration, state, utilities, nodes, graph, and main entry point.

## Project Structure

```
game_agent/
├── __init__.py
├── config.py          # Constants (file names, LLM settings, Git prefix)
├── state.py           # AgentState TypedDict definition
├── utils.py           # File I/O, Git operations, installation helpers
├── nodes.py           # LangGraph node functions (load, generate, build, play, etc.)
├── graph.py           # Graph construction and conditional routing
└── main.py            # Entry point
agent.py               # Launcher (imports and runs main)
install.sh             # Environment setup script for the agent
```

## Prerequisites

- **macOS Intel** (x86_64) – Other platforms may work but are not officially tested.
- **Python 3.8+**
- **Git** (command line tool)
- **DeepSeek API key** (or any OpenAI‑compatible LLM endpoint)

## Installation

1. **Clone or download** the project to your local machine.
2. **Run the agent’s installation script** (sets up a virtual environment and installs dependencies):
   ```bash
   chmod +x install.sh
   ./install.sh
   ```
3. **Activate the virtual environment**:
   ```bash
   source venv/bin/activate
   ```
4. **Set your LLM API key** (DeepSeek in this example):
   ```bash
   export DEEPSEEK_API_KEY="your-api-key-here"
   ```
   (You can also modify `game_agent/config.py` directly, but using an environment variable is recommended.)

## Usage

1. **Prepare your game directory** (e.g., `mahjong-evolution`) containing:
   - `game_v0.md` – initial markdown definition
   - `configure.json` – controller mapping (optional, will be created if missing)

   See the example files below.

2. **Run the agent** from the parent directory (where `agent.py` is located):
   ```bash
   cd /path/to/game_agent
   source venv/bin/activate
   cd mahjong-evolution
   python ../agent.py
   ```

3. **Interact with the agent**:
   - The agent shows the current definition and asks for suggestions.
   - Type your suggestions (or `skip`, `reload`, `quit`).
   - It then generates the next definition and game code, builds, and launches the game.
   - Play the game using the 8BitDo Pro 3 controller. Press **Escape three times** to exit.
   - After exiting, the agent asks if the version is satisfactory.
     - If `yes`, it commits everything to Git (branch `circle_vX`) and finishes.
     - If `no`, you can provide more suggestions for the next cycle.

## Example Initial Files

### `game_v0.md` (Mahjong Solitaire)
```markdown
# Mahjong Solitaire

## Role
A tile-matching puzzle game where the player removes pairs of identical, free tiles.

## Rules
- The game uses a standard set of 144 Mahjong tiles.
- Tiles are arranged in a pyramid.
- A tile is free if it has no tile on top and at least one side unobstructed.
- Select a free tile, then a matching free tile to remove the pair.
- ...
```

### `configure.json`
```json
{
  "select": "A",
  "cancel": "B",
  "shuffle": "Start",
  "rotate_left": "L1",
  "rotate_right": "R1"
}
```

## How It Works (High Level)

1. **`load_versions`** – scans for `game_v*.md`, parses the latest definition.
2. **`git_checkout_last_circle`** – checks out the Git branch of the last finished circle.
3. **`get_user_input`** – displays current definition and reads user suggestions or reload command.
4. **`generate_next_version`** – calls the LLM to produce a new markdown definition.
5. **`save_next_version`** – writes the new definition to disk.
6. **`generate_game_code`** – calls the LLM to produce a Python/Pygame implementation.
7. **`update_documentation`** – creates/updates `README.md` and `install.sh` for the game.
8. **`build_and_run`** – tries to run the game; auto‑installs `pygame` if missing.
9. **`play_game`** – runs the game; waits for it to exit (Esc three times).
10. **`user_approval`** – asks if satisfied; if yes, commits to Git and ends; else loops.

## Customisation

- **LLM provider** – Edit `game_agent/config.py` to change `LLM_MODEL`, `LLM_BASE_URL`, or `LLM_API_KEY`.
- **Controller mapping** – Modify `configure.json` in the game directory.
- **Game code template** – Adjust the prompt in `generate_game_code` (in `nodes.py`).

## Troubleshooting

- **`ModuleNotFoundError: No module named 'git'`** – Make sure you activated the virtual environment (`source venv/bin/activate`).
- **`pygame` not found after auto‑install** – Ensure Homebrew is installed (`brew --version`). On macOS, the script uses `brew install sdl2 ...` and `pip3 install pygame`.
- **LLM timeout / no output** – Check your internet connection and API key. The agent streams output, so you should see incremental text.
- **Game doesn’t exit on Esc three times** – The generated `game.py` must implement the triple‑escape logic. If not, provide a suggestion to fix it in the next evolution.

## License

This project is open source under the MIT License. See the `LICENSE` file (if any) or refer to the project repository.
```

Place this `README.md` in the root of the project (the directory containing `agent.py` and `install.sh`). Adjust any paths or details to match your actual setup.
