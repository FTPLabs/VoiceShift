import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";

interface ParamSliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  onChange: (value: number) => void;
  className?: string;
}

export function ParamSlider({
  label,
  value,
  min,
  max,
  step = 1,
  unit = "",
  onChange,
  className = ""
}: ParamSliderProps) {
  return (
    <div className={`space-y-3 ${className}`}>
      <div className="flex justify-between items-center">
        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</Label>
        <span className="text-xs font-mono text-primary">
          {Number.isInteger(step) ? value.toFixed(0) : value.toFixed(2)}{unit}
        </span>
      </div>
      <Slider
        min={min}
        max={max}
        step={step}
        value={[value]}
        onValueChange={(vals) => onChange(vals[0])}
        className="py-2 cursor-pointer"
      />
    </div>
  );
}
