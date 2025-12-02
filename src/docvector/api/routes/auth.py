"""Auth API routes."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from docvector.api.middleware.auth import (
    AuthContext,
    get_auth_context,
    require_auth,
    require_user,
)
from docvector.api.schemas.auth import (
    APIKeyCreate,
    APIKeyCreatedResponse,
    APIKeyResponse,
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from docvector.core import DocVectorException, get_logger
from docvector.db import get_db_session
from docvector.services.auth_service import AuthService

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ============ Registration & Login ============


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    data: UserCreate,
):
    """Register a new user account."""
    async with get_db_session() as db:
        auth_service = AuthService(db)

        try:
            user = await auth_service.create_user(
                email=data.email,
                password=data.password,
                username=data.username,
                display_name=data.display_name,
            )
            return user
        except DocVectorException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message,
            )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    data: LoginRequest,
):
    """Login with email and password."""
    async with get_db_session() as db:
        auth_service = AuthService(db)

        try:
            user, access_token, refresh_token = await auth_service.login(
                email=data.email,
                password=data.password,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
            )
        except DocVectorException as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=e.message,
            )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshRequest,
):
    """Refresh access token using refresh token."""
    async with get_db_session() as db:
        auth_service = AuthService(db)

        try:
            access_token, new_refresh_token = await auth_service.refresh_access_token(
                data.refresh_token
            )
            return TokenResponse(
                access_token=access_token,
                refresh_token=new_refresh_token,
            )
        except DocVectorException as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=e.message,
            )


@router.post("/logout")
async def logout(
    auth: AuthContext = Depends(require_user),
):
    """Logout and revoke all sessions."""
    async with get_db_session() as db:
        auth_service = AuthService(db)
        count = await auth_service.revoke_all_sessions(auth.user.id)
        return {"message": f"Logged out, revoked {count} sessions"}


# ============ Current User ============


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    auth: AuthContext = Depends(require_user),
):
    """Get current user profile."""
    return auth.user


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    data: UserUpdate,
    auth: AuthContext = Depends(require_user),
):
    """Update current user profile."""
    async with get_db_session() as db:
        user = await db.get(type(auth.user), auth.user.id)

        if data.username is not None:
            user.username = data.username
        if data.display_name is not None:
            user.display_name = data.display_name
        if data.avatar_url is not None:
            user.avatar_url = data.avatar_url

        user.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(user)

        return user


@router.post("/me/change-password")
async def change_password(
    data: PasswordChangeRequest,
    auth: AuthContext = Depends(require_user),
):
    """Change current user's password."""
    async with get_db_session() as db:
        auth_service = AuthService(db)

        # Verify current password
        if not auth_service.verify_password(data.current_password, auth.user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        # Update password
        user = await db.get(type(auth.user), auth.user.id)
        user.password_hash = auth_service.hash_password(data.new_password)
        user.updated_at = datetime.now(timezone.utc)
        await db.commit()

        # Revoke all sessions (force re-login)
        await auth_service.revoke_all_sessions(auth.user.id)

        return {"message": "Password changed successfully. Please login again."}


# ============ API Keys ============


@router.get("/api-keys", response_model=list[APIKeyResponse])
async def list_api_keys(
    auth: AuthContext = Depends(require_user),
):
    """List all API keys for current user."""
    async with get_db_session() as db:
        auth_service = AuthService(db)
        keys = await auth_service.list_api_keys(user_id=auth.user.id)
        return keys


@router.post("/api-keys", response_model=APIKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: APIKeyCreate,
    auth: AuthContext = Depends(require_user),
):
    """Create a new API key.

    WARNING: The full key is only shown once in this response.
    Store it securely!
    """
    async with get_db_session() as db:
        auth_service = AuthService(db)

        expires_at = None
        if data.expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

        api_key, full_key = await auth_service.create_api_key(
            name=data.name,
            user_id=auth.user.id,
            scopes=data.scopes,
            rate_limit_per_second=data.rate_limit_per_second,
            rate_limit_per_day=data.rate_limit_per_day,
            expires_at=expires_at,
        )

        return APIKeyCreatedResponse(
            id=api_key.id,
            name=api_key.name,
            key=full_key,
            key_prefix=api_key.key_prefix,
            scopes=list(api_key.scopes) if api_key.scopes else [],
            rate_limit_per_second=api_key.rate_limit_per_second,
            rate_limit_per_day=api_key.rate_limit_per_day,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
        )


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: UUID,
    auth: AuthContext = Depends(require_user),
):
    """Revoke an API key."""
    async with get_db_session() as db:
        from docvector.models import APIKey

        # Verify ownership
        api_key = await db.get(APIKey, key_id)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )
        if api_key.user_id != auth.user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to revoke this key",
            )

        auth_service = AuthService(db)
        await auth_service.revoke_api_key(key_id)

        return {"message": "API key revoked"}


# ============ Auth Status ============


@router.get("/status")
async def get_auth_status(
    auth: AuthContext = Depends(get_auth_context),
):
    """Get current authentication status."""
    return {
        "authenticated": auth.is_authenticated,
        "actor_type": auth.actor_type,
        "actor_id": auth.actor_id,
        "scopes": auth.scopes,
        "user": {
            "id": str(auth.user.id),
            "email": auth.user.email,
            "username": auth.user.username,
        } if auth.user else None,
        "api_key": {
            "id": str(auth.api_key.id),
            "name": auth.api_key.name,
            "prefix": auth.api_key.key_prefix,
        } if auth.api_key else None,
    }
