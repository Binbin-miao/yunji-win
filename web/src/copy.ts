/**
 * 全站文案表：唯一来源，组件不得内联硬编码说明文字。
 *
 * 约定：
 * - 每个可交互控件的说明（hint）不超过 18 个字，常驻在控件旁或作为 title
 * - 同一概念全站只有一种说法
 * - 由 copy.test.ts 表驱动校验，新增控件漏写文案会直接测试失败
 */

export const COPY = {
  appName: '云姬 · 网页版调音台',
  tagline: '浏览器直连 USB 设备，免安装',

  // ---------- 连接 ----------
  connectReal: '连接真机',
  connectSim: '试用模拟器',
  disconnect: '断开',
  reread: '重新读取',
  reading: '正在读取设备状态…',

  hintReal: '浏览器弹窗选设备，需授权访问',
  hintSim: '不插设备也能试全部功能',
  noHid: '当前浏览器不支持 WebHID，真机连接不可用；请改用 Chrome 或 Edge 113+ 桌面版。',
  mobile: '手机浏览器无法连接 USB 设备，请用电脑上的 Chrome / Edge 打开。',
  mobileTitle: '请用电脑打开',
  mobileWhy: '网页版靠 WebHID 直连 USB，手机浏览器没有这个能力，插转接头也不行。',
  simBanner: '模拟器模式：这里改动的是模拟数据，不会写入任何设备。',
  deviceGone: '设备已断开：请重新插拔后再次连接。',

  // ---------- 区块标题 ----------
  sectionModels: '支持的机型',
  sectionModelsHint: '旋润系列走厂商控制传输，浏览器通道暂不支持',
  sectionState: '设备设置',
  sectionStateHint: '拖动或点选后自动写入设备',
  supported: '浏览器可直连',
  unsupported: '请用桌面版',

  // ---------- 参数 ----------
  param: {
    firmware: { label: '固件版本', hint: '设备当前固件，与官方 App 一致' },
    volume: { label: '音量', hint: '满量程随芯片不同，数值越大越响' },
    mic: { label: '麦克风', hint: '回放音量 −30…+30' },
    filter: { label: '滤波器', hint: '数字滤波器的滚降与相位模式' },
    gain: { label: '增益', hint: '输出增益档位，高档更响也更易失真' },
    led: { label: '指示灯', hint: '当前固件无法通过浏览器控制' },
    balance: { label: '声道平衡', hint: '负值偏左、正值偏右' },
  },

  filterModes: ['低延迟陡降', '相位补偿陡降', '低延迟缓降', '相位补偿缓降', '无过采样'],
  gainLevels: ['低增益', '高增益'],

  // ---------- 控件（label + hint） ----------
  controls: {
    undo: { label: '撤销', hint: '回退上一步曲线改动' },
    redo: { label: '重做', hint: '重做刚撤销的改动' },
    import: { label: '导入', hint: '粘贴或拖入社区配置' },
    writeEq: { label: '写入设备', hint: '把当前 8 段写入硬件' },
    writeEqDone: { label: '写入中…', hint: '正在写设备，会短暂断音' },
    rangeToggle: { label: '纵轴范围', hint: '细调时换成 ±6 dB 更清楚' },
    delBand: { label: '删除这一段', hint: '删掉选中的频段' },
    targetNone: { label: '不叠加', hint: '只看自己的曲线' },
    targetPick: { label: '目标曲线', hint: '叠一条参考线看差多少' },
    fit: { label: '拟合成 8 段', hint: '超 8 段时压缩成设备上限' },
    fitting: { label: '拟合中…', hint: '正在算，稍等一下' },
    fitApply: { label: '应用拟合结果', hint: '确认用拟合后的参数' },
    fitCancel: { label: '放弃拟合', hint: '不改变当前曲线' },
    importApply: { label: '应用到曲线', hint: '把解析结果填进曲线' },
    importFile: { label: '选择文件', hint: '从本地读一份配置' },
    savePreset: { label: '保存当前曲线', hint: '存成可切换的预设' },
    exportAll: { label: '导出全部', hint: '备份成 JSON 文件' },
    importJson: { label: '导入 JSON', hint: '从备份文件恢复预设' },
    presetApply: { label: '应用', hint: '把这条预设载入曲线' },
    presetRename: { label: '改名', hint: '给预设换个名字' },
    presetCopy: { label: '复制', hint: '留一份再改' },
    presetDelete: { label: '删除', hint: '删掉这条预设' },
    confirmWrite: { label: '确认写入', hint: '确认覆盖设备现有 EQ' },
    cancel: { label: '取消', hint: '什么都不做' },
    goConnect: { label: '去连接', hint: '去连接页连设备' },
  },

  // ---------- 曲线区 ----------
  eqSimHint: '模拟器示例曲线，改完不会写入任何设备',
  eqLocalHint: '曲线改动先留在本地，点「写入设备」才进硬件',

  // ---------- 操作提示 ----------
  ops: {
    eq: '拖动锚点改频率与增益 · Ctrl 拖动锁单轴 · 滚轮调 Q · 点空白加段 · 双击归零 · 右键删除 · 方向键微调 · Ctrl+Z 撤销',
    limit: '最多 {n} 段',
    full: '已满 {n} 段，删掉一段才能再加',
    hide: '隐藏提示',
    show: '显示操作提示',
  },
} as const

export type ControlId = keyof typeof COPY.controls
