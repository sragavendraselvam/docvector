"""Proof-of-work anti-spam system for Q&A operations.

This module implements a hashcash-style proof-of-work system to prevent spam
while allowing legitimate AI agents to participate in Q&A.
"""

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from docvector.core import DocVectorException, get_logger

logger = get_logger(__name__)


@dataclass
class ProofOfWorkConfig:
    """Configuration for proof-of-work difficulty levels."""

    # Difficulty levels (number of leading zero bits required in hash)
    # Higher = more work required
    DIFFICULTY_VOTE = 16        # ~65K hashes, <1 second
    DIFFICULTY_COMMENT = 18     # ~262K hashes, ~2 seconds
    DIFFICULTY_ANSWER = 20      # ~1M hashes, ~5 seconds
    DIFFICULTY_QUESTION = 22    # ~4M hashes, ~20 seconds

    # Challenge expiry time in seconds
    CHALLENGE_EXPIRY = 300  # 5 minutes

    @classmethod
    def get_difficulty(cls, action: str) -> int:
        """Get difficulty for an action type."""
        difficulties = {
            "vote": cls.DIFFICULTY_VOTE,
            "comment": cls.DIFFICULTY_COMMENT,
            "answer": cls.DIFFICULTY_ANSWER,
            "question": cls.DIFFICULTY_QUESTION,
        }
        return difficulties.get(action, cls.DIFFICULTY_COMMENT)

    @classmethod
    def get_estimated_time(cls, action: str) -> float:
        """Get estimated solve time in seconds for an action."""
        estimates = {
            "vote": 0.5,
            "comment": 2.0,
            "answer": 5.0,
            "question": 20.0,
        }
        return estimates.get(action, 2.0)


class ProofOfWork:
    """Proof-of-work challenge generation and verification."""

    @staticmethod
    def generate_challenge(
        action: str,
        agent_id: str,
        target_id: Optional[str] = None,
    ) -> dict:
        """
        Generate a proof-of-work challenge.

        Args:
            action: Type of action (question, answer, comment, vote)
            agent_id: Identifier of the agent requesting the challenge
            target_id: Optional target ID (e.g., question_id for answers)

        Returns:
            Challenge dictionary with challenge string, difficulty, and expiry
        """
        timestamp = int(time.time())
        target_str = target_id or "new"

        # Create challenge string
        challenge = f"{action}:{target_str}:{agent_id}:{timestamp}"

        difficulty = ProofOfWorkConfig.get_difficulty(action)
        estimated_time = ProofOfWorkConfig.get_estimated_time(action)
        expires_at = timestamp + ProofOfWorkConfig.CHALLENGE_EXPIRY

        logger.debug(
            "Generated PoW challenge",
            action=action,
            agent_id=agent_id,
            difficulty=difficulty,
        )

        return {
            "challenge": challenge,
            "difficulty": difficulty,
            "timestamp": timestamp,
            "expires_at": expires_at,
            "estimated_time_seconds": estimated_time,
        }

    @staticmethod
    def solve(challenge: str, difficulty: int) -> Tuple[str, str]:
        """
        Solve a proof-of-work challenge.

        Args:
            challenge: Challenge string to solve
            difficulty: Number of leading zero bits required

        Returns:
            Tuple of (nonce, hash) that satisfies the difficulty requirement
        """
        # Convert bit difficulty to hex prefix length
        # 4 bits = 1 hex digit
        hex_prefix_len = difficulty // 4
        target = "0" * hex_prefix_len

        nonce = 0
        start_time = time.time()

        while True:
            data = f"{challenge}:{nonce}"
            hash_result = hashlib.sha256(data.encode()).hexdigest()

            if hash_result.startswith(target):
                elapsed = time.time() - start_time
                logger.debug(
                    "PoW solved",
                    nonce=nonce,
                    elapsed_seconds=elapsed,
                    difficulty=difficulty,
                )
                return str(nonce), hash_result

            nonce += 1

            # Safety limit to prevent infinite loops
            if nonce > 100_000_000:
                raise DocVectorException(
                    code="POW_SOLVE_TIMEOUT",
                    message="Failed to solve proof-of-work in reasonable time",
                    details={"challenge": challenge, "difficulty": difficulty},
                )

    @staticmethod
    def verify(
        challenge: str,
        nonce: str,
        hash_result: str,
        difficulty: int,
        expires_at: Optional[int] = None,
    ) -> bool:
        """
        Verify a proof-of-work solution.

        Args:
            challenge: Original challenge string
            nonce: Nonce value found by solver
            hash_result: Hash result claimed by solver
            difficulty: Required difficulty level
            expires_at: Optional expiry timestamp to check

        Returns:
            True if the solution is valid, False otherwise
        """
        # Check expiry if provided
        if expires_at and int(time.time()) > expires_at:
            logger.warning("PoW challenge expired", challenge=challenge)
            return False

        # Verify the hash is correct
        data = f"{challenge}:{nonce}"
        expected_hash = hashlib.sha256(data.encode()).hexdigest()

        if expected_hash != hash_result:
            logger.warning(
                "PoW hash mismatch",
                expected=expected_hash[:16],
                got=hash_result[:16],
            )
            return False

        # Check difficulty requirement
        hex_prefix_len = difficulty // 4
        target = "0" * hex_prefix_len

        if not hash_result.startswith(target):
            logger.warning(
                "PoW difficulty not met",
                required=target,
                got=hash_result[:hex_prefix_len],
            )
            return False

        logger.debug("PoW verified successfully", challenge=challenge)
        return True

    @staticmethod
    def parse_challenge(challenge: str) -> dict:
        """
        Parse a challenge string into its components.

        Args:
            challenge: Challenge string in format "action:target:agent:timestamp"

        Returns:
            Dictionary with parsed components
        """
        parts = challenge.split(":")
        if len(parts) != 4:
            raise DocVectorException(
                code="INVALID_CHALLENGE",
                message="Invalid challenge format",
                details={"challenge": challenge},
            )

        return {
            "action": parts[0],
            "target_id": parts[1] if parts[1] != "new" else None,
            "agent_id": parts[2],
            "timestamp": int(parts[3]),
        }


class RateLimiter:
    """Rate limiting for Q&A actions (in addition to PoW)."""

    # Rate limits per action type
    RATE_LIMITS = {
        "vote": {"per_minute": 10, "per_hour": 100},
        "comment": {"per_minute": 5, "per_hour": 50},
        "answer": {"per_minute": 2, "per_hour": 20},
        "question": {"per_minute": 1, "per_hour": 10},
    }

    def __init__(self):
        # In-memory storage for simplicity; use Redis in production
        self._action_counts: dict = {}

    def check_rate_limit(self, agent_id: str, action: str) -> bool:
        """
        Check if an agent has exceeded rate limits.

        Args:
            agent_id: Agent identifier
            action: Type of action

        Returns:
            True if within limits, False if exceeded
        """
        limits = self.RATE_LIMITS.get(action, {"per_minute": 5, "per_hour": 50})
        now = time.time()
        key = f"{agent_id}:{action}"

        if key not in self._action_counts:
            self._action_counts[key] = []

        # Clean old entries
        self._action_counts[key] = [
            ts for ts in self._action_counts[key]
            if ts > now - 3600  # Keep last hour
        ]

        actions = self._action_counts[key]

        # Check per-minute limit
        recent_minute = sum(1 for ts in actions if ts > now - 60)
        if recent_minute >= limits["per_minute"]:
            logger.warning(
                "Rate limit exceeded (per minute)",
                agent_id=agent_id,
                action=action,
            )
            return False

        # Check per-hour limit
        if len(actions) >= limits["per_hour"]:
            logger.warning(
                "Rate limit exceeded (per hour)",
                agent_id=agent_id,
                action=action,
            )
            return False

        return True

    def record_action(self, agent_id: str, action: str) -> None:
        """Record an action for rate limiting."""
        key = f"{agent_id}:{action}"
        if key not in self._action_counts:
            self._action_counts[key] = []
        self._action_counts[key].append(time.time())
