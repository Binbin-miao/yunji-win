#!/usr/bin/env node
/**
 * 截图 / 抓 DOM 小工具。省掉每次手搓 Chrome 参数（相对路径、端口没起、虚拟时钟）。
 *
 *   node web/tools/shot.mjs                        # 首页截图 → mock/shot.png
 *   node web/tools/shot.mjs "?sim=1&page=tune"      # 带查询参数
 *   node web/tools/shot.mjs --out a.png --size 640x900 --dpr 2
 *   node web/tools/shot.mjs --dom "?sim=1&page=tune"   # 抓渲染后的 DOM 文本
 *
 * 自带预览服务：端口没监听就自己起 `vite preview`，用完杀掉。
 */
import { spawn } from 'node:child_process'
import { existsSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const WEB_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const PORT = Number(process.env.SHOT_PORT || 4175)
const BASE = `http://127.0.0.1:${PORT}/yunji-win/web/`

function parseArgs(argv) {
  const opts = {
    query: '',
    out: 'mock/shot.png',
    size: '1280x920',
    dpr: '1',
    dom: false,
    wait: 5000,
    ua: '',
  }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--out') opts.out = argv[++i]
    else if (a === '--size') opts.size = argv[++i]
    else if (a === '--dpr') opts.dpr = argv[++i]
    else if (a === '--wait') opts.wait = Number(argv[++i])
    else if (a === '--ua') opts.ua = argv[++i]
    else if (a === '--mobile') opts.ua = MOBILE_UA
    else if (a === '--dom') opts.dom = true
    else if (a === '--help' || a === '-h') opts.help = true
    else if (!a.startsWith('--')) opts.query = a
  }
  return opts
}

const MOBILE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'

const CHROME_CANDIDATES = [
  process.env.CHROME,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean)

function findChrome() {
  const hit = CHROME_CANDIDATES.find(p => existsSync(p))
  if (!hit) throw new Error('找不到 Chrome/Edge，请用环境变量 CHROME 指一个')
  return hit
}

async function reachable(url) {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(1500) })
    return r.ok
  } catch {
    return false
  }
}

async function ensureServer() {
  if (await reachable(BASE)) return null
  const child = spawn('npx', ['vite', 'preview', '--port', String(PORT), '--strictPort'], {
    cwd: WEB_DIR,
    shell: true,
    stdio: 'ignore',
  })
  for (let i = 0; i < 40; i++) {
    await new Promise(r => setTimeout(r, 250))
    if (await reachable(BASE)) return child
  }
  child.kill()
  throw new Error(`预览服务起不来（端口 ${PORT}）`)
}

function run(chrome, args) {
  return new Promise((res, rej) => {
    const p = spawn(chrome, args, { stdio: ['ignore', 'pipe', 'pipe'] })
    let out = ''
    p.stdout.on('data', d => (out += d))
    p.stderr.on('data', () => {})
    p.on('close', code => (code === 0 ? res(out) : rej(new Error(`chrome 退出码 ${code}`))))
  })
}

const opts = parseArgs(process.argv.slice(2))
const [w, h] = opts.size.split('x').map(Number)

// Chromium 无头窗口有约 500px 的最小宽度：更窄的 --window-size 会被按 500 排版，
// 再裁到请求的宽度，看起来像「右边被切掉」，其实是假象。窄屏请用真机验证。
if (w < 500) {
  console.warn(`警告: 请求宽度 ${w}px 低于无头窗口最小宽度（约 500px），排版会按 500px 计算再裁切；窄屏请用 --size 500x… 或真机。`)
}

if (opts.help) {
  console.log(
    [
      '用法: node web/tools/shot.mjs [查询串] [--out 文件] [--size 1280x920] [--dpr 1] [--dom] [--wait ms] [--ua 串] [--mobile]',
      '示例: node web/tools/shot.mjs "?sim=1&page=tune" --out mock/tune.png --size 640x900',
      '手机:  --mobile 走 iPhone UA，配合 --size 390x844',
      '说明: 输出路径按仓库根解析成绝对路径（Chrome 不认相对路径）；端口没起会自动起预览服务。',
    ].join('\n'),
  )
  process.exit(0)
}

const chrome = findChrome()
const server = await ensureServer()
const url = BASE + (opts.query.startsWith('?') ? opts.query : opts.query ? `?${opts.query}` : '')
const outPath = resolve(process.cwd(), opts.out)

const common = [
  '--headless=new',
  '--disable-gpu',
  '--hide-scrollbars',
  `--window-size=${w},${h}`,
  `--force-device-scale-factor=${opts.dpr}`,
]
if (opts.ua) common.push(`--user-agent=${opts.ua}`)

try {
  if (opts.dom) {
    // 也要给虚拟时钟，否则 dump 发生在 React 首次渲染之前，抓到的是空壳
    const html = await run(chrome, [...common, `--virtual-time-budget=${opts.wait}`, '--dump-dom', url])
    process.stdout.write(html)
  } else {
    mkdirSync(dirname(outPath), { recursive: true })
    await run(chrome, [...common, `--virtual-time-budget=${opts.wait}`, `--screenshot=${outPath}`, url])
    console.log(outPath)
  }
} finally {
  if (server) server.kill()
}
