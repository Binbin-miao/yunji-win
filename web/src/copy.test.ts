import { describe, expect, it } from 'vitest'
import { COPY } from './copy'

/** hint 的长度上限（中文字符按 1 个算） */
const MAX_HINT = 18

describe('文案表', () => {
  it('每个参数的说明都不为空且不超过 18 字', () => {
    for (const [key, value] of Object.entries(COPY.param)) {
      expect(value.label.length, `${key} 的 label 为空`).toBeGreaterThan(0)
      expect(value.hint.length, `${key} 的 hint 为空`).toBeGreaterThan(0)
      expect(value.hint.length, `${key} 的 hint 太长：${value.hint}`).toBeLessThanOrEqual(MAX_HINT)
    }
  })

  it('每个控件的说明都不为空且不超过 18 字', () => {
    for (const [key, value] of Object.entries(COPY.controls)) {
      expect(value.label.length, `${key} 的 label 为空`).toBeGreaterThan(0)
      expect(value.hint.length, `${key} 的 hint 为空`).toBeGreaterThan(0)
      expect(value.hint.length, `${key} 的 hint 太长：${value.hint}`).toBeLessThanOrEqual(MAX_HINT)
    }
  })

  it('工具条与横幅文案都不为空', () => {
    for (const [key, value] of Object.entries(COPY)) {
      if (typeof value !== 'string') continue
      expect(value.trim().length, `${key} 为空`).toBeGreaterThan(0)
    }
  })

  it('滤波器与增益档位数量固定，不会与设备编号错位', () => {
    expect(COPY.filters).toHaveLength(5)
    expect(COPY.gainLevels).toHaveLength(2)
  })

  it('每个滤波模式的适配说明都不为空且不超过 18 字', () => {
    for (const f of COPY.filters) {
      expect(f.name.length).toBeGreaterThan(0)
      expect(f.fit.length, `${f.name} 的适合说明为空`).toBeGreaterThan(0)
      expect(f.fit.length, `${f.name} 的适合说明太长：${f.fit}`).toBeLessThanOrEqual(18)
      expect(f.cost.length, `${f.name} 的代价说明太长：${f.cost}`).toBeLessThanOrEqual(18)
    }
  })

  it('滤波模式卡片带免责说明，避免被当成实测数据', () => {
    expect(COPY.filterNote).toContain('示意')
    expect(COPY.filterNote).toContain('经验')
  })

  it('同一概念只有一种说法：控件标签不重复', () => {
    const labels = Object.values(COPY.controls).map(c => c.label)
    const dup = labels.filter((l, i) => labels.indexOf(l) !== i)
    expect(dup, `重复的控件标签：${dup.join(', ')}`).toEqual([])
  })

  it('操作提示包含关键手势，避免改文案时漏掉核心操作', () => {
    for (const word of ['拖动', 'Ctrl', '滚轮', '删除', '撤销']) {
      expect(COPY.ops.eq).toContain(word)
    }
  })

  it('带占位符的文案必须留出 {n}，否则界面会出现空值', () => {
    for (const raw of [COPY.ops.limit, COPY.ops.full]) {
      expect(raw).toContain('{n}')
      expect(raw.replace('{n}', '8')).not.toContain('{n}')
    }
  })

  it('曲线区两条说明互不相同，且都提到是否会写入设备', () => {
    expect(COPY.eqSimHint).not.toBe(COPY.eqLocalHint)
    expect(COPY.eqSimHint).toContain('不会写入')
    expect(COPY.eqLocalHint).toContain('写入设备')
  })
})
