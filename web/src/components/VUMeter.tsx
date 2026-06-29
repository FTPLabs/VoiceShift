interface VUMeterProps {
  level: number;
  label?: string;
  className?: string;
}

export function VUMeter({ level, label, className = "" }: VUMeterProps) {
  // Level is typically RMS between 0 and 1
  const heightPercent = Math.min(100, Math.max(0, level * 100));
  
  return (
    <div className={`flex flex-col items-center gap-2 ${className}`}>
      <div className="relative w-4 h-32 bg-muted/50 rounded-full overflow-hidden border border-border">
        <div 
          className="absolute bottom-0 w-full bg-primary transition-all duration-75 ease-linear rounded-full"
          style={{ height: `${heightPercent}%` }}
        />
        {/* Clip warning layer if > 95% */}
        {heightPercent > 95 && (
          <div className="absolute top-0 w-full h-2 bg-destructive" />
        )}
      </div>
      {label && <span className="text-[10px] uppercase font-bold text-muted-foreground">{label}</span>}
    </div>
  );
}
