<template>
  <LayoutHeader>
    <template #left-header>
      <h1 class="text-lg font-semibold text-ink-gray-9">团队日程</h1>
    </template>
    <template #right-header>
      <Button variant="solid" iconLeft="lucide-plus" :disabled="!ready" @click="openEditor">
        创建日程
      </Button>
    </template>
  </LayoutHeader>
  <main ref="workspace" class="crm-native-schedule min-w-0 space-y-4 px-3 pb-6 pt-3 sm:px-5" :inert="!ready">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <span class="text-sm text-ink-gray-6">当前用户：<strong id="current-user"></strong></span>
      <button id="reload-page" type="button">重新核验会话</button>
    </div>
    <p id="session-status" class="status schedule-session" role="status" aria-live="polite">数据仅在此工作区内存处理，离开后清除。</p>
    <!-- schedule-sections -->
  </main>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import { accountBoundary } from '../../node_modules/frappe-ui/src/resources/accountBoundary'
import { init } from './teamScheduleController.mjs'
import catalog from './teamScheduleCatalog.mjs'
import './teamSchedule.css'

const workspace = ref(null)
const ready = ref(false)
let dispose
let unsubscribe

function openEditor() {
  const editor = workspace.value.querySelector('#editor-section')
  editor.open = true
  editor.scrollIntoView({ block: 'start' })
  editor.querySelector('#schedule-title').focus({ preventScroll: true })
}

function start() {
  if (dispose || !workspace.value || accountBoundary.state !== 'ACTIVE') return
  const epoch = accountBoundary.epoch
  accountBoundary.assertActive(epoch)
  dispose = init(document, window, {
    root: workspace.value,
    currentUser: accountBoundary.user,
    csrfToken: window.csrf_token,
    catalog,
    standalone: false,
    autoLoad: true,
    assertSession: () => accountBoundary.assertActive(epoch),
    onAccessFailure: error => {
      if (error.status === 401 || !error.business) accountBoundary.failed(error)
    },
    recheck: () => {
      accountBoundary.pause()
      void accountBoundary.resume()
    },
  })
  ready.value = true
}

function stop() {
  ready.value = false
  dispose?.()
  dispose = undefined
}

onMounted(() => {
  unsubscribe = accountBoundary.onInvalidate(stop)
  window.addEventListener('crm-team-schedule-active', start)
  start()
})

onBeforeUnmount(() => {
  window.removeEventListener('crm-team-schedule-active', start)
  unsubscribe?.()
  stop()
})
</script>
