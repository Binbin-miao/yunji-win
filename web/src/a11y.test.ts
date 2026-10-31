import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const read = (rel: string) => readFileSync(new URL(rel, import.meta.url), 'utf8')
const css = read('./index.css')
const chartSource = read('./components/EqChart.tsx')

/**
 * 15 号工单的静态守卫：这些约定靠肉眼守不住，一改样式就容易悄悄退化。
 * - 字号必须用 rem，否则用户把系统字号调到 200% 时整站文字一动不动
 * - 必须有可见的键盘焦点环
 * - 画布必须能 Tab 到，并且给读屏软件一句能读懂的话
 */

describe('无障碍与缩放', () => {
  it('样式里不再出现 px 字号，系统字号放大才能生效', () => {
    const px = css.match(/font-size:\s*[\d.]+px/g) ?? []
    expect(px, `仍有 px 字号：${px.join(', ')}`).toEqual([])
  })

  it('有全局的键盘焦点环，且鼠标点击时不显示', () => {
    expect(css).toContain(':focus-visible')
    expect(css).toMatch(/outline:\s*2px solid var\(--glow\)/)
    expect(css).toContain(':focus:not(:focus-visible)')
  })

  it('放不下时允许换行，不靠裁切收场', () => {
    const clippers = css
      .split('}')
      .filter(rule => /overflow:\s*hidden/.test(rule) && !/visually-hidden/.test(rule))
    expect(clippers, `这些规则会把文字裁掉：${clippers.join(' | ')}`).toEqual([])
    expect(css).toContain('flex-wrap: wrap')
  })

  it('曲线画布能用键盘进入，并朗读当前曲线', () => {
    expect(chartSource).toMatch(/<canvas[\s\S]*?tabIndex=\{0\}/)
    expect(chartSource).toMatch(/aria-label=\{chartLabel\}/)
    expect(chartSource).toMatch(/aria-describedby="chart-help"/)
    expect(chartSource).toMatch(/className="visually-hidden"/)
  })
})
