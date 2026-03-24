---
sidebar_position: 1
---

# Skill ID 执行链路兼容改造实施计划

## 复盘结论（已确认）

本次改造采用以下最终口径：

1. 保留 `Ghost.spec.skills` 与 `Ghost.spec.preload_skills`（兼容旧版本）。
2. 新增 `Ghost.spec.skill_refs` 与 `Ghost.spec.preload_skill_refs`（精确定位元数据）。
3. 协议层继续下发 `skill_names`，并使用已有 `skill_configs`（含 `skill_id`）作为新执行链路主来源。
4. Executor 下载优先级：
   - `skill_configs.skill_id`
   - `preload_skill_refs[name]`（同名覆盖）
   - `skill_refs[name]`
   - 旧逻辑 name 查询
5. 下载集合：`unique(skills ∪ preload_skills)`。
6. 去重策略维持按 `name`。
7. 暂不支持“同时挂两个同名 skill”。
8. 在三池共库、设备不可实时升级前提下，旧协议长期兼容。

## 当前实现缺口（待修复）

1. `ExecutionRequest.skill_refs` 已生成，但在 `shared/models/openai_converter.py` 的 metadata 双向转换中未透传，导致 Executor 侧 `task_data.skill_refs={}`。
2. `_get_bot_skills()` 已改为返回四元组，但 early return 分支仍返回三元组，存在运行时解包风险。
3. Executor 当前仅使用 `task_data.skill_refs`，未优先消费已存在的 `task_data.skill_configs.skill_id`。
4. `preload_skill_refs` 与 `skill_refs` 的覆盖合并策略尚未统一落地到下载前映射构建。

## 实施阶段

## 阶段 A：修复协议透传与签名一致性（必须先做）

### A1. 修复 metadata 透传

文件：
- `shared/models/openai_converter.py`

改动：
1. `from_execution_request()` 的 metadata 增加：
   - `skill_refs`
   - `preload_skill_refs`（如果最终放在 ExecutionRequest 中）
2. `to_execution_request()` 反序列化增加对应字段。

验收：
- executor 收到的 `/v1/responses` metadata 中可见 `skill_refs`。

### A2. 修复 `_get_bot_skills` 返回值一致性

文件：
- `backend/app/services/execution/request_builder.py`

改动：
- 所有 early return 统一返回四元组：
  - `([], [], [], {})`

验收：
- 无 `ghostRef`、无 ghost 等分支不再触发 tuple unpack 异常。

## 阶段 B：统一 Executor 下载决策（核心）

### B1. 增加统一映射构建函数

文件：
- `executor/agents/claude_code/skill_deployer.py`（或提取到独立 util）

新增逻辑：
- 输入：`skills`, `preload_skills`, `skill_configs`, `skill_refs`, `preload_skill_refs`
- 输出：`resolved_skill_map: Dict[name, {skill_id, namespace, is_public}]`

优先级：
1. 先用 `skills` 填充（来自 `skill_configs`/`skill_refs`）
2. 再用 `preload_skills` 对应 ref 覆盖同名项（手动指定优先）

### B2. 下载改造为“按映射优先，name 回退”

文件：
- `executor/services/api_client.py`
- `executor/agents/claude_code/skill_deployer.py`

改动：
1. 下载入口传入 `resolved_skill_map`。
2. 单 skill 下载：
   - 有 `skill_id` -> `/kinds/skills/{skill_id}/download`
   - 无 `skill_id` -> 旧 `/kinds/skills?name=...`

验收：
- 当 metadata 含 `skill_configs.skill_id` 时，日志应显示走 id 下载分支。

## 阶段 C：Ghost 写路径一致性强化

文件：
- `backend/app/services/adapters/bot_kinds.py`

改动：
1. 创建/更新 Bot 时保持双写：
   - `skills` + `skill_refs`
   - `preload_skills` + `preload_skill_refs`
2. 增加校验：
   - `preload_skills` 必须可解析到 ref。

验收：
- DB 中 ghost JSON 的四个字段一致存在且对应关系正确。

## 阶段 D：回归测试与灰度开关

### D1. 测试补充

后端：
- `backend/tests/services/execution/` 增加：
  - metadata round-trip 后 `skill_refs` 不丢失
  - `_get_bot_skills` 四元组 early return

执行器：
- 新增/补充测试：
  - `skill_configs` 命中 id 下载
  - 无 id 时 fallback name 查询
  - preload 覆盖 skills

### D2. 灰度开关（建议）

- `SKILL_DOWNLOAD_USE_SKILL_CONFIG_ID=true`
- `SKILL_DOWNLOAD_ENABLE_LEGACY_NAME_FALLBACK=true`

## 分文件任务清单

1. `shared/models/execution.py`
- 如需，补 `preload_skill_refs` 字段定义。

2. `shared/models/openai_converter.py`
- metadata 双向透传 `skill_refs`（和 `preload_skill_refs`）。

3. `backend/app/services/execution/request_builder.py`
- `_get_bot_skills` early return 四元组一致。

4. `executor/agents/claude_code/skill_deployer.py`
- 构建统一 `resolved_skill_map`。
- 优先使用 `skill_configs`，再 `skill_refs`。

5. `executor/services/api_client.py`
- 接收 resolved map 并执行 id 优先下载。

6. `backend/app/services/adapters/bot_kinds.py`
- 保持 ghost 四字段双写与一致性。

## 验收标准

1. 同名 skill（个人/组）场景下，新链路稳定命中正确 `skill_id`。
2. 旧版本设备与服务在无新字段情况下仍可执行（name fallback 生效）。
3. `/v1/responses` metadata 中存在并透传 `skill_refs`（如启用 `preload_skill_refs` 也需存在）。
4. 下载日志可区分：id 下载与 name fallback。
5. 无 `_get_bot_skills` tuple unpack 异常。

## 回滚预案

1. 关闭 id 优先开关，仅走 name 查询。
2. 保留 `skills` 旧字段与旧下载路径，不需回滚数据库。
3. `skill_refs` 作为附加元数据可被安全忽略。

## 建议执行顺序

1. 先修 `openai_converter` 与 `_get_bot_skills` 签名问题。
2. 再改 Executor 决策优先级（skill_configs -> refs -> name）。
3. 最后补测试并在测试池灰度。
