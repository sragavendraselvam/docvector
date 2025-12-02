"""Auth API schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ============ User Schemas ============


class UserCreate(BaseModel):
    """Schema for creating a user."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    display_name: Optional[str] = Field(None, max_length=255)


class UserResponse(BaseModel):
    """Schema for user response."""

    id: UUID
    email: str
    username: Optional[str]
    display_name: Optional[str]
    avatar_url: Optional[str]
    account_type: str
    is_active: bool
    email_verified: bool
    reputation: int
    questions_count: int
    answers_count: int
    accepted_answers_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    username: Optional[str] = Field(None, min_length=3, max_length=100)
    display_name: Optional[str] = Field(None, max_length=255)
    avatar_url: Optional[str] = None


# ============ Auth Schemas ============


class LoginRequest(BaseModel):
    """Schema for login request."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Schema for token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600  # seconds


class RefreshRequest(BaseModel):
    """Schema for refresh token request."""

    refresh_token: str


class PasswordChangeRequest(BaseModel):
    """Schema for password change."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ============ API Key Schemas ============


class APIKeyCreate(BaseModel):
    """Schema for creating an API key."""

    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default=["read"])
    rate_limit_per_second: int = Field(default=5, ge=1, le=100)
    rate_limit_per_day: Optional[int] = Field(default=None, ge=100, le=1000000)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)


class APIKeyResponse(BaseModel):
    """Schema for API key response (without full key)."""

    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    rate_limit_per_second: int
    rate_limit_per_day: Optional[int]
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    total_requests: int
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreatedResponse(BaseModel):
    """Schema for newly created API key (includes full key - shown only once)."""

    id: UUID
    name: str
    key: str  # Full key - only shown once!
    key_prefix: str
    scopes: list[str]
    rate_limit_per_second: int
    rate_limit_per_day: Optional[int]
    expires_at: Optional[datetime]
    created_at: datetime
    warning: str = "Store this key securely. It will not be shown again."


# ============ Organization Schemas ============


class OrganizationCreate(BaseModel):
    """Schema for creating an organization."""

    slug: str = Field(min_length=3, max_length=100, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    website_url: Optional[str] = None


class OrganizationResponse(BaseModel):
    """Schema for organization response."""

    id: UUID
    slug: str
    name: str
    description: Optional[str]
    logo_url: Optional[str]
    website_url: Optional[str]
    plan: str
    plan_expires_at: Optional[datetime]
    max_members: int
    max_api_keys: int
    max_sources: int
    max_documents: int
    max_queries_per_day: int
    current_members: int
    current_sources: int
    current_documents: int
    queries_today: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class OrganizationUpdate(BaseModel):
    """Schema for updating an organization."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    logo_url: Optional[str] = None
    website_url: Optional[str] = None


class OrgMemberResponse(BaseModel):
    """Schema for organization member."""

    user_id: UUID
    email: str
    username: Optional[str]
    display_name: Optional[str]
    role: str
    joined_at: Optional[datetime]


class OrgInviteRequest(BaseModel):
    """Schema for inviting a member."""

    email: EmailStr
    role: str = Field(default="member", pattern=r"^(admin|member|viewer)$")
