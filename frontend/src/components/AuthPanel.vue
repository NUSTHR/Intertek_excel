<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  login,
  register,
  requestPasswordReset,
  resetPassword,
} from '../api/auth-api'
import type { AuthResponse } from '../types/auth'
import AppIcon from './AppIcon.vue'

type AuthMode = 'login' | 'register' | 'forgot' | 'reset'

const props = withDefaults(defineProps<{
  externalErrorMessage?: string
}>(), {
  externalErrorMessage: '',
})

const emit = defineEmits<{
  authenticated: [response: AuthResponse]
}>()

const mode = ref<AuthMode>('login')
const email = ref('')
const password = ref('')
const resetToken = ref('')
const resetTokenPreview = ref('')
const errorMessage = ref('')
const infoMessage = ref('')
const isSubmitting = ref(false)
const displayedErrorMessage = computed(() => errorMessage.value || props.externalErrorMessage)
const passwordMinLength = computed(() => (mode.value === 'login' ? 1 : 8))
const passwordPlaceholder = computed(() =>
  mode.value === 'login' ? 'Enter password' : 'At least 8 characters',
)

const title = computed(() => {
  if (mode.value === 'register') {
    return 'Create account'
  }
  if (mode.value === 'forgot') {
    return 'Reset password'
  }
  if (mode.value === 'reset') {
    return 'Set new password'
  }
  return 'Sign in'
})

const primaryLabel = computed(() => {
  if (isSubmitting.value) {
    return 'Working...'
  }
  if (mode.value === 'register') {
    return 'Create account'
  }
  if (mode.value === 'forgot') {
    return 'Send reset link'
  }
  if (mode.value === 'reset') {
    return 'Update password'
  }
  return 'Sign in'
})

async function submitAuthForm(): Promise<void> {
  errorMessage.value = ''
  infoMessage.value = ''
  isSubmitting.value = true
  try {
    if (mode.value === 'login') {
      emit('authenticated', await login(email.value, password.value))
      return
    }
    if (mode.value === 'register') {
      emit('authenticated', await register(email.value, password.value))
      return
    }
    if (mode.value === 'forgot') {
      const response = await requestPasswordReset(email.value)
      resetTokenPreview.value = response.reset_token ?? ''
      infoMessage.value = response.reset_token
        ? 'Reset token generated. Use it below to set a new password.'
        : 'If that account exists, a reset instruction has been issued.'
      mode.value = 'reset'
      resetToken.value = response.reset_token ?? ''
      password.value = ''
      return
    }
    emit('authenticated', await resetPassword(resetToken.value, password.value))
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Unexpected error.'
  } finally {
    isSubmitting.value = false
  }
}

function switchMode(nextMode: AuthMode): void {
  mode.value = nextMode
  errorMessage.value = ''
  infoMessage.value = ''
  if (nextMode !== 'reset') {
    resetToken.value = ''
    resetTokenPreview.value = ''
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-shell">
      <aside class="auth-brand-panel">
        <div class="auth-mark">
          <AppIcon name="analytics" />
        </div>
        <div>
          <p class="eyebrow">ExcelAI Workspace</p>
          <h1>Shared Excel knowledge, verified row evidence.</h1>
        </div>
        <div class="auth-proof-list">
          <span><AppIcon name="table_chart" /> Versioned workbooks</span>
          <span><AppIcon name="chat_bubble" /> Evidence-backed chat</span>
          <span><AppIcon name="verified" /> Admin-controlled library</span>
        </div>
      </aside>

      <section class="auth-card">
        <div class="auth-card-head">
          <div>
            <p class="eyebrow">Account</p>
            <h2>{{ title }}</h2>
          </div>
          <span class="auth-card-icon"><AppIcon name="lock" /></span>
        </div>

        <form class="auth-form" @submit.prevent="submitAuthForm">
          <label v-if="mode !== 'reset'" class="auth-field">
            <span>Email</span>
            <input
              v-model="email"
              type="email"
              autocomplete="email"
              placeholder="name@company.com"
              required
            />
          </label>

          <label v-if="mode === 'reset'" class="auth-field">
            <span>Reset token</span>
            <input
              v-model="resetToken"
              type="text"
              autocomplete="one-time-code"
              placeholder="Paste reset token"
              required
            />
          </label>

          <label v-if="mode !== 'forgot'" class="auth-field">
            <span>{{ mode === 'reset' ? 'New password' : 'Password' }}</span>
            <input
              v-model="password"
              type="password"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
              :placeholder="passwordPlaceholder"
              required
              :minlength="passwordMinLength"
            />
          </label>

          <div v-if="resetTokenPreview" class="auth-reset-token">
            <span>Development reset token</span>
            <code>{{ resetTokenPreview }}</code>
          </div>

          <p v-if="infoMessage" class="status-note tone-success">{{ infoMessage }}</p>
          <p v-if="displayedErrorMessage" class="error-note tone-error">
            {{ displayedErrorMessage }}
          </p>

          <button type="submit" class="auth-primary-button" :disabled="isSubmitting">
            <AppIcon name="login" />
            {{ primaryLabel }}
          </button>
        </form>

        <div class="auth-switch-row">
          <button v-if="mode !== 'login'" type="button" @click="switchMode('login')">
            Back to sign in
          </button>
          <button v-if="mode === 'login'" type="button" @click="switchMode('register')">
            Create account
          </button>
          <button v-if="mode === 'login'" type="button" @click="switchMode('forgot')">
            Forgot password
          </button>
          <button v-if="mode === 'forgot'" type="button" @click="switchMode('reset')">
            I have a token
          </button>
        </div>
      </section>
    </section>
  </main>
</template>
