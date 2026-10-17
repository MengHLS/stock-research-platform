<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'

const status = ref('检查中')
const version = ref('—')
onMounted(async () => {
  try {
    const { data } = await api.GET('/health/live')
    status.value = data?.status === 'ok' ? '已连接' : '未就绪'
    version.value = data?.version ?? '—'
  } catch {
    status.value = '未连接'
  }
})
</script>

<template>
  <section class="hero panel">
    <div class="eyebrow">FOUNDATION / 01</div>
    <h2>先把基础搭稳，<br />再把研究接进来。</h2>
    <p>
      前后端分离、业务模块清晰、接口类型自动生成。这里展示实际工程状态，不模拟研究收益或任务完成。
    </p>
    <div class="hero-bottom">
      <el-tag :type="status === '已连接' ? 'success' : 'info'">API {{ status }}</el-tag
      ><span>版本 {{ version }}</span>
    </div>
  </section>
  <div class="cards">
    <section class="panel">
      <span class="eyebrow">01 / FRONTEND</span>
      <h3>Vue 3 + TypeScript</h3>
      <p>Vite、Vue Router、Pinia、Element Plus。页面只通过有类型的 HTTP 客户端访问后台。</p>
    </section>
    <section class="panel">
      <span class="eyebrow">02 / BACKEND</span>
      <h3>FastAPI + SQLAlchemy</h3>
      <p>接口、校验和业务实现分开；Alembic 管理新工程结构，迁移不在服务启动时自动执行。</p>
    </section>
    <section class="panel">
      <span class="eyebrow">03 / EXECUTION</span>
      <h3>独立 Worker</h3>
      <p>持久化平台作业、幂等提交、租约与恢复基础。目前只注册数据库诊断，研究执行器待接入。</p>
    </section>
  </div>
  <section class="panel next-step">
    <h3>明确的下一步</h3>
    <p>
      接入真实身份与会话 → 完成私人资源验收 → 迁移模式研究与复盘。当前没有默认用户，也没有生产认证。
    </p>
    <el-alert
      title="这是可运行的开发框架，不是已上线的多用户产品。"
      type="warning"
      :closable="false"
      show-icon
    />
  </section>
</template>
