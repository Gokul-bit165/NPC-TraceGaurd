import { useState, useEffect, useCallback, useRef } from 'react'
import { errText } from '../api.js'

export function useApi(fetchFn, deps = [], options = {}) {
  const { immediate = true, initialData = null } = options
  const [data, setData] = useState(initialData)
  const [loading, setLoading] = useState(immediate)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState(null)
  const abortControllerRef = useRef(null)

  const execute = useCallback(async (...args) => {
    // Cancel previous in-flight request if any
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller

    setLoading(true)
    setError(null)
    setStatus(null)

    try {
      const res = await fetchFn(controller.signal, ...args)
      setData(res.data !== undefined ? res.data : res)
      setLoading(false)
      return res.data !== undefined ? res.data : res
    } catch (err) {
      if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') {
        // Request was aborted, do not update error state
        return null
      }
      setError(errText(err))
      setStatus(err?.response?.status ?? null)
      setLoading(false)
      throw err
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (immediate) {
      // The error is already in state; swallow the rejection so it is not reported as unhandled.
      execute().catch(() => {})
    }
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [execute, immediate])

  // Manual reloads report failures through `error` too, so callers can fire-and-forget.
  const reload = useCallback((...args) => execute(...args).catch(() => null), [execute])

  return { data, loading, error, status, reload, setData }
}
