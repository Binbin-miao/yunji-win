import { describe, expect, it } from 'vitest'
import type { EqBand } from './eq'
import {
  MAX_BANDS,
  MAX_GAIN,
  addBand,
  bandAtPoint,
  clampBand,
  dbAtY,
  dragBand,
  freqAtX,
  hitBand,
  nudgeBand,
  removeBand,
  scrollQ,
  snapGain,
  xAtFreq,
  yAtDb,
  type Layout,
} from './eqEdit'

const layout: Layout = { width: 600, height: 300, range: 12 }
const band = (freq: number, q: number, gain: number): EqBand => ({ freq, q, gain })

describe('坐标换算', () => {
  it('频率与像素可互相反解', () => {
    for (const f of [20, 100, 1000, 20000]) {
      expect(freqAtX(xAtFreq(f, layout), layout)).toBeCloseTo(f, 3)
    }
  })

  it('dB 与像素可互相反解', () => {
    for (const db of [-12, -3, 0, 6, 12]) {
      expect(dbAtY(yAtDb(db, layout), layout)).toBeCloseTo(db, 6)
    }
  })
})

describe('钳制与吸附', () => {
  it('增益靠近 0 时吸附为 0', () => {
    expect(snapGain(0.1)).toBe(0)
    expect(snapGain(-0.14)).toBe(0)
    expect(snapGain(0.2)).toBe(0.2)
  })

  it('频率、增益、Q 都被夹进合法区间，且精度固定', () => {
    const b = clampBand(band(999999, 99, 99))
    expect(b.freq).toBe(20000)
    expect(b.q).toBe(10)
    expect(b.gain).toBe(MAX_GAIN)

    const c = clampBand(band(1, 0, -99))
    expect(c.freq).toBe(20)
    expect(c.q).toBe(0.1)

    const d = clampBand(band(1000.7, 1.234, 2.46))
    expect(d.freq).toBe(1001)
    expect(d.q).toBe(1.23)
    expect(d.gain).toBe(2.5)
  })
})

describe('拖拽', () => {
  const start = band(1000, 1, 0)
  const sx = xAtFreq(start.freq, layout)
  const sy = yAtDb(start.gain, layout)

  it('向右拖动提高频率、向上拖动提高增益', () => {
    const moved = dragBand(start, layout, sx, sy, sx + 60, sy - 30, null)
    expect(moved.freq).toBeGreaterThan(start.freq)
    expect(moved.gain).toBeGreaterThan(0)
  })

  it('锁定频率时只有增益变化', () => {
    const moved = dragBand(start, layout, sx, sy, sx + 60, sy - 30, 'freq')
    expect(moved.freq).toBe(start.freq)
    expect(moved.gain).toBeGreaterThan(0)
  })

  it('锁定增益时只有频率变化', () => {
    const moved = dragBand(start, layout, sx, sy, sx + 60, sy - 30, 'gain')
    expect(moved.gain).toBe(start.gain)
    expect(moved.freq).toBeGreaterThan(start.freq)
  })

  it('拖出边界时被夹住而不是跑飞', () => {
    const moved = dragBand(start, layout, sx, sy, sx + 9999, sy - 9999, null)
    expect(moved.freq).toBeLessThanOrEqual(20000)
    expect(moved.gain).toBeLessThanOrEqual(MAX_GAIN)
  })

  it('回到起点位移为 0 时参数不变（无漂移）', () => {
    const moved = dragBand(start, layout, sx, sy, sx, sy, null)
    expect(moved.freq).toBe(start.freq)
    expect(moved.gain).toBe(start.gain)
  })
})

describe('命中检测', () => {
  const bands = [band(100, 1, 0), band(1000, 1, 6), band(8000, 1, -3)]

  it('点在锚点上能选中对应段', () => {
    expect(hitBand(bands, layout, xAtFreq(1000, layout), yAtDb(6, layout))).toBe(1)
    expect(hitBand(bands, layout, xAtFreq(8000, layout), yAtDb(-3, layout))).toBe(2)
  })

  it('点在空白处返回 -1', () => {
    expect(hitBand(bands, layout, xAtFreq(3000, layout), yAtDb(10, layout))).toBe(-1)
  })
})

describe('增删与键盘', () => {
  it('点空白生成的段落在合法范围内', () => {
    const b = bandAtPoint(layout, 400, 100)
    expect(b.freq).toBeGreaterThanOrEqual(20)
    expect(b.freq).toBeLessThanOrEqual(20000)
    expect(b.q).toBe(0.75)
  })

  it('加满 8 段后被拒绝', () => {
    const full = Array.from({ length: MAX_BANDS }, (_, i) => band(100 * (i + 1), 1, 0))
    expect(addBand(full, band(50, 1, 0))).toHaveLength(MAX_BANDS)
  })

  it('新增后按频率排序', () => {
    const list = addBand([band(1000, 1, 0), band(8000, 1, 0)], band(500, 0.75, 0))
    expect(list.map(b => b.freq)).toEqual([500, 1000, 8000])
  })

  it('删除按索引生效，越界不报错', () => {
    const list = [band(100, 1, 0), band(1000, 1, 0)]
    expect(removeBand(list, 0).map(b => b.freq)).toEqual([1000])
    expect(removeBand(list, 9)).toHaveLength(2)
  })

  it('方向键微调：细调 0.1 dB，Shift 粗调 1 dB', () => {
    expect(nudgeBand(band(1000, 1, 0), 'ArrowUp', false).gain).toBe(0.1)
    expect(nudgeBand(band(1000, 1, 0), 'ArrowUp', true).gain).toBe(1)
    expect(nudgeBand(band(1000, 1, 5), 'ArrowDown', false).gain).toBe(4.9)
  })

  it('方向键调频率，Shift 步进更大', () => {
    const fine = nudgeBand(band(1000, 1, 0), 'ArrowRight', false).freq
    const coarse = nudgeBand(band(1000, 1, 0), 'ArrowRight', true).freq
    expect(fine).toBeGreaterThan(1000)
    expect(coarse).toBeGreaterThan(fine)
  })

  it('滚轮调 Q，向上一格增大', () => {
    expect(scrollQ(band(1000, 1, 0), -100, false).q).toBeCloseTo(1.05, 2)
    expect(scrollQ(band(1000, 1, 0), 100, false).q).toBeCloseTo(0.95, 2)
    expect(scrollQ(band(1000, 1, 0), -100, true).q).toBeCloseTo(1.5, 2)
  })

  it('Q 被夹在 0.1–10', () => {
    expect(scrollQ(band(1000, 0.1, 0), 100, true).q).toBe(0.1)
    expect(scrollQ(band(1000, 9.9, 0), -100, true).q).toBe(10)
  })
})
