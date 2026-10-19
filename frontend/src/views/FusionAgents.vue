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
    </el-table>

    <Pager
      v-model:page="page"
      v-model:perPage="perPage"
      :total="filtered.length"
      :label="`${filtered.length} agents`"
    />
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
</style>
