<script setup lang="ts">
import { reactive } from 'vue'

import type { LadderRead, LadderRow } from '../../market/review'
import { buildLadderGroups, compareClass, formatSignedPercent } from '../../market/review'

const props = defineProps<{
  ladder: LadderRead
  date: string
  totalLimitUp: number | null | undefined
  brokenCount: number | null | undefined
}>()
const emit = defineEmits<{ select: [row: LadderRow] }>()

const expanded = reactive<Record<string, boolean>>({})
const groups = () => buildLadderGroups(props.ladder)
const displayLimit = (key: string) => (key === 'first' ? 24 : 18)
const visibleRows = (key: string, rows: LadderRow[]) =>
  expanded[key] ? rows : rows.slice(0, displayLimit(key))

function timeLabel(row: LadderRow): string {
  if (row.broken_kind) {
    return formatSignedPercent(row.change_pct)
  }
  if (row.boards === null) return '板数未知'
  return row.limit_up_time || '封板时间未知'
}
</script>

<template>
  <section class="panel">
    <header class="panel-head">
      <h2>连板梯队</h2>
      <span class="sub">{{ date }} · 高度 × 网格 · 一格一股</span>
      <span class="grow" />
      <span class="summary num">
        涨停 {{ totalLimitUp ?? '—' }} · 断板 {{ brokenCount ?? '—' }}
      </span>
    </header>

    <div class="panel-body">
      <div v-if="groups().length" class="ladder">
        <div v-for="group in groups()" :key="group.key" class="ladder-row">
          <div class="height">
            <b>{{ group.label }}</b>
            <span>{{ group.rows.length }} 只</span>
            <small v-if="group.rows.some((row) => row.broken_kind)">
              {{ group.rows.filter((row) => row.broken_kind).length }} 断板
            </small>
          </div>
          <div class="cells">
            <button
              v-for="row in visibleRows(group.key, group.rows)"
              :key="`${group.key}-${row.symbol}-${row.broken_kind ?? ''}`"
              type="button"
              class="stock"
              :class="{
                'stock--broken': Boolean(row.broken_kind),
                'stock--unknown': row.boards === null,
              }"
              :aria-label="`${row.name}，${row.boards === null ? '板数未知' : `${row.boards}板`}${row.broken_kind ? '，已断板' : ''}`"
              @click="emit('select', row)"
            >
              <span
                class="stock-top num"
                :class="row.broken_kind ? compareClass(row.change_pct) : ''"
              >
                <span v-if="row.one_word_board && !row.broken_kind" class="one-word">一字板</span>
                <template v-else>{{ timeLabel(row) }}</template>
              </span>
              <strong>{{ row.name }}</strong>
              <span class="sector">
                {{ row.sector }}
                <em v-if="row.broken_kind">
                  {{ row.broken_kind === 'connection' ? '连板中断' : '首板未续' }}
                </em>
              </span>
            </button>
            <button
              v-if="group.rows.length > displayLimit(group.key)"
              type="button"
              class="more"
              @click="expanded[group.key] = !expanded[group.key]"
            >
              {{ expanded[group.key] ? '收起' : `展开全部 ${group.rows.length}` }}
            </button>
          </div>
        </div>
      </div>
      <div v-else class="empty">该日没有涨停记录，无法区分真实空值与缺失。</div>
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
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.panel-head h2 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 650;
}

.sub {
  color: var(--muted);
  font-size: 11.5px;
}

.grow {
  flex: 1 1 auto;
}

.panel-body {
  padding: 16px;
}

.summary {
  color: var(--muted);
  font-size: 11px;
  white-space: nowrap;
}

.ladder {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.ladder-row {
  display: grid;
  grid-template-columns: 84px minmax(0, 1fr);
  border-top: 1px solid var(--border);
}

.ladder-row:first-child {
  border-top: 0;
}

.height {
  padding: 10px 8px;
  display: grid;
  place-content: center;
  gap: 2px;
  text-align: center;
  border-right: 1px solid var(--border);
  background: color-mix(in oklab, var(--surface2) 88%, var(--brand) 4%);
}

.height b {
  color: var(--up);
  font-family: var(--mono);
  font-size: 15px;
}

.height span {
  color: var(--muted);
  font-size: 10px;
}

.height small {
  color: var(--warn);
  font-size: 9px;
}

.cells {
  padding: 9px 10px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
  gap: 6px;
}

.stock {
  min-width: 0;
  min-height: 72px;
  padding: 6px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--fg);
  cursor: pointer;
  display: grid;
  align-content: start;
  gap: 1px;
  text-align: center;
  transition:
    background var(--duration),
    border-color var(--duration),
    transform var(--duration);
}

.stock:hover {
  background: var(--surface2);
  border-color: var(--border2);
  transform: translateY(-1px);
}

.stock-top,
.sector {
  color: var(--muted);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stock strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
}

.stock .sector {
  font-size: 10px;
}

.stock .sector em {
  margin-left: 4px;
  color: var(--warn);
  font-size: 9px;
  font-style: normal;
}

.one-word {
  display: inline-block;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--up);
  color: #fff;
  font-family: var(--font);
  font-size: 9.5px;
  font-weight: 600;
}

.stock--broken {
  border-color: var(--border);
  border-style: dashed;
}

.stock--broken strong {
  color: var(--muted);
  text-decoration: line-through;
  text-decoration-thickness: 1.5px;
}

.stock--unknown {
  background: color-mix(in oklab, var(--warn) 7%, transparent);
}

.more {
  min-height: 42px;
  border: 1px dashed var(--border2);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
}

.empty {
  padding: 28px 12px;
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  text-align: center;
  color: var(--muted);
  font-size: 12px;
}

.up {
  color: var(--up);
}

.down {
  color: var(--down);
}

.flat {
  color: var(--flat);
}

@media (max-width: 620px) {
  .panel-head {
    align-items: flex-start;
  }

  .ladder-row {
    grid-template-columns: 76px minmax(0, 1fr);
  }

  .cells {
    grid-template-columns: repeat(auto-fill, minmax(82px, 1fr));
  }
}
</style>
