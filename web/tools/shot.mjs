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
  const opts = { query: '', out: 'mock/shot.png', size: '1280x920', dpr: '1', dom: false, wait: 5000 }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--out') opts.out = argv[++i]
    else if (a === '--size') opts.size = argv[++i]
    else if (a === '--dpr') opts.dpr = argv[++i]
    else if (a === '--wait') opts.wait = Number(argv[++i])
    else if (a === '--dom') opts.dom = true
    else if (a === '--help' || a === '-h') opts.help = true
    else if (!a.startsWith('--')) opts.query = a
  }
  return opts
}

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

if (opts.help) {
  console.log(
    [
      '用法: node web/tools/shot.mjs [查询串] [--out 文件] [--size 1280x920] [--dpr 1] [--dom] [--wait ms]',
      '示例: node web/tools/shot.mjs "?sim=1&page=tune" --out mock/tune.png --size 640x900',
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
