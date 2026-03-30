# Prompt Draft Regenerate Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make prompt-draft regeneration send the current generated prompt back to the model as an `assistant` message, followed by a `user` dissatisfaction message requesting a better rewrite.

**Architecture:** Extend the prompt-draft generate request with regenerate metadata, keep the existing initial-generation flow unchanged, and add a regenerate-specific message builder in the backend prompt-draft pipeline. The frontend regenerate button will pass the current prompt so the backend can construct the intended assistant/user follow-up conversation without mutating stored conversation materials.

**Tech Stack:** FastAPI, Pydantic, frontend React/TypeScript, Jest, pytest

---

### Task 1: Add backend failing test for regenerate message building

**Files:**
- Create: `backend/tests/services/prompt_draft/test_pipeline.py`
- Modify: `backend/app/services/prompt_draft/pipeline.py`

**Step 1: Write the failing test**

```python
def test_build_generation_messages_for_regenerate_appends_current_prompt_and_user_feedback():
    messages = build_generation_messages(
        conversation_blocks=[("user", "用户原始需求"), ("assistant", "历史回复")],
        current_prompt="你是A助手，负责A。",
        regenerate=True,
    )

    assert messages[-2] == {"role": "assistant", "content": "你是A助手，负责A。"}
    assert messages[-1]["role"] == "user"
    assert "我对当前方案不满意" in messages[-1]["content"]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest backend/tests/services/prompt_draft/test_pipeline.py -q`
Expected: FAIL because `build_generation_messages` does not accept regenerate inputs yet.

**Step 3: Write minimal implementation**

Update `build_generation_messages` to accept optional `current_prompt` and `regenerate` arguments. When regenerate is true and `current_prompt` is present, append:
- one `assistant` message containing the current prompt
- one `user` message stating dissatisfaction and asking for a rewritten final prompt

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest backend/tests/services/prompt_draft/test_pipeline.py -q`
Expected: PASS

### Task 2: Add frontend failing test for regenerate request payload

**Files:**
- Modify: `frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`
- Modify: `frontend/src/features/prompt-draft/components/PromptDraftDialog.tsx`
- Modify: `frontend/src/apis/tasks.ts`

**Step 1: Write the failing test**

```typescript
test('regenerate sends current prompt and regenerate flag', async () => {
  // render dialog with an existing generated prompt
  // click regenerate
  // expect generatePromptDraftStream called with current_prompt and regenerate=true
})
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --runInBand frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`
Expected: FAIL because regenerate currently reuses the same request body as initial generation.

**Step 3: Write minimal implementation**

Extend the request type in `frontend/src/apis/tasks.ts` and update `PromptDraftDialog.generate()` so regenerate requests include:
- `current_prompt`
- `regenerate: true`

Leave initial generation unchanged.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --runInBand frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`
Expected: PASS

### Task 3: Wire regenerate request through backend service layer

**Files:**
- Modify: `backend/app/schemas/task.py`
- Modify: `backend/app/services/prompt_draft_service.py`
- Modify: `backend/app/services/prompt_draft/pipeline.py`

**Step 1: Write the failing test**

Add or extend a backend unit test that calls the service/pipeline entry with regenerate inputs and verifies the generated model request includes the appended assistant/user turn pair.

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest backend/tests/services/prompt_draft/test_pipeline.py -q`
Expected: FAIL because the service layer drops regenerate metadata.

**Step 3: Write minimal implementation**

Add `current_prompt` and `regenerate` to `PromptDraftGenerateRequest`, thread them through `generate_prompt_draft()` and `generate_prompt_draft_stream()`, and pass them into the pipeline helpers.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest backend/tests/services/prompt_draft/test_pipeline.py -q`
Expected: PASS

### Task 4: Verify targeted suites

**Files:**
- Test: `backend/tests/services/prompt_draft/test_pipeline.py`
- Test: `frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`

**Step 1: Run backend verification**

Run: `cd backend && uv run pytest backend/tests/services/prompt_draft/test_pipeline.py -q`
Expected: PASS

**Step 2: Run frontend verification**

Run: `cd frontend && npm test -- --runInBand frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`
Expected: PASS

**Step 3: Commit**

```bash
git add docs/plans/2026-03-29-prompt-draft-regenerate-implementation-plan.md backend/app/schemas/task.py backend/app/services/prompt_draft_service.py backend/app/services/prompt_draft/pipeline.py backend/tests/services/prompt_draft/test_pipeline.py frontend/src/apis/tasks.ts frontend/src/features/prompt-draft/components/PromptDraftDialog.tsx frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx
git commit -m "feat(prompt-draft): improve regenerate prompt flow"
```
