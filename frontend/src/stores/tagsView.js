import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// Onglets des vues visitées (pattern TagsView / vue-element-admin).
// La clé de déduplication est fullPath : deux query strings différentes
// sur la même vue ouvrent deux onglets (ex. /predictions?game=Cash).
export const useTagsViewStore = defineStore('tagsView', () => {
  const visitedViews = ref([])

  const cachedViews = computed(() =>
    visitedViews.value.map(v => v.name).filter(Boolean)
  )

  const addView = (view) => {
    const existing = visitedViews.value.find(v => v.fullPath === view.fullPath)
    if (existing) {
      Object.assign(existing, view)
      return
    }
    visitedViews.value.push(view)
  }

  const delView = (view) => {
    const index = visitedViews.value.findIndex(v => v.fullPath === view.fullPath)
    if (index !== -1 && !visitedViews.value[index].affix) {
      visitedViews.value.splice(index, 1)
    }
  }

  const delOthersViews = (view) => {
    visitedViews.value = visitedViews.value.filter(
      v => v.affix || v.fullPath === view.fullPath
    )
  }

  const delAllViews = () => {
    visitedViews.value = visitedViews.value.filter(v => v.affix)
  }

  const reset = () => {
    visitedViews.value = visitedViews.value.filter(v => v.affix)
  }

  return { visitedViews, cachedViews, addView, delView, delOthersViews, delAllViews, reset }
})
