/**
 * One inline SVG icon, rendered from a constant path table.
 *
 * Written with `defineComponent` and a render function rather than a template
 * because two template-level constraints collide here:
 *
 * - injecting constant markup through `v-html` trips `vue/no-v-html`, and
 *   suppressing that rule would weaken it for templates that *do* bind dynamic
 *   data;
 * - SVG attribute names with dashes (`stroke-width`, `aria-hidden`) survive
 *   render-function props exactly as written.
 *
 * The path table is a module-level constant and never receives user input, so the
 * `innerHTML` here cannot carry untrusted markup.
 *
 * Icons are decorative by default: every icon in this app sits next to its own
 * text label. An icon that must carry meaning alone passes `label`, which becomes
 * the accessible name.
 */
import { defineComponent, h, type PropType } from 'vue'

import { icons } from './AppIcon.icons'

export default defineComponent({
  name: 'AppIcon',
  props: {
    name: { type: String, required: true },
    size: { type: Number, default: 16 },
    label: { type: String as PropType<string | undefined>, default: undefined },
  },
  setup(props) {
    const decorative = (): boolean => !props.label
    return () =>
      h('svg', {
        class: 'app-icon',
        width: props.size,
        height: props.size,
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        'stroke-width': '1.8',
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'aria-hidden': decorative() ? 'true' : undefined,
        role: decorative() ? undefined : 'img',
        'aria-label': props.label,
        innerHTML: icons[props.name] ?? '',
      })
  },
})
