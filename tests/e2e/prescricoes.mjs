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

let ws, id = 0, resposta = '', recusa = null;     // recusa: confirm() com esse texto diz não
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
  recusa = null;
  await srv('/_preview/reset'); await medico({ name: 'Dra. Teste', crm: '123456', crm_uf: 'SP', consultorio_endereco: 'Rua A, 1', receita_papel: '' });
  await send('Page.navigate', { url: BASE + '/health' }); await sleep(250);
  await ev(`(() => { sessionStorage.clear(); localStorage.clear(); return 1; })()`);
}
async function abre(exemplo = true) {
  await send('Page.navigate', { url: BASE + '/_preview/pr?pid=9001&tab=prescricoes' + (exemplo ? '&exemplo=1' : '') });
  await ate(`!!document.getElementById('rnList') && document.querySelectorAll('#rnList .sg').length > 0`, 20000, 'sugestões');
}
async function item(nome, dose, pos, qtd) {
  // a busca (#rxNew, padrão do Finance): o nome + Enter sem escolher = texto livre → dose, posologia, quantidade e "Adicionar"
  await ate(`!document.getElementById('rxNew').hidden`, 3000, 'busca de novo item');
  await ev(`(() => { const q = document.querySelector('#rxNew .fz-in'); q.focus(); q.value = ${JSON.stringify(nome)};
    q.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); return 1; })()`);
  await ate(n('#rxNew .fz-f') + ' === 3', 3000, 'campos do item');
  await ev(`(() => { const f = (k) => document.querySelector('#rxNew .fz-f[data-k=' + k + ']'); f('dose').value = ${JSON.stringify(dose)};
    f('posologia').value = ${JSON.stringify(pos)}; f('quantidade').value = ${JSON.stringify(qtd)}; document.querySelector('#rxNew .fz-ok').click(); return 1; })()`);
}
// o rascunho salva sozinho 600 ms depois da última mudança: espera a gravação começar e terminar
const salvo = async () => { await sleep(900); await ate(`document.getElementById('rxSt').textContent === 'rascunho salvo'`, 8000, 'rascunho salvo'); };
async function emite() {
  await ev(`(() => { window.__folhas = null; document.body.classList.remove('rxp'); document.getElementById('rxEmit').click(); return 1; })()`);
  await ate(`window.__folhas !== null || !document.getElementById('rxMsg').hidden`, 10000, 'emitir');
}
const sg = (nome) => `[...document.querySelectorAll('#rnList .sg')].find((r) => r.querySelector('.ov-post-t').textContent.toLowerCase().startsWith(${JSON.stringify(nome.toLowerCase())}))`;
const emUso = async () => (await srv('/patients')).patients.find((p) => p.id === 9001).medications.split('\n');
// Histórico (visual da tabela de Consultas, uma linha por remédio): ação da receita i (no cabeçalho dela)
const acaoRh = (t, i = 0) => ev(`(() => { [...[...document.querySelectorAll('#rhList .rh-head')][${i}].querySelectorAll('.rh-acts button')]
  .find((b) => b.textContent === ${JSON.stringify(t)}).click(); return 1; })()`);
// "Usar nesta consulta" na linha do remédio (na i-ésima linha com esse nome)
const usaRh = (nome) => ev(`(() => { [...document.querySelectorAll('#rhList .rh-item')].find((r) => r.querySelector('.pr-tdate').textContent.startsWith(${JSON.stringify(nome)}))
  .querySelector('button').click(); return 1; })()`);
const daApi = () => ev(`fetch('/prontuario/receitas?patient_id=9001').then((r) => r.json()).then((j) => j.receitas.map((r) => [r.tipo, r.status, r.itens.map((i) => i.nome).join('+'), r.motivo_cancelamento || '']))`);

const cenarios = [
  ['excluir um remédio da receita pelo × e desfazer', async () => {
    await abre(); await item('Losartana', '50 mg', '1 comprimido de 12/12 h', '60 comprimidos');
    await item('Metformina', '850 mg', '1 comprimido 2x/dia', '60 comprimidos'); await item('Atorvastatina', '20 mg', '1 comprimido à noite', '30 comprimidos');
    await salvo(); certo((await ev(linhas)).length === 3, '3 itens na receita');
    await ev(`[...document.querySelectorAll('#rxBody .rx-row')].find((x) => x.innerText.includes('Metformina')).querySelector('.rx-x').click()`);
    await salvo(); certo((await daApi()).find((r) => r[1] === 'rascunho')[2] === 'Losartana+Atorvastatina', 'o rascunho salvo ficou sem a metformina');
    await ev(`document.querySelector('.pr-toast.pr-desfaz button').click()`); await salvo();
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
    await medico({ crm: '' }); await abre(); await item('Losartana', '50 mg', '1 comprimido de 12/12 h', '60 comprimidos');
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
    await acaoRh('Cancelar receita');
    await ate(`[...document.querySelectorAll('#rhList .rh-head')].some((h) => h.innerText.includes('Motivo: Dose errada') && h.querySelector('.pr-badge').textContent === 'Cancelada')`, 6000, 'cancelada na lista');
    certo((await daApi()).some((r) => r[1] === 'cancelada' && r[3] === 'Dose errada'), 'cancelada no servidor');
    return 'cancelada com o motivo';
  }],
  ['2ª via com a data da consulta e a marca', async () => {
    await abre();
    const em = new Date((await srv('/prontuario/receitas?patient_id=9001')).receitas.find((r) => r.status === 'emitida').emitida_em);
    const data = [em.getDate(), em.getMonth() + 1].map((x) => String(x).padStart(2, '0')).join('/') + '/' + em.getFullYear();
    await ev(`(() => { window.__folhas = null; return 1; })()`); await acaoRh('Imprimir 2ª via');
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
  ['depois de emitir, oferece atualizar as medicações em uso', async () => {
    await abre(); await ate(n('#rhList .rh-item') + ' > 0', 5000, 'histórico');
    await usaRh('Metformina'); await salvo();                                   // do Histórico: uso contínuo, 850 mg
    await ev(`(() => { [...document.querySelectorAll('#rxBody .rx-row')].find((r) => r.innerText.includes('Metformina')).querySelector('.rx-main').click(); return 1; })()`);
    await ate(n('#rxBody .rx-edit .rx-f') + ' >= 4', 3000, 'edição do item');
    await ev(`(() => { const f = document.querySelectorAll('#rxBody .rx-edit .rx-f'); f[1].value = '1000 mg'; document.querySelector('#rxBody .rx-edit .pr-save').click(); return 1; })()`);
    await salvo(); await emite(); await ate(`!document.getElementById('rxSync').hidden`, 6000, 'oferta de atualizar');
    const t = await ev(`document.getElementById('rxSync').innerText`);
    certo(t.includes('Metformina 850 mg 2x/dia → Metformina 1000 mg') && !t.includes('Tirar'), 'oferta: ' + t);
    await ev(`[...document.querySelectorAll('#rxSync button')].find((b) => b.textContent === 'Atualizar').click()`);
    await ate(`document.getElementById('rxSync').hidden`, 3000, 'fechou a oferta'); await sleep(400);
    const u = await emUso();
    certo(u.includes('Metformina 1000 mg 1 comprimido 2x/dia') && u.includes('Losartana 50 mg 12/12h'), 'em uso: ' + u.join('; '));
    return 'trocou a dose da Metformina nas medicações em uso';
  }],
  ['possíveis prescrições: só 2 remédios novos, só com Adicionar; a barra volta vazia depois de adicionar', async () => {
    await abre();
    certo(await ev(n('#rnList .sg')) === 2 && await ev(`!!${sg('Dapagliflozina')} && !!${sg('Semaglutida')}`), 'só 2 remédios novos');
    certo(await ev(`[...document.querySelectorAll('#rnBox button, #rnBox a')].filter((b) => b.offsetParent !== null).map((b) => b.textContent.trim()).join('|')`) === 'Adicionar|Adicionar',
      'só o Adicionar no cartão');
    await ev(`${sg('Dapagliflozina')}.querySelector('.sg-add').click()`); await salvo();
    certo((await ev(linhas)).some((l) => l.startsWith('Dapagliflozina 10 mg')), 'foi para a receita');
    certo(await ev(`!document.getElementById('rxNew').hidden && document.querySelector('#rxNew .fz-in').getAttribute('role') === 'combobox'`), 'busca sempre aberta');
    await item('Omeprazol', '20 mg', '1 cápsula em jejum', '30 cápsulas');
    certo(await ev(`document.querySelector('#rxNew .fz-in').value === '' && document.querySelector('#rxNew .fz-pan').hidden`), 'volta para a barra vazia, painel fechado');
    return 'Dapagliflozina e Semaglutida, só com Adicionar; a barra volta vazia';
  }],
  ['adicionar pela base de medicamentos: escolher a marca, a apresentação e a quantidade', async () => {
    await abre(false);
    await ev(`(() => { const q = document.querySelector('#rxNew .fz-in'); q.focus(); q.value = 'glifage'; q.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
    await ate(n('#rxNew .fz-row') + ' > 0', 5000, 'resultados da busca');
    const r = await ev(`[...document.querySelectorAll('#rxNew .fz-row')].map((b) => b.querySelector('.fz-t').textContent + ' / ' + b.querySelector('.fz-s').textContent).slice(0, 2)`);
    certo(r[0] === 'Glifage / Cloridrato de metformina · Merck', 'resultado: ' + r.join(' | '));
    certo(await ev(`[...document.querySelectorAll('#rxNew .fz-chip')].map((c) => c.textContent).join('|')`) === 'Todas|Substâncias|Marcas', 'filtros');
    await ev(`(() => { document.querySelector('#rxNew .fz-row').dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); return 1; })()`);
    await ate(`document.querySelector('#rxNew .fz-ht') && document.querySelector('#rxNew .fz-ht').textContent === 'Glifage (cloridrato de metformina)'`, 3000, 'apresentações da marca');
    await ev(`(() => { [...document.querySelectorAll('#rxNew .fz-row')].find((b) => b.querySelector('.fz-t').textContent === '850 mg').dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); return 1; })()`);
    await ate(n('#rxNew .fz-f') + ' === 2', 3000, 'posologia e quantidade');
    const f = (k) => `document.querySelector('#rxNew .fz-f[data-k=${k}]')`;
    certo(await ev(`${f('quantidade')}.value`) === '30 comprimidos' && (await ev(`${f('posologia')}.placeholder`)).includes('comprimido revestido'), 'quantidade e forma da apresentação');
    await ev(`(() => { ${f('posologia')}.value = '1 comprimido 2x/dia'; ${f('quantidade')}.value = '60 comprimidos'; document.querySelector('#rxNew .fz-ok').click(); return 1; })()`);
    await salvo();
    const l = await ev(linhas);
    certo(l.some((x) => x.startsWith('Glifage (cloridrato de metformina) 850 mg | 60 comprimidos')), 'na receita: ' + l.join('; '));
    // o cartão do Figma: 01, 02…, a forma da apresentação escolhida e os dados do topo (sem Validade)
    const row = `[...document.querySelectorAll('#rxBody .rx-row')].find((r) => r.innerText.includes('Glifage'))`;
    certo(await ev(`${row}.innerText.includes('Forma farmacêutica: Comprimido revestido') && /^0\\d$/.test(${row}.querySelector('.rxp-num').textContent)`), 'número e forma na linha');
    certo(await ev(`[...document.querySelectorAll('#rxDados dt')].map((d) => d.textContent).join('|')`) === 'Paciente|Documento|Data de emissão', 'dados do topo');
    return 'Glifage (cloridrato de metformina) 850 mg · 60 comprimidos';
  }],
  ['histórico de receitas: busca por remédio e escolha dos itens', async () => {
    await abre(); await ate(n('#rhList .rh-item') + ' > 0', 5000, 'histórico');
    certo(await ev(`document.querySelector('#rhBox .gh-t').textContent === 'Histórico' && !document.getElementById('rtBox')`), 'um cartão só, Histórico');
    const busca = (t) => ev(`(() => { const q = document.getElementById('rhQ'); q.value = ${JSON.stringify(t)}; q.dispatchEvent(new Event('input', { bubbles: true }));
      return document.querySelectorAll('#rhList .rh-item').length; })()`);
    certo(await busca('parac') === 1 && await ev(n('#rhList .rh-head')) === 1, 'a busca acha só a linha do paracetamol, com a receita dela');
    certo(await busca('xyz') === 0 && (await ev(`document.getElementById('rhList').innerText`)).includes('Nenhuma receita'), 'sem resultado avisa');
    await busca('');
    certo(await ev(n('#rhList .pr-tchev')) === 0, 'sem dropdown na lista');
    await usaRh('Losartana'); await usaRh('Atorvastatina'); await salvo();     // a escolha é linha a linha
    const l = (await ev(linhas)).map((x) => x.split(' | ')[0]).join(', ');
    certo(l === 'Losartana 50 mg, Atorvastatina 20 mg', 'foram só os escolhidos: ' + l);
    certo(await ev(`[...document.querySelectorAll('#rhList .rh-item')].filter((r) => r.innerText.includes('Na receita')).length`) >= 2, 'as linhas viram "Na receita"');
    return l + ' (a Metformina ficou de fora)';
  }],
  ['receita em A5 quando escolhido em Configurações', async () => {
    await medico({ receita_papel: 'A5' }); await abre(); await item('Losartana', '50 mg', '1 comprimido de 12/12 h', '60 comprimidos'); await salvo();
    await emite(); await ate(`window.__folhas !== null`, 8000, 'folha');
    certo(await ev(`document.getElementById('rxPapel').textContent.includes('size:A5') && document.getElementById('rxPrint').classList.contains('a5')`), 'folha em A5');
    await ev(`(() => { window.dispatchEvent(new Event('afterprint')); return 1; })()`);
    certo(await ev(`document.getElementById('rxPapel').textContent === '' && !document.body.classList.contains('rxp')`), 'o A5 sai depois de imprimir (o PDF do prontuário continua A4)');
    return 'A5 na receita; volta ao normal depois';
  }],
];

async function main() {
  for (let i = 0; i < 50; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch (_) {} await sleep(200); }
  await new Promise((ok) => ws.addEventListener('open', ok));
  ws.addEventListener('message', (m) => {
    const j = JSON.parse(m.data);
    if (j.id && espera.has(j.id)) { const w = espera.get(j.id); espera.delete(j.id); j.error ? w.no(new Error(j.error.message)) : w.ok(j.result); return; }
    if (j.method === 'Page.javascriptDialogOpening') send('Page.handleJavaScriptDialog', { accept: !(recusa && recusa.test(j.params.message)), promptText: resposta });
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
