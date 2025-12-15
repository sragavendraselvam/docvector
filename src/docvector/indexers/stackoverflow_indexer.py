"""StackOverflow data indexer.

Imports Q&A data from StackOverflow data dumps or API.

Data Sources:
1. Data Dump: https://archive.org/details/stackexchange (quarterly releases)
2. API: https://api.stackexchange.com/2.3/
3. Data Explorer: https://data.stackexchange.com/

Usage:
    # From API (for smaller datasets, specific tags)
    indexer = StackOverflowIndexer(db_session)
    await indexer.import_from_api(tag="python", page_size=100, max_pages=10)

    # From data dump (for large-scale imports)
    await indexer.import_from_dump("/path/to/stackoverflow-Posts.xml")
"""

import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional
from uuid import UUID

import aiohttp

from docvector.core import get_logger
from docvector.services.qa_service import QAService

logger = get_logger(__name__)


class StackOverflowIndexer:
    """Import Q&A from StackOverflow."""

    API_BASE = "https://api.stackexchange.com/2.3"
    SOURCE = "stackoverflow"

    def __init__(self, qa_service: QAService, api_key: Optional[str] = None):
        """Initialize indexer.

        Args:
            qa_service: QAService instance for creating questions/answers
            api_key: Optional StackExchange API key for higher rate limits
        """
        self.qa_service = qa_service
        self.api_key = api_key
        self.stats = {
            "questions_imported": 0,
            "answers_imported": 0,
            "comments_imported": 0,
            "errors": 0,
        }

    async def import_from_api(
        self,
        tag: str,
        page_size: int = 100,
        max_pages: int = 10,
        min_score: int = 1,
        has_accepted_answer: bool = True,
    ) -> Dict:
        """Import questions from StackOverflow API.

        Args:
            tag: Tag to filter questions (e.g., 'python', 'react')
            page_size: Number of questions per API page
            max_pages: Maximum number of pages to fetch
            min_score: Minimum question score
            has_accepted_answer: Only import questions with accepted answers

        Returns:
            Stats dictionary
        """
        logger.info(
            "Starting StackOverflow API import",
            tag=tag,
            page_size=page_size,
            max_pages=max_pages,
        )

        params = {
            "site": "stackoverflow",
            "tagged": tag,
            "sort": "votes",
            "order": "desc",
            "pagesize": page_size,
            "filter": "withbody",  # Include body content
        }

        if self.api_key:
            params["key"] = self.api_key

        async with aiohttp.ClientSession() as session:
            for page in range(1, max_pages + 1):
                params["page"] = page
                url = f"{self.API_BASE}/questions"

                try:
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            questions = data.get("items", [])

                            if not questions:
                                logger.info("No more questions to import", page=page)
                                break

                            for q in questions:
                                # Filter by score
                                if q.get("score", 0) < min_score:
                                    continue

                                # Filter by accepted answer
                                if has_accepted_answer and not q.get("accepted_answer_id"):
                                    continue

                                await self._import_question(session, q, tag)

                            # Check if there are more pages
                            if not data.get("has_more"):
                                break

                            # Rate limiting
                            await asyncio.sleep(0.5)
                        else:
                            logger.error("API request failed", status=resp.status, page=page)
                            self.stats["errors"] += 1

                except Exception as e:
                    logger.error("Error fetching page", page=page, error=str(e))
                    self.stats["errors"] += 1

        logger.info("StackOverflow API import complete", stats=self.stats)
        return self.stats

    async def _import_question(
        self,
        session: aiohttp.ClientSession,
        q_data: Dict,
        library_name: str,
    ) -> None:
        """Import a single question with its answers."""
        try:
            question_id = str(q_data["question_id"])
            title = q_data.get("title", "")
            body = q_data.get("body", "")
            score = q_data.get("score", 0)
            creation_date = datetime.fromtimestamp(q_data.get("creation_date", 0))
            is_answered = q_data.get("is_answered", False)
            accepted_answer_id = q_data.get("accepted_answer_id")
            tags = q_data.get("tags", [])
            link = q_data.get("link", f"https://stackoverflow.com/q/{question_id}")

            # Create question
            question = await self.qa_service.create_question(
                title=title,
                body=body,
                author_id=f"so_user_{q_data.get('owner', {}).get('user_id', 'unknown')}",
                author_type="external",
                library_name=library_name,
                tags=tags,
                source=self.SOURCE,
                source_id=question_id,
                source_url=link,
                metadata={
                    "score": score,
                    "view_count": q_data.get("view_count", 0),
                    "creation_date": creation_date.isoformat(),
                    "is_answered": is_answered,
                },
            )

            self.stats["questions_imported"] += 1
            logger.debug("Imported question", source_id=question_id, title=title[:50])

            # Fetch and import answers
            await self._import_answers(session, question.id, question_id, accepted_answer_id)

        except Exception as e:
            logger.error("Error importing question", question_id=q_data.get("question_id"), error=str(e))
            self.stats["errors"] += 1

    async def _import_answers(
        self,
        session: aiohttp.ClientSession,
        question_uuid: UUID,
        so_question_id: str,
        accepted_answer_id: Optional[int],
    ) -> None:
        """Import answers for a question."""
        params = {
            "site": "stackoverflow",
            "sort": "votes",
            "order": "desc",
            "filter": "withbody",
        }

        if self.api_key:
            params["key"] = self.api_key

        url = f"{self.API_BASE}/questions/{so_question_id}/answers"

        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    answers = data.get("items", [])

                    for a in answers:
                        answer_id = str(a["answer_id"])
                        body = a.get("body", "")
                        score = a.get("score", 0)
                        is_accepted = a.get("answer_id") == accepted_answer_id
                        link = f"https://stackoverflow.com/a/{answer_id}"

                        await self.qa_service.create_answer(
                            question_id=question_uuid,
                            body=body,
                            author_id=f"so_user_{a.get('owner', {}).get('user_id', 'unknown')}",
                            author_type="external",
                            source=self.SOURCE,
                            source_id=answer_id,
                            source_url=link,
                            is_accepted=is_accepted,
                            metadata={
                                "score": score,
                                "creation_date": datetime.fromtimestamp(a.get("creation_date", 0)).isoformat(),
                            },
                        )

                        self.stats["answers_imported"] += 1
                        logger.debug("Imported answer", source_id=answer_id)

        except Exception as e:
            logger.error("Error importing answers", so_question_id=so_question_id, error=str(e))
            self.stats["errors"] += 1

    async def import_from_dump(
        self,
        posts_file: str,
        library_name: str,
        max_questions: int = 10000,
        min_score: int = 5,
    ) -> Dict:
        """Import from StackOverflow data dump XML.

        The data dump can be downloaded from:
        https://archive.org/details/stackexchange

        Args:
            posts_file: Path to Posts.xml file
            library_name: Library name to associate with questions
            max_questions: Maximum questions to import
            min_score: Minimum score threshold

        Returns:
            Stats dictionary
        """
        logger.info(
            "Starting StackOverflow dump import",
            posts_file=posts_file,
            max_questions=max_questions,
        )

        posts_path = Path(posts_file)
        if not posts_path.exists():
            raise FileNotFoundError(f"Posts file not found: {posts_file}")

        # Parse XML incrementally for memory efficiency
        question_map = {}  # Map SO question ID to our UUID
        count = 0

        for event, elem in ET.iterparse(posts_path, events=["end"]):
            if elem.tag != "row":
                continue

            post_type = elem.get("PostTypeId")

            # PostTypeId: 1 = Question, 2 = Answer
            if post_type == "1":  # Question
                score = int(elem.get("Score", "0"))
                if score < min_score:
                    elem.clear()
                    continue

                if count >= max_questions:
                    break

                try:
                    question = await self._import_question_from_xml(elem, library_name)
                    if question:
                        question_map[elem.get("Id")] = question.id
                        count += 1
                except Exception as e:
                    logger.error("Error importing question from dump", error=str(e))
                    self.stats["errors"] += 1

            elif post_type == "2":  # Answer
                parent_id = elem.get("ParentId")
                if parent_id in question_map:
                    try:
                        await self._import_answer_from_xml(elem, question_map[parent_id])
                    except Exception as e:
                        logger.error("Error importing answer from dump", error=str(e))
                        self.stats["errors"] += 1

            elem.clear()

        logger.info("StackOverflow dump import complete", stats=self.stats)
        return self.stats

    async def _import_question_from_xml(self, elem, library_name: str) -> Optional:
        """Import a question from XML element."""
        question_id = elem.get("Id")
        title = elem.get("Title", "")
        body = elem.get("Body", "")
        score = int(elem.get("Score", "0"))
        tags_str = elem.get("Tags", "")
        creation_date = elem.get("CreationDate", "")
        accepted_answer_id = elem.get("AcceptedAnswerId")

        # Parse tags from format: <tag1><tag2><tag3>
        tags = [t for t in tags_str.replace("<", " ").replace(">", " ").split() if t]

        question = await self.qa_service.create_question(
            title=title,
            body=body,
            author_id=f"so_user_{elem.get('OwnerUserId', 'unknown')}",
            author_type="external",
            library_name=library_name,
            tags=tags[:5],  # Limit to 5 tags
            source=self.SOURCE,
            source_id=question_id,
            source_url=f"https://stackoverflow.com/q/{question_id}",
            metadata={
                "score": score,
                "view_count": int(elem.get("ViewCount", "0")),
                "creation_date": creation_date,
                "accepted_answer_id": accepted_answer_id,
            },
        )

        self.stats["questions_imported"] += 1
        return question

    async def _import_answer_from_xml(self, elem, question_uuid: UUID) -> None:
        """Import an answer from XML element."""
        answer_id = elem.get("Id")
        body = elem.get("Body", "")
        score = int(elem.get("Score", "0"))
        creation_date = elem.get("CreationDate", "")

        # Check if this is the accepted answer
        # Note: This would need the accepted_answer_id from the question
        is_accepted = False

        await self.qa_service.create_answer(
            question_id=question_uuid,
            body=body,
            author_id=f"so_user_{elem.get('OwnerUserId', 'unknown')}",
            author_type="external",
            source=self.SOURCE,
            source_id=answer_id,
            source_url=f"https://stackoverflow.com/a/{answer_id}",
            is_accepted=is_accepted,
            metadata={
                "score": score,
                "creation_date": creation_date,
            },
        )

        self.stats["answers_imported"] += 1
