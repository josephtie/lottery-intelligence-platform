<template>
  <div class="panel">
    <h3>🤝 Consensus des modèles — meta-ensemble</h3>

    <div class="filters">
      <select v-model="drawType" @change="load">
        <option v-for="t in types" :key="t.code + t.display_name" :value="t.display_name">
          {{ t.display_name }}</option>
      </select>
      <button v-for="s in strategies" :key="s" class="tab"
              :class="{ active: strategy === s }" @click="strategy = s">
        {{ s === 'CONSENSUS_COUNT' ? 'Vote simple' : 'Vote par famille' }}</button>
      <span v-if="loading" class="badge-warn">calcul en cours…</span>
    </div>
    <div v-if="error" class="badge-err">{{ error }}</div>

    <template v-else-if="data">
      <div class="sub" style="margin-bottom:12px">
        {{ data.draw_type }} · cible : {{ data.as_of === 'next' ? 'prochain tirage' : 'avant le ' + data.as_of }}
        · stratégie {{ strategy }} · {{ data.n_models }} modèles · {{ data.n_families }} familles
      </div>

      <!-- Les 5 meilleurs numéros -->
      <div class="top5">
        <div v-for="r in top5" :key="r.number" class="pick">
          <div class="big-ball">{{ r.number }}</div>
          <div class="rank">#{{ r.rank }}</div>
          <div class="votes">{{ r.votes }}/{{ data.n_models }} modèles</div>
          <div class="fams">{{ famNames(r.number).join(' · ') }}</div>
        </div>
        <div v-if="!top5.length" class="sub">Données insuffisantes pour un consensus.</div>
      </div>

      <!-- Récapitulatif -->
      <table class="data mb0" v-if="top5.length">
        <tr><th>Rang</th><th>Numéro</th><th>Votes</th><th>Familles impliquées</th></tr>
        <tr v-for="r in top5" :key="r.number">
          <td class="mono">{{ r.rank }}</td>
          <td class="mono"><b>{{ r.number }}</b></td>
          <td class="mono">{{ r.votes }}/{{ data.n_models }}</td>
          <td>{{ famNames(r.number).join(', ') || '—' }}</td>
        </tr>
      </table>

      <div class="sub" style="margin-top:10px;opacity:.8">
        Le nombre de votes mesure l'accord entre modèles, pas une probabilité de
        gain. Les prédictions scellées du méta-modèle (Turbo 2) figurent sous
        <span class="mono">meta_consensus_*</span> dans l'onglet « prédictions
        scellées » — ce Top-5 est une vue de recherche calculée à date, pas une
        prédiction scellée.
      </div>

      <!-- Détail repliable -->
      <details class="detail-box">
        <summary>Voir le détail (matrice des votes, classement complet, comparaison)</summary>

        <h4 style="margin:12px 0 6px">Classement complet</h4>
        <div class="filters" style="margin-bottom:6px">
          <button v-for="n in [10, 30, 90]" :key="n" class="tab"
                  :class="{ active: topN === n }" @click="topN = n">
            {{ n === 90 ? 'tous' : 'Top ' + n }}</button>
        </div>
        <table class="data mb0" style="margin-bottom:12px">
          <tr><th>Rang</th><th>N°</th><th>Votes</th><th>%</th><th>Familles</th>
              <th>{{ strategy === 'CONSENSUS_COUNT' ? 'Borda' : 'Score' }}</th></tr>
          <tr v-for="r in shown" :key="r.number" @click="selected = r.number"
              :class="{ sel: selected === r.number }" style="cursor:pointer">
            <td class="mono">{{ r.rank }}</td>
            <td class="mono">{{ r.number }}</td>
            <td class="mono">{{ r.votes }}/{{ data.n_models }}</td>
            <td class="mono">{{ Math.round(r.vote_pct * 100) }} %</td>
            <td class="mono">{{ r.families }}/{{ data.n_families }}</td>
            <td class="mono">{{ strategy === 'CONSENSUS_COUNT' ? r.borda : r.score }}</td>
          </tr>
        </table>
        <div v-if="selected != null" class="detail">
          <b>N° {{ selected }}</b> soutenu par :
          <span v-for="v in selectedModels" :key="v" class="chip">{{ v }}</span>
          <div class="sub">Familles : {{ famNames(selected).join(', ') || '—' }}</div>
        </div>

        <h4 style="margin:14px 0 6px">Matrice de votes</h4>
        <div class="vote-matrix">
          <table class="data mb0">
            <tr><th>Modèle</th><th>Famille</th>
                <th v-for="n in candidates" :key="n" class="mono">{{ n }}</th></tr>
            <tr v-for="c in groupedContributors" :key="c.code">
              <td class="mono">{{ c.code }}</td>
              <td class="sub">{{ FAMILY_LABELS[c.family] || c.family }}</td>
              <td v-for="n in candidates" :key="n" class="cell"
                  :class="{ on: c.picks.includes(n) }"
                  @click="selected = n">●</td>
            </tr>
          </table>
        </div>

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
        <div class="sub" style="margin-top:8px;opacity:.7">{{ data.tie_break_doc }}</div>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const FAMILY_LABELS: Record<string, string> = {
  frequency: 'Fréquence',
  delay: 'Retard',
  bayesian: 'Bayésien',
  combinatorial: 'Combinatoire',
  simulation: 'Monte-Carlo',
  calling_image: 'Calling/Image',
}

const types = ref<any[]>([])
const drawType = ref('')
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
const top5 = computed(() => (active.value.ranking ?? []).slice(0, 5))
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
const selectedModels = computed(() =>
  selected.value == null ? []
    : (data.value.contributors as any[])
        .filter(c => c.picks.includes(selected.value)).map(c => c.code))
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

function famNames(num: number): string[] {
  if (!data.value) return []
  const fams = (data.value.contributors as any[])
    .filter(c => c.picks.includes(num)).map(c => c.family)
  return [...new Set(fams)].map(f => FAMILY_LABELS[f] || f)
}
function pct(x?: number) { return x == null ? '—' : (x > 0 ? '+' : '') + x + ' %' }
function liftClass(x?: number) {
  return x == null ? '' : x > 0 ? 'badge-ok' : 'badge-err'
}

async function load() {
  if (!drawType.value) return
  loading.value = true; error.value = ''; data.value = null; selected.value = null
  try {
    const res = await api.get('/api/lab/consensus',
      { params: { draw_type: drawType.value } })
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

onMounted(async () => {
  try {
    const res = await api.get('/api/lab/draw-types')
    types.value = (res.data.data ?? [])
      .filter((t: any) => t.settled_draws >= 60)
      .sort((a: any, b: any) => b.settled_draws - a.settled_draws)
    if (types.value.length) {
      drawType.value = types.value[0].display_name
      load(); loadMatrix()
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

.top5 { display: flex; gap: 18px; flex-wrap: wrap; margin: 6px 0 16px; }
.pick { text-align: center; width: 92px; }
.big-ball {
  width: 58px; height: 58px; border-radius: 50%;
  background: var(--gold); color: #111;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 800; margin: 0 auto;
  border: 3px solid var(--gold-soft);
}
.rank { color: var(--muted); font-size: 11px; margin-top: 4px; }
.votes { font-size: 12px; font-weight: 700; }
.fams { color: var(--muted); font-size: 10px; line-height: 1.3; margin-top: 2px; }

.detail-box { margin-top: 14px; border-top: 1px solid var(--border); padding-top: 8px; }
.detail-box summary { cursor: pointer; color: var(--muted); font-size: 12px; }
.detail { margin: 8px 0; padding: 8px; border: 1px solid var(--border); border-radius: 6px; }
.chip {
  display: inline-block; font-size: 11px; padding: 1px 7px; margin: 2px;
  border: 1px solid var(--border); border-radius: 10px;
  font-family: ui-monospace, monospace;
}
.cell { color: transparent; text-align: center; cursor: pointer; padding: 2px 4px; }
.cell.on { color: var(--gold); }
.sel { outline: 1px solid var(--gold); background: rgba(255, 200, 0, .07); }
.baseline-row td { opacity: 0.7; font-style: italic; }
tr.meta td { background: rgba(100, 160, 255, .06); }
.vote-matrix { overflow-x: auto; }
</style>
