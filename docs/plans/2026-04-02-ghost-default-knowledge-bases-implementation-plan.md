---
sidebar_position: 1
---

# Ghost Default Knowledge Bases Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Ghost-level default knowledge base bindings that initialize `Task.spec.knowledgeBaseRefs` for new chats, while preserving message-time knowledge base selection as append behavior.

**Architecture:** Store default knowledge base refs in `Ghost.spec.defaultKnowledgeBaseRefs`, surface them through the existing bot APIs, and project them into `Task.spec.knowledgeBaseRefs` during task creation. Keep message-level explicit selections in `SubtaskContext` and reuse the existing sync-to-task path for append semantics.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Next.js 15, React 19, TypeScript, pytest

---

### Task 1: Add Ghost default knowledge base schema and bot API mapping

**Files:**
- Modify: `backend/app/schemas/kind.py`
- Modify: `backend/app/schemas/bot.py`
- Modify: `backend/app/services/adapters/bot_kinds.py`
- Test: `backend/tests/services/adapters/test_bot_kinds_default_knowledge_bases.py`

**Step 1: Write the failing backend schema tests**

Add tests covering:
- create bot request accepts `default_knowledge_base_refs`
- create/update bot writes refs into `Ghost.spec.defaultKnowledgeBaseRefs`
- bot detail/list response exposes `default_knowledge_base_refs`

Example assertion:

```python
assert ghost_crd.spec.defaultKnowledgeBaseRefs == [
    {"id": 101, "name": "Product Docs"}
]
```

**Step 2: Run the targeted tests to verify they fail**

Run:

```bash
cd backend && uv run pytest backend/tests/services/adapters/test_bot_kinds_default_knowledge_bases.py -v
```

Expected:
- FAIL because the request/response schemas and adapter logic do not yet know `default_knowledge_base_refs`

**Step 3: Add new Pydantic types and request/response fields**

Implement:
- `KnowledgeBaseDefaultRef` in `backend/app/schemas/kind.py`
- `GhostSpec.defaultKnowledgeBaseRefs`
- `BotCreate` / `BotUpdate` / `BotInDB` / `BotDetail` field for `default_knowledge_base_refs`

**Step 4: Map bot API fields to Ghost JSON**

Update `backend/app/services/adapters/bot_kinds.py` so that:
- create flow writes `defaultKnowledgeBaseRefs` into the new Ghost JSON
- update flow rewrites `defaultKnowledgeBaseRefs`
- `_convert_to_bot_dict()` reads `Ghost.spec.defaultKnowledgeBaseRefs` back into bot API payloads

**Step 5: Re-run targeted tests**

Run:

```bash
cd backend && uv run pytest backend/tests/services/adapters/test_bot_kinds_default_knowledge_bases.py -v
```

Expected:
- PASS

**Step 6: Commit**

```bash
git add backend/app/schemas/kind.py backend/app/schemas/bot.py backend/app/services/adapters/bot_kinds.py backend/tests/services/adapters/test_bot_kinds_default_knowledge_bases.py
git commit -m "feat(backend): add ghost default knowledge base refs"
```

### Task 2: Project Ghost default knowledge bases into new tasks

**Files:**
- Modify: `backend/app/services/chat/storage/task_manager.py`
- Create: `backend/app/services/chat/task_default_knowledge_bases.py`
- Test: `backend/tests/services/chat/test_task_default_knowledge_bases.py`

**Step 1: Write the failing task initialization tests**

Add tests covering:
- new task includes KB refs from all team member Ghosts
- `params.knowledge_base_id` is merged into the initial refs
- duplicate KBs are deduplicated by `id`
- inaccessible KBs are skipped instead of failing task creation

Example assertion:

```python
assert [ref["id"] for ref in task_crd.spec.knowledgeBaseRefs] == [11, 22, 33]
```

**Step 2: Run the targeted tests to verify they fail**

Run:

```bash
cd backend && uv run pytest backend/tests/services/chat/test_task_default_knowledge_bases.py -v
```

Expected:
- FAIL because `create_new_task()` only handles the legacy `knowledge_base_id` case

**Step 3: Extract task initialization helper**

Create `backend/app/services/chat/task_default_knowledge_bases.py` with focused helpers:
- load team member bots
- load corresponding ghosts
- collect `defaultKnowledgeBaseRefs`
- merge `params.knowledge_base_id`
- dedupe by KB `id`
- filter refs by current user access

**Step 4: Wire helper into task creation**

Update `create_new_task()` in `backend/app/services/chat/storage/task_manager.py` to:
- call the helper for every new task
- write returned refs into `task_json["spec"]["knowledgeBaseRefs"]` when non-empty
- remove special-casing that only initializes refs for `task_type == "knowledge"`

**Step 5: Re-run targeted tests**

Run:

```bash
cd backend && uv run pytest backend/tests/services/chat/test_task_default_knowledge_bases.py -v
```

Expected:
- PASS

**Step 6: Commit**

```bash
git add backend/app/services/chat/storage/task_manager.py backend/app/services/chat/task_default_knowledge_bases.py backend/tests/services/chat/test_task_default_knowledge_bases.py
git commit -m "feat(backend): initialize task kb refs from ghost defaults"
```

### Task 3: Preserve append semantics for message-time knowledge base selection

**Files:**
- Modify: `backend/tests/services/test_task_knowledge_base_sync.py`
- Modify: `backend/tests/services/chat/test_trigger_unified.py`

**Step 1: Add regression tests for append behavior**

Extend existing tests to prove:
- Ghost-initialized task refs remain present after message-time KB selection
- message-time selected KB still becomes `is_user_selected_kb=True`
- explicit subtask KB keeps priority over task-level fallback

Example assertion:

```python
assert set(task_level_ids) == {11, 22, 33}
assert kb_result.knowledge_base_ids == [33]
assert kb_result.is_user_selected_kb is True
```

**Step 2: Run the targeted regression tests**

Run:

```bash
cd backend && uv run pytest backend/tests/services/test_task_knowledge_base_sync.py backend/tests/services/chat/test_trigger_unified.py -v
```

Expected:
- FAIL only if task initialization broke append semantics

**Step 3: Fix any integration gaps**

If needed, make minimal changes so that:
- `link_contexts_to_subtask()` still appends
- `_prepare_kb_tools_from_contexts()` still prioritizes subtask-level KBs
- task-level fallback still uses the merged task refs

Keep the current priority model unchanged.

**Step 4: Re-run regression tests**

Run:

```bash
cd backend && uv run pytest backend/tests/services/test_task_knowledge_base_sync.py backend/tests/services/chat/test_trigger_unified.py -v
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add backend/tests/services/test_task_knowledge_base_sync.py backend/tests/services/chat/test_trigger_unified.py
git commit -m "test(backend): cover ghost default kb append semantics"
```

### Task 4: Add BotEdit UI for default knowledge bases

**Files:**
- Modify: `frontend/src/apis/bots.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/features/settings/components/BotEdit.tsx`
- Create: `frontend/src/features/settings/components/knowledge/KnowledgeBaseMultiSelector.tsx`
- Create: `frontend/src/features/settings/hooks/useKnowledgeBaseOptions.ts`
- Test: `frontend/src/features/settings/components/__tests__/BotEdit.default-knowledge-bases.test.tsx`

**Step 1: Write the failing frontend tests**

Add tests covering:
- existing bot loads default KB refs into the form
- user can add/remove multiple KBs
- save payload includes `default_knowledge_base_refs`

Example assertion:

```tsx
expect(updateBot).toHaveBeenCalledWith(
  7,
  expect.objectContaining({
    default_knowledge_base_refs: [{ id: 101, name: 'Product Docs' }],
  })
)
```

**Step 2: Run the targeted frontend tests to verify they fail**

Run:

```bash
cd frontend && npm test -- BotEdit.default-knowledge-bases.test.tsx
```

Expected:
- FAIL because the form and API types do not expose the field

**Step 3: Add types and API fields**

Update:
- `frontend/src/apis/bots.ts`
- `frontend/src/types/api.ts`

Add `default_knowledge_base_refs` to bot request and response types.

**Step 4: Build the selector UI**

Implement a small reusable multi-selector:
- fetch accessible/all knowledge bases
- support search
- support multiple selected chips
- return `{ id, name }[]`

Integrate it into `BotEdit.tsx` with explanatory helper text:
- used to initialize new chats
- manual chat selection appends more KBs later

**Step 5: Re-run targeted frontend tests**

Run:

```bash
cd frontend && npm test -- BotEdit.default-knowledge-bases.test.tsx
```

Expected:
- PASS

**Step 6: Commit**

```bash
git add frontend/src/apis/bots.ts frontend/src/types/api.ts frontend/src/features/settings/components/BotEdit.tsx frontend/src/features/settings/components/knowledge/KnowledgeBaseMultiSelector.tsx frontend/src/features/settings/hooks/useKnowledgeBaseOptions.ts frontend/src/features/settings/components/__tests__/BotEdit.default-knowledge-bases.test.tsx
git commit -m "feat(frontend): add bot default knowledge base selector"
```

### Task 5: Run integration verification and update docs if needed

**Files:**
- Modify: `docs/zh/developer-guide/` relevant doc if implementation changes public behavior materially
- Modify: `docs/en/developer-guide/` matching English doc if Chinese doc is updated

**Step 1: Run backend verification**

Run:

```bash
cd backend && uv run pytest backend/tests/services/adapters/test_bot_kinds_default_knowledge_bases.py backend/tests/services/chat/test_task_default_knowledge_bases.py backend/tests/services/test_task_knowledge_base_sync.py backend/tests/services/chat/test_trigger_unified.py -v
```

Expected:
- PASS

**Step 2: Run frontend verification**

Run:

```bash
cd frontend && npm test -- BotEdit.default-knowledge-bases.test.tsx
```

Expected:
- PASS

**Step 3: Run formatting/linting for touched surfaces**

Run:

```bash
cd frontend && npm run format && npm run lint
```

Run:

```bash
cd backend && uv run black . && uv run isort .
```

Expected:
- PASS with no formatting drift in touched files

**Step 4: Update docs only if the final API or behavior differs from this plan**

If implementation meaningfully changes public or developer behavior:
- update Chinese doc first
- then add matching English doc

Otherwise, skip extra docs and keep the design and plan files as the authoritative record.

**Step 5: Final commit**

```bash
git add docs
git commit -m "docs: record ghost default knowledge base rollout"
```

