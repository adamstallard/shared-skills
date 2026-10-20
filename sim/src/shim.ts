const store = new Map<string, unknown>()
export const atom = (ref: { plugin: string; key: string }, initial: unknown) => ({ ...ref, initial })
export const read = async (_$: unknown, a: { key: string; initial: unknown }) => (store.has(a.key) ? store.get(a.key) : a.initial)
export const update = async (_$: unknown, a: { key: string; initial: unknown }, f: (v: unknown) => unknown) => {
  store.set(a.key, f(store.has(a.key) ? store.get(a.key) : a.initial))
}
export const __store = store
