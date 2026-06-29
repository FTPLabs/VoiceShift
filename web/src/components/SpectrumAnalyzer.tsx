import { useEffect, useRef } from "react";

interface SpectrumAnalyzerProps {
  data: Uint8Array;
  className?: string;
}

export function SpectrumAnalyzer({ data, className = "" }: SpectrumAnalyzerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    
    ctx.clearRect(0, 0, width, height);
    
    if (!data || data.length === 0) return;

    const barWidth = width / data.length;
    let x = 0;

    for (let i = 0; i < data.length; i++) {
      const v = data[i] / 255.0;
      const barHeight = v * height;

      ctx.fillStyle = `hsla(243, 100%, 69%, ${v})`;
      ctx.fillRect(x, height - barHeight, barWidth, barHeight);
      x += barWidth;
    }
  }, [data]);

  return (
    <canvas
      ref={canvasRef}
      className={`w-full h-full rounded-md bg-muted/20 ${className}`}
      width={512}
      height={120}
    />
  );
}
