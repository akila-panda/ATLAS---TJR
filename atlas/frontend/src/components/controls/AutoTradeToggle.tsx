/**
 * frontend/src/components/controls/AutoTradeToggle.tsx
 * Prominent AUTO/MANUAL mode toggle with confirmation dialog.
 */
import { useState } from "react";
import { useAtlasStore }        from "../../store/atlasStore";
import { setMode as apiSetMode } from "../../lib/api";
import "./AutoTradeToggle.css";

export function AutoTradeToggle() {
  const mode    = useAtlasStore((s) => s.mode);
  const setMode = useAtlasStore((s) => s.setMode);
  const [loading, setLoading] = useState(false);

  async function handleToggle() {
    const newMode = mode === "AUTO" ? "MANUAL" : "AUTO";

    const confirmed = window.confirm(
      newMode === "AUTO"
        ? "Switch to AUTO mode?\n\nATLAS will execute trades automatically without confirmation.\n\nOnly switch to AUTO after verifying at least 10 correct signals in MANUAL mode."
        : "Switch to MANUAL mode?\n\nAll signals will require your confirmation before execution."
    );

    if (!confirmed) return;

    setLoading(true);
    try {
      await apiSetMode(newMode);
      setMode(newMode);
    } catch (e) {
      console.error("mode switch failed", e);
    } finally {
      setLoading(false);
    }
  }

  const isAuto = mode === "AUTO";

  return (
    <button
      className={`auto-trade-toggle ${isAuto ? "is-auto" : "is-manual"}`}
      onClick={() => void handleToggle()}
      disabled={loading}
    >
      <div className="toggle-text">
        <span className="toggle-mode-label">
          {loading ? "Switching…" : mode}
        </span>
        <span className="toggle-sub-label">
          {isAuto ? "Executes trades automatically" : "Requires confirmation"}
        </span>
      </div>

      <div className="toggle-switch">
        <div className="toggle-knob" />
      </div>
    </button>
  );
}
