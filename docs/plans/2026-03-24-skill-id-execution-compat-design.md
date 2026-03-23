---
sidebar_position: 1
---

# Skill ID 执行链路兼容改造设计

## 概述

本设计用于修复同名 Skill 在个人与组作用域下的串用问题，并满足以下强约束：

- 三个服务池（稳定池/内测池/测试池）版本可能不一致。
- 三个服务池共享同一数据库。
- AI 设备无法实时升级，旧版本客户端需长期可用。

本次采用渐进兼容方案：

- 保留 `Ghost.spec.skills` 作为兼容索引（按 `name`）。
- 新增 `Ghost.spec.skill_refs` 作为精确元数据（`name -> skill_id`）。
- Backend 同时下发 `skill_names` 与 `skill_refs`。
- Executor 新版本优先按 `skill_id` 下载；无 `skill_refs` 时回退旧逻辑按 `name`。
- 继续按 `name` 去重。
- 暂不支持“同时挂两个同名 skill”能力。

## 当前问题与根因

当前主链路依赖 `name` 作为运行时定位键：

1. Ghost 配置中 `spec.skills` 仅保存字符串数组。
2. 执行请求中主要透传 `skill_names`。
3. Executor 下载时通过 `/kinds/skills?name=...` 查询并取首条结果。

这会导致同名 Skill（个人 `default` 与组 `group_namespace`）在某些上下文下命中错误对象。

## 目标与非目标

### 目标

1. 新版本执行链路优先使用 `skill_id`，避免同名歧义。
2. 旧版本设备与服务不中断。
3. 不要求一次性全量迁移或同步升级。
4. 读写行为可观测、可灰度、可回滚。

### 非目标

1. 本期不实现“同时启用两个同名 Skill”。
2. 本期不强制改造前端交互与状态管理。
3. 本期不删除旧字段 `skills`。

## 数据模型设计

### Ghost 新结构

在保留旧字段基础上新增：

- `spec.skill_refs: Dict[str, SkillRefMeta]`
- `spec.preload_skill_refs: Dict[str, SkillRefMeta]`

`SkillRefMeta` 结构：

```json
{
  "skill_id": 101,
  "namespace": "default",
  "is_public": false
}
```

完整示例：

```json
{
  "spec": {
    "skills": ["excel-helper", "wiki-submit"],
    "skill_refs": {
      "excel-helper": {"skill_id": 101, "namespace": "default", "is_public": false},
      "wiki-submit": {"skill_id": 202, "namespace": "team-a", "is_public": false}
    },
    "preload_skills": ["excel-helper"],
    "preload_skill_refs": {
      "excel-helper": {"skill_id": 101, "namespace": "default", "is_public": false}
    }
  }
}
```

### 一致性约束

新版本写入时必须满足：

1. `skills` 中每个 name 都必须存在于 `skill_refs` 的 key。
2. `preload_skills` 中每个 name 都必须存在于 `preload_skill_refs` 的 key。
3. `preload_skills` 必须是 `skills` 的子集。
4. key 规范化：仅按原始 skill name 作为 key，不做大小写折叠。

## 解析与歧义规则

### 运行时解析流程

1. 先读取 `skills`（决定启用集合和顺序）。
2. 对每个 `skill_name`，优先从 `skill_refs[skill_name]` 获取 `skill_id`。
3. 若该项缺失，按上下文回退解析并可回写补齐。

### 歧义优先级（按确认规则）

1. 编辑个人（`namespace=default`）
- 优先：`user_id=current_user AND namespace=default`。

2. 编辑组（`namespace=group_xxx`）
- 优先：`namespace=group_xxx`。

3. 若优先桶内仍不唯一
- 返回明确错误，不随机选取。

## 执行协议设计（Phase B 重点）

ExecutionRequest 同时携带：

- `skill_names: list[str]`（兼容旧版本）
- `skill_refs: dict[str, SkillRefMeta]`（新版本优先）

兼容原则：

1. 旧 Executor：忽略 `skill_refs`，继续使用 `skill_names`。
2. 新 Executor：若某 `name` 在 `skill_refs` 存在，优先按 `skill_id` 下载。
3. 新 Executor：若 `skill_refs` 缺失该 `name`，回退旧 name 查询。
4. 去重策略保持不变：按 `name` 去重。

## 下载策略设计

### 新版本路径

当 `skill_refs[name]` 存在时：

- 直接调用 `/api/v1/kinds/skills/{skill_id}/download?namespace=...`

### 旧版本回退路径

当 `skill_refs` 不存在或缺项时：

- 调用 `/api/v1/kinds/skills?name=...&namespace=...`
- 维持现有行为（兼容旧设备）。

## 兼容矩阵（三池混跑）

1. 新 Backend + 旧 Executor
- 可用。旧 Executor 仅消费 `skill_names`。

2. 旧 Backend + 新 Executor
- 可用。新 Executor 检测无 `skill_refs` 后回退旧逻辑。

3. 新 Backend + 新 Executor
- 目标态。优先按 `skill_id` 下载，规避同名串用。

4. 任意旧设备
- 继续可用，不要求实时升级。

## 发布与灰度计划

### 阶段 1：Backend 扩展上线（双字段）

1. 增加 schema 对 `skill_refs`/`preload_skill_refs` 的读写支持。
2. 写路径双写（保留 `skills`，新增 `skill_refs`）。
3. 请求下发双字段（`skill_names` + `skill_refs`）。

### 阶段 2：Executor 上线（优先 skill_id）

1. 增加 `skill_refs` 解析。
2. 优先 `skill_id` 下载；缺失时回退 name 下载。
3. 保持按 `name` 去重。

### 阶段 3：三池灰度

1. 测试池先行。
2. 内测池跟进。
3. 稳定池最后。
4. 在三池完全完成前，不关闭旧字段支持。

## 开关设计

建议引入以下开关：

1. `SKILL_REFS_READ_ENABLED`
- 控制是否读取 `skill_refs`。

2. `SKILL_REFS_DUAL_WRITE_ENABLED`
- 控制写路径是否双写 `skills` + `skill_refs`。

3. `SKILL_REFS_DOWNLOAD_BY_ID_ENABLED`
- 控制 Executor 是否优先按 `skill_id` 下载。

4. `SKILL_REFS_STRICT_AMBIGUITY_FAIL`
- 控制歧义时是否强制失败（建议开启）。

## 监控与告警

核心指标：

1. `skill_refs_hit_count`
- 走 `skill_refs` 命中次数。

2. `skill_refs_missing_fallback_count`
- 缺失 `skill_refs` 后回退 name 查询次数。

3. `skill_ambiguity_error_count`
- 同名解析歧义失败次数。

4. `skill_download_by_id_count`
- 按 `skill_id` 下载次数。

5. `skill_download_by_name_count`
- 按 `name` 下载次数。

告警建议：

- `skill_ambiguity_error_count > 0` 触发高优先级告警。
- `skill_refs_missing_fallback_count` 持续偏高触发中优先级告警。

## 回滚策略

1. 关闭 `SKILL_REFS_DOWNLOAD_BY_ID_ENABLED`，Executor 恢复旧下载路径。
2. 关闭 `SKILL_REFS_READ_ENABLED`，Backend 恢复旧解析路径。
3. 保持 `skills` 数据不变，确保回滚后系统可运行。
4. 不需要回滚数据库结构（新增字段可忽略）。

## 测试计划

### 单元测试

1. 解析器优先 `skill_refs` 命中。
2. `skill_refs` 缺失项回退解析。
3. 个人/组上下文优先级正确。
4. 歧义冲突时报错。

### 集成测试

1. 同名 Skill（个人+组）场景：
- 新链路确认下载目标为 `skill_id` 指向对象。

2. 混合版本场景：
- 无 `skill_refs` 时新 Executor 回退旧逻辑可用。

3. 双写一致性：
- `skills` 和 `skill_refs` key 集合一致。

### 回归测试

1. 不选择 Skill 的任务行为不变。
2. 仅 public Skill 的行为不变。
3. preload 技能链路行为不变。

## 文件级改造清单

### Backend

1. `backend/app/schemas/kind.py`
- 增加 Ghost 的 `skill_refs` / `preload_skill_refs` schema。

2. `backend/app/services/adapters/bot_kinds.py`
- 创建/更新 Bot/Ghost 时双写新旧字段。

3. `backend/app/services/execution/request_builder.py`
- 构建 ExecutionRequest 时同时输出 `skill_names` 与 `skill_refs`。
- 解析链路优先使用 `skill_refs`。

4. `shared/models/execution.py`
- 增加 `skill_refs` 字段，保持反序列化兼容。

### Executor

1. `executor/services/api_client.py`
- 增加按 `skill_id` 下载接口调用。
- 保留 name 查询回退路径。

2. `executor/agents/claude_code/skill_deployer.py`
- 加入 `skill_refs` 优先分支。

3. `executor/app.py`
- 初始化下载链路接入 `skill_refs`。

## 验收标准

1. 组/个人同名 Skill 场景下，新链路命中正确 `skill_id`。
2. 旧设备在未升级情况下仍可执行任务。
3. 灰度期间无批量下载失败或任务不可执行。
4. 监控可观察到 `skill_download_by_id_count` 稳定上升。

## 决策结论

采用“`skills` 作为索引 + `skill_refs` 作为元数据”的双轨兼容方案。

这是当前约束下风险最低、上线可控、可长期演进的方案。
