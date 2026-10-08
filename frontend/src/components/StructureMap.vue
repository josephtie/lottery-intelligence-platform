<template>
  <div class="panel">
    <h3>🗺️ Structure Map — le processus a-t-il une structure ?</h3>
    <div class="sub" style="margin-bottom:10px">
      Chaque famille de phénomènes est déclarée, mesurée contre un modèle nul
      adapté (<b>NULL A</b> théorique, <b>NULL B</b> permutation,
      <b>NULL C</b> structural avec marges conservées), corrigée par FDR et
      répliquée sur le holdout final. <b>INTERESTING</b> n'est pas prédictif ;
      <b>VALIDATED</b> exige le prospectif scellé et n'est jamais attribué
      automatiquement.
    </div>
    <div class="filters">
      <select v-model="drawType" @change="load">
        <option v-for="t in types" :key="t.code + t.display_name" :value="t.display_name">
          {{ t.display_name }} ({{ t.settled_draws }} tirages)</option>
      </select>
      <button class="tab" :class="{ active: light }" @click="light = !light; load()"
              title="light : sans la matrice de transition 90×90 complète">
        {{ light ? 'mode light' : 'matrice complète' }}</button>
      <span v-if="loading" class="badge-warn">calcul en cours…</span>
    </div>
    <div v-if="error" class="badge-err">{{ error }}</div>
    <template v-else-if="result">
      <div class="sub" style="margin-bottom:8px">
        {{ result.draw_type }} · {{ result.n_draws }} tirages
        (train {{ result.train_size }} + holdout {{ result.holdout_size }})
        · verdict global :
        <b :class="verdictClass">{{ result.verdict }}</b>
      </div>
      <table class="data mb0">
        <tr><th>Famille</th><th>Null</th><th>tests</th><th>significatifs</th>
            <th>min q</th><th>OOS</th><th>Statut</th></tr>
        <tr v-for="s in result.statuses" :key="s.family"
            @click="open = open === s.family ? '' : s.family"
            style="cursor:pointer">
          <td class="mono">{{ familyLabel(s.family) }}</td>
          <td class="mono">{{ s.null ?? '—' }}</td>
          <td class="mono">{{ s.n_tests.toLocaleString() }}</td>
          <td class="mono">{{ s.significant }}</td>
          <td class="mono">{{ s.min_q ?? '—' }}</td>
          <td class="mono">{{ oosLabel(s.oos_ok) }}</td>
          <td><b :class="statusClass(s.status)">{{ s.status }}</b></td>
        </tr>
      </table>

      <!-- detail panel of the selected family -->
      <template v-if="open && detail">
        <div class="sub" style="margin:10px 0 6px"><b>{{ familyLabel(open) }}</b> — détail</div>
        <table class="data mb0" v-if="detailRows.length">
          <tr>
            <th v-for="h in detailCols" :key="h">{{ h }}</th>
          </tr>
          <tr v-for="(r, i) in detailRows" :key="i">
            <td v-for="h in detailCols" :key="h" class="mono"
                :class="h === 'q_fdr' && r[h] < 0.05 ? 'badge-warn' : ''">
              {{ fmtCell(r, h) }}</td>
          </tr>
        </table>
        <div v-else class="sub">{{ detailNote }}</div>
      </template>

      <div class="sub" style="margin-top:10px;opacity:.8">
        Nulls : {{ result.null_models?.NULL_A }} / {{ result.null_models?.NULL_B }} /
        {{ result.null_models?.NULL_C }}
      </div>
      <div class="sub" style="opacity:.8">{{ result.disclaimer }}</div>
    </template>
  </div>

  <div class="panel">
    <h3>🔗 Cross-game — transitions intra-jour X → Y</h3>
    <div class="sub" style="margin-bottom:8px">
      Pour chaque paire de jeux adjacents dans la journée (ordre horaire) :
      chevauchement moyen |X ∩ Y| vs espérance hypergéométrique (permutation)
      et densité des arêtes « appelées » X → Y. Jeux distincts — jamais
      poolés dans un même échantillon.
    </div>
    <span v-if="cgLoading" class="badge-warn">calcul en cours…</span>
    <div v-if="cgError" class="badge-err">{{ cgError }}</div>
    <template v-else-if="crossGame">
      <div class="sub" style="margin-bottom:6px">
        {{ crossGame.n_days }} jours · {{ crossGame.n_tests }} paires testées ·
        <b :class="crossGame.significant ? 'badge-warn' : 'badge-ok'">
          {{ crossGame.significant }} significative(s) q&lt;0.05</b>
      </div>
      <table class="data mb0" v-if="crossGame.pairs?.length">
        <tr><th>De → Vers</th><th>jours</th><th>∩ moyen</th><th>∩ attendu</th>
            <th>lift</th><th>∩ q perm</th><th>appelés obs</th><th>attendu</th>
            <th>appelés q perm</th><th>q FDR</th></tr>
        <tr v-for="p in crossGame.pairs" :key="p.from + p.to">
          <td class="mono">{{ p.from }} → {{ p.to }}</td>
          <td class="mono">{{ p.days }}</td>
          <td class="mono">{{ p.overlap_mean }}</td>
          <td class="mono">{{ p.overlap_expected }}</td>
          <td class="mono" :class="p.overlap_lift > 1 ? 'badge-ok' : ''">
            {{ p.overlap_lift ?? '—' }}</td>
          <td class="mono" :class="p.overlap_q_fdr < 0.05 ? 'badge-warn' : ''">
            {{ p.overlap_q_fdr }}</td>
          <td class="mono">{{ p.calling_hits }}</td>
          <td class="mono">{{ p.calling_expected }}</td>
          <td class="mono" :class="p.calling_q_fdr < 0.05 ? 'badge-warn' : ''">
            {{ p.calling_q_fdr }}</td>
          <td class="mono" :class="p.q_fdr < 0.05 ? 'badge-warn' : ''">{{ p.q_fdr }}</td>
        </tr>
      </table>
      <div v-else class="sub">Pas assez de paires de jeux avec ≥ 10 jours communs.</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const FAMILY_LABELS: Record<string, string> = {
  frequency: 'Fréquence (fenêtres)',
  autocorrelation: 'Autocorrélation A→A',
  transition: 'Transitions A→B (90×90)',
  position: 'Positions',
  runs_delay: 'Runs & retards',
  change_point: 'Point de rupture',
  seasonality: 'Saisonnalité',
  calling_image: 'Calling / Image',
}

const types = ref<any[]>([])
const drawType = ref('')
const result = ref<any>(null)
const loading = ref(false)
const error = ref('')
const light = ref(true)
const open = ref('')
const crossGame = ref<any>(null)
const cgLoading = ref(false)
const cgError = ref('')

const detail = computed(() => result.value?.families?.[open.value])
const detailRows = computed(() => {
  const d = detail.value
  if (!d) return []
  if (open.value === 'transition') return d.top ?? []
  if (open.value === 'autocorrelation') return d.top ?? []
  if (open.value === 'frequency') return d.top ?? []
  if (open.value === 'position')
    return (d.position_uniformity ?? []).concat(d.persistence ?? []).slice(0, 20)
  if (open.value === 'runs_delay')
    return (d.delay_top ?? []).concat(d.runs_top ?? []).slice(0, 20)
  if (open.value === 'calling_image')
    return Object.entries(d.sub ?? {}).map(([k, v]: [string, any]) => ({
      hypothesis: k, label: v.label, n_tests: v.n_tests,
      significant: v.significant, q_fdr: v.min_q }))
  return []
})
const detailCols = computed(() =>
  detailRows.value.length ? Object.keys(detailRows.value[0]) : [])
const detailNote = computed(() => {
  const d = detail.value
  if (!d) return ''
  if (open.value === 'change_point')
    return d.detail ? JSON.stringify(d.detail) : 'historique insuffisant'
  if (open.value === 'seasonality')
    return `table semaine×numéro : χ²=${d.weekday_table?.chi2} (p=${d.weekday_table?.p_value}) · totaux par jour : χ²=${d.weekday_totals?.chi2} (p=${d.weekday_totals?.p_value})`
  return 'aucun détail'
})
const verdictClass = computed(() => statusClass(result.value?.verdict))

function familyLabel(f: string) { return FAMILY_LABELS[f] ?? f }
function oosLabel(o: boolean | null) {
  return o === true ? 'répliqué' : o === false ? 'non répliqué' : '—'
}
function statusClass(s?: string) {
  return s === 'VALIDATED' || s === 'ROBUST' ? 'badge-ok'
    : s === 'NO_SIGNAL' ? 'badge-ok' : 'badge-warn'
}
function fmtCell(r: any, h: string) {
  const v = r[h]
  if (v == null) return '—'
  if (Array.isArray(v)) return v.join('→')
  return v
}

async function load() {
  if (!drawType.value) return
  loading.value = true; error.value = ''; result.value = null; open.value = ''
  try {
    const res = await api.get('/api/lab/structure-map',
      { params: { draw_type: drawType.value, light: light.value ? 1 : 0 } })
    if (res.data.error) error.value = res.data.error
    else result.value = res.data
  } catch (e: any) {
    error.value = e.response?.data?.error || e.message
  } finally { loading.value = false }
}

async function loadCrossGame() {
  cgLoading.value = true; cgError.value = ''
  try {
    const res = await api.get('/api/lab/cross-game')
    if (res.data.error) cgError.value = res.data.error
    else crossGame.value = res.data
  } catch (e: any) {
    cgError.value = e.response?.data?.error || e.message
  } finally { cgLoading.value = false }
}

onMounted(async () => {
  loadCrossGame()
  try {
    const res = await api.get('/api/lab/draw-types')
    types.value = (res.data.data ?? [])
      .filter((t: any) => t.settled_draws >= 60)
      .sort((a: any, b: any) => b.settled_draws - a.settled_draws)
    if (types.value.length) { drawType.value = types.value[0].display_name; await load() }
  } catch (e: any) { error.value = e.response?.data?.error || e.message }
})
</script>

<style scoped>
.tab {
  background: var(--panel); color: var(--muted); border: 1px solid var(--border);
  border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: 12px;
}
.tab.active { background: var(--gold); color: #111; font-weight: 700; border-color: var(--gold); }
</style>
