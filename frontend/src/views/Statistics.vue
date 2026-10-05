<template>
  <h2 class="page-title">📊 Statistiques par jeu</h2>
  <div class="sub" style="margin-bottom:12px">
    Fréquences réelles des numéros gagnants (versions VALID). Le test χ² mesure
    l'écart à une distribution uniforme — il ne prédit rien, il décrit.
  </div>

  <div class="panel">
    <div class="filters">
      <select v-model="drawType" @change="load">
        <option v-for="t in types" :key="t.code + t.display_name" :value="t.display_name">
          {{ t.display_name }} ({{ t.settled_draws }})</option>
      </select>
      <select v-model="days" @change="load">
        <option :value="30">30 derniers jours</option>
        <option :value="90">90 derniers jours</option>
        <option :value="365">1 an</option>
        <option :value="0">Tout l'historique</option>
      </select>
    </div>

    <div v-if="loading" class="sub">Chargement…</div>
    <div v-else-if="error" class="badge-err">{{ error }}</div>
    <template v-else-if="stats">
      <div class="cards" style="margin-bottom:14px">
        <div class="card"><div class="label">Tirages analysés</div>
          <div class="value">{{ stats.draw_count }}</div></div>
        <div class="card"><div class="label">Attendu / numéro</div>
          <div class="value">{{ stats.expected_per_number?.toFixed(1) }}</div></div>
        <div class="card"><div class="label">Test χ² uniformité</div>
          <div class="value" :class="stats.uniform ? 'green' : 'red'">
            {{ stats.p_value == null ? 'n/c' : 'p = ' + stats.p_value.toFixed(3) }}</div>
          <div class="sub">{{ stats.uniform ? 'compatible avec l\'uniforme' : 'écart significatif' }} · χ²={{ stats.chi_square?.toFixed(1) }} df=89</div></div>
        <div class="card"><div class="label">Plus grand retard</div>
          <div class="value gold">{{ stats.max_delay?.number }}</div>
          <div class="sub">{{ stats.max_delay?.delay }} tirages sans sortir · dernier {{ stats.max_delay?.last_date }}</div></div>
      </div>

      <div class="stat-grid">
        <div>
          <h3 class="sh">🔥 Chauds</h3>
          <div v-for="x in stats.hot" :key="'h'+x.number" class="stat-hbar">
            <span class="num-ball">{{ x.number }}</span>
            <div class="bar"><div class="fill" :style="{width: barw(x.count)}"></div></div>
            <span class="num">{{ x.count }}</span>
          </div>
        </div>
        <div>
          <h3 class="sh">🧊 Froids</h3>
          <div v-for="x in stats.cold" :key="'c'+x.number" class="stat-hbar">
            <span class="num-ball cold-ball">{{ x.number }}</span>
            <div class="bar"><div class="fill cold-fill" :style="{width: barw(x.count)}"></div></div>
            <span class="num">{{ x.count }}</span>
          </div>
        </div>
      </div>

      <h3 class="sh" style="margin-top:16px">Grille 1–90 (fréquence · retard en titre)</h3>
      <div class="grid90">
        <div v-for="x in stats.numbers" :key="x.number" class="cell"
             :class="cellClass(x)"
             :title="`n°${x.number} — ${x.count} sorties · retard ${x.delay} tirages · dernier ${x.last_date ?? 'jamais'}`">
          <span class="cn">{{ x.number }}</span>
          <span class="cc">{{ x.count }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const types = ref<any[]>([])
const drawType = ref('')
const days = ref(90)
const stats = ref<any>(null)
const loading = ref(false)
const error = ref('')

const maxCount = computed(() =>
  Math.max(1, ...(stats.value?.numbers ?? []).map((x: any) => x.count)))

function barw(c: number) { return (c / maxCount.value * 100).toFixed(1) + '%' }

function cellClass(x: any) {
  const r = maxCount.value ? x.count / maxCount.value : 0
  if (x.count === 0) return 'zero'
  if (r >= 0.75) return 'hot4'
  if (r >= 0.5) return 'hot3'
  if (r >= 0.25) return 'hot2'
  return 'hot1'
}

async function load() {
  if (!drawType.value) return
  loading.value = true; error.value = ''
  try {
    const res = await api.get('/api/statistics', {
      params: { draw_type: drawType.value, days: days.value } })
    if (res.data.error) { error.value = res.data.error; stats.value = null }
    else stats.value = res.data
  } catch (e: any) {
    error.value = e.response?.data?.error || e.message
    stats.value = null
  } finally { loading.value = false }
}

onMounted(async () => {
  try {
    const res = await api.get('/api/lab/draw-types')
    types.value = (res.data.data ?? []).filter((t: any) => t.settled_draws > 0)
    if (types.value.length) { drawType.value = types.value[0].display_name; await load() }
  } catch (e: any) { error.value = e.response?.data?.error || e.message }
})
</script>

<style scoped>
.sh { color: var(--gold); font-size: 13px; margin: 10px 0 8px; }
.stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
@media (max-width: 700px) { .stat-grid { grid-template-columns: 1fr; } }
.cold-ball { background: #4a6a8a; color: #fff; }
.cold-fill { background: #4a6a8a; }
.grid90 {
  display: grid; grid-template-columns: repeat(15, 1fr); gap: 4px;
}
@media (max-width: 900px) { .grid90 { grid-template-columns: repeat(10, 1fr); } }
@media (max-width: 600px) { .grid90 { grid-template-columns: repeat(6, 1fr); } }
.cell {
  display: flex; flex-direction: column; align-items: center;
  border-radius: 6px; padding: 4px 2px; font-size: 11px; cursor: default;
  border: 1px solid var(--border); background: var(--panel-2);
}
.cell .cn { font-weight: 700; }
.cell .cc { color: var(--muted); font-size: 10px; }
.cell.hot4 { background: var(--gold); color: #111; border-color: var(--gold); }
.cell.hot4 .cc { color: #333; }
.cell.hot3 { background: rgba(212,160,23,0.55); }
.cell.hot2 { background: rgba(212,160,23,0.28); }
.cell.hot1 { background: rgba(212,160,23,0.12); }
.cell.zero { opacity: 0.45; }
</style>
