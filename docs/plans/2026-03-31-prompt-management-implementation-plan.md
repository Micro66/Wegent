# Prompt Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a chat-native prompt management workflow that lets authorized users inspect, optimize, and apply an agent's base prompt through skill + MCP + chat blocks, without adding new database tables.

**Architecture:** Add a new `prompt-manager` skill backed by a dedicated Prompt MCP server that reuses the existing `@mcp_tool` auto-registration pattern. Resolve the editable prompt from the existing Team/adapter path, generate prompt candidates on demand, and pass candidate state through chat blocks instead of database persistence.

**Tech Stack:** FastAPI, SQLAlchemy, FastMCP, Pydantic, Next.js 15, React 19, TypeScript, Tailwind CSS, Playwright, pytest, uv.

---

### Task 1: Build backend prompt management service on top of existing Team prompt storage

**Files:**
- Create: `backend/app/services/prompt_management/service.py`
- Create: `backend/app/services/prompt_management/__init__.py`
- Modify: `backend/app/services/adapters/team_kinds.py`
- Modify: `backend/app/schemas/team.py`
- Test: `backend/tests/services/test_prompt_management_service.py`

**Step 1: Write the failing service tests**

```python
def test_get_base_prompt_requires_edit_permission():
    result = prompt_management_service.get_base_prompt(...)
    assert result["error"] == "permission_denied"


def test_apply_prompt_revision_updates_team_prompt():
    result = prompt_management_service.apply_prompt_revision(...)
    assert result["applied_prompt"] == "new prompt"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest backend/tests/services/test_prompt_management_service.py -v`
Expected: FAIL because prompt management service does not exist.

**Step 3: Write minimal implementation**

- Add a service that resolves current task -> current team -> editable prompt field.
- Reuse existing Team edit permission rules (`Developer+` for group teams).
- Implement:
  - `get_base_prompt`
  - `apply_prompt_revision`
- Ensure updates go through the existing Team prompt storage path instead of creating new models.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest backend/tests/services/test_prompt_management_service.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/prompt_management/service.py backend/app/services/prompt_management/__init__.py backend/app/services/adapters/team_kinds.py backend/app/schemas/team.py backend/tests/services/test_prompt_management_service.py
git commit -m "feat(backend): add prompt management service"
```

### Task 2: Add prompt optimization generation flow without persistence

**Files:**
- Create: `backend/app/services/prompt_management/optimizer.py`
- Modify: `backend/app/services/prompt_management/service.py`
- Test: `backend/tests/services/test_prompt_management_service.py`

**Step 1: Write the failing optimization tests**

```python
def test_propose_prompt_revision_returns_diff_and_optimized_prompt():
    result = prompt_management_service.propose_prompt_revision(...)
    assert result["optimized_prompt"]
    assert result["diff"]


def test_propose_prompt_revision_can_use_current_prompt_override():
    result = prompt_management_service.propose_prompt_revision(current_prompt="candidate", ...)
    assert result["original_prompt"] == "candidate"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest backend/tests/services/test_prompt_management_service.py -k "propose_prompt_revision" -v`
Expected: FAIL because optimizer flow is missing.

**Step 3: Write minimal implementation**

- Add an optimizer abstraction that accepts current prompt and user feedback.
- Produce:
  - optimized prompt
  - summary
  - line-based diff JSON
- Do not persist candidate output to the database.
- Accept optional `current_prompt` so frontend can submit the current candidate for repeated optimization.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest backend/tests/services/test_prompt_management_service.py -k "propose_prompt_revision" -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/prompt_management/optimizer.py backend/app/services/prompt_management/service.py backend/tests/services/test_prompt_management_service.py
git commit -m "feat(backend): add prompt revision generation"
```

### Task 3: Expose prompt management via MCP tools using `@mcp_tool`

**Files:**
- Create: `backend/app/mcp_server/tools/prompt.py`
- Modify: `backend/app/mcp_server/tools/__init__.py`
- Modify: `backend/app/mcp_server/server.py`
- Modify: `backend/app/mcp_server/__init__.py`
- Test: `backend/tests/mcp_server/test_prompt_tools.py`
- Test: `backend/tests/mcp_server/test_server_routes.py`

**Step 1: Write the failing MCP tests**

```python
def test_prompt_tools_are_registered_to_prompt_server():
    tools = get_registered_mcp_tools(server="prompt")
    assert "get_base_prompt" in tools


def test_prompt_mcp_root_returns_metadata_json():
    response = client.get("/mcp/prompt")
    assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest backend/tests/mcp_server/test_prompt_tools.py backend/tests/mcp_server/test_server_routes.py -v`
Expected: FAIL because prompt MCP server and tools do not exist.

**Step 3: Write minimal implementation**

- Add `prompt.py` MCP tools with `@mcp_tool(server="prompt")`:
  - `get_base_prompt`
  - `propose_prompt_revision`
  - `apply_prompt_revision`
- Add a new FastMCP prompt server.
- Register prompt tools in backend startup using the same pattern as knowledge MCP.
- Add metadata helper and `/mcp/prompt/sse` endpoint wiring.

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest backend/tests/mcp_server/test_prompt_tools.py backend/tests/mcp_server/test_server_routes.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/mcp_server/tools/prompt.py backend/app/mcp_server/tools/__init__.py backend/app/mcp_server/server.py backend/app/mcp_server/__init__.py backend/tests/mcp_server/test_prompt_tools.py backend/tests/mcp_server/test_server_routes.py
git commit -m "feat(backend): expose prompt management over mcp"
```

### Task 4: Add the `prompt-manager` skill definition

**Files:**
- Create: `backend/init_data/skills/prompt-manager/SKILL.md`
- Test: `backend/tests/services/chat_shell/test_prompt_manager_skill.py`

**Step 1: Write the failing skill configuration test**

```python
def test_prompt_manager_skill_declares_prompt_mcp_server():
    skill = load_skill("prompt-manager")
    assert "wegent-prompt" in skill["mcpServers"]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest backend/tests/services/chat_shell/test_prompt_manager_skill.py -v`
Expected: FAIL because the skill file does not exist.

**Step 3: Write minimal implementation**

- Add `SKILL.md` with frontmatter mirroring the knowledge skill pattern.
- Document supported operations and hard rules:
  - query current prompt
  - optimize prompt
  - do not auto-apply
  - deny without permission

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest backend/tests/services/chat_shell/test_prompt_manager_skill.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/init_data/skills/prompt-manager/SKILL.md backend/tests/services/chat_shell/test_prompt_manager_skill.py
git commit -m "feat(skill): add prompt manager skill"
```

### Task 5: Extend chat message block types for prompt blocks

**Files:**
- Modify: `frontend/src/features/tasks/components/message/thinking/types.ts`
- Modify: `frontend/src/features/tasks/components/message/thinking/MixedContentView.tsx`
- Create: `frontend/src/features/tasks/components/message/prompt/PromptViewBlock.tsx`
- Create: `frontend/src/features/tasks/components/message/prompt/PromptCandidateBlock.tsx`
- Create: `frontend/src/features/tasks/components/message/prompt/PromptAppliedBlock.tsx`
- Test: `frontend/src/__tests__/features/tasks/components/message/prompt-blocks.test.tsx`

**Step 1: Write the failing frontend rendering tests**

```tsx
it('renders prompt candidate block with diff and action buttons', () => {
  render(<MixedContentView blocks={[candidateBlock]} ... />)
  expect(screen.getByTestId('prompt-candidate-block')).toBeInTheDocument()
  expect(screen.getByTestId('apply-prompt-button')).toBeInTheDocument()
})
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --runInBand prompt-blocks.test.tsx`
Expected: FAIL because prompt block types and components do not exist.

**Step 3: Write minimal implementation**

- Extend `MessageBlock` to support prompt block types or prompt metadata payloads.
- Add dedicated prompt block components.
- Render prompt blocks inside `MixedContentView` before falling back to generic text/tool rendering.
- Add `data-testid` to all new interactive controls.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --runInBand prompt-blocks.test.tsx`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/features/tasks/components/message/thinking/types.ts frontend/src/features/tasks/components/message/thinking/MixedContentView.tsx frontend/src/features/tasks/components/message/prompt/PromptViewBlock.tsx frontend/src/features/tasks/components/message/prompt/PromptCandidateBlock.tsx frontend/src/features/tasks/components/message/prompt/PromptAppliedBlock.tsx frontend/src/__tests__/features/tasks/components/message/prompt-blocks.test.tsx
git commit -m "feat(frontend): render prompt management blocks"
```

### Task 6: Wire prompt block actions to backend APIs/MCP-triggered operations

**Files:**
- Create: `frontend/src/apis/prompt-management.ts`
- Modify: `frontend/src/features/tasks/components/message/prompt/PromptCandidateBlock.tsx`
- Modify: `frontend/src/features/tasks/components/message/prompt/PromptAppliedBlock.tsx`
- Modify: `frontend/src/features/tasks/components/chat/ChatArea.tsx`
- Test: `frontend/src/__tests__/apis/prompt-management.test.ts`
- Test: `frontend/src/__tests__/features/tasks/components/message/prompt-actions.test.tsx`

**Step 1: Write the failing action tests**

```tsx
it('calls apply api when user clicks replace prompt', async () => {
  render(<PromptCandidateBlock ... />)
  await user.click(screen.getByTestId('apply-prompt-button'))
  expect(promptManagementApis.applyPromptRevision).toHaveBeenCalled()
})
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --runInBand prompt-actions.test.tsx prompt-management.test.ts`
Expected: FAIL because the API module and action handlers do not exist.

**Step 3: Write minimal implementation**

- Add frontend API wrapper for prompt-management actions.
- Wire button clicks to apply prompt updates.
- When user clicks “再次优化”, submit the current candidate prompt back to `propose_prompt_revision`.
- Ensure success/error states update block UI without removing the chat history.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --runInBand prompt-actions.test.tsx prompt-management.test.ts`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/apis/prompt-management.ts frontend/src/features/tasks/components/message/prompt/PromptCandidateBlock.tsx frontend/src/features/tasks/components/message/prompt/PromptAppliedBlock.tsx frontend/src/features/tasks/components/chat/ChatArea.tsx frontend/src/__tests__/apis/prompt-management.test.ts frontend/src/__tests__/features/tasks/components/message/prompt-actions.test.tsx
git commit -m "feat(frontend): wire prompt management actions"
```

### Task 7: Add end-to-end coverage and docs updates

**Files:**
- Create: `frontend/e2e/tests/tasks/prompt-management.spec.ts`
- Modify: `frontend/e2e/pages/...` (create exact page objects only if needed)
- Modify: `docs/zh/developer-guide/...` or user-facing docs if implementation changes require it
- Modify: `docs/en/developer-guide/...` or user-facing docs if implementation changes require it

**Step 1: Write the failing E2E scenario**

```ts
test('authorized user can optimize and apply prompt from chat', async ({ page }) => {
  await page.getByTestId('chat-input').fill('帮我改下提示词')
  await page.getByTestId('send-button').click()
  await expect(page.getByTestId('prompt-candidate-block')).toBeVisible()
  await page.getByTestId('apply-prompt-button').click()
  await expect(page.getByTestId('prompt-applied-block')).toBeVisible()
})
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npx playwright test frontend/e2e/tests/tasks/prompt-management.spec.ts`
Expected: FAIL because the flow is not implemented yet.

**Step 3: Write minimal implementation/supporting fixtures**

- Add any required page objects or selectors.
- Add test setup data for an editable team with prompt-manager skill enabled.
- Add Chinese docs first, then English docs if user-facing behavior needs documentation.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npx playwright test frontend/e2e/tests/tasks/prompt-management.spec.ts`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/e2e/tests/tasks/prompt-management.spec.ts docs/zh docs/en
git commit -m "test(e2e): cover prompt management workflow"
```

### Task 8: Full verification pass

**Files:**
- Modify: only files needed to fix verification failures

**Step 1: Run backend verification**

Run: `cd backend && uv run pytest backend/tests/services/test_prompt_management_service.py backend/tests/mcp_server/test_prompt_tools.py backend/tests/mcp_server/test_server_routes.py backend/tests/services/chat_shell/test_prompt_manager_skill.py -v`
Expected: PASS.

**Step 2: Run frontend unit verification**

Run: `cd frontend && npm test -- --runInBand prompt-blocks.test.tsx prompt-actions.test.tsx prompt-management.test.ts`
Expected: PASS.

**Step 3: Run E2E verification**

Run: `cd frontend && npx playwright test frontend/e2e/tests/tasks/prompt-management.spec.ts`
Expected: PASS.

**Step 4: Run formatting/lint checks**

Run: `cd backend && uv run black . && uv run isort .`
Expected: PASS.

Run: `cd frontend && npm run format && npm run lint`
Expected: PASS.

**Step 5: Commit final fixes**

```bash
git add backend frontend docs
git commit -m "feat(prompt): finalize prompt management workflow"
```
