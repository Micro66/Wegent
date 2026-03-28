# Prompt Runtime Refactor Design

## Context

The current `conversation-to-prompt` change set delivers useful functionality, but it introduces three structural problems:

1. Backend runtime invocation now exists in more than one API path with partially duplicated request normalization and SSE formatting.
2. Prompt draft generation is implemented as a single large orchestration file that mixes transcript extraction, model resolution, generation strategy, fallback rules, and streaming.
3. Frontend prompt-draft behavior crosses feature boundaries and concentrates state orchestration inside `pet` UI components.

This is workable in the short term, but it will raise maintenance cost for any follow-up work on prompt generation, runtime APIs, or prompt tuning.

## Goals

1. Preserve all current user-facing behavior.
2. Reduce duplication across runtime invocation paths.
3. Split prompt-draft logic into cohesive backend modules.
4. Move frontend prompt-draft functionality to a dedicated feature boundary.
5. Keep the refactor incremental and test-driven.

## Non-Goals

1. No response payload redesign for external APIs.
2. No change to the prompt-draft product behavior unless required to preserve correctness.
3. No broad rewrite of the existing OpenAI-compatible `/api/v1/responses` pipeline.

## Approaches Considered

### Option A: Patch Current Files In Place

Keep the current file layout and only apply local cleanup.

Pros:
- Lowest immediate implementation cost
- Minimal file movement

Cons:
- Leaves duplicate runtime invocation patterns in place
- Leaves `prompt_draft_service.py` as a God service
- Leaves frontend feature boundary problems unsolved

Verdict: reject.

### Option B: Incremental Layered Refactor

Extract shared backend services and frontend feature modules while keeping current endpoints and visible UI stable.

Pros:
- Best balance of risk, clarity, and delivery speed
- Allows characterization tests before each extraction
- Keeps PRs reviewable

Cons:
- Requires temporary adapters and forwarding layers during transition

Verdict: recommend.

### Option C: Full Rewrite Around a New Prompt Platform

Redesign runtime, prompt draft, prompt tune, and frontend entrypoints together.

Pros:
- Cleanest end-state

Cons:
- High regression risk
- Too large for one safe change
- Hard to review and verify

Verdict: reject.

## Recommended Architecture

### Backend

Split prompt-draft backend logic into four layers:

1. `prompt_draft/transcript.py`
   - Reads subtasks and converts them into normalized conversation blocks.

2. `prompt_draft/modeling.py`
   - Resolves model config and strips model concerns away from orchestration.

3. `prompt_draft/generation.py`
   - Handles prompt/title generation, retries, streaming assembly, and log-safe model config rendering.

4. `prompt_draft/service.py`
   - Thin use-case orchestrator for API endpoints.

Also extract a shared stateless runtime facade so adapter endpoints do not each implement their own request normalization and SSE formatting.

### Frontend

Create a dedicated `prompt-draft` feature module:

1. `features/prompt-draft/hooks/`
   - model loading
   - draft generation
   - draft persistence

2. `features/prompt-draft/components/`
   - prompt draft dialog
   - prompt tuning launcher adapter

3. `features/prompt-draft/utils/`
   - storage helpers only

`pet` should become only an entry surface that opens the prompt-draft feature.

## Dependency Rules

1. `pet` may depend on `prompt-draft`.
2. `prompt-draft` must not depend on `settings`.
3. API endpoints depend on services, never on transcript/generation details directly.
4. Shared runtime formatting belongs in service/helpers, not endpoint files.

## Error Handling

1. Keep existing API status codes and SSE event schema stable.
2. Preserve fallback behavior when no model is available.
3. Keep secret masking centralized and reusable.
4. Avoid silent frontend state corruption when generation is cancelled or partially streamed.

## Testing Strategy

1. Add characterization tests before extraction.
2. Keep backend tests focused by module after the split.
3. Add frontend tests around the new prompt-draft hooks and pet entry behavior.
4. Run backend and chat-shell verification on every extraction step.

## Rollout Strategy

1. Extract shared helpers first behind existing APIs.
2. Split prompt-draft backend next.
3. Move frontend prompt-draft into its own feature module.
4. Refactor pet widget last so the entry surface only wires feature hooks.

This sequence minimizes API churn and keeps each refactor independently reversible.
