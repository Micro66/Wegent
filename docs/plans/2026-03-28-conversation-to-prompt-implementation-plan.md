---
sidebar_position: 1
---

# Conversation To Prompt Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a lightweight pet-triggered flow that turns the current chat conversation into a reusable prompt draft, then lets the user iterate it with the existing prompt fine-tune experience.

**Architecture:** The frontend adds a pet entrypoint, a lightweight generation dialog, and browser-local draft persistence. The backend adds a task-scoped generate endpoint that assembles full conversation history and invokes a new built-in `conversation_to_prompt` system skill through the chat shell path. The skill runs a multi-stage extract, generate, evaluate, and rewrite pipeline and returns strict JSON.

**Tech Stack:** Next.js 15, React 19, TypeScript, FastAPI, Pydantic, SQLAlchemy, Wegent built-in skills, Chat Shell execution

---

## UI Sketches

### 1. Pet idle state with lightweight bubble

```text
                         +----------------------+
                         | 要帮你总结一下吗？   |
                         +----------------------+
                                    \
                                     \
                              .-""""-.
                            .'  o  o  '.
                           /     ^      \
                          |   \_____/    |
                           \            /
                            '._    _.-'
                               |  |
                               |__|
```

Rules:
- Bubble is non-blocking and auto-dismisses.
- Clicking the pet always opens the panel, whether bubble is visible or not.
- Bubble copy stays short and pet-like; it is not a system alert.

### 2. Pet panel with persistent action

```text
+--------------------------------------------------+
| 宠物名：下午好！                                  |
|--------------------------------------------------|
| 经验值  [██████████------]                        |
| 未读消息 2 条                                     |
|                                                  |
| [ 帮我记住这种协作方式 ]                          |
|  将当前对话提炼成提示词草案                       |
+--------------------------------------------------+
```

Rules:
- New action lives in the pet panel, not in the main chat toolbar.
- The action remains available even after the lightweight bubble disappears.
- The CTA should expose intent, not technical implementation details.

### 3. Generation dialog

```text
+------------------------------------------------------------------+
| 提炼当前对话为提示词                                         [X] |
|------------------------------------------------------------------|
| 从当前会话中提炼“协作偏好 + 任务方法”，生成一份可继续微调的草案。 |
|                                                                  |
| 模型: [ 默认模型 v ]                                              |
|                                                                  |
| [ 开始生成 ]                                                      |
|------------------------------------------------------------------|
| 状态区                                                            |
| - 初始：展示说明                                                  |
| - 生成中：正在整理这段对话里的协作习惯和方法...                  |
| - 成功：展示 title + prompt                                      |
| - 失败：轻量错误 + 重试                                          |
+------------------------------------------------------------------+
```

### 4. Success state

```text
+------------------------------------------------------------------+
| 标题                                                             |
| 轻量产品设计与方案沟通协作提示词                                 |
|------------------------------------------------------------------|
| Prompt                                                           |
| 你是轻量产品设计与方案收敛助手，负责帮助我...                    |
|                                                                  |
| 你的工作方式：                                                   |
| - 优先给出直接判断...                                            |
|                                                                  |
| 处理任务时请遵循以下原则：                                       |
| - 优先复用现有能力链路...                                        |
|                                                                  |
| 输出要求：                                                       |
| - 结构清晰，便于直接复用或继续微调...                            |
|                                                                  |
| [ 重新生成 ]   [ 进入微调 ]   [ 关闭 ]                           |
+------------------------------------------------------------------+
```

## Task 1: Confirm target frontend insertion points

**Files:**
- Inspect: `frontend/src/features/pet/components/PetWidget.tsx`
- Inspect: `frontend/src/features/pet/components/PetNotificationPanel.tsx`
- Inspect: `frontend/src/features/pet/contexts/PetContext.tsx`
- Inspect: `frontend/src/features/settings/components/prompt-fine-tune/PromptFineTuneDialog.tsx`

**Step 1: Trace current pet render and hover behavior**

Run: `sed -n '1,220p' frontend/src/features/pet/components/PetWidget.tsx`
Expected: Confirm the pet panel currently appears on hover and there is no click-driven action dialog.

**Step 2: Trace current pet panel content**

Run: `sed -n '1,240p' frontend/src/features/pet/components/PetNotificationPanel.tsx`
Expected: Confirm task stats and greeting live here and identify where to add the new CTA.

**Step 3: Trace prompt fine-tune dialog reuse path**

Run: `sed -n '1,260p' frontend/src/features/settings/components/prompt-fine-tune/PromptFineTuneDialog.tsx`
Expected: Confirm the dialog already accepts `initialPrompt`, `modelName`, and `onSave`.

**Step 4: Commit planning checkpoint**

```bash
git add docs/plans/2026-03-28-conversation-to-prompt-implementation-plan.md
git commit -m "docs: add conversation-to-prompt implementation plan"
```

## Task 2: Define backend API contract and schemas

**Files:**
- Modify: `backend/app/schemas/task.py`
- Modify: `backend/app/api/endpoints/adapter/tasks.py`
- Test: `backend/tests/api/test_task_services.py`

**Step 1: Write failing API tests for generate endpoint**

Add tests for:
- authenticated user can generate a prompt draft for their task
- inaccessible task returns 404
- empty or too-short conversation returns 400
- response shape contains `title`, `prompt`, `model`, `version`, `created_at`

**Step 2: Run the targeted backend API tests**

Run: `cd backend && uv run pytest backend/tests/api/test_task_services.py -k prompt_draft -v`
Expected: FAIL because the request/response schema and route do not exist yet.

**Step 3: Add request and response schemas**

Add schema objects in `backend/app/schemas/task.py`:
- `PromptDraftGenerateRequest`
- `PromptDraftGenerateResponse`

Constraints:
- request accepts `model` and `source`
- response returns strict typed fields only

**Step 4: Add route in task adapter endpoint**

Add `POST /tasks/{task_id}/prompt-drafts/generate` in `backend/app/api/endpoints/adapter/tasks.py`.

Route responsibilities:
- verify user access to the task
- delegate to a service
- translate domain errors into HTTP 400/404/503

**Step 5: Run targeted tests**

Run: `cd backend && uv run pytest backend/tests/api/test_task_services.py -k prompt_draft -v`
Expected: PASS for schema and routing behavior.

**Step 6: Commit**

```bash
git add backend/app/schemas/task.py backend/app/api/endpoints/adapter/tasks.py backend/tests/api/test_task_services.py
git commit -m "feat(backend): add prompt draft generation endpoint"
```

## Task 3: Add backend service for conversation packaging

**Files:**
- Create: `backend/app/services/prompt_draft_service.py`
- Modify: `backend/app/services/adapters/task_kinds/service.py`
- Modify: `backend/app/services/chat/storage/db.py`
- Test: `backend/tests/services/test_prompt_draft_service.py`

**Step 1: Write failing service tests**

Cover:
- full conversation is loaded in chronological order
- system noise is excluded only when it is not user-visible metadata
- no hard truncation occurs
- too-short conversations raise a validation error

**Step 2: Run targeted service tests**

Run: `cd backend && uv run pytest backend/tests/services/test_prompt_draft_service.py -v`
Expected: FAIL because the service does not exist.

**Step 3: Implement task-scoped conversation loader**

Service responsibilities:
- verify the task exists and belongs to the user or approved member
- fetch the conversation from the same source of truth used for task detail rendering
- convert subtasks into a normalized message list
- preserve full message content
- reject conversations below the minimum threshold

**Step 4: Keep data access DRY**

If task detail helpers already expose suitable message fetching, extract and reuse them rather than re-querying ad hoc.

**Step 5: Run service tests**

Run: `cd backend && uv run pytest backend/tests/services/test_prompt_draft_service.py -v`
Expected: PASS.

**Step 6: Commit**

```bash
git add backend/app/services/prompt_draft_service.py backend/app/services/adapters/task_kinds/service.py backend/app/services/chat/storage/db.py backend/tests/services/test_prompt_draft_service.py
git commit -m "feat(backend): package full conversation for prompt draft generation"
```

## Task 4: Add system skill scaffold

**Files:**
- Create: `backend/init_data/skills/conversation_to_prompt/SKILL.md`
- Create: `backend/init_data/skills/conversation_to_prompt/__init__.py`
- Create: `backend/init_data/skills/conversation_to_prompt/provider.py`
- Test: `backend/tests/services/chat_shell/test_conversation_to_prompt_skill.py`

**Step 1: Write failing skill contract tests**

Cover:
- strict JSON output contract
- mixed mode structure contains `title` and `prompt`
- prompt starts with `你是...助手`
- prompt includes `你的工作方式` and `处理任务时请遵循以下原则`
- one-shot task summary output is rejected by evaluation

**Step 2: Run targeted skill tests**

Run: `cd backend && uv run pytest backend/tests/services/chat_shell/test_conversation_to_prompt_skill.py -v`
Expected: FAIL because the skill does not exist.

**Step 3: Create built-in system skill**

`SKILL.md` should define:
- purpose
- input contract
- output contract
- multi-stage execution instructions
- evaluation criteria
- rewrite-on-failure rule

Generated prompt structure must be fixed to a directly reusable system prompt:
- paragraph 1: `你是{助手身份}，负责{核心职责}`
- paragraph 2: `你的工作方式`
- paragraph 3: `处理任务时请遵循以下原则`
- paragraph 4: `输出要求`

**Step 4: Add provider glue only if required by current skill loading pattern**

Keep this minimal. Do not let the skill read the database or task table directly.

**Step 5: Run skill tests**

Run: `cd backend && uv run pytest backend/tests/services/chat_shell/test_conversation_to_prompt_skill.py -v`
Expected: PASS for skill packaging and contract checks.

**Step 6: Commit**

```bash
git add backend/init_data/skills/conversation_to_prompt backend/tests/services/chat_shell/test_conversation_to_prompt_skill.py
git commit -m "feat(skills): add conversation to prompt system skill"
```

## Task 5: Add orchestration from backend to chat shell

**Files:**
- Modify: `backend/app/services/prompt_draft_service.py`
- Modify: `backend/app/services/simple_chat/service.py`
- Modify: `backend/app/services/chat/config/model_resolver.py`
- Test: `backend/tests/services/test_prompt_draft_service.py`

**Step 1: Write failing orchestration tests**

Cover:
- explicit model override is respected
- default model is used when request omits model
- backend sends normalized conversation payload and generation requirements
- backend returns strict JSON after chat shell response validation

**Step 2: Run targeted tests**

Run: `cd backend && uv run pytest backend/tests/services/test_prompt_draft_service.py -k orchestration -v`
Expected: FAIL because orchestration is not implemented.

**Step 3: Implement orchestration**

Responsibilities:
- choose the effective model
- invoke the built-in skill with conversation payload
- validate JSON response shape
- surface structured errors for invalid model, execution failure, and malformed output

Validation must also reject prompt bodies that do not match the required system-prompt structure.

**Step 4: Keep evaluation inside the skill**

Do not expose scoring or internal stage details in the API response.

**Step 5: Run targeted tests**

Run: `cd backend && uv run pytest backend/tests/services/test_prompt_draft_service.py -v`
Expected: PASS.

**Step 6: Commit**

```bash
git add backend/app/services/prompt_draft_service.py backend/app/services/simple_chat/service.py backend/app/services/chat/config/model_resolver.py backend/tests/services/test_prompt_draft_service.py
git commit -m "feat(backend): orchestrate conversation prompt draft generation"
```

## Task 6: Add frontend API client and local draft persistence

**Files:**
- Modify: `frontend/src/apis/tasks.ts`
- Create: `frontend/src/features/pet/utils/promptDraftStorage.ts`
- Test: `frontend/src/__tests__/features/pet/promptDraftStorage.test.ts`

**Step 1: Write failing frontend unit tests for local persistence**

Cover:
- save draft by `task_id`
- load latest draft for `task_id`
- overwrite prior draft for same `task_id`
- tolerate malformed localStorage payload

**Step 2: Run targeted tests**

Run: `cd frontend && npm test -- promptDraftStorage`
Expected: FAIL because the storage module does not exist.

**Step 3: Add task API method**

Add `generatePromptDraft(taskId, request)` to `frontend/src/apis/tasks.ts`.

**Step 4: Add browser-local persistence helper**

Keep the stored payload minimal:
- `title`
- `prompt`
- `model`
- `version`
- `created_at`
- `sourceConversationId`

**Step 5: Run targeted tests**

Run: `cd frontend && npm test -- promptDraftStorage`
Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/src/apis/tasks.ts frontend/src/features/pet/utils/promptDraftStorage.ts frontend/src/__tests__/features/pet/promptDraftStorage.test.ts
git commit -m "feat(frontend): add prompt draft api client and local storage helper"
```

## Task 7: Add pet panel action and lightweight bubble state

**Files:**
- Modify: `frontend/src/features/pet/components/PetWidget.tsx`
- Modify: `frontend/src/features/pet/components/PetNotificationPanel.tsx`
- Modify: `frontend/src/features/pet/contexts/PetContext.tsx`
- Modify: `frontend/src/i18n/locales/zh-CN/pet.json`
- Modify: `frontend/src/i18n/locales/en/pet.json`
- Test: `frontend/src/__tests__/features/pet/PetNotificationPanel.test.tsx`

**Step 1: Write failing component tests**

Cover:
- pet panel renders the new CTA
- CTA can be clicked without hover regressions
- lightweight bubble can render and dismiss independently

**Step 2: Run targeted tests**

Run: `cd frontend && npm test -- PetNotificationPanel`
Expected: FAIL because the CTA and bubble behavior do not exist.

**Step 3: Add lightweight pet suggestion state**

Add minimal client-only state for:
- whether the suggestion bubble is visible
- last dismissed timestamp
- current task context gating

Behavior:
- pet may show the suggestion occasionally
- dismiss automatically
- panel action remains accessible afterward

**Step 4: Add CTA to panel**

Preferred i18n keys:
- `panel.prompt_draft.cta`
- `panel.prompt_draft.subtext`
- `bubble.prompt_draft`

**Step 5: Preserve current pet interactions**

Do not break:
- drag behavior
- close button
- busy thinking bubble
- existing task stats

**Step 6: Run targeted tests**

Run: `cd frontend && npm test -- PetNotificationPanel`
Expected: PASS.

**Step 7: Commit**

```bash
git add frontend/src/features/pet/components/PetWidget.tsx frontend/src/features/pet/components/PetNotificationPanel.tsx frontend/src/features/pet/contexts/PetContext.tsx frontend/src/i18n/locales/zh-CN/pet.json frontend/src/i18n/locales/en/pet.json frontend/src/__tests__/features/pet/PetNotificationPanel.test.tsx
git commit -m "feat(frontend): add pet entrypoint for prompt draft generation"
```

## Task 8: Build generation dialog and integrate existing prompt fine-tune flow

**Files:**
- Create: `frontend/src/features/pet/components/PromptDraftDialog.tsx`
- Modify: `frontend/src/features/pet/components/index.ts`
- Modify: `frontend/src/features/pet/components/PetWidget.tsx`
- Modify: `frontend/src/features/settings/components/prompt-fine-tune/PromptFineTuneDialog.tsx`
- Test: `frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx`

**Step 1: Write failing dialog tests**

Cover:
- initial state renders description and model selector
- generate button starts request and shows loading state
- success state shows `title + prompt`
- `重新生成` retriggers request
- `进入微调` opens existing prompt fine-tune dialog with generated prompt

**Step 2: Run targeted tests**

Run: `cd frontend && npm test -- PromptDraftDialog`
Expected: FAIL because the dialog does not exist.

**Step 3: Build the dialog**

State machine:
- idle
- loading
- success
- error

Data flow:
- fetch draft from local storage on open
- call backend on generate
- persist result locally on success
- hand generated prompt into `PromptFineTuneDialog`

**Step 4: Reuse existing prompt fine-tune**

Do not fork a second tuning experience. Use the current dialog and pass the generated draft as `initialPrompt`.

**Step 5: Add `data-testid` hooks**

Required IDs:
- `pet-prompt-draft-button`
- `prompt-draft-dialog`
- `prompt-draft-generate-button`
- `prompt-draft-regenerate-button`
- `prompt-draft-fine-tune-button`

**Step 6: Run targeted tests**

Run: `cd frontend && npm test -- PromptDraftDialog`
Expected: PASS.

**Step 7: Commit**

```bash
git add frontend/src/features/pet/components/PromptDraftDialog.tsx frontend/src/features/pet/components/index.ts frontend/src/features/pet/components/PetWidget.tsx frontend/src/features/settings/components/prompt-fine-tune/PromptFineTuneDialog.tsx frontend/src/__tests__/features/pet/PromptDraftDialog.test.tsx
git commit -m "feat(frontend): add prompt draft generation dialog"
```

## Task 9: Wire task context and current chat page integration

**Files:**
- Inspect: `frontend/src/app/(tasks)/chat/ChatPageDesktop.tsx`
- Inspect: `frontend/src/app/(tasks)/chat/ChatPageMobile.tsx`
- Modify: `frontend/src/features/tasks/contexts/taskContext.tsx`
- Modify: `frontend/src/features/tasks/hooks/useUnifiedMessages.ts`
- Test: `frontend/src/__tests__/features/tasks/components/message/MessagesArea.memo.test.tsx`

**Step 1: Write failing integration tests where needed**

Cover:
- current active task id is available to the pet flow
- group chat or missing task states disable generation gracefully

**Step 2: Run targeted tests**

Run: `cd frontend && npm test -- MessagesArea.memo`
Expected: FAIL if task context is insufficient for the dialog trigger.

**Step 3: Add minimal task-context plumbing**

The pet flow needs:
- current active task id
- current task title if needed for telemetry only

Do not duplicate message source of truth.

**Step 4: Ensure the flow degrades safely**

If no active task exists, CTA can render disabled with helper text instead of crashing.

**Step 5: Run targeted tests**

Run: `cd frontend && npm test -- MessagesArea.memo`
Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/src/features/tasks/contexts/taskContext.tsx frontend/src/features/tasks/hooks/useUnifiedMessages.ts frontend/src/__tests__/features/tasks/components/message/MessagesArea.memo.test.tsx
git commit -m "feat(frontend): connect pet prompt draft flow to active task context"
```

## Task 10: Add backend and frontend translations, analytics hooks, and docs

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN/pet.json`
- Modify: `frontend/src/i18n/locales/en/pet.json`
- Modify: `frontend/src/i18n/locales/zh-CN/promptTune.json`
- Modify: `frontend/src/i18n/locales/en/promptTune.json`
- Modify: `docs/zh/` and `docs/en/` only if user-facing docs are required

**Step 1: Add missing copy keys**

Required copy:
- bubble prompt
- panel CTA
- dialog title and description
- loading text
- empty-conversation error
- generate failure error

**Step 2: Verify naming consistency**

Use one namespace per feature and import from `@/hooks/useTranslation`.

**Step 3: Run frontend lint or targeted i18n tests**

Run: `cd frontend && npm test -- i18n`
Expected: PASS or no regressions.

**Step 4: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN/pet.json frontend/src/i18n/locales/en/pet.json frontend/src/i18n/locales/zh-CN/promptTune.json frontend/src/i18n/locales/en/promptTune.json
git commit -m "feat(frontend): add prompt draft flow copy"
```

## Task 11: Verification pass

**Files:**
- Verify: `backend/app/api/endpoints/adapter/tasks.py`
- Verify: `backend/app/services/prompt_draft_service.py`
- Verify: `backend/init_data/skills/conversation_to_prompt/SKILL.md`
- Verify: `frontend/src/features/pet/components/PromptDraftDialog.tsx`
- Verify: `frontend/src/features/pet/components/PetWidget.tsx`

**Step 1: Run backend targeted tests**

Run: `cd backend && uv run pytest backend/tests/api/test_task_services.py backend/tests/services/test_prompt_draft_service.py backend/tests/services/chat_shell/test_conversation_to_prompt_skill.py -v`
Expected: PASS.

**Step 2: Run frontend targeted tests**

Run: `cd frontend && npm test -- PromptDraftDialog PetNotificationPanel promptDraftStorage`
Expected: PASS.

**Step 3: Run focused lint and type checks if available**

Run: `cd frontend && npm run lint`
Expected: PASS.

Run: `cd backend && uv run python -m py_compile app/services/prompt_draft_service.py`
Expected: PASS.

**Step 4: Manual QA**

Checklist:
- open a chat task with enough history
- wait for or force the lightweight pet bubble in development
- click pet panel CTA
- generate a draft
- close and reopen dialog to confirm local persistence
- open fine-tune flow from generated draft
- verify no regression to pet hover, drag, and close interactions

**Step 5: Final commit**

```bash
git add backend frontend docs
git commit -m "feat: add pet-triggered conversation to prompt draft flow"
```

## Non-Goals For This Plan

- No backend persistence of prompt drafts
- No auto-application to team, bot, or ghost prompt config
- No multi-conversation aggregation
- No public visualization of internal evaluation stages
- No hard token-based truncation of conversation history

## Prompt Output Contract

The generated `prompt` is not a prose summary. It must be directly usable as a system prompt body.

Required structure:

```text
你是{助手身份}，负责{核心职责}。

你的工作方式：
- {协作偏好 1}
- {协作偏好 2}

处理任务时请遵循以下原则：
- {任务方法 1}
- {任务方法 2}

输出要求：
- {输出要求 1}
- {输出要求 2}
```

Rules:
- opening sentence must define assistant identity and responsibility
- body must read like reusable instructions, not a meeting summary
- `你的工作方式` focuses on stable collaboration preferences
- `处理任务时请遵循以下原则` focuses on reusable task methods
- `输出要求` constrains response form and quality
- omit one-off project names, temporary goals, and time-sensitive context

## Evaluation Rules For The Skill

The skill evaluation stage must reject or rewrite outputs when any of the following is true:

1. The prompt does not start by defining assistant identity and responsibility.
2. The prompt reads like a summary of the conversation instead of a reusable system prompt.
3. The prompt includes one-off context, concrete project identifiers, or temporary decisions.
4. The prompt is too vague to guide future behavior.
5. The prompt contains conflicting collaboration or output instructions.
