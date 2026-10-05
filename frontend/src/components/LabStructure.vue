<template>
  <div class="panel">
    <h3>🧬 Structure des tirages — hasard de référence, dépendance, ruptures</h3>
    <div class="sub" style="margin-bottom:10px">
      Trois tests qui répondent à « les tirages dévient-ils du hasard attendu ? »
      Référence nulle par simulation (M04), dépendance sérielle tirage→tirage (M05),
      rupture de distribution mensuelle (M06). Un signal ≠ une preuve : règles
      modifiées ou trous de collecte produisent les mêmes indices.
    </div>
    <div class="filters">
      <select v-model="drawType" @change="load">
        <option v-for="t in types" :key="t.code + t.display_name" :value="t.display_name">
          {{ t.display_name }} ({{ t.settled_draws }} tirages)</option>
      </select>
      <span v-if="loading" class="badge-warn">calcul en cours…</span>
    </div>
    <div v-if="error" class="badge-err">{{ error }}</div>

    <template v-else-if="data">
      <div class="cards">
        <!-- M04 -->
        <div class="stat-card">
          <h4>🎲 Référence nulle (M04)</h4>
          <template v-if="!data.null_reference?.insufficient">
            <div class="kpi" :class="data.null_reference.compatible_with_chance ? 'ok' : 'err'">
              {{ data.null_reference.compatible_with_chance ? 'Compatible avec le hasard' : 'Écart détecté' }}
            </div>
            <div class="sub">
              χ² observé {{ fmt(data.null_reference.observed_chi_square) }} ·
              médiane simulée {{ fmt(data.null_reference.simulated_median) }} ·
              p empirique {{ fmt(data.null_reference.empirical_p) }}
              ({{ data.null_reference.simulations }} simulations)
            </div>
          </template>
          <div v-else class="sub">Historique insuffisant ({{ data.null_reference.draws }} tirages).</div>
        </div>

        <!-- M05 -->
        <div class="stat-card">
          <h4>🔗 Dépendance sérielle (M05)</h4>
          <template v-if="!data.serial_dependence?.insufficient">
            <div class="kpi" :class="data.serial_dependence.serial_dependence_detected ? 'err' : 'ok'">
              {{ data.serial_dependence.serial_dependence_detected ? 'Dépendance détectée' : 'Pas de dépendance' }}
            </div>
            <div class="sub">
              Chevauchement moyen {{ fmt(data.serial_dependence.overlap_mean) }}
              vs attendu {{ fmt(data.serial_dependence.overlap_expected) }} ·
              p permutation {{ fmt(data.serial_dependence.overlap_permutation_p) }} ·
              indépendance χ² p={{ fmt(data.serial_dependence.independence_p_value) }}
            </div>
          </template>
          <div v-else class="sub">Historique insuffisant ({{ data.serial_dependence.draws }} tirages).</div>
        </div>

        <!-- M06 -->
        <div class="stat-card">
          <h4>📉 Rupture de régime (M06)</h4>
          <template v-if="!data.change_point?.insufficient">
            <div class="kpi" :class="data.change_point.change_detected ? 'warn' : 'ok'">
              {{ data.change_point.change_detected
                ? 'Rupture candidate : ' + data.change_point.candidate_split_period
                : 'Aucune rupture' }}
            </div>
            <div class="sub">
              {{ data.change_point.months }} mois · statistique {{ fmt(data.change_point.statistic) }}
              · p permutation {{ fmt(data.change_point.permutation_p) }}
            </div>
          </template>
          <div v-else class="sub">Moins de 3 mois de données ({{ data.change_point?.months ?? 0 }} mois).</div>
        </div>
      </div>
      <div class="sub" style="margin-top:8px">
        {{ data.draws }} tirages analysés · les tests de permutation mélangent
        l'ordre des tirages : un p élevé confirme que la séquence est
        indiscernable du hasard.
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'

const types = ref<any[]>([])
const drawType = ref('')
const data = ref<any>(null)
const loading = ref(false)
const error = ref('')

function fmt(x?: number) {
  return x == null ? '—' : (x < 0.001 ? x.toExponential(1) : Math.round(x * 1000) / 1000)
}

async function load() {
  if (!drawType.value) return
  loading.value = true; error.value = ''; data.value = null
  try {
    const res = await api.get('/api/lab/structure', { params: { draw_type: drawType.value } })
    if (res.data.error) error.value = res.data.error
    else data.value = res.data
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
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.stat-card { background: var(--panel2); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.stat-card h4 { margin: 0 0 8px; font-size: 13px; }
.kpi { font-size: 15px; font-weight: 700; margin-bottom: 4px; }
.kpi.ok { color: var(--green); }
.kpi.err { color: var(--red); }
.kpi.warn { color: var(--gold); }
</style>
