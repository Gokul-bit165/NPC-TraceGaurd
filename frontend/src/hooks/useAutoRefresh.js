import { useState, useEffect, useCallback, useRef } from 'react'

export function useAutoRefresh(callback, intervalMs = 30000, enabled = true) {
  const [lastUpdated, setLastUpdated] = useState(new Date())
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(enabled)
  const savedCallback = useRef(callback)

  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  const triggerRefresh = useCallback(async () => {
    setIsRefreshing(true)
    try {
      await savedCallback.current()
      setLastUpdated(new Date())
    } catch (e) {
      console.error('Auto refresh failed:', e)
    } finally {
      setIsRefreshing(false)
    }
  }, [])

  useEffect(() => {
    if (!autoRefreshEnabled) return

    const interval = setInterval(() => {
      // Avoid refreshing if page is hidden/inactive in background tab
      if (document.visibilityState === 'visible') {
        triggerRefresh()
      }
    }, intervalMs)

    return () => clearInterval(interval)
  }, [autoRefreshEnabled, intervalMs, triggerRefresh])

  return {
    lastUpdated,
    isRefreshing,
    autoRefreshEnabled,
    setAutoRefreshEnabled,
    refresh: triggerRefresh,
  }
}
