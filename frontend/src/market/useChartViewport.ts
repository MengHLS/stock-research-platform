import { onBeforeUnmount, onMounted, ref } from 'vue'

import { chartTooltipPosition } from './chart'

/** Keep SVG coordinates in CSS pixels so labels and markers retain their size. */
export function useChartViewport(minimumWidth: number, initialWidth = minimumWidth) {
  const chartHost = ref<HTMLElement | null>(null)
  const width = ref(initialWidth)
  const visibleLeft = ref(0)
  const visibleWidth = ref(initialWidth)
  let observer: ResizeObserver | undefined
  let scrollHost: HTMLElement | null = null

  function measureVisible() {
    visibleLeft.value = scrollHost?.scrollLeft ?? 0
    visibleWidth.value = scrollHost?.clientWidth || width.value
  }

  function revealX(x: number) {
    if (!scrollHost) return
    if (x < visibleLeft.value + 24 || x > visibleLeft.value + visibleWidth.value - 24) {
      scrollHost.scrollLeft = Math.max(0, x - visibleWidth.value / 2)
      measureVisible()
    }
  }

  function tooltipPosition(x: number, size: number) {
    return chartTooltipPosition(x, visibleLeft.value, visibleWidth.value, size)
  }

  onMounted(() => {
    const host = chartHost.value
    if (!host) return
    scrollHost = host.parentElement
    const measure = () => {
      width.value = Math.max(minimumWidth, Math.round(host.getBoundingClientRect().width))
      measureVisible()
    }
    measure()
    observer = new ResizeObserver(measure)
    observer.observe(host)
    if (scrollHost) {
      observer.observe(scrollHost)
      scrollHost.addEventListener('scroll', measureVisible, { passive: true })
    }
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    scrollHost?.removeEventListener('scroll', measureVisible)
  })

  return { chartHost, width, revealX, tooltipPosition }
}
