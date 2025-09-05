# app/auth_manager.py

import json
import os
import logging
from app import config

CURRENT_USER = {
    "username": None,
    "role": None,
    "token": None,
    "full_name": None,
    "last_sync_timestamp": None
}

def set_current_user(username: str, role: str, token: str, full_name: str):
    """Sets the active user for the current session."""
    CURRENT_USER["username"] = username
    CURRENT_USER["role"] = role
    CURRENT_USER["token"] = f"Bearer {token}"
    CURRENT_USER["full_name"] = full_name
    # Do not reset the timestamp on login, load it from the file

def save_session_to_disk():
    """Saves the entire current session object to session.json."""
    with open(config.SESSION_FILE, 'w') as f:
        json.dump(CURRENT_USER, f, indent=2)

def load_session_from_disk() -> bool:
    """Loads a session from session.json if it exists and is valid."""
    if not os.path.exists(config.SESSION_FILE):
        return False
    try:
        with open(config.SESSION_FILE, 'r') as f:
            session_data = json.load(f)
            if session_data.get("username") and session_data.get("token"):
                CURRENT_USER.update(session_data)
                return True
    except (json.JSONDecodeError, KeyError):
        logout()
    return False

def get_auth_headers() -> dict:
    """Returns the authorization headers required for API calls."""
    return {"Authorization": CURRENT_USER["token"]} if CURRENT_USER["token"] else {}

def get_current_role() -> str:
    """Returns the role of the currently logged-in user."""
    return CURRENT_USER["role"]

def get_current_user_info() -> dict:
    """Returns the entire dictionary of the current user's info."""
    return CURRENT_USER

def is_logged_in() -> bool:
    """Checks if a user is currently logged in."""
    return CURRENT_USER["token"] is not None

def logout():
    """Logs out the user and deletes the session file."""
    global CURRENT_USER
    CURRENT_USER = {
        "username": None, "role": None, "token": None,
        "full_name": None, "last_sync_timestamp": None
    }
    if os.path.exists(config.SESSION_FILE):
        os.remove(config.SESSION_FILE)

def update_session_timestamp(timestamp_str: str | None):
    """
    Safely updates only the sync timestamp in the current session
    and saves the changes to disk.
    """
    if "username" in CURRENT_USER and CURRENT_USER["username"] is not None:
        CURRENT_USER["last_sync_timestamp"] = timestamp_str
        save_session_to_disk()
    else:
        logging.warning("Attempted to update timestamp without a logged-in user.")