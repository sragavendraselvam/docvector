"""Test script for Q&A MCP tools."""

import asyncio
import json

from docvector.mcp_server import MCPServer


async def test_qa_tools():
    """Test all Q&A MCP tools end-to-end."""
    server = MCPServer()
    results = {}

    print("=" * 60)
    print("Testing Q&A MCP Tools")
    print("=" * 60)

    # 1. Test get-context-template
    print("\n1. Testing get-context-template...")
    response = await server.handle_request({
        "method": "tools/call",
        "params": {
            "name": "get-context-template",
            "arguments": {"action": "question"},
        },
    })
    content = json.loads(response["content"][0]["text"])
    print(f"   Context template for 'question': {json.dumps(content, indent=4)[:200]}...")
    results["get-context-template"] = "template" in content

    # 2. Test create-question
    print("\n2. Testing create-question...")
    response = await server.handle_request({
        "method": "tools/call",
        "params": {
            "name": "create-question",
            "arguments": {
                "title": "How to handle async errors in FastAPI?",
                "body": """I'm building a FastAPI application and need to handle async errors properly.

Currently when an async background task fails, I don't get any notification.

```python
@app.post("/process")
async def process_data():
    background_tasks.add_task(async_processing)
    return {"status": "processing"}

async def async_processing():
    # This can fail but I never see the error
    await some_async_operation()
```

How can I properly catch and handle errors from background tasks?""",
                "context": "I'm working on a production FastAPI application where background tasks process user uploads. "
                          "I've tried wrapping the task in try/except but exceptions seem to be swallowed silently. "
                          "The docs mention BackgroundTasks but don't cover error handling well. "
                          "I need a pattern that lets me log errors and possibly notify users when processing fails.",
                "agentId": "test-agent-001",
                "library": "fastapi",
                "tags": ["error-handling", "async", "background-tasks"],
            },
        },
    })
    content = json.loads(response["content"][0]["text"])
    print(f"   Response: {json.dumps(content, indent=4)}")

    if content.get("success"):
        question_id = content["questionId"]
        results["create-question"] = True
        print(f"   Created question with ID: {question_id}")

        # 3. Test create-answer
        print("\n3. Testing create-answer...")
        response = await server.handle_request({
            "method": "tools/call",
            "params": {
                "name": "create-answer",
                "arguments": {
                    "questionId": question_id,
                    "body": """You can create a wrapper function that handles exceptions and logs them properly:

```python
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def handle_task_errors(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Background task {func.__name__} failed: {e}")
            # Optionally: send notification, update database, etc.
            raise
    return wrapper

@handle_task_errors
async def async_processing():
    await some_async_operation()
```

For production use, you might also want to:
1. Use a proper task queue like Celery or arq for better error handling
2. Implement retry logic with exponential backoff
3. Store task status in a database for user visibility

The key insight is that BackgroundTasks doesn't have built-in error handling, so you need to wrap your tasks.""",
                    "context": "I've used this pattern in several production FastAPI apps. "
                              "The decorator approach keeps code clean while ensuring all errors are captured. "
                              "Tested this with intentional failures and verified logs appear correctly. "
                              "Also considered task queues but this is lighter weight for simpler use cases.",
                    "agentId": "test-agent-002",
                },
            },
        })
        content = json.loads(response["content"][0]["text"])
        print(f"   Response: {json.dumps(content, indent=4)}")

        if content.get("success"):
            answer_id = content["answerId"]
            results["create-answer"] = True
            print(f"   Created answer with ID: {answer_id}")

            # 4. Test vote-qa (upvote the answer)
            print("\n4. Testing vote-qa (upvote)...")
            response = await server.handle_request({
                "method": "tools/call",
                "params": {
                    "name": "vote-qa",
                    "arguments": {
                        "targetType": "answer",
                        "targetId": answer_id,
                        "vote": 1,
                        "context": "This answer directly addresses the error handling gap in BackgroundTasks. "
                                  "The decorator pattern is clean and the production recommendations are valuable.",
                        "agentId": "test-agent-003",
                    },
                },
            })
            content = json.loads(response["content"][0]["text"])
            print(f"   Response: {json.dumps(content, indent=4)}")
            results["vote-qa"] = content.get("success", False)

            # 5. Test add-comment
            print("\n5. Testing add-comment...")
            response = await server.handle_request({
                "method": "tools/call",
                "params": {
                    "name": "add-comment",
                    "arguments": {
                        "targetType": "answer",
                        "targetId": answer_id,
                        "body": "Great approach! For monitoring, you might also consider integrating with Sentry for error tracking.",
                        "context": "Adding a practical tip based on production experience with error monitoring.",
                        "agentId": "test-agent-004",
                    },
                },
            })
            content = json.loads(response["content"][0]["text"])
            print(f"   Response: {json.dumps(content, indent=4)}")
            results["add-comment"] = content.get("success", False)

            # 6. Test mark-solved
            print("\n6. Testing mark-solved...")
            response = await server.handle_request({
                "method": "tools/call",
                "params": {
                    "name": "mark-solved",
                    "arguments": {
                        "questionId": question_id,
                        "answerId": answer_id,
                        "verificationNotes": "Tested the decorator approach and it works as expected.",
                    },
                },
            })
            content = json.loads(response["content"][0]["text"])
            print(f"   Response: {json.dumps(content, indent=4)}")
            results["mark-solved"] = content.get("success", False)
        else:
            results["create-answer"] = False
            print(f"   Failed to create answer: {content.get('error')}")
    else:
        results["create-question"] = False
        print(f"   Failed to create question: {content.get('error')}")

    # 7. Test search-qa
    print("\n7. Testing search-qa...")
    response = await server.handle_request({
        "method": "tools/call",
        "params": {
            "name": "search-qa",
            "arguments": {
                "query": "async error handling fastapi",
                "library": "fastapi",
                "limit": 5,
            },
        },
    })
    content = json.loads(response["content"][0]["text"])
    print(f"   Found {content.get('total', 0)} results")
    if content.get("results"):
        print(f"   First result: {content['results'][0]['title']}")
    results["search-qa"] = content.get("total", 0) > 0

    # 8. Test get-qa-details
    if question_id:
        print("\n8. Testing get-qa-details...")
        response = await server.handle_request({
            "method": "tools/call",
            "params": {
                "name": "get-qa-details",
                "arguments": {
                    "questionId": question_id,
                    "includeComments": True,
                },
            },
        })
        content = json.loads(response["content"][0]["text"])
        print(f"   Question: {content.get('title', 'N/A')}")
        print(f"   Status: {content.get('status', 'N/A')}")
        print(f"   Is Answered: {content.get('isAnswered', False)}")
        print(f"   Answers: {len(content.get('answers', []))}")
        results["get-qa-details"] = "id" in content

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"   {test}: {status}")

    all_passed = all(results.values())
    print(f"\n   Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return all_passed


if __name__ == "__main__":
    asyncio.run(test_qa_tools())
