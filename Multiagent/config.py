"""
Centralised Azure OpenAI configuration.

Resolution order for every setting:
  1. Streamlit secrets  (st.secrets)  – used on Streamlit Cloud
  2. Environment variable              – used locally / in CI
  3. Hard-coded fallback (empty)       – ensures a clear error if nothing is set
"""

import os

def _get(key: str, default: str = "") -> str:
    """Return the secret from Streamlit secrets or the environment."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


AZURE_OPENAI_ENDPOINT    = _get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY     = _get("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT  = _get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.2-chat")
AZURE_OPENAI_API_VERSION = _get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

# agent.py uses a separate Azure OpenAI resource
AGENT_OPENAI_ENDPOINT    = _get("AGENT_OPENAI_ENDPOINT")
AGENT_OPENAI_API_KEY     = _get("AGENT_OPENAI_API_KEY")
AGENT_OPENAI_DEPLOYMENT  = _get("AGENT_OPENAI_DEPLOYMENT", "gpt-5.2-chat")
AGENT_OPENAI_API_VERSION = _get("AGENT_OPENAI_API_VERSION", "2024-12-01-preview")
