<script setup lang="ts">
import { useRoute } from 'vue-router'
import { computed } from 'vue'
import { useAppearance } from './stores/appearance'

const route = useRoute()
const appearance = useAppearance()
const themeLabel = computed(() => (appearance.dark ? '浅色模式' : '深色模式'))
appearance.apply()
</script>

<template>
  <div class="workspace">
    <aside class="rail">
      <div class="brand">
        <span class="brand-mark">研</span>
        <div>研究工作台<small>Vue × Python</small></div>
      </div>
      <p class="nav-caption">开发框架</p>
      <nav aria-label="主导航">
        <RouterLink to="/">工程概览</RouterLink>
        <RouterLink to="/patterns">模式目录</RouterLink>
      </nav>
      <div class="rail-foot">一个仓库 · 明确模块<br />少量文档 · 可复现任务</div>
    </aside>
    <div class="content">
      <header>
        <div>
          <span class="eyebrow">RESEARCH PLATFORM</span>
          <h1>{{ route.meta.title }}</h1>
        </div>
        <div class="header-actions">
          <el-tag type="warning" effect="plain">开发骨架</el-tag>
          <el-button @click="appearance.toggle">{{ themeLabel }}</el-button>
        </div>
      </header>
      <main><RouterView /></main>
    </div>
  </div>
</template>
