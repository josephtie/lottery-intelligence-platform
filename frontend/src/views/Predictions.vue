<template>
  <h2 class="page-title">🔮 Prédictions</h2>
  <div class="filters">
    <input type="date" v-model="day" @change="load" title="Date du tirage cible" />
    <input type="date" v-model="from" @change="load" title="Du" />
    <input type="date" v-model="to" @change="load" title="Au" />
    <select v-model="status" @change="load">
      <option value="">Tous statuts</option>
      <option>PENDING</option><option>LOCKED</option>
      <option>SCORED</option><option>INVALID</option>
    </select>
    <button @click="reset">Réinitialiser</button>
    <button @click="load" :disabled="loading">{{ loading ? '…' : 'Rafraîchir' }}</button>
    <span class="sub">{{ rows.length }} prédictions — données strictement prospectives</span>
  </div>
  <div v-if="err" class="panel"><span class="badge-err">{{ err }}</span></div>

  <div class="legend">
    <span class="num-ball turbo-ball">2</span> numéros Turbo prédits (scellés avant le tirage)
    &nbsp;·&nbsp;
    <span class="num-ball actual">5</span> numéros gagnants officiels (positions 1→5)
    &nbsp;·&nbsp;cerclé vert = numéro touché
  </div>

  <div class="panel">
    <table class="data mb0">
      <tr><th>Date cible</th><th>Type</th><th>Modèle</th><th>Statut</th>
          <th>Turbo prédits</th><th>Gagnants (5)</th><th>Hits</th><th>Mise</th><th>Scellée</th></tr>
      <tr v-for="p in rows" :key="p.prediction_id">
        <td class="mono">{{ p.scheduled_date }}</td>
        <td>{{ p.draw_type }}</td>
        <td class="mono">{{ p.model_code }}</td>
        <td><span :class="badge(p.status)">{{ p.status }}</span></td>
        <td><span v-for="n in p.predicted_numbers" :key="n" class="num-ball turbo-ball"
                  :class="{ hit: p.winning_numbers?.includes(n) }">{{ n }}</span></td>
        <td><template v-if="p.winning_numbers">
              <span v-for="(n, i) in p.winning_numbers" :key="i" class="num-ball actual"
                    :title="'position ' + (i + 1)">{{ n }}</span>
            </template><span v-else class="sub">en attente</span></td>
        <td class="mono" :class="p.hit_count > 0 ? 'badge-ok' : ''">
          {{ p.hit_count != null ? p.hit_count + '/' + p.predicted_numbers.length : '—' }}</td>
        <td class="mono">{{ p.stake }}</td>
        <td class="mono">{{ fmt(p.created_at) }}</td>
      </tr>
    </table>
    <div v-if="!rows.length && !loading" class="sub">Aucune prédiction pour ce filtre.</div>
  </div>

  <div class="panel" v-if="outcomes?.length">
    <h3>Résultats évalués (REALIZED)</h3>
    <table class="data mb0">
      <tr><th>Date</th><th>Type</th><th>Modèle</th><th>Hits</th><th>Turbo</th><th>Soldée</th></tr>
      <tr v-for="o in outcomes.slice(0, 30)" :key="o.outcome_id">
        <td class="mono">{{ o.scheduled_date }}</td>
        <td>{{ o.draw_type }}</td>
        <td class="mono">{{ o.model_code }}</td>
        <td>{{ o.hit_count }}</td>
        <td class="mono">{{ turbo(o) }}</td>
        <td class="mono">{{ fmt(o.settled_at) }}</td>
      </tr>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'
import { useFetch, needsToken } from '../useFetch'

const status = ref('')
const day = ref('')
const from = ref('')
const to = ref('')
const rows = ref<any[]>([]); const loading = ref(false); const err = ref('')
const { data: outcomes } = useFetch<any[]>('/api/outcomes')

async function load() {
  loading.value = true; err.value = ''
  try {
    const res = await api.get('/api/predictions', { params: {
      status: status.value || undefined,
      date: day.value || undefined,
      from: from.value || undefined,
      to: to.value || undefined,
      limit: 500,
    }})
    rows.value = res.data.predictions ?? res.data.data ?? []
  } catch (e: any) {
    if (e.response?.status === 401) { localStorage.setItem('lottery_auth_required', '1'); needsToken.value = true }
    err.value = e.response?.data?.error || e.message
  } finally { loading.value = false }
}
function reset() { day.value = from.value = to.value = status.value = ''; load() }
onMounted(load)
function badge(s: string) {
  return s === 'SCORED' ? 'badge-ok' : s === 'INVALID' ? 'badge-err' : 'badge-warn'
}
function fmt(s?: string) { return s ? s.replace('T', ' ').slice(0, 16) : '—' }
function turbo(o: any) {
  if (!o.turbo) return '—'
  return Object.entries(o.turbo).map(([k, v]: any) => `${k}:${v.hits ?? 0}`).join(' ')
}
</script>

<style scoped>
.legend { color: var(--muted); font-size: 12px; margin-bottom: 12px; }
.turbo-ball {
  background: var(--gold); color: #111;
  border: 2px solid var(--gold-soft);
  box-shadow: 0 0 0 2px var(--bg);
}
.turbo-ball.hit { border-color: var(--green); box-shadow: 0 0 0 2px var(--green); }
</style>
