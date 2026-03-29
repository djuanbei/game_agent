"""LangGraph construction and routing."""
from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes import (
    load_versions, git_checkout_last_circle, get_user_input,
    generate_next_version, save_next_version, generate_game_code,
    update_documentation, build_and_run, play_game, user_approval
)

# -----------------------------------------------------------------------------
# Routing functions
# -----------------------------------------------------------------------------

def should_continue_after_user_input(state: AgentState) -> str:
    if state['manual_reload_requested']:
        return "load_versions"
    else:
        return "generate_next_version"

def should_continue_after_build(state: AgentState) -> str:
    if not state['build_success'] and not state['build_retry_allowed']:
        return END
    else:
        return "play_game"

def should_continue_after_approval(state: AgentState) -> str:
    if state['game_running'] is False:
        return END
    else:
        return "get_user_input"

def build_graph() -> StateGraph:
    """Create and compile the LangGraph."""
    graph = StateGraph(AgentState)

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

    graph.set_entry_point("load_versions")

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
