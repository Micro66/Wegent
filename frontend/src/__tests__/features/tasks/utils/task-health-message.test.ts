import { buildTaskHealthInterruptedMessage } from '@/features/tasks/utils/task-health-message'

describe('buildTaskHealthInterruptedMessage', () => {
  it('uses lost response wording for known duration', () => {
    expect(buildTaskHealthInterruptedMessage('38秒')).toBe('任务已异常终止（约 38秒前失去响应）')
  })

  it('falls back to a plain interrupted message when duration is missing', () => {
    expect(buildTaskHealthInterruptedMessage('')).toBe('任务已异常终止')
  })
})
