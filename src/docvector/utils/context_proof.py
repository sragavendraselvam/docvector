"""Context-based proof system for Q&A operations.

Instead of cryptographic proof-of-work, agents provide context explaining
their reasoning for actions (create, upvote, comment). The system validates
that the context is genuine and not spam.

This approach is:
1. More practical - no computational overhead
2. More meaningful - captures the "why" behind actions
3. Easier to audit - human-readable context
4. Better for AI agents - natural language reasoning
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from docvector.core import get_logger

logger = get_logger(__name__)


@dataclass
class ContextProofConfig:
    """Configuration for context proof validation."""

    # Minimum context length by action type
    MIN_LENGTH_QUESTION = 50  # Must explain what you're asking
    MIN_LENGTH_ANSWER = 100   # Must explain your solution reasoning
    MIN_LENGTH_COMMENT = 20   # Brief clarification is OK
    MIN_LENGTH_UPVOTE = 30    # Brief reason why this is helpful
    MIN_LENGTH_DOWNVOTE = 50  # Must explain why it's wrong/unhelpful

    # Keywords that suggest spam
    SPAM_KEYWORDS = [
        "buy now", "click here", "free money", "casino", "crypto pump",
        "follow me", "subscribe", "dm me", "contact whatsapp",
    ]

    # Keywords that suggest low-quality context
    LOW_QUALITY_PATTERNS = [
        r"^(good|nice|thanks|ok|great|awesome)\.?$",  # Too generic
        r"^(this|it|that)$",  # Meaningless
        r"^(.)\1{5,}$",  # Repeated characters
    ]


class ContextProof:
    """Context-based proof validation for Q&A actions."""

    @staticmethod
    def validate_question_context(
        title: str,
        body: str,
        context: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate context for creating a question.

        The context should explain:
        - What problem you're trying to solve
        - What you've already tried
        - Why existing docs/answers don't help

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check minimum length
        if len(context) < ContextProofConfig.MIN_LENGTH_QUESTION:
            return False, f"Context too short. Please provide at least {ContextProofConfig.MIN_LENGTH_QUESTION} characters explaining your problem."

        # Check for spam
        if ContextProof._contains_spam(context):
            return False, "Context contains spam-like content."

        # Check for low-quality patterns
        if ContextProof._is_low_quality(context):
            return False, "Context is too generic. Please explain your specific situation."

        # Check context relates to title/body
        if not ContextProof._context_relates_to_content(context, title + " " + body):
            return False, "Context should relate to your question. Please explain your specific problem."

        return True, None

    @staticmethod
    def validate_answer_context(
        question_title: str,
        answer_body: str,
        context: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate context for creating an answer.

        The context should explain:
        - How you arrived at this solution
        - Why this approach works
        - Any testing/verification done

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check minimum length
        if len(context) < ContextProofConfig.MIN_LENGTH_ANSWER:
            return False, f"Context too short. Please provide at least {ContextProofConfig.MIN_LENGTH_ANSWER} characters explaining your reasoning."

        # Check for spam
        if ContextProof._contains_spam(context):
            return False, "Context contains spam-like content."

        # Check for low-quality patterns
        if ContextProof._is_low_quality(context):
            return False, "Context is too generic. Please explain how you arrived at this solution."

        # Check context mentions something about the approach/solution
        solution_keywords = ["because", "since", "works", "tested", "tried", "solution", "approach", "fix", "resolve"]
        has_reasoning = any(kw in context.lower() for kw in solution_keywords)
        if not has_reasoning:
            return False, "Please explain why this answer solves the problem."

        return True, None

    @staticmethod
    def validate_vote_context(
        target_content: str,
        vote_value: int,
        context: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate context for voting.

        For upvotes: Why is this helpful/correct?
        For downvotes: Why is this unhelpful/incorrect?

        Returns:
            Tuple of (is_valid, error_message)
        """
        min_length = (
            ContextProofConfig.MIN_LENGTH_DOWNVOTE if vote_value < 0
            else ContextProofConfig.MIN_LENGTH_UPVOTE
        )

        # Check minimum length
        if len(context) < min_length:
            action = "downvote" if vote_value < 0 else "upvote"
            return False, f"Please explain why you're {action}ing this (at least {min_length} characters)."

        # Check for spam
        if ContextProof._contains_spam(context):
            return False, "Context contains spam-like content."

        # Check for low-quality patterns
        if ContextProof._is_low_quality(context):
            return False, "Please provide a specific reason for your vote."

        # For downvotes, require explanation of what's wrong
        if vote_value < 0:
            negative_keywords = ["wrong", "incorrect", "doesn't work", "outdated", "misleading", "harmful", "spam", "off-topic"]
            has_reason = any(kw in context.lower() for kw in negative_keywords)
            if not has_reason:
                return False, "Please explain what's wrong with this content."

        return True, None

    @staticmethod
    def validate_comment_context(
        target_content: str,
        comment_body: str,
        context: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate context for adding a comment.

        The context should explain:
        - Why you're adding this comment
        - What clarification/addition you're providing

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check minimum length
        if len(context) < ContextProofConfig.MIN_LENGTH_COMMENT:
            return False, f"Please explain why you're adding this comment (at least {ContextProofConfig.MIN_LENGTH_COMMENT} characters)."

        # Check for spam
        if ContextProof._contains_spam(context):
            return False, "Context contains spam-like content."

        return True, None

    @staticmethod
    def _contains_spam(text: str) -> bool:
        """Check if text contains spam keywords."""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in ContextProofConfig.SPAM_KEYWORDS)

    @staticmethod
    def _is_low_quality(text: str) -> bool:
        """Check if text matches low-quality patterns."""
        text_clean = text.strip().lower()
        for pattern in ContextProofConfig.LOW_QUALITY_PATTERNS:
            if re.match(pattern, text_clean):
                return True
        return False

    @staticmethod
    def _context_relates_to_content(context: str, content: str) -> bool:
        """Check if context has some relation to the content."""
        # Extract meaningful words from content
        content_words = set(
            word.lower() for word in re.findall(r'\b\w{4,}\b', content)
        )
        context_words = set(
            word.lower() for word in re.findall(r'\b\w{4,}\b', context)
        )

        # At least some overlap expected
        overlap = content_words & context_words
        return len(overlap) >= 1  # At least one shared word

    @staticmethod
    def generate_context_template(action: str) -> dict:
        """
        Generate a template/guide for providing context.

        Returns:
            Dictionary with template and examples
        """
        templates = {
            "question": {
                "description": "Explain what you're trying to do and what you've already tried",
                "fields": {
                    "problem": "What problem are you trying to solve?",
                    "tried": "What have you already tried?",
                    "expected": "What result do you expect?",
                },
                "example": "I'm trying to implement user authentication in FastAPI. I've read the OAuth2 docs but I'm confused about how to handle refresh tokens. The docs show access tokens but don't cover token refresh flow.",
            },
            "answer": {
                "description": "Explain how you arrived at this solution",
                "fields": {
                    "approach": "Why does this approach work?",
                    "verification": "How did you verify this solution?",
                    "caveats": "Any limitations or edge cases?",
                },
                "example": "This works because FastAPI's Depends() creates a new dependency instance per request. I tested this with a sample app and verified tokens are properly refreshed. Note: This assumes you're using the default JWT handler.",
            },
            "upvote": {
                "description": "Explain why this is helpful",
                "fields": {
                    "reason": "Why is this answer/question helpful?",
                },
                "example": "This answer solved my exact problem with database connection pooling. The explanation of connection lifecycle was particularly helpful.",
            },
            "downvote": {
                "description": "Explain what's wrong or misleading",
                "fields": {
                    "issue": "What's incorrect or misleading?",
                    "suggestion": "How could it be improved?",
                },
                "example": "This solution is outdated and doesn't work with the current version. The API changed in v2.0 and this method is now deprecated.",
            },
            "comment": {
                "description": "Explain why you're adding this clarification",
                "fields": {
                    "purpose": "What are you clarifying or adding?",
                },
                "example": "Adding a note that this also works for PostgreSQL, not just MySQL as shown in the example.",
            },
        }

        return templates.get(action, {
            "description": "Explain your reasoning",
            "fields": {"reason": "Why are you taking this action?"},
            "example": "",
        })
