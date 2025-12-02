"""Authentication middleware for FastAPI."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader

from docvector.core import get_logger
from docvector.db import get_db_session
from docvector.models import APIKey, User
from docvector.services.auth_service import AuthService

logger = get_logger(__name__)

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthContext:
    """Authentication context for a request."""

    def __init__(
        self,
        user: Optional[User] = None,
        api_key: Optional[APIKey] = None,
        scopes: list[str] = None,
        organization_id: Optional[UUID] = None,
    ):
        self.user = user
        self.api_key = api_key
        self.scopes = scopes or []
        self.organization_id = organization_id

    @property
    def is_authenticated(self) -> bool:
        """Check if request is authenticated."""
        return self.user is not None or self.api_key is not None

    @property
    def actor_id(self) -> Optional[str]:
        """Get the actor ID for audit logging."""
        if self.user:
            return str(self.user.id)
        if self.api_key:
            return f"api_key:{self.api_key.id}"
        return None

    @property
    def actor_type(self) -> str:
        """Get the actor type for audit logging."""
        if self.user:
            return "user"
        if self.api_key:
            return "api_key"
        return "anonymous"

    def has_scope(self, scope: str) -> bool:
        """Check if the context has a specific scope."""
        if "admin" in self.scopes:
            return True
        return scope in self.scopes

    def require_scope(self, scope: str) -> None:
        """Require a specific scope or raise 403."""
        if not self.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {scope}",
            )


async def get_auth_context(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header),
) -> AuthContext:
    """Get authentication context from request.

    Supports both JWT Bearer tokens and API keys.
    """
    async with get_db_session() as db:
        auth_service = AuthService(db)

        # Try API key first (header: X-API-Key)
        if api_key:
            key_record = await auth_service.validate_api_key(api_key)
            if key_record:
                # Load user if key belongs to a user
                user = None
                if key_record.user_id:
                    user = await auth_service.get_user_by_id(key_record.user_id)

                return AuthContext(
                    user=user,
                    api_key=key_record,
                    scopes=list(key_record.scopes) if key_record.scopes else ["read"],
                    organization_id=key_record.organization_id,
                )

        # Try Bearer token
        if bearer:
            try:
                payload = auth_service.decode_token(bearer.credentials)

                if payload.get("type") != "access":
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token type",
                    )

                user_id = UUID(payload["sub"])
                user = await auth_service.get_user_by_id(user_id)

                if not user or not user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not found or inactive",
                    )

                return AuthContext(
                    user=user,
                    scopes=payload.get("scopes", ["read"]),
                )

            except HTTPException:
                raise
            except Exception as e:
                logger.warning("Token validation failed", error=str(e))
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                )

        # No authentication provided - return anonymous context
        return AuthContext()


async def require_auth(
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Require authentication (user or API key)."""
    if not auth.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth


async def require_user(
    auth: AuthContext = Depends(require_auth),
) -> AuthContext:
    """Require user authentication (not just API key)."""
    if not auth.user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User authentication required",
        )
    return auth


async def require_admin(
    auth: AuthContext = Depends(require_user),
) -> AuthContext:
    """Require admin user."""
    if not auth.user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return auth


def require_scope(scope: str):
    """Create a dependency that requires a specific scope."""
    async def check_scope(auth: AuthContext = Depends(require_auth)) -> AuthContext:
        auth.require_scope(scope)
        return auth
    return check_scope


# Pre-built scope dependencies
require_read = require_scope("read")
require_write = require_scope("write")
