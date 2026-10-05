<template>
  <div class="panel">
    <h3>🔮 Prospectif multi-modèles (H008)</h3>
    <div class="sub" style="margin-bottom:10px">
      Prédictions <b>scellées avant les tirages</b>, évaluées sur les résultats
      officiels — le seul niveau de preuve décisif. Comparaison au modèle nul
      sur les mêmes tirages admissibles.
    </div>
    <div v-if="err" class="badge-err">{{ err }}</div>
    <template v-else-if="rows.length">
      <table class="data mb0">
        <tr><th>Modèle</th><th>Type</th><th>Générées</th><th>Scellées</th>
            <th>Soldées</th><th>Taux règlement</th><th>Hits moy.</th>
            <th>Hits pos. ≤2</th><th>Alerte puissance</th></tr>
        <tr v-for="r in rows" :key="r.model_code + r.draw_type"
            :class="{ 'baseline-row': r.model_code === 'null_model_benchmark' }">
          <td class="mono">{{ r.model_code }}</td>
          <td>{{ r.draw_type }}</td>
          <td class="mono">{{ r.generated }}</td>
          <td class="mono">{{ r.locked }}</td>
          <td class="mono">{{ r.settled }}</td>
          <td class="mono">{{ r.settlement_rate != null ? (r.settlement_rate * 100).toFixed(0) + ' %' : '—' }}</td>
          <td class="mono">{{ r.mean_hits ?? '—' }}</td>
          <td class="mono">{{ r.hits_first_2 ?? '—' }}</td>
          <td><span v-if="r.low_power" class="badge-warn" title="échantillon insuffisant">⚠ faible</span>
              <span v-else class="sub">—</span></td>
        </tr>
      </table>
    </template>
    <div v-else class="sub">Pas encore de métriques prospectives — l'accumulation vient de démarrer.</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useFetch } from '../useFetch'

const { data, error: err } = useFetch<any[]>('/api/prospective/metrics')
const rows = computed(() =>
  (data.value ?? []).slice().sort(
    (a: any, b: any) => (b.settled ?? 0) - (a.settled ?? 0)
      || String(a.model_code).localeCompare(b.model_code)))
</script>

<style scoped>
.baseline-row td { opacity: 0.7; font-style: italic; }
</style>
