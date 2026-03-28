---
sidebar_position: 1
---

# Skill HTTP Identity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dedicated skill HTTP identity JWT, inject it into executor and sandbox environments, and expose an internal verification endpoint that validates `token + user_name` without revealing token ownership.

**Architecture:** Introduce a separate backend auth module for `skill_identity` JWTs, thread the token through `ExecutionRequest`, generate it during execution request building, inject it into runtime environments, and add a narrow internal API that only returns match status and reason codes. Keep the first version stateless: JWT only, no persistence, no expiration enforcement yet.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, dataclasses, PyJWT/JOSE stack already used by backend, executor-manager Docker runtime, pytest, uv

---

### Task 1: Add Skill Identity Token Auth Module

**Files:**
- Create: `backend/app/services/auth/skill_identity_token.py`
- Modify: `backend/app/services/auth/__init__.py`
- Test: `backend/tests/services/auth/test_skill_identity_token.py`

**Step 1: Write the failing test**

```python
from app.services.auth import create_skill_identity_token, verify_skill_identity_token


def test_create_and_verify_skill_identity_token():
    token = create_skill_identity_token(
        user_id=7,
        user_name="alice",
        runtime_type="executor",
        runtime_name="executor-1",
    )

    info = verify_skill_identity_token(token)

    assert info is not None
    assert info.user_id == 7
    assert info.user_name == "alice"
    assert info.runtime_type == "executor"
    assert info.runtime_name == "executor-1"


def test_verify_skill_identity_token_rejects_wrong_type():
    invalid_token = "..."
    assert verify_skill_identity_token(invalid_token) is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/services/auth/test_skill_identity_token.py -v`
Expected: FAIL with import or function-not-found error.

**Step 3: Write minimal implementation**

```python
# backend/app/services/auth/skill_identity_token.py
@dataclass
class SkillIdentityTokenInfo:
    user_id: int
    user_name: str
    runtime_type: str
    runtime_name: str


def create_skill_identity_token(...):
    payload = {
        "type": "skill_identity",
        "user_id": user_id,
        "user_name": user_name,
        "runtime_type": runtime_type,
        "runtime_name": runtime_name,
        "iat": now,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_skill_identity_token(token: str) -> SkillIdentityTokenInfo | None:
    ...
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/services/auth/test_skill_identity_token.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/auth/skill_identity_token.py backend/app/services/auth/__init__.py backend/tests/services/auth/test_skill_identity_token.py
git commit -m "feat(auth): add skill identity token support"
```

### Task 2: Extend Unified Execution Protocol with Skill Identity Token

**Files:**
- Modify: `shared/models/execution.py`
- Test: `backend/tests/services/execution/test_request_builder_skill_identity_protocol.py`

**Step 1: Write the failing test**

```python
from shared.models.execution import ExecutionRequest


def test_execution_request_round_trips_skill_identity_token():
    request = ExecutionRequest(
        task_id=1,
        subtask_id=2,
        user_id=3,
        user_name="alice",
        skill_identity_token="skill-jwt",
    )

    data = request.to_dict()
    restored = ExecutionRequest.from_dict(data)

    assert restored.skill_identity_token == "skill-jwt"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/services/execution/test_request_builder_skill_identity_protocol.py -v`
Expected: FAIL because field is missing on dataclass.

**Step 3: Write minimal implementation**

```python
# shared/models/execution.py
skill_identity_token: str = ""
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/services/execution/test_request_builder_skill_identity_protocol.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add shared/models/execution.py backend/tests/services/execution/test_request_builder_skill_identity_protocol.py
git commit -m "feat(execution): add skill identity token to unified request"
```

### Task 3: Generate Skill Identity Token in Request Builder

**Files:**
- Modify: `backend/app/services/execution/request_builder.py`
- Test: `backend/tests/services/execution/test_request_builder_skill_identity.py`

**Step 1: Write the failing test**

```python
def test_build_request_generates_skill_identity_token(...):
    result = request_builder.build_execution_request(...)

    assert result.skill_identity_token
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/services/execution/test_request_builder_skill_identity.py -v`
Expected: FAIL because `skill_identity_token` is empty.

**Step 3: Write minimal implementation**

```python
# backend/app/services/execution/request_builder.py
skill_identity_token = self._generate_skill_identity_token(user, subtask)
...
skill_identity_token=skill_identity_token,
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/services/execution/test_request_builder_skill_identity.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/execution/request_builder.py backend/tests/services/execution/test_request_builder_skill_identity.py
git commit -m "feat(execution): generate skill identity token in request builder"
```

### Task 4: Inject Skill Identity Environment Variables into Runtime

**Files:**
- Modify: `executor_manager/executors/docker/executor.py`
- Modify: `executor/config/env_reader.py`
- Modify: `executor/tasks/task_processor.py`
- Test: `executor_manager/tests/executors/test_docker_executor.py`
- Test: `executor/tests/config/test_env_reader.py`

**Step 1: Write the failing test**

```python
def test_sandbox_executor_command_includes_skill_identity_env(...):
    cmd = executor._build_docker_run_command(...)
    assert any(
        isinstance(item, str) and item.startswith("WEGENT_SKILL_IDENTITY_TOKEN=")
        for item in cmd
    )


def test_get_task_info_reads_skill_identity_token_from_task_info():
    ...
```

**Step 2: Run test to verify it fails**

Run: `cd executor_manager && uv run pytest tests/executors/test_docker_executor.py -v`
Expected: FAIL because env vars are missing.

Run: `cd executor && uv run pytest tests/config/test_env_reader.py -v`
Expected: FAIL if reader assertions are added for new fields.

**Step 3: Write minimal implementation**

```python
# executor_manager/executors/docker/executor.py
skill_identity_token = get_metadata_field(task, "skill_identity_token")
if skill_identity_token:
    cmd.extend(["-e", f"WEGENT_SKILL_IDENTITY_TOKEN={skill_identity_token}"])

if user_name:
    cmd.extend(["-e", f"WEGENT_SKILL_USER_NAME={user_name}"])
```

**Step 4: Run test to verify it passes**

Run: `cd executor_manager && uv run pytest tests/executors/test_docker_executor.py -v`
Expected: PASS.

Run: `cd executor && uv run pytest tests/config/test_env_reader.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add executor_manager/executors/docker/executor.py executor/config/env_reader.py executor/tasks/task_processor.py executor_manager/tests/executors/test_docker_executor.py executor/tests/config/test_env_reader.py
git commit -m "feat(runtime): inject skill identity env vars"
```

### Task 5: Add Internal Verification Endpoint

**Files:**
- Create: `backend/app/api/endpoints/internal/skill_identity.py`
- Modify: `backend/app/api/endpoints/internal/__init__` or router registration location
- Test: `backend/tests/api/endpoints/internal/test_skill_identity_api.py`

**Step 1: Write the failing test**

```python
def test_verify_skill_identity_returns_true_for_matching_user(client):
    token = create_skill_identity_token(
        user_id=1,
        user_name="alice",
        runtime_type="executor",
        runtime_name="executor-1",
    )

    response = client.post(
        "/api/internal/skill-identity/verify",
        json={"token": token, "user_name": "alice"},
    )

    assert response.status_code == 200
    assert response.json() == {"matched": True}


def test_verify_skill_identity_does_not_leak_real_username(client):
    token = create_skill_identity_token(
        user_id=1,
        user_name="alice",
        runtime_type="executor",
        runtime_name="executor-1",
    )

    response = client.post(
        "/api/internal/skill-identity/verify",
        json={"token": token, "user_name": "bob"},
    )

    assert response.status_code == 200
    assert response.json()["matched"] is False
    assert "alice" not in response.text
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/api/endpoints/internal/test_skill_identity_api.py -v`
Expected: FAIL because endpoint does not exist.

**Step 3: Write minimal implementation**

```python
# backend/app/api/endpoints/internal/skill_identity.py
@router.post("/skill-identity/verify")
def verify_skill_identity(request: VerifySkillIdentityRequest):
    info = verify_skill_identity_token(request.token)
    if info is None:
        return {"matched": False, "reason": "invalid_token"}
    if not request.user_name:
        return {"matched": False, "reason": "missing_user_name"}
    if info.user_name != request.user_name:
        return {"matched": False, "reason": "user_mismatch"}
    return {"matched": True}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/api/endpoints/internal/test_skill_identity_api.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/api/endpoints/internal/skill_identity.py backend/tests/api/endpoints/internal/test_skill_identity_api.py
git commit -m "feat(api): add skill identity verification endpoint"
```

### Task 6: Document Runtime Contract and Verify Regressions

**Files:**
- Modify: `backend/init_data/skills/wiki_submit/SKILL.md`
- Modify: other built-in skill docs that mention `TASK_INFO.auth_token` for HTTP identity if needed
- Test: targeted regression suites from previous tasks

**Step 1: Write the failing test**

No code test. Add a doc verification checklist in the commit.

**Step 2: Run targeted regression commands before doc update**

Run:
- `cd backend && uv run pytest tests/services/auth/test_skill_identity_token.py tests/services/execution/test_request_builder_skill_identity.py tests/api/endpoints/internal/test_skill_identity_api.py -v`
- `cd executor_manager && uv run pytest tests/executors/test_docker_executor.py -v`
- `cd executor && uv run pytest tests/config/test_env_reader.py -v`

Expected: PASS before finalizing docs.

**Step 3: Write minimal implementation**

Update skill-facing docs to recommend:

```bash
Authorization: Bearer $WEGENT_SKILL_IDENTITY_TOKEN
X-Wegent-User-Name: $WEGENT_SKILL_USER_NAME
```

and explain that business services must verify via Wegent internal API.

**Step 4: Run verification again**

Run the same commands from Step 2.
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/init_data/skills/wiki_submit/SKILL.md
git commit -m "docs(skill): document skill http identity contract"
```
