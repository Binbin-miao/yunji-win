/** 传输层错误：带上失败阶段，便于给出不同提示 */
export type Stage = 'connect' | 'write' | 'verify' | 'read'

export class TransportError extends Error {
  readonly stage: Stage

  constructor(message: string, stage: Stage) {
    super(message)
    this.name = 'TransportError'
    this.stage = stage
  }
}

export const STAGE_TEXT: Record<Stage, string> = {
  connect: '连接失败',
  write: '写入被设备拒绝',
  verify: '写入后回读不一致',
  read: '读取失败',
}
