/**
 * frontend/src/hooks/useAtlasData.ts
 * Periodic data polling — supplements WebSocket with REST fallback.
 */
import { useEffect } from "react";
import { useAtlasStore } from "../store/atlasStore";
import { getStatus }     from "../lib/api";

export function useAtlasData(): void {
  const { setMode, setRiskState, setLastUpdated } = useAtlasStore.getState();

  useEffect(() => {
    // Initial fetch
    void fetchStatus();

    // Poll every 30s as WebSocket fallback
    const interval = setInterval(() => { void fetchStatus(); }, 30_000);
    return () => clearInterval(interval);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function fetchStatus() {
    try {
      const data = await getStatus();
      setMode(data.mode);
      setRiskState({
        daily_loss_pct:     data.risk_state.daily_loss_pct,
        daily_loss_usd:     0,
        trades_today:       data.risk_state.trades_today,
        session_terminated: data.risk_state.session_terminated,
      });
      setLastUpdated(new Date());
    } catch {
      // Silently fail — WebSocket is primary
    }
  }
}