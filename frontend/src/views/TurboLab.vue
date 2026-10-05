<template>
  <h2 class="page-title">🧪 Turbo Laboratory</h2>
  <div class="sub" style="margin-bottom:12px">
    Évaluation <b>prospective</b> — prédictions scellées avant le tirage officiel.
    Montants calculés par le moteur de règlement selon les règles versionnées ;
    <b>aucune mise réelle n'a été engagée ni encaissée</b>.
  </div>
  <div v-if="errSum || errVar" class="panel"><span class="badge-err">{{ errSum || errVar }}</span></div>

  <!-- A. Synthèse financière -->
  <div class="cards" v-if="sum">
    <div class="card"><div class="label">Mises cumulées</div>
      <div class="value">{{ fcfa(sum.total_stake) }}</div>
      <div class="sub">{{ sum.evaluated }} prédictions évaluées · {{ sum.draws }} tirages</div></div>
    <div class="card"><div class="label">Gains bruts</div>
      <div class="value">{{ fcfa(sum.gross_payout) }}</div>
      <div class="sub">règle Turbo 2 officielle</div></div>
    <div class="card"><div class="label">Résultat net</div>
      <div class="value" :class="sum.net >= 0 ? 'green' : 'red'">{{ fcfa(sum.net) }}</div>
      <div class="sub">gains bruts − mises</div></div>
    <div class="card"><div class="label">ROI réalisé</div>
      <div class="value" :class="(sum.net / sum.total_stake) >= 0 ? 'green' : 'red'">
        {{ sum.total_stake > 0 ? ((sum.net / sum.total_stake) * 100).toFixed(1) + ' %' : 'n/c' }}</div>
      <div class="sub">net cumulé / mises cumulées</div></div>
  </div>
  <div class="panel" v-if="sum && sum.evaluated < 30">
    <span class="badge-warn">⚠ Échantillon faible ({{ sum.evaluated }} évaluations) — aucune conclusion statistique possible.</span>
  </div>

  <!-- B. Prédictions du prochain tirage -->
  <div class="panel">
    <h3>Prochains tirages — prédictions scellées</h3>
    <div class="filters">
      <select v-model="nextType"><option value="">Tous les types</option>
        <option v-for="t in nextTypes" :key="t" :value="t">{{ t }}</option></select>
    </div>
    <table class="data mb0" v-if="nextFiltered.length">
      <tr><th>Date</th><th>Type</th><th>Modèle</th><th>Numéros (rangs)</th><th>Statut</th><th>Scellée</th></tr>
      <tr v-for="p in nextFiltered" :key="p.prediction_id">
        <td class="mono">{{ p.scheduled_date }}</td>
        <td>{{ p.draw_type }}</td>
        <td class="mono">{{ p.model_code }} <span class="sub">v{{ p.model_version }}</span></td>
        <td><span v-for="(n, i) in p.predicted_numbers" :key="i" class="num-ball"
              :title="'rang ' + (i + 1)">{{ n }}</span></td>
        <td><span :class="p.status === 'LOCKED' ? 'badge-ok' : 'badge-warn'">{{ p.status }}</span></td>
        <td class="mono">{{ fmt(p.created_at) }}</td>
      </tr>
    </table>
    <div v-else class="sub">Aucune prédiction en vol.</div>
  </div>

  <!-- C. Tableau des performances Turbo -->
  <div class="panel">
    <h3>Performances par variante Turbo</h3>
    <table class="data mb0" v-if="variants?.length">
      <tr><th>Indicateur</th><th v-for="v in variants" :key="v.variant">{{ label(v.variant) }}</th></tr>
      <tr><td>Cote enregistrée</td><td v-for="v in variants" :key="v.variant" class="mono">{{ v.multiplier }}</td></tr>
      <tr><td>Paris évalués</td><td v-for="v in variants" :key="v.variant">{{ v.bets }}</td></tr>
      <tr><td>Gains</td><td v-for="v in variants" :key="v.variant">{{ v.wins }}</td></tr>
      <tr><td>Taux de réussite</td>
          <td v-for="v in variants" :key="v.variant" class="mono">{{ v.bets ? (v.wins / v.bets * 100).toFixed(1) + ' %' : 'n/c' }}</td></tr>
      <tr><td>Total des mises</td><td v-for="v in variants" :key="v.variant" class="mono">{{ fcfa(v.total_stake) }}</td></tr>
      <tr><td>Gains bruts</td><td v-for="v in variants" :key="v.variant" class="mono">{{ fcfa(v.gross_payout) }}</td></tr>
      <tr><td>Résultat net</td>
          <td v-for="v in variants" :key="v.variant" class="mono"
              :class="v.net >= 0 ? 'badge-ok' : 'badge-err'">{{ fcfa(v.net) }}</td></tr>
      <tr><td>ROI cumulé</td>
          <td v-for="v in variants" :key="v.variant" class="mono">{{ v.roi == null ? 'n/c' : (v.roi * 100).toFixed(1) + ' %' }}</td></tr>
    </table>
  </div>

  <!-- D. Comparaison modèles vs modèle nul -->
  <div class="panel">
    <h3>Modèles vs modèle nul — mêmes tirages évalués</h3>
    <table class="data mb0" v-if="modelRows.length">
      <tr><th>Modèle</th><th>Variante</th><th>Paris</th><th>Gains</th><th>Taux</th><th>Mises</th><th>Net</th><th>ROI</th></tr>
      <tr v-for="m in modelRows" :key="m.model_code + m.variant"
          :class="{ 'baseline-row': m.model_code === 'null_model_benchmark' }">
        <td class="mono">{{ m.model_code }}</td><td>{{ label(m.variant) }}</td>
        <td>{{ m.bets }}</td><td>{{ m.wins }}</td>
        <td class="mono">{{ m.bets ? (m.wins / m.bets * 100).toFixed(1) + ' %' : 'n/c' }}</td>
        <td class="mono">{{ fcfa(m.total_stake) }}</td>
        <td class="mono" :class="m.net >= 0 ? 'badge-ok' : 'badge-err'">{{ fcfa(m.net) }}</td>
        <td class="mono">{{ m.roi == null ? 'n/c' : (m.roi * 100).toFixed(1) + ' %' }}</td>
      </tr>
    </table>
    <div v-else class="sub">Pas encore assez de résultats pour comparer.</div>
  </div>

  <!-- D2. Replay walk-forward -->
  <ReplayLab />

  <!-- E. Résultats par tirage + export CSV -->
  <div class="panel">
    <h3 style="display:flex;justify-content:space-between;align-items:center">
      <span>Résultats par tirage</span>
      <button class="csv-btn" @click="exportCsv" :disabled="!resFiltered.length">Export CSV</button>
    </h3>
    <div class="filters">
      <select v-model="resModel"><option value="">Tous modèles</option>
        <option v-for="m in resModels" :key="m" :value="m">{{ m }}</option></select>
      <select v-model="resVariant"><option value="">Toutes variantes</option>
        <option>turbo_2</option><option>turbo_3</option><option>turbo_4</option><option>turbo_5</option></select>
    </div>
    <table class="data mb0" v-if="resFiltered.length">
      <tr><th>Date</th><th>Type</th><th>Modèle</th><th>Prédit</th><th>Officiel</th><th>Hits pos.</th>
          <th v-for="v in turboCols" :key="v">{{ label(v) }}</th><th>Soldée</th></tr>
      <tr v-for="r in resFiltered" :key="r.outcome_id">
        <td class="mono">{{ r.scheduled_date }}</td>
        <td>{{ r.draw_type }}</td>
        <td class="mono">{{ r.model_code }}</td>
        <td><span v-for="(n, i) in r.predicted_numbers" :key="i" class="num-ball">{{ n }}</span></td>
        <td><span v-for="(n, i) in r.winning_numbers" :key="i" class="num-ball actual">{{ n }}</span></td>
        <td class="mono">{{ JSON.stringify(r.positional_hits) }}</td>
        <td v-for="v in turboCols" :key="v" class="mono" style="font-size:11px">
          <template v-if="r.turbo?.[v]">
            <span :class="r.turbo[v].hit ? 'badge-ok' : 'badge-err'">{{ r.turbo[v].hit ? 'WIN' : '—' }}</span>
            {{ fcfa(r.turbo[v].net) }}
          </template>
          <template v-else>—</template>
        </td>
        <td class="mono">{{ fmt(r.settled_at) }}</td>
      </tr>
    </table>
    <div v-else class="sub">Aucun résultat évalué.</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useFetch } from '../useFetch'
import ReplayLab from '../components/ReplayLab.vue'

const { data: sum, error: errSum } = useFetch<any>('/api/turbo/summary')
const { data: variants, error: errVar } = useFetch<any[]>('/api/turbo/variants')
const { data: next } = useFetch<any[]>('/api/turbo/next')
const { data: models } = useFetch<any[]>('/api/turbo/models')
const { data: results } = useFetch<any[]>('/api/turbo/results')

const turboCols = ['turbo_2', 'turbo_3', 'turbo_4', 'turbo_5']
const nextType = ref(''); const resModel = ref(''); const resVariant = ref('')

const nextTypes = computed(() => [...new Set((next.value ?? []).map(p => p.draw_type))].sort())
const nextFiltered = computed(() => (next.value ?? []).filter(p => !nextType.value || p.draw_type === nextType.value))

const resModels = computed(() => [...new Set((results.value ?? []).map(r => r.model_code))].sort())
const resFiltered = computed(() => (results.value ?? []).filter(r =>
  (!resModel.value || r.model_code === resModel.value) &&
  (!resVariant.value || r.turbo?.[resVariant.value])))

const modelRows = computed(() => {
  const rows = models.value ?? []
  if (!resVariant.value) return rows
  return rows.filter(m => m.variant === resVariant.value)
})

function label(v: string) { return v.replace('turbo_', 'Turbo ') }
function fcfa(x?: number | null) {
  if (x == null) return 'n/c'
  return Math.round(x).toLocaleString('fr-FR') + ' FCFA'
}
function fmt(s?: string) { return s ? s.replace('T', ' ').slice(0, 16) : '—' }

function exportCsv() {
  const rows = resFiltered.value
  const head = ['date', 'draw_type', 'model', 'predicted', 'winning', 'hit_count',
                ...turboCols.map(v => `${v}_hit`), ...turboCols.map(v => `${v}_net`), 'settled_at']
  const lines = [head.join(';')]
  for (const r of rows) {
    lines.push([
      r.scheduled_date, r.draw_type, r.model_code,
      (r.predicted_numbers ?? []).join('-'), (r.winning_numbers ?? []).join('-'), r.hit_count,
      ...turboCols.map(v => r.turbo?.[v] ? (r.turbo[v].hit ? 1 : 0) : ''),
      ...turboCols.map(v => r.turbo?.[v]?.net ?? ''),
      r.settled_at,
    ].join(';'))
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `turbo_results_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}
</script>

<style scoped>
.baseline-row td { opacity: 0.7; font-style: italic; }
.csv-btn {
  background: var(--gold); color: #111; border: none; border-radius: 5px;
  padding: 6px 14px; font-weight: 700; cursor: pointer; font-size: 12px;
}
.csv-btn:disabled { opacity: 0.4; cursor: default; }
</style>
