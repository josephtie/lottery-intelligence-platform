<template>
  <h2 class="page-title">📈 Performance prospective</h2>
  <div class="sub" style="margin-bottom:14px">
    Métriques strictement <b>REALIZED</b> — prédictions enregistrées avant le tirage.
    Dénominateurs explicites, aucune promesse de gain.
  </div>

  <div class="cards" v-if="cov">
    <div class="card" v-for="c in covByStatus" :key="c.status">
      <div class="label">Couverture {{ c.status }}</div>
      <div class="value" :class="c.status === 'GENERATED' ? 'green' : (c.status === 'MISSING' ? 'red' : '')">{{ c.n }}</div>
      <div class="sub">{{ c.reason }}</div></div>
  </div>

  <div class="panel">
    <h3>Métriques par cohorte × modèle × type de tirage</h3>
    <table class="data mb0" v-if="metrics?.length">
      <tr><th>Cohorte</th><th>Modèle</th><th>Type</th><th>Éligibles</th><th>Générées</th><th>Soldées</th>
          <th>Taux</th><th>Hits moy.</th><th>Turbo-2 net</th><th>Puissance</th></tr>
      <tr v-for="m in metrics" :key="m.cohort_code + m.model_code + m.draw_type">
        <td class="mono">{{ m.cohort_code }}</td>
        <td class="mono">{{ m.model_code }}</td>
        <td>{{ m.draw_type }}</td>
        <td>{{ m.eligible_pairs }}</td>
        <td>{{ m.generated }}</td>
        <td>{{ m.settled }}</td>
        <td class="mono">{{ pct(m.settlement_rate) }}</td>
        <td class="mono">{{ m.mean_hits?.toFixed(2) ?? '—' }}</td>
        <td class="mono">{{ turboNet(m) }}</td>
        <td><span v-if="m.low_power" class="badge-warn" title="moins de 30 tirages historiques">low-power</span>
            <span v-else class="mono">{{ m.historical_draws }}</span></td>
      </tr>
    </table>
    <div v-else-if="!loading" class="sub">Aucune métrique encore — la cohorte accumule.</div>
    <div v-if="err" class="badge-err">{{ err }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useFetch } from '../useFetch'

const { data: metrics, loading, error: err } = useFetch<any[]>('/api/prospective/metrics')
const { data: cov } = useFetch<any[]>('/api/prospective/coverage')
const covByStatus = computed(() => cov.value ?? [])
function pct(x?: number) { return x == null ? '—' : (x * 100).toFixed(0) + '%' }
function turboNet(m: any) {
  const t = m.turbo?.turbo2 ?? m.turbo?.TURBO_2
  return t ? `${t.net}` : '—'
}
</script>
