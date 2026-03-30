---
sidebar_position: 1
---

# Skill HTTP 身份任务级注入设计

## 背景

上一版 `skill_identity_token` 设计默认把令牌当作“运行环境启动时注入的环境变量”处理。这在 `sandbox/docker` 场景下成立，因为容器生命周期基本等于任务生命周期；但在 `AI device/local executor` 场景下不成立，因为设备端 executor 可能常驻很多天，不会为每个任务重建宿主进程环境。

因此，`skill_identity_token` 的正确抽象不应是“容器级环境变量”，而应是“任务级执行上下文”。环境变量只是某些 runtime 对任务上下文的一种承载方式。

## 目标

- 统一 `sandbox/docker` 与 `AI device/local executor` 的 skill 身份注入语义
- 明确 `skill_identity_token` 属于任务级上下文，而非宿主进程级上下文
- 保持现有业务 HTTP 校验接口不变
- 避免 skill/provider 继续感知 runtime 差异并自行分支
- 明确 `skill_identity_token` 不得进入常驻 executor 进程状态或长期 session 状态

## 非目标

- 不重做 token 类型设计
- 不引入数据库存储或撤销机制
- 不在本次改造中重构所有 skill，只收敛实际用到 skill HTTP 身份的路径

## 问题定义

当前系统里存在两类执行边界：

1. `sandbox/docker`
- 每个任务对应独立容器
- 容器启动时注入 env，本质上就是任务级注入

2. `AI device/local executor`
- executor 进程常驻
- 任务通过 WebSocket 下发 `ExecutionRequest`
- 如果继续假设“token 必须存在于宿主进程 env”，则语义错误，也无法实现任务隔离

根因不是“AI device 漏传了 token”，而是“旧设计把 token 绑定到了不稳定的 runtime 载体上”。

## 方案选择

本次采用方案 A：统一为“任务级执行上下文注入”。

### 方案 A：任务级执行上下文注入

定义：
- `ExecutionRequest.skill_identity_token` 是唯一事实来源
- 每个 runtime 在“创建本次任务 agent/client/容器”时，把 token 注入本次任务的子执行上下文
- token 只允许存在于 `ExecutionRequest` 和本次任务临时执行上下文中

优点：
- 统一语义
- 与设备常驻进程模型兼容
- 不要求 skill 作者理解具体 runtime
- 与现有 `ExecutionRequest` 协议天然对齐

缺点：
- 需要明确每种 runtime 的任务启动边界

### 方案 B：保留双语义

定义：
- `sandbox` 继续读 env
- `AI device` 直接读 `ExecutionRequest`

问题：
- skill/provider 需要知道自己跑在哪种 runtime
- 后续新路径继续容易漏
- 架构上是继续积累条件分支

### 方案 C：把 token 写入常驻 executor 进程 env

不采用。

原因：
- 不是任务隔离
- 会导致跨任务污染
- 令牌生命周期和使用边界都错误

## 核心设计

### 1. 统一抽象

`skill_identity_token` 定义为任务级身份凭证：

- 来源：backend 构建 `ExecutionRequest` 时生成
- 传输：通过 `ExecutionRequest` / OpenAI metadata / WebSocket payload 透传
- 使用：在具体 runtime 创建本次任务执行单元时注入
- 约束：不得写入常驻 executor 进程 `os.environ`、全局单例状态、或跨请求复用的长期 session 状态

### 2. 统一构建与适配

逻辑上只保留一套构建过程：

1. 从 `ExecutionRequest` 构建任务级 identity context
2. 产出统一字段集合：
   - `WEGENT_SKILL_IDENTITY_TOKEN`
   - `WEGENT_SKILL_USER_NAME`
3. 由不同 runtime adapter 把这组字段挂载到本次任务执行单元

这样统一的是“构建逻辑”和“字段契约”，差异只保留在 runtime 挂载方式上：

- docker runtime：挂到任务容器 env
- local device runtime：挂到本次任务 client / subprocess env

### 3. Runtime 承载方式

#### sandbox/docker

保持现状，但语义上视为统一 task identity context 的 docker adapter：

- `executor_manager` 在创建任务容器时，将 `skill_identity_token` 注入 `WEGENT_SKILL_IDENTITY_TOKEN`
- 该 env 对容器来说是任务级的，因此语义正确

#### AI device/local executor

改为任务级子环境注入：

- device 端收到 `ExecutionRequest.skill_identity_token`
- 在创建 ClaudeCode/Agno 的本次任务 client 或子进程时，将其注入 `env`
- 不修改常驻 executor 进程自身的 `os.environ`
- 如果存在长驻 client/session 复用，则必须在每次任务边界刷新，不得沿用旧 token

### 4. Skill/Tool 读取约定

推荐统一约定：

1. 优先从显式任务上下文读取
2. 次选从本次任务子环境读取 `WEGENT_SKILL_IDENTITY_TOKEN`
3. 不依赖宿主进程全局 env 永远存在

本次先不做全量 skill 重构，但新代码和修复代码按这个方向收敛。

## 代码落点

### 1. backend 协议与派发

需要确认并测试：

- `backend/app/services/execution/request_builder.py`
- `backend/app/services/execution/dispatcher.py`
- `shared/models/execution.py`
- `shared/models/openai_converter.py`

目标：
- 保证 `skill_identity_token` 能进入 WebSocket payload
- 保证 device 路径和 chat_shell 路径使用同一字段

### 2. executor 本地设备路径

重点关注：

- `executor/modes/local/handlers.py`
- `executor/tasks/task_processor.py`
- `executor/services/agent_service.py`
- 新增统一 helper 的落点
- `executor/agents/claude_code/local_mode_strategy.py`
- `executor/agents/claude_code/config_manager.py`
- Agno 对应的任务初始化路径

目标：
- 抽一个统一的 task identity context builder
- 找到“本次任务 agent/client 创建时的 env 合并点”
- 由 runtime adapter 在该点挂载统一字段集合

### 3. sandbox/docker 路径

保持现有注入逻辑，但将其文档语义从“容器级注入”修正为“任务级注入的 docker 实现”：

- `executor_manager/executors/docker/executor.py`
- `executor_manager/services/sandbox/manager.py`

## 测试策略

### 单元测试

必须补齐的最小覆盖：

1. backend WebSocket payload 包含 `skill_identity_token`
2. executor local handler 从 payload 还原后保留 `skill_identity_token`
3. ClaudeCode local mode 在本次任务 env 中注入 `WEGENT_SKILL_IDENTITY_TOKEN`
4. sandbox/docker 现有 env 注入测试继续通过
5. 不存在将 token 写入全局 `os.environ` 或长期 session 状态的实现

### 集成验证

建议人工验证两条链路：

1. sandbox skill
- 容器内能看到 `WEGENT_SKILL_IDENTITY_TOKEN`
- 调用 `/api/internal/skill-identity/verify` 返回 `matched: true`

2. AI device skill
- 不要求设备宿主进程本身有全局 env
- 但任务执行时 skill 能通过本次任务执行环境或上下文拿到 token
- 调用 `/api/internal/skill-identity/verify` 返回 `matched: true`

## 风险与约束

### 1. ClaudeCode 与 Agno 的任务边界可能不同

不应为了“统一抽象”过早引入新的复杂基类。先分别在各自已有的任务启动边界接入，再抽共性。

### 2. 长生命周期 executor / session 带来的串值风险

executor 可能常驻很多天，因此：

- 不能把 token 放在宿主进程 env
- 不能把 token 缓存在全局单例
- 不能因为 session/client 复用就沿用上次任务 token

### 3. SkillBinary 仍是独立运行时来源

若改动涉及动态 skill 代码，必须同步更新数据库里的 `SkillBinary`。只改工作区文件不足以改变实际运行行为。

### 4. 不要再把 env 当成协议本体

env 只是 runtime 实现细节。真正稳定的契约应始终是 `ExecutionRequest.skill_identity_token`。

## 结论

本次设计结论如下：

- `skill_identity_token` 是任务级身份凭证
- 统一逻辑是“从 `ExecutionRequest` 构建 task identity context”，而不是分别为不同 runtime 设计不同 token 语义
- `sandbox/docker` 与 `AI device` 都应在“创建本次任务执行单元”时注入
- `sandbox` 使用容器 env 只是任务级注入的一种实现
- `AI device` 不能依赖宿主进程 env，而应在每次任务 agent/client 创建时注入子环境
- token 不得进入常驻 executor 状态，只允许存在于 `ExecutionRequest` 和本次任务临时执行上下文中

这比继续沿用“谁启动时能塞 env 就塞 env”的思路更稳定，也更符合系统分层。
