import './index.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createDialog } from './utils/dialogs'
import { initSocket } from './socket'
import router from './router'
import translationPlugin from './translation'
import App from './App.vue'

import {
  FrappeUI,
  Button,
  TextInput,
  FormControl,
  ErrorMessage,
  Dialog,
  Alert,
  Badge,
  setConfig,
  frappeRequest,
} from 'frappe-ui'

import { telemetryPlugin } from '@framework/ui/telemetry'
// injects the lucide SVG sprite into the DOM so the IconPicker and lucide Icons
// (used for view icons) can render from it
import { spritePlugin } from 'frappe-ui/experimental'

let globalComponents = {
  Button,
  TextInput,
  FormControl,
  ErrorMessage,
  Dialog,
  Alert,
  Badge,
}

import { accountBoundary } from '../node_modules/frappe-ui/src/resources/accountBoundary'

setConfig('resourceFetcher', frappeRequest)
accountBoundary.ready.then(() => {
  accountBoundary.assertActive()
  accountBoundary.markStage('PINIA_CREATE')
  let pinia = createPinia()

  accountBoundary.markStage('APP_CREATE')
  let app = createApp(App)
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
  for (let key in globalComponents) {
    app.component(key, globalComponents[key])
  }
  accountBoundary.markStage('TELEMETRY_PLUGIN')
  app.use(telemetryPlugin, { app_name: 'crm' })

  accountBoundary.markStage('DIALOG')
  app.config.globalProperties.$dialog = createDialog

  function mount() {
    accountBoundary.assertActive()
    accountBoundary.markStage('SOCKET')
    let socket = initSocket()
    app.config.globalProperties.$socket = socket
    accountBoundary.markStage('MOUNT')
    app.mount('#app')
    accountBoundary.markStage('READY')
  }
  if (import.meta.env.DEV) {
    window.$dialog = createDialog
    accountBoundary.markStage('DEV_CONTEXT')
    return frappeRequest({ url: '/api/method/crm.www.crm.get_context_for_dev' }).then(
      (values) => {
        for (let key in values) {
          window[key] = values[key]
        }
        mount()
      },
    )
  } else {
    mount()
  }
}).catch(() => accountBoundary.initializationFailed())
