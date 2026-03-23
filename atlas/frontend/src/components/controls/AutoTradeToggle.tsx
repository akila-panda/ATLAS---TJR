/**
 * frontend/src/components/controls/AutoTradeToggle.tsx
 * Prominent AUTO/MANUAL mode toggle with confirmation dialog.
 */
import { useState } from "react";
import { useAtlasStore }  from "../../store/atlasStore";
import { setMode as apiSetMode } from "../../lib/api";

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
      onClick={() => void handleToggle()}
      disabled={loading}
      className={`
        w-full py-3 px-4 flex items-center justify-between
        border font-mono transition-all duration-200
        disabled:opacity-50 disabled:cursor-wait
        ${isAuto
          ? "bg-atlas-accent/10 border-atlas-accent text-atlas-accent hover:bg-atlas-accent/20"
          : "bg-atlas-neutral/10 border-atlas-neutral text-atlas-neutral hover:bg-atlas-neutral/20"
        }
      `}
    >
      <div className="text-left">
        <span className="block text-xs font-bold tracking-[3px] uppercase">
          {loading ? "Switching…" : mode}
        </span>
        <span className="block text-[9px] font-sans tracking-wide text-atlas-text-dim mt-0.5">
          {isAuto ? "Executes trades automatically" : "Requires confirmation"}
        </span>
      </div>
      {/* Toggle visual */}
      <div className={`w-8 h-4 rounded-full transition-colors relative ${isAuto ? "bg-atlas-accent" : "bg-atlas-neutral"}`}>
        <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-atlas-bg transition-all ${isAuto ? "left-4.5" : "left-0.5"}`} />
      </div>
    </button>
  );
}