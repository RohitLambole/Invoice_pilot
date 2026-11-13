"""Configuration module for InvoicePilot.

Loads environment variables from the ``.env`` file, defines the application
constants (amount cap, currency, Gemini model name), and validates that all
required secrets are present at startup.

This module fails fast: importing it raises :class:`RuntimeError` with a clear
message if any required environment variable is missing. It never prints or
logs secret values -- error messages name only the missing variable, never
its value.

Environment variables
----------------------
Required (raise if missing):
    PAYPAL_CLIENT_ID   PayPal sandbox client id.
    PAYPAL_SECRET      PayPal sandbox secret. The alias PAYPAL_CLIENT_SECRET is
                       accepted and normalised to PAYPAL_SECRET when the
                       canonical name is not set.
    GOOGLE_API_KEY     Google Gemini API key.

Optional (have defaults):
    GEMINI_MODEL       Gemini model name. Defaults to "gemini-2.5-flash".
"""

import os

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Application constants (Requirement 2.1, 2.3, 12.4)
# ---------------------------------------------------------------------------

#: Maximum allowed invoice amount in USD. Hard block enforced before any
#: invoice proposal can be approved (Requirement 2.1).
AMOUNT_CAP = 1000.00

#: The only supported currency for every invoice proposal (Requirement 2.3).
CURRENCY = "USD"

#: Default Gemini model used when GEMINI_MODEL is not set in the environment.
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

# Load variables from a .env file into os.environ when present. Safe to call
# even when no .env file exists.
load_dotenv()


def _require_env(name: str, message: str | None = None) -> str:
    """Return a required, non-empty environment variable.

    Args:
        name: The environment variable name.
        message: Optional custom error message.

    Returns:
        The stripped value of the variable.

    Raises:
        RuntimeError: if the variable is missing or empty. The message names
            the missing variable only (never any value), so no secret leaks.
    """
    value = os.environ.get(name)
    if not value or not value.strip():
        raise RuntimeError(
            message
            or f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill in your credentials."
        )
    return value.strip()


# ---------------------------------------------------------------------------
# Required credentials
# ---------------------------------------------------------------------------

PAYPAL_CLIENT_ID = _require_env("PAYPAL_CLIENT_ID")

# Normalise the PayPal secret alias: when PAYPAL_SECRET is not set but
# PAYPAL_CLIENT_SECRET is (the PayPal dashboard labels it "Client Secret"),
# copy the alias into PAYPAL_SECRET so the rest of the app reads one name.
if not os.environ.get("PAYPAL_SECRET") and os.environ.get("PAYPAL_CLIENT_SECRET"):
    os.environ["PAYPAL_SECRET"] = os.environ["PAYPAL_CLIENT_SECRET"]

PAYPAL_SECRET = _require_env(
    "PAYPAL_SECRET",
    "Missing required environment variable: PAYPAL_SECRET "
    "(or its alias PAYPAL_CLIENT_SECRET). "
    "Copy .env.example to .env and fill in your credentials.",
)

GOOGLE_API_KEY = _require_env("GOOGLE_API_KEY")

# ---------------------------------------------------------------------------
# Optional configuration with defaults
# ---------------------------------------------------------------------------

# GEMINI_MODEL is optional. Defaulting it lets a judge swap models with a
# one-line change in .env (Requirement 12.4).
_gemini_model = os.environ.get("GEMINI_MODEL")
if not _gemini_model or not _gemini_model.strip():
    _gemini_model = DEFAULT_GEMINI_MODEL
GEMINI_MODEL = _gemini_model.strip()

# PAYPAL_SELLER_EMAIL is optional. When set, it is included in
# invoicer.email_address so PayPal uses the correct sandbox seller account.
PAYPAL_SELLER_EMAIL = os.environ.get("PAYPAL_SELLER_EMAIL", "").strip() or None

# PAYPAL_BUSINESS_NAME is used in invoicer.business_name (required by PayPal
# create_invoice schema). Defaults to 'InvoicePilot' if not set.
PAYPAL_BUSINESS_NAME = os.environ.get("PAYPAL_BUSINESS_NAME", "").strip() or "InvoicePilot"


__all__ = [
    "AMOUNT_CAP",
    "CURRENCY",
    "DEFAULT_GEMINI_MODEL",
    "PAYPAL_CLIENT_ID",
    "PAYPAL_SECRET",
    "GOOGLE_API_KEY",
    "GEMINI_MODEL",
    "PAYPAL_SELLER_EMAIL",
    "PAYPAL_BUSINESS_NAME",
]
