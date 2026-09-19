"""Backward-compatible alias for identifier normalization.

The canonical implementation lives in
``context_broker.context_ttc.tools.identity_tools.normalize_identifier``.
"""

from context_broker.context_ttc.tools.identity_tools import (
    normalize_identifier as safe_id,
)

__all__ = ["safe_id"]
