export interface VoiceParams {
  pitchSemitones: number;
  formantShift: number;
  roboticAmount: number;
  noiseGateDb: number;
  volumeOut: number;
  highpassFreq: number;
  lowpassFreq: number;
  compressorThreshold: number;
  compressorRatio: number;
}

export const DEFAULT_PARAMS: VoiceParams = {
  pitchSemitones: 0,
  formantShift: 1.0,
  roboticAmount: 0.0,
  noiseGateDb: -50,
  volumeOut: 1.0,
  highpassFreq: 80,
  lowpassFreq: 16000,
  compressorThreshold: -24,
  compressorRatio: 4,
};

export class VoiceProcessor {
  private ctx: AudioContext | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private destinationNode: MediaStreamAudioDestinationNode | null = null;
  private gainIn: GainNode | null = null;
  private gainOut: GainNode | null = null;
  private pitchShifter: AudioWorkletNode | null = null;
  private highpassFilter: BiquadFilterNode | null = null;
  private lowpassFilter: BiquadFilterNode | null = null;
  private formantFilter: BiquadFilterNode | null = null;
  private compressor: DynamicsCompressorNode | null = null;
  private analyserIn: AnalyserNode | null = null;
  private analyserOut: AnalyserNode | null = null;
  private stream: MediaStream | null = null;
  private delayNode: DelayNode | null = null;
  private delayGain: GainNode | null = null;
  private dryGain: GainNode | null = null;
  private monitorAudio: HTMLAudioElement | null = null;
  private _monitoring = false;
  private isRunning = false;

  // Noise gate state
  private gateLastOpenMs = 0;
  private gateIsOpen = true;
  private readonly gateHoldMs = 120;
  private readonly gateAttackConst = 0.008;
  private readonly gateReleaseConst = 0.06;

  async start(deviceId?: string): Promise<void> {
    if (this.isRunning) return;
    const constraints: MediaStreamConstraints = {
      audio: {
        deviceId: deviceId ? { exact: deviceId } : undefined,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: false,
        sampleRate: 48000,
        channelCount: 1,
      },
    };
    this.stream = await navigator.mediaDevices.getUserMedia(constraints);
    this.ctx = new AudioContext({ sampleRate: 48000, latencyHint: 'interactive' });

    // --- Load AudioWorklet for pitch shift ---
    let workletAvailable = false;
    try {
      const workletUrl = new URL('/pitch-shift-processor.js', window.location.href).href;
      await this.ctx.audioWorklet.addModule(workletUrl);
      workletAvailable = true;
    } catch (e) {
      console.warn('[VoiceShift] AudioWorklet unavailable, pitch shift disabled:', e);
    }

    // --- Create nodes ---
    this.sourceNode = this.ctx.createMediaStreamSource(this.stream);
    this.destinationNode = this.ctx.createMediaStreamDestination();

    this.gainIn = this.ctx.createGain();
    this.gainIn.gain.value = 1.0;

    this.analyserIn = this.ctx.createAnalyser();
    this.analyserIn.fftSize = 1024;
    this.analyserIn.smoothingTimeConstant = 0.6;

    // Pitch shifter (AudioWorklet)
    if (workletAvailable) {
      this.pitchShifter = new AudioWorkletNode(this.ctx, 'pitch-shift-processor');
    }

    // Highpass — removes low rumble
    this.highpassFilter = this.ctx.createBiquadFilter();
    this.highpassFilter.type = 'highpass';
    this.highpassFilter.frequency.value = 80;
    this.highpassFilter.Q.value = 0.7;

    // Lowpass — removes hiss
    this.lowpassFilter = this.ctx.createBiquadFilter();
    this.lowpassFilter.type = 'lowpass';
    this.lowpassFilter.frequency.value = 16000;
    this.lowpassFilter.Q.value = 0.7;

    // Formant filter — peaking EQ to emphasise formant region
    this.formantFilter = this.ctx.createBiquadFilter();
    this.formantFilter.type = 'peaking';
    this.formantFilter.frequency.value = 1200;
    this.formantFilter.Q.value = 0.8;
    this.formantFilter.gain.value = 0;

    // Dynamics compressor
    this.compressor = this.ctx.createDynamicsCompressor();
    this.compressor.threshold.value = -24;
    this.compressor.knee.value = 10;
    this.compressor.ratio.value = 4;
    this.compressor.attack.value = 0.003;
    this.compressor.release.value = 0.25;

    // Robotic comb filter (delay + dry mix)
    this.delayNode = this.ctx.createDelay(0.1);
    this.delayNode.delayTime.value = 0.01;
    this.delayGain = this.ctx.createGain();
    this.delayGain.gain.value = 0;
    this.dryGain = this.ctx.createGain();
    this.dryGain.gain.value = 1;

    this.gainOut = this.ctx.createGain();
    this.gainOut.gain.value = 1.0;

    this.analyserOut = this.ctx.createAnalyser();
    this.analyserOut.fftSize = 1024;
    this.analyserOut.smoothingTimeConstant = 0.8;

    // --- Wire up the chain ---
    // Mic → GainIn → AnalyserIn → [PitchShifter?] → HP → LP → Formant → Compressor
    //   → DryGain ──┐
    //   → Delay → DelayGain ──┤
    //                          └→ GainOut → AnalyserOut → Destination
    this.sourceNode.connect(this.gainIn);
    this.gainIn.connect(this.analyserIn);

    if (this.pitchShifter) {
      this.analyserIn.connect(this.pitchShifter);
      this.pitchShifter.connect(this.highpassFilter);
    } else {
      this.analyserIn.connect(this.highpassFilter);
    }

    this.highpassFilter.connect(this.lowpassFilter);
    this.lowpassFilter.connect(this.formantFilter);
    this.formantFilter.connect(this.compressor);

    this.compressor.connect(this.dryGain);
    this.compressor.connect(this.delayNode);
    this.delayNode.connect(this.delayGain);

    this.dryGain.connect(this.gainOut);
    this.delayGain.connect(this.gainOut);

    this.gainOut.connect(this.analyserOut);
    this.analyserOut.connect(this.destinationNode);

    this.isRunning = true;
    this.gateLastOpenMs = performance.now();
    this.gateIsOpen = true;

    if (this._monitoring) this._startMonitor();
  }

  stop(): void {
    if (!this.isRunning) return;
    this._stopMonitor();
    this.sourceNode?.disconnect();
    this.gainIn?.disconnect();
    this.analyserIn?.disconnect();
    this.pitchShifter?.disconnect();
    this.highpassFilter?.disconnect();
    this.lowpassFilter?.disconnect();
    this.formantFilter?.disconnect();
    this.compressor?.disconnect();
    this.dryGain?.disconnect();
    this.delayNode?.disconnect();
    this.delayGain?.disconnect();
    this.gainOut?.disconnect();
    this.analyserOut?.disconnect();
    this.stream?.getTracks().forEach(t => t.stop());
    this.ctx?.close();
    this.ctx = null;
    this.stream = null;
    this.pitchShifter = null;
    this.isRunning = false;
  }

  setParams(params: VoiceParams): void {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;

    // Pitch shift via AudioWorklet
    if (this.pitchShifter) {
      const factor = Math.pow(2, params.pitchSemitones / 12);
      const pf = this.pitchShifter.parameters.get('pitchFactor');
      if (pf) pf.setTargetAtTime(factor, t, 0.05);
    }

    // Highpass filter
    if (this.highpassFilter)
      this.highpassFilter.frequency.setTargetAtTime(params.highpassFreq, t, 0.02);

    // Lowpass filter (affected by formant shift)
    if (this.lowpassFilter) {
      const lpFreq = Math.min(params.lowpassFreq * params.formantShift, 20000);
      this.lowpassFilter.frequency.setTargetAtTime(lpFreq, t, 0.02);
    }

    // Formant filter: shift peak frequency and boost/cut
    if (this.formantFilter) {
      // Base formant ~1200 Hz, scaled by formantShift
      const formantFreq = Math.min(Math.max(500 * params.formantShift, 200), 6000);
      const formantGain = (params.formantShift - 1.0) * 12; // ±12 dB at extremes
      this.formantFilter.frequency.setTargetAtTime(formantFreq, t, 0.05);
      this.formantFilter.gain.setTargetAtTime(formantGain, t, 0.05);
    }

    // Compressor
    if (this.compressor) {
      this.compressor.threshold.setTargetAtTime(params.compressorThreshold, t, 0.01);
      this.compressor.ratio.setTargetAtTime(params.compressorRatio, t, 0.01);
    }

    // Robotic comb filter
    if (this.delayGain && this.dryGain) {
      this.delayGain.gain.setTargetAtTime(params.roboticAmount * 0.9, t, 0.01);
      this.dryGain.gain.setTargetAtTime(1 - params.roboticAmount * 0.5, t, 0.01);
    }

    // Output gain
    if (this.gainOut)
      this.gainOut.gain.setTargetAtTime(params.volumeOut, t, 0.01);
  }

  /**
   * Noise gate with hold time to prevent dropouts between syllables.
   * Call every animation frame.
   */
  applyNoiseGate(thresholdDb: number): void {
    if (!this.analyserIn || !this.gainIn || !this.ctx) return;
    const buf = new Uint8Array(this.analyserIn.frequencyBinCount);
    this.analyserIn.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / buf.length);
    const rmsDb = rms > 0 ? 20 * Math.log10(rms) : -100;
    const now = performance.now();

    if (rmsDb >= thresholdDb) {
      // Above threshold — open gate
      this.gateLastOpenMs = now;
      if (!this.gateIsOpen) {
        this.gateIsOpen = true;
        this.gainIn.gain.setTargetAtTime(1, this.ctx.currentTime, this.gateAttackConst);
      }
    } else if (now - this.gateLastOpenMs > this.gateHoldMs) {
      // Below threshold AND held long enough — close gate
      if (this.gateIsOpen) {
        this.gateIsOpen = false;
        this.gainIn.gain.setTargetAtTime(0, this.ctx.currentTime, this.gateReleaseConst);
      }
    }
    // During hold period: gate stays open even if below threshold
  }

  getInputLevel(): number {
    if (!this.analyserIn) return 0;
    const buf = new Uint8Array(this.analyserIn.frequencyBinCount);
    this.analyserIn.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128;
      sum += v * v;
    }
    return Math.sqrt(sum / buf.length);
  }

  getOutputLevel(): number {
    if (!this.analyserOut) return 0;
    const buf = new Uint8Array(this.analyserOut.frequencyBinCount);
    this.analyserOut.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128;
      sum += v * v;
    }
    return Math.sqrt(sum / buf.length);
  }

  getFrequencyData(): Uint8Array {
    if (!this.analyserOut) return new Uint8Array(512);
    const buf = new Uint8Array(this.analyserOut.frequencyBinCount);
    this.analyserOut.getByteFrequencyData(buf);
    return buf;
  }

  setMonitoring(enabled: boolean): void {
    this._monitoring = enabled;
    if (!this.isRunning) return;
    if (enabled) this._startMonitor();
    else this._stopMonitor();
  }

  private _startMonitor(): void {
    if (!this.destinationNode) return;
    this.monitorAudio = new Audio();
    this.monitorAudio.srcObject = this.destinationNode.stream;
    this.monitorAudio.muted = false;
    this.monitorAudio.play().catch(() => {});
  }

  private _stopMonitor(): void {
    if (this.monitorAudio) {
      this.monitorAudio.pause();
      this.monitorAudio.srcObject = null;
      this.monitorAudio = null;
    }
  }

  get active(): boolean { return this.isRunning; }
  get monitoring(): boolean { return this._monitoring; }
}
