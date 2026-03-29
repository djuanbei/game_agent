from typing import Dict, List, Any, Optional, TypedDict
import git

class AgentState(TypedDict):
    latest_version: int
    latest_definition: Dict[str, Any]
    all_definitions: List[Dict[str, Any]]
    user_suggestions: str
    next_version_definition: str
    build_retry_allowed: bool
    build_success: bool
    game_running: bool
    manual_reload_requested: bool
    play_requested: bool   # <-- added
    git_repo: Optional[git.Repo]