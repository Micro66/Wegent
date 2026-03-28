---
sidebar_position: 1
---

# Skill HTTP 身份令牌设计

## 概述

本设计为 skill 脚本新增一套独立于现有任务执行链路的 HTTP 身份能力，使脚本在 executor 或 sandbox 运行时能够稳定获取：

- 当前用户 `user_name`
- 一个专用于 skill 发起业务 HTTP 请求的身份令牌

该能力的目标不是让业务服务端直接解析并信任 token，而是让业务方把 `token + user_name` 回传给 Wegent 校验，从而确认“这是用户 X 发起的 skill 调用”。

已确认的产品约束：

- 令牌在 executor 或 sandbox 创建时生成并注入
- 第一版使用独立 JWT，不落库
- 第一版先不设置过期时间
- 业务方通过 Wegent 新接口在线校验，不提供“根据 token 反查用户”的接口

## 问题定义

当前执行链路中已经存在：

- `ExecutionRequest.user_name`
- `ExecutionRequest.auth_token`
- `TASK_INFO` 环境变量

但这些能力不适合作为 skill 调业务接口的正式身份契约：

1. `auth_token` 是现有任务链路用 token，语义不适合扩散到业务 HTTP 调用
2. `TASK_INFO` 是上下文载体，不是面向 skill 作者的稳定接口
3. shell skill 不适合依赖复杂的换 token 流程或额外服务发现

因此需要一套更直接、更独立的契约。

## 方案选择

本次采用方案 1：新增独立 JWT 类型 `skill_identity_token`，由业务方通过 Wegent 在线校验使用。

### 备选方案对比

1. 独立 JWT + Wegent 在线校验（本次采用）
- 优点：实现简单，不需要新表；与现有 task token 分离；skill 脚本直接可用
- 缺点：第一版若不设置过期，也不落库，则无法单独撤销

2. Opaque token + 服务端落库存映射
- 优点：边界更强，可撤销，可后续精细治理
- 缺点：需要新增表、hash 存储、撤销链路；首版实现成本更高

3. 启动注入 bootstrap credential，运行时再换短期 token
- 优点：业界更标准，安全边界更强
- 缺点：对 shell skill 过重；需要额外 helper 或刷新机制，不符合本次约束

## 核心设计

### 1. 新令牌类型

新增独立 JWT：`skill_identity_token`

用途：
- 仅用于 skill 脚本对业务 HTTP 接口声明“我是代表某个 Wegent 用户发起调用”
- 不替代 task token
- 不用于 skill 下载、附件上传下载、MCP 等现有内部链路

### 2. 运行时环境变量

executor 或 sandbox 创建时固定注入：

- `WEGENT_SKILL_USER_NAME`
- `WEGENT_SKILL_IDENTITY_TOKEN`

说明：
- 这两个变量面向 skill 作者，是正式契约
- `TASK_INFO` 保持兼容存在，但不再作为推荐的 skill HTTP 身份入口

### 3. Skill 调用业务接口方式

skill 发业务请求时带：

- `Authorization: Bearer <WEGENT_SKILL_IDENTITY_TOKEN>`
- `X-Wegent-User-Name: <WEGENT_SKILL_USER_NAME>`

shell skill 示例：

```bash
curl \
  -H "Authorization: Bearer $WEGENT_SKILL_IDENTITY_TOKEN" \
  -H "X-Wegent-User-Name: $WEGENT_SKILL_USER_NAME" \
  https://biz.example.com/api/action
```

### 4. 业务方使用方式

业务服务端收到请求后，不自行建立本地身份体系，也不需要解析用户身份结果。

业务服务端将：

- bearer token
- 声称的 `user_name`

回传给 Wegent 的校验接口，判断是否匹配。

Wegent 只返回校验结果，不提供 token 反查用户的能力。

## JWT Claims 设计

第一版 `skill_identity_token` 建议包含：

- `type: "skill_identity"`
- `user_id`
- `user_name`
- `runtime_type`: `executor` 或 `sandbox`
- `runtime_name`
- `iat`

第一版不加 `exp`，但代码结构要预留后续添加 `exp` 的能力。

明确不包含：

- task token 的既有语义类型
- 可直接代表完整用户登录态的 claims
- 面向业务方的敏感额外上下文

## 后端接口设计

新增内部接口：

`POST /api/internal/skill-identity/verify`

请求体：

```json
{
  "token": "jwt-string",
  "user_name": "alice"
}
```

成功响应：

```json
{
  "matched": true
}
```

失败响应：

```json
{
  "matched": false,
  "reason": "user_mismatch"
}
```

`reason` 建议枚举：

- `invalid_token`
- `wrong_token_type`
- `missing_user_name`
- `user_mismatch`

原则：

- 不返回 token 对应的真实用户名
- 不返回 user_id
- 不做 token 反查接口

## 代码落点

### 1. 令牌签发

新增独立签发函数，位置建议：

- `backend/app/services/auth/skill_identity_token.py`

职责：

- 创建 `skill_identity_token`
- 校验并解码 `skill_identity_token`

避免把逻辑继续塞进现有 `task_token.py`，降低语义耦合。

### 2. 请求构建

在执行请求构建阶段生成新 token，并写入 `ExecutionRequest`：

- `backend/app/services/execution/request_builder.py`
- `shared/models/execution.py`

建议新增字段：

- `skill_identity_token: str = ""`

这样 backend、executor、chat_shell 使用统一协议传递新字段。

### 3. 环境变量注入

在 executor/sandbox 启动和任务派发路径中，将新字段写入环境变量：

- executor 容器环境
- sandbox 执行环境

需要检查并修改的主要位置：

- `executor_manager/executors/docker/executor.py`
- executor 侧读取/派发环境的代码
- sandbox 相关环境注入路径

### 4. 校验接口

新增 FastAPI internal endpoint，位置建议：

- `backend/app/api/endpoints/internal/skill_identity.py`

职责：

- 校验 JWT 签名
- 校验 `type == "skill_identity"`
- 比较 `user_name` 是否匹配
- 返回最小结果

## 错误处理

### Skill 侧

skill 环境中缺失以下变量时，应视为运行环境配置错误：

- `WEGENT_SKILL_USER_NAME`
- `WEGENT_SKILL_IDENTITY_TOKEN`

首版不要求平台提供额外 helper，skill 按普通环境变量使用即可。

### 业务方校验侧

业务方调用 Wegent 校验接口失败时，建议默认拒绝该请求，而不是放行。

理由：

- 本能力本质是在线认证
- 若 Wegent 不可达而仍放行，会直接破坏认证边界

## 安全边界与限制

本次方案的安全边界是：

- skill 使用独立 token，不复用 task token
- 业务方不通过 Wegent 以外的方式确认用户身份
- Wegent 不提供 token 反查用户接口

已知限制：

1. 第一版不落库，无法单独撤销某个 token
2. 第一版不设置过期时间，泄露窗口长
3. 如果业务方绕过 Wegent 在线校验，边界会被削弱

因此第一版的约束必须明确写入文档：

- 业务方必须始终调用 Wegent 校验接口
- 不应在业务方本地直接验签并信任该 token

## 后续演进方向

后续若要收紧，可逐步演进为：

1. 增加 `exp`
2. 增加 token 落库或黑名单撤销
3. 为不同业务域增加 `aud`
4. 根据 runtime 生命周期做自动失效

本次不做这些能力，只保留代码结构扩展点。

## 测试策略

### 后端单测

- `create_skill_identity_token` 生成正确 claims
- `verify_skill_identity_token` 正确校验 `type`
- 错误 token / 错误类型 / 篡改 token 返回失败
- verify 接口对 `user_name` 不匹配返回 `matched=false`
- verify 接口不泄露真实绑定用户

### 集成测试

- `request_builder` 生成并传递 `skill_identity_token`
- `ExecutionRequest` 序列化反序列化保留该字段
- executor/sandbox 环境变量包含新字段

### 回归测试

- 现有 `auth_token` / `TASK_INFO` 相关逻辑不回归
- 现有 task token、skill 下载、附件链路不受影响

## 实施结论

第一版按以下原则实施：

- 新增独立 JWT 类型 `skill_identity_token`
- executor/sandbox 创建时注入 `WEGENT_SKILL_USER_NAME` 与 `WEGENT_SKILL_IDENTITY_TOKEN`
- 新增 Wegent 校验接口，仅支持 `token + user_name -> matched`
- 不提供 token 反查用户能力
- 不落库，不设置过期时间，但预留后续扩展空间
