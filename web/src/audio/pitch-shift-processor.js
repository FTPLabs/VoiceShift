/**
 * Pitch shift AudioWorklet processor.
 * Uses a dual read-head ring buffer with triangular crossfading.
 * Factor > 1 = pitch up, factor < 1 = pitch down.
 */
class PitchShiftProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [{
      name: 'pitchFactor',
      defaultValue: 1.0,
      minValue: 0.25,
      maxValue: 4.0,
      automationRate: 'k-rate'
    }];
  }

  constructor() {
    super();
    // Ring buffer: 8192 samples ≈ 170ms at 48kHz (must be power of 2)
    this.N = 8192;
    this.mask = this.N - 1;
    this.buf = new Float32Array(this.N);
    this.wp = 0;
    // Two read heads, half-buffer apart
    this.rp = [0.0, this.N / 2];
  }

  _read(pos) {
    const i = Math.floor(pos) & this.mask;
    const j = (i + 1) & this.mask;
    const f = pos - Math.floor(pos);
    return this.buf[i] * (1 - f) + this.buf[j] * f;
  }

  process(inputs, outputs, parameters) {
    const inp = inputs[0]?.[0];
    const outp = outputs[0]?.[0];
    if (!inp || !outp) return true;

    const factor = parameters.pitchFactor[0] ?? 1.0;
    const N = this.N;
    const halfN = N >> 1;
    const mask = this.mask;

    for (let i = 0; i < inp.length; i++) {
      // Write
      this.buf[this.wp] = inp[i];
      this.wp = (this.wp + 1) & mask;

      let out = 0;
      for (let p = 0; p < 2; p++) {
        this.rp[p] += factor;
        if (this.rp[p] >= N) this.rp[p] -= N;

        // Lag: how far behind the write pointer this read head is
        const lag = ((this.wp - this.rp[p]) + N) & mask;

        // If read head is about to overtake write, jump back by halfN
        if (lag > N - 128) {
          this.rp[p] = (this.rp[p] - halfN + N) % N;
        }

        // Triangular window over halfN
        // pos in [0, 2]: 0→0, 1→1, 2→0
        const pos = ((N - lag) / halfN);
        const w = pos < 1.0 ? pos : 2.0 - pos;

        out += w * this._read(this.rp[p]);
      }
      outp[i] = out;
    }

    return true;
  }
}

registerProcessor('pitch-shift-processor', PitchShiftProcessor);
