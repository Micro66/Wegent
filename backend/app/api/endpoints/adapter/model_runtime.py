# SPDX-FileCopyrightText: 2026 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core import security
from app.models.user import User
from app.schemas.model_runtime import (
    StatelessResponseCreateRequest,
    StatelessResponseCreateResult,
)
from app.services import chat_shell_model_service

router = APIRouter()


@router.post("/responses", response_model=StatelessResponseCreateResult)
async def create_stateless_response(
    request: StatelessResponseCreateRequest,
    current_user: User = Depends(security.get_current_user),
):
    del current_user
    if isinstance(request.input, str):
        input_messages = [{"role": "user", "content": request.input}]
    else:
        input_messages = [m.model_dump() for m in request.input]

    if request.stream:
        stream = await chat_shell_model_service.create_response(
            model=request.model,
            input_messages=input_messages,
            instructions=request.instructions,
            model_config=request.runtime_model_config,
            metadata=request.metadata,
            tools=request.tools,
            stream=True,
        )

        async def event_stream():
            async for event in stream:
                if hasattr(event, "model_dump"):
                    payload: dict[str, Any] = event.model_dump()
                elif isinstance(event, dict):
                    payload = event
                else:
                    payload = {"type": getattr(event, "type", "unknown")}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    output_text = await chat_shell_model_service.complete_text(
        model=request.model,
        input_messages=input_messages,
        instructions=request.instructions,
        model_config=request.runtime_model_config,
        metadata=request.metadata,
        tools=request.tools,
    )
    return StatelessResponseCreateResult(
        output_text=output_text,
        model=request.model,
        created_at=datetime.now(timezone.utc),
    )
