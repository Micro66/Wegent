---
sidebar_position: 1
---

# Task-Level Skill Identity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reframe `skill_identity_token` as task-scoped execution context, introduce one shared task identity context builder, and inject it only into per-task child execution environments for docker sandbox and AI device/local executor runtimes.

**Architecture:** Treat `ExecutionRequest.skill_identity_token` as the single source of truth. Build one shared task identity context from each request, producing the standard fields `WEGENT_SKILL_IDENTITY_TOKEN` and `WEGENT_SKILL_USER_NAME`. Docker sandbox and AI device each adapt that same context at their task startup boundary. The token must never be written into long-lived executor process state, global `os.environ`, or reusable session state.

**Tech Stack:** FastAPI, shared dataclass protocol, Socket.IO WebSocket dispatch, local executor runtime, Claude Code local mode, pytest, uv

---

### Task 1: Lock Down Device WebSocket Protocol Coverage

**Files:**
- Modify: `backend/tests/services/execution/test_dispatcher_websocket.py`
- Reference: `backend/app/services/execution/dispatcher.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_dispatch_websocket_emits_skill_identity_token_in_payload():
    dispatcher = ExecutionDispatcher()
    request = MagicMock()
    request.task_id = 1
    request.subtask_id = 2
    request.message_id = 3
    request.user = {"id": 9}
    request.to_dict.return_value = {
        "task_id": 1,
        "subtask_id": 2,
        "skill_identity_token": "skill-jwt",
    }

    target = ExecutionTarget(
        mode=CommunicationMode.WEBSOCKET,
        namespace="/local-executor",
        event="task:execute",
        room="device:9:device-1",
    )
    emitter = AsyncMock()
    sio = MagicMock()

    with (
        patch("app.core.socketio.get_sio", return_value=sio),
        patch.object(dispatcher, "_set_subtask_executor", AsyncMock()),
        patch("app.services.execution.dispatcher.run_in_main_loop", AsyncMock()),
    ):
        await dispatcher._dispatch_websocket(request, target, emitter)

    emitted_payload = ...
    assert emitted_payload["skill_identity_token"] == "skill-jwt"
```

**Step 2: Run test to verify current behavior**

Run: `cd backend && uv run pytest tests/services/execution/test_dispatcher_websocket.py -v`
Expected: FAIL until the test captures the emitted payload correctly or reveals that the field is missing.

**Step 3: Adjust or minimally fix implementation if needed**

```python
payload = request.to_dict()
await self._emit_socketio_in_main_loop(sio, target, payload)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/services/execution/test_dispatcher_websocket.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/tests/services/execution/test_dispatcher_websocket.py backend/app/services/execution/dispatcher.py
git commit -m "test(backend): cover skill identity token in websocket dispatch"
```

### Task 2: Lock Down Local Executor Request Deserialization

**Files:**
- Create: `executor/tests/modes/local/test_task_dispatch_handler.py`
- Reference: `executor/modes/local/handlers.py`
- Reference: `shared/models/execution.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_handle_task_dispatch_preserves_skill_identity_token():
    runner = AsyncMock()
    handler = TaskHandler(runner)

    await handler.handle_task_dispatch(
        {
            "task_id": 1,
            "subtask_id": 2,
            "skill_identity_token": "skill-jwt",
        }
    )

    request = runner.enqueue_task.await_args.args[0]
    assert request.skill_identity_token == "skill-jwt"
```

**Step 2: Run test to verify it fails or prove existing behavior**

Run: `cd executor && uv run pytest tests/modes/local/test_task_dispatch_handler.py -v`
Expected: Either FAIL because test file is new or PASS immediately and documents current behavior.

**Step 3: Write minimal implementation if needed**

```python
execution_request = ExecutionRequest.from_dict(data)
await self.runner.enqueue_task(execution_request)
```

**Step 4: Run test to verify it passes**

Run: `cd executor && uv run pytest tests/modes/local/test_task_dispatch_handler.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add executor/tests/modes/local/test_task_dispatch_handler.py executor/modes/local/handlers.py
git commit -m "test(executor): cover skill identity token in local dispatch handler"
```

### Task 3: Extract Shared Task Identity Context Builder

**Files:**
- Create or Modify: exact executor-side helper file discovered during implementation
- Add test: exact executor-side helper test file discovered during implementation
- Reference: `shared/models/execution.py`

**Step 1: Write the failing test**

```python
def test_build_task_identity_context_returns_standard_skill_identity_env():
    request = ExecutionRequest(
        user_name="alice",
        skill_identity_token="skill-jwt",
    )

    env = build_task_identity_context(request)

    assert env == {
        "WEGENT_SKILL_IDENTITY_TOKEN": "skill-jwt",
        "WEGENT_SKILL_USER_NAME": "alice",
    }
```

**Step 2: Run test to verify it fails**

Run: `cd executor && uv run pytest <helper-test-file> -v`
Expected: FAIL because the helper does not exist yet.

**Step 3: Write minimal implementation**

```python
def build_task_identity_context(request: ExecutionRequest) -> dict[str, str]:
    env = {}
    if request.skill_identity_token:
        env["WEGENT_SKILL_IDENTITY_TOKEN"] = request.skill_identity_token
    if request.user_name:
        env["WEGENT_SKILL_USER_NAME"] = request.user_name
    return env
```

**Step 4: Run test to verify it passes**

Run: `cd executor && uv run pytest <helper-test-file> -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add <helper-file> <helper-test-file>
git commit -m "refactor(executor): add task identity context builder"
```

### Task 4: Inject Shared Task Identity Context into ClaudeCode Task Environment

**Files:**
- Modify: `executor/agents/claude_code/local_mode_strategy.py`
- Modify: `executor/agents/claude_code/config_manager.py`
- Modify: shared helper introduced in Task 3 if wiring changes require it
- Add or Modify Test: `executor/tests/agents/claude_code/test_local_mode_strategy.py`

**Step 1: Write the failing test**

```python
def test_local_mode_strategy_injects_task_skill_identity_token():
    strategy = LocalModeStrategy()
    options = {"env": {"EXISTING": "1"}}
    env_config = {"ANTHROPIC_AUTH_TOKEN": "secret"}

    updated = strategy.configure_client_options(
        options=options,
        config_dir="/tmp/task/.claude",
        env_config=env_config,
    )

    assert updated["env"]["WEGENT_SKILL_IDENTITY_TOKEN"] == "skill-jwt"
```

Adjust the setup so the test flows from a real `ExecutionRequest` or helper that includes:

```python
ExecutionRequest(skill_identity_token="skill-jwt", ...)
```

**Step 2: Run test to verify it fails**

Run: `cd executor && uv run pytest tests/agents/claude_code/test_local_mode_strategy.py -v`
Expected: FAIL because no task-scoped token is injected yet.

**Step 3: Write minimal implementation**

Preferred implementation direction:

```python
task_identity_env = build_task_identity_context(task_data)
updated_options["env"] = {
    **updated_options.get("env", {}),
    **env_config,
    **task_identity_env,
}
```

Important:
- Inject only into the child task env
- Do not write to global `os.environ`
- If Claude session/client objects are reused, refresh the task identity env on every task boundary

**Step 4: Run test to verify it passes**

Run: `cd executor && uv run pytest tests/agents/claude_code/test_local_mode_strategy.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add executor/agents/claude_code/local_mode_strategy.py executor/agents/claude_code/config_manager.py executor/tests/agents/claude_code/test_local_mode_strategy.py <helper-file>
git commit -m "feat(executor): inject skill identity token into claude task env"
```

### Task 5: Evaluate and Patch Agno Task Environment Injection

**Files:**
- Inspect: `executor/agents/agno/*.py`
- Modify as needed: exact file discovered during implementation
- Add test: `executor/tests/agents/agno/test_task_env_skill_identity.py`

**Step 1: Trace the real Agno task startup boundary**

Read:

```bash
cd executor && rg -n "env|ExecutionRequest|agent_config" agents/agno -g '*.py'
```

Expected: find the point where per-task config is translated into runtime options.

**Step 2: Write failing test at the actual boundary**

```python
def test_agno_task_env_includes_skill_identity_token():
    ...
    assert runtime_env["WEGENT_SKILL_IDENTITY_TOKEN"] == "skill-jwt"
```

**Step 3: Implement the minimal fix if Agno uses child env**

```python
runtime_env.update(build_task_identity_context(task_data))
```

If Agno has no child env abstraction yet, stop and make the narrowest possible per-task config extension instead of introducing a new framework-wide abstraction.

**Step 4: Run the targeted test**

Run: `cd executor && uv run pytest tests/agents/agno/test_task_env_skill_identity.py -v`
Expected: PASS or explicit documented deferral if Agno path does not use skill HTTP flows.

**Step 5: Commit**

```bash
git add executor/tests/agents/agno/test_task_env_skill_identity.py executor/agents/agno/*.py <helper-file>
git commit -m "feat(executor): align agno task env with skill identity token"
```

### Task 6: Adapt Sandbox Docker Injection to the Shared Task Identity Context

**Files:**
- Modify: `executor_manager/executors/docker/executor.py`
- Reuse or extend tests:
  - `executor_manager/tests/executors/test_docker_executor.py`
  - `executor_manager/tests/services/test_sandbox_manager.py`
- Reference: shared helper / shared contract introduced above

**Step 1: Run existing sandbox tests before touching anything**

Run: `cd executor_manager && uv run pytest tests/executors/test_docker_executor.py tests/services/test_sandbox_manager.py -v`
Expected: PASS and establish current behavior baseline.

**Step 2: Switch docker injection to use the same standard context fields**

Example:

```python
task_identity_env = build_task_identity_context(task_request)
for key, value in task_identity_env.items():
    cmd.extend(["-e", f"{key}={value}"])
```

**Step 3: Re-run sandbox tests**

Run: `cd executor_manager && uv run pytest tests/executors/test_docker_executor.py tests/services/test_sandbox_manager.py -v`
Expected: PASS.

**Step 4: Commit**

```bash
git add executor_manager/executors/docker/executor.py executor_manager/services/sandbox/manager.py executor_manager/tests/executors/test_docker_executor.py executor_manager/tests/services/test_sandbox_manager.py
git commit -m "test(executor-manager): preserve task-scoped sandbox skill identity injection"
```

### Task 7: Add Guardrails Against Long-Lived State Leakage

**Files:**
- Add or modify tests at the actual stateful boundary discovered during implementation
- Likely:
  - executor session/client management tests
  - Claude local mode tests

**Step 1: Write a failing test for forbidden storage**

Examples:

```python
def test_task_identity_token_is_not_written_to_global_os_environ():
    ...


def test_reused_session_refreshes_task_identity_env_per_request():
    ...
```

**Step 2: Run the targeted tests**

Run: `cd executor && uv run pytest <stateful-boundary-tests> -v`
Expected: FAIL until the boundary is protected.

**Step 3: Implement the narrowest fix**

Requirements:
- No writes to process-global `os.environ` for task token fields
- No caching of task token in singletons
- Reused session/client state must derive token from the current request

**Step 4: Re-run the targeted tests**

Run: `cd executor && uv run pytest <stateful-boundary-tests> -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add executor <stateful-boundary-test-files>
git commit -m "test(executor): prevent long-lived skill identity token leakage"
```

### Task 8: Add End-to-End Regression Coverage for the Two Runtime Families

**Files:**
- Modify or add exact tests discovered during implementation
- Likely:
  - `backend/tests/init_data/skills/sandbox/test_provider.py`
  - `chat_shell/tests/test_sandbox_skill_identity.py`
  - new executor-side integration-style tests

**Step 1: Write the minimal regression matrix**

Cover these assertions:

```python
# sandbox path
assert sandbox_metadata["skill_identity_token"] == "skill-jwt"

# device/local executor path
assert task_env["WEGENT_SKILL_IDENTITY_TOKEN"] == "skill-jwt"
```

**Step 2: Run focused suites**

Run:

```bash
cd backend && uv run pytest tests/services/execution/test_request_builder_skill_identity.py tests/services/execution/test_dispatcher_websocket.py -v
cd chat_shell && uv run pytest tests/test_skill_mcp_loader.py tests/test_sandbox_skill_identity.py -v
cd executor && uv run pytest tests/modes/local/test_task_dispatch_handler.py tests/agents/claude_code/test_local_mode_strategy.py -v
cd executor_manager && uv run pytest tests/executors/test_docker_executor.py tests/services/test_sandbox_manager.py -v
```

Expected: PASS.

**Step 3: Commit**

```bash
git add backend chat_shell executor executor_manager
git commit -m "test(skill-identity): cover task-scoped injection across runtimes"
```

### Task 9: Update Design Notes to Prevent Future Drift

**Files:**
- Modify: `docs/plans/2026-03-29-skill-http-identity-design.md`
- Keep: `docs/plans/2026-03-30-task-level-skill-identity-design.md`

**Step 1: Add a short note clarifying the corrected model**

```markdown
Update: `skill_identity_token` is task-scoped. Docker env is only one runtime-specific carrier, not the protocol itself.
```

**Step 2: Verify docs are internally consistent**

Run:

```bash
rg -n "不设置过期时间|容器级|进程级" docs/plans/2026-03-29-skill-http-identity-design.md docs/plans/2026-03-30-task-level-skill-identity-design.md
```

Expected: no stale wording remains unaddressed.

**Step 3: Commit**

```bash
git add docs/plans/2026-03-29-skill-http-identity-design.md docs/plans/2026-03-30-task-level-skill-identity-design.md docs/plans/2026-03-30-task-level-skill-identity-implementation-plan.md
git commit -m "docs(skill-identity): document task-scoped runtime injection model"
```
