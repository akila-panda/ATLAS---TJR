/**
 * frontend/src/components/chart/AtlasChart.tsx
 * TradingView lightweight-charts v3 candlestick — light-mode colour tokens.
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
import "./AtlasChart.css";

// Light-mode chart colours
const C = {
  ash:     "#c41c38",
  asl:     "#0a7e5c",
  accent:  "#1a54da",
  short:   "#c41c38",
  long:    "#0a7e5c",
  neutral: "#b56b00",
  bg:      "#ffffff",
  surface: "#f4f6fa",
  border:  "#dde3ee",
  text:    "#374f6b",
  dim:     "#8097b1",
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

  const m5Candles = useAtlasStore((s) => s.candles.get("5min") ?? []);
  const session   = useAtlasStore((s) => s.session);
  const signal    = useAtlasStore((s) => s.latestSignal ?? s.pendingSignal);

  // Initialise chart
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height,
      layout: {
        background:  { type: ColorType.Solid, color: C.bg },
        textColor:   C.text,
        fontFamily:  '"JetBrains Mono", monospace',
        fontSize:    11,
      },
      grid: {
        vertLines: { color: C.border, style: LineStyle.Dotted },
        horzLines: { color: C.border, style: LineStyle.Dotted },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor:  C.border,
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      timeScale: {
        borderColor:    C.border,
        timeVisible:    true,
        secondsVisible: false,
      },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor:         C.long,
      downColor:       C.short,
      borderUpColor:   C.long,
      borderDownColor: C.short,
      wickUpColor:     C.long,
      wickDownColor:   C.short,
    });

    chartRef.current  = chart;
    candleRef.current = candleSeries;

    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) chart.applyOptions({ width: entry.contentRect.width });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current  = null;
      candleRef.current = null;
    };
  }, [height]);

  // Candle updates
  useEffect(() => {
    if (!candleRef.current || m5Candles.length === 0) return;
    candleRef.current.setData(m5Candles.map(toOHLCV));
  }, [m5Candles]);

  // Price lines
  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;

    const lines: ReturnType<typeof series.createPriceLine>[] = [];

    function addLine(opts: Partial<PriceLineOptions> & { price: number; title: string; color: string; lineStyle: LineStyle; lineWidth?: 1 | 2 | 3 }) {
      const line = series!.createPriceLine({
        price:            opts.price,
        color:            opts.color,
        lineWidth:        opts.lineWidth ?? 1,
        lineStyle:        opts.lineStyle,
        axisLabelVisible: true,
        lineVisible:      true,
        title:            opts.title,
      });
      lines.push(line);
    }

    if (session?.asia_high && session.range_valid)
      addLine({ price: session.asia_high, color: C.ash, lineStyle: LineStyle.Dashed, title: `ASH — ${session.asia_high.toFixed(5)}` });
    if (session?.asia_low && session.range_valid)
      addLine({ price: session.asia_low,  color: C.asl, lineStyle: LineStyle.Dashed, title: `ASL — ${session.asia_low.toFixed(5)}` });

    if (signal?.outcome === "ENTER") {
      if (signal.entry_price > 0) addLine({ price: signal.entry_price, color: C.accent, lineStyle: LineStyle.Solid, lineWidth: 2, title: "Entry" });
      if (signal.sl_price    > 0) addLine({ price: signal.sl_price,    color: C.short,  lineStyle: LineStyle.Dashed, title: "SL" });
      if (signal.tp1_price   > 0) addLine({ price: signal.tp1_price,   color: C.long,   lineStyle: LineStyle.Dashed, title: "TP1 (40%)" });
      if (signal.tp2_price   > 0) addLine({ price: signal.tp2_price,   color: C.long,   lineStyle: LineStyle.Dashed, lineWidth: 2, title: "TP2 (35%)" });
      if (signal.tp3_price   > 0) addLine({ price: signal.tp3_price,   color: C.long,   lineStyle: LineStyle.Dashed, lineWidth: 3, title: "TP3 (25%)" });
    }

    return () => {
      lines.forEach((l) => { try { series.removePriceLine(l); } catch { /* ignore */ } });
    };
  }, [session, signal]);

  return (
    <div className="atlas-chart-wrapper">
      <div ref={containerRef} className="atlas-chart-canvas" style={{ height }} />
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
        className="atlas-range-overlay"
        style={{
          top,
          height,
          background:   "rgba(196, 28, 56, 0.04)",
          borderTop:    "1px dashed rgba(196, 28, 56, 0.22)",
          borderBottom: "1px dashed rgba(10, 126, 92, 0.22)",
        }}
      />
    );
  } catch {
    return null;
  }
}

export const AtlasChart = memo(AtlasChartInner);
