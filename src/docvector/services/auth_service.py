"""Authentication service - JWT tokens, API keys, and session management."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID, uuid4

import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from docvector.core import DocVectorException, get_logger, settings
from docvector.models import APIKey, User, UserSession, Organization, AuditLog

logger = get_logger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings (can be moved to core.py settings)
JWT_SECRET_KEY = settings.cloud_api_key or "docvector-jwt-secret-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 30


class AuthService:
    """Service for authentication operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ============ Password Hashing ============

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash."""
        return pwd_context.verify(plain_password, hashed_password)

    # ============ API Key Hashing ============

    @staticmethod
    def generate_api_key() -> Tuple[str, str, str]:
        """Generate a new API key.

        Returns:
            Tuple of (full_key, key_prefix, key_hash)
        """
        # Generate a secure random key: dv_sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        random_part = secrets.token_hex(24)  # 48 chars
        full_key = f"dv_sk_{random_part}"
        key_prefix = full_key[:12]  # "dv_sk_xxxx"
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        return full_key, key_prefix, key_hash

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash an API key for storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    # ============ JWT Tokens ============

    def create_access_token(
        self,
        user_id: UUID,
        email: str,
        scopes: list[str] = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a JWT access token."""
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

        payload = {
            "sub": str(user_id),
            "email": email,
            "scopes": scopes or ["read"],
            "type": "access",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid4()),  # JWT ID for revocation
        }

        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    def create_refresh_token(
        self,
        user_id: UUID,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a JWT refresh token."""
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)

        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid4()),
        }

        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    def decode_token(self, token: str) -> dict:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            raise DocVectorException(
                code="TOKEN_EXPIRED",
                message="Token has expired",
            )
        except jwt.InvalidTokenError as e:
            raise DocVectorException(
                code="INVALID_TOKEN",
                message=f"Invalid token: {str(e)}",
            )

    # ============ User Operations ============

    async def create_user(
        self,
        email: str,
        password: Optional[str] = None,
        username: Optional[str] = None,
        display_name: Optional[str] = None,
        account_type: str = "user",
    ) -> User:
        """Create a new user."""
        # Check if email already exists
        existing = await self.session.scalar(
            select(User).where(User.email == email)
        )
        if existing:
            raise DocVectorException(
                code="EMAIL_EXISTS",
                message="A user with this email already exists",
            )

        # Check if username already exists
        if username:
            existing = await self.session.scalar(
                select(User).where(User.username == username)
            )
            if existing:
                raise DocVectorException(
                    code="USERNAME_EXISTS",
                    message="A user with this username already exists",
                )

        user = User(
            email=email,
            password_hash=self.hash_password(password) if password else None,
            username=username,
            display_name=display_name or username or email.split("@")[0],
            account_type=account_type,
        )

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        logger.info("User created", user_id=str(user.id), email=email)
        return user

    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get a user by ID."""
        return await self.session.get(User, user_id)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        return await self.session.scalar(
            select(User).where(User.email == email)
        )

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user with email and password."""
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not user.password_hash:
            return None
        if not self.verify_password(password, user.password_hash):
            return None
        if not user.is_active:
            return None
        return user

    async def login(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[User, str, str]:
        """Login a user and create tokens.

        Returns:
            Tuple of (user, access_token, refresh_token)
        """
        user = await self.authenticate_user(email, password)
        if not user:
            # Log failed attempt
            await self._log_audit(
                actor_type="anonymous",
                actor_id=email,
                action="login_failed",
                ip_address=ip_address,
                user_agent=user_agent,
                status="failure",
                error_message="Invalid credentials",
            )
            raise DocVectorException(
                code="INVALID_CREDENTIALS",
                message="Invalid email or password",
            )

        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        await self.session.commit()

        # Create tokens
        access_token = self.create_access_token(user.id, user.email)
        refresh_token = self.create_refresh_token(user.id)

        # Create session
        await self._create_session(
            user_id=user.id,
            token=refresh_token,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Log successful login
        await self._log_audit(
            actor_type="user",
            actor_id=str(user.id),
            action="login",
            ip_address=ip_address,
            user_agent=user_agent,
        )

        logger.info("User logged in", user_id=str(user.id), email=email)
        return user, access_token, refresh_token

    async def refresh_access_token(self, refresh_token: str) -> Tuple[str, str]:
        """Refresh an access token using a refresh token.

        Returns:
            Tuple of (new_access_token, new_refresh_token)
        """
        payload = self.decode_token(refresh_token)

        if payload.get("type") != "refresh":
            raise DocVectorException(
                code="INVALID_TOKEN_TYPE",
                message="Expected refresh token",
            )

        user_id = UUID(payload["sub"])
        user = await self.get_user_by_id(user_id)

        if not user or not user.is_active:
            raise DocVectorException(
                code="USER_NOT_FOUND",
                message="User not found or inactive",
            )

        # Create new tokens
        access_token = self.create_access_token(user.id, user.email)
        new_refresh_token = self.create_refresh_token(user.id)

        return access_token, new_refresh_token

    # ============ API Key Operations ============

    async def create_api_key(
        self,
        name: str,
        user_id: Optional[UUID] = None,
        organization_id: Optional[UUID] = None,
        scopes: list[str] = None,
        rate_limit_per_second: int = 5,
        rate_limit_per_day: Optional[int] = None,
        expires_at: Optional[datetime] = None,
    ) -> Tuple[APIKey, str]:
        """Create a new API key.

        Returns:
            Tuple of (api_key_model, full_key_string)
            NOTE: full_key_string is only returned once!
        """
        if not user_id and not organization_id:
            raise DocVectorException(
                code="INVALID_OWNER",
                message="API key must belong to a user or organization",
            )

        full_key, key_prefix, key_hash = self.generate_api_key()

        api_key = APIKey(
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            user_id=user_id,
            organization_id=organization_id,
            scopes=scopes or ["read"],
            rate_limit_per_second=rate_limit_per_second,
            rate_limit_per_day=rate_limit_per_day,
            expires_at=expires_at,
        )

        self.session.add(api_key)
        await self.session.commit()
        await self.session.refresh(api_key)

        logger.info("API key created", key_id=str(api_key.id), name=name, prefix=key_prefix)
        return api_key, full_key

    async def validate_api_key(self, api_key: str) -> Optional[APIKey]:
        """Validate an API key and return the key record."""
        key_hash = self.hash_api_key(api_key)

        key_record = await self.session.scalar(
            select(APIKey).where(APIKey.key_hash == key_hash)
        )

        if not key_record:
            return None

        # Check if active
        if not key_record.is_active:
            return None

        # Check if revoked
        if key_record.revoked_at:
            return None

        # Check if expired
        if key_record.expires_at and key_record.expires_at < datetime.now(timezone.utc):
            return None

        # Update last used
        key_record.last_used_at = datetime.now(timezone.utc)
        key_record.total_requests += 1
        key_record.requests_today += 1
        await self.session.commit()

        return key_record

    async def revoke_api_key(self, key_id: UUID) -> bool:
        """Revoke an API key."""
        key_record = await self.session.get(APIKey, key_id)
        if not key_record:
            return False

        key_record.is_active = False
        key_record.revoked_at = datetime.now(timezone.utc)
        await self.session.commit()

        logger.info("API key revoked", key_id=str(key_id))
        return True

    async def list_api_keys(
        self,
        user_id: Optional[UUID] = None,
        organization_id: Optional[UUID] = None,
    ) -> list[APIKey]:
        """List API keys for a user or organization."""
        query = select(APIKey)

        if user_id:
            query = query.where(APIKey.user_id == user_id)
        if organization_id:
            query = query.where(APIKey.organization_id == organization_id)

        query = query.where(APIKey.revoked_at.is_(None))
        query = query.order_by(APIKey.created_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    # ============ Session Operations ============

    async def _create_session(
        self,
        user_id: UUID,
        token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserSession:
        """Create a user session."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)

        session_record = UserSession(
            user_id=user_id,
            token_hash=token_hash,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )

        self.session.add(session_record)
        await self.session.commit()

        return session_record

    async def revoke_session(self, session_id: UUID) -> bool:
        """Revoke a user session."""
        session_record = await self.session.get(UserSession, session_id)
        if not session_record:
            return False

        session_record.is_active = False
        session_record.revoked_at = datetime.now(timezone.utc)
        await self.session.commit()

        return True

    async def revoke_all_sessions(self, user_id: UUID) -> int:
        """Revoke all sessions for a user."""
        result = await self.session.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.is_active == True,
            )
        )
        sessions = result.scalars().all()

        count = 0
        for session_record in sessions:
            session_record.is_active = False
            session_record.revoked_at = datetime.now(timezone.utc)
            count += 1

        await self.session.commit()
        return count

    # ============ Audit Logging ============

    async def _log_audit(
        self,
        actor_type: str,
        actor_id: str,
        action: str,
        organization_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        changes: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> AuditLog:
        """Log an audit event."""
        audit = AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            organization_id=organization_id,
            resource_type=resource_type,
            resource_id=resource_id,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            error_message=error_message,
        )

        self.session.add(audit)
        await self.session.commit()

        return audit
