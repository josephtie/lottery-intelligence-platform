<template>
  <h2 class="page-title">🤖 Parieurs — Agents Autonomes</h2>
  <div v-if="err" class="panel"><span class="badge-err">{{ err }}</span></div>

  <div class="cards" v-if="agents?.length">
    <div v-for="agent in agents" :key="agent.agent_id" class="card agent-card">
      <div class="agent-header">
        <div class="agent-name">{{ agent.display_name }}</div>
        <div class="agent-meta">
          <span class="badge-gen">Génération {{ agent.generation }}</span>
          <span :class="getLevelClass(agent.operational_level)">{{ agent.operational_level }}</span>
          <span :class="getStatusClass(agent.status)">{{ agent.status }}</span>
        </div>
      </div>

      <div class="agent-mission">
        <div class="label">Mission</div>
        <div class="mission-text">{{ agent.mission }}</div>
      </div>

      <div class="agent-capital">
        <div class="label">Capital virtuel</div>
        <div class="value" :class="agent.net_profit >= 0 ? 'green' : 'red'">
          {{ fmtCurrency(agent.current_capital) }} FCFA
        </div>
        <div class="sub">
          Profit net: <span :class="agent.net_profit >= 0 ? 'green' : 'red'">{{ fmtCurrency(agent.net_profit) }}</span>
          (ROI: {{ agent.roi?.toFixed(2) }}%)
        </div>
      </div>

      <div class="agent-stats">
        <div class="stat">
          <div class="stat-value">{{ agent.total_bets }}</div>
          <div class="stat-label">Paris</div>
        </div>
        <div class="stat">
          <div class="stat-value green">{{ agent.winning_bets }}</div>
          <div class="stat-label">Gagnés</div>
        </div>
        <div class="stat">
          <div class="stat-value red">{{ agent.losing_bets }}</div>
          <div class="stat-label">Perdus</div>
        </div>
        <div class="stat">
          <div class="stat-value">{{ agent.no_bet_count }}</div>
          <div class="stat-label">Abstentions</div>
        </div>
      </div>

      <div class="agent-memory">
        <div class="label">Mémoire</div>
        <div class="memory-summary">
          <span>Hypothèses: {{ agent.hypotheses_count }}</span>
          <span>Expériences: {{ agent.experiments_count }}</span>
          <span>Réussites: {{ agent.successes_count }}</span>
          <span>Échecs: {{ agent.failures_count }}</span>
        </div>
      </div>

      <div class="agent-reflection" v-if="agent.last_reflection">
        <div class="label">Dernière réflexion</div>
        <div class="reflection-text">{{ agent.last_reflection }}</div>
      </div>

      <div class="agent-actions">
        <button @click="viewDetails(agent)" class="btn btn-primary">Voir détails</button>
      </div>
    </div>
  </div>

  <div v-else class="panel">
    <div class="sub">Aucun agent actif.</div>
  </div>

  <!-- Agent Detail Modal -->
  <div v-if="selectedAgent" class="modal-overlay" @click="closeModal">
    <div class="modal-content" @click.stop>
      <div class="modal-header">
        <h3>{{ selectedAgent.display_name }}</h3>
        <button @click="closeModal" class="btn-close">×</button>
      </div>

      <div class="modal-body">
        <div class="modal-section">
          <h4>Profil</h4>
          <div class="detail-row">
            <span class="detail-label">Code:</span>
            <span>{{ selectedAgent.code }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Génération:</span>
            <span>{{ selectedAgent.generation }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Statut:</span>
            <span :class="getStatusClass(selectedAgent.status)">{{ selectedAgent.status }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Niveau opérationnel:</span>
            <span :class="getLevelClass(selectedAgent.operational_level)">{{ selectedAgent.operational_level }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Mission:</span>
            <span>{{ selectedAgent.mission }}</span>
          </div>
        </div>

        <div class="modal-section">
          <h4>Capital et risque</h4>
          <div class="detail-row">
            <span class="detail-label">Capital initial:</span>
            <span>{{ fmtCurrency(selectedAgent.initial_capital) }} FCFA</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Capital actuel:</span>
            <span :class="selectedAgent.net_profit >= 0 ? 'green' : 'red'">
              {{ fmtCurrency(selectedAgent.current_capital) }} FCFA
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Profit net:</span>
            <span :class="selectedAgent.net_profit >= 0 ? 'green' : 'red'">
              {{ fmtCurrency(selectedAgent.net_profit) }} FCFA
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">ROI:</span>
            <span>{{ selectedAgent.roi?.toFixed(2) }}%</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Drawdown max:</span>
            <span class="red">{{ selectedAgent.max_drawdown?.toFixed(2) }}%</span>
          </div>
        </div>

        <div class="modal-section">
          <h4>Stratégies testées</h4>
          <div class="detail-row">
            <span class="detail-label">Expériences:</span>
            <span>{{ selectedAgent.experiments_count }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Hypothèses:</span>
            <span>{{ selectedAgent.hypotheses_count }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Réussites:</span>
            <span class="green">{{ selectedAgent.successes_count }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Échecs:</span>
            <span class="red">{{ selectedAgent.failures_count }}</span>
          </div>
        </div>

        <div class="modal-section">
          <h4>Niveau de preuve</h4>
          <div class="proof-badge">{{ getProofLevel(selectedAgent) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useFetch } from '../useFetch'

const { data: agents, error: err } = useFetch<any[]>('/api/agents/active')
const selectedAgent = ref<any>(null)

function viewDetails(agent: any) {
  selectedAgent.value = agent
}

function closeModal() {
  selectedAgent.value = null
}

function fmtCurrency(value: number) {
  return value?.toLocaleString('fr-FR', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) || '0'
}

function getStatusClass(status: string) {
  return status === 'ACTIVE' ? 'badge-ok' : status === 'RETIRED' ? 'badge-warn' : 'badge-err'
}

function getLevelClass(level: string) {
  const classes: Record<string, string> = {
    'DECISION': 'badge-info',
    'RESEARCH': 'badge-purple',
    'EVOLUTION': 'badge-gold'
  }
  return classes[level] || 'badge-info'
}

function getProofLevel(agent: any) {
  if (agent.total_bets < 50) return 'Insuffisant'
  if (agent.roi > 5 && agent.experiments_count > 10) return 'Établi'
  if (agent.roi > 0) return 'Prometteur'
  return 'Non établi'
}
</script>

<style scoped>
.agent-card {
  min-width: 320px;
  max-width: 400px;
}

.agent-header {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.agent-name {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
}

.agent-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.badge-gen {
  background: var(--bg-alt);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.agent-mission {
  margin-bottom: 16px;
}

.mission-text {
  font-size: 13px;
  color: var(--muted);
  line-height: 1.4;
}

.agent-capital {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--bg-alt);
  border-radius: 8px;
}

.agent-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 16px;
}

.stat {
  text-align: center;
  padding: 8px;
  background: var(--bg-alt);
  border-radius: 6px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 11px;
  color: var(--muted);
}

.agent-memory {
  margin-bottom: 16px;
}

.memory-summary {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--muted);
}

.agent-reflection {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--bg-alt);
  border-radius: 8px;
}

.reflection-text {
  font-size: 13px;
  font-style: italic;
  color: var(--muted);
  line-height: 1.4;
}

.agent-actions {
  display: flex;
  gap: 8px;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg);
  border-radius: 12px;
  max-width: 600px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
  padding: 24px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
}

.btn-close {
  background: none;
  border: none;
  font-size: 28px;
  cursor: pointer;
  color: var(--muted);
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-close:hover {
  color: var(--fg);
}

.modal-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.modal-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-label {
  color: var(--muted);
  font-size: 13px;
}

.proof-badge {
  display: inline-block;
  padding: 8px 16px;
  background: var(--bg-alt);
  border-radius: 6px;
  font-weight: 500;
  text-align: center;
}

.badge-purple {
  background: #7c3aed;
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.badge-gold {
  background: #f59e0b;
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}
</style>
