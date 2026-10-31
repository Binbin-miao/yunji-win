import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createDebouncer } from './commit'

describe('提交策略', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('连续改动只提交最后一次', async () => {
    const commit = vi.fn().mockResolvedValue(undefined)
    const d = createDebouncer<number>(commit, 400)

    d.schedule(1)
    d.schedule(2)
    d.schedule(3)

    expect(commit).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(400)
    expect(commit).toHaveBeenCalledTimes(1)
    expect(commit).toHaveBeenCalledWith(3)
  })

  it('拖动期间（未到延时）不提交', async () => {
    const commit = vi.fn().mockResolvedValue(undefined)
    const d = createDebouncer<number>(commit, 400)

    d.schedule(1)
    await vi.advanceTimersByTimeAsync(300)
    d.schedule(2)
    await vi.advanceTimersByTimeAsync(300)

    expect(commit).not.toHaveBeenCalled()
  })

  it('同值重复调度只提交一次（松手后又触发一次的场景）', async () => {
    const commit = vi.fn().mockResolvedValue(undefined)
    const d = createDebouncer<number>(commit, 400)

    d.schedule(5)
    d.schedule(5)
    await vi.advanceTimersByTimeAsync(400)

    expect(commit).toHaveBeenCalledTimes(1)
  })

  it('cancel 丢弃待提交的值', async () => {
    const commit = vi.fn().mockResolvedValue(undefined)
    const d = createDebouncer<number>(commit, 400)

    d.schedule(9)
    d.cancel()
    await vi.advanceTimersByTimeAsync(1000)

    expect(commit).not.toHaveBeenCalled()
  })

  it('提交抛错不会让后续调度失效', async () => {
    const commit = vi.fn().mockRejectedValueOnce(new Error('boom')).mockResolvedValue(undefined)
    const d = createDebouncer<number>(commit, 400)

    d.schedule(1)
    await vi.advanceTimersByTimeAsync(400)
    d.schedule(2)
    await vi.advanceTimersByTimeAsync(400)

    expect(commit).toHaveBeenCalledTimes(2)
    expect(commit).toHaveBeenLastCalledWith(2)
  })
})
