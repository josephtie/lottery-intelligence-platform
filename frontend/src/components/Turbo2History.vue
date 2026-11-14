<template>
  <div>
    <div v-if="loading" class="sub">Chargement de l'historique Turbo 2…</div>
    <div v-else-if="err" class="badge-err">{{ err }}</div>
    <template v-else-if="data && !data.error">

      <div class="t2-head">
        <h3>🎯 {{ data.game.toUpperCase() }} — Historique Turbo 2</h3>
        <div class="sub">
          Règle scellée : {{ data.rule.definition }} · mise {{ fmt(data.rule.stake) }} · ×{{ data.rule.multiplier }}
          → +239 900 FCFA si HIT. Lecture des verdicts scellés — aucune donnée recalculée.
        </div>
      </div>

      <div v-if="!data.rows.length" class="sub" style="margin:14px 0">
        Aucun résultat Turbo 2 scellé pour ce jeu pour l'instant.
        Les paris prospectifs sont enregistrés avant les tirages et soldés à leur publication.
      </div>

      <template v-else>
        <!-- Filtres -->
        <div class="filters">
          <select v-model="fWeek" class="mini">
            <option value="">Toutes les semaines</option>
            <option v-for="w in data.weeks" :key="w" :value="w">{{ w }}</option>
          </select>
          <select v-model="fDow" class="mini">
            <option :value="-1">Tous les jours</option>
            <option v-for="(d,i) in DAYS" :key="i" :value="i">{{ d }}</option>
          </select>
          <select v-model="fModel" class="mini">
            <option value="">Tous les modèles</option>
            <option v-for="m in data.models" :key="m.model" :value="m.model">{{ m.model }}</option>
          </select>
        </div>

        <!-- KPI cards (recomputed on the filtered subset) -->
        <div class="syngrid">
          <div class="syn"><div class="sv">{{ nDraws }}</div><div class="sl">tirages</div></div>
          <div class="syn"><div class="sv">{{ kpi.bets }}</div><div class="sl">paris virtuels</div></div>
          <div class="syn"><div class="sv" :class="kpi.hits ? 'ok' : ''">{{ kpi.hits }}</div><div class="sl">hits Turbo 2</div></div>
          <div class="syn"><div class="sv">{{ kpi.hit_rate == null ? 'N/A' : (kpi.hit_rate*100).toFixed(1)+' %' }}</div><div class="sl">taux de réussite</div></div>
          <div class="syn"><div class="sv">{{ fmt(kpi.total_stake) }}</div><div class="sl">mise totale</div></div>
          <div class="syn"><div class="sv">{{ fmt(kpi.gross) }}</div><div class="sl">gain brut</div></div>
          <div class="syn"><div class="sv" :class="kpi.net > 0 ? 'ok' : 'neg'">{{ signed(kpi.net) }}</div><div class="sl">résultat net</div></div>
          <div class="syn"><div class="sv" :class="kpi.roi > 0 ? 'ok' : 'neg'">{{ kpi.roi == null ? 'N/A' : (kpi.roi*100).toFixed(0)+' %' }}</div><div class="sl">ROI</div></div>
        </div>
        <div class="sub" style="margin-bottom:10px">Courbe descriptive du net cumulé — pas une preuve de rentabilité future.</div>

        <!-- Cumulative net sparkline -->
        <div class="cumwrap" v-if="filtered.length">
          <svg :viewBox="`0 0 ${W} ${H}`" class="cum" preserveAspectRatio="none">
            <line :x1="0" :y1="zeroY" :x2="W" :y2="zeroY" class="zero" />
            <polyline :points="cumPoints" class="line" :class="{negline: cumEnd < 0}" />
          </svg>
          <div class="cum-legend mono">{{ cumStart }} → {{ cumEndFmt }} ({{ filtered.length }} paris)</div>
        </div>

        <!-- Main table -->
        <h4 style="margin-top:14px">Tirages — détail</h4>
        <div class="scrollbox tall">
          <table class="data mb0">
            <tr><th>Jour</th><th>Date</th><th>Tirage</th><th>Modèle</th><th>Prédiction</th>
                <th>2 premières positions réelles</th><th>Hits</th><th>Turbo 2</th>
                <th>Mise</th><th>Brut</th><th>Net</th><th>Net cumulé</th></tr>
            <tr v-for="r in displayRows" :key="r.outcome_id">
              <td>{{ DAYS[r.weekday] }}</td>
              <td class="mono">{{ r.date.slice(5) }}</td>
              <td class="mono">#{{ r.sequence }}</td>
              <td class="mono" style="font-size:11px">{{ r.model }}</td>
              <td><span v-for="n in r.predicted" :key="n" class="num-ball sm-ball">{{ n }}</span></td>
              <td>
                <span v-for="(n, i) in r.winning" :key="i"
                      class="num-ball sm-ball"
                      :class="{ 'win-pos': i < 2 }">{{ n }}</span>
              </td>
              <td class="mono">{{ r.hits_first2 }}</td>
              <td><span class="badge" :class="r.turbo2_hit ? 'badge-ok' : 'badge-loss'">{{ r.turbo2_hit ? 'HIT' : 'LOSS' }}</span></td>
              <td class="mono">{{ fmt(r.stake) }}</td>
              <td class="mono">{{ fmt(r.gross) }}</td>
              <td class="mono" :class="r.net > 0 ? 'ok' : 'neg'">{{ signed(r.net) }}</td>
              <td class="mono" :class="r.cumNet > 0 ? 'ok' : 'neg'">{{ signed(r.cumNet) }}</td>
            </tr>
          </table>
        </div>

        <!-- Daily summary -->
        <h4 style="margin-top:16px">Vue par jour</h4>
        <div class="scrollbox">
          <table class="data mb0">
            <tr><th>Jour</th><th>Paris</th><th>Hits</th><th>Pertes</th><th>Mise</th><th>Brut</th><th>Net</th><th>ROI</th></tr>
            <tr v-for="d in dailyFiltered" :key="d.weekday">
              <td>{{ DAYS[d.weekday] }}</td>
              <td class="mono">{{ d.bets }}</td>
              <td class="mono">{{ d.hits }}</td>
              <td class="mono">{{ d.losses }}</td>
              <td class="mono">{{ fmt(d.total_stake) }}</td>
              <td class="mono">{{ fmt(d.gross) }}</td>
              <td class="mono" :class="d.net > 0 ? 'ok' : 'neg'">{{ signed(d.net) }}</td>
              <td class="mono">{{ d.roi == null ? 'N/A' : (d.roi*100).toFixed(0)+' %' }}</td>
            </tr>
          </table>
        </div>

        <!-- Weekly comparison -->
        <h4 style="margin-top:16px">Semaine → semaine</h4>
        <div class="scrollbox">
          <table class="data mb0">
            <tr><th>Semaine</th><th>Paris</th><th>Hits</th><th>Taux</th><th>Mise</th><th>Brut</th><th>Net</th><th>ROI</th></tr>
            <tr v-for="w in weeklyFiltered" :key="w.iso_week">
              <td class="mono">{{ w.iso_week }}</td>
              <td class="mono">{{ w.bets }}</td>
              <td class="mono">{{ w.hits }}</td>
              <td class="mono">{{ w.hit_rate == null ? '—' : (w.hit_rate*100).toFixed(1)+' %' }}</td>
              <td class="mono">{{ fmt(w.total_stake) }}</td>
              <td class="mono">{{ fmt(w.gross) }}</td>
              <td class="mono" :class="w.net > 0 ? 'ok' : 'neg'">{{ signed(w.net) }}</td>
              <td class="mono">{{ w.roi == null ? 'N/A' : (w.roi*100).toFixed(0)+' %' }}</td>
            </tr>
          </table>
        </div>

        <!-- Model comparison -->
        <h4 style="margin-top:16px">Performance Turbo 2 par modèle
          <span class="sub">— constance observée, jamais probabilité de gagner</span></h4>
        <div class="scrollbox">
          <table class="data mb0">
            <tr><th>Modèle</th><th>Paris</th><th>Hits</th><th>Hit rate</th><th>Mise</th><th>Net</th><th>ROI</th>
                <th>Série pertes</th><th>Meilleure série</th><th>Dernier hit</th><th></th></tr>
            <tr v-for="m in modelsFiltered" :key="m.model"
                :class="{ 'baseline-row': ['null_model_benchmark','random'].includes(m.model) }">
              <td class="mono">{{ m.model }}</td>
              <td class="mono">{{ m.bets }}</td>
              <td class="mono">{{ m.hits }}</td>
              <td class="mono">{{ m.hit_rate == null ? '—' : (m.hit_rate*100).toFixed(1)+' %' }}</td>
              <td class="mono">{{ fmt(m.total_stake) }}</td>
              <td class="mono" :class="m.net > 0 ? 'ok' : 'neg'">{{ signed(m.net) }}</td>
              <td class="mono">{{ m.roi == null ? 'N/A' : (m.roi*100).toFixed(0)+' %' }}</td>
              <td class="mono">{{ m.worst_loss_streak }}</td>
              <td class="mono">{{ m.best_hit_streak }}</td>
              <td class="mono">{{ m.last_hit_date ?? 'jamais' }}</td>
              <td><span v-if="m.sample_level === 'weak'" class="badge badge-warn">ÉCHANTILLON FAIBLE</span></td>
            </tr>
          </table>
        </div>

        <!-- Same weekday across weeks -->
        <h4 style="margin-top:16px">Même jour, semaines successives</h4>
        <div class="filters" style="margin-bottom:8px">
          <button v-for="(d, i) in DAYS" :key="i" class="tab sm"
                  :class="{ active: wd === i }" @click="wd = i">{{ d }}</button>
        </div>
        <div class="scrollbox">
          <table class="data mb0">
            <tr><th>Semaine</th><th>Date</th><th>Modèle</th><th>Prédiction</th>
                <th>Réel (2 premières pos.)</th><th>Hits</th><th>Turbo 2</th><th>Net</th></tr>
            <tr v-for="r in sameDay" :key="r.outcome_id">
              <td class="mono">{{ r.iso_week }}</td>
              <td class="mono">{{ r.date }}</td>
              <td class="mono" style="font-size:11px">{{ r.model }}</td>
              <td><span v-for="n in r.predicted" :key="n" class="num-ball sm-ball">{{ n }}</span></td>
              <td><span v-for="(n, i) in r.winning" :key="i" class="num-ball sm-ball"
                        :class="{ 'win-pos': i < 2 }">{{ n }}</span></td>
              <td class="mono">{{ r.hits_first2 }}</td>
              <td><span class="badge" :class="r.turbo2_hit ? 'badge-ok' : 'badge-loss'">{{ r.turbo2_hit ? 'HIT' : 'LOSS' }}</span></td>
              <td class="mono" :class="r.net > 0 ? 'ok' : 'neg'">{{ signed(r.net) }}</td>
            </tr>
            <tr v-if="!sameDay.length"><td colspan="8" class="sub">Aucun tirage un {{ DAYS[wd].toLowerCase() }} dans cet historique.</td></tr>
          </table>
        </div>
      </template>
    </template>
    <div v-else-if="data?.error" class="badge-warn">{{ data.error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import api from '../api'

const props = defineProps<{ game: string }>()
const DAYS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

const data = ref<any>(null)
const loading = ref(false)
const err = ref('')
const fWeek = ref('')
const fDow = ref(-1)
const fModel = ref('')
const wd = ref(0)

const fmt = (x?: number) => x == null ? '—'
  : Math.round(x).toLocaleString('fr-FR')
const signed = (x?: number) => x == null ? '—'
  : (x > 0 ? '+' : '') + Math.round(x).toLocaleString('fr-FR')

const filtered = computed(() => (data.value?.rows ?? []).filter((r: any) =>
  (!fWeek.value || r.iso_week === fWeek.value)
  && (fDow.value === -1 || r.weekday === fDow.value)
  && (!fModel.value || r.model === fModel.value)))

function aggregate(rows: any[]) {
  const bets = rows.length
  const hits = rows.filter(r => r.turbo2_hit).length
  const stake = rows.reduce((s, r) => s + r.stake, 0)
  const gross = rows.reduce((s, r) => s + r.gross, 0)
  const net = rows.reduce((s, r) => s + r.net, 0)
  return { bets, hits, losses: bets - hits,
           hit_rate: bets ? hits / bets : null,
           total_stake: stake, gross, net,
           roi: stake ? net / stake : null }
}
const kpi = computed(() => aggregate(filtered.value))
const nDraws = computed(() => new Set(filtered.value.map(r => r.date)).size)

const displayRows = computed(() => {
  let cum = 0
  return filtered.value.map(r => { cum += r.net; return { ...r, cumNet: cum } })
})

// aggregates restricted to the active filters (week applied to daily,
// day+model applied to weekly, week+day applied to models)
const dailyFiltered = computed(() => (data.value?.daily ?? [])
  .filter((d: any) => fDow.value === -1 || d.weekday === fDow.value)
  .map((d: any) => {
    if (!fWeek.value && !fModel.value) return d
    const rs = data.value.rows.filter((r: any) => r.weekday === d.weekday
      && (!fWeek.value || r.iso_week === fWeek.value)
      && (!fModel.value || r.model === fModel.value))
    return { weekday: d.weekday, ...aggregate(rs) }
  }))
const weeklyFiltered = computed(() => (data.value?.weekly ?? [])
  .map((w: any) => {
    if (!fWeek.value && fDow.value === -1 && !fModel.value) return w
    const rs = data.value.rows.filter((r: any) => r.iso_week === w.iso_week
      && (fDow.value === -1 || r.weekday === fDow.value)
      && (!fModel.value || r.model === fModel.value))
    return { iso_week: w.iso_week, ...aggregate(rs) }
  }))
const modelsFiltered = computed(() => (data.value?.models ?? [])
  .map((m: any) => {
    if (!fWeek.value && fDow.value === -1) return m
    const rs = data.value.rows.filter((r: any) => r.model === m.model
      && (!fWeek.value || r.iso_week === fWeek.value)
      && (fDow.value === -1 || r.weekday === fDow.value))
    return { ...m, ...aggregate(rs) }
  }))

const sameDay = computed(() => (data.value?.rows ?? [])
  .filter((r: any) => r.weekday === wd.value))

// ── cumulative chart ──
const W = 600, H = 90, PAD = 8
const cumValues = computed(() => {
  let cum = 0
  return filtered.value.map(r => (cum += r.net))
})
const cumStart = 0
const cumEnd = computed(() => cumValues.value.at(-1) ?? 0)
const cumEndFmt = computed(() => signed(cumEnd.value))
const zeroY = computed(() => {
  const vals = cumValues.value
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals)
  if (hi === lo) return H / 2
  return PAD + (hi / (hi - lo)) * (H - 2 * PAD)
})
const cumPoints = computed(() => {
  const vals = cumValues.value
  if (!vals.length) return ''
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals)
  const rng = hi - lo || 1
  return vals.map((v, i) =>
    `${(i / Math.max(1, vals.length - 1)) * W},${PAD + ((hi - v) / rng) * (H - 2 * PAD)}`
  ).join(' ')
})

async function load() {
  loading.value = true; err.value = ''
  try {
    const res = await api.get('/api/lab/turbo2-history', { params: { draw_type: props.game } })
    data.value = res.data
  } catch (e: any) {
    err.value = e.response?.data?.error || e.message
  } finally { loading.value = false }
}
watch(() => props.game, load, { immediate: true })
</script>

<style scoped>
.t2-head { margin-bottom: 12px; }
.filters { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.mini { font-size: 12.5px; padding: 5px 9px; background: var(--panel-2);
  color: var(--text); border: 1px solid var(--border); border-radius: 5px; }
.syngrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 8px; }
.syn { border: 1px solid var(--border); border-radius: 7px; padding: 8px 10px;
  background: var(--panel-2); }
.sv { font-size: 16px; font-weight: 800; }
.sl { font-size: 10px; color: var(--muted); text-transform: uppercase;
  letter-spacing: 0.4px; }
.ok { color: var(--green); }
.neg { color: #e07070; }
.scrollbox { max-height: 300px; overflow: auto; border: 1px solid var(--border);
  border-radius: 6px; }
.scrollbox.tall { max-height: 460px; }
.sm-ball { font-size: 10px; padding: 1px 5px; }
.win-pos { border-color: var(--gold); color: var(--gold); font-weight: 700; }
.badge { font-size: 10px; padding: 1px 7px; border-radius: 9px;
  border: 1px solid var(--border); color: var(--muted); }
.badge.badge-ok { color: var(--green); border-color: var(--green); }
.badge.badge-loss { color: #e07070; border-color: #5a3a3a; }
.badge.badge-warn { color: var(--gold); border-color: var(--gold); }
.baseline-row td { opacity: 0.6; font-style: italic; }
.cumwrap { border: 1px solid var(--border); border-radius: 6px;
  padding: 8px; background: var(--panel-2); margin-bottom: 4px; }
.cum { width: 100%; height: 90px; display: block; }
.cum .zero { stroke: var(--border); stroke-width: 1; }
.cum .line { fill: none; stroke: var(--green); stroke-width: 1.5; }
.cum .line.negline { stroke: #e07070; }
.cum-legend { font-size: 11px; color: var(--muted); margin-top: 4px; }
h4 { margin-bottom: 6px; }
.tab.sm { padding: 4px 12px; font-size: 12px; }
</style>
