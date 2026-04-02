---
sidebar_position: 1
---

# Ghost 默认知识库绑定设计

## 概述

本文设计 Wegent 中“在智能体编辑时绑定知识库”的能力。

已确认的产品目标：
- 默认知识库绑定放在 `Ghost`。
- 创建新会话时，将 `Ghost` 默认知识库合并到 `Task.spec.knowledgeBaseRefs`。
- 用户在发消息时手动选择知识库，属于对 `Task.spec.knowledgeBaseRefs` 的追加，而不是覆盖。
- 单条消息显式选择的知识库仍保留消息级优先级。

本设计优先保证：
- 分层清晰，不把知识库能力错误塞进 `Team` 或 `Bot`。
- 会话行为稳定，`Task` 一旦创建即拥有自己的知识库快照。
- 尽量复用现有 `SubtaskContext -> Task.spec.knowledgeBaseRefs` 的同步链路。

## 概念梳理

当前系统的核心层级为：

```text
Ghost = 静态能力声明
  - systemPrompt
  - mcpServers
  - skills

Bot = Ghost + Shell + Model

Team = 多个 Bot + collaborationModel

Task = 一次真实会话/任务实例

SubtaskContext = 某条消息显式选择的临时上下文
```

现有知识库已经有两层运行时语义：
- 消息级：`SubtaskContext(context_type=knowledge_base)`，表示“本条消息显式选中”
- 会话级：`Task.spec.knowledgeBaseRefs`，表示“当前会话后续可继承使用”

当前运行时优先级已存在：
1. 当前消息显式选择的知识库
2. `Task.spec.knowledgeBaseRefs`

本次新增的是第三层来源：
- `Ghost.spec.defaultKnowledgeBaseRefs` 仅用于初始化 `Task`，不参与每轮消息直接解析

## 方案选择

本次采用方案 1：在 `Ghost` 存默认知识库配置，并在创建 `Task` 时投影到 `Task.spec.knowledgeBaseRefs`。

### 备选方案对比

1. `Ghost` 存默认知识库，本次采用
- 优点：与 `Ghost` 承载静态能力的职责一致。
- 优点：`Task` 继续作为会话快照，边界清晰。
- 缺点：需要在创建 `Task` 时补一段投影逻辑。

2. `Bot` 存默认知识库
- 优点：前端当前编辑入口就是 `BotEdit`。
- 缺点：破坏现有“静态能力归属 `Ghost`”的分层，不采用。

3. 每次消息发送时动态读取 `Ghost`
- 优点：实现表面更直接。
- 缺点：会让已创建会话随着配置变更而漂移，破坏 `Task` 快照边界，不采用。

## 数据模型

### Ghost 新增字段

在 `Ghost.spec` 新增：
- `defaultKnowledgeBaseRefs?: KnowledgeBaseDefaultRef[]`

新增类型：

```python
class KnowledgeBaseDefaultRef(BaseModel):
    id: int
    name: str
```

字段语义：
- `id`：知识库 `Kind.id`，作为唯一主键
- `name`：知识库展示名，便于前端回显与审计

### Task 保持现状

继续使用现有：
- `Task.spec.knowledgeBaseRefs: KnowledgeBaseTaskRef[]`

该结构继续包含：
- `id`
- `name`
- `boundBy`
- `boundAt`

`Ghost` 与 `Task` 不复用同一 ref 类型，原因是：
- `Ghost` 存的是静态默认配置
- `Task` 存的是实际运行态绑定，带审计字段

## 行为规则

### 1) 创建/编辑 Bot

虽然前端入口在 `BotEdit`，但后端应将该配置写入 `Ghost.spec.defaultKnowledgeBaseRefs`。

这意味着：
- API 层可继续走 `/bots`
- `BotCreate` / `BotUpdate` / `BotInDB` / `BotDetail` 暴露 `default_knowledge_base_refs`
- Adapter 层负责把该字段映射到关联 `Ghost` 的 `spec.defaultKnowledgeBaseRefs`

### 2) 创建新 Task

创建 `Task` 时，需要从 `Team` 下所有成员的 `Bot -> Ghost` 收集默认知识库，并合并进 `Task.spec.knowledgeBaseRefs`。

合并规则：
- 遍历 `Team.spec.members` 中所有成员
- 读取每个成员 `Bot` 对应 `Ghost.spec.defaultKnowledgeBaseRefs`
- 按遍历顺序追加
- 以 `kb.id` 去重
- 如果 `params.knowledge_base_id` 存在，也并入结果

说明：
- `knowledge` 页面发起会话时自带的 `knowledge_base_id` 也属于初始化来源之一
- 这样新建 `Task` 后，`Task.spec.knowledgeBaseRefs` 就是完整初始快照

### 3) 发消息时手动选择知识库

保持现有机制：
- 先创建 `SubtaskContext`
- 再通过 `sync_subtask_kb_to_task()` 追加到 `Task.spec.knowledgeBaseRefs`

语义为：
- `SubtaskContext` 代表“本条消息显式选择”
- 同步到 `Task.spec.knowledgeBaseRefs` 代表“从现在起会话也绑定了它”

### 4) 运行时优先级

保持现有逻辑不变：
1. 当前消息的 `SubtaskContext`
2. `Task.spec.knowledgeBaseRefs`

`Ghost.spec.defaultKnowledgeBaseRefs` 只在创建 `Task` 时参与一次，不在消息阶段直接读取。

## 权限与安全

### 保存 Ghost 默认知识库时

用户保存 `BotEdit` 时，后端需要校验：
- 当前编辑者是否有权限访问被配置的知识库

不允许把不可访问的知识库写进 `Ghost` 默认配置。

### 创建 Task 投影时

在把 `Ghost` 默认知识库投影到 `Task` 时，需要再次按“当前发起会话的用户”过滤：
- 若当前发起人对某个默认知识库无权访问，则跳过该知识库
- 不因单个默认知识库不可访问而阻断整个 `Task` 创建

这样可以避免：
- Team owner 在 `Ghost` 上绑定个人知识库
- 其他 team 成员创建会话时被隐式越权

## 前端设计

### 入口位置

复用现有 `BotEdit` 页面，不新增 Team 级配置入口。

新增区域：
- 标题：`默认知识库`
- 提示文案：`用于初始化新会话；会话中手动选择知识库会继续追加`

### 交互规则

- 支持多选知识库
- 支持搜索
- 已选项可删除
- 保存时提交 `default_knowledge_base_refs`
- 编辑已有 Bot 时回填 `Ghost` 上的默认知识库配置

### 组件策略

不建议直接复制群聊绑定对话框逻辑。

建议抽小型共享能力：
- `useKnowledgeBaseOptions()`：获取并搜索可访问知识库
- `KnowledgeBaseMultiSelector`：纯选择组件

仅抽取 `BotEdit` 与群聊绑定所需的最小公共部分，不做大而全的知识库平台组件。

## 后端实现边界

建议新增独立服务函数，而不是把逻辑堆进 `create_new_task()`：

- `get_team_default_knowledge_base_refs(...)`
- `build_initial_task_knowledge_base_refs(...)`

职责拆分建议：
- 读取 Team 成员的 Ghost 默认 KB：一个 helper
- 过滤权限、去重、合并 `params.knowledge_base_id`：另一个 helper
- `create_new_task()` 只负责调用并写入 `task_json`

## 非目标

本次不做以下内容：
- 不新增 Team 级默认知识库绑定
- 不让 Ghost 配置变更自动影响历史 Task
- 不在消息阶段实时回读 Ghost 默认配置
- 不新增独立数据库表
- 不改造现有 `SubtaskContext -> Task.spec.knowledgeBaseRefs` 追加链路

## 风险与回归点

### 1. 多 Bot Team 默认知识库来源不一致

风险：
- 不同成员 `Ghost` 可能配置不同默认知识库

处理：
- 按 `Team.spec.members` 顺序合并
- 按 `kb.id` 去重

### 2. 历史会话行为漂移

风险：
- 如果运行时直接读 Ghost，历史会话会随 Ghost 配置改变

处理：
- 只在创建 Task 时做一次快照

### 3. 共享 Team 的知识库越权

风险：
- 默认知识库对 owner 可见，但对普通成员不可见

处理：
- 创建 Task 时按当前发起者权限过滤，跳过不可访问项

## 测试策略

### 后端

- 创建 Bot 时，`default_knowledge_base_refs` 正确落到 `Ghost.spec.defaultKnowledgeBaseRefs`
- 更新 Bot 时可覆盖 Ghost 默认知识库配置
- 创建 Task 时合并所有 Team 成员 Ghost 默认知识库
- `params.knowledge_base_id` 与 Ghost 默认知识库可正确去重合并
- 消息级手动选择知识库仍会 append 到 `Task.spec.knowledgeBaseRefs`
- 当前发起用户无权限的 Ghost 默认知识库不会被投影到 Task

### 前端

- `BotEdit` 能加载并展示默认知识库
- 可新增、删除、搜索多个知识库
- 保存请求带上 `default_knowledge_base_refs`
- 编辑已有 Bot 时正确回填

### E2E

- 在 Bot 编辑页绑定默认知识库后创建新会话，Task 初始绑定正确
- 新会话中再手动选择知识库，Task 绑定列表追加成功
- 历史 Task 不受后续 Ghost 配置修改影响

## 最终结论

本次能力应落在：
- 配置层：`Ghost.spec.defaultKnowledgeBaseRefs`
- 会话层：`Task.spec.knowledgeBaseRefs`
- 消息层：`SubtaskContext(context_type=knowledge_base)`

这条链路能够在不破坏现有分层的前提下，支持：
- 智能体默认知识库
- 会话初始化绑定
- 运行中追加绑定
- 消息级显式优先级

