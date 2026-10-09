<template>
  <div class="panel">
    <h3>🤝 Consensus des modèles — meta-ensemble</h3>
    <div class="sub" style="margin-bottom:10px">
      Chaque modèle contributeur vote avec son Top 5. Deux stratégies pures,
      sans pondération apprise : <b>CONSENSUS_COUNT</b> (1 vote par modèle) et
      <b>CONSENSUS_FAMILY</b> (familles à poids égal — une famille à 4 variantes
      ne domine pas). Exclus : random, null_model_benchmark, ensemble_v1.
      Un vote majoritaire n'est pas une probabilité de gain : le consensus est
      évalué comme tout autre modèle (null, FDR, OOS, walk-forward, prospectif).
    </div>

    <div class="filters">
      <select v-model="drawType" @change="loadAll">
        <option v-for="t in types" :key="t.code + t.display_name" :value="t.display_name">
          {{ t.display_name }} ({{ t.settled_draws }} tirages)</option>
      </select>
      <input type="date" v-model="asOf" @change="loadAll"
             title="Vide = consensus pour le prochain tirage · date = consensus tel qu'il aurait été calculé avant ce tirage" />
      <button v-if="asOf" @click="asOf = ''; loadAll()">prochain tirage</button>
      <span v-if="loading" class="badge-warn">calcul en cours…</span>
    </div>
    <div v-if="error" class="badge-err">{{ error }}</div>

    <template v-else-if="data">
      <!-- A — tableau de bord -->
      <div class="sub" style="margin-bottom:8px">
        {{ data.draw_type }} · {{ data.n_draws }} tirages dans l'historique ·
        <b>{{ data.n_models }} modèles</b> participants ·
        {{ data.n_families }} familles ·
        cible : {{ data.as_of === 'next' ? 'prochain tirage' : 'avant le ' + data.as_of }}
      </div>
      <div class="filters" style="margin-bottom:10px">
        <button v-for="s in strategies" :key="s" class="tab"
                :class="{ active: strategy === s }" @click="strategy = s">
          {{ s }}</button>
        <span class="sub" style="align-self:center">{{ active.tie_break }}</span>
      </div>

      <!-- B — classement -->
      <div class="filters" style="margin-bottom:6px">
        <button v-for="n in [2, 3, 5, 10, 90]" :key="n" class="tab"
                :class="{ active: topN === n }" @click="topN = n">
          {{ n === 90 ? 'tous' : 'Top ' + n }}</button>
      </div>
      <table class="data mb0" style="margin-bottom:14px">
        <tr><th>Rang</th><th>N°</th><th>Votes</th><th>% modèles</th><th>Familles</th>
            <th>{{ strategy === 'CONSENSUS_COUNT' ? 'Borda' : 'Score' }}</th></tr>
        <tr v-for="r in shown" :key="r.number" @click="selected = r.number"
            :class="{ sel: selected === r.number }" style="cursor:pointer">
          <td class="mono">{{ r.rank }}</td>
          <td><span class="num-ball vote-ball">{{ r.number }}</span></td>
          <td class="mono"><b>{{ r.votes }}</b>/{{ data.n_models }}</td>
          <td class="mono">{{ Math.round(r.vote_pct * 100) }} %</td>
          <td class="mono">{{ r.families }}/{{ data.n_families }}</td>
          <td class="mono">{{ strategy === 'CONSENSUS_COUNT' ? r.borda : r.score }}</td>
        </tr>
      </table>

      <!-- F — détail du numéro sélectionné -->
      <div v-if="selectedDetail" class="detail">
        <b>N° {{ selected }}</b> soutenu par :
        <span v-for="v in selectedDetail.models" :key="v"
              class="chip">{{ v }}</span>
        <div class="sub">Familles : {{ selectedDetail.families.join(', ') }}</div>
      </div>

      <!-- C — matrice de votes modèles × numéros -->
      <h4 style="margin:14px 0 6px">Matrice de votes — qui propose quoi</h4>
      <div class="vote-matrix">
        <table class="data mb0">
          <tr><th>Modèle</th><th>Famille</th>
              <th v-for="n in candidates" :key="n" class="mono"
                  @click="selected = n" style="cursor:pointer"
                  :class="{ sel: selected === n }">{{ n }}</th></tr>
          <tr v-for="c in groupedContributors" :key="c.code">
            <td class="mono">{{ c.code }}</td>
            <td class="sub">{{ c.family }}</td>
            <td v-for="n in candidates" :key="n" class="cell"
                :class="{ on: c.picks.includes(n), sel: selected === n }"
                @click="selected = n">●</td>
          </tr>
        </table>
      </div>

      <!-- D — comparaison des stratégies -->
      <h4 style="margin:16px 0 6px">Comparaison — mêmes tirages, mêmes fenêtres</h4>
      <div v-if="matrixLoading" class="sub">matrice walk-forward en cours…</div>
      <table v-else-if="comparison.length" class="data mb0">
        <tr><th>Modèle</th><th>n WF</th><th>Hits moy.</th><th>Lift WF</th>
            <th>q FDR</th><th>Lift OOS</th><th>Prospectif (n)</th><th>Stage</th></tr>
        <tr v-for="m in comparison" :key="m.name"
            :class="{ 'baseline-row': m.baseline, meta: m.meta }">
          <td class="mono">{{ m.name }}</td>
          <td class="mono">{{ m.wf?.n ?? '—' }}</td>
          <td class="mono">{{ m.wf?.mean_hits ?? '—' }}</td>
          <td class="mono" :class="liftClass(m.wf?.lift_pct)">{{ pct(m.wf?.lift_pct) }}</td>
          <td class="mono">{{ m.wf?.q_fdr ?? '—' }}</td>
          <td class="mono" :class="liftClass(m.oos?.lift_pct)">{{ pct(m.oos?.lift_pct) }}</td>
          <td class="mono">{{ m.pros?.n != null ? (m.pros.mean_hits + ' (' + m.pros.n + ')') : '—' }}</td>
          <td class="mono" style="font-size:11px">{{ m.stage }}</td>
        </tr>
      </table>
      <div class="sub" style="margin-top:10px;opacity:.8">{{ data.disclaimer }}</div>
      <div class="sub" style="opacity:.7">{{ data.tie_break_doc }}</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const types = ref<any[]>([])
const drawType = ref('')
const asOf = ref('')
const data = ref<any>(null)
const matrix = ref<any>(null)
const loading = ref(false)
const matrixLoading = ref(false)
const error = ref('')
const strategies = ['CONSENSUS_COUNT', 'CONSENSUS_FAMILY']
const strategy = ref('CONSENSUS_COUNT')
const topN = ref(10)
const selected = ref<number | null>(null)

const active = computed(() => data.value?.strategies?.[strategy.value] ?? {})
const shown = computed(() =>
  (active.value.ranking ?? []).filter((r: any) => r.rank <= topN.value))
const candidates = computed(() => {
  const s = new Set<number>()
  for (const c of data.value?.contributors ?? [])
    for (const n of c.picks) s.add(n)
  return [...s].sort((a, b) => a - b)
})
const groupedContributors = computed(() =>
  [...(data.value?.contributors ?? [])]
    .sort((a: any, b: any) => a.family.localeCompare(b.family) || a.code.localeCompare(b.code)))
const selectedDetail = computed(() => {
  if (selected.value == null || !data.value) return null
  const models = (data.value.contributors as any[])
    .filter(c => c.picks.includes(selected.value)).map(c => c.code)
  const families = [...new Set((data.value.contributors as any[])
    .filter(c => c.picks.includes(selected.value)).map(c => c.family))]
  return { models, families }
})
const comparison = computed(() => {
  const m = matrix.value?.models ?? {}
  const rows = Object.entries(m).map(([name, e]: any) => ({
    name, wf: e.walk_forward, oos: e.out_of_sample, pros: e.prospective,
    stage: e.stage,
    meta: name.startsWith('meta_consensus'),
    baseline: ['random', 'null_model_benchmark'].includes(name),
  }))
  const meta = rows.filter(r => r.meta || r.name === 'ensemble_v1' || r.baseline)
  const best = rows.filter(r => !r.meta && !r.baseline && r.name !== 'ensemble_v1')
    .sort((a, b) => (b.wf?.lift_pct ?? -999) - (a.wf?.lift_pct ?? -999))
    .slice(0, 4)
  return [...meta, ...best]
    .sort((a, b) => (b.wf?.lift_pct ?? -999) - (a.wf?.lift_pct ?? -999))
})

function pct(x?: number) { return x == null ? '—' : (x > 0 ? '+' : '') + x + ' %' }
function liftClass(x?: number) {
  return x == null ? '' : x > 0 ? 'badge-ok' : 'badge-err'
}

async function load() {
  if (!drawType.value) return
  loading.value = true; error.value = ''; data.value = null; selected.value = null
  try {
    const res = await api.get('/api/lab/consensus', { params: {
      draw_type: drawType.value, date: asOf.value || undefined } })
    if (res.data.error) error.value = res.data.error
    else data.value = res.data
  } catch (e: any) {
    error.value = e.response?.data?.error || e.message
  } finally { loading.value = false }
}

async function loadMatrix() {
  if (!drawType.value) return
  matrixLoading.value = true
  try {
    const res = await api.get('/api/lab/matrix',
      { params: { draw_type: drawType.value } })
    matrix.value = res.data.error ? null : res.data
  } finally { matrixLoading.value = false }
}

async function loadAll() { load(); loadMatrix() }

onMounted(async () => {
  try {
    const res = await api.get('/api/lab/draw-types')
    types.value = (res.data.data ?? [])
      .filter((t: any) => t.settled_draws >= 60)
      .sort((a: any, b: any) => b.settled_draws - a.settled_draws)
    if (types.value.length) {
      drawType.value = types.value[0].display_name; await loadAll()
    }
  } catch (e: any) { error.value = e.response?.data?.error || e.message }
})
</script>

<style scoped>
.tab {
  background: var(--panel); color: var(--muted); border: 1px solid var(--border);
  border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: 12px;
}
.tab.active { background: var(--gold); color: #111; font-weight: 700; border-color: var(--gold); }
.vote-ball { background: var(--panel2, var(--panel)); }
.cell { color: transparent; text-align: center; cursor: pointer; padding: 2px 4px; }
.cell.on { color: var(--gold); }
.sel { outline: 1px solid var(--gold); background: rgba(255, 200, 0, .07); }
.baseline-row td { opacity: 0.7; font-style: italic; }
tr.meta td { background: rgba(100, 160, 255, .06); }
.detail { margin: 8px 0; padding: 8px; border: 1px solid var(--border); border-radius: 6px; }
.chip {
  display: inline-block; font-size: 11px; padding: 1px 7px; margin: 2px;
  border: 1px solid var(--border); border-radius: 10px;
  font-family: ui-monospace, monospace;
}
.vote-matrix { overflow-x: auto; }
.vote-matrix table { min-width: 100%; }
</style>
