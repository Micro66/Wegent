import type { CloudLoopItem } from '@/api/deliveries'

const STORAGE_KEY = 'wework.project-board-snapshots.v1'
const MAX_ENTRIES = 40
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000

interface BoardSnapshot {
  cachedAt: number
  items: CloudLoopItem[]
}

interface BoardSnapshotStore {
  entries: Record<string, BoardSnapshot>
}

function readStore(): BoardSnapshotStore {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY)
    if (!raw) return { entries: {} }
    const parsed = JSON.parse(raw) as Partial<BoardSnapshotStore>
    return parsed.entries && typeof parsed.entries === 'object'
      ? { entries: parsed.entries }
      : { entries: {} }
  } catch {
    return { entries: {} }
  }
}

export function readBoardSnapshot(
  projectSpaceKey: string,
  now = Date.now()
): CloudLoopItem[] | null {
  const snapshot = readStore().entries[projectSpaceKey]
  if (!snapshot || !Array.isArray(snapshot.items)) return null
  if (now - snapshot.cachedAt > MAX_AGE_MS) return null
  return snapshot.items
}

export function writeBoardSnapshot(
  projectSpaceKey: string,
  items: CloudLoopItem[],
  now = Date.now()
): void {
  try {
    const store = readStore()
    store.entries[projectSpaceKey] = { cachedAt: now, items }
    const entries = Object.entries(store.entries)
      .filter(([, snapshot]) => now - snapshot.cachedAt <= MAX_AGE_MS)
      .sort(([, left], [, right]) => right.cachedAt - left.cachedAt)
      .slice(0, MAX_ENTRIES)
    globalThis.localStorage?.setItem(
      STORAGE_KEY,
      JSON.stringify({ entries: Object.fromEntries(entries) })
    )
  } catch {
    // The in-memory board remains usable when durable browser storage is unavailable.
  }
}
