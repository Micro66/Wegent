# GroupChat Multi-Agent Switch Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add multi-agent GroupChat support so one group chat can bind multiple Agents, route each message to a selected Agent, and apply group-level history window settings.

**Architecture:** Extend GroupChat task metadata from a single `teamRef` to `teamRefs[]` plus `groupChatConfig.historyWindow`, then thread the selected per-message `team_id` through the frontend input flow and backend chat execution path. Keep read-time compatibility for old single-agent group chats while standardizing all new writes on the new schema.

**Tech Stack:** Next.js 15, React 19, TypeScript, FastAPI, SQLAlchemy, Pydantic, Socket.IO, pytest, Jest/RTL

---

### Task 1: Define Task spec support for multi-agent GroupChat

**Files:**
- Modify: `backend/app/schemas/kind.py`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/types/socket.ts`
- Test: `backend/tests/api/test_openapi_responses.py`

**Step 1: Write the failing test**

Add a schema-focused backend test that validates a GroupChat task payload can carry:
- `spec.teamRefs`
- `spec.groupChatConfig.historyWindow.maxDays`
- `spec.groupChatConfig.historyWindow.maxMessages`

**Step 2: Run test to verify it fails**

Run:
```bash
cd backend && uv run pytest backend/tests/api/test_openapi_responses.py -k groupchat -v
```

Expected: FAIL because the new schema fields are not yet defined.

**Step 3: Write minimal implementation**

Update task-related Pydantic schemas in `backend/app/schemas/kind.py` to add:
- `teamRefs`
- `groupChatConfig.historyWindow`

Update frontend task/socket types to mirror the new fields.

**Step 4: Run test to verify it passes**

Run:
```bash
cd backend && uv run pytest backend/tests/api/test_openapi_responses.py -k groupchat -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/schemas/kind.py frontend/src/types/api.ts frontend/src/types/socket.ts backend/tests/api/test_openapi_responses.py
git commit -m "feat(group-chat): add multi-agent task schema"
```

### Task 2: Make backend read old and new GroupChat agent config safely

**Files:**
- Create: `backend/app/services/chat/group_chat_config.py`
- Modify: `backend/app/services/chat/trigger/group_chat.py`
- Modify: `backend/app/api/ws/chat_namespace.py`
- Test: `backend/tests/services/chat/test_group_chat_config.py`

**Step 1: Write the failing test**

Create tests covering:
- new GroupChat config with `teamRefs[]`
- old GroupChat config with only `teamRef`
- default history window fallback to `2 days / 200 messages`

**Step 2: Run test to verify it fails**

Run:
```bash
cd backend && uv run pytest backend/tests/services/chat/test_group_chat_config.py -v
```

Expected: FAIL because the helper module does not exist.

**Step 3: Write minimal implementation**

Create `group_chat_config.py` with helpers such as:
- `get_group_chat_team_refs(task_json)`
- `is_allowed_group_chat_team(task_json, team_id)`
- `get_group_chat_history_window(task_json)`

Use the helper from `group_chat.py` and `chat_namespace.py`.

**Step 4: Run test to verify it passes**

Run:
```bash
cd backend && uv run pytest backend/tests/services/chat/test_group_chat_config.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/chat/group_chat_config.py backend/app/services/chat/trigger/group_chat.py backend/app/api/ws/chat_namespace.py backend/tests/services/chat/test_group_chat_config.py
git commit -m "refactor(group-chat): centralize group chat config parsing"
```

### Task 3: Enforce selected Agent validation on GroupChat send

**Files:**
- Modify: `backend/app/api/ws/chat_namespace.py`
- Modify: `backend/app/services/chat/storage/task_manager.py`
- Test: `backend/tests/api/ws/test_chat_namespace_group_chat.py`

**Step 1: Write the failing test**

Add websocket send tests for:
- valid `team_id` inside `teamRefs[]` succeeds
- invalid `team_id` outside `teamRefs[]` returns an error
- old single-agent GroupChat still accepts its single team

**Step 2: Run test to verify it fails**

Run:
```bash
cd backend && uv run pytest backend/tests/api/ws/test_chat_namespace_group_chat.py -v
```

Expected: FAIL because validation is missing.

**Step 3: Write minimal implementation**

In `chat_namespace.py`:
- detect GroupChat tasks
- validate `payload.team_id` against allowed team refs
- stop relying on `@TeamName` text matching for Web GroupChat trigger

In `task_manager.py`:
- make sure assistant subtasks preserve the selected `team_id`

**Step 4: Run test to verify it passes**

Run:
```bash
cd backend && uv run pytest backend/tests/api/ws/test_chat_namespace_group_chat.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/api/ws/chat_namespace.py backend/app/services/chat/storage/task_manager.py backend/tests/api/ws/test_chat_namespace_group_chat.py
git commit -m "feat(group-chat): validate per-message target agent"
```

### Task 4: Apply GroupChat history window when building model context

**Files:**
- Modify: `chat_shell/chat_shell/history/loader.py`
- Modify: `backend/app/services/memory/utils.py`
- Modify: `backend/app/services/memory/manager.py`
- Test: `chat_shell/tests/test_messages.py`
- Test: `backend/tests/services/chat/test_group_chat_history_window.py`

**Step 1: Write the failing test**

Add tests that confirm:
- only messages within `maxDays` are included
- final history size does not exceed `maxMessages`
- group chat formatting preserves `User[...]` and `Agent[...]`

**Step 2: Run test to verify it fails**

Run:
```bash
cd chat_shell && uv run pytest chat_shell/tests/test_messages.py -k group -v
cd backend && uv run pytest backend/tests/services/chat/test_group_chat_history_window.py -v
```

Expected: FAIL because history window logic is not implemented.

**Step 3: Write minimal implementation**

Add history-window aware filtering before prompt assembly, then format speakers with explicit labels for:
- users
- agent replies from different teams

Keep the logic shared where possible instead of duplicating per call path.

**Step 4: Run test to verify it passes**

Run:
```bash
cd chat_shell && uv run pytest chat_shell/tests/test_messages.py -k group -v
cd backend && uv run pytest backend/tests/services/chat/test_group_chat_history_window.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add chat_shell/chat_shell/history/loader.py backend/app/services/memory/utils.py backend/app/services/memory/manager.py chat_shell/tests/test_messages.py backend/tests/services/chat/test_group_chat_history_window.py
git commit -m "feat(group-chat): bound shared history by time and count"
```

### Task 5: Support multi-agent GroupChat creation and editing APIs

**Files:**
- Modify: `backend/app/api/endpoints/adapter/task_members.py`
- Modify: `backend/app/services/task_member_service.py`
- Modify: `backend/app/services/chat/storage/task_manager.py`
- Test: `backend/tests/services/test_task_access_control.py`
- Test: `backend/tests/app/services/channels/test_handler.py`

**Step 1: Write the failing test**

Add tests for:
- creating a new GroupChat task with `teamRefs[]`
- defaulting history window to `2 / 200`
- editing GroupChat settings to update `teamRefs[]` and history window

**Step 2: Run test to verify it fails**

Run:
```bash
cd backend && uv run pytest backend/tests/services/test_task_access_control.py backend/tests/app/services/channels/test_handler.py -k group -v
```

Expected: FAIL because create/update paths only support a single team.

**Step 3: Write minimal implementation**

Update task creation and GroupChat service APIs so new or edited group chats:
- write `teamRefs[]`
- write `groupChatConfig.historyWindow`
- continue to expose old `teamRef` only as a compatibility read fallback if needed

**Step 4: Run test to verify it passes**

Run:
```bash
cd backend && uv run pytest backend/tests/services/test_task_access_control.py backend/tests/app/services/channels/test_handler.py -k group -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/api/endpoints/adapter/task_members.py backend/app/services/task_member_service.py backend/app/services/chat/storage/task_manager.py backend/tests/services/test_task_access_control.py backend/tests/app/services/channels/test_handler.py
git commit -m "feat(group-chat): store multi-agent config on group chats"
```

### Task 6: Update frontend GroupChat creation UI for multi-agent config

**Files:**
- Modify: `frontend/src/features/tasks/components/group-chat/CreateGroupChatDialog.tsx`
- Modify: `frontend/src/apis/group-chat.ts`
- Modify: `frontend/src/apis/chat.ts`
- Test: `frontend/src/__tests__/app/(tasks)/chat/ChatPageDesktop.remote-workspace.test.tsx`

**Step 1: Write the failing test**

Add a frontend test that covers:
- selecting multiple agents in the create dialog
- editing default history window values
- submit payload containing `teamRefs[]` and history window

**Step 2: Run test to verify it fails**

Run:
```bash
cd frontend && npm test -- --runInBand "ChatPageDesktop.remote-workspace.test.tsx"
```

Expected: FAIL because the dialog only supports one team and no history settings.

**Step 3: Write minimal implementation**

Change `CreateGroupChatDialog.tsx` to:
- use a multi-select UI for agents
- add numeric inputs for `maxDays` and `maxMessages`
- send the new config shape to the backend

Keep existing `data-testid` values where present and add new ones for new interactive elements.

**Step 4: Run test to verify it passes**

Run:
```bash
cd frontend && npm test -- --runInBand "ChatPageDesktop.remote-workspace.test.tsx"
```

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/features/tasks/components/group-chat/CreateGroupChatDialog.tsx frontend/src/apis/group-chat.ts frontend/src/apis/chat.ts frontend/src/__tests__/app/(tasks)/chat/ChatPageDesktop.remote-workspace.test.tsx
git commit -m "feat(frontend): support multi-agent group chat creation"
```

### Task 7: Add per-message Agent selection and @ autocomplete behavior

**Files:**
- Modify: `frontend/src/features/tasks/components/input/ChatInput.tsx`
- Modify: `frontend/src/features/tasks/components/input/ChatInputCard.tsx`
- Modify: `frontend/src/features/tasks/components/chat/MentionAutocomplete.tsx`
- Modify: `frontend/src/features/tasks/components/chat/ChatArea.tsx`
- Test: `frontend/src/__tests__/features/tasks/components/input/chat-send-state.test.tsx`
- Test: `frontend/src/__tests__/features/tasks/components/chat/streamingJoinWarning.test.ts`

**Step 1: Write the failing test**

Add tests for:
- displaying a GroupChat agent selector
- using `@` to insert an agent mention and sync the current target
- sending a message with the selected `team_id`
- resetting the current target back to the default agent after send

**Step 2: Run test to verify it fails**

Run:
```bash
cd frontend && npm test -- --runInBand "chat-send-state.test.tsx|streamingJoinWarning.test.ts"
```

Expected: FAIL because current input flow only knows one team.

**Step 3: Write minimal implementation**

Update input components so GroupChat can:
- show allowed agents from task config
- set a current message target
- sync `@` autocomplete to that target
- reset to default after a successful send

Pass the selected `team_id` through `ChatArea` into `ChatStreamContext.sendMessage`.

**Step 4: Run test to verify it passes**

Run:
```bash
cd frontend && npm test -- --runInBand "chat-send-state.test.tsx|streamingJoinWarning.test.ts"
```

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/features/tasks/components/input/ChatInput.tsx frontend/src/features/tasks/components/input/ChatInputCard.tsx frontend/src/features/tasks/components/chat/MentionAutocomplete.tsx frontend/src/features/tasks/components/chat/ChatArea.tsx frontend/src/__tests__/features/tasks/components/input/chat-send-state.test.tsx frontend/src/__tests__/features/tasks/components/chat/streamingJoinWarning.test.ts
git commit -m "feat(frontend): route group chat messages to selected agent"
```

### Task 8: Show agent identity on AI messages and history replay

**Files:**
- Modify: `frontend/src/features/tasks/components/message/MessagesArea.tsx`
- Modify: `frontend/src/features/tasks/components/message/MessageBubble.tsx`
- Modify: `frontend/src/features/tasks/state/*`
- Modify: `frontend/src/features/tasks/hooks/useUnifiedMessages.ts`
- Modify: `frontend/src/features/tasks/contexts/chatStreamContext.tsx`
- Modify: `frontend/src/features/tasks/components/chat/useChatStreamHandlers.tsx`
- Test: `frontend/src/__tests__/features/tasks/components/message/chat-task.spec.ts.test.tsx`

**Step 1: Write the failing test**

Add coverage that verifies:
- AI messages display the correct agent name/icon
- history replay preserves agent identity across mixed-agent replies

**Step 2: Run test to verify it fails**

Run:
```bash
cd frontend && npm test -- --runInBand chat-task.spec.ts
```

Expected: FAIL because mixed-agent metadata is not surfaced in the UI.

**Step 3: Write minimal implementation**

Propagate selected-agent metadata from websocket/task payloads into unified messages, then render it in the message header UI.
For streaming replies, preserve the selected Agent identity from the send action until the real task/subtask IDs arrive.

**Step 4: Run test to verify it passes**

Run:
```bash
cd frontend && npm test -- --runInBand chat-task.spec.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/features/tasks/components/message/MessagesArea.tsx frontend/src/features/tasks/components/message/MessageBubble.tsx frontend/src/features/tasks/contexts/chatStreamContext.tsx frontend/src/features/tasks/hooks/useUnifiedMessages.ts frontend/src/features/tasks/components/chat/useChatStreamHandlers.tsx frontend/src/features/tasks/state frontend/src/__tests__/features/tasks/components/message/chat-task.spec.ts.test.tsx
git commit -m "feat(frontend): display replying agent in group chat history"
```

### Task 9: Run focused verification across backend, chat_shell, and frontend

**Files:**
- Modify: `docs/plans/2026-04-17-groupchat-multi-agent-design.md`
- Modify: `docs/plans/2026-04-17-groupchat-multi-agent-implementation-plan.md`

**Step 1: Write the failing test**

No new test file. Assemble the full focused verification command set for the changed surface.

**Step 2: Run test to verify it fails**

Run the most relevant targeted suites first while implementation is in progress; investigate any failures before broadening scope.

**Step 3: Write minimal implementation**

If any failures expose small missing integration details, fix them in the relevant modules before claiming completion.

**Step 4: Run test to verify it passes**

Run:
```bash
cd backend && uv run pytest backend/tests/services/chat/test_group_chat_config.py backend/tests/api/ws/test_chat_namespace_group_chat.py backend/tests/services/chat/test_group_chat_history_window.py -v
cd chat_shell && uv run pytest chat_shell/tests/test_messages.py -k group -v
cd frontend && npm test -- --runInBand "chat-send-state.test.tsx|streamingJoinWarning.test.ts|ChatPageDesktop.remote-workspace.test.tsx|chat-task.spec.ts"
```

Expected: PASS

**Step 5: Commit**

```bash
git add docs/plans/2026-04-17-groupchat-multi-agent-design.md docs/plans/2026-04-17-groupchat-multi-agent-implementation-plan.md
git commit -m "docs(plans): finalize group chat multi-agent implementation plan"
```
