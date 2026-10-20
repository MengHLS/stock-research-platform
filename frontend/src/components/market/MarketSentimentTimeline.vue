<script setup lang="ts">
import { computed } from 'vue'

import type { ReviewHistoryRow } from '../../market/review'
import { emotionRating } from '../../market/review'
import { sentimentTimeline } from '../../market/sentiment'

const props = defineProps<{
  history: ReviewHistoryRow[]
  selectedDate: string
}>()
const emit = defineEmits<{ select: [date: string] }>()

const rows = computed(() => sentimentTimeline(props.history, 14))

function barWidth(score: number | null | undefined): string {
  if (score === null || score === undefined || !Number.isFinite(score)) return '0%'
  return `${Math.max(4, Math.min(100, score))}%`
}
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <h2>情绪评级时间轴</h2>
      <span class="sub">近 14 个交易日 · 最新在上 · 缺失不按 0 处理</span>
    </header>
    <div class="panel-body">
      <div v-if="rows.length" class="timeline">
        <button
          v-for="row in rows"
          :key="row.date"
          type="button"
          class="timeline-row"
          :class="{
            selected: row.date === selectedDate,
            missing: row.emotion_score === null || row.emotion_score === undefined,
          }"
          :aria-label="`${row.date}，情绪评分 ${row.emotion_score ?? '缺失'}，${emotionRating(row.emotion_score).label}`"
          @click="emit('select', row.date)"
        >
          <span class="date">{{ row.date.slice(5) }}</span>
          <span class="track">
            <i
              :class="`bar--${emotionRating(row.emotion_score).tone}`"
              :style="{ width: barWidth(row.emotion_score) }"
            />
          </span>
          <span class="value" :class="`tone--${emotionRating(row.emotion_score).tone}`">
            {{ row.emotion_score ?? '缺失' }} {{ emotionRating(row.emotion_score).label }}
          </span>
        </button>
      </div>
      <div v-else class="empty">当前窗口没有情绪评级记录。</div>
      <p class="note">
        评级阈值：≥86 亢奋、≥71 活跃、≥51 正常、≥31 低迷，其余为冰点；评分缺失保持未知。
      </p>
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

.panel-body {
  padding: 14px 16px 16px;
}

.timeline {
  display: grid;
  gap: 5px;
}

.timeline-row {
  width: 100%;
  min-width: 0;
  display: grid;
  grid-template-columns: 68px minmax(120px, 1fr) 96px;
  align-items: center;
  gap: 10px;
  min-height: 29px;
  padding: 2px 5px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--fg2);
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--duration) var(--ease),
    background var(--duration) var(--ease);
}

.timeline-row:hover,
.timeline-row.selected {
  border-color: var(--border2);
  background: var(--surface2);
}

.timeline-row.selected {
  box-shadow: inset 2px 0 0 var(--brand);
}

.date {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 11px;
}

.track {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface3);
}

.track i {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.value {
  text-align: right;
  font-size: 10.5px;
  font-weight: 600;
  white-space: nowrap;
}

.tone--up {
  color: var(--up);
}

.tone--flat {
  color: var(--accent);
}

.tone--down {
  color: var(--down);
}

.bar--up {
  background: var(--up);
}

.bar--flat {
  background: var(--accent);
}

.bar--down {
  background: var(--down);
}

.timeline-row.missing .track {
  background:
    repeating-linear-gradient(
      135deg,
      color-mix(in oklab, var(--border2) 60%, transparent) 0 4px,
      transparent 4px 8px
    ),
    var(--surface3);
}

.timeline-row.missing .value {
  color: var(--muted);
}

.note {
  margin: 9px 0 0;
  color: var(--muted);
  font-size: 10px;
  line-height: 1.5;
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

  .timeline-row {
    grid-template-columns: 58px minmax(90px, 1fr) 88px;
    gap: 7px;
  }
}
</style>
