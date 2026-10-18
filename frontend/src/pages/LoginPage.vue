<script setup lang="ts">
/**
 * Sign-in / sign-up screen.
 *
 * One form with a mode switch rather than two routes: the fields are the same and
 * the prototype keeps authentication to a single screen. Errors are rendered in
 * one place with the server's safe message; the form never echoes the password
 * back and never logs it.
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import AppIcon from '../components/AppIcon'
import { useAppearance } from '../stores/appearance'
import { useSession } from '../stores/session'

const session = useSession()
const appearance = useAppearance()
const router = useRouter()

const mode = ref<'login' | 'register'>('login')
const email = ref('')
const password = ref('')
const displayName = ref('')
const localError = ref<string | null>(null)

const isRegister = computed(() => mode.value === 'register')
const submitLabel = computed(() => (isRegister.value ? '注册并登录' : '登录'))

function switchMode(next: 'login' | 'register') {
  mode.value = next
  localError.value = null
  session.error = null
}

async function submit() {
  localError.value = null
  // Client-side guard only for empty fields: length and format policy belong to
  // the server so there is one authority.
  if (!email.value.trim() || !password.value) {
    localError.value = '请填写邮箱和密码。'
    return
  }
  const error = isRegister.value
    ? await session.register(email.value.trim(), password.value, displayName.value.trim())
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
  <div class="login">
    <button
      type="button"
      class="login__theme"
      :aria-label="appearance.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
      @click="appearance.toggleTheme()"
    >
      <AppIcon :name="appearance.theme === 'dark' ? 'sun' : 'moon'" :size="18" />
    </button>

    <form class="login__card" @submit.prevent="submit">
      <div class="login__brand">
        <span class="login__mark" aria-hidden="true">研</span>
        <div>
          <h1>研究工作台</h1>
          <p>Stock research platform</p>
        </div>
      </div>

      <div class="login__tabs" role="tablist">
        <button
          type="button"
          role="tab"
          :aria-selected="!isRegister"
          :class="{ 'is-active': !isRegister }"
          @click="switchMode('login')"
        >
          登录
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="isRegister"
          :class="{ 'is-active': isRegister }"
          @click="switchMode('register')"
        >
          注册
        </button>
      </div>

      <label v-if="isRegister" class="login__field">
        <span>显示名称（可选）</span>
        <input v-model="displayName" type="text" autocomplete="nickname" maxlength="120" />
      </label>

      <label class="login__field">
        <span>邮箱</span>
        <input
          v-model="email"
          type="email"
          autocomplete="email"
          required
          maxlength="320"
          placeholder="you@example.com"
        />
      </label>

      <label class="login__field">
        <span>密码</span>
        <input
          v-model="password"
          type="password"
          :autocomplete="isRegister ? 'new-password' : 'current-password'"
          required
          :minlength="isRegister ? 10 : undefined"
          maxlength="128"
        />
        <small v-if="isRegister">至少 10 个字符。</small>
      </label>

      <p v-if="localError" class="login__error" role="alert">{{ localError }}</p>

      <button type="submit" class="login__submit" :disabled="session.busy">
        {{ session.busy ? '处理中…' : submitLabel }}
      </button>

      <p class="login__hint">
        账号保存在本平台数据库中；未配置服务端认证时，此页面会提示认证未启用。
      </p>
    </form>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: var(--bg);
}

.login__theme {
  position: fixed;
  top: 16px;
  right: 16px;
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg2);
  cursor: pointer;
}

.login__card {
  width: min(100%, 380px);
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 28px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
}

.login__brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
}

.login__mark {
  width: 40px;
  height: 40px;
  flex: none;
  display: grid;
  place-items: center;
  border-radius: var(--radius);
  background: var(--brand);
  color: #fff;
  font-weight: 650;
}

.login__brand h1 {
  margin: 0;
  font-size: 17px;
  line-height: 1.3;
}

.login__brand p {
  margin: 0;
  font-size: 11px;
  color: var(--muted);
}

.login__tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  padding: 3px;
  background: var(--surface2);
  border-radius: var(--radius-sm);
}

.login__tabs button {
  padding: 7px;
  background: none;
  border: 0;
  border-radius: var(--radius-sm);
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
}

.login__tabs button.is-active {
  background: var(--surface);
  color: var(--fg);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.login__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--fg2);
}

.login__field input {
  padding: 9px 11px;
  background: var(--bg);
  border: 1px solid var(--border2);
  border-radius: var(--radius-sm);
  color: var(--fg);
  font-size: 14px;
  font-family: inherit;
}

.login__field input:focus {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.login__field small {
  color: var(--muted);
  font-size: 11px;
}

.login__error {
  margin: 0;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: color-mix(in oklab, var(--up) 14%, transparent);
  border: 1px solid color-mix(in oklab, var(--up) 35%, transparent);
  color: var(--up);
  font-size: 12px;
}

.login__submit {
  padding: 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--brand);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.login__submit:disabled {
  opacity: 0.6;
  cursor: progress;
}

.login__hint {
  margin: 0;
  font-size: 11px;
  line-height: 1.6;
  color: var(--muted);
}
</style>
