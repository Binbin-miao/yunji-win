/**
 * 提交策略：拖动中只改本地，停顿 delay 毫秒后提交一次；连续改动只保留最后一次。
 * 抽成独立对象，UI 与传输层都不需要自己管定时器。
 */

export interface Debouncer<T> {
  schedule(value: T): void
  /** 丢弃待提交的值 */
  cancel(): void
}

export function createDebouncer<T>(
  commit: (value: T) => Promise<void>,
  delay = 400,
  isEqual: (a: T, b: T) => boolean = Object.is,
): Debouncer<T> {
  let pending: { value: T } | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  const clear = () => {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  const fire = () => {
    clear()
    if (!pending) return
    const { value } = pending
    pending = null
    void commit(value)
  }

  return {
    schedule(value: T) {
      // 同值重复提交没有意义（例如松手后又触发一次）
      if (pending && isEqual(pending.value, value)) return
      pending = { value }
      clear()
      timer = setTimeout(fire, delay)
    },

    cancel() {
      clear()
      pending = null
    },
  }
}
