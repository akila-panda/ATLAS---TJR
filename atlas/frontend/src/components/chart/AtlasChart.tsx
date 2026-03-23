/**
 * frontend/src/components/chart/AtlasChart.tsx
 * TradingView lightweight-charts v3 candlestick with TJR overlays.
 * Draws ASH/ASL lines, Asia range box, sweep marker, and trade levels.
 */
/// <reference types="vite/client" />
import { useEffect, useRef, memo } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  PriceLineOptions,
  LineStyle,
  CrosshairMode,
  ColorType,
} from "lightweight-charts";
import { useAtlasStore } from "../../store/atlasStore";
import type { CandleBar, SessionState, SignalData } from "../../store/atlasStore";

// Atlas color tokens
const C = {
  ash:     "#ff4d6d",
  asl:     "#00ff9d",
  accent:  "#00d4ff",
  short:   "#ff4d6d",
  long:    "#00ff9d",
  neutral: "#ffd166",
  bg:      "#0a0c0f",
  surface: "#0f1218",
  border:  "#1e2530",
  text:    "#c8d8e8",
  dim:     "#6a7d92",
};

function toOHLCV(bar: CandleBar) {
  return {
    time:  (new Date(bar.datetime).getTime() / 1000) as unknown as import("lightweight-charts").UTCTimestamp,
    open:  bar.open,
    high:  bar.high,
    low:   bar.low,
    close: bar.close,
  };
}

interface Props {
  height?: number;
}

function AtlasChartInner({ height = 480 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef     = useRef<IChartApi | null>(null);
  const candleRef    = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const m5Candles  = useAtlasStore((s) => s.candles.get("5min") ?? []);
  const session    = useAtlasStore((s) => s.session);
  const signal     = useAtlasStore((s) => s.latestSignal ?? s.pendingSignal);

  // ── Chart initialisation ──────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height,
      layout: {
        background:  { type: ColorType.Solid, color: C.bg },
        textColor:   C.text,
        fontFamily:  '"IBM Plex Mono", monospace',
        fontSize:    11,
      },
      grid: {
        vertLines:   { color: C.border, style: LineStyle.Dotted },
        horzLines:   { color: C.border, style: LineStyle.Dotted },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: C.border,
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      timeScale: {
        borderColor:    C.border,
        timeVisible:    true,
        secondsVisible: false,
      },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor:          C.long,
      downColor:        C.short,
      borderUpColor:    C.long,
      borderDownColor:  C.short,
      wickUpColor:      C.long,
      wickDownColor:    C.short,
    });

    chartRef.current  = chart;
    candleRef.current = candleSeries;

    // Responsive resize
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current  = null;
      candleRef.current = null;
    };
  }, [height]);

  // ── Candle data updates ───────────────────────────────────────────────────
  useEffect(() => {
    if (!candleRef.current || m5Candles.length === 0) return;
    const data = m5Candles.map(toOHLCV);
    candleRef.current.setData(data);
  }, [m5Candles]);

  // ── Price lines — ASH, ASL, trade levels ─────────────────────────────────
  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;

    const lines: ReturnType<typeof series.createPriceLine>[] = [];

    function addLine(opts: Partial<PriceLineOptions> & { price: number; title: string; color: string; lineStyle: LineStyle; lineWidth?: 1 | 2 | 3; axisLabelVisible?: boolean }) {
      const line = series!.createPriceLine({
        price:            opts.price,
        color:            opts.color,
        lineWidth:        opts.lineWidth ?? 1,
        lineStyle:        opts.lineStyle,
        axisLabelVisible: opts.axisLabelVisible ?? true,
        lineVisible:      true,
        title:            opts.title,
      });
      lines.push(line);
    }

    if (session?.asia_high && session.range_valid) {
      addLine({ price: session.asia_high, color: C.ash, lineStyle: LineStyle.Dashed, title: `ASH — ${session.asia_high.toFixed(5)}` });
    }
    if (session?.asia_low && session.range_valid) {
      addLine({ price: session.asia_low, color: C.asl, lineStyle: LineStyle.Dashed, title: `ASL — ${session.asia_low.toFixed(5)}` });
    }

    if (signal?.outcome === "ENTER") {
      if (signal.entry_price > 0)
        addLine({ price: signal.entry_price, color: C.accent, lineStyle: LineStyle.Solid, lineWidth: 2, title: "Entry" });
      if (signal.sl_price > 0)
        addLine({ price: signal.sl_price,    color: C.short, lineStyle: LineStyle.Dashed, title: "SL" });
      if (signal.tp1_price > 0)
        addLine({ price: signal.tp1_price, color: C.long, lineStyle: LineStyle.Dashed, title: "TP1 (40%)" });
      if (signal.tp2_price > 0)
        addLine({ price: signal.tp2_price, color: C.long, lineStyle: LineStyle.Dashed, lineWidth: 2, title: "TP2 (35%)" });
      if (signal.tp3_price > 0)
        addLine({ price: signal.tp3_price, color: C.long, lineStyle: LineStyle.Dashed, lineWidth: 3, title: "TP3 (25%)" });
    }

    return () => {
      lines.forEach((l) => { try { series.removePriceLine(l); } catch { /* ignore */ } });
    };
  }, [session, signal]);

  return (
    <div className="w-full h-full bg-atlas-bg relative">
      <div
        ref={containerRef}
        style={{ height }}
        className="w-full"
      />
      {/* Asia range semi-transparent overlay box */}
      {session?.asia_high && session.asia_low && session.range_valid && candleRef.current && (
        <AsiaRangeOverlay
          series={candleRef.current}
          ashPrice={session.asia_high}
          aslPrice={session.asia_low}
        />
      )}
    </div>
  );
}

/** Semi-transparent Asia range band overlay (Rule 1.5c: ~10% opacity) */
function AsiaRangeOverlay({
  series,
  ashPrice,
  aslPrice,
}: {
  series:   ISeriesApi<"Candlestick">;
  ashPrice: number;
  aslPrice: number;
}) {
  try {
    const ashY = series.priceToCoordinate(ashPrice);
    const aslY = series.priceToCoordinate(aslPrice);
    if (ashY == null || aslY == null) return null;

    const top    = Math.min(ashY, aslY);
    const height = Math.abs(ashY - aslY);

    return (
      <div
        className="absolute left-0 right-0 pointer-events-none"
        style={{
          top,
          height,
          background:   "rgba(255,77,109,0.06)",
          borderTop:    "1px dashed rgba(255,77,109,0.25)",
          borderBottom: "1px dashed rgba(0,255,157,0.25)",
        }}
      />
    );
  } catch {
    return null;
  }
}

export const AtlasChart = memo(AtlasChartInner);