"""
Group AI Session Helper — returns persistent synthetic user_id and session_id for group ADK sessions.
"""
from typing import Tuple

APP_NAME = "my_agent"


def get_group_session_identity(group_id: str) -> Tuple[str, str]:
    """
    Returns (user_id, session_id) for the group's AI session.
    Using synthetic user_id 'group_{group_id}' ensures ADK context is shared across all group members.
    """
    return f"group_{group_id}", f"gsession_{group_id}"
