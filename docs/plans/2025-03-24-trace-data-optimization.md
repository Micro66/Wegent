# Trace Data Optimization - Migration from Tags to Logs

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate large trace data from span attributes (tags) to span events (logs) to reduce storage size and improve query performance.

**Architecture:** Large data like HTTP bodies, tool I/O, and ID lists will be stored in span events (logs) instead of span attributes (tags). Attributes will only contain lightweight metadata (lengths, counts, statuses) for querying.

**Tech Stack:** Python, OpenTelemetry, FastAPI

---

## Background

Currently, large data is stored in span attributes (tags):
- `http.request.body` - Full request body (can be very large with chat messages, code)
- `http.response.body` - Full response body
- `tool.input` / `tool.output` - Tool I/O data
- `document_ids`, `memory.ids` - Large ID lists

**Problem:** Span attributes are indexed and used for queries. Large data in attributes causes:
1. Excessive storage usage
2. Slower query performance
3. Potential truncation by trace backends

**Solution:** Use span events (logs) for large data, keep only lightweight metadata in attributes.

---

## Task 1: Create Helper Function for Large Data Logging

**Files:**
- Create: `shared/telemetry/context/large_data.py`
- Modify: `shared/telemetry/context/__init__.py`
- Test: `shared/tests/telemetry/test_large_data.py`

**Step 1: Create the helper function**

Create `shared/telemetry/context/large_data.py`:

```python
# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Utilities for logging large data to span events instead of attributes.

This module provides functions to store large data (bodies, lists, etc.) in span events
while keeping only lightweight metadata in span attributes for querying.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from shared.telemetry.context.span import add_span_event, set_span_attributes

logger = logging.getLogger(__name__)


def log_large_attribute(
    attribute_name: str,
    data: Any,
    max_attr_length: int = 100,
    max_event_length: int = 10000,
    event_name: Optional[str] = None,
    extra_attributes: Optional[Dict[str, Any]] = None,
) -> None:
    """Log large data to span event, keep only metadata in span attribute.

    This function stores the full data in a span event (log) while only keeping
    lightweight metadata (like length, truncated preview) in span attributes.
    This reduces storage size and improves query performance since attributes
    are indexed but events are not.

    Args:
        attribute_name: Name for the attribute (will store metadata)
        data: The data to log (string, dict, list, etc.)
        max_attr_length: Maximum length for attribute value (default: 100)
        max_event_length: Maximum length for event data (default: 10000)
        event_name: Optional custom event name (default: "large_data:{attribute_name}")
        extra_attributes: Optional additional attributes to set

    Example:
        # Instead of:
        set_span_attribute("http.request.body", large_body)

        # Use:
        log_large_attribute("http.request.body", large_body)
        # Sets attribute: http.request.body.length = 5000
        # Adds event: large_data:http.request.body with full body
    """
    try:
        # Convert data to string
        if isinstance(data, (dict, list)):
            import json

            data_str = json.dumps(data, ensure_ascii=False, default=str)
        else:
            data_str = str(data) if data is not None else ""

        data_length = len(data_str)

        # Build attribute metadata
        attr_metadata: Dict[str, Any] = {
            f"{attribute_name}.length": data_length,
        }

        # Add truncated preview to attribute if data is not empty
        if data_str:
            preview = data_str[:max_attr_length]
            if data_length > max_attr_length:
                preview += f"... [truncated, total: {data_length}]"
            attr_metadata[attribute_name] = preview

        # Add any extra attributes
        if extra_attributes:
            attr_metadata.update(extra_attributes)

        # Set attributes (lightweight metadata only)
        set_span_attributes(attr_metadata)

        # Build event data
        event_data = data_str[:max_event_length] if data_str else ""
        if data_length > max_event_length:
            event_data += f"\n... [truncated, total length: {data_length}]"

        # Add event with full data
        actual_event_name = event_name or f"large_data:{attribute_name}"
        add_span_event(
            actual_event_name,
            attributes={"data": event_data, "original_length": data_length},
        )

    except Exception as e:
        logger.debug(f"Failed to log large attribute {attribute_name}: {e}")
        # Fallback: try to set at least the length
        try:
            set_span_attributes({f"{attribute_name}.length": -1})
        except Exception:
            pass


def log_large_string_list(
    attribute_name: str,
    items: List[str],
    max_attr_items: int = 5,
    max_event_items: int = 1000,
    event_name: Optional[str] = None,
) -> None:
    """Log a large list of strings to span event, keep only count in attribute.

    Args:
        attribute_name: Name for the attribute (will store count and preview)
        items: List of string items
        max_attr_items: Maximum number of items to include in attribute (default: 5)
        max_event_items: Maximum number of items to include in event (default: 1000)
        event_name: Optional custom event name

    Example:
        # Instead of:
        set_span_attribute("document_ids", ",".join(ids))

        # Use:
        log_large_string_list("document_ids", ids)
        # Sets attribute: document_ids.count = 500
        # Adds event: large_data:document_ids with full list
    """
    try:
        total_count = len(items)

        # Build attribute with count and preview
        preview_items = items[:max_attr_items]
        attr_value = ",".join(preview_items)
        if total_count > max_attr_items:
            attr_value += f",... [and {total_count - max_attr_items} more]"

        attr_metadata = {
            f"{attribute_name}.count": total_count,
            attribute_name: attr_value,
        }
        set_span_attributes(attr_metadata)

        # Build event data with full list (up to max)
        event_items = items[:max_event_items]
        event_data = ",".join(event_items)
        if total_count > max_event_items:
            event_data += f",... [truncated, total: {total_count}]"

        actual_event_name = event_name or f"large_data:{attribute_name}"
        add_span_event(
            actual_event_name,
            attributes={
                "items": event_data,
                "total_count": total_count,
            },
        )

    except Exception as e:
        logger.debug(f"Failed to log large string list {attribute_name}: {e}")


def log_json_body(
    attribute_name: str,
    body: Union[str, bytes, dict],
    max_attr_preview: int = 100,
    max_event_size: int = 10000,
) -> None:
    """Log JSON request/response body to span event.

    Specialized helper for HTTP bodies that handles JSON parsing and
    extracts key fields for attributes.

    Args:
        attribute_name: Name for the attribute (e.g., "http.request.body")
        body: The body content (string, bytes, or dict)
        max_attr_preview: Maximum length for attribute preview
        max_event_size: Maximum size for event data

    Example:
        log_json_body("http.request.body", request_body)
        # Sets attributes: length, content_type, has_messages, etc.
        # Adds event: large_data:http.request.body with full body
    """
    try:
        # Convert body to string
        if isinstance(body, bytes):
            body_str = body.decode("utf-8", errors="replace")
        elif isinstance(body, dict):
            import json

            body_str = json.dumps(body, ensure_ascii=False)
        else:
            body_str = str(body) if body else ""

        body_length = len(body_str)

        # Build attributes
        attrs: Dict[str, Any] = {
            f"{attribute_name}.length": body_length,
        }

        # Try to parse JSON and extract key fields
        if body_str:
            try:
                import json

                parsed = json.loads(body_str)
                if isinstance(parsed, dict):
                    # Extract common fields for query purposes
                    if "messages" in parsed:
                        attrs[f"{attribute_name}.has_messages"] = True
                        attrs[f"{attribute_name}.message_count"] = len(
                            parsed.get("messages", [])
                        )
                    if "model" in parsed:
                        attrs[f"{attribute_name}.model"] = str(parsed["model"])[:50]
                    if "task_id" in parsed:
                        attrs[f"{attribute_name}.task_id"] = parsed["task_id"]
                    if "stream" in parsed:
                        attrs[f"{attribute_name}.is_stream"] = parsed["stream"]
            except json.JSONDecodeError:
                attrs[f"{attribute_name}.is_json"] = False
            else:
                attrs[f"{attribute_name}.is_json"] = True

            # Add truncated preview
            preview = body_str[:max_attr_preview]
            if body_length > max_attr_preview:
                preview += f"... [truncated, total: {body_length}]"
            attrs[attribute_name] = preview

        set_span_attributes(attrs)

        # Add event with full body (truncated if needed)
        event_body = body_str[:max_event_size]
        if body_length > max_event_size:
            event_body += f"\n... [truncated, total length: {body_length}]"

        add_span_event(
            f"large_data:{attribute_name}",
            attributes={"body": event_body, "original_length": body_length},
        )

    except Exception as e:
        logger.debug(f"Failed to log JSON body {attribute_name}: {e}")
```

**Step 2: Update `shared/telemetry/context/__init__.py` to export the new functions**

Add to imports:
```python
from shared.telemetry.context.large_data import (
    log_json_body,
    log_large_attribute,
    log_large_string_list,
)
```

Add to `__all__`:
```python
    "log_large_attribute",
    "log_large_string_list",
    "log_json_body",
```

**Step 3: Create tests**

Create `shared/tests/telemetry/test_large_data.py`:

```python
# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for large data logging utilities."""

import json
from unittest.mock import MagicMock, patch

import pytest

from shared.telemetry.context.large_data import (
    log_json_body,
    log_large_attribute,
    log_large_string_list,
)


class TestLogLargeAttribute:
    """Tests for log_large_attribute function."""

    @patch("shared.telemetry.context.large_data.set_span_attributes")
    @patch("shared.telemetry.context.large_data.add_span_event")
    def test_logs_string_data(self, mock_add_event, mock_set_attrs):
        """Test logging string data."""
        log_large_attribute("test.attr", "hello world")

        # Check attributes were set with metadata
        mock_set_attrs.assert_called_once()
        attrs = mock_set_attrs.call_args[0][0]
        assert attrs["test.attr.length"] == 11
        assert attrs["test.attr"] == "hello world"

        # Check event was added with full data
        mock_add_event.assert_called_once()
        assert mock_add_event.call_args[0][0] == "large_data:test.attr"
        assert mock_add_event.call_args[1]["attributes"]["data"] == "hello world"

    @patch("shared.telemetry.context.large_data.set_span_attributes")
    @patch("shared.telemetry.context.large_data.add_span_event")
    def test_truncates_large_data(self, mock_add_event, mock_set_attrs):
        """Test that large data is truncated appropriately."""
        large_data = "x" * 20000
        log_large_attribute("test.attr", large_data, max_attr_length=50, max_event_length=100)

        attrs = mock_set_attrs.call_args[0][0]
        assert attrs["test.attr.length"] == 20000
        assert "... [truncated, total: 20000]" in attrs["test.attr"]
        assert len(attrs["test.attr"]) <= 100  # 50 + truncation message

        event_attrs = mock_add_event.call_args[1]["attributes"]
        assert "... [truncated, total length: 20000]" in event_attrs["data"]

    @patch("shared.telemetry.context.large_data.set_span_attributes")
    @patch("shared.telemetry.context.large_data.add_span_event")
    def test_handles_dict_data(self, mock_add_event, mock_set_attrs):
        """Test logging dict data."""
        data = {"key": "value", "number": 42}
        log_large_attribute("test.attr", data)

        attrs = mock_set_attrs.call_args[0][0]
        assert attrs["test.attr.length"] > 0

        event_attrs = mock_add_event.call_args[1]["attributes"]
        parsed = json.loads(event_attrs["data"])
        assert parsed["key"] == "value"


class TestLogLargeStringList:
    """Tests for log_large_string_list function."""

    @patch("shared.telemetry.context.large_data.set_span_attributes")
    @patch("shared.telemetry.context.large_data.add_span_event")
    def test_logs_id_list(self, mock_add_event, mock_set_attrs):
        """Test logging a list of IDs."""
        ids = ["id1", "id2", "id3", "id4", "id5"]
        log_large_string_list("document_ids", ids, max_attr_items=3)

        attrs = mock_set_attrs.call_args[0][0]
        assert attrs["document_ids.count"] == 5
        assert "id1,id2,id3" in attrs["document_ids"]
        assert "... [and 2 more]" in attrs["document_ids"]

        event_attrs = mock_add_event.call_args[1]["attributes"]
        assert event_attrs["total_count"] == 5
        assert "id1,id2,id3,id4,id5" in event_attrs["items"]


class TestLogJsonBody:
    """Tests for log_json_body function."""

    @patch("shared.telemetry.context.large_data.set_span_attributes")
    @patch("shared.telemetry.context.large_data.add_span_event")
    def test_logs_json_body(self, mock_add_event, mock_set_attrs):
        """Test logging JSON request body."""
        body = json.dumps({"messages": [{"role": "user", "content": "hello"}], "model": "gpt-4"})
        log_json_body("http.request.body", body)

        attrs = mock_set_attrs.call_args[0][0]
        assert attrs["http.request.body.length"] > 0
        assert attrs["http.request.body.has_messages"] is True
        assert attrs["http.request.body.message_count"] == 1
        assert attrs["http.request.body.model"] == "gpt-4"
        assert attrs["http.request.body.is_json"] is True

    @patch("shared.telemetry.context.large_data.set_span_attributes")
    @patch("shared.telemetry.context.large_data.add_span_event")
    def test_handles_bytes(self, mock_add_event, mock_set_attrs):
        """Test logging bytes body."""
        body = b'{"test": "data"}'
        log_json_body("http.request.body", body)

        attrs = mock_set_attrs.call_args[0][0]
        assert attrs["http.request.body.length"] == 16

        event_attrs = mock_add_event.call_args[1]["attributes"]
        assert '{"test": "data"}' in event_attrs["body"]
```

**Step 4: Run tests**

```bash
cd /Volumes/OuterHD/OuterIdeaProjects/Wegent/shared
uv run pytest tests/telemetry/test_large_data.py -v
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add shared/telemetry/context/large_data.py shared/telemetry/context/__init__.py shared/tests/telemetry/test_large_data.py
git commit -m "feat(telemetry): add helper functions for logging large data to events

Add log_large_attribute, log_large_string_list, and log_json_body functions
to store large data in span events instead of attributes for better
performance and reduced storage."
```

---

## Task 2: Update HTTP Instrumentation to Use Events for Bodies

**Files:**
- Modify: `shared/telemetry/instrumentation.py`
- Test: `shared/tests/telemetry/test_instrumentation.py`

**Step 1: Update HTTPX request hooks**

In `_create_httpx_request_hook`, replace:
```python
span.set_attribute("http.request.body", body_str)
```

With:
```python
from shared.telemetry.context.large_data import log_json_body
log_json_body("http.request.body", body)
```

**Step 2: Update HTTPX async request hook**

In `_create_httpx_async_request_hook`, replace the body capture logic:
```python
span.set_attribute("http.request.body", body_str)
```

With:
```python
log_json_body("http.request.body", body)
```

**Step 3: Update HTTPX response hooks**

Replace:
```python
span.set_attribute("http.response.body", body_str)
```

With:
```python
log_json_body("http.response.body", body)
```

**Step 4: Update Requests hooks**

Replace:
```python
span.set_attribute("http.request.body", body_str)
span.set_attribute("http.response.body", body_str)
```

With:
```python
log_json_body("http.request.body", body)
log_json_body("http.response.body", body)
```

**Step 5: Update FastAPI server request hook**

Replace query param and path param logging to use events for large data.

**Step 6: Run tests**

```bash
cd /Volumes/OuterHD/OuterIdeaProjects/Wegent/shared
uv run pytest tests/telemetry/test_instrumentation.py -v
```

**Step 7: Commit**

```bash
git add shared/telemetry/instrumentation.py
git commit -m "refactor(telemetry): store HTTP bodies in events instead of attributes

Migrate http.request.body and http.response.body from span attributes
to span events to reduce storage size and improve query performance."
```

---

## Task 3: Update Tool Events to Use Events for I/O

**Files:**
- Modify: `chat_shell/chat_shell/tools/events.py`

**Step 1: Update tool_start event**

Replace:
```python
add_span_event(
    f"tool_start:{tool_name}",
    attributes={
        "tool.name": tool_name,
        "tool.run_id": run_id,
        "tool.tool_use_id": tool_use_id,
        "tool.input": str(serializable_input)[:1000],
    },
)
```

With:
```python
from shared.telemetry.context.large_data import log_large_attribute

# Log tool input to event instead of attribute
log_large_attribute(
    "tool.input",
    serializable_input,
    max_attr_length=100,
    max_event_length=5000,
    event_name=f"tool_start:{tool_name}",
    extra_attributes={
        "tool.name": tool_name,
        "tool.run_id": run_id,
        "tool.tool_use_id": tool_use_id,
    },
)
```

**Step 2: Update tool_end event**

Replace:
```python
add_span_event(
    f"tool_end:{tool_name}",
    attributes={
        "tool.name": tool_name,
        "tool.run_id": run_id,
        "tool.tool_use_id": tool_use_id,
        "tool.output_length": len(output_str),
        "tool.output": output_str[:1000],
        "tool.status": "completed",
    },
)
```

With:
```python
log_large_attribute(
    "tool.output",
    serializable_output,
    max_attr_length=100,
    max_event_length=5000,
    event_name=f"tool_end:{tool_name}",
    extra_attributes={
        "tool.name": tool_name,
        "tool.run_id": run_id,
        "tool.tool_use_id": tool_use_id,
        "tool.output_length": len(output_str),
        "tool.status": "completed",
    },
)
```

**Step 3: Commit**

```bash
git add chat_shell/chat_shell/tools/events.py
git commit -m "refactor(chat_shell): store tool I/O in events instead of attributes

Migrate tool.input and tool.output from span attributes to span events
to reduce trace data size."
```

---

## Task 4: Update Knowledge Listing Tools

**Files:**
- Modify: `chat_shell/chat_shell/tools/builtin/knowledge_listing.py`

**Step 1: Update document_ids logging in kb_head tool**

Replace:
```python
set_span_attribute("document_ids", str(document_ids))
```

With:
```python
from shared.telemetry.context.large_data import log_large_string_list
log_large_string_list("document_ids", [str(d) for d in document_ids])
```

**Step 2: Update all occurrences**

There are multiple places where `document_ids` is logged. Update all of them.

**Step 3: Commit**

```bash
git add chat_shell/chat_shell/tools/builtin/knowledge_listing.py
git commit -m "refactor(chat_shell): store document_ids in events instead of attributes

Use log_large_string_list for document_ids to reduce attribute size."
```

---

## Task 5: Update Memory Utils

**Files:**
- Modify: `backend/app/services/memory/utils.py`

**Step 1: Update memory.ids logging**

Replace:
```python
set_span_attribute("memory.ids", ",".join(memory_ids))
```

With:
```python
from shared.telemetry.context.large_data import log_large_string_list
log_large_string_list("memory.ids", memory_ids)
```

**Step 2: Update metadata.filtered_fields logging**

Replace:
```python
set_span_attribute("metadata.filtered_fields", ",".join(filtered.keys()))
```

With:
```python
log_large_string_list("metadata.filtered_fields", list(filtered.keys()))
```

**Step 3: Commit**

```bash
git add backend/app/services/memory/utils.py
git commit -m "refactor(backend): store memory IDs and fields in events

Migrate memory.ids and metadata.filtered_fields to use events for
large lists, keeping only counts in attributes."
```

---

## Task 6: Update WebSocket Decorators

**Files:**
- Modify: `backend/app/api/ws/decorators.py`

**Step 1: Update request body logging**

Replace:
```python
_safe_set_attribute(span, "websocket.request_body", request_body_json)
```

With:
```python
from shared.telemetry.context.large_data import log_large_attribute
log_large_attribute(
    "websocket.request_body",
    request_body_json,
    max_attr_length=200,
    max_event_length=10000,
    event_name="websocket.request_received",
)
```

**Step 2: Commit**

```bash
git add backend/app/api/ws/decorators.py
git commit -m "refactor(backend): store WebSocket request body in events

Migrate websocket.request_body from attribute to event for large data."
```

---

## Task 7: Update Main Application Files

**Files:**
- Modify: `backend/app/main.py`
- Modify: `chat_shell/chat_shell/main.py`
- Modify: `executor/app.py`
- Modify: `executor_manager/routers/routers.py`

**Step 1: Update backend main.py**

Replace:
```python
current_span.set_attribute("http.request.body", request_body)
```

With:
```python
from shared.telemetry.context.large_data import log_json_body
log_json_body("http.request.body", request_body)
```

**Step 2: Update chat_shell main.py**

Same change as above.

**Step 3: Update executor app.py**

Same change as above.

**Step 4: Update executor_manager routers**

Same change as above.

**Step 5: Commit**

```bash
git add backend/app/main.py chat_shell/chat_shell/main.py executor/app.py executor_manager/routers/routers.py
git commit -m "refactor: store HTTP request bodies in events across all services

Update all main application files to use log_json_body for request bodies."
```

---

## Task 8: Run All Tests

**Step 1: Run shared tests**

```bash
cd /Volumes/OuterHD/OuterIdeaProjects/Wegent/shared
uv run pytest tests/telemetry/ -v
```

**Step 2: Run backend tests**

```bash
cd /Volumes/OuterHD/OuterIdeaProjects/Wegent/backend
uv run pytest tests/ -k "telemetry" -v
```

**Step 3: Run chat_shell tests**

```bash
cd /Volumes/OuterHD/OuterIdeaProjects/Wegent/chat_shell
uv run pytest tests/ -v
```

**Step 4: Final commit**

```bash
git commit -m "test: add tests for trace data optimization

Verify all changes work correctly across services."
```

---

## Summary

After completing all tasks:

1. **Large data** (bodies, lists) is stored in **span events** (logs)
2. **Lightweight metadata** (lengths, counts, previews) is stored in **span attributes** (tags)
3. **Query performance** improves since attributes are smaller and indexed
4. **Storage costs** reduce since events are typically cheaper to store

### Migration Checklist

- [x] Created helper functions for large data logging
- [x] Updated HTTP instrumentation (HTTPX, Requests, FastAPI)
- [x] Updated tool events (tool.input, tool.output)
- [x] Updated knowledge listing tools (document_ids)
- [x] Updated memory utils (memory.ids, metadata.filtered_fields)
- [x] Updated WebSocket decorators (websocket.request_body)
- [x] Updated all main application files
- [x] All tests pass
