---
name: "subscription-manager"
description: "Create and manage scheduled subscription tasks. Use when the user wants to set up recurring reminders, periodic reports, scheduled checks, or any automated tasks that run on a schedule. Supports cron expressions, fixed intervals, and one-time executions."
displayName: "订阅任务管理"
version: "1.0.0"
author: "Wegent Team"
tags: ["subscription", "scheduler", "automation", "cron", "periodic"]
bindShells:
  - Chat
  - Agno
  - ClaudeCode
mcpServers:
  wegent-subscription:
    type: streamable-http
    url: "${{backend_url}}/mcp/subscription/sse"
    headers:
      Authorization: "Bearer ${{task_token}}"
    timeout: 60
---

# Subscription Task Manager

You now have access to subscription management tools. Use them to create scheduled, recurring, or periodic tasks for the user.

## When to Use

1. **Recurring reminders** - "remind me every morning", "notify me weekly"
2. **Periodic reports** - "send me a daily summary", "generate weekly analytics"
3. **Scheduled checks** - "check status every hour", "monitor every 30 minutes"
4. **One-time future tasks** - "remind me tomorrow at 3pm", "check this next Friday"
5. **Any automated recurring task** - anything that needs to run on a schedule

## Available Tools

### 1. preview_subscription

**ALWAYS call this first** when the user mentions scheduling intent.

Generates a preview of the subscription configuration **without creating it**. Shows a summary table for user confirmation.

**Key Parameters:**
- `display_name` (string): Human-readable task name
- `trigger_type` (string): `"cron"`, `"interval"`, or `"one_time"`
- `prompt_template` (string): The prompt to execute on each run
- `cron_expression` (string): For cron type, e.g., `"0 9 * * *"` (daily at 9am)
- `interval_value` + `interval_unit`: For interval type, e.g., `30 + "minutes"`
- `execute_at` (string): For one_time type, ISO format datetime
- `preserve_history` (boolean): Whether to keep conversation context across runs
- `expiration_type` + `expiration_fixed_date`/`expiration_duration_days`: Optional expiration

**Workflow:**
1. User: "remind me every morning to drink water"
2. You: Call `preview_subscription` with appropriate parameters
3. You: Show the returned preview table to the user
4. You: Ask "请确认以上配置是否正确？回复「执行」创建任务，或告诉我需要修改的内容。"
5. User: "执行" / "确认"
6. You: Call `create_subscription` with the `preview_id`

### 2. create_subscription

**ONLY call this after** the user confirms the preview.

Creates the actual subscription task. Requires `preview_id` from `preview_subscription`.

**Required Parameters:**
- `display_name` (string): Task name
- `trigger_type` (string): Same as preview
- `prompt_template` (string): Same as preview
- `preview_id` (string): **REQUIRED** - from `preview_subscription` response

## Important Rules

1. **NEVER call `create_subscription` directly** - always use `preview_subscription` first
2. **When time is vague** (e.g., "every morning"), offer 2-3 specific time options
3. **Use `preserve_history: true`** for tasks needing context continuity (daily reports, monitoring)
4. **Use `preserve_history: false`** for independent tasks (reminders, checks)
5. **Name generation**: Create concise, readable names based on task content

## Examples

### Daily morning reminder

```
preview_subscription(
  display_name="Daily Morning Water Reminder",
  trigger_type="cron",
  cron_expression="0 9 * * *",
  prompt_template="Remind me to drink a glass of water to start the day healthy!",
  preserve_history=false
)
```

### Weekly report (preserves history for context)

```
preview_subscription(
  display_name="Weekly Project Summary",
  trigger_type="cron",
  cron_expression="0 18 * * 5",
  prompt_template="Generate a weekly summary of project progress, blockers, and next week's priorities.",
  preserve_history=true,
  history_message_count=20
)
```

### Every 30 minutes monitoring

```
preview_subscription(
  display_name="Server Status Monitor",
  trigger_type="interval",
  interval_value=30,
  interval_unit="minutes",
  prompt_template="Check server CPU and memory usage. Alert if CPU > 80% or memory > 90%.",
  preserve_history=false
)
```

### One-time future task

```
preview_subscription(
  display_name="Deployment Reminder",
  trigger_type="one_time",
  execute_at="2025-04-15T14:00:00",
  prompt_template="Remind me to deploy the new feature to production.",
  preserve_history=false
)
```

### With expiration (30 days)

```
preview_subscription(
  display_name="Trial Monitoring",
  trigger_type="interval",
  interval_value=1,
  interval_unit="days",
  prompt_template="Check trial account status and send daily summary.",
  expiration_type="duration_days",
  expiration_duration_days=30
)
```

## Response Format

**preview_subscription returns:**
```json
{
  "success": true,
  "preview_id": "preview_abc123",
  "execution_id": "exec_xyz789",
  "preview_table": "markdown table showing configuration",
  "message": "检测到您需要创建定时任务，请确认以下配置："
}
```

**create_subscription returns:**
```json
{
  "success": true,
  "subscription": {
    "id": 123,
    "name": "sub-daily-water-abc123",
    "display_name": "Daily Morning Water Reminder",
    "trigger_type": "cron",
    "next_execution_time": "2025-04-10T09:00:00"
  },
  "message": "订阅任务创建成功！将于 2025-04-10 09:00:00 首次执行。"
}
```
