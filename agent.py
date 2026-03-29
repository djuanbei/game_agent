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

from .config import (
    WORK_DIR,
    GAME_CODE_FILE,
    CONFIG_FILE,
    README_FILE,
    INSTALL_FILE,
    LLM_MODEL,
    LLM_BASE_URL,
    LLM_API_KEY as BASE_LLM_API_KEY,
    CIRCLE_BRANCH_PREFIX,
)

# Override API key from environment
LLM_API_KEY = os.environ.get("DEEPSEEK_API_KEY", BASE_LLM_API_KEY)

# -----------------------------------------------------------------------------
# State definition
# -----------------------------------------------------------------------------


from .state import AgentState


# -----------------------------------------------------------------------------
# Helper functions (file I/O, Git, installation, code fixing)
# -----------------------------------------------------------------------------

from .utils import (
    load_all_definitions,
    parse_definition,
    save_definition,
    load_controller_config,
    save_controller_config,
    ensure_controller_config,
    get_git_repo,
    checkout_last_circle,
    commit_circle,
    ensure_install_script,
    auto_install_pygame,
    auto_install_missing_module,
    auto_fix_code,
)

from .nodes import (
    load_versions,
    initialize_game,
    git_checkout_last_circle,
    get_user_input,
    generate_next_version,
    save_approved_version,
    generate_game_code,
    update_documentation,
    build_and_run,
    play_game,
    user_approval,
)

from .graph import (
    build_graph,
    should_continue_after_user_input,
    should_continue_after_build,
    after_play,
    after_approval,
)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main():
    initial_state: AgentState = {
        "latest_version": 0,
        "latest_definition": {},
        "all_definitions": [],
        "user_suggestions": "",
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
