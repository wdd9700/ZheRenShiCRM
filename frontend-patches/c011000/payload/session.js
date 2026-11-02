import { defineStore } from 'pinia'
import { createResource } from 'frappe-ui'
import { ref, computed } from 'vue'
import { accountBoundary } from '../../node_modules/frappe-ui/src/resources/accountBoundary'

export const sessionStore = defineStore('crm-session', () => {
  let user = ref(accountBoundary.user)
  const isLoggedIn = computed(() => !!user.value)

  const login = createResource({
    url: 'login',
    onError() {
      throw new Error(__('Invalid Email or Password'))
    },
    onSuccess() {
      accountBoundary.changed()
      window.location.assign('/crm')
    },
  })

  const logout = createResource({
    url: 'logout',
    onSuccess() {
      accountBoundary.changed()
      user.value = null
      window.location.href = '/login?redirect-to=/crm'
    },
  })

  return {
    user,
    isLoggedIn,
    login,
    logout,
  }
})
