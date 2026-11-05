import { reactive } from 'vue'
import debounce from '../utils/debounce'
import { request } from '../utils/request'
import { getLocal, saveLocal } from './local'
import { getConfig } from '../utils/config'
import { accountBoundary } from './accountBoundary'

let cached = {}
const automaticRequests = new WeakMap()
const sharedReads = new Set(['frappe.onboarding.get_onboarding_status', 'frappe.client.get',
  'frappe.client.get_list', 'crm.api.doc.get_data'])

function requestKey(options) {
  try {
    const params = JSON.stringify(options.params, (_key, value) => {
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        if (Object.prototype.toString.call(value) !== '[object Object]') throw Error('Non-plain params')
        return Object.fromEntries(Object.keys(value).sort().map(key => [key, value[key]]))
      }
      if (typeof value === 'function' || typeof value === 'symbol') throw Error('Non-data params')
      return value
    })
    return JSON.stringify([options.url, options.method, params])
  } catch { return Symbol() }
}

function automaticFetch(resource, entry) {
  resource.fetch()
  entry.promise = resource.promise
}
accountBoundary.onInvalidate(() => { cached = {} })

export function createResource(options, vm) {
  let cacheKey = null
  if (options.cache) {
    cacheKey = getCacheKey(options.cache)
    let cachedResource = cached[cacheKey]
    const entry = cachedResource && automaticRequests.get(cachedResource)
    const sameRequest = entry && entry.key === requestKey(options) &&
      entry.key === requestKey({ ...options, params: cachedResource.params || options.params }) &&
      entry.makeParams === options.makeParams && entry.resourceFetcher === options.resourceFetcher

    if (cachedResource && (!(cachedResource.auto || options.auto) || sameRequest)) {
      if (cachedResource.auto) {
        const read = options.method === 'GET' || (!options.method && sharedReads.has(options.url))
        const shared = read && !options.force && !options.makeParams && !options.debounce &&
          cachedResource.loading && cachedResource.promise === entry.promise
        if (!shared) automaticFetch(cachedResource, entry)
      }
      return cachedResource
    }
  }

  if (typeof options == 'string') {
    options = {
      url: options,
      auto: true,
    }
  }

  let fetchFunction = options.debounce
    ? debounce(fetch, options.debounce)
    : fetch

  let controller = new AbortController()

  let out = reactive({
    method: options.method,
    url: options.url,
    data: options.initialData || null,
    previousData: null,
    loading: false,
    fetched: false,
    error: null,
    promise: null,
    auto: options.auto,
    params: null,
    fetch: fetchFunction,
    reload: fetchFunction,
    submit: fetchFunction,
    abort: () => {
      generation++
      controller.abort()
      out.loading = false
    },
    reset,
    update,
    setData,
  })

  let generation = 0
  const epoch = accountBoundary.epoch
  const authAction = ['login', 'logout'].includes(options.url)
  const unsubscribe = authAction ? () => {} : accountBoundary.onInvalidate(() => {
    generation++
    controller.abort()
    out.data = null
    out.previousData = null
    out.params = null
    out.loading = false
    out.fetched = false
    unsubscribe()
  })

  function assertCurrent(id) {
    if (id !== generation) {
      throw Object.assign(new Error('Resource request superseded'), { name: 'AbortError' })
    }
    if (!authAction) accountBoundary.assertRequest(epoch, options.url)
  }

  function fetch(params, tempOptions = {}) {
    let id = ++generation
    let promise = runFetch(params, tempOptions, id)
    promise.catch(() => {})
    out.promise = promise
    accountBoundary.track(promise)
    if (id === generation) {
      out.loading = true
      out.error = null
    }
    return promise
  }

  async function runFetch(params, tempOptions, id) {
    let errorFunctions = [options.onError, tempOptions.onError]
    try {
      await accountBoundary.ready
      assertCurrent(id)
      let resourceFetcher =
        options.resourceFetcher || getConfig('resourceFetcher') || request

      if (params instanceof Event) params = null
      params = params || out.params
      if (options.makeParams) params = options.makeParams.call(vm, params)
      out.params = params
      out.previousData = null
      options.onFetch?.call(vm, out.params)

      for (let fn of [options.beforeSubmit, tempOptions.beforeSubmit]) {
        assertCurrent(id)
        fn?.call(vm, out.params)
      }

      let validateFunction = tempOptions.validate || options.validate
      if (validateFunction) {
        let invalidMessage = await validateFunction.call(vm, out.params)
        if (invalidMessage && typeof invalidMessage === 'string') {
          throw new Error(invalidMessage)
        }
      }

      assertCurrent(id)
      controller = new AbortController()
      let data = await resourceFetcher({
        ...options,
        signal: controller.signal,
        onError: undefined,
        params: params || options.params,
      })
      assertCurrent(id)
      let transformed = transform(data)
      assertCurrent(id)
      saveLocal(cacheKey, data)
      out.data = transformed
      out.fetched = true
      for (let fn of [options.onSuccess, tempOptions.onSuccess, options.onData, tempOptions.onData]) {
        assertCurrent(id)
        fn?.call(vm, data)
      }
      return out.data
    } catch (error) {
      if (id !== generation) {
        throw Object.assign(new Error('Resource request superseded'), { name: 'AbortError' })
      }
      if (error?.name === 'AbortError') throw error
      handleError(error, errorFunctions)
    } finally {
      if (id === generation) out.loading = false
    }
  }

  function update({ method, url, params, auto }) {
    if (method && method !== options.method) {
      out.method = method
    }
    if (url && url !== options.url) {
      out.url = url
    }
    if (params && params !== options.params) {
      out.params = params
    }
    if (auto !== undefined && auto !== out.auto) {
      out.auto = auto
    }
  }

  function reset() {
    out.data = options.initialData || null
    out.previousData = null
    out.loading = false
    out.fetched = false
    out.error = null
    out.params = null
    out.auto = options.auto
  }

  function handleError(error, errorFunctions) {
    out.loading = false
    out.data = null
    out.previousData = null
    out.fetched = false
    accountBoundary.failed(error, options.method === 'GET' || /(?:get_data|get_list|frappe.client.get)$/.test(options.url || ''))
    out.error = error
    for (let fn of errorFunctions) {
      if (fn) {
        fn.call(vm, error)
      }
    }
    // if no error handler is defined, use fallbackErrorHandler
    if (errorFunctions.every((fn) => fn == null)) {
      let errorHandler = getConfig('fallbackErrorHandler')
      if (errorHandler) {
        try {
          errorHandler(error)
        } catch (error) {
          // who handles the error handler?
          console.warn('Error in fallbackErrorHandler', error)
        }
      }
    }
    throw error
  }

  // usage:
  // setData(newData) or
  // setData(data => data.filter(d => !d.deleted))
  function setData(data) {
    if (typeof data === 'function') {
      data = data.call(vm, out.data)
    }
    out.data = transform(data)
  }

  function transform(data) {
    if (options.transform) {
      let returnValue = options.transform.call(vm, data)
      if (returnValue != null) {
        return returnValue
      }
    }
    return data
  }

  const automatic = { key: requestKey(options), makeParams: options.makeParams,
    resourceFetcher: options.resourceFetcher, promise: null }
  automaticRequests.set(out, automatic)
  if (cacheKey) {
    cached[cacheKey] = out
  }

  if (options.auto) {
    automaticFetch(out, automatic)
  }

  return out
}

export function getCacheKey(cacheKey) {
  if (!cacheKey) {
    return null
  }
  if (typeof cacheKey === 'string') {
    cacheKey = [cacheKey]
  }
  return JSON.stringify([accountBoundary.scope, accountBoundary.epoch, cacheKey])
}

export function getCachedResource(cacheKey) {
  cacheKey = getCacheKey(cacheKey)
  return cached[cacheKey] || null
}
