<script setup lang="ts">
/**
 * Sign-in / sign-up screen.
 *
 * Two-column shell taken from the Open Design `auth.html` prototype: the brand
 * column (`BrandShowcase`) carries the product argument and the live system
 * state, the right column carries the form. The prototype's fake terminal
 * preview, demo account, verification code, SSO buttons and "forgot password"
 * are deliberately not implemented — this server has none of those capabilities,
 * and the design checklist forbids presenting a control that cannot work.
 *
 * One form with a mode switch rather than two routes: the fields are the same and
 * the prototype keeps authentication to a single screen. Errors render in one
 * place with the server's safe message; the form never echoes the password back
 * and never logs it.
 *
 * Password length is *stated* (10, the server's default) but not enforced here:
 * `minlength` on a `novalidate` form never fires, so a client-side check would be
 * a lie that also blocks a deployment which lowered the limit. The server is the
 * single authority and its error is what the user sees.
 */
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'

import AppIcon from '../components/AppIcon'
import BrandShowcase from '../components/BrandShowcase.vue'
import { brand } from '../brand'
import { useAppearance } from '../stores/appearance'
import { useSession } from '../stores/session'

const session = useSession()
const appearance = useAppearance()
const router = useRouter()

const mode = ref<'login' | 'register'>('login')
const email = ref('')
const password = ref('')
const displayName = ref('')
const invitationCode = ref('')
const localError = ref<string | null>(null)

/** Password visibility is a view toggle; the value is never logged or echoed. */
const passwordVisible = ref(false)
const emailInput = ref<HTMLInputElement | null>(null)

const isRegister = computed(() => mode.value === 'register')
const submitLabel = computed(() => (isRegister.value ? '注册并登录' : '登录'))

function switchMode(next: 'login' | 'register') {
  if (mode.value === next) return
  mode.value = next
  localError.value = null
  session.error = null
  passwordVisible.value = false
  // Focus follows the switch so a keyboard user is not stranded on the old tab.
  void nextTick(() => emailInput.value?.focus())
}

/**
 * Both tabs target one panel (`#pane-auth`), because the form is the same shape
 * in both modes — only which fields show changes. A `tablist` still owes the
 * keyboard arrow-key roving-focus behaviour, so it is implemented rather than
 * left implied by the roles.
 */
function onTabKeydown(event: KeyboardEvent) {
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(event.key)) return
  event.preventDefault()
  const next = event.key === 'ArrowLeft' || event.key === 'Home' ? 'login' : 'register'
  switchMode(next)
  void nextTick(() => document.getElementById(`tab-${next}`)?.focus())
}

async function submit() {
  localError.value = null
  if (!email.value.trim() || !password.value) {
    localError.value = '请填写邮箱和密码。'
    return
  }
  if (isRegister.value && !invitationCode.value.trim()) {
    localError.value = '请输入邀请码。没有邀请码请联系管理员。'
    return
  }
  const error = isRegister.value
    ? await session.register(
        email.value.trim(),
        password.value,
        displayName.value.trim(),
        invitationCode.value,
      )
    : await session.login(email.value.trim(), password.value)
  if (error) {
    localError.value = error
    return
  }
  password.value = ''
  const redirect = (router.currentRoute.value.query.redirect as string | undefined) ?? '/'
  await router.replace(redirect)
}
</script>

<template>
  <div class="auth">
    <BrandShowcase class="auth__showcase" />

    <section class="auth__panel" aria-label="账号">
      <div class="auth__corner">
        <button
          type="button"
          class="auth__icon"
          :aria-label="appearance.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
          @click="appearance.toggleTheme()"
        >
          <AppIcon :name="appearance.theme === 'dark' ? 'sun' : 'moon'" :size="18" />
        </button>
      </div>

      <div class="auth__form-wrap">
        <header class="auth__head">
          <h1>{{ isRegister ? '创建工作台账号' : '登录研究工作台' }}</h1>
          <p>
            {{ isRegister ? '已有账号？' : '还没有账号？' }}
            <button
              type="button"
              class="auth__link"
              @click="switchMode(isRegister ? 'login' : 'register')"
            >
              {{ isRegister ? '返回登录' : '使用邀请码注册' }}
            </button>
          </p>
        </header>

        <div class="tabs" role="tablist" aria-label="登录或注册" @keydown="onTabKeydown">
          <button
            id="tab-login"
            type="button"
            role="tab"
            :aria-selected="!isRegister"
            :tabindex="isRegister ? -1 : 0"
            aria-controls="pane-auth"
            :class="{ 'is-active': !isRegister }"
            @click="switchMode('login')"
          >
            登录
          </button>
          <button
            id="tab-register"
            type="button"
            role="tab"
            :aria-selected="isRegister"
            :tabindex="isRegister ? 0 : -1"
            aria-controls="pane-auth"
            :class="{ 'is-active': isRegister }"
            @click="switchMode('register')"
          >
            注册
          </button>
        </div>

        <form
          id="pane-auth"
          class="form"
          role="tabpanel"
          :aria-labelledby="isRegister ? 'tab-register' : 'tab-login'"
          novalidate
          @submit.prevent="submit"
        >
          <label v-if="isRegister" class="field">
            <span class="field__label">显示名称 <span class="field__opt">可选</span></span>
            <span class="control">
              <span class="control__icon"><AppIcon name="user" :size="15" /></span>
              <input
                v-model="displayName"
                class="input"
                type="text"
                autocomplete="nickname"
                maxlength="120"
                placeholder="研究台里显示的名字"
              />
            </span>
          </label>

          <label class="field">
            <span class="field__label">邮箱</span>
            <span class="control">
              <span class="control__icon"><AppIcon name="mail" :size="15" /></span>
              <input
                ref="emailInput"
                v-model="email"
                class="input"
                type="email"
                inputmode="email"
                :autocomplete="isRegister ? 'email' : 'username'"
                required
                maxlength="320"
                placeholder="you@example.com"
              />
            </span>
          </label>

          <label v-if="isRegister" class="field">
            <span class="field__label">邀请码</span>
            <span class="control">
              <span class="control__icon"><AppIcon name="key" :size="15" /></span>
              <input
                v-model="invitationCode"
                class="input"
                type="text"
                autocomplete="off"
                required
                maxlength="80"
                placeholder="rp_xxxxxxxxxxx"
              />
            </span>
            <span class="hint">管理员一次性发放，每个邀请码只能注册一个账号。</span>
          </label>

          <label class="field">
            <span class="field__label">密码</span>
            <span class="control">
              <span class="control__icon"><AppIcon name="lock" :size="15" /></span>
              <input
                v-model="password"
                class="input input--trail"
                :type="passwordVisible ? 'text' : 'password'"
                :autocomplete="isRegister ? 'new-password' : 'current-password'"
                required
                maxlength="128"
                :placeholder="isRegister ? '默认至少 10 个字符' : '输入密码'"
              />
              <span class="control__trail">
                <button
                  type="button"
                  class="control__eye"
                  :aria-label="passwordVisible ? '隐藏密码' : '显示密码'"
                  :aria-pressed="passwordVisible"
                  @click.prevent="passwordVisible = !passwordVisible"
                >
                  <AppIcon :name="passwordVisible ? 'eye-off' : 'eye'" :size="16" />
                </button>
              </span>
            </span>
            <span v-if="isRegister" class="hint"> 默认至少 10 个字符。 </span>
          </label>

          <p v-if="localError" class="error" role="alert">
            <AppIcon name="alert-triangle" :size="13" />
            {{ localError }}
          </p>

          <button type="submit" class="submit" :disabled="session.busy">
            <span v-if="session.busy" class="submit__spin" aria-hidden="true"></span>
            {{ session.busy ? '处理中…' : submitLabel }}
          </button>

          <p class="legal">
            {{
              brand.tagline
            }}。本平台当前为邀请制：注册需要管理员发放的邀请码，连续登录失败会被锁定。
          </p>
        </form>
      </div>
    </section>
  </div>
</template>

<style scoped>
.auth {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1.12fr) minmax(0, 1fr);
  background: var(--bg);
}

.auth__panel {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 28px;
  background: var(--bg);
}

.auth__corner {
  position: absolute;
  top: 18px;
  right: 20px;
}

.auth__icon {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg2);
  cursor: pointer;
}

.auth__icon:hover {
  background: var(--surface2);
  color: var(--fg);
}

.auth__form-wrap {
  width: 100%;
  max-width: 396px;
  display: grid;
  gap: 20px;
}

.auth__head {
  display: grid;
  gap: 6px;
}

.auth__head h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.3;
}

.auth__head p {
  margin: 0;
  font-size: 12.5px;
  color: var(--fg2);
  line-height: 1.6;
}

.auth__link {
  background: none;
  border: 0;
  padding: 0;
  font-size: 12.5px;
  color: var(--accent);
  cursor: pointer;
  border-bottom: 1px solid color-mix(in oklab, var(--accent) 40%, transparent);
}

.auth__link:hover {
  color: var(--fg);
}

.tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
  padding: 3px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.tabs button {
  appearance: none;
  border: 0;
  background: transparent;
  cursor: pointer;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 600;
  color: var(--fg2);
  transition:
    color var(--duration) var(--ease),
    background var(--duration) var(--ease);
}

.tabs button:hover {
  color: var(--fg);
}

.tabs button.is-active {
  background: var(--surface);
  color: var(--fg);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.03),
    0 2px 8px rgba(0, 0, 0, 0.25);
}

.form {
  display: grid;
  gap: 14px;
}

.field {
  display: grid;
  gap: 6px;
}

.field__label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 550;
  color: var(--fg2);
}

.field__opt {
  font-weight: 400;
  font-size: 10.5px;
  color: var(--fg2);
}

.control {
  position: relative;
  display: flex;
  align-items: center;
}

.control__icon {
  position: absolute;
  left: 11px;
  display: flex;
  color: var(--fg2);
  pointer-events: none;
}

.input {
  width: 100%;
  height: 42px;
  padding: 0 12px 0 36px;
  background: var(--surface);
  border: 1px solid var(--border2);
  border-radius: var(--radius);
  color: var(--fg);
  /* 16px on purpose: iOS Safari zooms the viewport when a focused input is
     smaller, and the browser then leaves the layout scrolled sideways. */
  font-size: 16px;
  font-family: inherit;
  transition:
    border-color var(--duration) var(--ease),
    box-shadow var(--duration) var(--ease);
}

.input--trail {
  padding-right: 40px;
}

/* The placeholder sits on --surface, where --muted still clears 4.5:1; it stays
   dimmer than a real value so empty and filled fields remain distinguishable. */
.input::placeholder {
  color: var(--muted);
}

.input:hover {
  border-color: color-mix(in oklab, var(--border2) 70%, var(--fg2));
}

.input:focus-visible {
  /* Colour + ring, and the global :focus-visible outline still applies on top:
     removing it would make the field indistinguishable for keyboard users. */
  border-color: color-mix(in oklab, var(--accent) 65%, var(--border2));
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--accent) 16%, transparent);
}

.control__trail {
  position: absolute;
  right: 6px;
  display: flex;
}

.control__eye {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--fg2);
  cursor: pointer;
}

.control__eye:hover {
  color: var(--fg);
  background: var(--surface2);
}

.hint {
  font-size: 10.5px;
  line-height: 1.5;
  color: var(--fg2);
}

.error {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 0;
  padding: 9px 11px;
  border-radius: var(--radius);
  /* --warn, not --up: red means "price rose" in this product, so it cannot also
     mean "this request failed". --warn also clears 4.5:1 here. */
  border: 1px solid color-mix(in oklab, var(--warn) 42%, var(--border));
  background: color-mix(in oklab, var(--warn) 9%, var(--surface2));
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--warn);
}

.error svg {
  flex: none;
  margin-top: 2px;
}

.submit {
  height: 44px;
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--brand), var(--brand2));
  color: #fff;
  font-size: 14px;
  font-weight: 650;
  letter-spacing: 0.01em;
  cursor: pointer;
  transition:
    filter var(--duration) var(--ease),
    transform var(--duration) var(--ease);
}

.submit:hover:not(:disabled) {
  filter: brightness(1.07);
}

.submit:active:not(:disabled) {
  transform: translateY(1px);
}

.submit:disabled {
  cursor: progress;
  filter: saturate(0.55) brightness(0.85);
  /* The palette's disabled treatment is a saturation drop, not an opacity that
     would push the label below contrast. */
  color: #fff;
}

.submit__spin {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.legal {
  margin: 0;
  font-size: 10px;
  line-height: 1.7;
  color: var(--fg2);
}

@media (max-width: 1020px) {
  .auth {
    grid-template-columns: minmax(0, 1fr);
  }

  .auth__panel {
    padding: 30px 20px 40px;
  }
}

@media (max-width: 560px) {
  .auth__form-wrap {
    max-width: none;
  }
}
</style>
