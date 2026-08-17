import { afterEach, describe, expect, it } from 'vitest'
import type { CloudLoopItem } from '@/api/deliveries'
import { readBoardSnapshot, writeBoardSnapshot } from './boardSnapshotCache'

const item = {
  id: 'WEG-1',
  title: 'Cached task',
} as CloudLoopItem

describe('boardSnapshotCache', () => {
  afterEach(() => localStorage.clear())

  it('persists snapshots independently for each project space', () => {
    writeBoardSnapshot('backend:11', [item], 100)
    writeBoardSnapshot('local:11', [{ ...item, id: 'LOCAL-1' }], 200)

    expect(readBoardSnapshot('backend:11', 300)).toEqual([item])
    expect(readBoardSnapshot('local:11', 300)).toEqual([{ ...item, id: 'LOCAL-1' }])
  })

  it('ignores snapshots older than seven days', () => {
    writeBoardSnapshot('backend:11', [item], 100)

    expect(readBoardSnapshot('backend:11', 100 + 7 * 24 * 60 * 60 * 1000 + 1)).toBeNull()
  })
})
