// Store de tags partagés — filtres transverses (modèle, jeu, pari, niveau).
// Une sélection ici filtre toutes les vues qui consomment le store.
import { atom } from 'nanostores'

export interface TagState {
  models: string[]   // ex: ['hot_frequency_v1', 'bayesian_v1']
  games: string[]    // ex: ['Digital Reveil 7h']
  bets: string[]     // ex: ['2N', 'TURBO_5']
  levels: string[]   // ex: ['walk_forward', 'out_of_sample', 'prospective']
}

export const tags = atom<TagState>({ models: [], games: [], bets: [], levels: [] })

export function toggleTag(kind: keyof TagState, value: string) {
  const cur = { ...tags.get() }
  const list = cur[kind] as string[]
  cur[kind] = list.includes(value) ? list.filter(v => v !== value) : [...list, value]
  tags.set(cur)
}

export function clearTags(kind?: keyof TagState) {
  if (!kind) { tags.set({ models: [], games: [], bets: [], levels: [] }); return }
  const cur = { ...tags.get() }
  cur[kind] = []
  tags.set(cur)
}

export function hasTags(): boolean {
  const t = tags.get()
  return t.models.length > 0 || t.games.length > 0 || t.bets.length > 0 || t.levels.length > 0
}

export function activeCount(): number {
  const t = tags.get()
  return t.models.length + t.games.length + t.bets.length + t.levels.length
}

// helpers d'interrogation pour les vues
export function matchesModel(m: string): boolean {
  const t = tags.get()
  return t.models.length === 0 || t.models.includes(m)
}
export function matchesGame(g: string): boolean {
  const t = tags.get()
  return t.games.length === 0 || t.games.includes(g)
}
export function matchesBet(b: string): boolean {
  const t = tags.get()
  return t.bets.length === 0 || t.bets.includes(b)
}
