<template>
  <div>
    <div class="panel">
      <h3>💰 Simulateur Monte-Carlo — bankroll Turbo (M08)</h3>
      <div class="sub" style="margin-bottom:10px">
        Chemins de bankroll sous hasard uniforme : toute sélection a la même
        espérance. Le curseur « lift » explore le scénario où un modèle
        surperformerait réellement le hasard — jamais démontré à ce jour.
      </div>
      <div class="filters">
        <label>Variante
          <select v-model="variant">
            <option :value="2">Turbo 2 (×2400)</option>
            <option :value="3">Turbo 3 (×800)</option>
            <option :value="4">Turbo 4 (×400)</option>
            <option :value="5">Turbo 5 (×240)</option>
          </select></label>
        <label>Paris <input type="number" v-model.number="draws" min="10" max="2000" /></label>
        <label>Bankroll <input type="number" v-model.number="bankroll" min="1000" step="1000" /></label>
        <label>Mise <input type="number" v-model.number="stake" min="50" step="50" /></label>
        <label>Lift <input type="number" v-model.number="lift" min="0.5" max="3" step="0.1" /></label>
        <button class="tab" @click="load">Simuler</button>
        <span v-if="loading" class="badge-warn">500 chemins…</span>
      </div>
      <div v-if="error" class="badge-err">{{ error }}</div>
      <template v-else-if="sim">
        <div class="cards">
          <div class="stat-card"><h4>Gain attendu / pari</h4>
            <div class="kpi err">{{ fmt(sim.expected_value_per_bet) }} FCFA</div>
            <div class="sub">retour théorique {{ (sim.expected_return_rate*100).toFixed(1) }} % · p(hit) {{ sim.hit_probability.toExponential(2) }}</div></div>
          <div class="stat-card"><h4>Ruin probability</h4>
            <div class="kpi" :class="sim.ruin_probability > 0.5 ? 'err' : 'warn'">{{ (sim.ruin_probability*100).toFixed(1) }} %</div>
            <div class="sub">bankroll {{ sim.initial_bankroll.toLocaleString() }} FCFA sur {{ sim.draws_per_path }} paris</div></div>
          <div class="stat-card"><h4>Bankroll finale</h4>
            <div class="kpi" :class="sim.final_equity.median < sim.initial_bankroll ? 'err' : 'ok'">
              {{ fmt(sim.final_equity.median) }} FCFA</div>
            <div class="sub">p5 {{ fmt(sim.final_equity.p05) }} · p95 {{ fmt(sim.final_equity.p95) }} · moyenne {{ fmt(sim.final_equity.mean) }}</div></div>
          <div class="stat-card"><h4>Pire série perdante (p95)</h4>
            <div class="kpi warn">{{ sim.longest_losing_streak.p95 }} paris</div>
            <div class="sub">médiane {{ sim.longest_losing_streak.median }} · drawdown p95 {{ fmt(sim.max_drawdown.p95) }} FCFA</div></div>
        </div>
      </template>
    </div>

    <div class="panel">
      <h3>🎯 Optimiseur de couverture (M10)</h3>
      <div class="sub" style="margin-bottom:10px">
        Portefeuille de grilles maximisant la couverture (numéros distincts
        répartis uniformément + paires distinctes), comparé à des portefeuilles
        aléatoires. La couverture répartit le risque — elle n'augmente pas la
        probabilité de gain.
      </div>
      <div class="filters">
        <label>Tickets <input type="number" v-model.number="tickets" min="1" max="500" /></label>
        <label>Taille grille
          <select v-model.number="pickSize"><option :value="2">2 numéros</option><option :value="5">5 numéros</option></select></label>
        <button class="tab" @click="loadCov">Optimiser</button>
      </div>
      <div v-if="covError" class="badge-err">{{ covError }}</div>
      <template v-else-if="cov">
        <table class="data mb0" style="max-width:640px">
          <tr><th></th><th>Portefeuille optimisé</th><th>Aléatoire (moy./max)</th></tr>
          <tr><td>Numéros distincts</td><td>{{ cov.metrics.distinct_numbers }}/90</td><td>—</td></tr>
          <tr><td>Paires distinctes</td><td>{{ cov.metrics.distinct_pairs }}</td>
              <td>{{ cov.random_baseline.distinct_pairs_mean.toFixed(1) }} / {{ cov.random_baseline.distinct_pairs_max }}</td></tr>
          <tr><td>Écart-type apparitions</td><td>{{ cov.metrics.appearances_stdev.toFixed(3) }}</td>
              <td>{{ cov.random_baseline.appearances_stdev_mean.toFixed(3) }}</td></tr>
          <tr><td>Apparitions min–max</td><td>{{ cov.metrics.appearances_min }}–{{ cov.metrics.appearances_max }}</td><td>—</td></tr>
        </table>
        <div class="balls" style="margin-top:10px">
          <span v-for="(t, i) in cov.portfolio" :key="i" class="ticket">
            <b v-for="n in t" :key="n" class="ball">{{ n }}</b>
          </span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'

const variant = ref(2); const draws = ref(200); const bankroll = ref(10000)
const stake = ref(100); const lift = ref(1.0)
const sim = ref<any>(null); const loading = ref(false); const error = ref('')
const tickets = ref(20); const pickSize = ref(2)
const cov = ref<any>(null); const covError = ref('')

function fmt(x?: number) { return x == null ? '—' : Math.round(x).toLocaleString() }

async function load() {
  loading.value = true; error.value = ''; sim.value = null
  try {
    const res = await api.get('/api/lab/simulation', { params: {
      variant: variant.value, draws: draws.value, bankroll: bankroll.value,
      stake: stake.value, lift: lift.value } })
    if (res.data.error) error.value = res.data.error
    else sim.value = res.data
  } catch (e: any) { error.value = e.response?.data?.error || e.message }
  finally { loading.value = false }
}

async function loadCov() {
  covError.value = ''; cov.value = null
  try {
    const res = await api.get('/api/lab/coverage', { params: { tickets: tickets.value, pick_size: pickSize.value } })
    if (res.data.error) covError.value = res.data.error
    else cov.value = res.data
  } catch (e: any) { covError.value = e.response?.data?.error || e.message }
}

onMounted(() => { load(); loadCov() })
</script>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.stat-card { background: var(--panel2); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.stat-card h4 { margin: 0 0 8px; font-size: 13px; }
.kpi { font-size: 16px; font-weight: 700; margin-bottom: 4px; }
.kpi.ok { color: var(--green); } .kpi.err { color: var(--red); } .kpi.warn { color: var(--gold); }
.filters { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; margin-bottom: 10px; }
.filters label { font-size: 12px; color: var(--muted); display: flex; flex-direction: column; gap: 4px; }
.filters input, .filters select { width: 110px; }
.balls { display: flex; flex-wrap: wrap; gap: 6px; }
.ticket { display: inline-flex; gap: 3px; padding: 2px 4px; border: 1px solid var(--border); border-radius: 6px; }
</style>
