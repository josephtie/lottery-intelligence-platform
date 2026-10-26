<template>
  <div class="fusion-agents-page">
    <div class="page-header">
      <h2 class="page-title">🧬 Parieurs — Fusion inter-modèles</h2>
      <span class="page-subtitle">Agents virtuels · aucun avantage économique démontré · aucune mise réelle</span>
    </div>

    <div v-if="err" class="error-banner">
      <el-alert type="error" :closable="false" show-icon>{{ err }}</el-alert>
    </div>

    <div class="filters-bar">
      <el-select
        v-model="drawType"
        placeholder="Jeu"
        filterable
        style="width: 220px"
        @change="reload"
      >
        <el-option
          v-for="g in games"
          :key="g.code"
          :label="g.display_name"
          :value="g.display_name"
        />
      </el-select>
      <el-input
        v-model="search"
        placeholder="Rechercher un agent ou une stratégie…"
        prefix-icon="Search"
        clearable
        style="width: 300px"
      />
      <el-radio-group v-model="sortKey" class="sort-toggle">
        <el-radio-button label="confidence">Confiance</el-radio-button>
        <el-radio-button label="name">Nom</el-radio-button>
        <el-radio-button label="strategy">Stratégie</el-radio-button>
      </el-radio-group>
    </div>

    <div v-if="data" class="meta-line">
      <span class="meta-chip">Jeu : <b>{{ data.draw_type }}</b></span>
      <span class="meta-chip">{{ data.n_draws }} tirages réglés</span>
      <span class="meta-chip">{{ data.agents?.length }} agents</span>
      <span class="meta-chip">Dernier tirage : <b>{{ data.last_draw_date }}</b></span>
    </div>
    <div v-if="data?.last_draw_numbers?.length" class="draw-line">
      <span class="draw-label">Numéros gagnants du dernier tirage :</span>
      <span v-for="n in data.last_draw_numbers" :key="n" class="number-ball win">{{ n }}</span>
    </div>

    <el-table :data="paged" stripe style="width: 100%">
      <el-table-column label="Agent" min-width="180">
        <template #default="{ row }">
          <div class="agent-cell">
            <div class="agent-name">{{ row.display_name }}</div>
            <div class="agent-code">{{ row.code }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="strategy" label="Stratégie" width="130">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.strategy }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="bet_type" label="Type de pari" width="120">
        <template #default="{ row }">
          <el-tag size="small" type="warning">{{ row.bet_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Numéros proposés" min-width="240">
        <template #default="{ row }">
          <div class="numbers-cell">
            <span v-for="n in row.selected_numbers" :key="n"
                  class="number-ball" :class="{ win: isWin(n) }">{{ n }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="Résultat (dernier tirage)" width="180">
        <template #default="{ row }">
          <div class="result-cell">
            <span class="hits">{{ row.hits_last }}/5</span>
            <span :class="row.net_result_last > 0 ? 'net-win' : 'net-loss'">
              {{ row.net_result_last > 0 ? '+' : '' }}{{ row.net_result_last }} F
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="Confiance (accord des modèles)" width="200">
        <template #default="{ row }">
          <el-progress
            :percentage="Math.round(row.confidence_score * 100)"
            :stroke-width="12"
            :format="() => (row.confidence_score * 100).toFixed(1) + '%'"
          />
        </template>
      </el-table-column>
      <el-table-column label="Mise virtuelle" width="120" align="right">
        <template #default="{ row }">
          <span class="mono">{{ Number(row.stake_amount).toLocaleString('fr-FR') }} F</span>
        </template>
      </el-table-column>
      <el-table-column prop="reasoning" label="Raisonnement" min-width="280">
        <template #default="{ row }">
          <span class="reasoning">{{ row.reasoning }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="90" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openDetail(row)">Détails</el-button>
        </template>
      </el-table-column>
    </el-table>

    <Pager
      v-model:page="page"
      v-model:perPage="perPage"
      :total="filtered.length"
      :label="`${filtered.length} agents`"
    />

    <el-drawer
      v-model="drawerVisible"
      :title="detail?.display_name || 'Détail du parieur'"
      direction="rtl"
      size="52%"
    >
      <div v-if="detailLoading" class="drawer-loading">
        <el-skeleton :rows="6" animated />
      </div>
      <div v-else-if="detailErr" class="drawer-error">
        <el-alert type="error" :closable="false" show-icon>{{ detailErr }}</el-alert>
      </div>
      <div v-else-if="detail" class="drawer-content">
        <div class="detail-head">
          <div class="head-stat">
            <div class="head-label">Capital virtuel</div>
            <div class="head-value">{{ fmtF(detail.capital) }} F</div>
          </div>
          <div class="head-stat">
            <div class="head-label">Profit net</div>
            <div class="head-value" :class="detail.profit_net >= 0 ? 'text-green' : 'text-red'">
              {{ detail.profit_net >= 0 ? '+' : '' }}{{ fmtF(detail.profit_net) }} F
            </div>
          </div>
          <div class="head-stat">
            <div class="head-label">Niveau de preuve</div>
            <el-tag :type="proofType" size="small">{{ proofLevel }}</el-tag>
          </div>
          <div class="head-stat">
            <div class="head-label">Entrées mémoire</div>
            <div class="head-value">{{ detail.memory_entries }}</div>
          </div>
        </div>

        <el-tabs v-model="activeTab" class="detail-tabs">
          <el-tab-pane label="Profil" name="profil">
            <div class="tab-block">
              <p class="kv"><span class="k">Code</span><span class="v mono">{{ detail.code }}</span></p>
              <p class="kv"><span class="k">Stratégie</span><span class="v">{{ detail.strategy }}</span></p>
              <p class="kv"><span class="k">Type de pari</span><span class="v">{{ detail.bet_type }}</span></p>
              <p class="kv"><span class="k">Mission</span><span class="v">{{ detail.mission }}</span></p>
              <p class="kv"><span class="k">Spécialités</span><span class="v">{{ (detail.specialties || []).join(', ') }}</span></p>
              <p class="kv"><span class="k">Méthodes</span><span class="v">{{ (detail.preferred_methods || []).join(', ') }}</span></p>
            </div>
          </el-tab-pane>
          <el-tab-pane label="Mémoire" name="memoire">
            <div class="tab-block">
              <p class="kv"><span class="k">Entrées mémoire</span><span class="v">{{ detail.memory_entries }}</span></p>
              <p class="kv"><span class="k">Tirages évalués</span><span class="v">{{ detail.evaluated_draws }}</span></p>
              <el-alert type="info" :closable="false" show-icon
                title="Mémoire walk-forward (historique strict, append-only par construction)" />
            </div>
          </el-tab-pane>
          <el-tab-pane label="Stratégies" name="strategies">
            <div class="tab-block">
              <p class="kv"><span class="k">Stratégie active</span><span class="v">{{ detail.strategy }}</span></p>
              <p class="kv"><span class="k">Type de pari</span><span class="v">{{ detail.bet_type }}</span></p>
              <p class="kv"><span class="k">Méthodes préférées</span><span class="v">{{ (detail.preferred_methods || []).join(', ') }}</span></p>
            </div>
          </el-tab-pane>
          <el-tab-pane label="Expériences" name="experiences">
            <div class="tab-block">
              <p class="kv"><span class="k">Paris (expériences)</span><span class="v">{{ detail.bets }}</span></p>
              <p class="kv"><span class="k">Gains</span><span class="v">{{ detail.wins }}</span></p>
              <p class="kv"><span class="k">Hits moyens</span><span class="v">{{ detail.hits_mean }}</span></p>
            </div>
          </el-tab-pane>
          <el-tab-pane label="Paris" name="paris">
            <div class="tab-block">
              <p class="kv"><span class="k">Nombre de paris</span><span class="v">{{ detail.bets }}</span></p>
              <p class="kv"><span class="k">Paris gagnants</span><span class="v text-green">{{ detail.wins }}</span></p>
              <p class="kv"><span class="k">Taux de réussite</span><span class="v">{{ (detail.win_rate * 100).toFixed(1) }}%</span></p>
              <p class="kv"><span class="k">Hits moyen / tirage</span><span class="v">{{ detail.hits_mean }} (hasard ≈ 0,278)</span></p>
            </div>
            <div class="bets-list">
              <div v-for="(b, i) in detail.bets_history" :key="i" class="bet-row">
                <div class="bet-line">
                  <span class="bet-date">{{ b.date || '—' }}</span>
                  <el-tag size="small" type="warning">{{ b.bet_type }}</el-tag>
                  <span class="bet-stake mono">mise {{ b.stake }} F</span>
                  <span :class="b.net > 0 ? 'text-green' : 'text-red'">{{ b.net > 0 ? '+' : '' }}{{ b.net }} F</span>
                  <el-tag size="small" :type="b.outcome === 'WIN' ? 'success' : 'info'">{{ b.outcome }}</el-tag>
                  <span class="bet-capital mono">capital {{ fmtF(b.capital_after) }} F</span>
                </div>
                <div class="bet-numbers">
                  <span class="bet-nums-label">joué :</span>
                  <span v-for="n in b.selected_numbers" :key="n" class="mini-ball"
                        :class="{ win: (b.winning_numbers || []).includes(n) }">{{ n }}</span>
                  <span class="bet-hit" :class="b.hits > 0 ? 'hit-ok' : ''">{{ b.hits }}/5</span>
                </div>
                <div class="bet-numbers">
                  <span class="bet-nums-label">gagnant :</span>
                  <span v-for="n in b.winning_numbers" :key="n" class="mini-ball win">{{ n }}</span>
                </div>
              </div>
            </div>
          </el-tab-pane>
          <el-tab-pane label="Capital et risque" name="capital">
            <div class="tab-block">
              <p class="kv"><span class="k">Capital initial</span><span class="v">{{ fmtF(detail.initial_capital) }} F</span></p>
              <p class="kv"><span class="k">Capital actuel</span><span class="v">{{ fmtF(detail.capital) }} F</span></p>
              <p class="kv"><span class="k">Profit net</span><span class="v" :class="detail.profit_net >= 0 ? 'text-green' : 'text-red'">{{ fmtF(detail.profit_net) }} F</span></p>
              <p class="kv"><span class="k">Drawdown max</span><span class="v text-red">{{ detail.max_drawdown_pct }}%</span></p>
            </div>
          </el-tab-pane>
          <el-tab-pane label="Historique des versions" name="versions">
            <div class="tab-block">
              <el-timeline>
                <el-timeline-item
                  v-for="(v, i) in detail.version_history"
                  :key="i"
                  :timestamp="`version ${i + 1}`"
                  type="primary"
                >{{ v }}</el-timeline-item>
              </el-timeline>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import api from '../api'
import Pager from '../components/Pager.vue'

const games = ref<any[]>([])
const data = ref<any>(null)
const err = ref('')
const drawType = ref('')
const search = ref('')
const sortKey = ref('confidence')
const page = ref(1)
const perPage = ref(20)

async function load() {
  err.value = ''
  try {
    const path = drawType.value
      ? `/api/fusion/agents?draw_type=${encodeURIComponent(drawType.value)}`
      : '/api/fusion/agents'
    const res = await api.get(path)
    data.value = res.data
  } catch (e: any) {
    err.value = e.response?.data?.error || e.message || 'erreur réseau'
  }
}

onMounted(async () => {
  try {
    const g = await api.get('/api/lab/draw-types')
    games.value = g.data.data || []
    if (games.value.length) drawType.value = games.value[0].display_name
  } catch { /* ignore */ }
  await load()
})

watch(drawType, () => { page.value = 1; load() })

const filtered = computed(() => {
  const list = data.value?.agents || []
  const q = search.value.trim().toLowerCase()
  const out = q
    ? list.filter((a: any) =>
        a.display_name.toLowerCase().includes(q) ||
        a.code.toLowerCase().includes(q) ||
        a.strategy.toLowerCase().includes(q))
    : [...list]
  return out.sort((a: any, b: any) => {
    if (sortKey.value === 'name') return a.display_name.localeCompare(b.display_name)
    if (sortKey.value === 'strategy') return a.strategy.localeCompare(b.strategy)
    return b.confidence_score - a.confidence_score
  })
})

const paged = computed(() => {
  const start = (page.value - 1) * perPage.value
  return filtered.value.slice(start, start + perPage.value)
})

function isWin(n: number) {
  return (data.value?.last_draw_numbers || []).includes(n)
}

const drawerVisible = ref(false)
const detail = ref<any>(null)
const detailLoading = ref(false)
const detailErr = ref('')
const activeTab = ref('profil')

async function openDetail(row: any) {
  drawerVisible.value = true
  detail.value = null
  detailLoading.value = true
  detailErr.value = ''
  activeTab.value = 'profil'
  try {
    const path = `/api/fusion/agent-detail?code=${encodeURIComponent(row.code)}`
      + (drawType.value ? `&draw_type=${encodeURIComponent(drawType.value)}` : '')
    const res = await api.get(path)
    detail.value = res.data
  } catch (e: any) {
    detailErr.value = e.response?.data?.error || e.message || 'erreur réseau'
  } finally {
    detailLoading.value = false
  }
}

function fmtF(v: number) {
  return (v ?? 0).toLocaleString('fr-FR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

const proofLevel = computed(() => {
  if (!detail.value) return '—'
  if (detail.value.bets < 50) return 'En test'
  if (detail.value.profit_net > 0) return 'Prometteur'
  return 'Non établi'
})

const proofType = computed(() => {
  if (proofLevel.value === 'Prometteur') return 'warning'
  if (proofLevel.value === 'En test') return 'info'
  return 'danger'
})
</script>

<style scoped>
.fusion-agents-page {
  padding: 24px;
}
.page-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 20px;
}
.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}
.page-subtitle {
  color: var(--muted);
  font-size: 13px;
}
.error-banner {
  margin-bottom: 16px;
}
.filters-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}
.sort-toggle {
  margin-left: auto;
}
.meta-line {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.meta-chip {
  background: var(--bg-alt);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--muted);
}
.agent-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.agent-name {
  font-weight: 600;
}
.agent-code {
  font-size: 12px;
  color: var(--muted);
}
.numbers-cell {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.number-ball {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--gold);
  color: white;
  font-weight: 600;
  font-size: 13px;
}
.number-ball.win {
  background: #67c23a;
}
.draw-line {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.draw-label {
  font-size: 12px;
  color: var(--muted);
  margin-right: 4px;
}
.result-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.hits {
  font-size: 12px;
  color: var(--muted);
}
.net-win {
  color: #67c23a;
  font-weight: 600;
}
.net-loss {
  color: #f56c6c;
}
.reasoning {
  font-size: 12px;
  color: var(--muted);
}
.mono {
  font-family: monospace;
}
.text-green {
  color: #67c23a;
}
.text-red {
  color: #f56c6c;
}
.drawer-content {
  padding: 0 8px;
}
.drawer-loading,
.drawer-error {
  padding: 16px;
}
.detail-head {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.head-stat {
  background: var(--bg-alt);
  padding: 12px;
  border-radius: 8px;
}
.head-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.head-value {
  font-size: 18px;
  font-weight: 600;
}
.detail-tabs {
  margin-top: 8px;
}
.tab-block {
  padding: 8px 0;
}
.kv {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  margin: 0;
}
.kv .k {
  color: var(--muted);
  font-size: 13px;
}
.kv .v {
  font-weight: 500;
  font-size: 13px;
  text-align: right;
}
.bets-list {
  margin-top: 8px;
  max-height: 340px;
  overflow-y: auto;
}
.bet-row {
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}
.bet-line {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
}
.bet-date {
  color: var(--muted);
  min-width: 80px;
}
.bet-stake {
  color: var(--muted);
}
.bet-capital {
  color: var(--muted);
  margin-left: auto;
}
.bet-numbers {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.bet-nums-label {
  font-size: 11px;
  color: var(--muted);
}
.bet-hit {
  font-size: 11px;
  color: var(--muted);
  margin-left: 8px;
  font-family: monospace;
}
.bet-hit.hit-ok {
  color: #67c23a;
  font-weight: 600;
}
.mini-ball {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--gold);
  color: white;
  font-size: 11px;
  font-weight: 600;
}
.mini-ball.win {
  background: #67c23a;
}
</style>
