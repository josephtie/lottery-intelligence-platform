<template>
  <div class="panel">
    <h3>🧠 Profils des jeux — Temporal Intelligence</h3>
    <div class="sub" style="margin-bottom:10px">
      Couche d'observation : chaque modèle est rejoué en walk-forward strict
      (jamais de donnée future) puis agrégé par semaine ISO et jour de semaine.
      C'est un profil historique — pas une prédiction, pas un sélecteur.
      Nul de référence : attendu hypergéométrique exact
      (≥1 ≈ {{ data?.null_reference?.expected_ge1_pct }} %,
      moyenne ≈ {{ data?.null_reference?.expected_mean_hits }} hits).
    </div>
    <div class="filters">
      <select v-model="drawType" @change="load">
        <option v-for="t in types" :key="t.code + t.display_name" :value="t.display_name">
          {{ t.display_name }} ({{ t.settled_draws }} tirages)</option>
      </select>
      <select v-model="model" v-if="data?.models">
        <option v-for="(_, m) in data.models" :key="m" :value="m">{{ m }}</option>
      </select>
      <span v-if="loading" class="badge-warn">replay walk-forward en cours (~15 s)…</span>
    </div>
    <div v-if="error" class="badge-err">{{ error }}</div>
    <template v-else-if="data">
      <div v-if="data.error" class="badge-warn">{{ data.error }}</div>
      <template v-else>
        <div class="sub" style="margin-bottom:8px">
          {{ data.game }} · {{ data.n_draws }} tirages · {{ data.n_replayed }} rejoués
          · seuils : &lt;{{ data.thresholds.preliminary }} insuffisant,
          &lt;{{ data.thresholds.adequate }} préliminaire
        </div>

        <h4>Profil actuel — classement historique (descriptif)</h4>
        <table class="data mb0">
          <tr><th>Modèle</th><th>n</th><th>Moy.hits</th><th>≥1</th><th>≥2</th><th>≥3</th>
              <th>Streak</th><th>Consistance</th><th>Tendance</th>
              <th>vs nul (lift / p)</th><th>vs null pairé (Δ / p)</th><th>Échantillon</th></tr>
          <tr v-for="m in ranked" :key="m.name"
              :class="{ 'baseline-row': m.name === 'null_model_benchmark' }">
            <td class="mono">{{ m.name }}</td>
            <td class="mono">{{ m.n }}</td>
            <td class="mono">{{ m.mean_hits ?? '—' }}</td>
            <td class="mono">{{ pct(m.ge1_pct) }}</td>
            <td class="mono">{{ pct(m.ge2_pct) }}</td>
            <td class="mono">{{ pct(m.ge3_pct) }}</td>
            <td class="mono">{{ m.best_ge1_streak ?? '—' }}</td>
            <td class="mono" :title="'CV hebdo ' + (m.consistency?.cv_weekly ?? '—')">
              {{ m.consistency?.consistency_index ?? '—' }}
              <span class="badge" :class="stabClass(m.consistency?.stability)">{{ stabLabel(m.consistency?.stability) }}</span>
            </td>
            <td class="mono">{{ trendLabel(m.trend) }}</td>
            <td class="mono">{{ vsNull(m.vs_null) }}</td>
            <td class="mono">{{ paired(m.paired_vs_null) }}</td>
            <td class="mono"><span class="badge" :class="sampleClass(m.sample_level)">{{ sampleLabel(m.sample_level) }}</span></td>
          </tr>
        </table>

        <template v-if="current">
          <h4 style="margin-top:16px">Évolution hebdomadaire — <span class="mono">{{ model }}</span></h4>
          <div class="scrollbox">
            <table class="data mb0">
              <tr><th>Semaine</th><th>n</th><th>Moy.hits</th><th>≥1</th><th>≥2</th><th>≥3</th><th></th></tr>
              <tr v-for="w in current.weekly" :key="w.iso_week">
                <td class="mono">{{ w.iso_week }}</td>
                <td class="mono">{{ w.n }}</td>
                <td class="mono">{{ w.mean_hits }}</td>
                <td class="mono">{{ pct(w.ge1_pct) }}</td>
                <td class="mono">{{ pct(w.ge2_pct) }}</td>
                <td class="mono">{{ pct(w.ge3_pct) }}</td>
                <td><span class="wbar" :style="{ width: barWidth(w.mean_hits) }"></span></td>
              </tr>
            </table>
          </div>

          <h4 style="margin-top:16px">Jour de semaine — <span class="mono">{{ model }}</span>
            <span class="sub"> (lundi vs lundis, mardi vs mardis…)</span></h4>
          <table class="data mb0">
            <tr><th>Jour</th><th>n</th><th>Moy.hits</th><th>≥1</th><th>≥2</th><th>≥3</th><th>Échantillon</th></tr>
            <tr v-for="d in current.weekday" :key="d.weekday">
              <td>{{ weekdayName(d.weekday) }}</td>
              <td class="mono">{{ d.n }}</td>
              <td class="mono">{{ d.mean_hits }}</td>
              <td class="mono">{{ pct(d.ge1_pct) }}</td>
              <td class="mono">{{ pct(d.ge2_pct) }}</td>
              <td class="mono">{{ pct(d.ge3_pct) }}</td>
              <td class="mono"><span class="badge" :class="sampleClass(d.sample_level)">{{ sampleLabel(d.sample_level) }}</span></td>
            </tr>
          </table>
        </template>

        <h4 style="margin-top:16px">Alertes analytiques (descriptives)</h4>
        <ul class="sub" v-if="alerts.length">
          <li v-for="a in alerts" :key="a">{{ a }}</li>
        </ul>
        <div v-else class="sub">Aucun changement de régime détecté · aucune dégradation
          signalée · aucun échantillon insuffisant à signaler.</div>
      </template>
    </template>

    <h4 style="margin-top:20px">Matrice Jeu × Modèle — prédictions scellées prospectives</h4>
    <div class="sub">Source : outcomes prospectifs réels uniquement
      ({{ matrix?.as_of }}). Les cellules éparses sont étiquetées, pas inventées.</div>
    <div class="scrollbox" v-if="matrix">
      <table class="data mb0">
        <tr><th>Jeu</th><th v-for="m in matrixModels" :key="m" class="mono" style="font-size:10px">{{ m }}</th></tr>
        <tr v-for="g in matrixGames" :key="g">
          <td>{{ g }}</td>
          <td v-for="m in matrixModels" :key="m" class="mono cell">
            <span v-if="cell(g, m)" :title="'n=' + cell(g, m).n">
              {{ cell(g, m).mean_hits ?? '—' }}<br/>
              <span class="badge" :class="sampleClass(cell(g, m).sample_level)" style="font-size:9px">
                n={{ cell(g, m).n }}</span>
            </span>
            <span v-else class="sub">—</span>
          </td>
        </tr>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const types = ref<any[]>([])
const drawType = ref('')
const model = ref('')
const data = ref<any>(null)
const matrix = ref<any>(null)
const loading = ref(false)
const error = ref('')

const DAYS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
const weekdayName = (w: number) => DAYS[w] ?? w
const pct = (x?: number) => x == null ? '—' : x + ' %'
const barWidth = (m?: number) => `${Math.min(100, (m ?? 0) * 180)}px`
const trendLabel = (t: any) =>
  ({ improving: '↗ amélioration', declining: '↘ dégradation',
     flat: '→ stable', not_computable: '—' } as any)[t?.label] ?? '—'
const stabLabel = (s?: string) =>
  ({ stable: 'stable', mixed: 'mixte', volatile: 'volatile',
     not_computable: 'n/c' } as any)[s ?? ''] ?? '—'
const stabClass = (s?: string) =>
  s === 'stable' ? 'badge-ok' : s === 'volatile' ? 'badge-warn' : 'badge'
const sampleLabel = (s?: string) =>
  ({ adequate: 'suffisant', preliminary: 'préliminaire',
     insufficient: 'insuffisant' } as any)[s ?? ''] ?? '—'
const sampleClass = (s?: string) =>
  s === 'adequate' ? 'badge-ok' : s === 'preliminary' ? 'badge-warn' : 'badge-err'
const vsNull = (v: any) => v?.lift_mean_pct == null ? '—'
  : `${v.lift_mean_pct > 0 ? '+' : ''}${v.lift_mean_pct} % / ${v.binomial_p_ge1}`
const paired = (v: any) => v?.mean_hit_diff == null ? '—'
  : `${v.mean_hit_diff > 0 ? '+' : ''}${v.mean_hit_diff} / ${v.permutation_p}`

const ranked = computed(() =>
  Object.entries(data.value?.models ?? {})
    .map(([name, e]: any) => ({ name, ...e.profile,
      paired_vs_null: e.paired_vs_null }))
    .sort((a, b) => (b.mean_hits ?? -9) - (a.mean_hits ?? -9)))

const current = computed(() =>
  model.value ? data.value?.models?.[model.value] : null)

const alerts = computed(() => {
  const out: string[] = []
  for (const [name, e] of Object.entries<any>(data.value?.models ?? {})) {
    const p = e.profile ?? {}
    if (p.change_point)
      out.push(`Changement détecté — ${name} sur ${data.value.game} autour de ${p.change_point.iso_week} (p=${p.change_point.permutation_p}).`)
    if (p.trend?.label === 'declining')
      out.push(`Dégradation récente — ${name} : ${p.trend.delta_pct} % sur les ${p.trend.recent_weeks?.length} dernières semaines.`)
    if (p.trend?.label === 'improving')
      out.push(`Amélioration récente — ${name} : +${p.trend.delta_pct} % (observation, pas une preuve).`)
    if (p.sample_level === 'insufficient')
      out.push(`Échantillon insuffisant — ${name} : n=${p.n}.`)
  }
  return out
})

const matrixGames = computed(() => Object.keys(matrix.value?.matrix ?? {}).sort())
const matrixModels = computed(() => {
  const set = new Set<string>()
  for (const g of Object.values<any>(matrix.value?.matrix ?? {}))
    for (const m of Object.keys(g)) set.add(m)
  return [...set].sort()
})
const cell = (g: string, m: string) => matrix.value?.matrix?.[g]?.[m]

async function load() {
  if (!drawType.value) return
  loading.value = true; error.value = ''; data.value = null
  try {
    const res = await api.get('/api/lab/game-profiles', { params: { draw_type: drawType.value } })
    if (res.data.error) error.value = res.data.error
    else {
      data.value = res.data
      model.value = Object.keys(res.data.models ?? {})[0] ?? ''
    }
  } catch (e: any) {
    error.value = e.response?.data?.error || e.message
  } finally { loading.value = false }
}

onMounted(async () => {
  try {
    const [t, m] = await Promise.all([
      api.get('/api/lab/draw-types'),
      api.get('/api/lab/game-matrix'),
    ])
    matrix.value = m.data
    types.value = (t.data.data ?? [])
      .filter((x: any) => x.settled_draws >= 60)
      .sort((a: any, b: any) => b.settled_draws - a.settled_draws)
    if (types.value.length) { drawType.value = types.value[0].display_name; await load() }
  } catch (e: any) { error.value = e.response?.data?.error || e.message }
})
</script>

<style scoped>
.baseline-row td { opacity: 0.7; font-style: italic; }
.cell { text-align: center; font-size: 11px; }
.scrollbox { max-height: 280px; overflow-y: auto; }
.wbar { display: inline-block; height: 8px; background: var(--gold, #d4a017); border-radius: 2px; }
h4 { margin-bottom: 6px; }
</style>
