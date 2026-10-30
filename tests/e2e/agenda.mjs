// Agenda no Chrome sem tela, sem servidor: a página de verdade (web/) é servida pelo próprio Chrome (interceptação do
// DevTools) e as rotas respondem com uma agenda fictícia. Nada vai para a rede (endereços externos são recusados).
//
//     node tests/e2e/agenda.mjs                 (SHOT=/pasta salva Dia e Semana em PNG; CHROME=/caminho para outro Chrome)
//
// Confere: eventos de dia inteiro aparecem no Dia e na Semana (e abrem a janela); plantão que passa da meia-noite abre,
// salva e vai ao prontuário com o fim no dia seguinte; criar às 23h30 funciona; editar as férias mantém os dias;
// alteração que não dá para salvar avisa em vez de sumir; a semana e a busca pedem o teto e a busca lê o futuro à parte.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync, existsSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, extname, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const WEB = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'web');
const ORIG = 'http://agenda.test';                         // .test nunca resolve: tudo é respondido aqui
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9950 + Math.floor(Math.random() * 40);
const PROF = mkdtempSync(join(tmpdir(), 'od-e2e-ag-'));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(...a);

const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROF}`, '--window-size=1440,900',
  '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--disable-component-update', '--disable-sync',
  '--no-pings', '--disable-domain-reliability', '--host-resolver-rules=MAP * ~NOTFOUND', 'about:blank'],
  { stdio: 'ignore', env: { ...process.env, TZ: 'America/Sao_Paulo' } });
const fim = () => { try { chrome.kill(); } catch (_) {} try { rmSync(PROF, { recursive: true, force: true }); } catch (_) {} };
process.on('exit', fim);

let ws, id = 0;
const espera = new Map(), erros = [], pedidos = [];
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
const certo = (cond, msg) => { if (!cond) throw new Error(msg); };

// ----- agenda fictícia (São Paulo, UTC−3): hoje e os próximos dias -----
const dia = (n) => new Date(Date.now() - 3 * 36e5 + n * 864e5).toISOString().slice(0, 10);
const utc = (d, hm) => new Date(`${d}T${hm}:00-03:00`).toISOString();      // instante que a página manda (toISOString)
const EVS = [
  { id: 'ferias', title: 'Férias', start: dia(0), end: dia(3), allDay: true },
  { id: 'aniv', title: 'Aniversário da Ana', start: dia(0), end: dia(1), allDay: true },
  { id: 'manha', title: 'Retorno — Pedro Lima', start: `${dia(0)}T10:00:00-03:00`, end: `${dia(0)}T10:30:00-03:00`, allDay: false },
  { id: 'plantao', title: 'Plantão', start: `${dia(0)}T19:00:00-03:00`, end: `${dia(1)}T07:00:00-03:00`, allDay: false },
  { id: 'joana', title: 'Consulta — Joana Prado', patient_id: 5, start: `${dia(0)}T23:30:00-03:00`, end: `${dia(1)}T00:00:00-03:00`, allDay: false },
];
const TIPOS = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.woff2': 'font/woff2', '.woff': 'font/woff', '.json': 'application/json', '.ico': 'image/x-icon' };
function rota(method, path, q, body) {
  if (path === '/me') return { logged_in: true, scribe: false, user: { id: 'u-teste' } };
  if (path === '/patients' && method === 'GET') return { patients: [{ id: 5, name: 'Joana Prado' }] };
  if (path === '/calendar/events' && method === 'GET') return { logged_in: true, connected: 'google', events: EVS };
  if (path === '/calendar/events' && method === 'POST') {
    const e = { id: 'novo' + EVS.length, title: body.title, start: body.start, end: body.end, allDay: !!body.all_day };
    EVS.push(e); return { ok: true, event: e };
  }
  if (path.startsWith('/calendar/events/') && method === 'PATCH') return { ok: true, event: {} };
  return null;
}
async function responde(p) {
  const u = new URL(p.request.url), method = p.request.method;
  if (u.origin !== ORIG) return send('Fetch.failRequest', { requestId: p.requestId, errorReason: 'BlockedByClient' });
  let body = null; try { body = p.request.postData ? JSON.parse(p.request.postData) : null; } catch (_) {}
  const arq = normalize(join(WEB, decodeURIComponent(u.pathname)));
  let status = 200, tipo = 'application/json', dado;
  if (arq.startsWith(WEB) && extname(arq) && existsSync(arq)) { dado = readFileSync(arq); tipo = TIPOS[extname(arq)] || 'application/octet-stream'; }
  else {
    const j = rota(method, u.pathname, u.searchParams, body);
    pedidos.push({ method, path: u.pathname, q: Object.fromEntries(u.searchParams), body });
    if (j === null) status = 404;
    dado = Buffer.from(JSON.stringify(j || {}));
  }
  return send('Fetch.fulfillRequest', { requestId: p.requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: tipo }], body: dado.toString('base64') });
}

const vis = (s) => `(() => { const e = document.querySelector(${JSON.stringify(s)}); return !!e && !e.hidden && !!e.offsetParent; })()`;
const val = (s) => ev(`document.querySelector(${JSON.stringify(s)}).value`);
const txt = (s) => ev(`(document.querySelector(${JSON.stringify(s)}) || {}).textContent || ''`);
const tecla = (k) => ev(`(() => { document.dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(k)}, bubbles: true })); return 1; })()`);
const clica = (s) => ev(`(() => { document.querySelector(${JSON.stringify(s)}).click(); return 1; })()`);
const patches = (idEv) => pedidos.filter((r) => r.method === 'PATCH' && r.path === '/calendar/events/' + idEv);
async function foto(nome) {
  if (!process.env.SHOT) return;
  const r = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(process.env.SHOT, nome), Buffer.from(r.data, 'base64'));
}
async function abreEvento(sel) {
  await ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.click(); return 1; })()`);
  await ate(`!document.getElementById('evPop').hidden`, 3000, 'janela do evento');
}
async function fecha() { await tecla('Escape'); await sleep(300); }

const cenarios = [
  ['dia inteiro aparece no Dia, entre a data e a linha', async () => {
    await ate(`!document.getElementById('calAllDay').hidden`, 8000, 'faixa de dia inteiro');
    const nomes = await ev(`[...document.querySelectorAll('#calAllDay .wk-ev')].map((b) => b.textContent)`);
    certo(nomes.join(' | ') === 'Férias | Aniversário da Ana', 'pílulas: ' + nomes.join(' | '));
    const g = await ev(`(() => { const c = document.querySelector('.center').getBoundingClientRect(), s = document.getElementById('calAllDay').getBoundingClientRect(),
      d = document.querySelector('.cal-head .date').getBoundingClientRect(), r = document.querySelector('.cal-inner .ev-real').getBoundingClientRect();
      return { top: s.top - c.top, bottom: s.bottom - c.top, data: d.bottom - c.top, left: s.left, card: r.left }; })()`);
    certo(g.top >= g.data && g.bottom <= 106, 'faixa entre a data e a linha: ' + JSON.stringify(g));
    certo(Math.abs(g.left - g.card) < 1, 'alinhada aos cards: ' + JSON.stringify(g));
    certo(await ev(`document.querySelectorAll('.cal-inner .ev-real').length`) === 3, 'os 3 eventos com horário continuam');
    await foto('agenda-dia.png');
    return 'Férias e Aniversário na faixa; cards com horário intactos';
  }],
  ['plantão 19h–7h: abre, salva com o fim no dia seguinte', async () => {
    await abreEvento('.ev-real[data-evkey="plantao"]');
    certo(await val('#evStart') === '19:00' && await val('#evEnd') === '07:00', 'horários');
    certo(await txt('#evDur') === '12 h', 'duração: ' + await txt('#evDur'));
    await ev(`document.getElementById('evLocation').value = 'Hospital'`);
    await fecha();
    await ate(`document.getElementById('evPop').hidden`, 2000, 'fechou');
    await sleep(300);
    const p = patches('plantao');
    certo(p.length === 1, 'um PATCH: ' + p.length);
    certo(p[0].body.start === utc(dia(0), '19:00') && p[0].body.end === utc(dia(1), '07:00'), 'fim no dia seguinte: ' + JSON.stringify(p[0].body));
    return p[0].body.start + ' → ' + p[0].body.end;
  }],
  ['consulta 23h30–0h abre o prontuário (sem "O fim deve ser depois do início.")', async () => {
    await ev(`window.__ctx = null; window.__openProntuario = (c) => { window.__ctx = c; }; 1`);
    await abreEvento('.ev-real[data-evkey="joana"]');
    certo(await val('#evEnd') === '00:00' && await txt('#evDur') === '30 minutos', 'duração: ' + await txt('#evDur'));
    await sleep(400);                                          // pacientes carregados
    await clica('#evCreate');
    await ate(`!!window.__ctx`, 3000, 'abriu o prontuário: ' + await txt('#evMsg'));
    const c = await ev(`window.__ctx`);
    certo(c.patient_id === 5 && c.end === utc(dia(1), '00:00'), 'contexto: ' + JSON.stringify(c));
    certo(patches('joana').length === 0, 'nada mudou: sem PATCH');
    return 'prontuário com fim ' + c.end;
  }],
  ['criar às 23h30 (fim 0h) e criar de dia inteiro, que aparece na faixa', async () => {
    await ev(`window.__openEventAt(200, 200, new Date(), 23, 30); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela');
    certo(await val('#evEnd') === '00:00' && await txt('#evDur') === '30 minutos', 'fim 0h: ' + await txt('#evDur'));
    await ev(`document.getElementById('evTitle').value = 'Encaixe'`);
    await clica('#evCreate');
    await ate(`document.getElementById('evMsg').textContent === 'Evento criado!'`, 3000, 'criado: ' + await txt('#evMsg'));
    const a = pedidos.filter((r) => r.method === 'POST').pop().body;
    certo(a.start === utc(dia(0), '23:30') && a.end === utc(dia(1), '00:00'), 'fim no dia seguinte: ' + JSON.stringify(a));
    await ate(`document.getElementById('evPop').hidden`, 3000, 'fechou sozinha');
    await ev(`window.__openEventAt(200, 200, new Date(), 10, 0); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela');
    await clica('#evAllDay');
    await ev(`document.getElementById('evTitle').value = 'Congresso'`);
    await clica('#evCreate');
    await ate(`document.getElementById('evMsg').textContent === 'Evento criado!'`, 3000, 'criado');
    const b = pedidos.filter((r) => r.method === 'POST').pop().body;
    certo(b.all_day === true && b.start === dia(0) && b.end === dia(1), 'dia inteiro: ' + JSON.stringify(b));
    await ate(`[...document.querySelectorAll('#calAllDay .wk-ev')].some((x) => x.textContent === 'Congresso')`, 3000, 'Congresso na faixa');
    await ate(`document.getElementById('evPop').hidden`, 3000, 'fechou sozinha');
    return 'Encaixe até 0h do dia seguinte; Congresso aparece na faixa';
  }],
  ['editar as férias mantém os 3 dias', async () => {
    await abreEvento('#calAllDay .wk-ev[data-evkey="ferias"]');
    certo(await ev(`document.getElementById('evAllDay').classList.contains('on')`), 'Dia todo ligado');
    certo(await ev(`document.querySelector('#calAllDay .wk-ev[data-evkey="ferias"]').classList.contains('sel')`), 'pílula selecionada');
    await ev(`document.getElementById('evTitle').value = 'Férias de verão'`);
    await fecha();
    await ate(`document.getElementById('evPop').hidden`, 2000, 'fechou');
    await sleep(300);
    const p = patches('ferias');
    certo(p.length === 1 && p[0].body.all_day === true && p[0].body.start === dia(0) && p[0].body.end === dia(3), 'férias: ' + JSON.stringify(p.map((x) => x.body)));
    return p[0].body.start + ' → ' + p[0].body.end + ' (fim exclusivo)';
  }],
  ['alteração que não dá para salvar avisa em vez de sumir', async () => {
    await abreEvento('.ev-real[data-evkey="joana"]');
    await ev(`(() => { const p = document.getElementById('evPatient'); p.value = 'Zé'; p.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
    await fecha();
    certo(await ev(`!document.getElementById('evPop').hidden`), 'a janela fica aberta');
    certo(await txt('#evMsg') === 'Escolha um paciente da lista ou crie um novo.', 'aviso: ' + await txt('#evMsg'));
    await fecha();
    certo(await ev(`document.getElementById('evPop').hidden`) && patches('joana').length === 0, 'fechar de novo descarta, sem PATCH');
    return 'avisou; fechar de novo descartou';
  }],
  ['plantão de 24 h: fim 08:00 grava 25 h e fim 06:00 grava 23 h (o fim fica no dia mais próximo)', async () => {
    const t24 = { id: 't24', title: 'Plantão 24 h', start: `${dia(0)}T07:00:00-03:00`, end: `${dia(1)}T07:00:00-03:00`, allDay: false };
    const abre = async () => { await ev(`window.__openEventEdit(400, 300, ${JSON.stringify(t24)}); 1`);
      await ate(`!document.getElementById('evPop').hidden`, 3000, 'janela do evento'); };
    const fim = (hm) => ev(`(() => { const s = document.getElementById('evEnd'); s.value = ${JSON.stringify(hm)}; s.dispatchEvent(new Event('change')); return 1; })()`);
    await abre();
    certo(await txt('#evDur') === '24 h', 'abre com 24 h: ' + await txt('#evDur'));
    await fim('08:00'); certo(await txt('#evDur') === '25 h', 'estender: ' + await txt('#evDur'));
    await fecha(); await sleep(300);
    let p = patches('t24');
    certo(p.length === 1 && p[0].body.end === utc(dia(1), '08:00'), 'gravou 25 h: ' + JSON.stringify(p.map((x) => x.body.end)));
    await abre();
    await fim('06:00'); certo(await txt('#evDur') === '23 h', 'encurtar: ' + await txt('#evDur'));
    await fecha(); await sleep(300);
    p = patches('t24');
    certo(p.length === 2 && p[1].body.end === utc(dia(1), '06:00'), 'gravou 23 h: ' + JSON.stringify(p.map((x) => x.body.end)));
    return '25 h e 23 h, como na tela';
  }],
  ['plantão de 36 h (19h → 7h dois dias depois): fim 19:00 vira 24 h, depois fim 07:00 vira 12 h', async () => {
    const t36 = { id: 't36', title: 'Plantão 36 h', start: `${dia(0)}T19:00:00-03:00`, end: `${dia(2)}T07:00:00-03:00`, allDay: false };
    await ev(`window.__openEventEdit(400, 300, ${JSON.stringify(t36)}); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 3000, 'janela do evento');
    const fim = (hm) => ev(`(() => { const s = document.getElementById('evEnd'); s.value = ${JSON.stringify(hm)}; s.dispatchEvent(new Event('change')); return 1; })()`);
    certo(await txt('#evDur') === '36 h', 'abre com 36 h: ' + await txt('#evDur'));
    await fim('19:00'); certo(await txt('#evDur') === '24 h', 'fim 19:00: ' + await txt('#evDur'));
    await fim('07:00'); certo(await txt('#evDur') === '12 h', 'fim 07:00: ' + await txt('#evDur'));
    await fecha(); await sleep(300);
    const p = patches('t36');
    certo(p.length === 1 && p[0].body.end === utc(dia(1), '07:00'), 'gravou 12 h: ' + JSON.stringify(p.map((x) => x.body.end)));
    return '36 h → 24 h → 12 h';
  }],
  ['fim igual ao início numa consulta curta avisa e não grava um dia inteiro', async () => {
    await abreEvento('.ev-real[data-evkey="manha"]');
    await ev(`(() => { const s = document.getElementById('evEnd'); s.value = '10:00'; s.dispatchEvent(new Event('change')); return 1; })()`);
    await fecha();
    certo(await ev(`!document.getElementById('evPop').hidden`), 'a janela fica aberta');
    certo(await txt('#evMsg') === 'O fim deve ser depois do início.', 'aviso: ' + await txt('#evMsg'));
    await fecha();
    certo(patches('manha').length === 0, 'sem PATCH');
    return 'avisou e não gravou';
  }],
  ['semana: linha de dia inteiro abaixo dos dias, fixa ao rolar; pede o teto', async () => {
    const antes = pedidos.length;
    await clica('#viewSel');
    await ate(`document.querySelectorAll('.wk-ad .wk-ev').length > 0`, 8000, 'linha de dia inteiro na semana');
    const semana = pedidos.slice(antes).find((r) => r.path === '/calendar/events' && r.method === 'GET');
    certo(semana && semana.q.limit === '2500', 'a semana pede o teto: ' + JSON.stringify(semana && semana.q));
    const n = await ev(`[...document.querySelectorAll('.wk-ad .wk-ev')].map((b) => b.textContent)`);
    certo(n.includes('Férias') && n.includes('Aniversário da Ana') && n.includes('Congresso'), 'pílulas: ' + n.join(' | '));
    certo(await ev(`document.querySelectorAll('.wk-ad').length`) === 8, 'uma célula por dia + a da calha');
    const agora = await ev(`(() => { const l = document.querySelector('.wk-now'); if (!l) return null; const n = new Date();
      return parseFloat(l.style.top) - document.querySelector('.wk-col').offsetTop - (n.getHours() + n.getMinutes() / 60) * 142; })()`);
    certo(agora === null || Math.abs(agora) < 2, 'o traço da hora continua na hora certa: ' + agora);
    await ev(`document.getElementById('wk').scrollLeft = 1e4`);   // a foto mostra o fim da semana (onde estão as férias)
    await foto('agenda-semana.png');
    await ev(`document.getElementById('wk').scrollLeft = 0`);
    const fixo = await ev(`(() => { const w = document.getElementById('wk'); w.scrollTop = 600;
      return document.querySelector('.wk-ad').getBoundingClientRect().top - w.getBoundingClientRect().top; })()`);
    certo(Math.abs(fixo - 51) < 1, 'fixa abaixo dos dias ao rolar: ' + fixo);
    await abreEvento('.wk-ad .wk-ev[data-evkey="aniv"]');
    certo(await ev(`document.getElementById('evAllDay').classList.contains('on')`) && await val('#evTitle') === 'Aniversário da Ana', 'abre a janela');
    await fecha();
    certo(patches('aniv').length === 0, 'sem mudança, sem PATCH');
    return n.length + ' pílulas na semana';
  }],
  ['busca lê as próximas e o passado em separado, todas com o teto', async () => {
    const antes = pedidos.length;
    await clica('#agSearch');
    await ate(`document.querySelectorAll('#srchList .srch-item').length > 0`, 5000, 'lista da busca');
    const lidas = pedidos.slice(antes).filter((r) => r.path === '/calendar/events' && r.method === 'GET' && r.q.limit === '2500');
    certo(lidas.length === 3, 'três leituras: ' + lidas.length);
    const hoje0 = utc(dia(0), '00:00');
    certo(lidas.some((r) => r.q.start === hoje0) && lidas.some((r) => r.q.end === hoje0), 'corte em hoje 0h: ' + JSON.stringify(lidas.map((r) => r.q)));
    const itens = await ev(`[...document.querySelectorAll('#srchList .srch-item .srch-t')].map((t) => t.textContent)`);
    certo(new Set(itens).size === itens.length, 'sem repetidos: ' + itens.join(' | '));
    return itens.length + ' próximas, sem repetir';
  }],
];

async function main() {
  for (let i = 0; i < 50; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch (_) {} await sleep(200); }
  await new Promise((ok) => ws.addEventListener('open', ok));
  ws.addEventListener('message', (m) => {
    const j = JSON.parse(m.data);
    if (j.id && espera.has(j.id)) { const w = espera.get(j.id); espera.delete(j.id); j.error ? w.no(new Error(j.error.message)) : w.ok(j.result); return; }
    if (j.method === 'Fetch.requestPaused') responde(j.params).catch((e) => erros.push('interceptação: ' + e.message));
    if (j.method === 'Page.javascriptDialogOpening') { erros.push('diálogo: ' + j.params.message); send('Page.handleJavaScriptDialog', { accept: true }); }
    if (j.method === 'Runtime.exceptionThrown') erros.push(j.params.exceptionDetails.exception?.description || j.params.exceptionDetails.text);
  });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] });
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setTimezoneOverride', { timezoneId: 'America/Sao_Paulo' });
  await send('Emulation.setFocusEmulationEnabled', { enabled: true });
  await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html' });
  let falhas = 0;
  for (const [nome, fn] of cenarios) {
    const t0 = Date.now();
    try { const r = await fn(); log(`✓ ${nome} (${Math.round((Date.now() - t0) / 1000)} s): ${r}`); }
    catch (e) { falhas++; log(`✗ ${nome}: ${e.message}`); }
  }
  if (erros.length) { falhas++; log('✗ erros na página:\n  ' + erros.join('\n  ')); }
  log(falhas ? `\n${falhas} falha(s)` : '\ntudo certo');
  return falhas;
}
main().then((f) => { fim(); process.exit(f ? 1 : 0); }, (e) => { console.error('erro:', e.message); fim(); process.exit(2); });
