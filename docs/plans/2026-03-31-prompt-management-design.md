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
- 支持对已替换的提示词执行回滚
- 对查询、优化、替换、回滚统一做权限控制

本设计明确以智能体当前 `base_prompt` 为唯一管理对象，不引入会话级 `session_override_prompt`。

## 背景与问题

当前项目已经具备两类可复用能力：

1. `chat_shell` 已支持 skill 动态加载与 MCP server 联动
2. Backend 已具备基于 `@mcp_tool` 的 MCP 工具快速声明与自动注册机制
3. Frontend 聊天消息流已支持 block-based mixed content 渲染

现有设置页中的 Prompt Fine Tune 能力偏向配置页编辑，不满足以下会话内协作需求：

- 用户在对话中自然表达“这段提示词不对，帮我改一下”
- 系统基于当前会话上下文给出优化方案
- 用户在聊天流中直接审阅优化结果、查看 diff、点击替换
- 用户在替换后可以立刻回滚提示词

因此需要一条新的会话内提示词管理链路，但必须尽量复用现有 MCP、skill、消息 block 和权限体系。

## 设计目标

### 功能目标

- 在会话中识别提示词管理意图
- 查询当前智能体生效的 `base_prompt`
- 输出结构化的提示词优化候选
- 支持候选多轮迭代优化
- 支持用户手动替换当前智能体提示词
- 支持快速回滚上一版提示词
- 为后续扩展历史版本列表与任意版本回滚预留接口

### 非功能目标

- 权限边界只放在 MCP/Backend，不信任前端或模型文本判断
- 设计与 `wegent-knowledge` skill 模式一致
- MCP 工具通过 `@mcp_tool` 快速声明，减少样板代码
- 不引入与现有 CRD 模型冲突的新 prompt 配置层级
- 为审计和版本追踪保留清晰的数据链路

## 非目标

本设计首版不包含以下内容：

- 会话级 `session_override_prompt`
- 仅影响当前会话的 prompt 应用范围
- 设置页中的弹窗式提示词编辑复用
- 首版完整历史版本 UI
- 任意历史版本回滚的前端选择器

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

1. 前端调用 `apply_prompt_candidate`
2. MCP 校验权限
3. 先保存旧版 prompt 快照
4. 写入新 `base_prompt`
5. 返回 `prompt_applied` block
6. block 提供 `回滚上一版`

### 场景 4：回滚提示词

用户点击 `回滚上一版`。

系统行为：

1. 前端调用 `rollback_prompt`
2. MCP 校验权限
3. 恢复上一版 prompt 为当前 `base_prompt`
4. 记录回滚操作对应的快照
5. 返回 `prompt_rollback` block

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
- 在多轮优化中优先基于最近候选继续优化

### MCP 层职责

`prompt` MCP server 负责：

- 查询智能体当前 `base_prompt`
- 基于用户反馈生成提示词候选
- 将候选写回为新的 `base_prompt`
- 记录历史快照
- 执行提示词回滚
- 做统一权限校验

### Frontend 层职责

Frontend 聊天消息 block 负责：

- 渲染当前提示词、候选提示词、应用结果、回滚结果
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
description: "Prompt management tools for Wegent. Provides capabilities to inspect, optimize, apply, and rollback an agent's system prompt during a chat session."
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
- 回滚通过 `rollback_prompt` 完成
- 没有权限时，不得泄露提示词全文
- 多轮优化时，优先基于最近一次候选继续生成下一版

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
- `can_rollback_prompt`

### 2. propose_prompt_revision

用途：基于当前 `base_prompt` 与用户反馈生成优化候选。

输入：

- `user_feedback: str`
- `base_candidate_id: Optional[int]`

输出：

- `candidate_id`
- `original_prompt`
- `optimized_prompt`
- `summary`
- `diff`
- 权限字段

说明：

- 当 `base_candidate_id` 存在时，基于该候选继续优化
- 当 `base_candidate_id` 不存在时，基于当前 `base_prompt` 优化

### 3. apply_prompt_candidate

用途：将某个候选写回智能体 `base_prompt`。

输入：

- `candidate_id: int`

输出：

- `applied_version_id`
- `previous_version_id`
- `new_prompt`
- `applied_at`
- `can_rollback_prompt`

执行规则：

1. 校验权限
2. 读取候选
3. 保存当前 prompt 快照到历史表
4. 写回智能体 `base_prompt`
5. 标记 candidate 状态为 `applied`

### 4. rollback_prompt

用途：回滚提示词。

输入：

- `target_version_id: Optional[int]`

输出：

- `current_version_id`
- `rolled_back_from_version_id`
- `rolled_back_to_version_id`
- `prompt`

首版规则：

- 不传 `target_version_id` 时，默认回滚上一版
- 前端首版只暴露“回滚上一版”
- 接口预留未来“回滚到指定历史版本”能力

### 5. list_prompt_versions

用途：查看当前智能体的提示词历史版本。

输入：

- `limit: int = 10`

输出：

- `items[]`
  - `version_id`
  - `created_at`
  - `created_by`
  - `source`
  - `summary`

说明：

- 首版 UI 可以不完全展开历史列表
- 先提供 MCP 能力，便于后续扩展

## 数据模型设计

首版建议新增两张表。

### 1. prompt_candidates

用途：保存每次提示词优化候选。

建议字段：

- `id`
- `task_id`
- `team_id`
- `user_id`
- `original_prompt`
- `optimized_prompt`
- `summary`
- `diff_json`
- `base_candidate_id` nullable
- `status`
  - `draft`
  - `applied`
  - `superseded`
- `created_at`

设计价值：

- 支持再次优化
- 支持重复应用
- 让 apply 操作有稳定主键
- 避免候选只存在于前端内存

### 2. prompt_versions

用途：保存提示词历史版本与回滚链。

建议字段：

- `id`
- `team_id`
- `namespace`
- `user_id`
- `prompt_content`
- `created_by`
- `created_at`
- `source`
  - `manual_apply`
  - `rollback`
- `parent_version_id` nullable
- `candidate_id` nullable
- `change_summary` nullable

设计价值：

- 支持回滚上一版
- 为后续任意版本回滚提供基础
- 保留审计信息

## base_prompt 的定位

本设计明确：

- 查询对象是当前智能体的 `base_prompt`
- 应用目标是当前智能体的 `base_prompt`
- 回滚对象是当前智能体的 `base_prompt`

本设计不新增 `session_override_prompt`，避免形成两套 prompt 状态并增加复杂度。

## 权限设计

### 权限原则

所有操作统一要求用户具备“该智能体的编辑权限”。

操作包括：

- 查询提示词
- 优化提示词
- 替换提示词
- 回滚提示词

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
- `can_rollback_prompt`

## Prompt 版本与回滚设计

### 替换时的版本处理

执行 `apply_prompt_candidate` 时，必须先保存旧 prompt 快照，再更新新 prompt。

因此任何一次替换后，系统至少具备：

- 当前生效 prompt
- 上一版历史 prompt

### 回滚策略

首版支持“回滚上一版”，这是最短链路且风险最低。

执行 `rollback_prompt` 时：

1. 找到当前 team 对应的最近历史版本
2. 将当前 prompt 恢复为该历史版本内容
3. 将回滚前当前 prompt 也记录为一个新版本快照
4. 返回回滚结果

这样可形成完整的版本链，而不是一次性覆盖。

## Frontend Block 设计

首版建议新增 4 类 block。

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
- `candidateId`
- `originalPrompt`
- `optimizedPrompt`
- `summary`
- `diff`
- `permissions`
- `status`

交互按钮：

- `替换原提示词`
- `再次优化`

### 3. prompt_applied

用于展示替换成功结果。

字段建议：

- `type: prompt_applied`
- `candidateId`
- `appliedVersionId`
- `promptSummary`
- `canRollback`

交互按钮：

- `回滚上一版`

### 4. prompt_rollback

用于展示回滚成功结果。

字段建议：

- `type: prompt_rollback`
- `rolledBackToVersionId`
- `promptSummary`

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

### 1. prompt 来源确定

需要先明确当前智能体真正可写入的系统提示词字段来源。

建议首版收敛：

- 统一读取和写回 Team 当前主系统提示词字段
- 不在首版做 Team/Bot/Ghost 多层组合反向写入

### 2. 候选与版本不能只存在前端

如果候选或版本只保存在前端状态中，将导致：

- 重复应用不稳定
- 回滚链丢失
- 跨刷新无法恢复

因此首版必须落库。

### 3. 没有版本表则无法安全回滚

简单地“保存上一版到内存”只能支持极弱回滚，不满足正式提示词管理能力要求。

## 测试设计

### Backend 单元测试

- 有权限用户可查询提示词
- 无权限用户查询返回 403
- `propose_prompt_revision` 可生成候选
- 候选支持基于 `base_candidate_id` 再次优化
- `apply_prompt_candidate` 会先写版本快照再更新 prompt
- `rollback_prompt` 可回滚上一版
- 多次替换后的版本链正确
- 不同 task/team 的候选和版本不会串数据

### MCP 测试

- `@mcp_tool(server="prompt")` 工具可被正确注册
- Prompt MCP server 路由与认证正常
- token_info 自动注入正常

### Frontend 测试

- `prompt_view` block 正确渲染全文
- `prompt_candidate` block 正确渲染优化后提示词与 diff
- 权限不足时按钮禁用或隐藏
- 点击 `替换原提示词` 后渲染成功 block
- 点击 `回滚上一版` 后渲染回滚成功 block
- 新交互元素包含稳定 `data-testid`

### E2E 测试

- 在真实会话中触发提示词查询
- 触发提示词优化并展示候选 block
- 执行替换成功
- 执行回滚成功
- 无权限用户无法查询、优化、替换、回滚

## 首版实施范围

建议首版包含：

- `prompt-manager` skill
- `prompt` MCP server
- `get_base_prompt`
- `propose_prompt_revision`
- `apply_prompt_candidate`
- `rollback_prompt`
- `list_prompt_versions`
- `prompt_candidates` 表
- `prompt_versions` 表
- 4 类会话 block
- 快速回滚上一版

建议暂缓：

- 历史版本完整前端浏览器
- 任意版本回滚 UI
- 会话级 prompt 覆盖
- 设置页 prompt 管理复用

## 推荐结论

最终推荐方案如下：

1. 新增 `prompt-manager` skill，模式与 `wegent-knowledge` 一致
2. 新增 `prompt` MCP server，路径为 `/mcp/prompt/sse`
3. Prompt MCP 工具全部使用现有 `@mcp_tool` 注解快速声明
4. 在聊天消息流中新增 prompt 专用 blocks 展示提示词、候选、diff、替换结果、回滚结果
5. 所有操作统一绑定到智能体 `base_prompt`
6. 所有查询、优化、替换、回滚统一使用“智能体编辑权限”校验
7. 通过 `prompt_versions` 实现可审计、可回滚的提示词版本管理

该方案最大化复用现有项目模式，避免引入新的 prompt 状态层，同时满足会话内提示词管理的核心需求。
