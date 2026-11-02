export function saveLocal<T = any>(_key: string, _data: T): Promise<null> {
  return Promise.resolve(null)
}

export function deleteLocal(_key: string): Promise<null> {
  return Promise.resolve(null)
}

export function getLocal<T = any>(_key: string): Promise<T | null> {
  return Promise.resolve(null)
}
