"""LangGraph construction and routing."""

from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes import (
    load_versions,
    git_checkout_last_circle,
    get_user_input,
    generate_next_version,
    generate_game_code,
    update_documentation,
    build_and_run,
    play_game,
    user_approval,
    save_approved_version,
    initialize_game,
)


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
    # If we came from a 'play' command, go back to user input; otherwise continue to approval
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
