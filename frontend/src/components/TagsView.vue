<template>
  <div class="tags-view">
    <el-scrollbar class="tv-scroll">
      <div class="tv-inner">
        <router-link
          v-for="tag in visitedViews"
          :key="tag.fullPath"
          :to="{ path: tag.path, query: tag.query }"
          class="tv-tag"
          :class="isActive(tag) ? 'tv-active' : ''"
        >
          {{ tag.title }}
          <el-icon
            v-if="!tag.affix"
            class="tv-close"
            :size="12"
            @click.prevent.stop="closeSelectedTag(tag)"
          >
            <Close />
          </el-icon>
        </router-link>
      </div>
    </el-scrollbar>

    <!-- Actions groupées -->
    <el-dropdown
      v-if="visitedViews.length > 1"
      trigger="click"
      class="tv-actions"
      @command="handleCommand"
    >
      <button class="tv-menu-btn">
        <ChevronDown class="tv-chevron" />
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="others">Fermer les autres</el-dropdown-item>
          <el-dropdown-item command="all">Tout fermer</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Close } from '@element-plus/icons-vue'
import { ChevronDown } from 'lucide-vue-next'
import { useTagsViewStore } from '../stores/tagsView'

const route = useRoute()
const router = useRouter()
const tagsViewStore = useTagsViewStore()

const visitedViews = computed(() => tagsViewStore.visitedViews)

const isActive = (tag) => tag.fullPath === route.fullPath

const closeSelectedTag = (tag) => {
  tagsViewStore.delView(tag)
  if (isActive(tag)) {
    toLastView()
  }
}

const toLastView = () => {
  const lastView = visitedViews.value.slice(-1)[0]
  // route racine du projet (le Dashboard est la vue d'accueil)
  router.push(lastView ? lastView.fullPath : '/')
}

const handleCommand = (command) => {
  if (command === 'others') {
    tagsViewStore.delOthersViews({
      fullPath: route.fullPath
    })
  } else if (command === 'all') {
    tagsViewStore.delAllViews()
    toLastView()
  }
}

const addTags = () => {
  const { name, meta } = route
  if (name && meta?.title) {
    tagsViewStore.addView({
      path: route.path,
      fullPath: route.fullPath,
      name: name,
      title: meta.title,
      query: route.query,
      affix: !!meta.affix
    })
  }
}

watch(() => route.fullPath, addTags)

onMounted(addTags)
</script>

<style scoped>
/* Conversion du Tailwind d'origine en CSS scoped (projet sans Tailwind),
   adaptée au thème sombre LOTOTRON. */
.tags-view {
  display: flex; align-items: center;
  height: 36px; width: 100%;
  background: var(--panel, #1b1e24);
  border-bottom: 1px solid var(--border, #333);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
}
.tv-scroll { flex: 1; }
.tv-inner { display: flex; align-items: center; height: 36px; padding: 0 8px; }
.tv-tag {
  display: inline-flex; align-items: center;
  height: 24px; padding: 0 10px; margin-right: 6px;
  font-size: 12px; border-radius: 4px;
  border: 1px solid var(--border, #333);
  color: var(--muted, #8b93a1);
  background: transparent;
  text-decoration: none; white-space: nowrap;
  transition: all 0.15s;
}
.tv-tag:hover { color: var(--text, #eee); background: var(--panel-2, #22262e); }
.tv-tag.tv-active {
  background: var(--gold, #e6b455); color: #1b1e24;
  border-color: var(--gold, #e6b455); font-weight: 600;
}
.tv-close {
  margin-left: 4px; border-radius: 50%; cursor: pointer;
}
.tv-close:hover { background: rgba(0, 0, 0, 0.15); }
.tv-tag.tv-active .tv-close:hover { background: rgba(255, 255, 255, 0.25); }
.tv-actions { flex-shrink: 0; padding: 0 8px; }
.tv-menu-btn {
  display: flex; align-items: center; height: 24px; width: 26px;
  justify-content: center;
  background: transparent; color: var(--muted);
  border: 1px solid var(--border, #333); border-radius: 4px; cursor: pointer;
}
.tv-menu-btn:hover { color: var(--text); background: var(--panel-2); }
.tv-chevron { width: 14px; height: 14px; }
</style>
