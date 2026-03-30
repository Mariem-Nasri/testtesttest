/**
 * usePolling.js
 * ──────────────────────────────────────────────────────────────────────────────
 * Custom hook that calls a callback function on a fixed interval.
 *
 * Usage:
 *   usePolling(callback, interval)
 *   - callback : async function to run on each tick
 *   - interval : number in ms — pass null to STOP polling
 *
 * Example:
 *   usePolling(
 *     () => fetchStatus(docId),
 *     status !== 'completed' ? 3000 : null
 *   )
 */

import { useEffect, useRef } from 'react'

export default function usePolling(callback, interval) {
  // Store latest callback in a ref so the interval doesn't go stale
  const callbackRef = useRef(callback)
  useEffect(() => { callbackRef.current = callback }, [callback])

  useEffect(() => {
    if (!interval) return  // null → polling disabled

    const tick = async () => {
      try {
        await callbackRef.current()
      } catch (err) {
        console.error('[usePolling] error:', err)
      }
    }

    const id = setInterval(tick, interval)

    // Clean up on unmount or when interval changes
    return () => clearInterval(id)
  }, [interval])
}
