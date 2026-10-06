<template>
  <div class="panel">
    <!-- ══════════ ÉCRAN 1 — CARTES DES JEUX ══════════ -->
    <template v-if="!game">
      <h3>🧠 PROFILS DES JEUX</h3>
      <div class="sub" style="margin-bottom:14px">
        Chaque jeu a sa propre fiche d'analyse — les modèles sont rejoués en
        walk-forward strict (jamais de donnée future) puis mesurés sur
        {{ cards?.card_window ?? 156 }} derniers tirages.
        Clique sur un jeu pour ouvrir son espace.
      </div>
      <div v-if="errCards" class="badge-err">{{ errCards }}</div>
      <div v-else-if="!cards" class="sub">
        Calcul des cartes en cours — un replay par jeu (première visite ~1 min)…
      </div>
      <div class="cardgrid" v-else>
        <div class="gamecard" v-for="c in cards.cards" :key="c.game">
          <div class="gc-title">{{ c.game.toUpperCase() }}</div>
          <template v-if="c.sample_level === 'insufficient'">
            <div class="gc-line sub">Échantillon insuffisant</div>
            <div class="gc-line mono">{{ c.settled_draws }} tirages suivis</div>
          </template>
          <template v-else>
            <div class="gc-line mono">{{ c.window_draws }} tirages analysés · {{ c.settled_draws }} au total</div>
            <div class="gc-line" v-if="c.dominant_model">
              ≥2 hits : <b>{{ c.dominant_model.ge2_pct }} %</b>
              · ≥3 : {{ c.dominant_model.ge3_pct }} %
            </div>
            <div class="gc-line" v-if="c.dominant_model">
              Modèle dominant : <b class="mono">{{ c.dominant_model.model }}</b>
            </div>
            <div class="gc-line" v-if="c.dominant_model">
              Constance : <b :class="stabClass(c.dominant_model.stability)">{{ stabLabel(c.dominant_model.stability) }}</b>
            </div>
            <div class="gc-line sub mono" style="font-size:11px">
              moy. hits (tous modèles) : {{ c.pooled_mean_hits }}
            </div>
          </template>
          <button class="btn-open" @click="open(c.game)">OUVRIR ▸</button>
        </div>
      </div>
    </template>

    <!-- ══════════ ÉCRAN 2 — FICHE D'UN JEU ══════════ -->
    <template v-else>
      <!-- Sélecteur de jeu -->
      <div class="gamenav">
        <button class="gn-back" @click="game = ''">◂ Tous les jeux</button>
        <button v-for="c in cards?.cards ?? []" :key="c.game"
                class="gn-chip" :class="{ on: c.game === game }"
                @click="open(c.game)">{{ c.game.toUpperCase() }}</button>
      </div>

      <div v-if="loading" class="sub" style="margin:14px 0">
        Replay walk-forward de {{ game }} en cours (~10-25 s)…
      </div>
      <div v-else-if="err" class="badge-err">{{ err }}</div>

      <template v-else-if="data && !data.error">
        <!-- Synthèse -->
        <h3>PROFIL {{ data.game.toUpperCase() }}</h3>
        <div class="syngrid">
          <div class="syn"><div class="sv">{{ data.n_replayed }}</div><div class="sl">tirages analysés</div></div>
          <div class="syn"><div class="sv">{{ period }}</div><div class="sl">période couverte</div></div>
          <div class="syn"><div class="sv">{{ topModel?.mean_hits ?? '—' }}</div><div class="sl">moy. hits (meilleur)</div></div>
          <div class="syn"><div class="sv">{{ topModel ? topModel.ge1_pct + ' %' : '—' }}</div><div class="sl">≥1 hit</div></div>
          <div class="syn"><div class="sv">{{ topModel ? topModel.ge2_pct + ' %' : '—' }}</div><div class="sl">≥2 hits</div></div>
          <div class="syn"><div class="sv">{{ topModel ? topModel.ge3_pct + ' %' : '—' }}</div><div class="sl">≥3 hits</div></div>
          <div class="syn"><div class="sv" style="font-size:13px">{{ mostStable?.name ?? '—' }}</div><div class="sl">le plus constant</div></div>
          <div class="syn"><div class="sv" style="font-size:13px">{{ topModel?.name ?? '—' }}</div><div class="sl">le plus performant</div></div>
          <div class="syn"><div class="sv" :class="stateClass">{{ stateLabel }}</div><div class="sl">état actuel</div></div>
        </div>
        <div class="sub" style="margin:6px 0 14px">
          Référence hasard : {{ data.null_reference.expected_mean_hits }} hits/tirage ·
          ≥1 = {{ data.null_reference.expected_ge1_pct }} % · ≥2 = {{ data.null_reference.expected_ge2_pct }} %.
          Ce profil est une observation historique, pas une prédiction.
        </div>

        <!-- SECTION 1 — modèles de ce jeu -->
        <h4>① Les modèles sur {{ data.game.toUpperCase() }}</h4>
        <div class="scrollbox">
          <table class="data mb0">
            <tr><th>Modèle</th><th>n</th><th>Moy.</th><th>Méd.</th><th>≥1</th><th>≥2</th><th>≥3</th>
                <th>Série max</th><th>Constance</th><th>Tendance</th><th>vs hasard</th></tr>
            <tr v-for="m in ranked" :key="m.name"
                :class="{ 'baseline-row': ['null_model_benchmark','random'].includes(m.name) }">
              <td class="mono">{{ m.name }}</td>
              <td class="mono">{{ m.n }}</td>
              <td class="mono">{{ m.mean_hits ?? '—' }}</td>
              <td class="mono">{{ m.median_hits ?? '—' }}</td>
              <td class="mono">{{ pct(m.ge1_pct) }}</td>
              <td class="mono">{{ pct(m.ge2_pct) }}</td>
              <td class="mono">{{ pct(m.ge3_pct) }}</td>
              <td class="mono">{{ m.best_ge1_streak ?? '—' }}</td>
              <td class="mono"><span class="badge" :class="stabClass(m.consistency?.stability)">{{ stabLabel(m.consistency?.stability) }}</span></td>
              <td class="mono">{{ trendLabel(m.trend) }}</td>
              <td class="mono" :title="vsNullTitle(m.vs_null)">{{ vsNull(m.vs_null) }}</td>
            </tr>
          </table>
        </div>

        <!-- SECTION 6 — constants -->
        <h4 style="margin-top:16px">② Modèles constants sur {{ data.game.toUpperCase() }}
          <span class="sub">— part des tirages avec ≥2 hits (n observations)</span></h4>
        <div class="podium">
          <div class="pod" v-for="(m, i) in constants" :key="m.name">
            <span class="pod-medal">{{ ['🥇','🥈','🥉'][i] }}</span>
            <b class="mono">{{ m.name }}</b>
            <span class="mono">{{ m.ge2_pct }} % des tirages ≥2 hits</span>
            <span class="sub mono" style="font-size:11px">n={{ m.n }} · moy {{ m.mean_hits }}</span>
          </div>
          <div v-if="!constants.length" class="sub">Données insuffisantes pour établir un classement.</div>
        </div>

        <!-- SECTION 5 — ligne de progression -->
        <h4 style="margin-top:16px">③ Progression hebdomadaire
          <span class="sub">— moyenne de hits par semaine ISO</span></h4>
        <div class="scrollbox">
          <table class="data mb0">
            <tr><th>Modèle</th>
                <th v-for="w in lastWeeks" :key="w" class="mono">{{ w }}</th>
                <th>Sens</th></tr>
            <tr v-for="name in progModels" :key="name"
                :class="{ 'baseline-row': ['null_model_benchmark','random'].includes(name) }">
              <td class="mono">{{ name }}</td>
              <td v-for="w in lastWeeks" :key="w" class="mono prog-cell">
                {{ progVal(name, w) }}</td>
              <td class="mono">{{ progArrow(name) }}</td>
            </tr>
          </table>
        </div>

        <!-- SECTION 3 — vue par semaine -->
        <h4 style="margin-top:16px">④ Historique par semaine — <span class="mono">{{ focusModel }}</span>
          <select v-model="focusModel" class="mini">
            <option v-for="n in data.model_names" :key="n" :value="n">{{ n }}</option>
          </select></h4>
        <div class="scrollbox">
          <table class="data mb0">
            <tr><th>Semaine</th><th>Tirages</th><th>Moy.hits</th><th>≥1</th><th>≥2</th><th>≥3</th><th></th></tr>
            <tr v-for="w in currentWeekly" :key="w.iso_week">
              <td class="mono">{{ w.iso_week }}</td>
              <td class="mono">{{ w.n }}</td>
              <td class="mono">{{ w.mean_hits }}</td>
              <td class="mono">{{ pct(w.ge1_pct) }}</td>
              <td class="mono">{{ pct(w.ge2_pct) }}</td>
              <td class="mono">{{ pct(w.ge3_pct) }}</td>
              <td><span class="wbar" :style="{ width: barWidth(w.mean_hits) }"></span></td>
            </tr>
          </table>
        </div>

        <!-- SECTION 4 — même jour de semaine -->
        <h4 style="margin-top:16px">⑤ Même jour, semaines successives</h4>
        <div class="filters" style="margin-bottom:8px">
          <button v-for="(d, i) in DAYS" :key="i" class="tab sm"
                  :class="{ active: wd === i }" @click="wd = i">{{ d }}</button>
        </div>
        <div class="scrollbox">
          <table class="data mb0">
            <tr><th>Date</th><th>Semaine</th><th>Résultat</th>
                <th v-for="n in data.model_names" :key="n" class="mono" style="font-size:10px">{{ shortName(n) }}</th></tr>
            <tr v-for="r in wdDraws" :key="r.date">
              <td class="mono">{{ r.date }}</td>
              <td class="mono">{{ r.iso_week }}</td>
              <td><span v-for="nb in r.winning" :key="nb" class="num-ball sm-ball">{{ nb }}</span></td>
              <td v-for="n in data.model_names" :key="n" class="mono"
                  :class="{ 'hit-cell': r.hits[n] >= 2 }">{{ r.hits[n] }}</td>
            </tr>
          </table>
        </div>

        <!-- SECTION 2 — historique des tirages -->
        <h4 style="margin-top:16px">⑥ Historique des tirages
          <span class="sub">— les {{ data.draws.length }} tirages rejoués (récents d'abord)</span></h4>
        <div class="scrollbox tall">
          <table class="data mb0">
            <tr><th>Date</th><th>Jour</th><th>Sem.</th><th>Résultat</th>
                <th v-for="n in data.model_names" :key="n" class="mono" style="font-size:10px">{{ shortName(n) }}</th></tr>
            <tr v-for="r in reversedDraws" :key="r.date">
              <td class="mono">{{ r.date }}</td>
              <td>{{ weekdayName(r.weekday) }}</td>
              <td class="mono">{{ r.iso_week }}</td>
              <td><span v-for="nb in r.winning" :key="nb" class="num-ball sm-ball">{{ nb }}</span></td>
              <td v-for="n in data.model_names" :key="n" class="mono"
                  :class="{ 'hit-cell': r.hits[n] >= 2 }">{{ r.hits[n] }}</td>
            </tr>
          </table>
        </div>

        <!-- Alertes -->
        <h4 style="margin-top:16px">⑦ Observations analytiques</h4>
        <ul class="sub" v-if="alerts.length">
          <li v-for="a in alerts" :key="a">{{ a }}</li>
        </ul>
        <div v-else class="sub">Aucun changement détecté · aucune dégradation ·
          échantillons suffisants.</div>
      </template>
      <div v-else-if="data?.error" class="badge-warn">{{ data.error }}</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const DAYS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
const weekdayName = (w: number) => DAYS[w] ?? w

const cards = ref<any>(null)
const errCards = ref('')
const game = ref('')
const data = ref<any>(null)
const loading = ref(false)
const err = ref('')
const focusModel = ref('')
const wd = ref(0) // Monday

const pct = (x?: number) => x == null ? '—' : x + ' %'
const barWidth = (m?: number) => `${Math.min(120, (m ?? 0) * 200)}px`
const shortName = (n: string) => n.replace('_v1', '').replace(/_/g, ' ')
const stabLabel = (s?: string) =>
  ({ stable: 'stable', mixed: 'mixte', volatile: 'volatile',
     not_computable: 'n/c' } as any)[s ?? ''] ?? '—'
const stabClass = (s?: string) =>
  s === 'stable' ? 'badge-ok' : s === 'volatile' ? 'badge-warn' : ''
const trendLabel = (t: any) =>
  ({ improving: '↗ monte', declining: '↘ descend',
     flat: '→ stable', not_computable: '—' } as any)[t?.label] ?? '—'
const vsNull = (v: any) => v?.lift_mean_pct == null ? '—'
  : `${v.lift_mean_pct > 0 ? '+' : ''}${v.lift_mean_pct} %`
const vsNullTitle = (v: any) => v?.binomial_p_ge1 != null
  ? `p binomial ≥1 = ${v.binomial_p_ge1}` : ''

const period = computed(() => {
  const ds = data.value?.draws ?? []
  return ds.length ? `${ds[0].date.slice(0, 7)} → ${ds[ds.length - 1].date.slice(0, 7)}` : '—'
})

const ranked = computed(() =>
  Object.entries(data.value?.models ?? {})
    .map(([name, e]: any) => ({ name, ...e.profile, paired_vs_null: e.paired_vs_null }))
    .filter(m => m.sample_level !== 'insufficient')
    .sort((a, b) => (b.mean_hits ?? -9) - (a.mean_hits ?? -9)))

const topModel = computed(() =>
  ranked.value.filter(m => !['null_model_benchmark', 'random'].includes(m.name))[0])
const mostStable = computed(() =>
  [...ranked.value].filter(m => !['null_model_benchmark', 'random'].includes(m.name))
    .sort((a, b) => (b.consistency?.consistency_index ?? -9) - (a.consistency?.consistency_index ?? -9))[0])

const stateLabel = computed(() => {
  const cps = Object.values<any>(data.value?.models ?? {}).filter(m => m.profile?.change_point)
  if (cps.length) return '⚠ changement détecté'
  const declining = Object.values<any>(data.value?.models ?? {})
    .filter(m => m.profile?.trend?.label === 'declining')
  const improving = Object.values<any>(data.value?.models ?? {})
    .filter(m => m.profile?.trend?.label === 'improving')
  if (declining.length > improving.length) return '↘ en baisse'
  if (improving.length) return '↗ en hausse'
  return '→ stable'
})
const stateClass = computed(() =>
  stateLabel.value.includes('changement') ? 'badge-warn' : '')

const constants = computed(() =>
  ranked.value.filter(m => !['null_model_benchmark', 'random'].includes(m.name)
                        && (m.n ?? 0) >= 10)
    .sort((a, b) => (b.ge2_pct ?? -9) - (a.ge2_pct ?? -9)).slice(0, 3))

// ── progression (section 5) ──
const lastWeeks = computed(() =>
  (data.value?.weekly_models ?? []).slice(-8).map((w: any) => w.iso_week))
const progModels = computed(() =>
  ranked.value.slice(0, 6).map(m => m.name))
const progVal = (name: string, w: string) => {
  const row = (data.value?.weekly_models ?? []).find((r: any) => r.iso_week === w)
  return row?.models?.[name] ?? '·'
}
const progArrow = (name: string) => {
  const t = data.value?.models?.[name]?.profile?.trend
  return ({ improving: '↗', declining: '↘', flat: '→' } as any)[t?.label] ?? '·'
}

// ── per-model weekly + weekday draws ──
const currentWeekly = computed(() =>
  data.value?.models?.[focusModel.value]?.weekly ?? [])
const reversedDraws = computed(() =>
  [...(data.value?.draws ?? [])].reverse())
const wdDraws = computed(() =>
  reversedDraws.value.filter(r => r.weekday === wd.value))

const alerts = computed(() => {
  const out: string[] = []
  for (const [name, e] of Object.entries<any>(data.value?.models ?? {})) {
    const p = e.profile ?? {}
    if (p.change_point)
      out.push(`Changement détecté — ${name} autour de ${p.change_point.iso_week} (p=${p.change_point.permutation_p}). Observation, pas une règle.`)
    if (p.trend?.label === 'declining')
      out.push(`Baisse récente — ${name} : ${p.trend.delta_pct} %.`)
    if (p.trend?.label === 'improving')
      out.push(`Hausse récente — ${name} : +${p.trend.delta_pct} % (observation).`)
    if (p.sample_level === 'insufficient')
      out.push(`Échantillon insuffisant — ${name} : n=${p.n}.`)
  }
  return out
})

async function open(g: string) {
  game.value = g
  loading.value = true; err.value = ''; data.value = null
  try {
    const res = await api.get('/api/lab/game-profiles', { params: { draw_type: g } })
    if (res.data.error) data.value = res.data
    else {
      data.value = res.data
      focusModel.value = topModel.value?.name
        ?? Object.keys(res.data.models ?? {})[0] ?? ''
    }
  } catch (e: any) {
    err.value = e.response?.data?.error || e.message
  } finally { loading.value = false }
}

onMounted(async () => {
  try {
    const res = await api.get('/api/lab/game-cards')
    if (res.data.error) errCards.value = res.data.error
    else cards.value = res.data
  } catch (e: any) {
    errCards.value = e.response?.data?.error || e.message
  }
})
</script>

<style scoped>
.cardgrid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.gamecard {
  border: 1px solid var(--border); border-radius: 8px; padding: 14px;
  background: var(--panel-2); display: flex; flex-direction: column; gap: 5px;
}
.gc-title { font-weight: 800; letter-spacing: 1px; color: var(--gold); }
.gc-line { font-size: 12.5px; color: var(--text); }
.btn-open {
  margin-top: 8px; background: var(--gold); color: #111; border: none;
  border-radius: 5px; padding: 6px 10px; font-weight: 700; font-size: 12px;
  cursor: pointer;
}
.btn-open:hover { filter: brightness(1.1); }

.gamenav { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; align-items: center; }
.gn-back { background: none; border: 1px solid var(--border); color: var(--muted);
  border-radius: 5px; padding: 5px 10px; cursor: pointer; font-size: 12px; }
.gn-chip { background: var(--panel-2); border: 1px solid var(--border); color: var(--muted);
  border-radius: 12px; padding: 4px 12px; cursor: pointer; font-size: 11.5px;
  font-weight: 700; letter-spacing: 0.5px; }
.gn-chip.on { background: var(--gold); color: #111; border-color: var(--gold); }

.syngrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px; margin-bottom: 4px; }
.syn { border: 1px solid var(--border); border-radius: 7px; padding: 9px 11px;
  background: var(--panel-2); }
.sv { font-size: 18px; font-weight: 800; color: var(--text); }
.sl { font-size: 10.5px; color: var(--muted); text-transform: uppercase;
  letter-spacing: 0.4px; }

.podium { display: flex; gap: 10px; flex-wrap: wrap; }
.pod { border: 1px solid var(--border); border-radius: 7px; padding: 10px 14px;
  background: var(--panel-2); display: flex; flex-direction: column; gap: 3px;
  font-size: 12.5px; min-width: 180px; }
.pod-medal { font-size: 18px; }

.scrollbox { max-height: 300px; overflow: auto; border: 1px solid var(--border);
  border-radius: 6px; }
.scrollbox.tall { max-height: 420px; }
.prog-cell { text-align: center; min-width: 46px; }
.hit-cell { color: var(--green); font-weight: 700; }
.baseline-row td { opacity: 0.65; font-style: italic; }
.sm-ball { font-size: 10px; padding: 1px 5px; }
.mini { font-size: 12px; margin-left: 8px; }
.tab.sm { padding: 4px 12px; font-size: 12px; }
h4 { margin-bottom: 6px; }
.badge { font-size: 10px; padding: 1px 7px; border-radius: 9px;
  border: 1px solid var(--border); color: var(--muted); }
.badge.badge-ok { color: var(--green); border-color: var(--green); }
.badge.badge-warn { color: var(--gold); border-color: var(--gold); }
</style>
