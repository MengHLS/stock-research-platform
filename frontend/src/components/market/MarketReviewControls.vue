<script setup lang="ts">
import AppIcon from '../AppIcon'
import type { ReviewContext, ReviewWindow } from '../../market/review'

defineProps<{
  context: ReviewContext | null
  value: string
  windowValue: ReviewWindow
  windowOptions: number[]
  loading: boolean
}>()
const emit = defineEmits<{
  date: [date: string]
  window: [window: number]
  previous: []
  next: []
  latest: []
  reload: []
}>()

function chooseDate(event: Event) {
  const value = (event.target as HTMLInputElement).value
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) emit('date', value)
}

function chooseWindow(event: Event) {
  emit('window', Number((event.target as HTMLSelectElement).value))
}
</script>

<template>
  <div class="controls">
    <div class="date-stepper">
      <button
        type="button"
        :disabled="!context?.previous_trading_day"
        aria-label="前一交易日"
        @click="emit('previous')"
      >
        <AppIcon name="chevron-left" :size="15" />
      </button>
      <input
        type="date"
        :value="value"
        :min="context?.calendar_start ?? undefined"
        :max="context?.calendar_end ?? undefined"
        aria-label="观察日"
        @change="chooseDate"
      />
      <button
        type="button"
        :disabled="!context?.next_trading_day"
        aria-label="后一交易日"
        @click="emit('next')"
      >
        <AppIcon name="chevron-right" :size="15" />
      </button>
    </div>
    <button type="button" class="button" @click="emit('latest')">最近有记录日</button>
    <label class="window-control">
      <span>窗口</span>
      <select :value="windowValue" @change="chooseWindow">
        <option v-for="option in windowOptions" :key="option" :value="option">
          {{ option }} 日
        </option>
      </select>
    </label>
    <button
      type="button"
      class="button button--icon"
      :disabled="loading"
      aria-label="重新读取"
      @click="emit('reload')"
    >
      <AppIcon name="refresh" :size="14" />
      {{ loading ? '读取中' : '刷新' }}
    </button>
  </div>
</template>

<style scoped>
.controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 7px;
  flex-wrap: wrap;
}

.date-stepper {
  display: inline-flex;
  align-items: center;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
}

.date-stepper button,
.button {
  height: 29px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--fg2);
  cursor: pointer;
}

.date-stepper button {
  width: 30px;
  display: grid;
  place-items: center;
  border: 0;
  border-right: 1px solid var(--border);
}

.date-stepper button:last-child {
  border-right: 0;
  border-left: 1px solid var(--border);
}

.date-stepper button:hover:not(:disabled),
.button:hover:not(:disabled) {
  background: var(--surface3);
  color: var(--fg);
}

.date-stepper button:disabled,
.button:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}

.date-stepper input {
  width: 124px;
  height: 29px;
  padding: 0 7px;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--fg);
  font-family: var(--mono);
  font-size: 11px;
}

.button {
  padding: 0 9px;
  border-radius: var(--radius-sm);
  font-size: 10.5px;
}

.button--icon {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.window-control {
  display: inline-flex;
  align-items: center;
  height: 29px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface2);
  color: var(--muted);
  font-size: 10px;
}

.window-control span {
  padding: 0 7px;
  border-right: 1px solid var(--border);
}

.window-control select {
  height: 27px;
  padding: 0 7px;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--fg2);
  font-family: var(--mono);
  font-size: 10.5px;
}

@media (max-width: 760px) {
  .controls {
    justify-content: flex-start;
    width: 100%;
  }
}
</style>
