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
    const saved = localStorage.getItem("voiceshift_params");
    return saved ? JSON.parse(saved) : DEFAULT_PARAMS;
  });

  const [isActive, setIsActive] = useState(false);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [inputLevel, setInputLevel] = useState(0);
  const [outputLevel, setOutputLevel] = useState(0);
  const [freqData, setFreqData] = useState<Uint8Array>(new Uint8Array(0));
  const [micPermission, setMicPermission] = useState<'pending' | 'granted' | 'denied'>('pending');
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");

  const rafRef = useRef<number | null>(null);
  const { toast } = useToast();

  useEffect(() => {
    processorRef.current = new VoiceProcessor();
    return () => {
      processorRef.current?.stop();
    };
  }, []);

  const fetchDevices = async () => {
    try {
      const devs = await navigator.mediaDevices.enumerateDevices();
      const audioInputs = devs.filter(d => d.kind === 'audioinput');
      setDevices(audioInputs);
      if (audioInputs.length > 0 && !selectedDeviceId) {
        setSelectedDeviceId(audioInputs[0].deviceId);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleStart = async () => {
    if (!processorRef.current) return;
    
    if (isActive) {
      processorRef.current.stop();
      setIsActive(false);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    try {
      await processorRef.current.start(selectedDeviceId || undefined);
      processorRef.current.setParams(params);
      processorRef.current.setMonitoring(isMonitoring);
      setMicPermission('granted');
      setIsActive(true);
      fetchDevices();
      loop();
    } catch (err) {
      console.error("Mic error", err);
      setMicPermission('denied');
      toast({
        title: "Microphone Access Denied",
        description: "Please allow microphone permissions to use VoiceShift.",
        variant: "destructive"
      });
    }
  };

  const loop = useCallback(() => {
    if (!processorRef.current?.active) return;
    
    processorRef.current.applyNoiseGate(params.noiseGateDb);
    setInputLevel(processorRef.current.getInputLevel());
    setOutputLevel(processorRef.current.getOutputLevel());
    setFreqData(processorRef.current.getFrequencyData());
    
    rafRef.current = requestAnimationFrame(loop);
  }, [params.noiseGateDb]);

  const updateParam = (key: keyof VoiceParams, value: number) => {
    const newParams = { ...params, [key]: value };
    setParams(newParams);
    processorRef.current?.setParams(newParams);
    localStorage.setItem("voiceshift_params", JSON.stringify(newParams));
  };

  const loadPreset = (newParams: VoiceParams) => {
    setParams(newParams);
    processorRef.current?.setParams(newParams);
    localStorage.setItem("voiceshift_params", JSON.stringify(newParams));
  };

  const toggleMonitor = () => {
    const next = !isMonitoring;
    setIsMonitoring(next);
    processorRef.current?.setMonitoring(next);
  };

  return (
    <div className="min-h-screen w-full bg-background text-foreground flex flex-col items-center justify-center p-4">
      <div className="max-w-6xl w-full grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Main Controls - Left/Center Column */}
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
                  <p className="text-xs text-muted-foreground uppercase tracking-widest font-mono">Audio Processor rack</p>
                </div>
              </div>
              
              <div className="flex items-center gap-4">
                <Button 
                  variant={isMonitoring ? "default" : "outline"} 
                  size="sm"
                  onClick={toggleMonitor}
                  className={`gap-2 ${isMonitoring ? 'bg-primary text-primary-foreground' : ''}`}
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

            {micPermission === 'denied' && (
              <div className="bg-destructive/10 text-destructive border border-destructive p-4 rounded-md flex items-center gap-3">
                <MicOff className="w-5 h-5" />
                <p className="text-sm font-medium">Microphone access denied. Check your browser settings.</p>
              </div>
            )}

            {/* Top row: IO selection and Spectrum */}
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
                        {d.label || `Microphone ${d.deviceId.slice(0,5)}`}
                      </SelectItem>
                    ))}
                    {devices.length === 0 && <SelectItem value="default">Default Device</SelectItem>}
                  </SelectContent>
                </Select>
                
                <div className="mt-4 flex-1">
                  <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block mb-2">Spectrum Output</label>
                  <div className="h-[120px] w-full bg-black/40 rounded-md border border-border p-1">
                    <SpectrumAnalyzer data={freqData} />
                  </div>
                </div>
              </div>
              
              {/* Meters */}
              <div className="flex items-end gap-6 px-4 pb-2">
                <VUMeter level={inputLevel} label="IN" />
                <VUMeter level={outputLevel} label="OUT" />
              </div>
            </div>
          </Card>

          {/* Parameters Rack */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="border-border bg-card p-5">
              <h3 className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-4 pb-2 border-b border-border">Pitch & Format</h3>
              <div className="space-y-6">
                <ParamSlider 
                  label="Pitch Shift" 
                  value={params.pitchSemitones} 
                  min={-12} max={12} step={1} unit=" st"
                  onChange={(v) => updateParam('pitchSemitones', v)}
                />
                <ParamSlider 
                  label="Formant Shift" 
                  value={params.formantShift} 
                  min={0.5} max={2.0} step={0.01} unit="x"
                  onChange={(v) => updateParam('formantShift', v)}
                />
                <ParamSlider 
                  label="Robotic Effect" 
                  value={params.roboticAmount} 
                  min={0} max={1} step={0.01}
                  onChange={(v) => updateParam('roboticAmount', v)}
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
                  onChange={(v) => updateParam('noiseGateDb', v)}
                />
                <ParamSlider 
                  label="Highpass Filter" 
                  value={params.highpassFreq} 
                  min={20} max={500} step={1} unit=" Hz"
                  onChange={(v) => updateParam('highpassFreq', v)}
                />
                <ParamSlider 
                  label="Output Gain" 
                  value={params.volumeOut} 
                  min={0} max={2} step={0.05} unit="x"
                  onChange={(v) => updateParam('volumeOut', v)}
                />
              </div>
            </Card>
          </div>
        </div>

        {/* Right Column - Presets */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          <PresetPanel currentParams={params} onLoadPreset={loadPreset} />
        </div>
        
      </div>
    </div>
  );
}
