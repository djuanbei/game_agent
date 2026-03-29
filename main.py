"""Main entry point for the LangGraph agent."""
import os

from .config import LLM_API_KEY
from .state import AgentState
from .graph import build_graph

def main():
    # Override API key from environment
    if "DEEPSEEK_API_KEY" in os.environ:
        from .config import LLM_API_KEY as _key
        # Actually we need to set the module variable; simpler: just use env var in nodes
        # We'll handle it inside nodes by reading os.environ each time.
        pass

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
    final_state = app.invoke(initial_state)
    print("Agent finished.")

if __name__ == "__main__":
    main()
