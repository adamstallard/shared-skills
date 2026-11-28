// The initial value of each of the mod's `$.state` values, each declared in
// types/index.d.ts. `claude plugin validate` reads a state reference only
// from a const of the file that uses it, so each file declares its own atoms, with these
// initial values.
import type {
  Answer,
  Declining,
  Judged,
  Judging,
  PlacedRow,
  Previewed,
  Revision,
  Seen,
  ServiceState,
  Turn,
} from '../types'
import type { PendingView, QuestionView } from './core-protocol'

export const INITIAL = {
  marker: false,
  service: { status: 'none' } as ServiceState,
  questions: {} as Record<string, QuestionView>,
  order: [] as string[],
  cursor: 0,
  answers: {} as Record<string, Answer>,
  prompt: '',
  flash: null as string | null,
  talking: null as string | null,
  talks: {} as Record<string, Turn[]>,
  thinking: {} as Record<string, 'reply' | 'rephrase' | 'draft'>,
  rephrased: {} as Record<string, Revision>,
  original: {} as Record<string, boolean>,
  awaiting: [] as { id: string; text: string }[],
  replyTurns: {} as Record<string, string>,
  editing: {} as Record<string, true>,
  asking: {} as Record<string, true>,
  declining: null as Declining | null,
  seen: {} as Record<string, Seen>,
  viewing: null as { id: string; page: number } | null,
  rows: {} as Record<string, PlacedRow>,
  posting: {} as Record<string, true>,
  marked: {} as Record<string, true>,
  previewed: null as Previewed | null,
  confirm: null as (Previewed & { asked: string }) | null,
  arrived: null as string | null,
  places: {} as Record<string, string>,
  picking: false,
  knownPlaces: [] as string[],
  pending: [] as PendingView[],
  judging: null as Judging | null,
  judged: { last: null, ends: 0 } as Judged,
  turn: null as string | null,
  relays: {} as Record<string, string>,
  rateLimitedUntil: null as string | null,
}

/** A record without one key. */
export function without<T>(record: Record<string, T>, id: string): Record<string, T> {
  const { [id]: _gone, ...rest } = record
  return rest
}
