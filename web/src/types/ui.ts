/** 界面层共用类型 */

export type WriteStatus = { kind: 'idle' | 'writing' | 'done' | 'warn' | 'error'; text?: string }
export type SliderKey = 'volume' | 'mic' | 'balance'
export type ParamKey = SliderKey | 'filter' | 'gain' | 'led'
export type PageKey = 'connect' | 'tune' | 'presets' | 'about'
