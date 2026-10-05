<template>
  <h2 class="page-title">🎲 Tirages</h2>
  <div class="filters">
    <select v-model="type"><option value="">Tous les types</option>
      <option v-for="t in types" :key="t" :value="t">{{ t }}</option></select>
    <select v-model="status"><option value="">Tous statuts</option>
      <option>SETTLED</option><option>FROZEN</option><option>EXPECTED</option></select>
    <input type="date" v-model="day" />
    <span class="sub">{{ filtered.length }} / {{ draws?.length ?? 0 }} affichés</span>
  </div>
  <div v-if="err" class="panel"><span class="badge-err">{{ err }}</span></div>
  <div class="panel">
    <table class="data mb0">
      <tr><th>Date</th><th>Type</th><th>Statut</th><th>Validation</th><th>Gagnants</th></tr>
      <tr v-for="d in filtered" :key="d.draw_id">
        <td class="mono">{{ d.scheduled_date }}</td>
        <td>{{ d.draw_type }}</td>
        <td><span :class="d.status === 'SETTLED' ? 'badge-ok' : 'badge-warn'">{{ d.status }}</span></td>
        <td class="mono">{{ d.validation_status ?? '—' }}</td>
        <td><span v-for="n in (d.winning_numbers || [])" :key="n" class="num-ball">{{ n }}</span></td>
      </tr>
    </table>
    <div v-if="filtered.length === 0 && !loading" class="sub">Aucun tirage pour ces filtres.</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useFetch } from '../useFetch'

const { data: draws, loading, error: err } = useFetch<any[]>('/api/draws')
const type = ref(''); const status = ref(''); const day = ref('')
const types = computed(() => [...new Set((draws.value ?? []).map(d => d.draw_type))].sort())
const filtered = computed(() => (draws.value ?? []).filter(d =>
  (!type.value || d.draw_type === type.value) &&
  (!status.value || d.status === status.value) &&
  (!day.value || d.scheduled_date === day.value)))
</script>
