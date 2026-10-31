import { describe, expect, it } from 'vitest'
import { DAC_VOL, balDisplay, micDisplay, volBounds, volDisplay, volRaw } from './params'

describe('音量换算', () => {
  it('cb5100 原始 0 显示为 60（最大档，不是静音）', () => {
    expect(volDisplay(0, 'cb5100')).toBe(60)
    expect(volDisplay(-60, 'cb5100')).toBe(0)
  })

  it('cb5100 显示值可反算回原始值', () => {
    for (const display of [0, 12, 30, 48, 60]) {
      expect(volDisplay(volRaw(display, 'cb5100'), 'cb5100')).toBe(display)
    }
  })

  it('cb1200 的滑杆区间是 −8..4，负档不能被钳成 0', () => {
    expect(volBounds('cb1200')).toEqual({ min: -8, max: 4 })
    expect(volRaw(-5, 'cb1200')).toBe(-5)
    expect(volDisplay(-5, 'cb1200')).toBe(-5)
  })

  it('越界值被夹到芯片量程', () => {
    expect(volRaw(99, 'cb5100')).toBe(DAC_VOL.cb5100.max)
    expect(volRaw(-99, 'cb5100')).toBe(DAC_VOL.cb5100.min)
    expect(volRaw(99, 'cb1200')).toBe(4)
    expect(volRaw(-99, 'cb1200')).toBe(-8)
  })
})

describe('其他参数显示', () => {
  it('麦克风显示原始值，正值带 + 号', () => {
    expect(micDisplay(18)).toBe('+18')
    expect(micDisplay(-6)).toBe('-6')
    expect(micDisplay(0)).toBe('0')
  })

  it('平衡显示左右与居中', () => {
    expect(balDisplay(0)).toBe('居中')
    expect(balDisplay(3)).toBe('右 3')
    expect(balDisplay(-2)).toBe('左 2')
  })
})
