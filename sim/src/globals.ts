;(globalThis as any).h = (tag: any, props: any, ...children: any[]) => {
  const p = { ...(props ?? {}), children: children.flat(Infinity) }
  if (typeof tag === 'function') return tag(p)
  return { type: tag, props: p }
}
;(globalThis as any).Fragment = (p: any) => ({ type: 'Box', props: { flexDirection: 'column', ...p } })
