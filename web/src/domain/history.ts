/**
 * 撤销/重做历史。
 *
 * 拖拽会在一秒内产生上百次变更，不能每次都入栈。
 * 用 begin/commit 包住一次连续操作：拖动开始记快照，松手才真正入栈。
 */

export interface History<T> {
  readonly present: T
  readonly canUndo: boolean
  readonly canRedo: boolean
  readonly undoDepth: number
  readonly redoDepth: number
  /** transient=true 时只更新现值、不入栈（拖拽中） */
  set(next: T, transient?: boolean): void
  /** 开始一段连续操作（拖拽按下） */
  begin(): void
  /** 结束连续操作并入栈（松手）；没有变化则不入栈 */
  commit(): void
  undo(): void
  redo(): void
  reset(value: T): void
}

export const HISTORY_LIMIT = 50

export function createHistory<T>(initial: T, limit = HISTORY_LIMIT): History<T> {
  let present = initial
  let past: T[] = []
  let future: T[] = []
  let pending: { snapshot: T } | null = null

  const same = (a: T, b: T) => JSON.stringify(a) === JSON.stringify(b)

  const push = (snapshot: T) => {
    past.push(snapshot)
    if (past.length > limit) past.shift()
    future = []
  }

  return {
    get present() {
      return present
    },
    get canUndo() {
      return past.length > 0 || pending !== null
    },
    get canRedo() {
      return future.length > 0
    },
    get undoDepth() {
      return past.length + (pending ? 1 : 0)
    },
    get redoDepth() {
      return future.length
    },

    set(next, transient = false) {
      if (same(next, present)) return
      if (transient) {
        present = next
        return
      }
      push(present)
      present = next
    },

    begin() {
      pending = { snapshot: present }
    },

    commit() {
      if (!pending) return
      if (!same(pending.snapshot, present)) push(pending.snapshot)
      pending = null
    },

    undo() {
      // 拖拽尚未提交时，先撤回到按下前的状态
      if (pending) {
        present = pending.snapshot
        pending = null
        return
      }
      const prev = past.pop()
      if (prev === undefined) return
      future.unshift(present)
      present = prev
    },

    redo() {
      const next = future.shift()
      if (next === undefined) return
      past.push(present)
      present = next
    },

    reset(value) {
      present = value
      past = []
      future = []
      pending = null
    },
  }
}
