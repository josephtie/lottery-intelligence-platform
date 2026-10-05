<template>
  <div class="panel">
    <h3>📐 Matrice de performance — jeu × modèle × niveau</h3>
    <div class="sub" style="margin-bottom:10px">
      Chaque modèle rejoue les mêmes tirages à 4 niveaux : in-sample (exploration),
      walk-forward (backtest réel), out-of-sample (20% récents cachés), prospectif
      (prédictions scellées). Correction FDR par jeu. Verdict par défaut :
      aucun modèle démontré.
    </div>
    <div class="filters">
      <select v-model="drawType" @change="load">
        <option v-for="t in types" :key="t.code + t.display_name" :value="t.display_name">
          {{ t.display_name }} ({{ t.settled_draws }} tirages)</option>
      </select>
      <span v-if="loading" class="badge-warn">calcul walk-forward en cours (~10 s)…</span>
    </div>
    <div v-if="error" class="badge-err">{{ error }}</div>
    <template v-else-if="matrix">
      <div class="sub" style="margin-bottom:8px">
        {{ matrix.game }} · {{ matrix.n_history }} tirages · holdout OOS {{ matrix.n_oos }}
        · verdict : <b :class="matrix.candidate?.candidate ? 'badge-ok' : 'badge-warn'">{{ matrix.candidate?.verdict }}</b>
      </div>
      <table class="data mb0">
        <tr><th>Modèle</th><th>n WF</th><th>Hits moy.</th><th>Lift WF</th>
            <th>p</th><th>q FDR</th><th>Lift OOS</th><th>Prospectif (n)</th>
            <th>Robustesse</th><th>Stage</th></tr>
        <tr v-for="m in sortedModels" :key="m.name"
            :class="{ 'baseline-row': ['random','null_model_benchmark'].includes(m.name) }">
          <td class="mono">{{ m.name }}
            <span v-if="m.name === 'hot_frequency_v1'" title="modèle de référence">★</span></td>
          <td class="mono">{{ m.wf?.n ?? '—' }}</td>
          <td class="mono">{{ m.wf?.mean_hits ?? '—' }}</td>
          <td class="mono" :class="liftClass(m.wf?.lift_pct)">{{ pct(m.wf?.lift_pct) }}</td>
          <td class="mono">{{ m.wf?.p_value ?? '—' }}</td>
          <td class="mono" :class="qClass(m.wf?.q_fdr)">{{ m.wf?.q_fdr ?? '—' }}</td>
          <td class="mono" :class="liftClass(m.oos?.lift_pct)">{{ pct(m.oos?.lift_pct) }}</td>
          <td class="mono">{{ m.pros?.n != null ? (m.pros.mean_hits + ' (' + m.pros.n + ')') : '—' }}</td>
          <td class="mono">{{ m.robustness }}/100</td>
          <td class="mono" style="font-size:11px">{{ m.stage }}</td>
        </tr>
      </table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const types = ref<any[]>([])
const drawType = ref('')
const matrix = ref<any>(null)
const loading = ref(false)
const error = ref('')

const sortedModels = computed(() => {
  const m = matrix.value?.models ?? {}
  return Object.entries(m)
    .map(([name, e]: any) => ({
      name, wf: e.walk_forward, oos: e.out_of_sample,
      pros: e.prospective, stage: e.stage, robustness: e.robustness,
    }))
    .sort((a, b) => (b.wf?.lift_pct ?? -999) - (a.wf?.lift_pct ?? -999))
})

function pct(x?: number) { return x == null ? '—' : (x > 0 ? '+' : '') + x + ' %' }
function liftClass(x?: number) {
  return x == null ? '' : x > 0 ? 'badge-ok' : 'badge-err'
}
function qClass(q?: number) {
  return q == null ? '' : q < 0.10 ? 'badge-ok' : ''
}

async function load() {
  if (!drawType.value) return
  loading.value = true; error.value = ''; matrix.value = null
  try {
    const res = await api.get('/api/lab/matrix', { params: { draw_type: drawType.value } })
    if (res.data.error) error.value = res.data.error
    else matrix.value = res.data
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
.baseline-row td { opacity: 0.7; font-style: italic; }
</style>
