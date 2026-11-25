// AudioWorklet: downsample mic audio to 16 kHz mono PCM16 and post ~200 ms chunks to the main thread.
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000; // input samples per output sample
    this.pos = 0;                    // fractional read position relative to current block
    this.last = 0;                   // last sample of previous block (for interpolation)
    this.out = new Int16Array(3200); // 200 ms @ 16 kHz
    this.n = 0;
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    const len = ch.length;
    let pos = this.pos;
    while (pos < len - 1) {
      const i = Math.floor(pos);
      const frac = pos - i;
      const a = i < 0 ? this.last : ch[i];
      const b = ch[i + 1];
      let s = a + (b - a) * frac;
      s = Math.max(-1, Math.min(1, s));
      this.out[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.n === this.out.length) {
        this.port.postMessage(this.out.buffer.slice(0));
        this.n = 0;
      }
      pos += this.ratio;
    }
    this.pos = pos - len;
    this.last = ch[len - 1];
    return true;
  }
}
registerProcessor("pcm-processor", PCMProcessor);
