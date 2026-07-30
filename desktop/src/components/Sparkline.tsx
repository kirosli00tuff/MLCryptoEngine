interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
}

/** Minimal inline sparkline; renders nothing until there are two points. */
export default function Sparkline({
  values,
  width = 120,
  height = 28,
  stroke = "var(--color-bid)",
}: SparklineProps) {
  if (values.length < 2) {
    return <div style={{ width, height }} aria-hidden />;
  }
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`)
    .join(" ");

  return (
    <svg width={width} height={height} className="block" aria-hidden>
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity="0.9"
      />
    </svg>
  );
}
