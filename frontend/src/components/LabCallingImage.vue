<template>
  <div class="panel">
    <h3>🧲 Calling / Image — hypothèses directionnelles</h3>
    <div class="sub" style="margin-bottom:10px">
      Quatre hypothèses mesurées séparément : <b>H1 image</b> (57→75),
      <b>H2 numéros appelés</b> (voisins de grille), <b>H3 appelés + images</b>,
      <b>H4 positionnel</b>. Pour chaque arête A→B : P(B|A) vs P(B), lift,
      p binomiale, p par permutation, correction FDR. Une anomalie est un
      <i>candidat</i>, jamais un verdict — elle doit survivre au modèle nul,
      à l'OOS, au walk-forward et au prospectif scellé.
    </div>
    <div class="filters">
      <select v-model="drawType" @change="load">
        <option v-for="t in types" :key="t.code + t.display_name" :value="t.display_name">
          {{ t.display_name }} ({{ t.settled_draws }} tirages)</option>
      </select>
      <span v-if="loading" class="badge-warn">calcul en cours…</span>
    </div>
    <div v-if="error" class="badge-err">{{ error }}</div>
    <template v-else-if="result">
      <div class="sub" style="margin-bottom:8px">
        {{ result.draw_type }} · {{ result.n_draws }} tirages
      </div>
      <div class="filters" style="margin-bottom:8px">
        <button v-for="(h, code) in result.hypotheses" :key="code"
                class="tab" :class="{ active: hypo === code }"
                @click="hypo = code; horizon = '0'">
          {{ code }}</button>
      </div>
      <template v-if="activeHypo">
        <div class="sub">{{ activeHypo.label }} · {{ activeHypo.edge_count }} arêtes dirigées</div>
        <div class="filters" v-if="!isPositional" style="margin:6px 0">
          <button v-for="h in horizons" :key="h" class="tab"
                  :class="{ active: horizon === h }" @click="horizon = h">
            {{ horizonLabel(h) }}</button>
        </div>
        <div class="sub" v-if="activeCell" style="margin-bottom:6px">
          {{ activeCell.edges_tested }} tests (≥ support) ·
          {{ activeCell.edges_low_support }} sous support ·
          <b :class="activeCell.significant_fdr ? 'badge-warn' : 'badge-ok'">
            {{ activeCell.significant_fdr }} arête(s) q&lt;0.05</b>
          <span v-if="activeOos">
            · réplication OOS : {{ activeOos.oos_surviving }}/{{ activeOos.train_candidates }}
            candidat(s) train gardent lift&gt;1
          </span>
        </div>
        <table class="data mb0" v-if="activeCell?.edges?.length">
          <tr><th>Arête</th><th v-if="isPositional">pos</th><th>n</th><th>hits</th>
              <th>P(B|A)</th><th>P(B)</th><th>lift</th><th>p</th><th>p perm</th><th>q FDR</th></tr>
          <tr v-for="e in activeCell.edges" :key="edgeKey(e)">
            <td class="mono">{{ e.a }} → {{ e.b }}</td>
            <td class="mono" v-if="isPositional">{{ e.pos_a }}→{{ e.pos_b }}</td>
            <td class="mono">{{ e.n_trigger }}</td>
            <td class="mono">{{ e.hits }}</td>
            <td class="mono">{{ e.p_cond }}</td>
            <td class="mono">{{ e.p_base }}</td>
            <td class="mono" :class="liftClass(e.lift)">{{ e.lift ?? '—' }}</td>
            <td class="mono">{{ e.p_value }}</td>
            <td class="mono">{{ e.p_perm ?? '—' }}</td>
            <td class="mono" :class="e.q_fdr < 0.05 ? 'badge-warn' : ''">{{ e.q_fdr }}</td>
          </tr>
        </table>
        <div v-else class="sub">Aucune arête ne dépasse le seuil de support à cet horizon.</div>
      </template>
      <div class="sub" style="margin-top:10px;opacity:.8">{{ result.disclaimer }}</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const types = ref<any[]>([])
const drawType = ref('')
const result = ref<any>(null)
const loading = ref(false)
const error = ref('')
const hypo = ref('H1_IMAGE')
const horizon = ref('0')

const horizons = computed(() =>
  (result.value?.horizons ?? [0, 1, 3]).map((h: number) => String(h)))
const activeHypo = computed(() => result.value?.hypotheses?.[hypo.value])
const isPositional = computed(() => hypo.value === 'H4_CALLING_IMAGE_POSITION')
const activeCell = computed(() =>
  isPositional.value
    ? activeHypo.value?.per_horizon?.position
    : activeHypo.value?.per_horizon?.[horizon.value])
const activeOos = computed(() =>
  isPositional.value
    ? activeHypo.value?.oos
    : activeHypo.value?.oos?.[horizon.value])

function horizonLabel(h: string) {
  return h === '0' ? 'même tirage' : h === '1' ? 'tirage suivant' : `fenêtre ${h}`
}
function edgeKey(e: any) {
  return `${e.a}-${e.b}-${e.pos_a ?? ''}-${e.pos_b ?? ''}`
}
function liftClass(x?: number) {
  return x == null ? '' : x > 1 ? 'badge-ok' : 'badge-err'
}

async function load() {
  if (!drawType.value) return
  loading.value = true; error.value = ''; result.value = null
  try {
    const res = await api.get('/api/lab/calling-image',
      { params: { draw_type: drawType.value } })
    if (res.data.error) error.value = res.data.error
    else result.value = res.data
  } catch (e: any) {
    error.value = e.response?.data?.error || e.message
  } finally { loading.value = false }
}

onMounted(async () => {
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
