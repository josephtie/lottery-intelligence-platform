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
      <h3>🎯 Coverage Laboratory (M10)</h3>
      <div class="sub" style="margin-bottom:10px">
        Portefeuille optimisé (tickets mutuellement disjoints d'abord, puis
        recyclage à overlap minimal) comparé à des portefeuilles aléatoires
        équivalents. Règle de payout lue depuis le catalogue versionné
        (<code>{{ cov?.payout_rule?.code || 'turbo_fixed_odds' }}</code>).
      </div>
      <div class="filters">
        <label>Budget FCFA <input type="number" v-model.number="budget" min="100" step="100" /></label>
        <label>Mise <input type="number" v-model.number="covStake" min="25" step="25" /></label>
        <label>Pick size
          <select v-model.number="pickSize"><option :value="1">1</option><option :value="2">2</option><option :value="5">5</option></select></label>
        <label>Variante
          <select v-model="variant">
            <option value="turbo_2">Turbo 2</option><option value="turbo_3">Turbo 3</option>
            <option value="turbo_4">Turbo 4</option><option value="turbo_5">Turbo 5</option>
          </select></label>
        <label>Seed <input type="number" v-model.number="covSeed" min="0" /></label>
        <button class="tab" @click="loadCov">Optimiser</button>
      </div>
      <div v-if="covError" class="badge-err">{{ covError }}</div>
      <template v-else-if="cov">
        <div class="sub" style="margin-bottom:8px">
          Règle : <b>{{ cov.payout_rule.version }}</b>
          ({{ cov.payout_rule.verification_status }}) · ×{{ cov.payout_rule.payout_multiplier }} ·
          {{ cov.tickets }} tickets × {{ cov.stake_unit }} FCFA = {{ cov.stake_total }} FCFA
          <template v-if="cov.remainder_fcfa">· reste {{ cov.remainder_fcfa }} FCFA non alloué</template>
        </div>
        <table class="data mb0" style="max-width:720px">
          <tr><th></th><th>OPTIMISÉ</th><th>RANDOM (moyenne)</th></tr>
          <tr><td>Numéros couverts</td><td>{{ cov.optimized.metrics.distinct_numbers }}/90</td>
              <td>{{ cov.random_baseline.distinct_numbers_mean.toFixed(1) }}</td></tr>
          <tr><td>Paires couvertes</td><td>{{ cov.optimized.metrics.distinct_pairs }}</td>
              <td>{{ cov.random_baseline.distinct_pairs_mean.toFixed(1) }} (max {{ cov.random_baseline.distinct_pairs_max }})</td></tr>
          <tr><td>Overlap paires / ticket</td><td>{{ cov.optimized.metrics.pair_overlap_mean.toFixed(3) }}</td>
              <td>{{ cov.random_baseline.pair_overlap_mean.toFixed(3) }}</td></tr>
          <tr><td>Écart-type apparitions</td><td>{{ cov.optimized.metrics.appearances_stdev.toFixed(3) }}</td>
              <td>{{ cov.random_baseline.appearances_stdev_mean.toFixed(3) }}</td></tr>
          <tr><td>P(≥1 gain)</td>
              <td>{{ (cov.optimized.probability_at_least_one_win.value * 100).toFixed(2) }} %
                  <span class="sub">{{ probMethod(cov.optimized.probability_at_least_one_win) }}</span></td>
              <td>{{ (cov.random_baseline.p_at_least_one_mean * 100).toFixed(2) }} % (max {{ (cov.random_baseline.p_at_least_one_max * 100).toFixed(2) }} %)</td></tr>
          <tr><td>EV portefeuille</td><td class="err">{{ fmt(cov.optimized.economics.ev_portfolio) }} FCFA</td>
              <td>identique (EV = n × EV ticket)</td></tr>
          <tr><td>RTP</td><td>{{ (cov.optimized.economics.rtp * 100).toFixed(1) }} %</td><td>identique</td></tr>
          <tr><td>Perte attendue</td><td class="err">{{ fmt(cov.optimized.economics.expected_loss) }} FCFA</td><td>identique</td></tr>
        </table>
        <div class="sub" style="margin-top:8px; max-width:720px">{{ cov.disclaimer }}</div>
        <div class="balls" style="margin-top:10px">
          <span v-for="(t, i) in cov.optimized.portfolio" :key="i" class="ticket">
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
const budget = ref(2000); const covStake = ref(100); const pickSize = ref(2)
const covSeed = ref(0)
const cov = ref<any>(null); const covError = ref('')

function fmt(x?: number) { return x == null ? '—' : Math.round(x).toLocaleString() }
function probMethod(p: any) {
  if (!p) return ''
  return p.method === 'EXACT' ? 'EXACT'
    : `MONTE_CARLO — ${p.mc_sims} sims — seed ${p.mc_seed}` +
      (p.ci95_wilson ? ` · IC95 [${(p.ci95_wilson[0]*100).toFixed(2)}–${(p.ci95_wilson[1]*100).toFixed(2)} %]` : '')
}

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
    const res = await api.get('/api/lab/coverage', { params: {
      budget: budget.value, stake: covStake.value, pick_size: pickSize.value,
      variant: variant.value, seed: covSeed.value } })
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
