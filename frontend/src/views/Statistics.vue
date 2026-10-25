<template>
  <h2 class="page-title">📊 Statistiques par jeu</h2>
  <div class="sub" style="margin-bottom:12px">
    Fréquences réelles des numéros gagnants (versions VALID). Le test χ² mesure
    l'écart à une distribution uniforme — il ne prédit rien, il décrit.
  </div>

  <div class="panel">
    <div class="filters">
      <select v-model="drawType" @change="onGameChange">
        <option v-for="t in types" :key="t.code + t.display_name" :value="t.display_name">
          {{ t.display_name }} ({{ t.settled_draws }})</option>
      </select>
    </div>

    <el-tabs v-model="activeTab">
      <!-- ======================= Onglet Numéros ======================= -->
      <el-tab-pane label="🔢 Numéros" name="numbers">
        <div class="filters" style="margin-bottom:10px">
          <select v-model="days" @change="load">
            <option :value="10">10 derniers jours</option>
            <option :value="30">30 derniers jours</option>
            <option :value="50">50 derniers jours</option>
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

          <div class="stat-grid" style="margin-top:14px">
            <div>
              <h3 class="sh">🎯 Deux premiers numéros (positions 1–2)</h3>
              <div class="sub" style="margin-bottom:8px">
                Fréquence de sortie en 1re ou 2e position · attendu ≈
                {{ stats.first_two_expected?.toFixed(1) }} sorties sur {{ stats.draw_count }} tirages
              </div>
              <div v-for="x in stats.first_two" :key="'f'+x.number" class="stat-hbar">
                <span class="num-ball pos-ball">{{ x.number }}</span>
                <div class="bar"><div class="fill pos-fill"
                     :style="{width: barw2(x.count, stats.first_two[0]?.count)}"></div></div>
                <span class="num">{{ x.count }}</span>
              </div>
            </div>
            <div>
              <h3 class="sh">👯 Paires les plus fréquentes</h3>
              <div class="sub" style="margin-bottom:6px">
                Comparées à l'attente du hasard — p-value binomiale, q corrigé FDR
                sur les 4005 paires possibles. q &lt; 0.10 seulement = signal.
              </div>
              <table class="data mb0" v-if="stats.top_pairs?.length">
                <tr><th>Paire</th><th>Sorties</th><th>Attendu</th><th>Lift</th><th>p</th><th>q FDR</th><th>Dernière</th></tr>
                <tr v-for="p in stats.top_pairs.slice(0, 12)" :key="p.pair.join('-')">
                  <td><span v-for="n in p.pair" :key="n" class="num-ball pair-ball">{{ n }}</span></td>
                  <td class="mono">{{ p.count }}</td>
                  <td class="mono sub">{{ p.expected != null ? p.expected.toFixed(2) : '—' }}</td>
                  <td class="mono">{{ p.lift != null ? '×' + p.lift.toFixed(1) : '—' }}</td>
                  <td class="mono sub">{{ p.p_value != null ? p.p_value.toExponential(1) : '—' }}</td>
                  <td class="mono" :class="p.q_fdr != null && p.q_fdr < 0.10 ? 'badge-ok' : 'sub'">
                    {{ p.q_fdr != null ? p.q_fdr.toFixed(2) : '—' }}</td>
                  <td class="mono sub">{{ p.last_date }}</td>
                </tr>
              </table>
              <div v-else class="sub">Pas assez de tirages.</div>
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
      </el-tab-pane>

      <!-- =================== Onglet Racines numériques =================== -->
      <el-tab-pane label="🌱 Racines numériques" name="roots">
        <div class="sub" style="margin-bottom:10px">
          Racine numérique = somme des chiffres réduite à un chiffre, <b>9 → 0</b> :
          9 classes (0–8), chacune couvrant 10 numéros → référence uniforme
          <b>{{ roots?.reference_freq_pct ?? '11,111' }} %</b>. Statistique
          <b>descriptive</b> : une fréquence élevée n'est jamais une garantie de sortie.
        </div>

        <div class="filters" style="margin-bottom:10px">
          <select v-model="rootsWindow" @change="loadRoots">
            <option :value="10">10 jours</option>
            <option :value="30">30 jours</option>
            <option :value="45">45 jours</option>
            <option :value="60">60 jours</option>
            <option :value="90">90 jours</option>
          </select>
          <input type="date" v-model="referenceDate" @change="loadRoots"
                 :max="today" title="Date de référence (tirages postérieurs exclus)" />
        </div>

        <div v-if="rootsLoading" class="sub">Chargement…</div>
        <div v-else-if="rootsError" class="badge-err">{{ rootsError }}</div>
        <template v-else-if="roots">
          <div class="cards" style="margin-bottom:12px">
            <div class="card"><div class="label">Tirages (fenêtre)</div>
              <div class="value">{{ win?.draws }}</div></div>
            <div class="card"><div class="label">Numéros analysés</div>
              <div class="value">{{ win?.numbers }}</div></div>
            <div class="card"><div class="label">Référence / racine</div>
              <div class="value">{{ roots.reference_freq_pct }} %</div></div>
            <div class="card"><div class="label">Racine dominante</div>
              <div class="value gold">{{ win?.top_root ?? '—' }}</div></div>
          </div>

          <div v-if="roots.warning" class="badge-warn">{{ roots.warning }}</div>

          <h3 class="sh">Distribution des racines (fenêtre {{ rootsWindow }} j)</h3>
          <table class="data mb0">
            <tr><th>Racine</th><th>Occurrences</th><th>%</th><th>Écart (pt)</th><th>Tirages</th><th>Famille de numéros</th></tr>
            <tr v-for="r in (win?.distribution ?? roots.global)" :key="r.root">
              <td class="mono"><b>{{ r.root }}</b></td>
              <td class="mono">{{ r.count }}</td>
              <td class="mono">{{ r.percentage.toFixed(1) }} %</td>
              <td class="mono" :class="Math.abs(r.deviation_pct) >= 1.5 ? 'badge-ok' : ''">
                {{ r.deviation_pct > 0 ? '+' : '' }}{{ r.deviation_pct.toFixed(1) }}</td>
              <td class="mono">{{ r.draws }}</td>
              <td class="mono sub">{{ r.family.join('·') }}</td>
            </tr>
          </table>

          <h3 class="sh" style="margin-top:16px">Racine dominante par position</h3>
          <div class="root-pos-grid">
            <div v-for="p in positionList" :key="p" class="card">
              <div class="label">Position {{ p }}</div>
              <div class="value gold">{{ roots.position[p].top_root ?? '—' }}</div>
              <div class="sub">{{ roots.position[p].top_count }} / {{ roots.position[p].total }} sorties</div>
            </div>
          </div>

          <h3 class="sh" style="margin-top:16px">Comparaison des fenêtres (imbriquées)</h3>
          <div class="sub" style="margin-bottom:6px">
            Les fenêtres 10 ⊂ 30 ⊂ 45 ⊂ 60 ⊂ 90 jours sont imbriquées — ce ne sont
            PAS des échantillons indépendants.
          </div>
          <table class="data mb0">
            <tr><th>Fenêtre</th><th>Tirages</th><th>Numéros</th><th>Racine top</th><th>Part</th></tr>
            <tr v-for="w in roots.windows" :key="w" :class="{ 'row-active': w === String(rootsWindow) }">
              <td class="mono">{{ w }} j</td>
              <td class="mono">{{ roots.evolution.per_window[w].draws }}</td>
              <td class="mono">{{ roots.evolution.per_window[w].numbers }}</td>
              <td class="mono gold">{{ roots.evolution.per_window[w].top_root }}</td>
              <td class="mono">{{ roots.evolution.per_window[w].top_share.toFixed(1) }} %</td>
            </tr>
          </table>

          <h3 class="sh" style="margin-top:16px">Signatures des derniers tirages</h3>
          <table class="data mb0" v-if="roots.signatures?.length">
            <tr><th>Date</th><th>Numéros</th><th>Signature</th><th>Distincts</th><th>Répétitions</th></tr>
            <tr v-for="s in roots.signatures" :key="s.draw_id">
              <td class="mono">{{ s.date }}</td>
              <td class="mono">{{ s.numbers.join('·') }}</td>
              <td class="mono gold">{{ s.signature }}</td>
              <td class="mono">{{ s.distinct_count }}</td>
              <td class="mono sub">{{ s.repeats.join(', ') || '—' }}</td>
            </tr>
          </table>

          <h3 class="sh" style="margin-top:16px">Évaluation walk-forward (racine par position)</h3>
          <div class="sub" style="margin-bottom:6px">
            Prédit la racine suivante par le mode de la fenêtre passée (strictement
            antérieure), comparé au hasard uniforme (1/9 ≈ 11,1 %).
          </div>
          <table class="data mb0">
            <tr><th>Fenêtre</th><th>Essais</th><th>Hits</th><th>Taux</th><th>Hasard</th></tr>
            <tr v-for="r in roots.walkforward.results" :key="r.window">
              <td class="mono">{{ r.window }} j</td>
              <td class="mono">{{ r.trials }}</td>
              <td class="mono">{{ r.hits }}</td>
              <td class="mono">{{ r.hit_rate != null ? (r.hit_rate * 100).toFixed(1) + ' %' : '—' }}</td>
              <td class="mono sub">{{ (r.random_baseline * 100).toFixed(1) }} %</td>
            </tr>
          </table>
        </template>
      </el-tab-pane>
    </el-tabs>
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

const activeTab = ref('numbers')
const rootsWindow = ref(30)
const referenceDate = ref('')
const roots = ref<any>(null)
const rootsLoading = ref(false)
const rootsError = ref('')

const today = new Date().toISOString().slice(0, 10)

const win = computed(() =>
  roots.value?.evolution?.per_window?.[String(rootsWindow.value)] ?? null)
const positionList = computed(() =>
  roots.value ? Object.keys(roots.value.position).sort((a, b) => +a - +b) : [])

const maxCount = computed(() =>
  Math.max(1, ...(stats.value?.numbers ?? []).map((x: any) => x.count)))

function barw(c: number) { return (c / maxCount.value * 100).toFixed(1) + '%' }
function barw2(c: number, max: number) {
  return (c / Math.max(1, max ?? 1) * 100).toFixed(1) + '%'
}

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

async function loadRoots() {
  if (!drawType.value) return
  rootsLoading.value = true; rootsError.value = ''
  try {
    const params: any = { draw_type: drawType.value }
    if (referenceDate.value) params.reference_date = referenceDate.value
    const res = await api.get('/api/digital-root-statistics', { params })
    if (res.data.error) { rootsError.value = res.data.error; roots.value = null }
    else roots.value = res.data
  } catch (e: any) {
    rootsError.value = e.response?.data?.error || e.message
    roots.value = null
  } finally { rootsLoading.value = false }
}

function onGameChange() { load(); loadRoots() }

onMounted(async () => {
  try {
    const res = await api.get('/api/lab/draw-types')
    types.value = (res.data.data ?? []).filter((t: any) => t.settled_draws > 0)
    if (types.value.length) {
      drawType.value = types.value[0].display_name
      await load()
      await loadRoots()
    }
  } catch (e: any) { error.value = e.response?.data?.error || e.message }
})
</script>

<style scoped>
.sh { color: var(--gold); font-size: 13px; margin: 10px 0 8px; }
.stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
@media (max-width: 700px) { .stat-grid { grid-template-columns: 1fr; } }
.cold-ball { background: #4a6a8a; color: #fff; }
.cold-fill { background: #4a6a8a; }
.pos-ball { background: var(--green); color: #fff; }
.pos-fill { background: var(--green); }
.pair-ball { background: var(--panel); color: var(--gold-soft); border: 1px solid var(--gold); }
.badge-warn { background: rgba(212,160,23,0.15); color: var(--gold-soft); padding: 6px 10px; border-radius: 6px; margin-bottom: 8px; }
.root-pos-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
@media (max-width: 700px) { .root-pos-grid { grid-template-columns: repeat(2, 1fr); } }
.row-active { background: rgba(212,160,23,0.10); }
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
