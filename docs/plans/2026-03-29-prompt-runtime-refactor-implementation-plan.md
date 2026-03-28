# Prompt Runtime Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the new prompt runtime and prompt-draft changes into cohesive backend and frontend modules without changing public behavior.

**Architecture:** Use characterization tests to freeze current behavior, then incrementally extract shared runtime helpers, split prompt-draft orchestration into focused backend modules, and move frontend prompt-draft code into its own feature boundary. Keep existing endpoints and user flows stable during the transition.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, Next.js 15, React 19, TypeScript, Jest

---

### Task 1: Freeze Current Runtime And Prompt-Draft Behavior

**Files:**
- Modify: `backend/tests/services/test_prompt_draft_service.py`
- Modify: `backend/tests/api/endpoints/test_task_prompt_draft_api.py`
- Modify: `backend/tests/api/endpoints/test_model_runtime_api.py`
- Modify: `chat_shell/tests/test_context_stateless.py`
- Modify: `frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`

**Step 1: Write the failing tests**

Add assertions for:
- stateless runtime SSE formatting
- prompt-draft fallback model behavior
- masked logging behavior
- `history_limit=0` not restoring request history
- prompt-draft dialog behavior when a saved draft has no explicit model

**Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && uv run pytest tests/services/test_prompt_draft_service.py tests/api/endpoints/test_task_prompt_draft_api.py tests/api/endpoints/test_model_runtime_api.py -q
cd chat_shell && uv run pytest tests/test_context_stateless.py -q
cd frontend && npm test -- --runInBand src/__tests__/features/pet/PromptDraftDialog.test.tsx
```

Expected:
- New assertions fail for the current implementation.

**Step 3: Make only the minimum test fixture updates needed**

Do not refactor production code yet. Only fix test fixtures so failures point to the intended behavior mismatch.

**Step 4: Re-run tests to confirm red state is clean**

Run the same commands again.

Expected:
- Tests still fail, but only for the new behavior assertions.

**Step 5: Commit**

```bash
git add backend/tests/services/test_prompt_draft_service.py backend/tests/api/endpoints/test_task_prompt_draft_api.py backend/tests/api/endpoints/test_model_runtime_api.py chat_shell/tests/test_context_stateless.py frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx
git commit -m "test: add characterization coverage for prompt runtime refactor"
```

### Task 2: Extract Shared Stateless Runtime Service

**Files:**
- Create: `backend/app/services/model_runtime/stateless_runtime_service.py`
- Create: `backend/app/services/model_runtime/__init__.py`
- Modify: `backend/app/api/endpoints/adapter/model_runtime.py`
- Test: `backend/tests/api/endpoints/test_model_runtime_api.py`

**Step 1: Write the failing test**

Add a test that verifies request normalization and streaming payload serialization through a dedicated service interface rather than endpoint-local logic.

Example:
```python
async def test_stateless_runtime_service_normalizes_string_input():
    result = await build_runtime_request("hello")
    assert result == [{"role": "user", "content": "hello"}]
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd backend && uv run pytest tests/api/endpoints/test_model_runtime_api.py -q
```

Expected:
- FAIL because the service does not exist yet.

**Step 3: Write minimal implementation**

Implement:
- input normalization helper
- event-to-SSE payload serializer
- `complete()` wrapper
- `stream()` wrapper

Move endpoint code to use the service.

**Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && uv run pytest tests/api/endpoints/test_model_runtime_api.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add backend/app/services/model_runtime/stateless_runtime_service.py backend/app/services/model_runtime/__init__.py backend/app/api/endpoints/adapter/model_runtime.py backend/tests/api/endpoints/test_model_runtime_api.py
git commit -m "refactor(backend): extract stateless runtime service"
```

### Task 3: Split Prompt-Draft Transcript And Model Resolution

**Files:**
- Create: `backend/app/services/prompt_draft/transcript.py`
- Create: `backend/app/services/prompt_draft/modeling.py`
- Create: `backend/app/services/prompt_draft/__init__.py`
- Modify: `backend/app/services/prompt_draft_service.py`
- Test: `backend/tests/services/test_prompt_draft_service.py`

**Step 1: Write the failing tests**

Add focused tests for:
- transcript block extraction from subtasks
- tool-call summary extraction
- model resolution fallback rules

Example:
```python
def test_resolve_model_config_returns_empty_name_when_no_model():
    model_config, selected = _resolve_model_config(db, user, None)
    assert model_config is None
    assert selected == ""
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd backend && uv run pytest tests/services/test_prompt_draft_service.py -q
```

Expected:
- FAIL for the new module-level expectations.

**Step 3: Write minimal implementation**

Extract:
- conversation block readers
- transcript normalization
- model config resolution

Keep `prompt_draft_service.py` as a compatibility facade that imports and delegates.

**Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && uv run pytest tests/services/test_prompt_draft_service.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add backend/app/services/prompt_draft/transcript.py backend/app/services/prompt_draft/modeling.py backend/app/services/prompt_draft/__init__.py backend/app/services/prompt_draft_service.py backend/tests/services/test_prompt_draft_service.py
git commit -m "refactor(backend): split prompt draft transcript and modeling"
```

### Task 4: Split Prompt-Draft Generation And Streaming

**Files:**
- Create: `backend/app/services/prompt_draft/generation.py`
- Create: `backend/app/services/prompt_draft/fallback.py`
- Modify: `backend/app/services/prompt_draft_service.py`
- Modify: `backend/app/api/endpoints/adapter/tasks.py`
- Test: `backend/tests/services/test_prompt_draft_service.py`
- Test: `backend/tests/api/endpoints/test_task_prompt_draft_api.py`

**Step 1: Write the failing tests**

Add tests for:
- generation retry behavior
- masked model-config logging helper
- streaming completed event shape
- task endpoint preserving existing status codes

**Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && uv run pytest tests/services/test_prompt_draft_service.py tests/api/endpoints/test_task_prompt_draft_api.py -q
```

Expected:
- FAIL because generation/fallback logic has not been extracted yet.

**Step 3: Write minimal implementation**

Extract:
- prompt generation strategy
- title generation strategy
- safe logging helper
- fallback builder
- stream event assembly

Endpoint files should continue calling only the orchestration API.

**Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && uv run pytest tests/services/test_prompt_draft_service.py tests/api/endpoints/test_task_prompt_draft_api.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add backend/app/services/prompt_draft/generation.py backend/app/services/prompt_draft/fallback.py backend/app/services/prompt_draft_service.py backend/app/api/endpoints/adapter/tasks.py backend/tests/services/test_prompt_draft_service.py backend/tests/api/endpoints/test_task_prompt_draft_api.py
git commit -m "refactor(backend): split prompt draft generation pipeline"
```

### Task 5: Create A Dedicated Frontend Prompt-Draft Feature

**Files:**
- Create: `frontend/src/features/prompt-draft/components/PromptDraftDialog.tsx`
- Create: `frontend/src/features/prompt-draft/hooks/usePromptDraftGeneration.ts`
- Create: `frontend/src/features/prompt-draft/hooks/usePromptDraftModels.ts`
- Create: `frontend/src/features/prompt-draft/hooks/usePromptDraftStorage.ts`
- Create: `frontend/src/features/prompt-draft/index.ts`
- Modify: `frontend/src/features/pet/components/PromptDraftDialog.tsx`
- Modify: `frontend/src/features/pet/components/PetWidget.tsx`
- Test: `frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`

**Step 1: Write the failing tests**

Add tests that assert:
- `pet` uses prompt-draft feature exports instead of local orchestration
- generation state is driven by hooks
- no direct dependency from `pet` to `settings` prompt-tune component remains

**Step 2: Run test to verify it fails**

Run:
```bash
cd frontend && npm test -- --runInBand src/__tests__/features/pet/PromptDraftDialog.test.tsx
```

Expected:
- FAIL because the feature split does not exist yet.

**Step 3: Write minimal implementation**

Move prompt-draft state and side effects into hooks.

Temporarily keep `frontend/src/features/pet/components/PromptDraftDialog.tsx` as a re-export shim if needed to avoid broad import churn in one step.

**Step 4: Run tests to verify they pass**

Run:
```bash
cd frontend && npm test -- --runInBand src/__tests__/features/pet/PromptDraftDialog.test.tsx
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add frontend/src/features/prompt-draft frontend/src/features/pet/components/PromptDraftDialog.tsx frontend/src/features/pet/components/PetWidget.tsx frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx
git commit -m "refactor(frontend): extract prompt draft feature module"
```

### Task 6: Remove Cross-Feature Prompt-Tune Dependency

**Files:**
- Create: `frontend/src/features/prompt-draft/components/PromptFineTuneLauncher.tsx`
- Modify: `frontend/src/features/settings/components/prompt-fine-tune/PromptFineTuneDialog.tsx`
- Modify: `frontend/src/features/prompt-draft/components/PromptDraftDialog.tsx`
- Test: `frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`

**Step 1: Write the failing test**

Add a test that proves prompt-draft can launch prompt tuning through a prompt-draft-local adapter without importing from `settings` feature paths.

**Step 2: Run test to verify it fails**

Run:
```bash
cd frontend && npm test -- --runInBand src/__tests__/features/pet/PromptDraftDialog.test.tsx
```

Expected:
- FAIL because the launcher adapter does not exist yet.

**Step 3: Write minimal implementation**

Introduce a thin adapter owned by `prompt-draft`.

If needed, move shared prompt-tune pieces into a neutral location and let both `settings` and `prompt-draft` depend on them.

**Step 4: Run tests to verify they pass**

Run:
```bash
cd frontend && npm test -- --runInBand src/__tests__/features/pet/PromptDraftDialog.test.tsx
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add frontend/src/features/prompt-draft/components/PromptFineTuneLauncher.tsx frontend/src/features/settings/components/prompt-fine-tune/PromptFineTuneDialog.tsx frontend/src/features/prompt-draft/components/PromptDraftDialog.tsx frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx
git commit -m "refactor(frontend): remove prompt draft dependency on settings feature"
```

### Task 7: Move Pet Entry Logic Into Dedicated Hooks

**Files:**
- Create: `frontend/src/features/pet/hooks/usePetPromptDraftEntry.ts`
- Create: `frontend/src/features/pet/hooks/usePetPromptHint.ts`
- Modify: `frontend/src/features/pet/components/PetWidget.tsx`
- Modify: `frontend/src/features/pet/components/PetNotificationPanel.tsx`
- Test: `frontend/src/__tests__/features/pet/PetNotificationPanel.test.tsx`

**Step 1: Write the failing tests**

Add tests for:
- hint cooldown behavior
- dialog-open action behavior
- no widget-local random entry logic remaining in component body

**Step 2: Run test to verify it fails**

Run:
```bash
cd frontend && npm test -- --runInBand src/__tests__/features/pet/PetNotificationPanel.test.tsx
```

Expected:
- FAIL because hooks do not exist yet.

**Step 3: Write minimal implementation**

Move:
- selected task lookup
- prompt entry state
- hint cooldown logic

Keep `PetWidget` focused on rendering and pointer interaction only.

**Step 4: Run tests to verify they pass**

Run:
```bash
cd frontend && npm test -- --runInBand src/__tests__/features/pet/PetNotificationPanel.test.tsx
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add frontend/src/features/pet/hooks/usePetPromptDraftEntry.ts frontend/src/features/pet/hooks/usePetPromptHint.ts frontend/src/features/pet/components/PetWidget.tsx frontend/src/features/pet/components/PetNotificationPanel.tsx frontend/src/__tests__/features/pet/PetNotificationPanel.test.tsx
git commit -m "refactor(frontend): move pet prompt entry logic into hooks"
```

### Task 8: Run Full Verification And Remove Transitional Shims

**Files:**
- Modify: any temporary re-export or compatibility shims introduced in earlier tasks
- Test: `backend/tests/services/test_prompt_draft_service.py`
- Test: `backend/tests/api/endpoints/test_task_prompt_draft_api.py`
- Test: `backend/tests/api/endpoints/test_model_runtime_api.py`
- Test: `chat_shell/tests/test_context_stateless.py`
- Test: `chat_shell/tests/test_history_loader.py`
- Test: `frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`
- Test: `frontend/src/__tests__/features/pet/PetNotificationPanel.test.tsx`

**Step 1: Write the failing cleanup test**

Add assertions that old shim imports are no longer used where the final architecture forbids them.

**Step 2: Run targeted checks to verify they fail**

Run the smallest relevant test command for the cleanup you are making.

**Step 3: Remove temporary glue code**

Delete:
- obsolete prompt-draft re-export shims
- dead helper functions left in endpoint files
- dead imports between `pet` and `settings`

**Step 4: Run full verification**

Run:
```bash
cd backend && uv run pytest tests/services/test_prompt_draft_service.py tests/api/endpoints/test_task_prompt_draft_api.py tests/api/endpoints/test_model_runtime_api.py -q
cd chat_shell && uv run pytest tests/test_context_stateless.py tests/test_history_loader.py -q
cd frontend && npm test -- --runInBand src/__tests__/features/pet/PromptDraftDialog.test.tsx src/__tests__/features/pet/PetNotificationPanel.test.tsx
```

Expected:
- All commands pass

**Step 5: Commit**

```bash
git add backend chat_shell frontend
git commit -m "refactor: finalize prompt runtime and prompt draft boundaries"
```

Plan complete and saved to `docs/plans/2026-03-29-prompt-runtime-refactor-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
