import './index.css'

import { createApp, nextTick } from 'vue'
import { createPinia, disposePinia } from 'pinia'
import { createDialog } from './utils/dialogs'
import { initSocket } from './socket'
import router from './router'
import translationPlugin from './translation'
import App from './App.vue'
import { createResumeAdapter } from './resumeRuntime'
import {
  FrappeUI, Button, TextInput, FormControl, ErrorMessage, Dialog, Alert, Badge,
  setConfig, frappeRequest,
} from 'frappe-ui'
import { spritePlugin } from 'frappe-ui/experimental'
import { accountBoundary } from '../node_modules/frappe-ui/src/resources/accountBoundary'

const globalComponents = { Button, TextInput, FormControl, ErrorMessage, Dialog, Alert, Badge }
let runtime = null
setConfig('resourceFetcher', frappeRequest)

function stop() {
  if (!runtime) return
  const previous = runtime
  runtime = null
  try {
    previous.socket?.removeAllListeners?.()
    previous.socket?.disconnect?.()
  } finally {
    try { previous.app?.unmount() }
    finally {
      if (previous.pinia) {
        disposePinia(previous.pinia)
        previous.pinia.state.value = {}
      }
    }
  }
}

async function boot() {
  const epoch = accountBoundary.epoch
  accountBoundary.assertRequest(epoch, 'crm.www.crm.get_context_for_dev')
  accountBoundary.markStage('PINIA_CREATE')
  const pinia = createPinia()
  runtime = { pinia }
  accountBoundary.markStage('APP_CREATE')
  const app = createApp(App)
  runtime.app = app
  accountBoundary.markStage('FRAPPE_UI_PLUGIN')
  app.use(FrappeUI)
  accountBoundary.markStage('SPRITE_PLUGIN')
  app.use(spritePlugin)
  accountBoundary.markStage('PINIA_PLUGIN')
  app.use(pinia)
  accountBoundary.markStage('ROUTER_PLUGIN')
  app.use(router)
  accountBoundary.markStage('TRANSLATION_PLUGIN')
  app.use(translationPlugin)
  accountBoundary.markStage('COMPONENTS')
  for (const key in globalComponents) app.component(key, globalComponents[key])
  accountBoundary.markStage('DIALOG')
  app.config.globalProperties.$dialog = createDialog

  if (import.meta.env.DEV) {
    window.$dialog = createDialog
    accountBoundary.markStage('DEV_CONTEXT')
    const values = await frappeRequest({ url: '/api/method/crm.www.crm.get_context_for_dev' })
    accountBoundary.assertRequest(epoch, 'crm.www.crm.get_context_for_dev')
    for (const key in values) window[key] = values[key]
  }
  accountBoundary.markStage('SOCKET')
  const socket = initSocket()
  runtime.socket = socket
  app.config.globalProperties.$socket = socket
  accountBoundary.markStage('MOUNT')
  app.mount('#app')
  accountBoundary.markStage('READY')
}

accountBoundary.ready.then(async () => {
  accountBoundary.assertActive()
  accountBoundary.setAdapter(createResumeAdapter({ router, boot, stop, nextTick,
    read: (url, params) => frappeRequest({ url, params }),
  }))
  await boot()
}).catch(() => accountBoundary.initializationFailed())
