---
sidebar_position: 1
---

# 会话内提示词管理设计

## 概述

本文设计一套基于 `skill + MCP` 的会话内提示词管理能力。用户在聊天会话中可以直接发起提示词相关操作，而无需跳转到设置页或使用独立弹窗。

目标能力包括：

- 查询当前智能体的系统提示词
- 基于当前对话上下文和用户反馈优化提示词
- 以结构化 block 展示优化后的提示词与 diff
- 用户手动决定是否替换原提示词
- 对查询、优化、替换统一做权限控制

本设计明确以智能体当前 `base_prompt` 为唯一管理对象，不引入会话级 `session_override_prompt`，也不包含提示词回滚能力。

## 背景与问题

当前项目已经具备三类可复用能力：

1. `chat_shell` 已支持 skill 动态加载与 MCP server 联动
2. Backend 已具备基于 `@mcp_tool` 的 MCP 工具快速声明与自动注册机制
3. Frontend 聊天消息流已支持 block-based mixed content 渲染

现有设置页中的 Prompt Fine Tune 能力偏向配置页编辑，不满足以下会话内协作需求：

- 用户在对话中自然表达“这段提示词不对，帮我改一下”
- 系统基于当前会话上下文给出优化方案
- 用户在聊天流中直接审阅优化结果、查看 diff、点击替换

因此需要一条新的会话内提示词管理链路，但必须尽量复用现有 MCP、skill、消息 block 和权限体系。

## 设计目标

### 功能目标

- 在会话中识别提示词管理意图
- 查询当前智能体生效的 `base_prompt`
- 输出结构化的提示词优化候选
- 支持候选连续再次优化
- 支持用户手动替换当前智能体提示词

### 非功能目标

- 权限边界只放在 MCP/Backend，不信任前端或模型文本判断
- 设计与 `wegent-knowledge` skill 模式一致
- MCP 工具通过 `@mcp_tool` 快速声明，减少样板代码
- 不引入新表或新的 prompt 状态层级
- 尽量复用现有 Team 提示词读写链路

## 非目标

本设计首版不包含以下内容：

- 会话级 `session_override_prompt`
- 仅影响当前会话的 prompt 应用范围
- 提示词历史版本
- 提示词回滚
- 候选结果持久化到数据库
- 设置页中的弹窗式提示词编辑复用

## 用户场景

### 场景 1：查询当前提示词

用户在聊天中输入：

```text
看看当前系统提示词
```

系统行为：

1. skill 识别为提示词查询意图
2. 调用 MCP `get_base_prompt`
3. 返回结构化结果
4. 前端渲染 `prompt_view` block

### 场景 2：优化提示词

用户在聊天中输入：

```text
这块约束太重了，帮我把提示词改得更灵活一点
```

系统行为：

1. skill 识别为提示词优化意图
2. 先读取当前 `base_prompt`
3. 再调用 `propose_prompt_revision`
4. 前端渲染 `prompt_candidate` block，展示：
   - 优化后完整提示词
   - 变更摘要
   - diff
   - 替换按钮
   - 再次优化按钮

### 场景 3：替换原提示词

用户点击 `替换原提示词`。

系统行为：

1. 前端调用 `apply_prompt_revision`
2. MCP 校验权限
3. 写入新 `base_prompt`
4. 返回 `prompt_applied` block

## 整体架构

系统拆分为三层：

1. `prompt-manager` skill
2. `prompt` MCP server
3. Frontend 会话 block 渲染层

### Skill 层职责

`prompt-manager` skill 负责：

- 识别用户是否在进行提示词管理
- 规范模型在不同意图下应调用的 MCP 工具
- 明确优化结果必须展示给用户，不能自动替换
- 明确无权限时必须拒绝操作并避免泄露提示词全文
- 在多轮优化中优先基于当前候选继续优化

### MCP 层职责

`prompt` MCP server 负责：

- 查询智能体当前 `base_prompt`
- 基于用户反馈生成提示词候选
- 将候选写回为新的 `base_prompt`
- 做统一权限校验

### Frontend 层职责

Frontend 聊天消息 block 负责：

- 渲染当前提示词、候选提示词、应用结果
- 展示结构化 diff
- 提供操作按钮
- 根据 MCP 返回的权限字段控制按钮可用态
- 保持所有操作都在聊天流中完成

## Skill 设计

新增 skill：

- 路径：`backend/init_data/skills/prompt-manager/SKILL.md`
- 绑定 Shell：`Chat`、`Agno`、`ClaudeCode`
- MCP server 声明方式与 `wegent-knowledge` 保持一致

建议 skill frontmatter 示例：

```yaml
---
description: "Prompt management tools for Wegent. Provides capabilities to inspect, optimize, and apply an agent's system prompt during a chat session."
displayName: "Wegent Prompt Manager"
version: "1.0.0"
author: "Wegent Team"
tags: ["prompt", "system-prompt", "agent", "optimization"]
bindShells:
  - Chat
  - Agno
  - ClaudeCode
mcpServers:
  wegent-prompt:
    type: streamable-http
    url: "${{backend_url}}/mcp/prompt/sse"
    headers:
      Authorization: "Bearer ${{task_token}}"
    timeout: 300
---
```

### Skill 行为规则

skill 需要明确约束模型：

- 查看当前提示词时调用 `get_base_prompt`
- 优化提示词时先读取当前提示词，再调用 `propose_prompt_revision`
- 优化结果只能作为候选展示，不得自动生效
- 替换必须由用户点击按钮或明确确认后执行
- 没有权限时，不得泄露提示词全文
- 多轮优化时，可以携带当前候选全文继续生成下一版，而不是依赖数据库候选 ID

## MCP Server 设计

### 路由与注册

新增 Prompt MCP server，路径风格与 Knowledge MCP 保持一致：

- Root：`/mcp/prompt`
- Streamable transport：`/mcp/prompt/sse`

需要在 Backend MCP server 中新增：

- `prompt_mcp_server = FastMCP(...)`
- `ensure_prompt_tools_registered()`
- `_register_prompt_tools()`
- Prompt MCP 的 `McpAppSpec`

### 工具声明方式

Prompt MCP 工具放在：

- `backend/app/mcp_server/tools/prompt.py`

工具全部采用现有注解：

- `@mcp_tool(server="prompt", ...)`

这保证与 `knowledge.py` 的声明、注册、schema 推导机制一致。

## MCP 工具设计

### 1. get_base_prompt

用途：读取当前会话所关联智能体的当前系统提示词。

输入：

- 无显式业务参数，依赖 `token_info` 推导当前 task、user、team

输出：

- `team_id`
- `team_name`
- `base_prompt`
- `can_view_prompt`
- `can_optimize_prompt`
- `can_apply_prompt`

### 2. propose_prompt_revision

用途：基于当前提示词与用户反馈生成优化候选。

输入：

- `user_feedback: str`
- `current_prompt: Optional[str]`

说明：

- `current_prompt` 为空时，以当前 `base_prompt` 为输入
- `current_prompt` 有值时，以该提示词作为继续优化的基线
- 这样可以支持再次优化，而无需持久化 candidate 表

输出：

- `original_prompt`
- `optimized_prompt`
- `summary`
- `diff`
- `can_apply_prompt`

### 3. apply_prompt_revision

用途：将某个优化后的提示词直接写回智能体 `base_prompt`。

输入：

- `prompt: str`

输出：

- `team_id`
- `team_name`
- `applied_prompt`
- `applied_at`

执行规则：

1. 校验权限
2. 校验 prompt 非空且与当前值有差异
3. 直接写回智能体 `base_prompt`

## 状态管理设计

本设计不新增数据库表。

因此优化候选采用会话内临时状态管理：

- MCP 生成候选后，结果直接回到消息 block
- 前端在 block 中保存当前候选 prompt 和 diff
- 用户点击“再次优化”时，把当前候选 prompt 作为 `current_prompt` 再发给 MCP
- 用户点击“替换原提示词”时，把当前候选全文直接提交给 `apply_prompt_revision`

这个设计牺牲了候选持久化和历史审计，但满足“无新表”的约束。

## base_prompt 的定位

本设计明确：

- 查询对象是当前智能体的 `base_prompt`
- 应用目标是当前智能体的 `base_prompt`

本设计不新增 `session_override_prompt`，避免形成两套 prompt 状态并增加复杂度。

## 权限设计

### 权限原则

所有操作统一要求用户具备“该智能体的编辑权限”。

操作包括：

- 查询提示词
- 优化提示词
- 替换提示词

### 权限来源

沿用现有 Team 编辑权限模型：

- 个人智能体：资源创建者可编辑
- 组智能体：`Developer+` 可编辑

### 权限边界

权限校验只在 MCP/Backend 执行。

前端职责仅为：

- 根据返回字段展示或禁用按钮
- 不作为安全边界

建议工具统一返回：

- `can_view_prompt`
- `can_optimize_prompt`
- `can_apply_prompt`

## Frontend Block 设计

首版建议新增 3 类 block。

### 1. prompt_view

用于展示当前 `base_prompt`。

字段建议：

- `type: prompt_view`
- `teamId`
- `teamName`
- `prompt`
- `permissions`

### 2. prompt_candidate

用于展示优化候选。

字段建议：

- `type: prompt_candidate`
- `originalPrompt`
- `optimizedPrompt`
- `summary`
- `diff`
- `permissions`

交互按钮：

- `替换原提示词`
- `再次优化`

### 3. prompt_applied

用于展示替换成功结果。

字段建议：

- `type: prompt_applied`
- `teamId`
- `teamName`
- `appliedPrompt`
- `appliedAt`

## Diff 设计

Diff 建议由 MCP 返回结构化结果，而不是前端临时自行计算。

建议格式：

```json
[
  {"type": "unchanged", "content": "..."},
  {"type": "removed", "content": "..."},
  {"type": "added", "content": "..."}
]
```

优点：

- schema 稳定
- 前端只负责渲染
- 未来可以替换为段落级或 section 级 diff，而不影响交互协议

## 现有能力复用点

本方案明确复用以下能力：

1. Skill MCP 声明方式
   - 参考 `backend/init_data/skills/wegent-knowledge/SKILL.md`

2. MCP 工具快速注解
   - 使用 `backend/app/mcp_server/tools/decorator.py` 中的 `@mcp_tool`

3. FastMCP 自动注册
   - 使用 `backend/app/mcp_server/tool_registry.py`

4. 聊天消息 block 渲染
   - 利用 Frontend 现有 mixed-content message blocks 架构

5. Team 编辑权限模型
   - 沿用现有 `Developer+` 的组资源编辑判定

## 风险与约束

### 1. 无候选持久化

由于不新增表，候选结果只存在于当前消息流中。这意味着：

- 刷新后不能可靠恢复候选链
- 不适合做复杂的多分支候选管理

### 2. 无回滚

由于不做版本历史，替换是直接写回当前 `base_prompt`。一旦替换成功，若用户想回到旧版本，只能重新手动修改。

### 3. prompt 来源确定

需要先明确当前智能体真正可写入的系统提示词字段来源。

建议首版收敛：

- 统一读取和写回 Team 当前主系统提示词字段
- 不在首版做 Team/Bot/Ghost 多层组合反向写入

## 测试设计

### Backend 单元测试

- 有权限用户可查询提示词
- 无权限用户查询返回 403
- `propose_prompt_revision` 可生成候选
- 可基于 `current_prompt` 再次优化
- `apply_prompt_revision` 可直接更新当前 prompt

### MCP 测试

- `@mcp_tool(server="prompt")` 工具可被正确注册
- Prompt MCP server 路由与认证正常
- token_info 自动注入正常

### Frontend 测试

- `prompt_view` block 正确渲染全文
- `prompt_candidate` block 正确渲染优化后提示词与 diff
- 权限不足时按钮禁用或隐藏
- 点击 `替换原提示词` 后渲染成功 block
- 点击 `再次优化` 时会携带当前候选全文再次请求
- 新交互元素包含稳定 `data-testid`

### E2E 测试

- 在真实会话中触发提示词查询
- 触发提示词优化并展示候选 block
- 执行替换成功
- 无权限用户无法查询、优化、替换

## 首版实施范围

建议首版包含：

- `prompt-manager` skill
- `prompt` MCP server
- `get_base_prompt`
- `propose_prompt_revision`
- `apply_prompt_revision`
- 3 类会话 block
- 基于当前候选的再次优化

建议暂缓：

- 历史版本
- 回滚
- 会话级 prompt 覆盖
- 设置页 prompt 管理复用

## 推荐结论

最终推荐方案如下：

1. 新增 `prompt-manager` skill，模式与 `wegent-knowledge` 一致
2. 新增 `prompt` MCP server，路径为 `/mcp/prompt/sse`
3. Prompt MCP 工具全部使用现有 `@mcp_tool` 注解快速声明
4. 在聊天消息流中新增 prompt 专用 blocks 展示提示词、候选、diff、替换结果
5. 所有操作统一绑定到智能体 `base_prompt`
6. 所有查询、优化、替换统一使用“智能体编辑权限”校验
7. 候选状态只在会话 block 中临时维护，不新增数据库表

该方案最大化复用现有项目模式，避免引入新的 prompt 状态层，同时满足会话内提示词管理的核心需求。
