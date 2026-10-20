<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '../AppIcon'
import type { LadderRead, LadderRow } from '../../market/review'
import { sentimentLeaders } from '../../market/sentiment'

const props = defineProps<{
  ladder: LadderRead
  date: string
}>()
const emit = defineEmits<{ select: [row: LadderRow] }>()

const leaders = computed(() => sentimentLeaders(props.ladder, 8))
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <h2>龙头梯队</h2>
      <span class="sub">{{ date }} · 最高板与连板高度排序</span>
      <span class="grow" />
      <RouterLink class="detail-link" :to="{ path: '/market/limit-up', query: { date } }">
        涨停复盘明细
        <AppIcon name="arrow-right" :size="13" />
      </RouterLink>
    </header>
    <div class="panel-body">
      <div v-if="leaders.length" class="leaders">
        <button
          v-for="(row, index) in leaders"
          :key="`${row.symbol}-${row.limit_up_time}`"
          type="button"
          class="leader"
          :aria-label="`${row.name}，${row.boards ?? '板数未知'}板，${row.sector}`"
          @click="emit('select', row)"
        >
          <span class="rank">#{{ index + 1 }}</span>
          <span class="boards">{{ row.boards ?? '—' }} 板</span>
          <strong>{{ row.name }}</strong>
          <code>{{ row.symbol }}</code>
          <span class="meta">
            <span>{{ row.sector }}</span>
            <span>{{ row.one_word_board ? '一字' : row.limit_up_time || '时间未知' }}</span>
          </span>
        </button>
      </div>
      <div v-else class="empty">当日没有可展示的龙头梯队记录。</div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}

.panel-head h2 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 680;
}

.sub {
  color: var(--muted);
  font-size: 11px;
}

.grow {
  flex: 1 1 auto;
}

.detail-link {
  min-height: 28px;
  padding: 3px 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg2);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10.5px;
  white-space: nowrap;
}

.detail-link:hover {
  border-color: var(--border2);
  color: var(--accent);
}

.panel-body {
  padding: 14px 16px 16px;
}

.leaders {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(154px, 1fr));
  gap: 8px;
}

.leader {
  min-width: 0;
  min-height: 96px;
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--fg);
  display: grid;
  grid-template-columns: 1fr auto;
  align-content: start;
  gap: 1px 8px;
  text-align: left;
  cursor: pointer;
  transition:
    transform var(--duration) var(--ease),
    border-color var(--duration) var(--ease),
    background var(--duration) var(--ease);
}

.leader:hover {
  border-color: var(--border2);
  background: var(--surface3);
  transform: translateY(-1px);
}

.rank {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 9px;
}

.boards {
  color: var(--brand);
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
}

.leader strong {
  grid-column: 1 / -1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.leader code {
  grid-column: 1 / -1;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 9px;
}

.meta {
  grid-column: 1 / -1;
  min-width: 0;
  display: flex;
  justify-content: space-between;
  gap: 6px;
  color: var(--muted);
  font-size: 9.5px;
}

.meta span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty {
  min-height: 120px;
  display: grid;
  place-items: center;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  color: var(--muted);
  font-size: 12px;
}

@media (max-width: 620px) {
  .panel-head,
  .panel-body {
    padding-inline: 14px;
  }

  .leaders {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
