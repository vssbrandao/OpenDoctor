// Captura da gravação da consulta (AudioWorklet). Roda fora da tela, sem parar: recebe o áudio do microfone na
// taxa do aparelho (44,1 ou 48 kHz), reduz para 16 kHz mono (média das amostras de cada passo, um passa-baixa
// simples que basta para voz) e manda blocos de 100 ms em PCM 16 bits, com o volume (RMS) de cada bloco.
// Nada é descartado aqui: quem corta os trechos é a página, sempre entre blocos inteiros.
class ODRec extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const o = (options && options.processorOptions) || {};
    this.out = o.outRate || 16000;
    this.ratio = sampleRate / this.out;
    this.size = Math.round(this.out * (o.blockMs || 100) / 1000);
    this.buf = new Int16Array(this.size);
    this.n = 0; this.pos = 0; this.acc = 0; this.cnt = 0; this.sq = 0;
    this.on = true;
    this.port.onmessage = (e) => { if (e.data && e.data.cmd === 'stop') this.on = false; };
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return this.on;
    for (let i = 0; i < ch.length; i++) {
      this.acc += ch[i]; this.cnt++; this.pos += 1;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        let v = this.acc / this.cnt; this.acc = 0; this.cnt = 0;
        v = v > 1 ? 1 : v < -1 ? -1 : v;
        this.buf[this.n++] = v < 0 ? v * 32768 : v * 32767;
        this.sq += v * v;
        if (this.n === this.size) {
          this.port.postMessage({ pcm: this.buf, rms: Math.sqrt(this.sq / this.size) }, [this.buf.buffer]);
          this.buf = new Int16Array(this.size); this.n = 0; this.sq = 0;
        }
      }
    }
    return this.on;
  }
}
registerProcessor('od-rec', ODRec);
