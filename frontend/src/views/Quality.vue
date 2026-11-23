<template>
  <h2 class="page-title">⚠️ Qualité des données</h2>

  <div class="cards" v-if="coll?.length">
    <div class="card"><div class="label">Succès de collecte (dernier jour)</div>
      <div class="value" :class="coll[0].success_rate >= 0.99 ? 'green' : 'red'">
        {{ (coll[0].success_rate * 100).toFixed(1) }}%</div>
      <div class="sub">{{ coll[0].succeeded }}/{{ coll[0].runs }} runs · {{ coll[0].day }}</div></div>
    <div class="card"><div class="label">Taux de doublons</div>
      <div class="value">{{ (coll[0].duplicate_rate * 100).toFixed(1) }}%</div>
      <div class="sub">re-collectes attendues — payloads identiques</div></div>
    <div class="card"><div class="label">Tirages à résultat manquant</div>
      <div class="value" :class="missingCount ? 'red' : 'green'">{{ missingCount }}</div>
      <div class="sub">EXPECTED passés sans résultat publié</div></div>
  </div>

  <div class="panel">
    <h3>Anomalies par type de tirage</h3>
    <table class="data mb0" v-if="summary?.length">
      <tr><th>Type</th><th>Tirages</th><th>Manquants</th><th>Mauvais compte</th><th>Doublon</th><th>Hors plage</th><th>Anormaux</th></tr>
      <tr v-for="q in summary" :key="q.draw_type" :class="{ 'warn-row': q.anomalous > 0 }">
        <td>{{ q.draw_type }}</td><td>{{ q.draws }}</td>
        <td>{{ q.missing_result }}</td><td>{{ q.wrong_count }}</td>
        <td>{{ q.duplicate_number }}</td><td>{{ q.number_out_of_range }}</td>
        <td><span :class="q.anomalous ? 'badge-err' : 'badge-ok'">{{ q.anomalous }}</span></td>
      </tr>
    </table>
  </div>

  <div class="panel" v-if="anomalies?.length">
    <h3>Dernières anomalies ({{ anomalies.length }})</h3>
    <table class="data mb0">
      <tr><th>Date</th><th>Type</th><th>Statut</th><th>Flags</th></tr>
      <tr v-for="a in anomalies.slice(0, 25)" :key="a.draw_type + a.scheduled_date">
        <td class="mono">{{ a.scheduled_date }}</td><td>{{ a.draw_type }}</td>
        <td class="mono">{{ a.draw_status }}</td>
        <td class="mono" style="font-size:11px">{{ flags(a) }}</td>
      </tr>
    </table>
  </div>

  <div class="panel" v-if="coll?.length">
    <h3>Collecte par jour</h3>
    <table class="data mb0">
      <tr><th>Jour</th><th>Source</th><th>Runs</th><th>Réussis</th><th>Échoués</th><th>Succès</th><th>Doublons</th></tr>
      <tr v-for="c in coll.slice(0, 14)" :key="c.source + c.day">
        <td class="mono">{{ c.day }}</td><td class="mono">{{ c.source }}</td>
        <td>{{ c.runs }}</td><td>{{ c.succeeded }}</td><td>{{ c.failed }}</td>
        <td class="mono">{{ (c.success_rate * 100).toFixed(1) }}%</td>
        <td class="mono">{{ (c.duplicate_rate * 100).toFixed(1) }}%</td>
      </tr>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useFetch } from '../useFetch'
const { data: summary } = useFetch<any[]>('/api/quality')
const { data: anomalies } = useFetch<any[]>('/api/quality/anomalies')
const { data: coll } = useFetch<any[]>('/api/quality/collection')
const missingCount = computed(() =>
  (anomalies.value ?? []).filter(a => a.missing_result).length)
function flags(a: any) {
  return ['missing_result', 'wrong_count', 'duplicate_number', 'number_out_of_range']
    .filter(k => a[k]).join(', ')
}
</script>

<style scoped>
.warn-row td { background: rgba(224,154,63,0.06); }
</style>
