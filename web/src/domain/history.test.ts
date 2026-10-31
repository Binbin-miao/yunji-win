import { describe, expect, it } from 'vitest'
import { HISTORY_LIMIT, createHistory } from './history'

type Band = { freq: number; gain: number }
const b = (freq: number, gain = 0): Band => ({ freq, gain })

describe('历史栈', () => {
  it('普通变更可撤销与重做', () => {
    const h = createHistory<Band[]>([b(100)])
    h.set([b(200)])
    expect(h.present[0].freq).toBe(200)
    expect(h.canUndo).toBe(true)

    h.undo()
    expect(h.present[0].freq).toBe(100)
    expect(h.canRedo).toBe(true)

    h.redo()
    expect(h.present[0].freq).toBe(200)
  })

  it('无变化时不入栈', () => {
    const h = createHistory<Band[]>([b(100)])
    h.set([b(100)])
    expect(h.canUndo).toBe(false)
  })

  it('拖拽：多次 transient 只产生一步', () => {
    const h = createHistory<Band[]>([b(100)])
    h.begin()
    for (const f of [110, 130, 160, 180]) h.set([b(f)], true)
    h.commit()

    expect(h.present[0].freq).toBe(180)
    h.undo()
    expect(h.present[0].freq).toBe(100)
    expect(h.canUndo).toBe(false)
  })

  it('拖拽回到原点时不产生历史', () => {
    const h = createHistory<Band[]>([b(100)])
    h.begin()
    h.set([b(150)], true)
    h.set([b(100)], true)
    h.commit()
    expect(h.canUndo).toBe(false)
  })

  it('拖拽未提交时 undo 回到按下前', () => {
    const h = createHistory<Band[]>([b(100)])
    h.begin()
    h.set([b(300)], true)
    h.undo()
    expect(h.present[0].freq).toBe(100)
    expect(h.canUndo).toBe(false)
  })

  it('新操作会清空重做栈', () => {
    const h = createHistory<Band[]>([b(100)])
    h.set([b(200)])
    h.undo()
    expect(h.canRedo).toBe(true)
    h.set([b(300)])
    expect(h.canRedo).toBe(false)
  })

  it('历史深度有上限', () => {
    const h = createHistory<Band[]>([b(0)])
    for (let i = 1; i <= HISTORY_LIMIT + 10; i++) h.set([b(i)])
    let steps = 0
    while (h.canUndo) {
      h.undo()
      steps++
    }
    expect(steps).toBe(HISTORY_LIMIT)
  })

  it('reset 清空全部历史', () => {
    const h = createHistory<Band[]>([b(100)])
    h.set([b(200)])
    h.reset([b(500)])
    expect(h.present[0].freq).toBe(500)
    expect(h.canUndo).toBe(false)
    expect(h.canRedo).toBe(false)
  })
})
