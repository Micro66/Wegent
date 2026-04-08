# 订阅工具迁移计划：从 Builtin 到 MCP + Skill

## 概述

将 `preview_subscription` 和 `create_subscription` 工具从 chat_shell 的 builtin LangChain 工具改为 **MCP + Skill** 架构，并迁移到 backend。

## 目标

1. 在 backend 创建新的 MCP 服务器 `/mcp/subscription`，提供订阅相关工具
2. 创建 Skill (`subscription-manager`)，引用该 MCP 服务器
3. 该 Skill 默认内置（所有场景自动可用）
4. 订阅任务执行场景不注入该 Skill（避免嵌套订阅）
5. 从 chat_shell 中移除旧的 builtin 工具实现

---

## 架构变化

### 当前架构

```
用户对话 → Chat Shell
    ↓
PreviewSubscriptionTool / CreateSubscriptionTool (builtin LangChain 工具)
    ↓
直接调用 backend service 或 HTTP API
```

### 目标架构

```
用户对话 → Chat Shell
    ↓
MCP Client → Backend /mcp/subscription/sse
    ↓
preview_subscription / create_subscription (MCP 工具)
    ↓
subscription_service.create_subscription()
```

---

## 实施步骤

### Phase 1: Backend MCP 服务器搭建

**文件**: `backend/app/mcp_server/tools/subscription.py`

- [ ] 创建订阅 MCP 工具模块
- [ ] 实现 `preview_subscription` 工具函数
  - 复用现有 `preview_subscription.py` 逻辑
  - 使用 `@mcp_tool` 装饰器注册
  - 处理 preview 数据存储（Redis，复用现有 storage）
- [ ] 实现 `create_subscription` 工具函数
  - 复用现有 `create_subscription.py` 逻辑
  - 使用 `@mcp_tool` 装饰器注册
  - 调用 `subscription_service.create_subscription()`

**文件**: `backend/app/mcp_server/server.py`

- [ ] 添加 `SUBSCRIPTION_MCP_MOUNT_PATH = "/mcp/subscription"`
- [ ] 创建 `subscription_mcp_server` FastMCP 实例
- [ ] 注册工具（通过 import `subscription` 模块触发装饰器）
- [ ] 添加 `SUBSCRIPTION_MCP_SPEC` 和 `MCP_APP_SPECS`
- [ ] 实现 `get_mcp_subscription_config()` 函数

**关键代码结构**:
```python
# backend/app/mcp_server/tools/subscription.py
from app.mcp_server.tools.decorator import mcp_tool
from app.mcp_server.auth import TaskTokenInfo

@mcp_tool(
    name="preview_subscription",
    description="Preview subscription configuration before creating it",
    server="subscription",
    exclude_params=["token_info"],
)
def preview_subscription(
    token_info: TaskTokenInfo,
    display_name: str,
    trigger_type: Literal["cron", "interval", "one_time"],
    prompt_template: str,
    # ... other params
) -> dict:
    """Generate preview of subscription configuration."""
    # Implementation here
    pass

@mcp_tool(
    name="create_subscription",
    description="Create a subscription task after preview",
    server="subscription",
    exclude_params=["token_info"],
)
def create_subscription(
    token_info: TaskTokenInfo,
    preview_id: str,
    # ... other params
) -> dict:
    """Create subscription using preview configuration."""
    # Implementation here
    pass
```

---

### Phase 2: Skill 创建与配置

**文件**: `backend/app/core/default_skills.py` (新建)

- [ ] 创建默认 Skill 配置模块
- [ ] 定义 `subscription-manager` Skill 配置
- [ ] 包含 MCP 服务器引用信息

**关键代码结构**:
```python
# backend/app/core/default_skills.py
"""Default system skills configuration.

These skills are automatically injected into all tasks unless excluded.
"""

DEFAULT_SYSTEM_SKILLS = [
    {
        "name": "subscription-manager",
        "description": "Manage scheduled subscription tasks - preview and create recurring/periodic tasks",
        "display_name": "订阅任务管理",
        "mcp_servers": [
            {
                "name": "subscription-mcp",
                "type": "streamable-http",
                "url": "${BACKEND_URL}/mcp/subscription/sse",
                "auth": {
                    "type": "task_token",
                },
            }
        ],
    }
]

def get_default_skills(exclude_in_subscription_context: bool = False) -> list[dict]:
    """Get default system skills.

    Args:
        exclude_in_subscription_context: If True, exclude skills that should not
            be available in subscription task execution (like subscription-manager itself)

    Returns:
        List of skill configurations
    """
    if exclude_in_subscription_context:
        # Exclude subscription-manager in subscription tasks to prevent nested subscriptions
        return [s for s in DEFAULT_SYSTEM_SKILLS if s["name"] != "subscription-manager"]
    return DEFAULT_SYSTEM_SKILLS
```

**文件**: `backend/app/schemas/kind.py`

- [ ] 确认 Ghost.spec 中 `skills` 字段支持 MCP 服务器引用
- [ ] 确认 `skill_configs` 可以传递 MCP 配置

---

### Phase 3: Backend 任务执行层集成

**文件**: `backend/app/services/chat/` (或相关任务创建服务)

- [ ] 修改任务创建逻辑，注入默认 skills
- [ ] 根据任务类型（是否为订阅任务）决定是否注入 `subscription-manager`
- [ ] 将 MCP 服务器配置传递给 chat_shell

**关键修改点**:
```python
# 在创建 ExecutionRequest 时
from app.core.default_skills import get_default_skills

def build_execution_request(task, subtask, ...):
    # ... existing code

    # Get default skills (exclude subscription-manager for subscription tasks)
    is_subscription_task = task.kind == "Subscription" or subtask.is_subscription
    default_skills = get_default_skills(
        exclude_in_subscription_context=is_subscription_task
    )

    # Merge with user-defined skills
    skill_configs = user_skill_configs + default_skills

    execution_request = ExecutionRequest(
        # ... existing fields
        skill_configs=skill_configs,
        mcp_servers=extract_mcp_servers_from_skills(skill_configs),
        is_subscription=is_subscription_task,
    )
```

**文件**: `backend/app/services/chat/chat_service.py` 或相关服务

- [ ] 在构建 chat_shell 请求时包含 MCP 服务器配置
- [ ] 确保 MCP 服务器 URL 使用正确的 backend 地址

---

### Phase 4: Chat Shell 适配

**文件**: `chat_shell/chat_shell/services/context.py`

- [ ] 移除 `CreateSubscriptionTool` 和 `PreviewSubscriptionTool` 的导入和添加逻辑
- [ ] 保留 `is_subscription` 检查逻辑（但现在用于其他目的，如决定是否注入系统 Skill 的 MCP）

**删除代码**:
```python
# 删除以下代码块 (lines ~803-870)
# Add CreateSubscriptionTool and PreviewSubscriptionTool
# Only enabled when NOT in a subscription task execution...
if not self._request.is_subscription:
    from chat_shell.tools.builtin import CreateSubscriptionTool
    # ... entire block
```

**文件**: `chat_shell/chat_shell/tools/builtin/__init__.py`

- [ ] 从 `__all__` 中移除 `CreateSubscriptionTool` 和 `PreviewSubscriptionTool`
- [ ] 可选：保留文件但标记为已弃用，或完全删除

**文件**: `chat_shell/chat_shell/tools/builtin/preview_subscription.py`
和 `create_subscription.py`

- [ ] 可选：标记为已弃用或删除

---

### Phase 5: MCP 配置注入

**文件**: `backend/app/services/chat/skill_config_service.py` (新建或修改现有)

- [ ] 创建服务处理 Skill 配置到 MCP 服务器的转换
- [ ] 处理变量替换（如 `${BACKEND_URL}`）
- [ ] 处理认证信息注入

**关键逻辑**:
```python
def resolve_mcp_servers(skill_configs: list[dict], context: dict) -> list[dict]:
    """Resolve MCP server configurations from skills.

    Replaces placeholders like ${BACKEND_URL} with actual values.
    Injects authentication tokens where needed.
    """
    mcp_servers = []
    for skill in skill_configs:
        for mcp_server in skill.get("mcp_servers", []):
            resolved = resolve_placeholders(mcp_server, context)
            if resolved.get("auth", {}).get("type") == "task_token":
                resolved["headers"] = {
                    "Authorization": f"Bearer {context['task_token']}"
                }
            mcp_servers.append(resolved)
    return mcp_servers
```

---

### Phase 6: 测试

**文件**: `backend/tests/mcp/test_subscription_mcp.py` (新建)

- [ ] 测试 `preview_subscription` MCP 工具
- [ ] 测试 `create_subscription` MCP 工具
- [ ] 测试 preview 数据存储和过期
- [ ] 测试错误处理

**文件**: `backend/tests/services/test_default_skills.py` (新建)

- [ ] 测试默认 skills 注入
- [ ] 测试订阅任务中排除 subscription-manager

**文件**: `chat_shell/tests/test_context_without_subscription_tools.py` (修改现有)

- [ ] 验证 chat_shell 不再通过 builtin 添加订阅工具
- [ ] 验证 MCP 工具正常工作

---

### Phase 7: 清理和文档

- [ ] 删除 chat_shell 中旧的订阅工具文件（或标记为已弃用）
- [ ] 更新 AGENTS.md 文档
- [ ] 更新 Skill 系统文档
- [ ] 更新 API 文档

---

## 数据流

### Preview Subscription Flow

```
1. 用户: "帮我创建一个每天早上9点的提醒"
   ↓
2. Chat Shell 通过 MCP 调用 preview_subscription
   ↓
3. Backend MCP Server:
   - 验证参数
   - 生成 preview_id
   - 存储到 Redis (TTL=5min)
   - 返回 preview 表格
   ↓
4. Chat Shell 显示预览给用户
```

### Create Subscription Flow

```
1. 用户: "确认创建"
   ↓
2. Chat Shell 通过 MCP 调用 create_subscription(preview_id)
   ↓
3. Backend MCP Server:
   - 从 Redis 获取 preview 数据
   - 调用 subscription_service.create_subscription()
   - 清除 preview 数据
   - 返回创建结果
   ↓
4. Chat Shell 显示成功消息
```

---

## 关键设计决策

### 1. Skill 配置方式

- 使用 Python 代码定义默认 Skills（而非数据库存储）
- 便于版本控制和代码审查
- 系统启动时加载到内存

### 2. MCP 服务器认证

- 使用 Task Token 认证（与现有 system MCP 一致）
- Token 包含 user_id, task_id, subtask_id 等上下文

### 3. Preview 数据存储

- 继续使用 Redis（与现有实现一致）
- Key: `subscription:preview:{preview_id}`
- TTL: 5 分钟

### 4. 订阅任务检测

- 通过 `is_subscription` 标志检测
- 来源：
  - Task.kind == "Subscription"
  - 或 Subtask.is_subscription == True

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| MCP 连接失败 | 保持 fallback 机制，或显示友好错误 |
| Preview 数据过期 | 清晰的错误提示，引导用户重新预览 |
| 向后兼容性 | 保留旧 API 端点一段时间，或同时支持两种模式 |

---

## 时间估算

| Phase | 估算时间 |
|-------|----------|
| Phase 1: Backend MCP 服务器 | 4-6 小时 |
| Phase 2: Skill 配置 | 2-3 小时 |
| Phase 3: Backend 集成 | 3-4 小时 |
| Phase 4: Chat Shell 适配 | 2-3 小时 |
| Phase 5: MCP 配置注入 | 2-3 小时 |
| Phase 6: 测试 | 4-6 小时 |
| Phase 7: 文档 | 2 小时 |
| **总计** | **19-27 小时** |

---

## 后续优化

1. **UI 支持**：前端可以显示默认内置的 Skills
2. **权限控制**：细粒度的 Skill 使用权限
3. **Metrics**：监控 MCP 工具调用频率
4. **Caching**：缓存 Skill 配置减少重复解析
