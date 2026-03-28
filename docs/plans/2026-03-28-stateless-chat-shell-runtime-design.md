---
sidebar_position: 1
---

# Stateless Chat Shell Runtime Design

## Goal

Provide a reusable backend capability that calls chat_shell as a pure model runtime service without task/subtask persistence, and migrate prompt-draft generation to a two-step pipeline:

1. Generate prompt text
2. Generate title from generated prompt

## Scope

- Add a reusable stateless chat_shell model service in backend.
- Add a new adapter API endpoint for stateless model runtime calls.
- Refactor prompt draft generation to reuse the stateless service.
- Keep existing prompt draft API contract unchanged.

## Design

### 1) Reusable stateless service

New module: `backend/app/services/chat_shell_model_service.py`

- Unified stateless `responses.create` wrapper.
- Forces metadata:
  - `history_limit=0`
  - `stateless=true`
- Exposes:
  - `create_response(..., stream: bool)`
  - `complete_text(...)`
  - `extract_response_text(...)`

### 2) Stateless runtime adapter API

New endpoint:
- `POST /api/model-runtime/responses`

Request:
- `model`
- `input` (string or message array)
- `instructions`
- `stream`
- optional `metadata`, `model_config`, `tools`

Behavior:
- `stream=false`: returns extracted `output_text`
- `stream=true`: proxies SSE events
- No DB write and no task/subtask lifecycle orchestration

### 3) Prompt draft generation refactor

Refactor `backend/app/services/prompt_draft_service.py`:

- Replace JSON-contract output with two text-generation calls:
  - call-1: prompt body generation (skill-guided)
  - call-2: title generation based on prompt
- Reuse `chat_shell_model_service.complete_text` for both calls.
- Keep fallback path and contract validation.
- Lower fallback logging level from `ERROR` to `WARNING` with stack for diagnosis.

## Error Handling

- If stateless runtime call fails in prompt draft flow, return dynamic fallback output.
- Preserve existing API behavior (`200` with fallback payload).
- Keep diagnostics in logs with clear phase labels.

## Testing

- Update prompt draft service tests to assert two-phase model invocation.
- Add adapter API tests for stateless runtime endpoint:
  - list input mode
  - string input mode

## Non-Goals

- This iteration does not add prompt-draft frontend streaming UI protocol changes.
- This iteration does not persist prompt/title generation intermediate state.
