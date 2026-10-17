<template>
  <div class="agents-page">
    <!-- Header -->
    <div class="page-header">
      <h2 class="page-title">🤖 Parieurs — Agents Autonomes</h2>
      <div class="header-actions">
        <div class="summary-card">
          <div class="summary-label">Capital Total</div>
          <div class="summary-value">{{ fmtCurrency(totalCapital) }} FCFA</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">Profit Net</div>
          <div class="summary-value" :class="totalProfit >= 0 ? 'green' : 'red'">
            {{ fmtCurrency(totalProfit) }} FCFA
          </div>
        </div>
        <div class="summary-card">
          <div class="summary-label">Taux de réussite</div>
          <div class="summary-value">{{ winRate }}%</div>
        </div>
      </div>
    </div>

    <!-- Error State -->
    <div v-if="err" class="error-banner">
      <el-alert type="error" :closable="false" show-icon>
        {{ err }}
      </el-alert>
    </div>

    <!-- Empty State -->
    <div v-if="!agents?.length" class="empty-state">
      <el-empty description="Aucun agent actif">
        <el-button type="primary">Créer un agent</el-button>
      </el-empty>
    </div>

    <!-- Main Content -->
    <div v-else class="main-content">
      <!-- Filters -->
      <div class="filters-bar">
        <el-input
          v-model="searchQuery"
          placeholder="Rechercher un agent..."
          prefix-icon="Search"
          clearable
          style="width: 300px"
        />
        <el-select v-model="statusFilter" placeholder="Statut" clearable style="width: 150px">
          <el-option label="Actif" value="ACTIVE" />
          <el-option label="En pause" value="PAUSED" />
          <el-option label="Retraité" value="RETIRED" />
        </el-select>
        <el-select v-model="levelFilter" placeholder="Niveau" clearable style="width: 150px">
          <el-option label="Décision" value="DECISION" />
          <el-option label="Recherche" value="RESEARCH" />
          <el-option label="Évolution" value="EVOLUTION" />
        </el-select>
        <el-radio-group v-model="viewMode" class="view-toggle">
          <el-radio-button label="cards">Cartes</el-radio-button>
          <el-radio-button label="table">Tableau</el-radio-button>
        </el-radio-group>
      </div>

      <!-- Cards View -->
      <div v-if="viewMode === 'cards'" class="agents-grid">
        <div v-for="agent in filteredAgents" :key="agent.agent_id" class="agent-card" @click="selectAgent(agent)">
          <!-- Card Header -->
          <div class="card-header">
            <div class="agent-avatar">
              <span class="avatar-emoji">🤖</span>
              <span class="generation-badge">G{{ agent.generation }}</span>
            </div>
            <div class="agent-info">
              <div class="agent-name">{{ agent.display_name }}</div>
              <div class="agent-code">{{ agent.code }}</div>
            </div>
            <div class="agent-status">
              <el-tag :type="getStatusType(agent.status)" size="small">
                {{ getStatusLabel(agent.status) }}
              </el-tag>
              <el-tag :type="getLevelType(agent.operational_level)" size="small">
                {{ agent.operational_level }}
              </el-tag>
            </div>
          </div>

          <!-- Capital Section -->
          <div class="card-section capital-section">
            <div class="section-label">Capital virtuel</div>
            <div class="capital-display">
              <div class="capital-value" :class="agent.net_profit >= 0 ? 'positive' : 'negative'">
                {{ fmtCurrency(agent.current_capital) }} FCFA
              </div>
              <div class="capital-change">
                <span :class="agent.net_profit >= 0 ? 'positive' : 'negative'">
                  {{ agent.net_profit >= 0 ? '+' : '' }}{{ fmtCurrency(agent.net_profit) }}
                </span>
                <span class="roi-badge">ROI: {{ agent.roi?.toFixed(1) }}%</span>
              </div>
            </div>
            <!-- Progress bar for capital -->
            <div class="capital-progress">
              <el-progress
                :percentage="getCapitalPercentage(agent)"
                :color="agent.net_profit >= 0 ? '#67c23a' : '#f56c6c'"
                :show-text="false"
                :stroke-width="4"
              />
            </div>
          </div>

          <!-- Stats Grid -->
          <div class="card-section stats-section">
            <div class="stats-grid">
              <div class="stat-item">
                <div class="stat-icon">🎯</div>
                <div class="stat-value">{{ agent.total_bets }}</div>
                <div class="stat-label">Paris</div>
              </div>
              <div class="stat-item">
                <div class="stat-icon">✅</div>
                <div class="stat-value positive">{{ agent.winning_bets }}</div>
                <div class="stat-label">Gagnés</div>
              </div>
              <div class="stat-item">
                <div class="stat-icon">❌</div>
                <div class="stat-value negative">{{ agent.losing_bets }}</div>
                <div class="stat-label">Perdus</div>
              </div>
              <div class="stat-item">
                <div class="stat-icon">⏸️</div>
                <div class="stat-value">{{ agent.no_bet_count }}</div>
                <div class="stat-label">Abstentions</div>
              </div>
            </div>
          </div>

          <!-- Memory Section -->
          <div class="card-section memory-section">
            <div class="section-label">Mémoire</div>
            <div class="memory-bars">
              <div class="memory-item">
                <span class="memory-label">Hypothèses</span>
                <el-progress
                  :percentage="getMemoryPercentage(agent.hypotheses_count, 50)"
                  :show-text="false"
                  :stroke-width="6"
                  color="#409eff"
                />
                <span class="memory-count">{{ agent.hypotheses_count }}</span>
              </div>
              <div class="memory-item">
                <span class="memory-label">Expériences</span>
                <el-progress
                  :percentage="getMemoryPercentage(agent.experiments_count, 100)"
                  :show-text="false"
                  :stroke-width="6"
                  color="#67c23a"
                />
                <span class="memory-count">{{ agent.experiments_count }}</span>
              </div>
              <div class="memory-item">
                <span class="memory-label">Réussites</span>
                <el-progress
                  :percentage="getMemoryPercentage(agent.successes_count, 20)"
                  :show-text="false"
                  :stroke-width="6"
                  color="#e6a23c"
                />
                <span class="memory-count">{{ agent.successes_count }}</span>
              </div>
            </div>
          </div>

          <!-- Proof Level -->
          <div class="card-section proof-section">
            <div class="proof-indicator">
              <span class="proof-label">Niveau de preuve</span>
              <el-tag :type="getProofType(agent)" size="small">
                {{ getProofLevel(agent) }}
              </el-tag>
            </div>
          </div>

          <!-- Last Reflection -->
          <div v-if="agent.last_reflection" class="card-section reflection-section">
            <div class="reflection-preview">
              <span class="reflection-icon">💭</span>
              <span class="reflection-text">{{ truncateText(agent.last_reflection, 80) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Table View -->
      <div v-else class="table-view">
        <el-table :data="filteredAgents" stripe style="width: 100%">
          <el-table-column prop="display_name" label="Agent" width="180">
            <template #default="{ row }">
              <div class="table-agent-name">
                <span>{{ row.display_name }}</span>
                <el-tag size="small" type="info">G{{ row.generation }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="code" label="Code" width="120" />
          <el-table-column prop="status" label="Statut" width="100">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)" size="small">
                {{ getStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="operational_level" label="Niveau" width="100">
            <template #default="{ row }">
              <el-tag :type="getLevelType(row.operational_level)" size="small">
                {{ row.operational_level }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Capital" width="150">
            <template #default="{ row }">
              <div :class="row.net_profit >= 0 ? 'text-green' : 'text-red'">
                {{ fmtCurrency(row.current_capital) }} FCFA
              </div>
            </template>
          </el-table-column>
          <el-table-column label="Profit Net" width="120">
            <template #default="{ row }">
              <div :class="row.net_profit >= 0 ? 'text-green' : 'text-red'">
                {{ row.net_profit >= 0 ? '+' : '' }}{{ fmtCurrency(row.net_profit) }}
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="roi" label="ROI" width="80">
            <template #default="{ row }">
              <span :class="row.roi >= 0 ? 'text-green' : 'text-red'">
                {{ row.roi?.toFixed(1) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column label="Paris" width="80" align="center">
            <template #default="{ row }">
              {{ row.total_bets }}
            </template>
          </el-table-column>
          <el-table-column label="Gagnés" width="80" align="center">
            <template #default="{ row }">
              <span class="text-green">{{ row.winning_bets }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Taux réussite" width="100">
            <template #default="{ row }">
              <el-progress
                :percentage="getWinRate(row)"
                :show-text="true"
                :format="() => getWinRate(row) + '%'"
                :stroke-width="12"
              />
            </template>
          </el-table-column>
          <el-table-column label="Preuve" width="120">
            <template #default="{ row }">
              <el-tag :type="getProofType(row)" size="small">
                {{ getProofLevel(row) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Actions" width="100" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="selectAgent(row)">
                Détails
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- Agent Detail Drawer -->
    <el-drawer
      v-model="drawerVisible"
      :title="selectedAgent?.display_name"
      direction="rtl"
      size="50%"
      :before-close="closeDrawer"
    >
      <div v-if="selectedAgent" class="drawer-content">
        <!-- Tabs -->
        <el-tabs v-model="activeTab" class="detail-tabs">
          <!-- Profil Tab -->
          <el-tab-pane label="📋 Profil" name="profile">
            <div class="tab-content">
              <div class="profile-header">
                <div class="profile-avatar">
                  <span class="avatar-emoji-large">🤖</span>
                  <el-tag type="info" size="large">Génération {{ selectedAgent.generation }}</el-tag>
                </div>
                <div class="profile-info">
                  <h3>{{ selectedAgent.display_name }}</h3>
                  <p class="profile-code">{{ selectedAgent.code }}</p>
                  <div class="profile-badges">
                    <el-tag :type="getStatusType(selectedAgent.status)">
                      {{ getStatusLabel(selectedAgent.status) }}
                    </el-tag>
                    <el-tag :type="getLevelType(selectedAgent.operational_level)">
                      {{ selectedAgent.operational_level }}
                    </el-tag>
                  </div>
                </div>
              </div>

              <el-divider />

              <div class="info-grid">
                <div class="info-item">
                  <span class="info-label">Mission</span>
                  <span class="info-value">{{ selectedAgent.mission }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">Créé le</span>
                  <span class="info-value">{{ formatDate(selectedAgent.agent_created_at) }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">Capital mis à jour</span>
                  <span class="info-value">{{ formatDate(selectedAgent.capital_updated_at) }}</span>
                </div>
              </div>
            </div>
          </el-tab-pane>

          <!-- Capital Tab -->
          <el-tab-pane label="💰 Capital" name="capital">
            <div class="tab-content">
              <div class="capital-overview">
                <div class="capital-card main-capital">
                  <div class="capital-label">Capital actuel</div>
                  <div class="capital-value-large" :class="selectedAgent.net_profit >= 0 ? 'positive' : 'negative'">
                    {{ fmtCurrency(selectedAgent.current_capital) }} FCFA
                  </div>
                </div>
                <div class="capital-card">
                  <div class="capital-label">Capital initial</div>
                  <div class="capital-value">{{ fmtCurrency(selectedAgent.initial_capital) }} FCFA</div>
                </div>
                <div class="capital-card">
                  <div class="capital-label">Profit net</div>
                  <div class="capital-value" :class="selectedAgent.net_profit >= 0 ? 'positive' : 'negative'">
                    {{ selectedAgent.net_profit >= 0 ? '+' : '' }}{{ fmtCurrency(selectedAgent.net_profit) }} FCFA
                  </div>
                </div>
                <div class="capital-card">
                  <div class="capital-label">ROI</div>
                  <div class="capital-value" :class="selectedAgent.roi >= 0 ? 'positive' : 'negative'">
                    {{ selectedAgent.roi?.toFixed(2) }}%
                  </div>
                </div>
              </div>

              <el-divider />

              <div class="capital-details">
                <h4>Détails des paris</h4>
                <div class="detail-stats">
                  <div class="detail-stat">
                    <span class="detail-stat-label">Total paris</span>
                    <span class="detail-stat-value">{{ selectedAgent.total_bets }}</span>
                  </div>
                  <div class="detail-stat">
                    <span class="detail-stat-label">Paris gagnants</span>
                    <span class="detail-stat-value positive">{{ selectedAgent.winning_bets }}</span>
                  </div>
                  <div class="detail-stat">
                    <span class="detail-stat-label">Paris perdants</span>
                    <span class="detail-stat-value negative">{{ selectedAgent.losing_bets }}</span>
                  </div>
                  <div class="detail-stat">
                    <span class="detail-stat-label">Abstentions</span>
                    <span class="detail-stat-value">{{ selectedAgent.no_bet_count }}</span>
                  </div>
                </div>

                <el-divider />

                <h4>Indicateurs de risque</h4>
                <div class="risk-indicators">
                  <div class="risk-item">
                    <span class="risk-label">Drawdown maximum</span>
                    <el-progress
                      :percentage="selectedAgent.max_drawdown || 0"
                      :show-text="true"
                      :format="() => (selectedAgent.max_drawdown || 0).toFixed(1) + '%'"
                      :stroke-width="20"
                      color="#f56c6c"
                    />
                  </div>
                  <div class="risk-item">
                    <span class="risk-label">Capital de pointe</span>
                    <span class="risk-value">{{ fmtCurrency(selectedAgent.peak_capital) }} FCFA</span>
                  </div>
                </div>
              </div>
            </div>
          </el-tab-pane>

          <!-- Mémoire Tab -->
          <el-tab-pane label="🧠 Mémoire" name="memory">
            <div class="tab-content">
              <div class="memory-overview">
                <div class="memory-summary-card">
                  <div class="memory-stat">
                    <span class="memory-stat-label">Hypothèses</span>
                    <span class="memory-stat-value">{{ selectedAgent.hypotheses_count }}</span>
                  </div>
                  <div class="memory-stat">
                    <span class="memory-stat-label">Expériences</span>
                    <span class="memory-stat-value">{{ selectedAgent.experiments_count }}</span>
                  </div>
                  <div class="memory-stat">
                    <span class="memory-stat-label">Réussites</span>
                    <span class="memory-stat-value positive">{{ selectedAgent.successes_count }}</span>
                  </div>
                  <div class="memory-stat">
                    <span class="memory-stat-label">Échecs</span>
                    <span class="memory-stat-value negative">{{ selectedAgent.failures_count }}</span>
                  </div>
                </div>
              </div>

              <el-divider />

              <div class="memory-compartments">
                <h4>Compartiments de mémoire</h4>
                <el-descriptions :column="1" border>
                  <el-descriptions-item label="Identité">
                    Mission, spécialités, objectifs, historique des versions
                  </el-descriptions-item>
                  <el-descriptions-item label="Hypothèses">
                    Idées proposées, justifications, critères de réfutation
                  </el-descriptions-item>
                  <el-descriptions-item label="Expériences">
                    Données utilisées, paramètres, résultats, validation
                  </el-descriptions-item>
                  <el-descriptions-item label="Réussites">
                    Stratégies validées, périodes, incertitude
                  </el-descriptions-item>
                  <el-descriptions-item label="Échecs">
                    Hypothèses réfutées, pertes, conditions d'abandon
                  </el-descriptions-item>
                  <el-descriptions-item label="Calibration">
                    Probabilités estimées vs observées, fiabilité
                  </el-descriptions-item>
                  <el-descriptions-item label="Risque">
                    Drawdown, volatilité, exposition, seuils d'arrêt
                  </el-descriptions-item>
                </el-descriptions>
              </div>
            </div>
          </el-tab-pane>

          <!-- Preuve Tab -->
          <el-tab-pane label="🎯 Preuve" name="proof">
            <div class="tab-content">
              <div class="proof-overview">
                <el-result
                  :icon="getProofIcon(selectedAgent)"
                  :title="getProofLevel(selectedAgent)"
                  :sub-title="getProofDescription(selectedAgent)"
                >
                  <template #extra>
                    <div class="proof-metrics">
                      <div class="proof-metric">
                        <span class="metric-label">Paris effectués</span>
                        <span class="metric-value">{{ selectedAgent.total_bets }}</span>
                      </div>
                      <div class="proof-metric">
                        <span class="metric-label">Expériences validées</span>
                        <span class="metric-value">{{ selectedAgent.experiments_count }}</span>
                      </div>
                      <div class="proof-metric">
                        <span class="metric-label">ROI actuel</span>
                        <span class="metric-value" :class="selectedAgent.roi >= 0 ? 'positive' : 'negative'">
                          {{ selectedAgent.roi?.toFixed(1) }}%
                        </span>
                      </div>
                    </div>
                  </template>
                </el-result>
              </div>

              <el-divider />

              <div class="proof-criteria">
                <h4>Critères de validation</h4>
                <el-timeline>
                  <el-timeline-item
                    :timestamp="selectedAgent.total_bets >= 50 ? '✓' : '✗'"
                    :type="selectedAgent.total_bets >= 50 ? 'success' : 'info'"
                  >
                    Minimum 50 paris effectués
                    <span class="timeline-value">{{ selectedAgent.total_bets }}/50</span>
                  </el-timeline-item>
                  <el-timeline-item
                    :timestamp="selectedAgent.experiments_count >= 10 ? '✓' : '✗'"
                    :type="selectedAgent.experiments_count >= 10 ? 'success' : 'info'"
                  >
                    Minimum 10 expériences validées
                    <span class="timeline-value">{{ selectedAgent.experiments_count }}/10</span>
                  </el-timeline-item>
                  <el-timeline-item
                    :timestamp="selectedAgent.roi > 0 ? '✓' : '✗'"
                    :type="selectedAgent.roi > 0 ? 'success' : 'info'"
                  >
                    ROI positif
                    <span class="timeline-value">{{ selectedAgent.roi?.toFixed(1) }}%</span>
                  </el-timeline-item>
                  <el-timeline-item
                    :timestamp="selectedAgent.roi > 5 ? '✓' : '✗'"
                    :type="selectedAgent.roi > 5 ? 'success' : 'info'"
                  >
                    ROI > 5%
                    <span class="timeline-value">{{ selectedAgent.roi?.toFixed(1) }}%</span>
                  </el-timeline-item>
                </el-timeline>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useFetch } from '../useFetch'

const { data: agents, error: err } = useFetch<any[]>('/api/agents/active')
const drawerVisible = ref(false)
const selectedAgent = ref<any>(null)
const activeTab = ref('profile')
const searchQuery = ref('')
const statusFilter = ref('')
const levelFilter = ref('')
const viewMode = ref('cards')

// Computed
const filteredAgents = computed(() => {
  if (!agents.value) return []
  
  return agents.value.filter(agent => {
    const matchesSearch = !searchQuery.value || 
      agent.display_name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      agent.code.toLowerCase().includes(searchQuery.value.toLowerCase())
    
    const matchesStatus = !statusFilter.value || agent.status === statusFilter.value
    const matchesLevel = !levelFilter.value || agent.operational_level === levelFilter.value
    
    return matchesSearch && matchesStatus && matchesLevel
  })
})

const totalCapital = computed(() => {
  if (!agents.value) return 0
  return agents.value.reduce((sum, agent) => sum + (agent.current_capital || 0), 0)
})

const totalProfit = computed(() => {
  if (!agents.value) return 0
  return agents.value.reduce((sum, agent) => sum + (agent.net_profit || 0), 0)
})

const winRate = computed(() => {
  if (!agents.value) return 0
  const totalBets = agents.value.reduce((sum, agent) => sum + (agent.total_bets || 0), 0)
  const totalWins = agents.value.reduce((sum, agent) => sum + (agent.winning_bets || 0), 0)
  return totalBets > 0 ? ((totalWins / totalBets) * 100).toFixed(1) : 0
})

// Methods
function selectAgent(agent: any) {
  selectedAgent.value = agent
  drawerVisible.value = true
  activeTab.value = 'profile'
}

function closeDrawer() {
  drawerVisible.value = false
  selectedAgent.value = null
}

function fmtCurrency(value: number) {
  return value?.toLocaleString('fr-FR', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) || '0'
}

function formatDate(dateStr: string) {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('fr-FR')
}

function getStatusType(status: string) {
  const types: Record<string, string> = {
    'ACTIVE': 'success',
    'PAUSED': 'warning',
    'RETIRED': 'info',
    'SUSPENDED': 'danger'
  }
  return types[status] || 'info'
}

function getStatusLabel(status: string) {
  const labels: Record<string, string> = {
    'ACTIVE': 'Actif',
    'PAUSED': 'En pause',
    'RETIRED': 'Retraité',
    'SUSPENDED': 'Suspendu'
  }
  return labels[status] || status
}

function getLevelType(level: string) {
  const types: Record<string, string> = {
    'DECISION': 'primary',
    'RESEARCH': 'warning',
    'EVOLUTION': 'danger'
  }
  return types[level] || 'info'
}

function getProofLevel(agent: any) {
  if (agent.total_bets < 50) return 'Insuffisant'
  if (agent.roi > 5 && agent.experiments_count > 10) return 'Établi'
  if (agent.roi > 0) return 'Prometteur'
  return 'Non établi'
}

function getProofType(agent: any) {
  const level = getProofLevel(agent)
  if (level === 'Établi') return 'success'
  if (level === 'Prometteur') return 'warning'
  if (level === 'Insuffisant') return 'info'
  return 'danger'
}

function getProofIcon(agent: any) {
  const level = getProofLevel(agent)
  if (level === 'Établi') return 'CircleCheckFilled'
  if (level === 'Prometteur') return 'WarningFilled'
  return 'CircleCloseFilled'
}

function getProofDescription(agent: any) {
  const level = getProofLevel(agent)
  const descriptions: Record<string, string> = {
    'Établi': 'L\'agent a démontré une performance positive avec suffisamment de données',
    'Prometteur': 'L\'agent montre des résultats positifs mais nécessite plus de validation',
    'Insuffisant': 'Données insuffisantes pour évaluer la performance',
    'Non établi': 'L\'agent n\'a pas encore démontré de performance positive'
  }
  return descriptions[level] || 'Non évalué'
}

function getCapitalPercentage(agent: any) {
  if (!agent.initial_capital) return 0
  const percentage = ((agent.current_capital / agent.initial_capital) * 100)
  return Math.min(Math.max(percentage, 0), 100)
}

function getMemoryPercentage(value: number, max: number) {
  if (!value) return 0
  return Math.min((value / max) * 100, 100)
}

function getWinRate(agent: any) {
  if (!agent.total_bets || agent.total_bets === 0) return 0
  return ((agent.winning_bets / agent.total_bets) * 100).toFixed(0)
}

function truncateText(text: string, maxLength: number) {
  if (!text) return ''
  return text.length > maxLength ? text.substring(0, maxLength) + '...' : text
}
</script>

<style scoped>
.agents-page {
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 16px;
}

.summary-card {
  background: var(--bg-alt);
  padding: 16px 24px;
  border-radius: 8px;
  min-width: 150px;
}

.summary-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}

.summary-value {
  font-size: 20px;
  font-weight: 600;
}

.error-banner {
  margin-bottom: 24px;
}

.empty-state {
  display: flex;
  justify-content: center;
  padding: 60px 0;
}

.main-content {
  min-height: 400px;
}

.filters-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  align-items: center;
}

.view-toggle {
  margin-left: auto;
}

/* Cards View */
.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 20px;
}

.agent-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.agent-card:hover {
  border-color: var(--gold);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.agent-avatar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 50px;
  height: 50px;
  background: var(--bg-alt);
  border-radius: 50%;
}

.avatar-emoji {
  font-size: 24px;
}

.generation-badge {
  position: absolute;
  bottom: -4px;
  right: -4px;
  background: var(--gold);
  color: white;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 10px;
}

.agent-info {
  flex: 1;
}

.agent-name {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}

.agent-code {
  font-size: 12px;
  color: var(--muted);
}

.agent-status {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-end;
}

.card-section {
  margin-bottom: 16px;
}

.section-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.capital-section {
  background: var(--bg-alt);
  padding: 16px;
  border-radius: 8px;
}

.capital-display {
  margin-bottom: 12px;
}

.capital-value {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 4px;
}

.capital-value.positive {
  color: #67c23a;
}

.capital-value.negative {
  color: #f56c6c;
}

.capital-change {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.capital-change .positive {
  color: #67c23a;
}

.capital-change .negative {
  color: #f56c6c;
}

.roi-badge {
  background: var(--bg);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.capital-progress {
  margin-top: 8px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.stat-item {
  text-align: center;
  padding: 12px 8px;
  background: var(--bg-alt);
  border-radius: 8px;
}

.stat-icon {
  font-size: 20px;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 2px;
}

.stat-value.positive {
  color: #67c23a;
}

.stat-value.negative {
  color: #f56c6c;
}

.stat-label {
  font-size: 11px;
  color: var(--muted);
}

.memory-section {
  background: var(--bg-alt);
  padding: 16px;
  border-radius: 8px;
}

.memory-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.memory-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.memory-label {
  flex: 1;
  font-size: 12px;
  color: var(--muted);
}

.memory-count {
  font-size: 12px;
  font-weight: 600;
  min-width: 30px;
  text-align: right;
}

.proof-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.proof-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}

.proof-label {
  font-size: 12px;
  color: var(--muted);
}

.reflection-section {
  background: var(--bg-alt);
  padding: 12px;
  border-radius: 8px;
}

.reflection-preview {
  display: flex;
  align-items: center;
  gap: 8px;
}

.reflection-icon {
  font-size: 16px;
}

.reflection-text {
  flex: 1;
  font-size: 12px;
  color: var(--muted);
  font-style: italic;
}

/* Table View */
.table-view {
  background: var(--bg);
  border-radius: 8px;
  overflow: hidden;
}

.table-agent-name {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.text-green {
  color: #67c23a;
}

.text-red {
  color: #f56c6c;
}

/* Drawer */
.drawer-content {
  padding: 0;
}

.detail-tabs {
  padding: 0 24px;
}

.tab-content {
  padding: 24px;
}

.profile-header {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.profile-avatar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.avatar-emoji-large {
  font-size: 48px;
}

.profile-info {
  flex: 1;
}

.profile-info h3 {
  margin: 0 0 4px 0;
  font-size: 20px;
}

.profile-code {
  margin: 0 0 8px 0;
  color: var(--muted);
  font-size: 14px;
}

.profile-badges {
  display: flex;
  gap: 8px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 12px;
  color: var(--muted);
}

.info-value {
  font-size: 14px;
  font-weight: 500;
}

.capital-overview {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.capital-card {
  background: var(--bg-alt);
  padding: 20px;
  border-radius: 8px;
}

.capital-card.main-capital {
  grid-column: span 2;
}

.capital-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
}

.capital-value {
  font-size: 24px;
  font-weight: 600;
}

.capital-value-large {
  font-size: 32px;
  font-weight: 700;
}

.capital-value.positive {
  color: #67c23a;
}

.capital-value.negative {
  color: #f56c6c;
}

.detail-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.detail-stat {
  display: flex;
  justify-content: space-between;
  padding: 12px;
  background: var(--bg-alt);
  border-radius: 8px;
}

.detail-stat-label {
  font-size: 13px;
  color: var(--muted);
}

.detail-stat-value {
  font-size: 16px;
  font-weight: 600;
}

.detail-stat-value.positive {
  color: #67c23a;
}

.detail-stat-value.negative {
  color: #f56c6c;
}

.risk-indicators {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.risk-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.risk-label {
  font-size: 13px;
  color: var(--muted);
}

.risk-value {
  font-size: 16px;
  font-weight: 600;
}

.memory-overview {
  margin-bottom: 24px;
}

.memory-summary-card {
  background: var(--bg-alt);
  padding: 20px;
  border-radius: 8px;
}

.memory-stat {
  display: flex;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
}

.memory-stat:last-child {
  border-bottom: none;
}

.memory-stat-label {
  font-size: 13px;
  color: var(--muted);
}

.memory-stat-value {
  font-size: 18px;
  font-weight: 600;
}

.memory-stat-value.positive {
  color: #67c23a;
}

.memory-stat-value.negative {
  color: #f56c6c;
}

.memory-compartments h4 {
  margin: 0 0 16px 0;
}

.proof-overview {
  margin-bottom: 24px;
}

.proof-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 16px;
}

.proof-metric {
  text-align: center;
  padding: 12px;
  background: var(--bg-alt);
  border-radius: 8px;
}

.metric-label {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}

.metric-value {
  font-size: 18px;
  font-weight: 600;
}

.metric-value.positive {
  color: #67c23a;
}

.metric-value.negative {
  color: #f56c6c;
}

.proof-criteria h4 {
  margin: 0 0 16px 0;
}

.timeline-value {
  margin-left: 8px;
  font-weight: 600;
}
</style>
