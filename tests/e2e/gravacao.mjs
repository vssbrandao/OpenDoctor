// Teste ponta a ponta da gravação da consulta, no Chrome sem tela, contra o preview local:
//   .venv/bin/uvicorn scripts.preview_gravacao:app --port 8770      (num terminal)
//   node tests/e2e/gravacao.mjs                                       (noutro; CHROME=/caminho para outro Chrome)
// O microfone é trocado por uma fala sintética gerada na página (o Chrome sem tela não libera o microfone no Mac);
// worklet, cortes, IndexedDB, fila, recuperação e as rotas do servidor são os de verdade. Só pacientes fictícios.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const BASE = process.env.PREVIEW || 'http://localhost:8770';
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9400 + Math.floor(Math.random() * 400);
const PROF = mkdtempSync(join(tmpdir(), 'od-e2e-'));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(...a);

const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROF}`, '--window-size=1440,900',
  '--autoplay-policy=no-user-gesture-required', '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' });
const fim = () => { try { chrome.kill(); } catch (_) {} try { rmSync(PROF, { recursive: true, force: true }); } catch (_) {} };
process.on('exit', fim);

let ws, id = 0, dialogo = true, dialogos = 0;
const espera = new Map(), erros = [];
function send(method, params = {}) {
  return new Promise((ok, no) => { const i = ++id; espera.set(i, { ok, no }); ws.send(JSON.stringify({ id: i, method, params })); });
}
async function ev(expr) {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error('na página: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
  return r.result.value;
}
async function ate(expr, ms, oque) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { try { if (await ev(expr)) return; } catch (_) {} await sleep(200); }
  throw new Error('esperou demais: ' + oque);
}
const srv = async (p) => (await fetch(BASE + p)).json();
const UI = `(() => { const q = (s) => document.querySelector(s), t = (s) => { const e = q(s); return e && !e.hidden && e.offsetParent !== null ? e.textContent.trim() : ''; };
  return { chip: t('#prRec .hc-chip'), tempo: t('#rcTime'), alerta: t('#rcAlert'), nota: t('#rcNote'), pill: q('#rcPill') && !q('#rcPill').hidden ? q('#rcPill').textContent.trim() : '',   // fixo: não tem offsetParent
          
           pontos: q('#rcReview') && !q('#rcReview').hidden ? q('#rcReview').querySelectorAll('.rc-pt').length : 0,
           botoes: [...document.querySelectorAll('#prRec button')].map((b) => (b.textContent.trim() || b.title) + (b.disabled ? ' (off)' : '')) }; })()`;
const IDB = `(async () => { const dbs = await indexedDB.databases(); const n = dbs.find((d) => d.name.startsWith('od_gravacao_')); if (!n) return [];
  return await new Promise((ok) => { const q = indexedDB.open(n.name); q.onsuccess = () => { const g = q.result.transaction('seg').objectStore('seg').getAll();
  g.onsuccess = () => { ok(g.result.map((x) => ({ k: x.k, part: !!x.part, pid: x.pid, dead: x.dead || null }))); q.result.close(); }; }; }); })()`;
const clica = (sel, txt) => ev(`(() => { const b = [...document.querySelectorAll(${JSON.stringify(sel)})].find((x) => !x.disabled && x.offsetParent !== null && (!${JSON.stringify(txt || '')} || x.textContent.includes(${JSON.stringify(txt || '')}))); if (b) b.click(); return !!b; })()`);
const chip = (t) => `(document.querySelector('#prRec .hc-chip')||{}).textContent === ${JSON.stringify(t)}`;
const rede = (on) => send('Network.emulateNetworkConditions', { offline: !on, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });

async function abre(url) {
  await send('Page.navigate', { url: BASE + url });
  await ate(`!!document.querySelector('#prRec') && [...document.querySelectorAll('#prRec .rc-go')].some((b) => b.offsetParent !== null)`, 20000, 'gravador visível');
}
async function grava(url, segundos) {
  if (url) await abre(url);
  await ate(`!!document.getElementById('rcConsentIn') && !document.getElementById('rcConsent').hidden`, 10000, 'autorização');
  if (!(await ev(`document.getElementById('rcConsentIn').checked`))) await ev(`document.getElementById('rcConsentIn').click()`);
  await clica('#prRec .rc-go', 'Gravar');
  await ate(chip('Gravando'), 10000, 'começar a gravar');
  await sleep(segundos * 1000);
}
async function encerra() {
  await clica('#prRec .rc-go', 'Encerrar');
  await ate(`!!document.querySelector('#prRec .rc-sum')`, 60000, 'evolução pronta');
  await sleep(1200);
}
const estado = () => srv('/_preview/estado');
async function limpa() {
  await srv('/_preview/reset');
  await send('Page.navigate', { url: BASE + '/health' }); await sleep(300);
  await ev(`(async () => { for (const d of await indexedDB.databases()) await new Promise((ok) => { const r = indexedDB.deleteDatabase(d.name); r.onsuccess = r.onerror = r.onblocked = ok; }); sessionStorage.clear(); return 1; })()`);
}

const cenarios = [
  ['envio sem perda: internet cai, aba recarrega no meio, continua e encerra', async () => {
    await grava('/_preview/pr?pid=9003&ev=evA', 32);
    await rede(false); await sleep(20000);
    const off = await ev(UI);
    if (!/Sem internet/.test(off.alerta)) throw new Error('faltou o aviso de sem internet: ' + off.alerta);
    if (!(await ev(IDB)).filter((x) => !x.part).length) throw new Error('nada guardado no computador durante a queda');
    await rede(true);
    await ate(`${IDB}.then((l) => l.filter((x) => !x.part).length === 0)`, 30000, 'fila esvaziar');
    await sleep(5000);
    await send('Page.reload', { ignoreCache: true });
    await ate(chip('Interrompida'), 20000, 'recuperar como interrompida');
    await clica('#prRec .rc-go', 'Continuar'); await ate(chip('Gravando'), 10000, 'voltar a gravar'); await sleep(10000);
    await encerra();
    const g = Object.values((await estado()).gravacoes);
    if (g.length !== 1 || g[0].status !== 'gerada') throw new Error('esperava 1 gravação gerada: ' + JSON.stringify(g.map((x) => x.status)));
    const t = g[0].trechos, buracos = t.slice(1).filter((s, i) => Math.abs(s.at - (t[i].at + t[i].dur)) > 0.06);
    if (buracos.length) throw new Error('buraco entre trechos: ' + JSON.stringify(buracos));
    return `${t.length} trechos, ${t.reduce((a, s) => a + s.dur, 0).toFixed(1)} s, sem buracos`;
  }],
  ['trocar de paciente com a gravação ligada não perde o trecho em andamento', async () => {
    await grava('/_preview/pr?pid=9003&ev=evA', 8);
    await ev(`window.__openProntuario({ patient_id: 9004, patient: 'x', from: 'pacientes' })`);
    await sleep(4000);
    const g = Object.values((await estado()).gravacoes);
    if (g.length !== 1 || g[0].pid !== 9003 || g[0].event_id !== 'evA' || !g[0].trechos.length) throw new Error('trecho perdido ou no paciente errado: ' + JSON.stringify(g));
    const mortos = (await ev(IDB)).filter((x) => x.dead);
    if (mortos.length) throw new Error('trecho recusado: ' + JSON.stringify(mortos));
    return `${g[0].trechos[0].dur.toFixed(1)} s guardados na paciente 9003 (consulta evA)`;
  }],
  ['a evolução de um paciente nunca usa a gravação de outro', async () => {
    await grava('/_preview/pr?pid=9004&ev=evB', 20); await encerra();
    const recB = Object.keys((await estado()).gravacoes)[0];
    await grava('/_preview/pr?pid=9003&ev=evA', 20);
    await rede(false); await clica('#prRec .rc-go', 'Encerrar'); await sleep(1500);
    await rede(true);
    await ev(`window.__openProntuario({ patient_id: 9004, patient: 'x', from: 'pacientes', event_id: 'evB', title: 'Retorno' })`);
    await sleep(12000);
    await ev(`window.__openProntuario({ patient_id: 9003, patient: 'x', from: 'pacientes', event_id: 'evA', title: 'Retorno' })`);
    await ate(`!!document.querySelector('#prRec .rc-sum')`, 20000, 'evolução de A pronta'); await sleep(3500);
    const e = await estado(), recA = Object.keys(e.gravacoes).find((k) => k !== recB);
    const nA = Object.values(e.evolucoes).find((n) => n.pid === 9003 && n.event_id === 'evA');
    if (!nA || !nA.scribe || JSON.stringify(nA.scribe.rec_ids) !== JSON.stringify([recA])) throw new Error('evolução de A aponta para: ' + JSON.stringify(nA && nA.scribe));
    if (e.gravacoes[recB].pid !== 9004) throw new Error('gravação de B mudou de paciente');
    return 'a evolução de A veio só da gravação de A';
  }],
  ['sair do prontuário pausa a gravação', async () => {
    await grava('/_preview/pr?pid=9003&ev=evA', 6);
    await ev(`window.__closeProntuario()`); await sleep(3000);
    const ativo = await ev(`window.__mic.tracks.some((t) => t.readyState === 'live')`);
    if (ativo) throw new Error('o microfone continuou ligado depois de sair do prontuário');
    const g = Object.values((await estado()).gravacoes);
    if (!g.length || !g[0].trechos.length) throw new Error('o trecho até a saída não foi guardado');
    return `pausou; ${g[0].trechos[0].dur.toFixed(1)} s guardados`;
  }],
  ['nas outras abas aparece o aviso "Gravando", que leva de volta', async () => {
    await grava('/_preview/pr?pid=9003&ev=evA', 3);
    await ev(`document.querySelector('#prTabs [data-tab=geral]').click()`); await sleep(600);
    const fora = await ev(UI);
    if (!/Gravando/.test(fora.pill)) throw new Error('sem aviso fora da aba Consulta');
    if (process.env.FOTO) { const f = await send('Page.captureScreenshot', { format: 'png' }); (await import('node:fs')).writeFileSync(process.env.FOTO, Buffer.from(f.data, 'base64')); }
    await ev(`document.getElementById('rcPill').click()`); await sleep(600);
    if ((await ev(UI)).pill) throw new Error('o aviso continuou na aba Consulta');
    await clica('#prRec button[aria-label^="Pausar"]');
    return fora.pill;
  }],
  ['consulta avulsa (sem agenda): a gravação volta ao reabrir', async () => {
    await grava('/_preview/pr?pid=9003', 20);
    await clica('#prRec button[aria-label^="Pausar"]'); await sleep(2500);
    await ev(`window.__openProntuario({ patient_id: 9003, patient: 'x', from: 'pacientes' })`);
    await ate(chip('Interrompida'), 15000, 'reencontrar a gravação avulsa');
    return (await ev(UI)).tempo + ' recuperados';
  }],
  ['revisão continua depois de recarregar: pontos, selo e sem duplicar', async () => {
    await grava('/_preview/pr?pid=9003&ev=evC', 20); await encerra(); await sleep(2500);
    const antes = (await ev(UI)).pontos;
    await send('Page.reload', { ignoreCache: true });
    await ate(`!!document.querySelector('#prRec .rc-sum')`, 20000, 'tela depois de recarregar'); await sleep(1500);
    const depois = await ev(UI);
    if (!antes || depois.pontos !== antes) throw new Error(`pontos para conferir: ${antes} antes, ${depois.pontos} depois`);
    await ev(`(() => { const t = document.getElementById('prNote'); t.value += ' .'; t.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await sleep(3500);
    const nota = () => estado().then((e) => Object.values(e.evolucoes).find((n) => n.event_id === 'evC'));
    if (!(await nota()).scribe) throw new Error('o selo sumiu depois de recarregar e editar');
    await clica('#prRec button', 'Gravar mais um trecho'); await ate(chip('Gravando'), 10000, 'gravar mais'); await sleep(8000);
    await encerra(); await sleep(2500);
    const n = await nota(), vezes = (n.content.match(/Refere boa adesão/g) || []).length;
    if (vezes !== 1) throw new Error('texto gerado aparece ' + vezes + ' vezes');
    if (!n.scribe) throw new Error('o selo sumiu depois de gravar mais');
    return `${depois.pontos} pontos mantidos, selo mantido, texto uma vez só`;
  }],
  ['Desfazer pergunta antes de apagar o que o médico escreveu depois', async () => {
    await abre('/_preview/pr?pid=9003&ev=evD');
    await ev(`(() => { const t = document.getElementById('prNote'); t.value = 'Texto da médica antes.'; t.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await grava('', 18); await encerra();
    await ev(`(() => { const t = document.getElementById('prNote'); t.value += ' Conduta acrescentada pela médica.'; t.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    dialogo = false; const d0 = dialogos;
    await clica('#rcNoteBtn', 'Desfazer'); await sleep(600);
    const texto = await ev(`document.getElementById('prNote').value`);
    dialogo = true;
    if (dialogos === d0) throw new Error('não perguntou antes de desfazer');
    if (!texto.includes('Conduta acrescentada pela médica.')) throw new Error('apagou o que a médica escreveu');
    await clica('#rcNoteBtn', 'Desfazer'); await sleep(600);
    if ((await ev(`document.getElementById('prNote').value`)) !== 'Texto da médica antes.') throw new Error('Desfazer confirmado não voltou ao texto anterior');
    return 'perguntou; cancelando, nada mudou; confirmando, voltou ao texto anterior';
  }],
  ['a paciente de exemplo continua com a demonstração', async () => {
    await send('Page.navigate', { url: BASE + '/_preview/pr?pid=9001&ev=evnext' });
    await ate(`[...document.querySelectorAll('#prRec .rc-go')].some((b) => b.offsetParent !== null)`, 20000, 'gravador');
    const t = await ev(`(document.querySelector('#prRec .rc-r')||{}).textContent || ''`);
    if (!/autorização/.test(t)) throw new Error('não está na demonstração: ' + t);
    return 'demonstração';
  }],
];

async function main() {
  let u;
  for (let i = 0; i < 60 && !u; i++) { try { u = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((t) => t.type === 'page')?.webSocketDebuggerUrl; } catch (_) {} await sleep(200); }
  if (!u) throw new Error('o Chrome não abriu (CHROME=' + CHROME + ')');
  ws = new WebSocket(u); await new Promise((r) => ws.addEventListener('open', r, { once: true }));
  ws.addEventListener('message', (m) => {
    const j = JSON.parse(m.data);
    if (j.id && espera.has(j.id)) { const w = espera.get(j.id); espera.delete(j.id); j.error ? w.no(new Error(j.error.message)) : w.ok(j.result); return; }
    if (j.method === 'Page.javascriptDialogOpening') { dialogos++; send('Page.handleJavaScriptDialog', { accept: dialogo }); }
    if (j.method === 'Runtime.exceptionThrown') erros.push(j.params.exceptionDetails.exception?.description || j.params.exceptionDetails.text);
  });
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `(() => {
    window.__mic = { tracks: [], mode: 'voz' };
    navigator.mediaDevices.getUserMedia = async () => {                     // fala sintética: 3,2 s de som e 0,8 s de pausa
      const ac = new AudioContext(), dst = ac.createMediaStreamDestination(), sr = ac.sampleRate, len = Math.round(sr * 4);
      const buf = ac.createBuffer(1, len, sr), d = buf.getChannelData(0); let s = 7;
      for (let i = 0; i < len; i++) { s = (s * 16807) % 2147483647; d[i] = i < sr * 3.2 ? (s / 2147483647 - 0.5) * 0.5 * (0.6 + 0.4 * Math.sin(i / sr * 25)) : 0; }
      const src = ac.createBufferSource(); src.buffer = buf; src.loop = true; src.connect(dst); src.start();
      const t = dst.stream.getAudioTracks()[0]; window.__mic.tracks.push(t); return dst.stream;
    };
    navigator.mediaDevices.enumerateDevices = async () => [{ kind: 'audioinput', deviceId: 'teste1', label: 'Microfone de teste', groupId: 'g' }];
  })();` });
  let falhas = 0;
  const so = (process.env.SO || '').split(',').filter(Boolean).map(Number);
  for (const [i, [nome, fn]] of cenarios.entries()) {
    if (so.length && !so.includes(i + 1)) continue;
    const t0 = Date.now();
    try {
      await limpa(); await rede(true);
      const r = await fn();
      log(`✓ ${nome} (${Math.round((Date.now() - t0) / 1000)} s): ${r}`);
    } catch (e) {
      falhas++; log(`✗ ${nome}: ${e.message}`);
      try { log('   tela:', JSON.stringify(await ev(UI))); } catch (_) {}
    }
  }
  if (erros.length) { falhas++; log('✗ erros de JavaScript na página:\n  ' + erros.join('\n  ')); }
  log(falhas ? `\n${falhas} falha(s)` : '\ntudo certo');
  return falhas;
}
main().then((f) => { fim(); process.exit(f ? 1 : 0); }, (e) => { console.error('erro:', e.message); fim(); process.exit(2); });
