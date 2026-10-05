// One usage window as the engine reports it (SessionRateLimit's fields).
export type UsageLimit = { kind: string; percentUsed: number; resetsAt?: string }

declare module 'claude-code' {
  interface PluginState {
    'usage-hint': { limits: UsageLimit[] }
  }
}
