// Teste ponta a ponta da aba Prescrições (receitas) contra o preview local (scripts/preview_gravacao.py): Chrome sem
// janela, a página de verdade e as rotas de verdade, com o banco em memória. Nada toca banco, OpenAI ou produção.
//
//     PREVIEW=http://localhost:8792 node tests/e2e/prescricoes.mjs        (SO=1,3 roda só esses cenários)
//
// Rode num preview SÓ DELE (outra porta): o teste limpa os dados do preview a cada cenário.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const BASE = process.env.PREVIEW || 'http://localhost:8792';
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9800 + Math.floor(Math.random() * 150);
const PROF = mkdtempSync(join(tmpdir(), 'od-e2e-rx-'));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(...a);

const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROF}`, '--window-size=1440,900',
  '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' });
const fim = () => { try { chrome.kill(); } catch (_) {} try { rmSync(PROF, { recursive: true, force: true }); } catch (_) {} };
process.on('exit', fim);

let ws, id = 0, resposta = '';
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
  while (Date.now() - t0 < ms) { try { if (await ev(expr)) return; } catch (_) {} await sleep(150); }
  throw new Error('esperou demais: ' + oque);
}
const srv = async (p, op) => (await fetch(BASE + p, op)).json();
const medico = (campos) => srv('/me/medico', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(campos) });
const linhas = `[...document.querySelectorAll('#rxBody .rx-row')].map((b) => b.querySelector('.rx-n').textContent + ' | ' + b.querySelector('.rx-q').textContent)`;
const n = (sel) => `document.querySelectorAll(${JSON.stringify(sel)}).length`;
const certo = (cond, msg) => { if (!cond) throw new Error(msg); };

async function limpa() {
  await srv('/_preview/reset'); await medico({ name: 'Dra. Teste', crm: '123456', crm_uf: 'SP', consultorio_endereco: 'Rua A, 1' });
  await send('Page.navigate', { url: BASE + '/health' }); await sleep(250);
  await ev(`(() => { sessionStorage.clear(); return 1; })()`);
}
async function abre(exemplo = true) {
  await send('Page.navigate', { url: BASE + '/_preview/pr?pid=9001&tab=prescricoes' + (exemplo ? '&exemplo=1' : '') });
  await ate(`!!document.getElementById('rnList') && document.querySelectorAll('#rnList .sg').length > 0`, 20000, 'sugestões');
}
async function item(nome, dose, pos, qtd) {
  await ev(`document.getElementById('rxAdd').click()`);
  await ate(n('#rxBody .rx-edit .rx-f') + ' >= 4', 3000, 'campos do item');
  await ev(`(() => { const f = document.querySelectorAll('#rxBody .rx-edit .rx-f'); f[0].value = ${JSON.stringify(nome)}; f[1].value = ${JSON.stringify(dose)};
    f[2].value = ${JSON.stringify(pos)}; f[3].value = ${JSON.stringify(qtd)}; document.querySelector('#rxBody .rx-edit .pr-save').click(); return 1; })()`);
}
// o rascunho salva sozinho 600 ms depois da última mudança: espera a gravação começar e terminar
const salvo = async () => { await sleep(900); await ate(`document.getElementById('rxSt').textContent === 'rascunho salvo'`, 8000, 'rascunho salvo'); };
async function emite() {
  await ev(`(() => { window.__folhas = null; document.body.classList.remove('rxp'); document.getElementById('rxEmit').click(); return 1; })()`);
  await ate(`window.__folhas !== null || !document.getElementById('rxMsg').hidden`, 10000, 'emitir');
}
const daApi = () => ev(`fetch('/prontuario/receitas?patient_id=9001').then((r) => r.json()).then((j) => j.receitas.map((r) => [r.tipo, r.status, r.itens.map((i) => i.nome).join('+'), r.motivo_cancelamento || '']))`);

const cenarios = [
  ['excluir um remédio da receita pelo × e desfazer', async () => {
    await abre(); await ev(`document.getElementById('rnAll').click()`); await salvo();
    certo((await ev(linhas)).length === 3, 'renovar trouxe 3 itens');
    await ev(`[...document.querySelectorAll('#rxBody .rx-row')].find((x) => x.innerText.includes('Metformina')).querySelector('.rx-x').click()`);
    await salvo(); certo((await daApi()).find((r) => r[1] === 'rascunho')[2] === 'Losartana+Atorvastatina', 'o rascunho salvo ficou sem a metformina');
    await ev(`document.querySelector('.pr-toast.act button').click()`); await salvo();
    const l = await ev(linhas); certo(l.length === 3 && l[1].startsWith('Metformina'), 'desfazer volta no mesmo lugar');
    return 'saiu, salvou sem ela e voltou no lugar';
  }],
  ['item digitado à mão é conferido (alergia e antimicrobiano)', async () => {
    await abre(); await item('Amoxicilina', '500 mg', '1 cápsula de 8/8 h', '21 cápsulas');
    await ate(`document.querySelector('#rxBody').innerText.includes('Alergia registrada: Penicilina')`, 6000, 'aviso de alergia');
    const t = await ev(`document.querySelector('#rxBody').innerText`);
    certo(t.includes('Antimicrobiano: sai numa receita separada'), 'tipo antimicrobiano');
    return 'alergia a penicilina e antimicrobiano avisados';
  }],
  ['emitir sem CRM pede os dados; com os dados separa e imprime em vias', async () => {
    await medico({ crm: '' }); await abre(); await ev(`document.getElementById('rnAll').click()`);
    await item('Azitromicina', '500 mg', '1 comprimido ao dia por 3 dias', '3 comprimidos'); await salvo();
    await emite(); const m = await ev(`document.getElementById('rxMsg').innerText`);
    certo(m.includes('complete seus dados') && m.includes('CRM'), 'recado de dados do médico: ' + m);
    await medico({ crm: '123456' }); await emite();
    await ate(`window.__folhas !== null`, 8000, 'folhas');
    const f = await ev(`window.__folhas`);
    certo(f.join('|') === 'Receita|Receita de antimicrobiano · 1ª via · retida na farmácia|Receita de antimicrobiano · 2ª via · paciente', 'folhas: ' + f.join('|'));
    await ate(n('#rxBody .rx-row') + ' === 0', 5000, 'rascunho vazio depois de emitir');
    const api = await daApi(); certo(api.filter((r) => r[1] === 'emitida' && r[2].includes('Azitromicina')).length === 1, 'antimicrobiano emitido à parte');
    return f.length + ' folhas: simples + antimicrobiano em 2 vias';
  }],
  ['o que exige talão não sai', async () => {
    await abre(false); await item('Clonazepam', '2 mg', '1 comprimido à noite', '30 comprimidos');
    await ate(`document.querySelector('#rxBody').innerText.includes('Notificação de Receita B')`, 6000, 'aviso de talão'); await salvo();
    await emite(); const m = await ev(`document.getElementById('rxMsg').innerText`);
    certo(m.includes('talão') && m.includes('Clonazepam'), 'recusou: ' + m);
    certo(!(await daApi()).some((r) => r[1] === 'emitida'), 'nada emitido');
    return 'recusado, com o recado do talão';
  }],
  ['controle especial em 2 vias, com comprador e fornecedor', async () => {
    await abre(false); await item('Sertralina', '50 mg', '1 comprimido pela manhã', '30 comprimidos'); await salvo();
    await emite(); await ate(`window.__folhas !== null`, 8000, 'folhas');
    const f = await ev(`window.__folhas`), id = await ev(n('#rxPrint .rx-id'));
    certo(f.length === 2 && f[0].startsWith('Receituário de controle especial') && id === 2, 'folhas: ' + f.join('|'));
    return '2 vias de controle especial';
  }],
  ['cancelar uma receita emitida, com motivo', async () => {
    await abre(); resposta = 'Dose errada';
    await ev(`[...[...document.querySelectorAll('#rhList .sg')][0].querySelectorAll('.sg-add')].find((b) => b.textContent === 'Cancelar').click()`);
    await ate(`document.getElementById('rhList').innerText.includes('Cancelada: Dose errada')`, 6000, 'cancelada na lista');
    certo((await daApi()).some((r) => r[1] === 'cancelada' && r[3] === 'Dose errada'), 'cancelada no servidor');
    return 'cancelada com o motivo';
  }],
  ['2ª via com a data da consulta e a marca', async () => {
    await abre();
    const data = await ev(`[...document.querySelectorAll('#rhList .sg')][0].querySelector('.ov-post-src small').textContent.split('·')[1].trim()`);
    await ev(`(() => { window.__folhas = null; [...[...document.querySelectorAll('#rhList .sg')][0].querySelectorAll('.sg-add')].find((b) => b.textContent === '2ª via').click(); return 1; })()`);
    await ate(`window.__folhas !== null`, 5000, 'folha da 2ª via');
    const t = await ev(`document.getElementById('rxPrint').innerText`);
    certo(t.includes(data) && t.includes('2ª via, impressa em'), 'data e marca: ' + t.slice(0, 200));
    return 'data ' + data + ' e marca de 2ª via';
  }],
  ['recarregar no meio: o rascunho volta igual', async () => {
    await abre(false); await item('Losartana', '50 mg', '1 comprimido de 12/12 h', '60 comprimidos');
    await item('Omeprazol', '20 mg', '1 cápsula em jejum', '30 cápsulas'); await salvo();
    await send('Page.reload'); await sleep(500);
    await ate(`!!document.getElementById('rxBody') && document.querySelectorAll('#rxBody .rx-row').length === 2`, 15000, 'rascunho depois de recarregar');
    return (await ev(linhas)).map((l) => l.split(' | ')[0]).join(', ') + ' voltaram';
  }],
  ['receitas emitidas aparecem no card da consulta no Histórico', async () => {
    await abre();
    await ev(`document.querySelector('#prTabs [data-tab=consultas]').click()`); await sleep(500);
    await ev(`(() => { const r = [...document.querySelectorAll('.pr-trow')].find((x) => x.offsetParent !== null && /Retorno/.test(x.innerText)); r.click(); return 1; })()`);
    await ate(`[...document.querySelectorAll('.pr-item.hc .hc-sp')].some((x) => /Receita simples · emitida/.test(x.textContent))`, 6000, 'receita no card');
    return 'seção "Receita simples · emitida em …" no card';
  }],
];

async function main() {
  for (let i = 0; i < 50; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch (_) {} await sleep(200); }
  await new Promise((ok) => ws.addEventListener('open', ok));
  ws.addEventListener('message', (m) => {
    const j = JSON.parse(m.data);
    if (j.id && espera.has(j.id)) { const w = espera.get(j.id); espera.delete(j.id); j.error ? w.no(new Error(j.error.message)) : w.ok(j.result); return; }
    if (j.method === 'Page.javascriptDialogOpening') send('Page.handleJavaScriptDialog', { accept: true, promptText: resposta });
    if (j.method === 'Runtime.exceptionThrown') erros.push(j.params.exceptionDetails.exception?.description || j.params.exceptionDetails.text);
  });
  await send('Page.enable'); await send('Runtime.enable');
  // a impressão não abre janela: guarda o título e a via de cada folha
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `window.__folhas = null; window.print = () => {
    window.__folhas = [...document.querySelectorAll('#rxPrint .rx-folha')].map((f) => [f.querySelector('h1').textContent, (f.querySelector('.rx-via') || {}).textContent].filter(Boolean).join(' · ')); };` });
  let falhas = 0;
  const so = (process.env.SO || '').split(',').filter(Boolean).map(Number);
  for (const [i, [nome, fn]] of cenarios.entries()) {
    if (so.length && !so.includes(i + 1)) continue;
    const t0 = Date.now();
    try { await limpa(); const r = await fn(); log(`✓ ${nome} (${Math.round((Date.now() - t0) / 1000)} s): ${r}`); }
    catch (e) { falhas++; log(`✗ ${nome}: ${e.message}`); }
  }
  if (erros.length) { falhas++; log('✗ erros de JavaScript na página:\n  ' + erros.join('\n  ')); }
  log(falhas ? `\n${falhas} falha(s)` : '\ntudo certo');
  return falhas;
}
main().then((f) => { fim(); process.exit(f ? 1 : 0); }, (e) => { console.error('erro:', e.message); fim(); process.exit(2); });
