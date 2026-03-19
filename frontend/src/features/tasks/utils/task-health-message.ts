export function buildTaskHealthInterruptedMessage(durationLabel: string): string {
  if (!durationLabel) {
    return '任务已异常终止'
  }

  return `任务已异常终止（约 ${durationLabel}前失去响应）`
}
