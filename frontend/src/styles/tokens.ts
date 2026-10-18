/**
 * Design tokens, ported from the Open Design prototype so the implementation
 * matches the reviewed design instead of inventing a second visual language.
 *
 * The prototype is a single HTML file with two token sets (dark default, light
 * override). Keeping them here as CSS variables means components never hard-code
 * a colour, and a theme switch is one attribute change.
 */
export const THEME_ATTRIBUTE = 'data-theme'
export type ThemeName = 'dark' | 'light'

/** Palette mirrored from the prototype's `:root` / `[data-theme="light"]`. */
export const tokens = {
  dark: {
    bg: '#0e1116',
    bg2: '#121722',
    surface: '#161c27',
    surface2: '#1c2331',
    surface3: '#232c3c',
    border: '#252e3e',
    border2: '#333e51',
    fg: '#e8ecf4',
    fg2: '#b3bccd',
    muted: '#7c8698',
    brand: '#ff6a1a',
    brand2: '#e02330',
    accent: '#3ec1f0',
    up: '#f6465d',
    down: '#16c784',
    flat: '#8b93a7',
    warn: '#f5a524',
    vol: '#4d8bf5',
    margin: '#f5a524',
    grid: '#1f2531',
  },
  light: {
    bg: '#f3f6fb',
    bg2: '#eaeef6',
    surface: '#ffffff',
    surface2: '#f4f6fa',
    surface3: '#e9eef6',
    border: '#e2e7ef',
    border2: '#d0d8e4',
    fg: '#0f172a',
    fg2: '#44506a',
    muted: '#68738a',
    brand: '#e8590c',
    brand2: '#c81e2b',
    accent: '#0284c7',
    up: '#d61f3b',
    down: '#0a9d63',
    flat: '#64748b',
    warn: '#b45309',
    vol: '#2563eb',
    margin: '#d97706',
    grid: '#e7ecf4',
  },
} as const
