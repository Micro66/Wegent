---
sidebar_position: 1
---

# GroupChat 多智能体切换设计

## 概述

本设计为 Web 端 GroupChat 增加“多智能体 + 单条消息切换”能力。

目标：
- 一个 GroupChat 可以绑定多个 Team/Agent。
- 用户发送每条消息时可以选择目标 Agent。
- 切换只对当前这条消息生效，不持久修改后续消息的默认目标。
- 群聊历史作为公共上下文，对所有可选 Agent 可见。
- 群聊级历史读取窗口支持按时间和条数配置，默认最近 2 天、最多 200 条。

明确不做：
- 不做群聊默认 Agent 的持久切换。
- 不做一条消息同时广播给多个 Agent。
- 不做 Agent 之间自动协作、自动转交或流水线编排。

## 已确认的产品规则

- GroupChat 支持绑定多个 Team/Agent。
- “切换智能体”只影响当前这条消息。
- 历史读取范围是群聊级设置。
- 历史范围支持两个维度：
  - 时间窗口（最近 N 天）
  - 条数上限（最多 N 条）
- 默认历史范围：
  - 最近 2 天
  - 最多 200 条
- 输入 `@` 时像“@人”一样弹出 Agent 列表。
- 选择 `@Agent` 后：
  - 在输入框中插入 mention 文本
  - 同步设置当前这条消息的目标 Agent
- 真正发送路由以结构化 `team_id` 为准，不依赖最终 prompt 文本解析。

## 现状与约束

当前实现中，Web GroupChat 仍是“单 Agent 群聊”：

- `Task.spec` 只有单个 `teamRef`。
- `CreateGroupChatDialog` 只能选择一个 Team。
- 输入框中的 mention 自动补全只展示当前 Team 本身。
- 后端 `chat:send` 仅接收一个 `team_id`，GroupChat 的 AI 触发依赖 `@TeamName` 文本匹配。

这意味着本次能力不能仅靠前端交互补丁实现，必须同时调整：
- GroupChat 的任务配置模型
- 创建/编辑群聊的前端表单
- 输入区单条消息目标选择
- 后端 GroupChat 消息发送校验与历史装载逻辑

## 方案选择

本次采用方案 1：将 GroupChat 扩展为“多 Agent 容器”，每条消息显式指定目标 `team_id`。

### 备选方案对比

1. GroupChat 显式持有多个 `teamRefs[]`，消息显式带 `team_id`（本次采用）
- 优点：模型清晰，路由稳定，前后端职责明确。
- 缺点：需要改 Task spec、群聊创建页和发送链路。

2. 保持单 `teamRef`，另存一份群聊扩展元数据维护 Agents
- 优点：表面改动较小。
- 缺点：群聊绑定对象分成两套来源，长期维护成本高，不采用。

3. 继续依赖 `@AgentName` 文本解析做路由
- 优点：初期改动最少。
- 缺点：重命名、同名、国际化和前端展示都容易失真，不采用。

## 核心交互行为

### 群聊创建

- 创建 GroupChat 时允许多选 Agent。
- 至少需要选择 1 个 Agent。
- 选中顺序保留，首个 Agent 作为输入区默认目标。
- 创建时同时配置群聊历史读取窗口：
  - `maxDays`
  - `maxMessages`

### 输入区单条消息切换

- 输入区显示“发送给”选择器，表示本条消息的目标 Agent。
- 用户可通过两种方式切换当前消息的目标：
  - 直接操作选择器
  - 输入 `@` 触发 Agent 列表并选择
- 当用户发送完成后，输入区目标 Agent 自动恢复为默认 Agent（即 `teamRefs[0]`）。

### `@` 交互

- 输入 `@` 时弹出该 GroupChat 可用 Agent 列表。
- 选择后在输入框中插入 `@AgentName`。
- 同步更新当前这条消息的目标 Agent。
- 用户后续删除 mention 文本，不自动回退选择器状态。
- 最终路由以发送请求中的结构化 `team_id` 为准。

### 消息展示

- 每条 AI 回复都显示对应 Agent 的名称与图标。
- 历史消息回放时同样要保留该信息。
- 用户消息保持现有展示方式。
- 前端消息状态中需要保存每条 AI 回复的 `teamId / botName / botIcon`：
  - 历史回放阶段按 `subtask.team_id` 解析实际回复 Agent。
  - 实时流式阶段先使用当前发送选择的 Agent 元数据占位，等任务与消息 ID 落稳后继续沿用同一份身份信息。

## 数据模型设计

建议将 GroupChat 任务配置扩展为如下结构：

```ts
Task.spec = {
  title: string
  prompt: string
  is_group_chat: true

  // 兼容旧数据
  teamRef?: TeamRef

  // 新增：群聊允许切换的 Agent 集合
  teamRefs: TeamRef[]

  // 新增：群聊级历史读取配置
  groupChatConfig: {
    historyWindow: {
      mode: 'bounded'
      maxDays: number
      maxMessages: number
    }
  }

  workspaceRef?: ...
  knowledgeBaseRefs?: ...
}
```

规则：
- `teamRefs[]` 是 GroupChat 的唯一 Agent 来源。
- 单条消息发送时必须显式带一个目标 `team_id`。
- `team_id` 必须属于 `teamRefs[]`。
- `maxDays` 和 `maxMessages` 为群聊级配置，只影响后续模型上下文装载。

默认值：
- `maxDays = 2`
- `maxMessages = 200`

## 后端执行与上下文装载

### 消息发送

- 继续复用 `chat:send` 中已有的 `team_id` 字段。
- 在普通聊天中，`team_id` 仍表示当前对话的 Team。
- 在 GroupChat 中，`team_id` 表示“当前这条消息发给哪个 Agent”。

### GroupChat 校验

- 发送 GroupChat 消息时，后端读取 `Task.spec.teamRefs[]`。
- 若请求中的 `team_id` 不在允许列表内，返回明确错误。
- 若是旧数据且仅有 `teamRef`，则临时映射成单元素 `teamRefs[]`。

### AI 子任务归属

- 每条用户消息创建后，对应的 AI 子任务记录本次目标 `team_id`。
- 这样消息展示、重试、恢复流式输出都能稳定知道是谁在回复。

### 历史窗口装载

- 所有 Agent 读取同一份“群聊公共历史”。
- 历史窗口按两个条件共同裁剪：
  - 仅取最近 `maxDays` 天
  - 结果最多 `maxMessages` 条
- 两个条件取交集，避免上下文无限膨胀。

### 历史格式化

送给模型前统一标注发言者：
- `User[张三]: ...`
- `Agent[A]: ...`
- `Agent[B]: ...`

这样当前目标 Agent 能明确理解：
- 哪些是用户发言
- 哪些是其他 Agent 的历史回复

### 触发逻辑调整

Web GroupChat 不再依赖 `@TeamName` 文本匹配决定是否触发 AI。

新规则：
- 只要前端显式选中了本条消息目标 Agent，并传入合法 `team_id`，就触发 AI。
- `@` 仅是前端选择 Agent 的快捷方式。

外部 IM 群聊若仍依赖 `@bot` 触发，可继续保留原有逻辑，不与 Web GroupChat 强绑定。

## 前端设计

### 创建群聊

`CreateGroupChatDialog` 调整为：
- 多选 Agent
- 设置历史窗口：
  - 最近 N 天
  - 最多 N 条

默认值直接展示为：
- 2 天
- 200 条

### 输入区

在群聊输入卡片中新增：
- 单条消息目标 Agent 选择器

行为：
- 默认选中 `teamRefs[0]`
- 手动切换仅对本条消息生效
- 发送后重置回默认 Agent

### Mention 自动补全

`@` 自动补全展示该 GroupChat 的全部可用 Agent：
- 名称
- 图标

选择后：
- 输入框插入 `@AgentName`
- 当前消息目标同步切换为该 Agent

### 群聊设置入口

在现有 GroupChat 面板中新增设置入口，用于：
- 管理可用 Agents
- 修改历史读取窗口

## 迁移策略

采用“读取兼容，写入新结构”策略：

- 老 GroupChat 若仅包含 `teamRef`
  - 读取时映射为 `teamRefs = [teamRef]`
  - 历史窗口默认补全为 `2 天 / 200 条`
- 新建或编辑 GroupChat 时
  - 一律写入 `teamRefs[]`
  - 一律写入 `groupChatConfig.historyWindow`

首阶段不强依赖离线批量迁移脚本，先保证运行时兼容。

## 测试策略

### 前端

1. 创建群聊
- 可多选 Agent
- 默认历史窗口为 `2 天 / 200 条`
- 至少选择 1 个 Agent 才能提交

2. 输入区切换
- 群聊输入区显示 Agent 选择器
- 手动切换只作用于当前发送
- 发送完成后回到默认 Agent

3. 消息身份展示
- AI 消息头部显示实际回复 Agent 的名称与图标
- 混合 Agent 的历史回放保持正确身份，不被当前选中的 Agent 覆盖

3. `@` 自动补全
- 输入 `@` 弹出 Agent 列表
- 选择后插入 mention 并同步目标 Agent
- 删除 mention 不回退当前选择器状态

4. 消息展示
- AI 消息显示正确 Agent 名称和图标
- 历史回放可区分不同 Agent 回复

### 后端

1. GroupChat 配置解析
- `teamRefs[]` 正常读取
- 旧 `teamRef` 数据能兼容读取

2. 发送校验
- GroupChat 发送时仅允许使用 `teamRefs[]` 内的 `team_id`
- 非法目标返回错误

3. 历史窗口
- 同时按 `maxDays` 和 `maxMessages` 截断
- 超出条件的消息不会进入模型上下文

4. AI 子任务归属
- AI 子任务保存正确目标 `team_id`
- 重试和恢复流式输出保持原目标 Agent

5. 群聊历史格式化
- 用户与不同 Agent 的发言者标签正确

## 风险与边界

- 现有很多前端逻辑默认一个 Task 对应一个 Team，需要避免把 GroupChat 的“任务所属群聊”和“单条消息目标 Agent”混为一谈。
- 若消息展示层直接从任务级 `team_id` 推导头像/名称，会误显示，需要改成优先读取子任务级目标 Agent。
- 老数据兼容期内，读路径需要同时支持 `teamRef` 与 `teamRefs[]`，但写路径应统一收敛到新结构，避免双向扩散。
