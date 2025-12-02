"""API middleware components."""

from docvector.api.middleware.auth import (
    AuthContext,
    get_auth_context,
    require_auth,
    require_user,
    require_admin,
    require_scope,
    require_read,
    require_write,
)
from docvector.api.middleware.rate_limit import (
    RateLimiter,
    rate_limit,
)

__all__ = [
    # Auth
    "AuthContext",
    "get_auth_context",
    "require_auth",
    "require_user",
    "require_admin",
    "require_scope",
    "require_read",
    "require_write",
    # Rate limiting
    "RateLimiter",
    "rate_limit",
]
