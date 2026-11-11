"""Client registry service for InvoicePilot.

Loads ``clients.json`` -- a flat ``{"name": "email"}`` mapping -- and provides
case-sensitive, exact-match name-to-email lookup (OQ-1 design assumption).

This module is read-only: it never writes to ``clients.json`` and never calls
any PayPal API.
"""

import json
from pathlib import Path

#: Default location of the clients registry file.
CLIENTS_FILE = "clients.json"


def load_clients(path: str = CLIENTS_FILE) -> dict[str, str]:
    """Load ``clients.json`` as a flat ``{"name": "email"}`` dict.

    Args:
        path: Path to the clients JSON file. Defaults to ``clients.json`` in
            the current working directory.

    Returns:
        A dictionary mapping client names to email addresses.

    Raises:
        FileNotFoundError: if the file does not exist, with a clear message
            explaining how to create it from the example.
        ValueError: if the file does not contain a flat name-to-email object.
    """
    clients_path = Path(path)
    if not clients_path.exists():
        raise FileNotFoundError(
            f"Client registry not found: {clients_path}. "
            f"Copy clients.json.example to clients.json and add your clients."
        )
    with clients_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # Defensive: ensure the loaded structure is a flat name->email mapping.
    if not isinstance(data, dict):
        raise ValueError(
            f"Expected clients.json to be a flat object mapping names to "
            f"emails, got {type(data).__name__}."
        )
    return data


def lookup_email(name: str, clients: dict[str, str]) -> str | None:
    """Look up a client email by exact, case-sensitive name match.

    Args:
        name: The exact client name to look up.
        clients: The ``{"name": "email"}`` mapping from :func:`load_clients`.

    Returns:
        The email address if found, or ``None`` when the name is not present.
        Lookup is case-sensitive with no fuzzy matching (OQ-1).
    """
    return clients.get(name)


__all__ = ["CLIENTS_FILE", "load_clients", "lookup_email"]
