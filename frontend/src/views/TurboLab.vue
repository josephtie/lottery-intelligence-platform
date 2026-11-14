<template>
  <h2 class="page-title">🧪 Turbo Laboratory</h2>
  <div class="sub" style="margin-bottom:12px">
    Évaluation <b>prospective</b> — prédictions scellées avant le tirage officiel.
    Montants calculés par le moteur de règlement selon les règles versionnées ;
    <b>aucune mise réelle n'a été engagée ni encaissée</b>.
  </div>
  <div v-if="errSum || errVar" class="panel"><span class="badge-err">{{ errSum || errVar }}</span></div>

  <el-tabs v-model="activeTab">
    <!-- Onglet Turbo Standard -->
    <el-tab-pane label="🎰 Turbo Standard" name="standard">
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
    </el-tab-pane>

    <!-- Onglet Racine Numérique -->
    <el-tab-pane label="🌱 Racine Numérique" name="digital-root">
      <div class="sub" style="margin-bottom:12px">
        Prédictions basées sur les racines numériques (digital roots) avec Turbo 2 et Turbo 5.
        Racine numérique = somme des chiffres réduite à un chiffre, <b>9 → 0</b>.
      </div>

      <div class="panel">
        <h3>Prédictions Racine Numérique</h3>
        <div class="filters">
          <select v-model="rootGame"><option value="">Tous les jeux</option>
            <option v-for="opt in gameOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option></select>
          <select v-model="rootVariant">
            <option value="turbo_2">Turbo 2</option>
            <option value="turbo_5">Turbo 5</option>
          </select>
          <input type="date" v-model="rootDate" :max="today" />
          <button @click="loadRootPrediction" class="csv-btn">Générer</button>
        </div>

        <div v-if="rootLoading" class="sub">Chargement…</div>
        <div v-else-if="rootError" class="badge-err">{{ rootError }}</div>
        <template v-else-if="rootPrediction">
          <div class="cards" style="margin-bottom:14px">
            <div class="card"><div class="label">Jeu</div>
              <div class="value">{{ rootPrediction.draw_type }}</div></div>
            <div class="card"><div class="label">Date cible</div>
              <div class="value">{{ rootPrediction.target_date }}</div></div>
            <div class="card"><div class="label">Variante</div>
              <div class="value">{{ label(rootPrediction.variant) }}</div></div>
            <div class="card"><div class="label">Confiance</div>
              <div class="value">{{ (rootPrediction.confidence * 100).toFixed(0) }}%</div></div>
          </div>

          <h3 class="sh">Racines prédites (Système Adaptatif)</h3>
          <table class="data mb0">
            <tr><th>Racine</th><th>Confiance</th></tr>
            <tr v-for="r in rootPrediction.predicted_roots" :key="r.root">
              <td class="mono"><b>{{ r.root }}</b></td>
              <td class="mono">{{ (r.confidence * 100).toFixed(1) }} %</td>
            </tr>
          </table>

          <div v-if="rootPrediction.metadata" class="sub" style="margin-top:10px">
            <b>Raisonnement :</b> {{ rootPrediction.metadata }}
          </div>
        </template>
      </div>
    </el-tab-pane>

    <!-- Onglet Tableau Journalier -->
    <el-tab-pane label="📊 Tableau Journalier" name="daily-table">
      <div class="sub" style="margin-bottom:12px">
        Tableau des jeux du jour avec prédictions de racines numériques et résultats officiels.
      </div>

      <div class="panel">
        <h3>Jeux du jour - Prédictions et Résultats</h3>
        <div class="filters">
          <input type="date" v-model="dailyDate" :max="today" />
          <button @click="loadDailyPredictions" class="csv-btn">Charger</button>
        </div>

        <div v-if="dailyLoading" class="sub">Chargement…</div>
        <div v-else-if="dailyError" class="badge-err">{{ dailyError }}</div>
        <template v-else-if="dailyData">
          <div class="cards" style="margin-bottom:14px">
            <div class="card"><div class="label">Date</div>
              <div class="value">{{ dailyData.date }}</div></div>
            <div class="card"><div class="label">Total jeux</div>
              <div class="value">{{ dailyData.total_games }}</div></div>
          </div>

          <table class="data mb0">
            <tr>
              <th>Jeu</th>
              <th>Statut</th>
              <th>Résultat officiel</th>
              <th>Racines</th>
              <th>Adaptatif</th>
              <th>Confiance</th>
              <th>Turbo 2 N°</th>
              <th>Turbo 2 Racines</th>
              <th>Turbo 2 Hits</th>
              <th>Turbo 5 N°</th>
              <th>Turbo 5 Racines</th>
              <th>Turbo 5 Hits</th>
            </tr>
            <tr v-for="game in dailyData.predictions" :key="game.draw_id">
              <td>{{ game.draw_type }}</td>
              <td><span :class="game.status === 'SETTLED' ? 'badge-ok' : 'badge-warn'">{{ game.status }}</span></td>
              <td>
                <span v-if="game.actual_numbers">
                  <span v-for="n in game.actual_numbers" :key="n" class="num-ball actual">{{ n }}</span>
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td class="mono">{{ game.actual_roots?.join(', ') || '—' }}</td>
              <td>
                <span v-if="game.predictions.adaptive.error" class="badge-err">{{ game.predictions.adaptive.error }}</span>
                <span v-else-if="game.predictions.adaptive.predicted_roots" class="mono">
                  {{ game.predictions.adaptive.predicted_roots.join(', ') }}
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td class="mono">
                <span v-if="game.predictions.adaptive.confidence !== undefined">
                  {{ (game.predictions.adaptive.confidence * 100).toFixed(0) }}%
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td>
                <span v-if="game.predictions.turbo_2.error" class="badge-err">{{ game.predictions.turbo_2.error }}</span>
                <span v-else-if="game.predictions.turbo_2.final_selection">
                  <span v-for="n in game.predictions.turbo_2.final_selection" :key="n" class="num-ball">{{ n }}</span>
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td class="mono">{{ game.predictions.turbo_2.predicted_roots?.join(', ') || '—' }}</td>
              <td class="mono">
                <span v-if="game.actual_numbers && game.predictions.turbo_2.final_selection">
                  {{ countHits(game.predictions.turbo_2.final_selection, game.actual_numbers) }} / {{ game.predictions.turbo_2.numbers_required }}
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td>
                <span v-if="game.predictions.turbo_5.error" class="badge-err">{{ game.predictions.turbo_5.error }}</span>
                <span v-else-if="game.predictions.turbo_5.final_selection">
                  <span v-for="n in game.predictions.turbo_5.final_selection" :key="n" class="num-ball">{{ n }}</span>
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td class="mono">{{ game.predictions.turbo_5.predicted_roots?.join(', ') || '—' }}</td>
              <td class="mono">
                <span v-if="game.actual_numbers && game.predictions.turbo_5.final_selection">
                  {{ countHits(game.predictions.turbo_5.final_selection, game.actual_numbers) }} / {{ game.predictions.turbo_5.numbers_required }}
                </span>
                <span v-else class="sub">—</span>
              </td>
            </tr>
          </table>
        </template>
      </div>

      <!-- Tableau par plage de dates -->
      <div class="panel" style="margin-top:16px">
        <h3 style="display:flex;justify-content:space-between;align-items:center">
          <span>Plage de dates - Prédictions et Résultats</span>
          <button class="csv-btn" @click="exportRangeExcel" :disabled="!rangeData || !rangeData.predictions.length">Export CSV</button>
        </h3>
        <div class="filters">
          <input type="date" v-model="rangeStartDate" :max="rangeEndDate" />
          <input type="date" v-model="rangeEndDate" :min="rangeStartDate" :max="today" />
          <select v-model="rangeGame"><option value="">Tous les jeux</option>
            <option v-for="opt in gameOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option></select>
          <button @click="loadRangePredictions" class="csv-btn">Charger</button>
        </div>

        <div v-if="rangeLoading" class="sub">Chargement…</div>
        <div v-else-if="rangeError" class="badge-err">{{ rangeError }}</div>
        <template v-else-if="rangeData">
          <div class="cards" style="margin-bottom:14px">
            <div class="card"><div class="label">Du</div>
              <div class="value">{{ rangeData.start_date }}</div></div>
            <div class="card"><div class="label">Au</div>
              <div class="value">{{ rangeData.end_date }}</div></div>
            <div class="card"><div class="label">Total jeux</div>
              <div class="value">{{ rangeData.total_games }}</div></div>
          </div>

          <table class="data mb0">
            <tr>
              <th>Date</th>
              <th>Jeu</th>
              <th>Statut</th>
              <th>Résultat officiel</th>
              <th>Racines</th>
              <th>Adaptatif</th>
              <th>Confiance</th>
              <th>Turbo 2 N°</th>
              <th>Turbo 2 Racines</th>
              <th>Turbo 2 Hits</th>
              <th>Turbo 5 N°</th>
              <th>Turbo 5 Racines</th>
              <th>Turbo 5 Hits</th>
            </tr>
            <tr v-for="game in rangeData.predictions" :key="game.draw_id">
              <td class="mono">{{ game.scheduled_date }}</td>
              <td>{{ game.draw_type }}</td>
              <td><span :class="game.status === 'SETTLED' ? 'badge-ok' : 'badge-warn'">{{ game.status }}</span></td>
              <td>
                <span v-if="game.actual_numbers">
                  <span v-for="n in game.actual_numbers" :key="n" class="num-ball actual">{{ n }}</span>
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td class="mono">{{ game.actual_roots?.join(', ') || '—' }}</td>
              <td>
                <span v-if="game.predictions.adaptive.error" class="badge-err">{{ game.predictions.adaptive.error }}</span>
                <span v-else-if="game.predictions.adaptive.predicted_roots" class="mono">
                  {{ game.predictions.adaptive.predicted_roots.join(', ') }}
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td class="mono">
                <span v-if="game.predictions.adaptive.confidence !== undefined">
                  {{ (game.predictions.adaptive.confidence * 100).toFixed(0) }}%
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td>
                <span v-if="game.predictions.turbo_2.error" class="badge-err">{{ game.predictions.turbo_2.error }}</span>
                <span v-else-if="game.predictions.turbo_2.final_selection">
                  <span v-for="n in game.predictions.turbo_2.final_selection" :key="n" class="num-ball">{{ n }}</span>
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td class="mono">{{ game.predictions.turbo_2.predicted_roots?.join(', ') || '—' }}</td>
              <td class="mono">
                <span v-if="game.actual_numbers && game.predictions.turbo_2.final_selection">
                  {{ countHits(game.predictions.turbo_2.final_selection, game.actual_numbers) }} / {{ game.predictions.turbo_2.numbers_required }}
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td>
                <span v-if="game.predictions.turbo_5.error" class="badge-err">{{ game.predictions.turbo_5.error }}</span>
                <span v-else-if="game.predictions.turbo_5.final_selection">
                  <span v-for="n in game.predictions.turbo_5.final_selection" :key="n" class="num-ball">{{ n }}</span>
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td class="mono">{{ game.predictions.turbo_5.predicted_roots?.join(', ') || '—' }}</td>
              <td class="mono">
                <span v-if="game.actual_numbers && game.predictions.turbo_5.final_selection">
                  {{ countHits(game.predictions.turbo_5.final_selection, game.actual_numbers) }} / {{ game.predictions.turbo_5.numbers_required }}
                </span>
                <span v-else class="sub">—</span>
              </td>
            </tr>
          </table>
        </template>
      </div>
    </el-tab-pane>
  </el-tabs>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useFetch } from '../useFetch'
import api from '../api'
import ReplayLab from '../components/ReplayLab.vue'

const { data: sum, error: errSum } = useFetch<any>('/api/turbo/summary')
const { data: variants, error: errVar } = useFetch<any[]>('/api/turbo/variants')
const { data: next } = useFetch<any[]>('/api/turbo/next')
const { data: models } = useFetch<any[]>('/api/turbo/models')
const { data: results } = useFetch<any[]>('/api/turbo/results')
const { data: drawTypes } = useFetch<any[]>('/api/lab/draw-types')

// Use display_name for game selection
const gameOptions = computed(() => {
  if (!drawTypes.value) return []
  return drawTypes.value.map((dt: any) => ({
    value: dt.display_name,
    label: dt.display_name
  }))
})

const turboCols = ['turbo_2', 'turbo_3', 'turbo_4', 'turbo_5']
const nextType = ref(''); const resModel = ref(''); const resVariant = ref('')

const activeTab = ref('standard')
const rootGame = ref('')
const rootVariant = ref('turbo_2')
const rootDate = ref(new Date().toISOString().slice(0, 10))
const rootPrediction = ref<any>(null)
const rootLoading = ref(false)
const rootError = ref('')

const dailyDate = ref(new Date().toISOString().slice(0, 10))
const dailyData = ref<any>(null)
const dailyLoading = ref(false)
const dailyError = ref('')

const rangeStartDate = ref(new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10))
const rangeEndDate = ref(new Date().toISOString().slice(0, 10))
const rangeGame = ref('')
const rangeData = ref<any>(null)
const rangeLoading = ref(false)
const rangeError = ref('')

const today = new Date().toISOString().slice(0, 10)

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

async function loadRootPrediction() {
  rootLoading.value = true; rootError.value = ''
  try {
    const params: any = { top_roots: 5 }
    if (rootGame.value) params.draw_type = rootGame.value
    if (rootDate.value) params.date = rootDate.value
    // Extract hour from date if available
    if (rootDate.value) {
      const d = new Date(rootDate.value)
      params.hour = d.getHours()
    }
    const res = await api.get('/api/adaptive-root/predict', { params })
    if (res.data.error) { rootError.value = res.data.error; rootPrediction.value = null }
    else {
      // Format adaptive prediction to match expected structure
      const overallConfidence = res.data.confidence || 0.5
      rootPrediction.value = {
        draw_type: rootGame.value || 'Tous les jeux',
        target_date: rootDate.value || new Date().toISOString().split('T')[0],
        variant: rootVariant.value,
        numbers_required: rootVariant.value === 'turbo_2' ? 2 : 5,
        confidence: overallConfidence,
        predicted_roots: res.data.predicted_roots.map((r: any) => ({
          root: r,
          confidence: overallConfidence
        })),
        turbo_candidates: [],
        final_selection: [],
        metadata: res.data.reasoning
      }
    }
  } catch (e: any) {
    rootError.value = e.response?.data?.error || e.message
    rootPrediction.value = null
  } finally { rootLoading.value = false }
}

async function loadDailyPredictions() {
  dailyLoading.value = true; dailyError.value = ''
  try {
    const params: any = {}
    if (dailyDate.value) params.date = dailyDate.value
    const res = await api.get('/api/digital-root-turbo/daily', { params })
    if (res.data.error) { dailyError.value = res.data.error; dailyData.value = null }
    else dailyData.value = res.data
  } catch (e: any) {
    dailyError.value = e.response?.data?.error || e.message
    dailyData.value = null
  } finally { dailyLoading.value = false }
}

function countHits(predicted: number[], actual: number[]) {
  if (!predicted || !actual) return 0
  return predicted.filter(n => actual.includes(n)).length
}

async function loadRangePredictions() {
  rangeLoading.value = true; rangeError.value = ''
  try {
    const params: any = {}
    if (rangeStartDate.value) params.start_date = rangeStartDate.value
    if (rangeEndDate.value) params.end_date = rangeEndDate.value
    if (rangeGame.value) params.draw_type = rangeGame.value
    const res = await api.get('/api/digital-root-turbo/range', { params })
    if (res.data.error) { rangeError.value = res.data.error; rangeData.value = null }
    else rangeData.value = res.data
  } catch (e: any) {
    rangeError.value = e.response?.data?.error || e.message
    rangeData.value = null
  } finally { rangeLoading.value = false }
}

onMounted(() => {
  loadDailyPredictions()
  loadRangePredictions()
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

function exportRangeExcel() {
  if (!rangeData.value) return
  const rows = rangeData.value.predictions
  const head = ['Date', 'Jeu', 'Statut', 'Résultat officiel', 'Racines',
                'Turbo 2 N°', 'Turbo 2 Racines', 'Turbo 2 Hits',
                'Turbo 5 N°', 'Turbo 5 Racines', 'Turbo 5 Hits']
  const lines = [head.join(';')]
  for (const r of rows) {
    lines.push([
      r.scheduled_date, r.draw_type, r.status,
      (r.actual_numbers ?? []).join('-'), (r.actual_roots ?? []).join(','),
      (r.predictions.turbo_2.final_selection ?? []).join('-'),
      (r.predictions.turbo_2.predicted_roots ?? []).join(','),
      r.actual_numbers && r.predictions.turbo_2.final_selection 
        ? countHits(r.predictions.turbo_2.final_selection, r.actual_numbers) + '/' + r.predictions.turbo_2.numbers_required 
        : '',
      (r.predictions.turbo_5.final_selection ?? []).join('-'),
      (r.predictions.turbo_5.predicted_roots ?? []).join(','),
      r.actual_numbers && r.predictions.turbo_5.final_selection 
        ? countHits(r.predictions.turbo_5.final_selection, r.actual_numbers) + '/' + r.predictions.turbo_5.numbers_required 
        : '',
    ].join(';'))
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `digital_root_range_${rangeData.value.start_date}_to_${rangeData.value.end_date}.csv`
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
