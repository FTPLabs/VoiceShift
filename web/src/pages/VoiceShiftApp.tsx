import { useState, useRef, useEffect, useCallback } from "react";
import { VoiceProcessor, VoiceParams, DEFAULT_PARAMS } from "../audio/VoiceProcessor";
import { SpectrumAnalyzer } from "@/components/SpectrumAnalyzer";
import { VUMeter } from "@/components/VUMeter";
import { ParamSlider } from "@/components/ParamSlider";
import { PresetPanel } from "@/components/PresetPanel";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card } from "@/components/ui/card";
import { Power, Mic, MicOff, Settings2, Headphones } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function VoiceShiftApp() {
  const processorRef = useRef<VoiceProcessor | null>(null);

  const [params, setParams] = useState<VoiceParams>(() => {
    try {
      const saved = localStorage.getItem("voiceshift_params");
      return saved ? (JSON.parse(saved) as VoiceParams) : DEFAULT_PARAMS;
    } catch {
      return DEFAULT_PARAMS;
    }
  });

  // Keep a ref to params so the rAF loop always reads fresh values
  // without needing to recreate the loop callback
  const paramsRef = useRef<VoiceParams>(params);
  paramsRef.current = params;

  const [isActive, setIsActive] = useState(false);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [inputLevel, setInputLevel] = useState(0);
  const [outputLevel, setOutputLevel] = useState(0);
  const [freqData, setFreqData] = useState<Uint8Array>(new Uint8Array(0));
  const [micPermission, setMicPermission] = useState<"pending" | "granted" | "denied">("pending");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");

  const rafRef = useRef<number | null>(null);
  const { toast } = useToast();

  useEffect(() => {
    processorRef.current = new VoiceProcessor();
    return () => {
      processorRef.current?.stop();
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const fetchDevices = async () => {
    try {
      const devs = await navigator.mediaDevices.enumerateDevices();
      const audioInputs = devs.filter(d => d.kind === "audioinput");
      setDevices(audioInputs);
      if (audioInputs.length > 0 && !selectedDeviceId) {
        setSelectedDeviceId(audioInputs[0].deviceId);
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Stable rAF loop — reads from paramsRef so it never goes stale
  const loop = useCallback(() => {
    const proc = processorRef.current;
    if (!proc?.active) return;
    proc.applyNoiseGate(paramsRef.current.noiseGateDb);
    setInputLevel(proc.getInputLevel());
    setOutputLevel(proc.getOutputLevel());
    setFreqData(proc.getFrequencyData());
    rafRef.current = requestAnimationFrame(loop);
  }, []); // intentionally empty — loop never needs to be recreated

  const handleStart = async () => {
    if (!processorRef.current) return;

    if (isActive) {
      processorRef.current.stop();
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      setIsActive(false);
      setInputLevel(0);
      setOutputLevel(0);
      setFreqData(new Uint8Array(0));
      return;
    }

    try {
      await processorRef.current.start(selectedDeviceId || undefined);
      processorRef.current.setParams(params);
      processorRef.current.setMonitoring(isMonitoring);
      setMicPermission("granted");
      setIsActive(true);
      fetchDevices();
      loop();
    } catch (err) {
      console.error("Mic error", err);
      setMicPermission("denied");
      toast({
        title: "Microphone Access Denied",
        description: "Please allow microphone permissions in your browser to use VoiceShift.",
        variant: "destructive",
      });
    }
  };

  const updateParam = (key: keyof VoiceParams, value: number) => {
    const newParams = { ...params, [key]: value };
    setParams(newParams);
    processorRef.current?.setParams(newParams);
    try {
      localStorage.setItem("voiceshift_params", JSON.stringify(newParams));
    } catch {}
  };

  const loadPreset = (newParams: VoiceParams) => {
    setParams(newParams);
    processorRef.current?.setParams(newParams);
    try {
      localStorage.setItem("voiceshift_params", JSON.stringify(newParams));
    } catch {}
  };

  const toggleMonitor = () => {
    const next = !isMonitoring;
    setIsMonitoring(next);
    processorRef.current?.setMonitoring(next);
  };

  return (
    <div className="min-h-screen w-full bg-background text-foreground flex flex-col items-center justify-center p-4">
      <div className="max-w-6xl w-full grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* Main Controls */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          <Card className="border-border bg-card p-6 rounded-xl flex flex-col gap-6 shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div className="flex items-center gap-3">
                <div className="bg-primary/20 p-2 rounded-md">
                  <Settings2 className="w-6 h-6 text-primary" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold tracking-tight">VoiceShift</h1>
                  <p className="text-xs text-muted-foreground uppercase tracking-widest font-mono">Audio Processor Rack</p>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <Button
                  variant={isMonitoring ? "default" : "outline"}
                  size="sm"
                  onClick={toggleMonitor}
                  className={`gap-2 ${isMonitoring ? "bg-primary text-primary-foreground" : ""}`}
                  title="Monitor: hear your processed voice through headphones"
                >
                  <Headphones className="w-4 h-4" />
                  Monitor
                </Button>
                <Button
                  variant={isActive ? "destructive" : "default"}
                  onClick={handleStart}
                  className="gap-2 font-bold px-6"
                >
                  <Power className="w-4 h-4" />
                  {isActive ? "STOP" : "START"}
                </Button>
              </div>
            </div>

            {micPermission === "denied" && (
              <div className="bg-destructive/10 text-destructive border border-destructive p-4 rounded-md flex items-center gap-3">
                <MicOff className="w-5 h-5 shrink-0" />
                <div>
                  <p className="text-sm font-semibold">Microphone access denied.</p>
                  <p className="text-xs mt-0.5 opacity-80">Click the lock icon in your browser address bar and allow microphone access, then refresh.</p>
                </div>
              </div>
            )}

            {micPermission === "pending" && !isActive && (
              <div className="bg-muted/30 border border-border p-3 rounded-md flex items-center gap-3">
                <Mic className="w-4 h-4 text-primary shrink-0" />
                <p className="text-xs text-muted-foreground">
                  Press <strong>START</strong> to begin. Enable <strong>Monitor</strong> to hear your processed voice through headphones/speakers.
                </p>
              </div>
            )}

            {/* Device + Spectrum */}
            <div className="flex flex-col md:flex-row gap-6">
              <div className="flex-1 flex flex-col gap-2">
                <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Input Device</label>
                <Select value={selectedDeviceId} onValueChange={setSelectedDeviceId} disabled={isActive}>
                  <SelectTrigger className="w-full bg-background">
                    <SelectValue placeholder="Select Microphone" />
                  </SelectTrigger>
                  <SelectContent>
                    {devices.map(d => (
                      <SelectItem key={d.deviceId} value={d.deviceId}>
                        {d.label || `Microphone ${d.deviceId.slice(0, 5)}`}
                      </SelectItem>
                    ))}
                    {devices.length === 0 && (
                      <SelectItem value="default">Default Device</SelectItem>
                    )}
                  </SelectContent>
                </Select>

                <div className="mt-4 flex-1">
                  <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block mb-2">Spectrum Output</label>
                  <div className="h-[120px] w-full bg-black/40 rounded-md border border-border p-1">
                    <SpectrumAnalyzer data={freqData} />
                  </div>
                </div>
              </div>

              {/* VU Meters */}
              <div className="flex items-end gap-6 px-4 pb-2">
                <VUMeter level={inputLevel} label="IN" />
                <VUMeter level={outputLevel} label="OUT" />
              </div>
            </div>
          </Card>

          {/* Parameter Rack */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="border-border bg-card p-5">
              <h3 className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-4 pb-2 border-b border-border">Pitch & Formant</h3>
              <div className="space-y-6">
                <ParamSlider
                  label="Pitch Shift"
                  value={params.pitchSemitones}
                  min={-12} max={12} step={1} unit=" st"
                  onChange={(v) => updateParam("pitchSemitones", v)}
                />
                <ParamSlider
                  label="Formant Shift"
                  value={params.formantShift}
                  min={0.5} max={2.0} step={0.05} unit="x"
                  onChange={(v) => updateParam("formantShift", v)}
                />
                <ParamSlider
                  label="Robotic Effect"
                  value={params.roboticAmount}
                  min={0} max={1} step={0.01}
                  onChange={(v) => updateParam("roboticAmount", v)}
                />
              </div>
            </Card>

            <Card className="border-border bg-card p-5">
              <h3 className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-4 pb-2 border-b border-border">Dynamics & EQ</h3>
              <div className="space-y-6">
                <ParamSlider
                  label="Noise Gate"
                  value={params.noiseGateDb}
                  min={-80} max={-10} step={1} unit=" dB"
                  onChange={(v) => updateParam("noiseGateDb", v)}
                />
                <ParamSlider
                  label="Highpass Filter"
                  value={params.highpassFreq}
                  min={20} max={500} step={1} unit=" Hz"
                  onChange={(v) => updateParam("highpassFreq", v)}
                />
                <ParamSlider
                  label="Compressor"
                  value={params.compressorThreshold}
                  min={-60} max={0} step={1} unit=" dB"
                  onChange={(v) => updateParam("compressorThreshold", v)}
                />
                <ParamSlider
                  label="Output Gain"
                  value={params.volumeOut}
                  min={0} max={2} step={0.05} unit="x"
                  onChange={(v) => updateParam("volumeOut", v)}
                />
              </div>
            </Card>
          </div>
        </div>

        {/* Right Column — Presets */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          <PresetPanel currentParams={params} onLoadPreset={loadPreset} />
        </div>

      </div>
    </div>
  );
}
