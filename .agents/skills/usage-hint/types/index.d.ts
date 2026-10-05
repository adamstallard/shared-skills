// What the hint line shows, or null to leave it as the engine draws it.
export type UsageTail = string | null

declare module 'claude-code' {
  interface PluginState {
    'usage-hint': { tail: UsageTail }
  }
}
