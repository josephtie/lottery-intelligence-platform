<template>
  <div class="token-gate" v-if="needsToken">
    <div class="tg-card">
      <div class="tg-title">🔐 Token requis</div>
      <div class="tg-sub">L'API exige un Bearer token (LOTTERY_API_TOKEN).</div>
      <input v-model="tok" type="password" placeholder="Bearer token"
             @keyup.enter="go" autofocus />
      <button @click="go">Connexion</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { needsToken, submitToken } from '../useFetch'

const tok = ref('')
function go() { if (tok.value.trim()) submitToken(tok.value.trim()) }
</script>

<style scoped>
.token-gate {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,.75); display: flex; align-items: center; justify-content: center;
}
.tg-card {
  background: var(--panel); border: 1px solid var(--gold);
  border-radius: 10px; padding: 28px; width: 340px; text-align: center;
}
.tg-title { color: var(--gold); font-size: 18px; font-weight: 700; margin-bottom: 8px; }
.tg-sub { color: var(--muted); font-size: 13px; margin-bottom: 16px; }
.tg-card input { width: 100%; margin-bottom: 12px; }
.tg-card button {
  width: 100%; background: var(--gold); color: #111; border: none;
  padding: 8px; border-radius: 5px; font-weight: 700; cursor: pointer;
}
</style>
