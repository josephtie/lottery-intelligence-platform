<template>
  <h2 class="page-title">🎲 Tirages</h2>
  <div class="filters">
    <select v-model="type"><option value="">Tous les jeux</option>
      <option v-for="t in types" :key="t" :value="t">{{ t }}</option></select>
    <select v-model="status"><option value="">Tous statuts</option>
      <option>SETTLED</option><option>FROZEN</option><option>EXPECTED</option></select>
    <input type="date" v-model="day" placeholder="Date exacte" />
    <input type="date" v-model="dayFrom" placeholder="Du" />
    <input type="date" v-model="dayTo" placeholder="Au" />
    <span class="sub">{{ rows.length }} affichés <span v-if="rows.length >= limit">(limité — précise la date)</span></span>
  </div>
  <div v-if="err" class="panel"><span class="badge-err">{{ err }}</span></div>
  <div class="panel">
    <table class="data mb0">
      <tr><th>Date</th><th>Type</th><th>Statut</th><th>Validation</th><th>Gagnants</th></tr>
      <tr v-for="d in rows" :key="d.draw_id">
        <td class="mono">{{ d.scheduled_date }}</td>
        <td>{{ d.draw_type }}</td>
        <td><span :class="d.status === 'SETTLED' ? 'badge-ok' : 'badge-warn'">{{ d.status }}</span></td>
        <td class="mono">{{ d.validation_status ?? '—' }}</td>
        <td><span v-for="n in (d.winning_numbers || [])" :key="n" class="num-ball">{{ n }}</span></td>
      </tr>
    </table>
    <div v-if="!rows.length && !loading" class="sub">Aucun tirage pour ces filtres.</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import api from '../api'

const rows = ref<any[]>([])
const types = ref<string[]>([])
const loading = ref(false)
const err = ref('')
const type = ref(''); const status = ref('')
const day = ref(''); const dayFrom = ref(''); const dayTo = ref('')
// a specific day or a range raises the limit — the default 100 only
// covers ~2-3 days of draws at ~40 games/day
const limit = ref(100)

async function load() {
  loading.value = true; err.value = ''
  try {
    const params: any = { limit: limit.value }
    if (day.value) params.date = day.value
    if (dayFrom.value) params.from = dayFrom.value
    if (dayTo.value) params.to = dayTo.value
    if (type.value) params.type = type.value
    if (status.value) params.status = status.value
    const res = await api.get('/api/draws', { params })
    rows.value = res.data.data ?? res.data ?? []
  } catch (e: any) {
    err.value = e.response?.data?.error || e.message
  } finally { loading.value = false }
}

watch([day, dayFrom, dayTo, type, status], () => {
  limit.value = (day.value || dayFrom.value || dayTo.value || type.value) ? 2000 : 100
  load()
})

onMounted(async () => {
  load()
  try {
    const res = await api.get('/api/lab/draw-types')
    types.value = (res.data.data ?? res.data ?? []).map((t: any) => t.display_name)
  } catch { /* type list is convenience only */ }
})
</script>
