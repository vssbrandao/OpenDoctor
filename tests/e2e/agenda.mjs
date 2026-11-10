// Agenda no Chrome sem tela, sem servidor: a página de verdade (web/) é servida pelo próprio Chrome (interceptação do
// DevTools) e as rotas respondem com uma agenda fictícia. Nada vai para a rede (endereços externos são recusados).
//
//     node tests/e2e/agenda.mjs                 (SHOT=/pasta salva Dia e Semana em PNG; CHROME=/caminho para outro Chrome)
//
// Confere: eventos de dia inteiro aparecem no Dia e na Semana (e abrem a janela); plantão que passa da meia-noite abre,
// salva e vai ao prontuário com o fim no dia seguinte; criar às 23h30 funciona; editar as férias mantém os dias;
// alteração que não dá para salvar avisa em vez de sumir; a semana e a busca pedem o teto e a busca lê o futuro à parte;
// a faixa "Reconectar" diz se o Google Agenda está sem permissão ou se a conexão expirou;
// no campo Paciente, a de exemplo fica por último e o Enter nunca a escolhe (só a seta ou o mouse); com a lista de
// pacientes cortada (more), o campo Paciente e a tela Pacientes acham no servidor quem ficou de fora; o Dia não mostra
// consulta nenhuma que não seja da agenda (nem enquanto ela carrega, nem sem a agenda conectada, nem com ela vazia); a
// agenda sempre abre no Dia (a Semana escolhida não volta ao recarregar, e a escolha guardada pela versão anterior sai);
// os 8 botões de cima (Agenda e Assistente) mostram no mouseover a dica escura com o que fazem e o atalho (⇧⌘ + letra),
// sem a dica do navegador, e cada atalho aperta o seu botão (como o clique: fecha a janela do evento), nunca o escondido;
// o Expandir agenda volta ao nome certo quando o assistente reaparece pelo prontuário; a busca (lupa, ⇧⌘F, Buscar do
// menu e agenda#buscar) abre no meio da tela com Tudo · Consultas · Pacientes · Receitas, o trecho em negrito, e o
// termo nunca vai na URL (as receitas: no corpo do POST); escolher abre a consulta, o paciente ou a receita; a lupa
// (e o ⇧⌘F) abre já em Consultas, o Buscar do menu em Tudo; sem agenda conectada, nada de pedir para conectar.
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
let RECONECTAR = null;                                     // 'permissao' ou 'expirada': o servidor pede reconectar
let SEM_AGENDA = false;                                    // a conta não tem agenda conectada
let BOAS_VINDAS = false;                                   // a sessão é da conta que acabou de nascer (/me boas_vindas)
let UID = 'u-teste';                                       // a conta logada (outra conta no mesmo navegador: troca)
let ME_FORA = false;                                       // o /me não responde (a agenda não sabe de quem é a sessão)
let AGENDA_VAZIA = false;                                  // a agenda conectada não tem nada
let LENTA_AGENDA = 0;                                      // ms de espera do /calendar/events (GET)
const TIPOS = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.woff2': 'font/woff2', '.woff': 'font/woff', '.json': 'application/json', '.ico': 'image/x-icon' };
const PACS = [{ id: 7, name: 'Maria Silva', example: true }, { id: 5, name: 'Joana Prado' }];   // a de exemplo vem primeiro
let MAIS = false;                                          // a lista veio cortada: há pacientes só na busca do servidor
let LENTA = 0;                                             // ms de espera da busca no servidor
let LENTA_RX = 0;                                          // ms de espera da busca de receitas
let LENTO_PAC = 0;                                         // ms de espera do cadastro de paciente (POST /patients)
let FALTA_0021 = false;                                    // produção sem a migração 0021: e-mail/atendimento dão 503
const ANTIGOS = [{ id: 900, name: 'Otávio Antigo', notes: 3, last: '2025-01-10T12:00:00+00:00' }];
const sem = (v) => v.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
// receitas que a busca acha (POST /prontuario/receitas/busca: o termo no corpo; vazio, as recentes)
const RECEITAS = [
  { id: '11111111-1111-4111-8111-111111111111', patient_id: 5, patient: 'Joana Prado', tipo: 'simples', status: 'emitida',
    data: '2026-11-05T13:00:00+00:00', remedios: ['Losartana 50 mg'] },
  { id: '22222222-2222-4222-8222-222222222222', patient_id: 7, patient: 'Maria Silva', tipo: 'especial', status: 'emitida',
    data: '2026-10-21T13:00:00+00:00', remedios: ['Clonazepam 2 mg', 'Dipirona 500 mg'] },
];
function rota(method, path, q, body) {
  if (path === '/me' && ME_FORA) return null;      // 404: a agenda não sabe a conta
  if (path === '/me') return { logged_in: true, scribe: false, user: { id: UID }, boas_vindas: BOAS_VINDAS };
  if (path === '/me/boas-vindas' && method === 'POST') { BOAS_VINDAS = false; return { ok: true }; }
  if (path === '/patients' && method === 'GET') return { patients: PACS, more: MAIS };
  if (path === '/patients/search' && method === 'POST') return { patients: ANTIGOS.filter((p) => sem(p.name).includes(sem(body.q).trim())) };
  if (path === '/patients' && method === 'POST' && FALTA_0021 && (body.email || body.coverage)) return { __status: 503, error: 'o cadastro com e-mail e convênio ainda não está disponível' };
  if (path === '/patients' && method === 'POST') { const p = { id: 40 + PACS.length, name: body.name }; PACS.push(p); return { ok: true, patient: p }; }
  if (path === '/calendar/events' && method === 'GET' && SEM_AGENDA) return { logged_in: true, connected: null, events: [] };
  if (path === '/calendar/events' && method === 'GET' && AGENDA_VAZIA) return { logged_in: true, connected: 'google', events: [] };
  if (path === '/calendar/events' && method === 'GET') return RECONECTAR
    ? { logged_in: true, connected: 'google', events: [], needs_reconnect: true, reason: RECONECTAR }
    : { logged_in: true, connected: 'google', events: EVS };
  if (path === '/calendar/events' && method === 'POST') {
    const e = { id: 'novo' + EVS.length, title: body.title, start: body.start, end: body.end, allDay: !!body.all_day };
    EVS.push(e); return { ok: true, event: e };
  }
  if (path.startsWith('/calendar/events/') && method === 'PATCH') return { ok: true, event: {} };
  if (path === '/prontuario/receitas/busca' && method === 'POST') {
    const k = sem((body && body.q) || '').trim();
    return { receitas: RECEITAS.filter((r) => !k || sem(r.patient + ' ' + r.remedios.join(' ')).includes(k)) };
  }
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
    if (LENTA && u.pathname === '/patients/search') await sleep(LENTA);
    if (LENTA_AGENDA && u.pathname === '/calendar/events' && method === 'GET') await sleep(LENTA_AGENDA);
    if (LENTO_PAC && u.pathname === '/patients' && method === 'POST') await sleep(LENTO_PAC);
    if (LENTA_RX && u.pathname === '/prontuario/receitas/busca') await sleep(LENTA_RX);
    const j = rota(method, u.pathname, u.searchParams, body);
    pedidos.push({ method, path: u.pathname, q: Object.fromEntries(u.searchParams), body });
    if (j === null) status = 404;
    if (j && j.__status) { status = j.__status; delete j.__status; }
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
  // sem janela, o Chrome só desenha quando pede a foto: a 1ª começa as animações (o rótulo que sobe), a 2ª sai com elas no fim
  await send('Page.captureScreenshot', { format: 'png' });
  await sleep(250);
  const r = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(process.env.SHOT, nome), Buffer.from(r.data, 'base64'));
}
async function abreEvento(sel) {
  await ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.click(); return 1; })()`);
  await ate(`!document.getElementById('evPop').hidden`, 3000, 'janela do evento');
}
async function fecha() { await tecla('Escape'); await sleep(300); }

// os botões das barras de cima da agenda: o texto da dica (o aria-label) e a letra do atalho (⇧⌘ + letra, Ctrl+Shift fora do Mac)
const BOTOES = [['agCreate', 'Criar evento', 'E'], ['calBtn', 'Escolher data', 'D'], ['viewSel', 'Mudar para Semana', 'U'],
                ['agSearch', 'Buscar', 'F'], ['agExpand', 'Expandir agenda', 'A'], ['raNew', 'Nova conversa', 'O'],
                ['raHist', 'Histórico', 'H'], ['raExpand', 'Expandir', 'X']];

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
    await ate(`document.querySelectorAll('#bsList .bs-it[data-tipo="consulta"]').length > 0`, 5000, 'lista da busca');
    const lidas = pedidos.slice(antes).filter((r) => r.path === '/calendar/events' && r.method === 'GET' && r.q.limit === '2500');
    certo(lidas.length === 3, 'três leituras: ' + lidas.length);
    const hoje0 = utc(dia(0), '00:00');
    certo(lidas.some((r) => r.q.start === hoje0) && lidas.some((r) => r.q.end === hoje0), 'corte em hoje 0h: ' + JSON.stringify(lidas.map((r) => r.q)));
    const itens = await ev(`[...document.querySelectorAll('#bsList .bs-it[data-tipo="consulta"] .bs-r')].map((t) => t.textContent)`);
    certo(new Set(itens).size === itens.length, 'sem repetidos: ' + itens.join(' | '));
    return itens.length + ' próximas, sem repetir';
  }],
  ['reconectar: a faixa diz "sem permissão" ou "expirou", e some quando a agenda volta', async () => {
    await tecla('Escape');                                     // fecha a busca
    certo(await ev(`document.getElementById('busca').hidden && !document.querySelector('.stage').inert`), 'o Esc não fechou a busca');
    const faixa = `(document.querySelector('#calReconnect b') || {}).textContent`;
    RECONECTAR = 'permissao';
    await ev(`window.__refreshAgenda(); 1`);
    await ate(`!document.getElementById('calReconnect').hidden`, 3000, 'faixa');
    certo(await ev(faixa) === 'O Google Agenda está sem permissão para o OpenDoctor.', 'sem permissão: ' + await ev(faixa));
    RECONECTAR = 'expirada';
    await ev(`window.__refreshAgenda(); 1`);
    await ate(`${faixa} === 'A conexão com o Google Agenda expirou.'`, 3000, 'expirou: ' + await ev(faixa));
    certo(await ev(`document.querySelector('#calReconnect a').getAttribute('href')`) === '/integrations/google/connect', 'link Reconectar');
    RECONECTAR = null;
    await ev(`window.__refreshAgenda(); 1`);
    await ate(`document.getElementById('calReconnect').hidden`, 3000, 'faixa some');
    return 'sem permissão → expirou → some';
  }],
  ['paciente: "Maria Silva" + Enter nunca escolhe a de exemplo; com a seta, sim', async () => {
    const lista = () => ev(`[...document.querySelectorAll('#evPList .evpop-po')].map((b) => (b.classList.contains('on') ? '*' : '') + b.lastChild.textContent)`);
    const digita = async (v) => {
      await ev(`(() => { const p = document.getElementById('evPatient'); p.focus(); p.value = ${JSON.stringify(v)}; p.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
      await ate(`(() => { const b = [...document.querySelectorAll('#evPList .evpop-po')], u = b[b.length - 1];   // a lista já é a deste nome
        return !!document.querySelector('#evPList .evpop-po.on') && !!u && u.textContent.endsWith(${JSON.stringify('"' + v + '"')}); })()`, 3000, 'lista de ' + v);
    };
    const noCampo = (k) => ev(`(() => { document.getElementById('evPatient').dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(k)}, bubbles: true, cancelable: true })); return 1; })()`);
    const cria = async () => {
      const antes = pedidos.length;
      await clica('#evCreate');
      await ate(`document.getElementById('evMsg').textContent === 'Evento criado!'`, 3000, 'criado: ' + await txt('#evMsg'));
      await ate(`document.getElementById('evPop').hidden`, 3000, 'fechou sozinha');
      return pedidos.slice(antes).find((r) => r.method === 'POST' && r.path === '/calendar/events').body;
    };
    await fecha();
    await ev(`window.__openEventAt(200, 200, new Date(), 9, 0); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela');
    await digita('a');                                         // a de exemplo vai para o fim, o destaque fica na de verdade
    let l = await lista();
    certo(l.join(' | ') === '*Joana Prado | Maria Silva (exemplo) | Criar paciente "a"', 'lista "a": ' + l.join(' | '));
    await digita('Maria Silva');                               // só a de exemplo tem o nome: o destaque vai para Criar
    l = await lista();
    certo(l.join(' | ') === 'Maria Silva (exemplo) | *Criar paciente "Maria Silva"', 'lista "Maria Silva": ' + l.join(' | '));
    await noCampo('Enter');
    await ate(`!document.getElementById('evPClear').hidden`, 3000, 'paciente escolhido');
    const novo = pedidos.filter((r) => r.method === 'POST' && r.path === '/patients');
    certo(novo.length === 1 && novo[0].body.name === 'Maria Silva' && !novo[0].body.force, 'criou a Maria de verdade: ' + JSON.stringify(novo.map((r) => r.body)));
    const real = PACS[PACS.length - 1].id;
    const a = await cria();
    certo(a.patient_id === real, 'consulta da Maria de verdade: ' + a.patient_id);
    await ev(`window.__openEventAt(200, 200, new Date(), 10, 0); 1`);   // agora há a de verdade: ela fica em destaque
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela');
    await digita('Maria Silva');
    l = await lista();
    certo(l.join(' | ') === '*Maria Silva | Maria Silva (exemplo) | Criar outro paciente "Maria Silva"', 'com a de verdade: ' + l.join(' | '));
    await noCampo('ArrowDown');                                // escolher a de exemplo de propósito continua valendo
    l = await lista();
    certo(l[1] === '*Maria Silva (exemplo)', 'seta na de exemplo: ' + l.join(' | '));
    await noCampo('Enter');
    await ate(`!document.getElementById('evPClear').hidden`, 3000, 'paciente escolhido');
    const b = await cria();
    certo(b.patient_id === 7, 'escolhida com a seta: ' + b.patient_id);
    return 'Enter criou a Maria de verdade (id ' + real + '); a seta ainda escolhe a de exemplo';
  }],
  ['lista cortada: o campo Paciente e a tela Pacientes acham no servidor o paciente que ficou de fora', async () => {
    const lista = () => ev(`[...document.querySelectorAll('#evPList .evpop-po')].map((b) => (b.classList.contains('on') ? '*' : '') + b.lastChild.textContent)`);
    const digita = async (v) => {
      await ev(`(() => { const p = document.getElementById('evPatient'); p.focus(); p.value = ${JSON.stringify(v)}; p.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
      await ate(`(() => { const b = [...document.querySelectorAll('#evPList .evpop-po')], u = b[b.length - 1];
        return !!u && u.textContent.endsWith(${JSON.stringify('"' + v + '"')}) && b.length > 1; })()`, 3000, 'lista de ' + v);
    };
    const buscas = () => pedidos.filter((r) => r.method === 'POST' && r.path === '/patients/search');
    await ev(`window.__openEventAt(200, 200, new Date(), 11, 0); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela');
    await digita('Joana');                                     // sem corte: nada vai ao servidor
    certo(buscas().length === 0, 'buscou sem a lista estar cortada');
    await fecha();
    MAIS = true;
    await ev(`window.__openEventAt(200, 200, new Date(), 11, 0); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela');
    await digita('otavio');
    let l = await lista();
    certo(l.join(' | ') === '*Otávio Antigo | Criar paciente "otavio"', 'lista "otavio": ' + l.join(' | '));
    const b = buscas();
    certo(b.length >= 1 && b[b.length - 1].body.q === 'otavio' && !Object.keys(b[b.length - 1].q).length, 'nome no corpo, nunca na URL: ' + JSON.stringify(b));
    await digita('Otávio Antigo');                             // o nome exato já existe: é outra pessoa?
    l = await lista();
    certo(l.join(' | ') === '*Otávio Antigo | Criar outro paciente "Otávio Antigo"', 'nome exato: ' + l.join(' | '));
    await ev(`(() => { document.getElementById('evPatient').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })); return 1; })()`);
    await ate(`!document.getElementById('evPClear').hidden`, 3000, 'paciente escolhido');
    const antes = pedidos.length;
    await clica('#evCreate');
    await ate(`document.getElementById('evMsg').textContent === 'Evento criado!'`, 3000, 'criado: ' + await txt('#evMsg'));
    const novo = pedidos.slice(antes).find((r) => r.method === 'POST' && r.path === '/calendar/events').body;
    certo(novo.patient_id === 900, 'consulta do paciente antigo: ' + novo.patient_id);
    certo(!pedidos.some((r) => r.method === 'POST' && r.path === '/patients' && r.body.name === 'Otávio Antigo'), 'não cadastrou de novo');
    await ate(`document.getElementById('evPop').hidden`, 3000, 'fechou sozinha');
    await clica('#navPacientes');                              // a tela Pacientes
    await ate(`[...document.querySelectorAll('#ptList .pt-empty')].some((e) => e.textContent.startsWith('Aqui estão os pacientes usados mais recentemente'))`, 3000, 'aviso da lista cortada');
    // a lupa de Pacientes abre a busca já em Pacientes, e ela pergunta ao servidor por quem ficou de fora da lista cortada
    await clica('#ptBusca');
    await ate(`!document.getElementById('busca').hidden && document.querySelector('#bsAbas .on').dataset.aba === 'pacientes'`, 3000, 'a busca em Pacientes');
    await ev(`(() => { const s = document.getElementById('bsIn'); s.value = 'Otá'; s.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
    await ate(`[...document.querySelectorAll('#bsList .bs-it .bs-r')].map((e) => e.textContent).join() === 'Otávio Antigo'`, 3000,
      'achou pela busca de Pacientes: ' + await ev(`document.getElementById('bsList').textContent`));
    await ev(`(() => { document.getElementById('bsX').click(); return 1; })()`);
    await clica('#navConsultas');
    MAIS = false;
    return 'campo Paciente e tela Pacientes acharam o Otávio no servidor; a consulta ficou com o cadastro dele';
  }],
  ['lista cortada e busca lenta: o Enter logo depois de digitar vale para o que está escrito, nunca para a lista anterior', async () => {
    MAIS = true; LENTA = 400;
    const poe = (v) => ev(`(() => { const p = document.getElementById('evPatient'); p.focus(); p.value = ${JSON.stringify(v)}; p.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
    const enter = () => ev(`(() => { document.getElementById('evPatient').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })); return 1; })()`);
    const criados = () => pedidos.filter((r) => r.method === 'POST' && r.path === '/patients').map((r) => r.body.name);
    await ev(`window.__openEventAt(200, 200, new Date(), 11, 0); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela');
    await poe('Ot');
    await ate(`[...document.querySelectorAll('#evPList .evpop-po')].some((b) => b.textContent.includes('Otávio Antigo'))`, 3000, 'lista de "Ot"');
    await poe('Otto'); await sleep(50); await enter();          // antes da resposta da busca de "Otto"
    await ate(`!document.getElementById('evPClear').hidden`, 3000, 'paciente escolhido');
    certo(await val('#evPatient') === 'Otto' && criados().pop() === 'Otto', 'escolheu: ' + await val('#evPatient') + ' / ' + JSON.stringify(criados()));
    await fecha(); await ate(`document.getElementById('evPop').hidden`, 2000, 'fechou');
    await ev(`window.__openEventAt(200, 200, new Date(), 11, 0); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela');
    await poe('Zé'); await sleep(50);
    await poe('Zé Carlos'); await sleep(50); await enter();
    await ate(`!document.getElementById('evPClear').hidden`, 3000, 'paciente escolhido');
    certo(await val('#evPatient') === 'Zé Carlos' && criados().pop() === 'Zé Carlos', 'nome inteiro: ' + JSON.stringify(criados()));
    await fecha(); await ate(`document.getElementById('evPop').hidden`, 2000, 'fechou');
    await ev(`window.__openEventAt(200, 200, new Date(), 11, 0); 1`);      // a busca que chega depois da escolha não reabre a lista
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela');
    await poe('Joana Prado');
    await ate(`[...document.querySelectorAll('#evPList .evpop-po.on')].some((b) => b.textContent.includes('Joana Prado'))`, 3000, 'Joana na lista');
    await enter();
    await ate(`!document.getElementById('evPClear').hidden`, 3000, 'Joana escolhida');
    await sleep(LENTA + 300);
    certo(await ev(`document.getElementById('evPList').hidden`), 'a lista reabriu com a resposta atrasada');
    await fecha(); await ate(`document.getElementById('evPop').hidden`, 2000, 'fechou');
    MAIS = false; LENTA = 0;
    await ev(`window.__openEventAt(200, 200, new Date(), 11, 0); 1`);      // campo vazio: o Enter não escolhe o mais recente
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela');
    await poe('');
    await ate(`[...document.querySelectorAll('#evPList .evpop-pmsg')].some((m) => m.textContent === 'Pacientes recentes')`, 3000, 'recentes');
    await enter(); await sleep(300);
    certo(await val('#evPatient') === '' && await ev(`document.getElementById('evPClear').hidden`), 'Enter no campo vazio escolheu: ' + await val('#evPatient'));
    await fecha(); await ate(`document.getElementById('evPop').hidden`, 2000, 'fechou');
    return 'Otto e Zé Carlos criados com o nome digitado; o Otávio da lista anterior não foi escolhido; a resposta atrasada não reabriu a lista; Enter vazio não escolheu';
  }],
  ['campo Paciente: o nome exato vem primeiro, a paciente do evento antes da homônima, e Enter duplo cria um cadastro só', async () => {
    const poe = (v) => ev(`(() => { const p = document.getElementById('evPatient'); p.focus(); p.value = ${JSON.stringify(v)}; p.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
    const tecla1 = `document.getElementById('evPatient').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))`;
    const destaque = () => ev(`(() => { const b = document.querySelector('#evPList .evpop-po.on'); return b ? b.lastChild.textContent : null; })()`);
    PACS.unshift({ id: 60, name: 'Ana Souza Lima' }, { id: 61, name: 'Ana Souza' });   // a mais recente só contém o nome
    await ev(`window.__openEventAt(200, 200, new Date(), 11, 0); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela'); await sleep(400);
    await poe('Ana Souza');
    await ate(`!!document.querySelector('#evPList .evpop-po.on')`, 3000, 'lista');
    certo(await destaque() === 'Ana Souza', 'destaque: ' + await destaque());
    await ev(`${tecla1}; 1`);
    await ate(`!document.getElementById('evPClear').hidden`, 3000, 'escolhida');
    const antes = pedidos.length;
    await clica('#evCreate');
    await ate(`document.getElementById('evMsg').textContent === 'Evento criado!'`, 3000, 'criado: ' + await txt('#evMsg'));
    const novo = pedidos.slice(antes).find((r) => r.method === 'POST' && r.path === '/calendar/events').body;
    certo(novo.patient_id === 61, 'consulta da Ana Souza: ' + novo.patient_id);
    await ate(`document.getElementById('evPop').hidden`, 3000, 'fechou sozinha');

    PACS.unshift({ id: 62, name: 'Joana Prado', birth_date: '1990-01-01' });   // homônima mais recente da Joana do evento
    const p0 = patches('joana').length;
    await abreEvento('.ev-real[data-evkey="joana"]'); await sleep(400);
    await ev(`document.getElementById('evPatient').blur(); document.getElementById('evPatient').focus(); 1`);
    await ate(`!!document.querySelector('#evPList .evpop-po.on')`, 3000, 'lista do evento');
    certo(await destaque() === 'Joana Prado', 'destaque na homônima: ' + await destaque());
    await ev(`${tecla1}; 1`); await sleep(200);
    await fecha(); await ate(`document.getElementById('evPop').hidden`, 2000, 'fechou'); await sleep(300);
    certo(patches('joana').length === p0, 'trocou a paciente do evento: ' + JSON.stringify(patches('joana').slice(p0).map((x) => x.body.patient_id)));

    await ev(`window.__openEventAt(200, 200, new Date(), 11, 0); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela');
    await poe('Bruno Novo');
    await ate(`[...document.querySelectorAll('#evPList .evpop-po')].some((b) => b.textContent.endsWith('"Bruno Novo"'))`, 3000, 'opção criar');
    await ev(`${tecla1}; ${tecla1}; 1`);                      // Enter duplo antes da resposta
    await ate(`!document.getElementById('evPClear').hidden`, 3000, 'criado');
    const n = pedidos.filter((r) => r.method === 'POST' && r.path === '/patients' && r.body.name === 'Bruno Novo').length;
    certo(n === 1, 'cadastros do Bruno Novo: ' + n);
    await fecha(); await ate(`document.getElementById('evPop').hidden`, 2000, 'fechou');
    return 'Ana Souza (exata) escolhida antes da Ana Souza Lima; a Joana do evento ficou; Enter duplo criou um cadastro';
  }],
  ['campo Paciente: cadastro em andamento não deixa criar a consulta no homônimo; a de exemplo nunca leva o Enter a outra pessoa', async () => {
    const poe = (v) => ev(`(() => { const p = document.getElementById('evPatient'); p.focus(); p.value = ${JSON.stringify(v)}; p.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
    const tecla = (k) => ev(`document.getElementById('evPatient').dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(k)}, bubbles: true, cancelable: true })); 1`);
    const destaque = () => ev(`(() => { const b = document.querySelector('#evPList .evpop-po.on'); return b ? b.lastChild.textContent : null; })()`);
    const eventos = () => pedidos.filter((r) => r.method === 'POST' && r.path === '/calendar/events').length;
    // só a de exemplo se chama "Maria Silva"; a real "Maria Silva Santos" só contém o nome: o Enter é "Criar paciente"
    for (let i = PACS.length - 1; i >= 0; i--) if (!PACS[i].example && PACS[i].name === 'Maria Silva') PACS.splice(i, 1);
    PACS.unshift({ id: 70, name: 'Maria Silva Santos' });
    await ev(`window.__openEventAt(200, 200, new Date(), 11, 0); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela'); await sleep(400);
    await poe('Maria Silva');
    await ate(`!!document.querySelector('#evPList .evpop-po.on')`, 3000, 'lista');
    certo(await destaque() === 'Criar paciente "Maria Silva"', 'destaque: ' + await destaque());
    await fecha(); await ate(`document.getElementById('evPop').hidden`, 2000, 'fechou');

    // "Criar outro paciente" em andamento: Criar avisa, o blur não escolhe o homônimo, e a consulta fica no cadastro novo
    LENTO_PAC = 700;
    await ev(`window.__openEventAt(200, 200, new Date(), 15, 0); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela'); await sleep(400);
    await poe('Joana Prado');
    await ate(`[...document.querySelectorAll('#evPList .evpop-po')].some((b) => b.textContent.startsWith('+Criar outro') || b.lastChild.textContent.startsWith('Criar outro'))`, 3000, 'opção criar outro');
    await tecla('ArrowUp');                                      // sobe até "Criar outro paciente" (a última)
    certo((await destaque() || '').startsWith('Criar outro paciente'), 'destaque: ' + await destaque());
    const e0 = eventos();
    await tecla('Enter');
    await ev(`document.getElementById('evPatient').blur(); 1`);
    certo(await ev(`document.getElementById('evPClear').hidden`), 'o blur escolheu o homônimo durante o cadastro');
    await clica('#evCreate');
    certo(await txt('#evMsg') === 'Aguarde o cadastro do paciente.' && eventos() === e0, 'Criar durante o cadastro: ' + await txt('#evMsg'));
    await ev(`(() => { const p = document.getElementById('evPatient'); p.focus(); p.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })); return 1; })()`);
    certo(await txt('#evMsg') === 'Aguarde o cadastro do paciente.', 'Enter de novo durante o cadastro: ' + await txt('#evMsg'));
    await ate(`!document.getElementById('evPClear').hidden`, 3000, 'cadastro novo escolhido');
    certo(await ev(`document.getElementById('evMsg').hidden`), 'o "Aguarde" ficou na tela depois do cadastro');
    const novoPac = pedidos.filter((r) => r.method === 'POST' && r.path === '/patients').pop();
    certo(novoPac.body.name === 'Joana Prado' && novoPac.body.force === true, 'cadastro: ' + JSON.stringify(novoPac.body));
    await clica('#evCreate');
    await ate(`document.getElementById('evMsg').textContent === 'Evento criado!'`, 3000, 'criado: ' + await txt('#evMsg'));
    const novo = pedidos.filter((r) => r.method === 'POST' && r.path === '/calendar/events').pop().body;
    const criado = PACS[PACS.length - 1];                      // o mock põe o cadastro novo no fim
    certo(criado.name === 'Joana Prado' && novo.patient_id === criado.id, 'consulta no cadastro novo: ' + novo.patient_id + ' / ' + JSON.stringify(criado));
    await ate(`document.getElementById('evPop').hidden`, 3000, 'fechou sozinha');
    LENTO_PAC = 0;

    // consulta ligada à de exemplo, com uma "Maria Silva" real mais recente: focar e dar Enter não troca a paciente
    PACS.unshift({ id: 71, name: 'Maria Silva' });
    const mx = { id: 'mx', title: 'Consulta — Maria Silva', patient_id: 7, start: `${dia(0)}T16:00:00-03:00`, end: `${dia(0)}T16:30:00-03:00`, allDay: false };
    await ev(`window.__openEventEdit(400, 300, ${JSON.stringify(mx)}); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 3000, 'janela do evento'); await sleep(400);
    await ev(`document.getElementById('evPatient').blur(); document.getElementById('evPatient').focus(); 1`);
    await ate(`!!document.querySelector('#evPList .evpop-po.on')`, 3000, 'lista do evento');
    certo(await destaque() === 'Maria Silva (exemplo)', 'destaque: ' + await destaque());
    await tecla('Enter'); await sleep(200);
    await fecha(); await ate(`document.getElementById('evPop').hidden`, 2000, 'fechou'); await sleep(300);
    certo(patches('mx').length === 0, 'trocou a paciente do evento: ' + JSON.stringify(patches('mx').map((x) => x.body.patient_id)));
    return 'Enter foi para "Criar paciente"; Criar esperou o cadastro e a consulta ficou nele; a de exemplo do evento ficou';
  }],
  ['campo Paciente: cadastro que responde depois do prazo não vira dois pacientes', async () => {
    const poe = (v) => ev(`(() => { const p = document.getElementById('evPatient'); p.focus(); p.value = ${JSON.stringify(v)}; p.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
    const enter = () => ev(`document.getElementById('evPatient').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })); 1`);
    const posts = () => pedidos.filter((r) => r.method === 'POST' && r.path === '/patients' && r.body.name === 'Lia Demorada').length;
    await ev(`window.__prazoCadastro = 400; 1`);
    LENTO_PAC = 1200;                                            // o servidor cria aos 1,2 s; a tela desiste aos 0,4 s
    await ev(`window.__openEventAt(200, 200, new Date(), 17, 0); 1`);
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela'); await sleep(400);
    await poe('Lia Demorada');
    await ate(`[...document.querySelectorAll('#evPList .evpop-po')].some((b) => b.textContent.endsWith('"Lia Demorada"'))`, 3000, 'opção criar');
    await enter();
    await ate(`document.getElementById('evMsg').textContent.startsWith('Não foi possível criar o paciente agora')`, 4000, 'desistiu: ' + await txt('#evMsg'));
    await sleep(1200);                                           // o cadastro chegou no servidor
    LENTO_PAC = 0;
    await poe('Lia Demorada');
    await ate(`[...document.querySelectorAll('#evPList .evpop-po')].some((b) => b.textContent.endsWith('"Lia Demorada"'))`, 3000, 'opção criar de novo');
    await enter();
    await ate(`!document.getElementById('evPClear').hidden`, 4000, 'paciente ligado: ' + await txt('#evMsg'));
    certo(posts() === 1 && PACS.filter((p) => p.name === 'Lia Demorada').length === 1, 'cadastros: ' + posts());
    await ev(`window.__prazoCadastro = 0; 1`);
    await fecha(); await ate(`document.getElementById('evPop').hidden`, 2000, 'fechou');
    return 'a segunda tentativa achou o paciente criado e não cadastrou outro';
  }],
  ['boas-vindas: vêm da sessão da conta nova, uma vez, só para quem não tem a agenda conectada', async () => {
    const CONVITE = 'Bem-vindo! Conecte sua agenda do Google.';
    // o aviso fica numa linha só em qualquer largura; a frase inteira cabe a partir de 1366 px (abaixo, as reticências)
    const linha = async () => {
      const r = [];
      for (const w of [1280, 1366, 1440, 1536, 1920]) {
        await send('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 1, mobile: false });
        await sleep(150);
        r.push(await ev(`(() => { const t = document.getElementById('odWelcome'), s = t.querySelector('span'),
            c = document.querySelector('.center').getBoundingClientRect(), b = t.getBoundingClientRect();
          return { w: ${w}, linhas: Math.round(s.getBoundingClientRect().height / parseFloat(getComputedStyle(s).lineHeight)),
                   cortada: s.scrollWidth > s.clientWidth, dentro: b.left >= c.left && b.right <= c.right, alto: Math.round(b.height) }; })()`));
      }
      await send('Emulation.clearDeviceMetricsOverride');
      return r;
    };
    const linhaSo = (r) => r.every((x) => x.linhas === 1 && x.dentro && x.alto <= 64 && (x.w < 1366 || !x.cortada));
    const abre = async (q = '') => {
      await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html' + q });
      await ate(`document.readyState === 'complete' && !!window.__calUltima`, 8000, 'a 1ª resposta da agenda');
      await sleep(400);
      return ev(`({ v: !document.getElementById('odWelcome').hidden, t: document.querySelector('#odWelcome span').textContent,
                  a: !!(document.querySelector('#odWelcome a') || {}).offsetParent, q: location.search })`);
    };
    BOAS_VINDAS = true;
    let r = await abre();
    certo(!r.v, 'conta nova com a agenda conectada viu o aviso: ' + JSON.stringify(r));
    certo(pedidos.some((x) => x.method === 'POST' && x.path === '/me/boas-vindas') && !BOAS_VINDAS, 'a marca não saiu da sessão');
    // a agenda conectada que demora a responder (o Google pode levar segundos): nenhum convite enquanto espera
    BOAS_VINDAS = true; LENTA_AGENDA = 4000;
    try {
      await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html?lenta=1' });
      await ate(`location.search === '?lenta=1' && document.readyState === 'complete'`, 8000, 'a agenda lenta');
      await sleep(3600);
      certo(await ev(`document.getElementById('odWelcome').hidden`), 'o convite apareceu com a agenda conectada ainda carregando');
      await ate(`!!window.__calUltima`, 10000, 'a resposta lenta da agenda');
      await sleep(300);
      certo(await ev(`document.getElementById('odWelcome').hidden`), 'aviso com a agenda conectada (lenta)');
    } finally { LENTA_AGENDA = 0; BOAS_VINDAS = false; }
    SEM_AGENDA = true; BOAS_VINDAS = true;
    try {
      r = await abre();
      await foto('boas-vindas-1.png');
      certo(linhaSo(await linha()), 'o convite não ficou numa linha: ' + JSON.stringify(await linha()));
      certo(r.v && r.t === CONVITE && r.a, 'conta nova sem a agenda: ' + JSON.stringify(r));
      r = await abre('?de-novo=1');
      certo(!r.v, 'as boas-vindas voltaram ao recarregar: ' + JSON.stringify(r));
      r = await abre('?bemvindo=1');                                          // endereço antigo: só sai da URL
      certo(!r.v && r.q === '', 'o ?bemvindo antigo deu boas-vindas: ' + JSON.stringify(r));
    } finally { SEM_AGENDA = false; BOAS_VINDAS = false; }
    RECONECTAR = 'expirada'; BOAS_VINDAS = true;                               // a conexão expirou: o convite também
    try {
      r = await abre('?expirada=1');
      certo(r.v && r.t === CONVITE && r.a, 'conta nova com a conexão expirada: ' + JSON.stringify(r));
    } finally { RECONECTAR = null; BOAS_VINDAS = false; }
    return 'uma vez, pela sessão, só sem a agenda: conectada (mesmo demorando) sem aviso; sem a agenda ou com a conexão expirada, o convite com Conectar agenda; o ?bemvindo antigo não vale';
  }],
  ['outra conta no mesmo navegador: o prontuário aberto e as conversas da anterior não aparecem', async () => {
    UID = 'u-teste';
    await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html' });
    await ate(`document.readyState === 'complete' && !!window.__odUid`, 8000, 'agenda da conta 1');
    await ev(`sessionStorage.setItem('od_prontuario_ctx', JSON.stringify({ patient_id: 7, patient: 'Maria Silva', uid: 'u-teste' }));
              localStorage.setItem('od_conversas_v1', JSON.stringify([{ id: 'c1', title: 'Pergunta da conta 1', turns: [] }]));
              localStorage.setItem('od_draft_7_new', JSON.stringify({ s: 'rascunho da conta 1', base: '', at: Date.now() })); 1`);
    UID = 'u-outra';                                                          // a sessão acabou e outra conta entrou
    try {
      const antes = pedidos.length;
      await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html?outra=1#prontuario' });   // página nova (só o # não recarrega)
      await ate(`document.readyState === 'complete' && window.__odUid === 'u-outra'`, 8000, 'agenda da conta 2');
      await sleep(800);
      const r = await ev(`({ pr: document.querySelector('.stage') && document.querySelector('.stage').classList.contains('prontuario'),
        h: location.hash, ctx: sessionStorage.getItem('od_prontuario_ctx'), conv: localStorage.getItem('od_conversas_v1'),
        dr: localStorage.getItem('od_draft_7_new'), hist: document.body.innerText.indexOf('Pergunta da conta 1') >= 0,
        uid: localStorage.getItem('od_uid') })`);
      certo(!r.pr && r.h === '' && !r.ctx && !r.conv && !r.dr && !r.hist && r.uid === 'u-outra', 'a conta 2 viu a 1: ' + JSON.stringify(r));
      certo(!pedidos.slice(antes).some((x) => x.path === '/prontuario/list'), 'pediu o prontuário da conta 1');
      // a mesma conta que volta encontra o que é dela
      await ev(`sessionStorage.setItem('od_prontuario_ctx', JSON.stringify({ patient_id: 7, patient: 'Maria Silva', uid: 'u-outra' }));
                localStorage.setItem('od_draft_7_new', JSON.stringify({ s: 'rascunho da conta 2', base: '', at: Date.now() })); 1`);
      await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html' });
      await ate(`document.readyState === 'complete' && window.__odUid === 'u-outra'`, 8000, 'de volta à conta 2');
      await sleep(400);
      certo(await ev(`(JSON.parse(localStorage.getItem('od_draft_7_new') || '{}')).s`) === 'rascunho da conta 2', 'apagou o rascunho da própria conta');
    } finally {
      UID = 'u-teste';
      await ev(`localStorage.removeItem('od_draft_7_new'); sessionStorage.removeItem('od_prontuario_ctx'); 1`);
    }
    // guardado antes desta versão (sem dono): as conversas e o prontuário aberto saem; os rascunhos ficam
    await ev(`localStorage.removeItem('od_uid');
              localStorage.setItem('od_conversas_v1', JSON.stringify([{ id: 'c9', title: 'Pergunta de antes', turns: [] }]));
              localStorage.setItem('od_draft_7_new', JSON.stringify({ s: 'rascunho de antes', base: '', at: Date.now() })); 1`);
    await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html?antes=1' });
    await ate(`document.readyState === 'complete' && localStorage.getItem('od_uid') === 'u-teste'`, 8000, 'agenda depois da versão');
    await sleep(400);
    const v = await ev(`({ conv: localStorage.getItem('od_conversas_v1'), dr: (JSON.parse(localStorage.getItem('od_draft_7_new') || '{}')).s,
                          hist: document.body.innerText.indexOf('Pergunta de antes') >= 0 })`);
    certo(!v.conv && !v.hist && v.dr === 'rascunho de antes', 'o guardado antes desta versão: ' + JSON.stringify(v));
    await ev(`localStorage.removeItem('od_draft_7_new'); 1`);
    // a troca de conta apaga o rascunho de outra conta (o dono nele), e deixa o gravado sem saber a conta (u '')
    await ev(`localStorage.setItem('od_uid', 'u-outra');
              localStorage.setItem('od_draft_7_e1', JSON.stringify({ s: 'da outra', base: '', at: Date.now(), u: 'u-outra' }));
              localStorage.setItem('od_draft_7_e2', JSON.stringify({ s: 'sem dono', base: '', at: Date.now(), u: '' })); 1`);
    await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html?dono=1' });
    await ate(`document.readyState === 'complete' && localStorage.getItem('od_uid') === 'u-teste'`, 8000, 'agenda da conta 1 de novo');
    await sleep(300);
    const dr = await ev(`[localStorage.getItem('od_draft_7_e1'), (JSON.parse(localStorage.getItem('od_draft_7_e2') || '{}')).s]`);
    certo(dr[0] === null && dr[1] === 'sem dono', 'rascunhos na troca de conta: ' + JSON.stringify(dr));
    // o prontuário aberto de outra conta sai, mesmo se outra aba já deixou esta conta como dona do navegador
    await ev(`localStorage.removeItem('od_draft_7_e2');
              sessionStorage.setItem('od_prontuario_ctx', JSON.stringify({ patient_id: 7, patient: 'Maria Silva', uid: 'u-outra' })); 1`);
    await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html?alheio=1' });
    await ate(`document.readyState === 'complete' && window.__odUid === 'u-teste'`, 8000, 'agenda com o prontuário alheio');
    await sleep(300);
    certo(await ev(`sessionStorage.getItem('od_prontuario_ctx')`) === null, 'o prontuário da outra conta ficou na aba');
    // o /me não respondeu: sem saber de quem é a sessão, as conversas guardadas não aparecem
    await ev(`localStorage.setItem('od_conversas_v1', JSON.stringify([{ id: 'c8', title: 'Pergunta guardada', turns: [] }])); 1`);
    ME_FORA = true;
    try {
      await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html?mefora=1' });
      await ate(`document.readyState === 'complete' && window.__odUid === ''`, 8000, 'agenda sem o /me');
      await sleep(400);
      certo(!(await ev(`document.body.innerText.indexOf('Pergunta guardada') >= 0`)), 'sem o /me, mostrou as conversas guardadas');
    } finally { ME_FORA = false; await ev(`localStorage.removeItem('od_conversas_v1'); 1`); }
    return 'a conta 2 não reabre o prontuário nem vê as conversas e os rascunhos da 1; a própria conta mantém os dela; as conversas sem dono saem';
  }],
  ['sem consultas de exemplo: o Dia fica vazio enquanto a agenda carrega, sem a agenda e com a agenda vazia', async () => {
    const vazio = `(() => { const c = document.querySelector('.cal-inner');
      return !c.querySelector('.ev-real') && [...c.querySelectorAll('.hr-row')].every((r) => r.children.length === 1)
        && !/[A-Za-zÀ-ú]{3}/.test(c.innerText); })()`;                       // só as horas (0h…23h) e o traço de agora
    const abre = async (q) => {
      await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html' + q });
      await ate(`location.search === ${JSON.stringify(q)} && document.readyState === 'complete'`, 8000, 'agenda ' + q);
      certo(!(await ev(`document.querySelector('.stage').classList.contains('week')`)), 'abriu na Semana');
    };
    LENTA_AGENDA = 2000;
    try {
      await abre('?carregando=1');
      await sleep(300);
      certo(!(await ev(`!!window.__calUltima`)) && await ev(vazio), 'apareceu consulta enquanto a agenda carregava');
      await foto('dia-carregando.png');
      await ate(`!!document.querySelector('.cal-inner .ev-real')`, 8000, 'os eventos da agenda depois');
    } finally { LENTA_AGENDA = 0; }
    SEM_AGENDA = true;
    try {
      await abre('?semagenda=1');
      await ate(`!!window.__calUltima`, 8000, 'a resposta da agenda');
      await sleep(300);
      certo(await ev(vazio), 'apareceu consulta sem a agenda conectada');
      await foto('dia-sem-agenda.png');
    } finally { SEM_AGENDA = false; }
    AGENDA_VAZIA = true;
    try {
      await abre('?vazia=1');
      await ate(`!!window.__calUltima`, 8000, 'a resposta da agenda');
      await sleep(300);
      certo(await ev(vazio), 'apareceu consulta com a agenda vazia');
      await foto('dia-vazio.png');
    } finally { AGENDA_VAZIA = false; }
    await abre('?volta=1');
    await ate(`!!document.querySelector('.cal-inner .ev-real')`, 8000, 'a agenda de volta');
    return 'só as horas: enquanto o /calendar/events não responde, sem a agenda conectada e com a agenda conectada sem nada';
  }],
  ['a agenda sempre abre no Dia: a Semana escolhida não volta ao recarregar (nem a guardada pela versão anterior)', async () => {
    const dia = `(() => { const st = document.querySelector('.stage'), b = document.getElementById('viewSel');
      return !st.classList.contains('week') && b.getAttribute('aria-label') === 'Mudar para Semana' && /agenda-day\.svg/.test(document.getElementById('viewIcon').src); })()`;
    const abre = async (q) => {
      await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html' + q });
      await ate(`location.search === ${JSON.stringify(q)} && document.readyState === 'complete'`, 8000, 'agenda ' + q);
    };
    await ev(`localStorage.setItem('od_agenda_view', 'semana'); 1`);         // o que a versão anterior guardava
    await abre('?visao=1');
    certo(await ev(dia), 'com a Semana guardada, abriu na Semana');
    certo(await ev(`localStorage.getItem('od_agenda_view')`) === null, 'a escolha antiga ficou guardada');
    await clica('#viewSel');
    await ate(`document.querySelector('.stage').classList.contains('week')`, 3000, 'Semana pelo botão');
    certo(await ev(`localStorage.getItem('od_agenda_view')`) === null, 'a Semana foi guardada');
    await abre('?visao=2');
    certo(await ev(dia), 'depois de escolher a Semana, recarregar abriu na Semana');
    return 'abre no Dia com a Semana guardada; a Semana do botão não volta ao recarregar; nada guardado';
  }],
  ['os botões de cima (Agenda e Assistente) mostram a dica escura com o que fazem e o atalho no mouseover, sem a do navegador', async () => {
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html?dica=1' });
    await ate(`location.search === '?dica=1' && document.readyState === 'complete'`, 8000, 'agenda');
    const mouse = (x, y, type = 'mouseMoved') => send('Input.dispatchMouseEvent', { type, x, y, button: type === 'mouseMoved' ? 'none' : 'left', clickCount: 1 });
    const tecla = async (key, code, vk) => {
      await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key, code, windowsVirtualKeyCode: vk });
      await send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, windowsVirtualKeyCode: vk });
    };
    const mac = await ev(`/Mac|iPhone|iPad/.test(navigator.platform || '')`);
    const ligada = `document.querySelector('.nav-tip').classList.contains('on')`;
    const longe = async () => { await mouse(700, 600); await ate(`!(${ligada})`, 1000, 'a dica some ao sair'); };
    const dica = (id) => ev(`(() => { const b = document.getElementById(${JSON.stringify(id)}), t = b.getBoundingClientRect(),
        p = document.querySelector('.nav-tip'), r = p.getBoundingClientRect(), cs = getComputedStyle(p);
      return { on: p.classList.contains('on'), texto: p.querySelector('span').textContent, label: b.getAttribute('aria-label'),
               title: b.getAttribute('title'), atalho: getComputedStyle(p.querySelector('kbd')).display, h: r.height,
               kbd: p.querySelector('kbd').textContent, ks: b.getAttribute('aria-keyshortcuts'),
               kdir: Math.round(r.right - p.querySelector('kbd').getBoundingClientRect().right),
               pad: [cs.paddingLeft, cs.paddingRight], vao: Math.round(r.top - t.bottom), esq: Math.round(r.left), dir: Math.round(innerWidth - r.right),
               centro: Math.round(r.left + r.width / 2 - (t.left + t.width / 2)), bx: t.left + t.width / 2, by: t.top + t.height / 2 }; })()`);
    const passa = async (id, texto, letra) => {
      let d = await dica(id);
      await mouse(d.bx, d.by);
      await ate(ligada, 2000, `dica do ${id}`);
      d = await dica(id);
      certo(d.texto === texto && d.label === texto && d.title === null && d.h === 30 && d.vao === 6 && d.esq >= 8 && d.dir >= 8,
            `${id}: ` + JSON.stringify(d));
      // o atalho na etiqueta cinza, a 6 px da beira, e anunciado ao leitor de tela
      certo(d.atalho === 'flex' && d.kbd === (mac ? '⇧⌘' : 'Ctrl+Shift+') + letra && d.pad.join() === '14px,6px' && d.kdir === 6 &&
            d.ks === (mac ? 'Meta+Shift+' : 'Control+Shift+') + letra, `${id}: atalho ` + JSON.stringify(d));
      // centrada no botão, a não ser que encoste na beira da tela (o último do Assistente)
      certo(Math.abs(d.centro) <= 1 || d.dir === 8, `${id}: posição ` + JSON.stringify(d));
      return d;
    };
    const vistos = [];
    for (const [id, texto, letra] of BOTOES) {
      await longe();
      const d = await passa(id, texto, letra);
      if (id === 'raExpand') await foto('dica-barras.png');
      vistos.push(texto + ' ' + d.kbd + (d.dir === 8 ? ' (na beira)' : ''));
    }
    await longe();
    // o nome muda com o estado: o clique esconde a dica, e a próxima já diz o novo
    let d = await dica('viewSel');
    await mouse(d.bx, d.by); await ate(ligada, 2000, 'dica do Dia/Semana');
    await mouse(d.bx, d.by, 'mousePressed'); await mouse(d.bx, d.by, 'mouseReleased');
    await ate(`document.querySelector('.stage').classList.contains('week') && !(${ligada})`, 2000, 'Semana pelo clique, sem a dica');
    await longe(); await passa('viewSel', 'Mudar para Dia', 'U');
    await clica('#viewSel');
    await ate(`!document.querySelector('.stage').classList.contains('week')`, 2000, 'de volta ao Dia');
    // o calendário: o clique abre o calendário e esconde a dica; o Esc fecha e a dica não volta sozinha
    await longe();
    d = await dica('calBtn');
    await mouse(d.bx, d.by); await ate(ligada, 2000, 'dica do calendário');
    await mouse(d.bx, d.by, 'mousePressed'); await mouse(d.bx, d.by, 'mouseReleased');
    await ate(`!document.getElementById('calPop').hidden && !(${ligada})`, 2000, 'calendário aberto, sem a dica');
    await tecla('Escape', 'Escape', 27);
    await ate(`document.getElementById('calPop').hidden`, 2000, 'o Esc fecha o calendário');
    await sleep(500);
    certo(!(await ev(ligada)), 'a dica voltou depois do Esc');
    // pelo teclado: o Tab que chega ao botão mostra a dica dele
    await longe();
    await ev(`document.getElementById('agCreate').focus(); 1`);
    await tecla('Tab', 'Tab', 9);
    await ate(`document.activeElement && document.activeElement.id === 'calBtn' && ${ligada}`, 2000, 'dica pelo Tab');
    certo((await dica('calBtn')).texto === 'Escolher data', 'texto da dica pelo Tab');
    await ev(`document.activeElement.blur(); 1`);
    await ate(`!(${ligada})`, 1000, 'a dica some ao sair do botão');
    return vistos.join(', ') + '; o nome que muda (Dia/Semana); clique e Esc não deixam a dica; Tab mostra';
  }],
  ['cada atalho aperta o seu botão; com o botão escondido não faz nada; letra sem botão e digitar sem ⌘ ficam como estão', async () => {
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    const mac = await ev(`/Mac|iPhone|iPad/.test(navigator.platform || '')`);
    const mods = (mac ? 4 : 2) + 8;                              // ⌘ (ou Ctrl) + Shift
    let n = 0;
    const nova = async () => {                                   // agenda do zero, contando os cliques nos botões
      const q = '?atalho=' + (++n);
      await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html' + q });
      await ate(`location.search === ${JSON.stringify(q)} && document.readyState === 'complete'`, 8000, 'agenda ' + q);
      await ate(`!!window.__calConnected`, 8000, 'agenda conectada');
      await ev(`window.__cliques = []; document.addEventListener('click', (e) => {
        const b = e.target.closest && e.target.closest('#navToggle, .hd-btn'); if (b) window.__cliques.push(b.id); }, true); 1`);
    };
    const atalho = async (letra, m = mods) => {
      const p = { modifiers: m, key: m & 8 ? letra : letra.toLowerCase(), code: 'Key' + letra, windowsVirtualKeyCode: letra.charCodeAt(0) };
      await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', ...p });
      await send('Input.dispatchKeyEvent', { type: 'keyUp', ...p });
    };
    const efeito = {
      calBtn: `!document.getElementById('calPop').hidden`,
      viewSel: `document.querySelector('.stage').classList.contains('week')`,
      agSearch: `!document.getElementById('busca').hidden`,
      agExpand: `document.querySelector('.right').classList.contains('collapsed')`,
      raHist: `document.querySelector('.stage').classList.contains('expanded')`,
      raExpand: `document.querySelector('.stage').classList.contains('expanded')`,
    };
    const feitos = [];
    for (const [id, , letra] of BOTOES) {
      await nova();
      await atalho(letra);
      await ate(`window.__cliques.join() === ${JSON.stringify(id)}`, 2000, `${id} pelo atalho ${letra}`);
      if (efeito[id]) await ate(efeito[id], 2000, `o que o ${id} faz`);
      feitos.push(letra + ' → ' + id);
    }
    // o atalho é um clique de verdade: com a janela do evento aberta (⇧⌘E), o ⇧⌘D fecha ela (fecha ao clicar fora) e abre o calendário
    await nova();
    await atalho('E');
    await ate(`!document.getElementById('evPop').hidden`, 2000, 'janela do evento pelo atalho');
    await atalho('D');
    await ate(`document.getElementById('evPop').hidden && !document.getElementById('calPop').hidden`, 2000, 'o ⇧⌘D fecha o evento e abre o calendário');
    // o assistente que volta pelo prontuário ("Perguntar ao assistente" aperta o #showChat): o Expandir agenda volta ao nome dele
    await nova();
    await atalho('A');
    await ate(`document.querySelector('.right').classList.contains('collapsed') && document.getElementById('agExpand').getAttribute('aria-label') === 'Mostrar assistente'`, 2000, 'assistente escondido');
    await clica('#showChat');
    await ate(`!document.querySelector('.right').classList.contains('collapsed') && document.getElementById('agExpand').getAttribute('aria-label') === 'Expandir agenda'`, 2000, 'o nome do Expandir agenda depois do assistente voltar');
    // com o Assistente na tela toda, a barra da agenda some: o atalho dela não aperta o botão escondido
    await nova();
    await atalho('X');
    await ate(efeito.raExpand + ` && !document.getElementById('agCreate').getClientRects().length`, 2000, 'Assistente na tela toda');
    await ev(`window.__cliques = []; 1`);
    await atalho('E');
    await sleep(300);
    certo(await ev(`window.__cliques.length === 0`), 'o atalho apertou o botão escondido: ' + await ev(`window.__cliques.join()`));
    // letra sem botão: o navegador fica com ela (não é bloqueada)
    const livre = await ev(`(() => { const e = new KeyboardEvent('keydown', { key: 'G', code: 'KeyG', shiftKey: true, metaKey: ${mac},
      ctrlKey: ${!mac}, bubbles: true, cancelable: true }); document.body.dispatchEvent(e); return !e.defaultPrevented; })()`);
    certo(livre, '⇧⌘G foi bloqueado sem ter botão');
    // digitar no Assistente sem ⌘: as letras vão para o texto, nenhum botão é apertado
    await nova();
    await ev(`document.getElementById('biInput').focus(); 1`);
    await send('Input.insertText', { text: 'edufahox' });
    for (const l of ['E', 'D', 'U']) await atalho(l, 8);         // só Shift: letra maiúscula, sem atalho
    await sleep(200);
    certo(await ev(`window.__cliques.length === 0`), 'digitar apertou botão: ' + await ev(`window.__cliques.join()`));
    return feitos.join(', ') + '; botão escondido não; ⇧⌘G livre; digitar não';
  }],
  ['a busca abre no meio da tela: Tudo · Consultas · Pacientes · Receitas, o trecho em negrito, o termo nunca na URL', async () => {
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    const abre = async (q) => {
      await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html' + q });
      await ate(`location.pathname === '/opendoctor-agenda.html' && document.readyState === 'complete' && !!window.__calConnected`, 8000, 'agenda ' + q);
      // o prontuário não abre de verdade aqui (as rotas dele não existem neste teste): guarda o que a busca pediu
      await ev(`window.__abriu = []; window.__openProntuario = (c) => { window.__abriu.push(c); }; 1`);
    };
    const key = async (key, code, vk, m = 0) => {
      await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', modifiers: m, key, code, windowsVirtualKeyCode: vk });
      await send('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: m, key, code, windowsVirtualKeyCode: vk });
    };
    const aberta = `!document.getElementById('busca').hidden`;
    const linhas = () => ev(`[...document.querySelectorAll('#bsList .bs-it')].map((b) => ({ tipo: b.dataset.tipo, t: b.querySelector('.bs-r').textContent, k: b.querySelector('.bs-k').textContent,
        b: [...b.querySelectorAll('.bs-r b')].map((x) => x.textContent).join('|'), s: (b.querySelector('.bs-s') || {}).textContent || '',
        d: (b.querySelector('.bs-d') || {}).textContent || '', on: b.classList.contains('on') }))`);
    const digita = async (t) => { await ev(`document.getElementById('bsIn').focus(); 1`); await send('Input.insertText', { text: t }); };
    const aba = async (a) => { await clica(`#bsAbas [data-aba="${a}"]`); };
    // os cenários anteriores criaram pacientes: volta à lista do começo (a de exemplo e a Joana)
    PACS.splice(0, PACS.length, { id: 7, name: 'Maria Silva', example: true }, { id: 5, name: 'Joana Prado' }); MAIS = false;
    await abre('?busca=1');
    const antes = pedidos.length;

    // o Buscar do menu abre a janela: 780 × 572 no meio da tela, a agenda atrás sem foco, o campo com o foco
    await clica('#navBuscar');
    await ate(`${aberta} && document.querySelectorAll('#bsList .bs-it').length > 0`, 5000, 'a busca pelo menu');
    const g = await ev(`(() => { const r = document.getElementById('bsCard').getBoundingClientRect();
      return { w: r.width, h: r.height, x: Math.round(r.left), y: Math.round(r.top), inert: document.querySelector('.stage').inert,
               foco: document.activeElement && document.activeElement.id, abas: [...document.querySelectorAll('#bsAbas [data-aba]')].map((b) => b.textContent + (b.classList.contains('on') ? '*' : '')),
               limpa: document.getElementById('bsLimpa').hidden, sep: getComputedStyle(document.querySelector('.bs-sep')).display }; })()`);
    certo(g.w === 780 && g.h === 572 && g.x === 330 && g.y === 164 && g.inert && g.foco === 'bsIn' && g.limpa && g.sep === 'none' &&
          g.abas.join() === 'Tudo*,Consultas,Pacientes,Receitas', 'janela: ' + JSON.stringify(g));
    let L = await linhas();
    certo(L[0].on && L.filter((x) => x.on).length === 1, 'a primeira linha vem marcada: ' + JSON.stringify(L));
    certo(L.some((x) => x.tipo === 'consulta') && L.filter((x) => x.tipo === 'paciente').map((x) => x.t).join() === 'Joana Prado,Maria Silva',
          'sem termo: as próximas consultas e os pacientes recentes (a de exemplo por último): ' + JSON.stringify(L));

    // com termo (sem diferença de maiúsculas): pacientes, consultas e receitas, o trecho em negrito, a data à direita
    await digita('JOANA');
    await ate(`[...document.querySelectorAll('#bsList .bs-it')].some((b) => b.dataset.tipo === 'receita')`, 4000, 'a receita da Joana');
    L = await linhas();
    certo(L[0].tipo === 'paciente' && L[0].t === 'Joana Prado' && L[0].b === 'Joana' && L[0].on, 'o paciente primeiro: ' + JSON.stringify(L[0]));
    // o tipo vem antes do achado: "Paciente · Joana Prado", "Consulta · …", "Receita · …"
    certo(L.every((x) => x.k === { paciente: 'Paciente · ', consulta: 'Consulta · ', receita: 'Receita · ' }[x.tipo]), 'o tipo primeiro: ' + JSON.stringify(L.map((x) => x.k + x.t)));
    certo(await ev(`document.querySelector('#bsList .bs-it .bs-t').textContent`) === 'Paciente · Joana Prado', 'a linha inteira');
    const c = L.find((x) => x.tipo === 'consulta'), r = L.find((x) => x.tipo === 'receita');
    certo(c && /Joana Prado$/.test(c.t) && c.b === 'Joana' && / de [a-z]{3}\./.test(c.d), 'a consulta: ' + JSON.stringify(c));
    certo(r && r.t === 'Losartana 50 mg' && r.s === 'Joana Prado · Emitida' && r.d.startsWith('5 de nov.'), 'a receita: ' + JSON.stringify(r));
    certo(!L.some((x) => x.t === 'Maria Silva'), 'quem não bate saiu');
    await foto('busca.png');
    certo(!(await ev(`document.getElementById('bsLimpa').hidden`)) && (await ev(`getComputedStyle(document.querySelector('.bs-sep')).display`)) !== 'none',
          'o Limpar (e o divisor) aparecem com texto');
    // o termo (pode ser um nome) nunca vai na URL; nas receitas, só no corpo do POST
    const depois = pedidos.slice(antes);
    certo(!depois.some((x) => /joana/i.test(x.path + JSON.stringify(x.q))), 'nome na URL: ' + JSON.stringify(depois.map((x) => x.path)));
    const rx = depois.filter((x) => x.path === '/prontuario/receitas/busca');
    certo(rx.length === 1 && rx[0].method === 'POST' && rx[0].body.q === 'JOANA' && !Object.keys(rx[0].q).length, 'busca das receitas: ' + JSON.stringify(rx));
    // setas
    await key('ArrowDown', 'ArrowDown', 40);
    certo((await linhas())[1].on, 'a seta desce');
    await key('ArrowUp', 'ArrowUp', 38);
    certo((await linhas())[0].on, 'a seta sobe');

    // cada aba mostra só o seu
    await aba('receitas'); await ate(`[...document.querySelectorAll('#bsList .bs-it')].every((b) => b.dataset.tipo === 'receita')`, 2000, 'aba Receitas');
    await aba('pacientes'); await ate(`[...document.querySelectorAll('#bsList .bs-it')].map((b) => b.dataset.tipo + ':' + b.querySelector('.bs-r').textContent).join() === 'paciente:Joana Prado'`, 2000, 'aba Pacientes');
    await aba('consultas'); await ate(`document.querySelectorAll('#bsList .bs-it').length && [...document.querySelectorAll('#bsList .bs-it')].every((b) => b.dataset.tipo === 'consulta')`, 2000, 'aba Consultas');
    certo(await ev(`document.activeElement.id === 'bsIn'`), 'a aba devolve o foco ao campo');
    // Limpar: tira o termo e fica na aba
    await clica('#bsLimpa');
    await ate(`document.getElementById('bsIn').value === '' && document.getElementById('bsLimpa').hidden && document.querySelector('#bsAbas .on').dataset.aba === 'consultas'`, 2000, 'Limpar');
    // Receitas sem termo: as recentes; escolher uma abre o prontuário dela na aba Prescrições
    await aba('receitas');
    await ate(`[...document.querySelectorAll('#bsList .bs-it .bs-r')].some((t) => t.textContent === 'Clonazepam 2 mg, Dipirona 500 mg')`, 3000, 'as receitas recentes');
    L = await linhas();
    certo(L.find((x) => x.t === 'Clonazepam 2 mg, Dipirona 500 mg').s === 'Maria Silva · Emitida · Controle especial', 'o tipo na linha: ' + JSON.stringify(L));
    await ev(`[...document.querySelectorAll('#bsList .bs-it')].find((b) => b.querySelector('.bs-r').textContent.startsWith('Clonazepam')).click(); 1`);
    await ate(`!(${aberta}) && !document.querySelector('.stage').inert && window.__abriu.length === 1`, 2000, 'abriu a receita');
    const a1 = await ev(`window.__abriu[0]`);
    certo(a1.patient_id === 7 && a1.patient === 'Maria Silva' && a1.tab === 'prescricoes' && a1.rx === RECEITAS[1].id, 'o prontuário da receita: ' + JSON.stringify(a1));

    // ⇧⌘F abre de novo, limpa; Enter abre o paciente marcado
    const mods = (await ev(`/Mac|iPhone|iPad/.test(navigator.platform || '')`)) ? 4 + 8 : 2 + 8;
    await key('F', 'KeyF', 70, mods);
    await ate(`${aberta} && document.getElementById('bsIn').value === '' && document.querySelector('#bsAbas .on').dataset.aba === 'consultas'`, 2000, 'a lupa (⇧⌘F) abre limpa, já nas consultas');
    await clica('#bsX'); await ate(`!(${aberta})`, 2000, 'fecha');
    await clica('#navBuscar');
    await ate(`${aberta} && document.querySelector('#bsAbas .on').dataset.aba === 'tudo'`, 2000, 'o Buscar do menu abre em Tudo');
    await digita('joana');
    await ate(`(document.querySelector('#bsList .bs-it.on') || {}).dataset?.tipo === 'paciente'`, 3000, 'paciente marcado');
    await key('Enter', 'Enter', 13);
    await ate(`!(${aberta}) && window.__abriu.length === 2`, 2000, 'Enter abriu o paciente');
    const a2 = await ev(`window.__abriu[1]`);
    certo(a2.patient_id === 5 && a2.patient === 'Joana Prado' && !a2.tab && !a2.rx, 'o prontuário do paciente: ' + JSON.stringify(a2));

    // a consulta: vai ao dia dela, selecionada
    await clica('#agSearch');
    await ate(aberta, 2000, 'a lupa abre');
    await aba('consultas'); await digita('pedro');
    await ate(`[...document.querySelectorAll('#bsList .bs-it .bs-r')].map((t) => t.textContent).join() === 'Retorno — Pedro Lima'`, 3000, 'só a consulta do Pedro');
    await ev(`document.querySelector('#bsList .bs-it').click(); 1`);
    await ate(`!(${aberta}) && window.__selEv === 'manha'`, 2000, 'a consulta escolhida');
    // Enter logo depois de digitar (antes da lista redesenhar) vale para o que está escrito
    await clica('#agSearch'); await ate(aberta, 2000, 'abre');
    await aba('consultas');
    await ate(`document.querySelectorAll('#bsList .bs-it').length > 1`, 2000, 'a lista sem termo');
    await digita('pedro'); await key('Enter', 'Enter', 13);
    await ate(`!(${aberta}) && window.__selEv === 'manha'`, 2000, 'o Enter rápido abriu a consulta certa (' + await ev(`window.__selEv`) + ')');

    // a resposta atrasada (as receitas chegam depois) não tira a linha que a pessoa marcou
    LENTA_RX = 900;
    try {
      await clica('#navBuscar'); await ate(aberta, 2000, 'abre');
      await digita('joana');
      await ate(`(() => { const b = [...document.querySelectorAll('#bsList .bs-it')];
        return b.length >= 2 && b[0].querySelector('.bs-r').textContent === 'Joana Prado' && !b.some((x) => x.dataset.tipo === 'receita'); })()`, 2000, 'a lista da joana, antes das receitas');
      await key('ArrowDown', 'ArrowDown', 40);
      const marcada = await ev(`document.querySelector('#bsList .bs-it.on .bs-r').textContent + '|' + document.querySelector('#bsList .bs-it.on').dataset.tipo`);
      await ate(`[...document.querySelectorAll('#bsList .bs-it')].some((b) => b.dataset.tipo === 'receita')`, 3000, 'as receitas chegam');
      const depois = await ev(`document.querySelector('#bsList .bs-it.on .bs-r').textContent + '|' + document.querySelector('#bsList .bs-it.on').dataset.tipo`);
      certo(marcada === depois && !marcada.endsWith('|paciente'), 'a linha marcada mudou com a resposta: ' + marcada + ' → ' + depois);
      await clica('#bsX'); await ate(`!(${aberta})`, 2000, 'fecha');
    } finally { LENTA_RX = 0; }
    await clica('#calBtn'); await ate(`!document.getElementById('calPop').hidden && document.getElementById('calBtn').classList.contains('on')`, 2000, 'calendário aberto');
    await clica('#navBuscar'); await ate(aberta, 2000, 'abre por cima do calendário');
    certo(await ev(`document.getElementById('calPop').hidden && !document.getElementById('calBtn').classList.contains('on')`), 'o ícone do calendário ficou apertado');
    await clica('#bsX'); await ate(`!(${aberta})`, 2000, 'fecha');
    // o foco não sai da janela (Tab real); fecha no ×, fora dela e no Esc
    await clica('#agSearch'); await ate(aberta, 2000, 'abre');
    for (let i = 0; i < 9; i++) await key('Tab', 'Tab', 9);
    certo(await ev(`document.getElementById('bsCard').contains(document.activeElement)`), 'o Tab saiu da janela: ' + await ev(`document.activeElement.outerHTML.slice(0, 80)`));
    await clica('#bsX'); await ate(`!(${aberta}) && !document.querySelector('.stage').inert`, 2000, 'o × fecha');
    await clica('#agSearch'); await ate(aberta, 2000, 'abre');
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: 60, y: 450, button: 'left', clickCount: 1 });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: 60, y: 450, button: 'left', clickCount: 1 });
    await ate(`!(${aberta})`, 2000, 'clicar fora fecha');
    // nada achado (como a referência): a lupa e "Nenhum resultado" no meio da lista, e o Limpar (há texto)
    await clica('#navBuscar'); await ate(aberta, 2000, 'abre');
    await digita('xyzw');
    await ate(`!!document.querySelector('#bsList .bs-vazio')`, 3000, 'o vazio');
    const v = await ev(`(() => { const c = document.getElementById('bsCard').getBoundingClientRect(), l = document.getElementById('bsList').getBoundingClientRect(),
        e = document.querySelector('#bsList .bs-vazio'), t = e.querySelector('span').getBoundingClientRect(), i = e.querySelector('svg').getBoundingClientRect();
      const x0 = i.left, x1 = t.right, y = (i.top + i.bottom) / 2;
      return { texto: e.textContent, cor: getComputedStyle(e).color, fs: getComputedStyle(e).fontSize, ic: [i.width, i.height],
               dx: Math.round((x0 + x1) / 2 - (c.left + c.width / 2)), dy: Math.round(y - (l.top + (l.height - 12) / 2)),
               limpa: !document.getElementById('bsLimpa').hidden, linhas: document.querySelectorAll('#bsList .bs-it').length }; })()`);
    certo(v.texto === 'Nenhum resultado' && v.cor === 'rgb(132, 132, 132)' && v.fs === '16px' && v.ic.join() === '16,16' &&
          Math.abs(v.dx) <= 1 && Math.abs(v.dy) <= 1 && v.limpa && !v.linhas, 'nada achado: ' + JSON.stringify(v));
    await foto('busca-vazia.png');
    for (const a of ['consultas', 'pacientes', 'receitas']) {
      await aba(a);
      await ate(`(document.querySelector('#bsList .bs-vazio') || {}).textContent === 'Nenhum resultado'`, 3000, 'nada achado em ' + a);
    }
    await key('Escape', 'Escape', 27); await ate(`!(${aberta})`, 2000, 'fecha');
    // sem agenda conectada: não pede para conectar — Consultas só diz que não há, Tudo mostra o resto
    SEM_AGENDA = true;
    try {
      await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html?semagenda=1' });
      await ate(`location.search === '?semagenda=1' && document.readyState === 'complete' && window.__calConnected === false`, 8000, 'agenda sem calendário');
      await clica('#agSearch');
      await ate(`${aberta} && document.querySelector('#bsAbas .on').dataset.aba === 'consultas' && /Nenhuma consulta/.test(document.getElementById('bsList').textContent)`, 3000, 'Consultas sem agenda');
      certo(!/Conecte|Integrações/.test(await ev(`document.getElementById('bsCard').textContent`)), 'pediu para conectar a agenda');
      await aba('tudo');
      await ate(`[...document.querySelectorAll('#bsList .bs-it')].some((b) => b.dataset.tipo === 'paciente')`, 3000, 'Tudo sem agenda');
      certo(!/Conecte|Integrações/.test(await ev(`document.getElementById('bsCard').textContent`)), 'pediu para conectar a agenda no Tudo');
      await key('Escape', 'Escape', 27);
    } finally { SEM_AGENDA = false; }
    // de outra tela: agenda#buscar abre a busca (em Tudo) e o endereço volta ao normal
    await abre('?outra=1#buscar');
    await ate(`${aberta} && location.hash === '' && document.querySelector('#bsAbas .on').dataset.aba === 'tudo'`, 3000, 'o #buscar abre a busca em Tudo');
    await key('Escape', 'Escape', 27);
    await ate(`!(${aberta})`, 2000, 'o Esc fecha');
    return 'menu, lupa, ⇧⌘F e #buscar; 780×572 no meio; Tudo/Consultas/Pacientes/Receitas; negrito; nome só no corpo; Enter, setas, Tab, ×, fora, Esc';
  }],
  ['Pacientes no tamanho dos Diagnósticos: os 3 números, nome com a etiqueta da última consulta e idade · consultas embaixo | ⋯, alinhado com o título e a lupa, as páginas presas embaixo e o novo paciente (com contato e convênio) no lugar do assistente pelo + no alto', async () => {
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    const dias = (n) => new Date(Date.now() - n * 864e5).toISOString();
    PACS.splice(0, PACS.length,
      { id: 7, name: 'Maria Silva', example: true, notes: 11, last: dias(20), birth_date: '1972-03-10', sex: 'F' },
      { id: 5, name: 'Joana Prado', notes: 3, last: dias(100), birth_date: '1988-06-01', sex: 'F' },
      { id: 11, name: 'Carlos Nunes', notes: 1, last: dias(400), birth_date: '1955-01-20', sex: 'M' },
      { id: 12, name: 'Ana Clara Ribeiro', notes: 0 });
    for (let i = 1; i <= 35; i++) PACS.push({ id: 100 + i, name: 'Paciente ' + String(i).padStart(2, '0'), notes: i % 3, last: i % 3 ? dias(i * 9) : null });
    MAIS = false;
    await send('Page.navigate', { url: ORIG + '/opendoctor-agenda.html?pacientes=1' });
    await ate(`location.search === '?pacientes=1' && document.readyState === 'complete'`, 8000, 'agenda');
    await ev(`window.__abriu = []; window.__openProntuario = (c) => { window.__abriu.push(c); }; 1`);
    await clica('#navPacientes');
    await ate(`document.querySelectorAll('#ptList .pt-lista .pt-linha').length === 30`, 5000, 'a lista');
    const t = await ev(`(() => ({
      nums: ['ptStTotal', 'ptStCons', 'ptSt30'].map((i) => document.getElementById(i).textContent), cards: document.querySelectorAll('#ptStats .pt-stat').length,
      rotulos: [...document.querySelectorAll('#ptStats .pt-stat span')].map((x) => x.textContent),
      cab: document.querySelectorAll('#ptList table, #ptList th').length,
      pag: document.getElementById('ptPag').textContent,
      maria: (() => { const r = [...document.querySelectorAll('#ptList .pt-linha')].find((x) => x.querySelector('.pt-name').textContent === 'Maria Silva');
        return r && { ini: !!r.querySelector('.pt-ini'), barra: !!r.querySelector('.pt-bar, .pt-cons i'), nome: r.querySelector('.pt-nm').textContent,
                      sub: r.querySelector('.pt-desc small').textContent, dir: r.children.length,
                      tags: [...r.querySelectorAll('.pt-nm .pt-ex, .pt-tag')].map((x) => x.textContent + '|' + Math.round(x.getBoundingClientRect().height) + '|' + getComputedStyle(x).backgroundColor + '|' + getComputedStyle(x).borderTopLeftRadius + '|' + getComputedStyle(x).paddingLeft + ',' + getComputedStyle(x).paddingRight + '|' + getComputedStyle(x).fontSize),
                      num: [...r.querySelectorAll('.pt-numc b, .pt-numc small')].map((x) => x.textContent).join('|'),
                      pos: (() => { const c = r.querySelector('.pt-ultc:not(.pt-numc)'), b = c.querySelector('b'), s = c.querySelector('small'), m = r.querySelector('.pt-mais').getBoundingClientRect();
                        const n = r.querySelector('.pt-name'), i = r.querySelector('.pt-desc small'), st = (x) => getComputedStyle(x), fs = (x) => st(x).fontSize + '/' + st(x).fontWeight + '/' + st(x).color;
                        return { b: b && b.textContent, s: s && s.textContent, linhas: [Math.round(b.getBoundingClientRect().top - n.getBoundingClientRect().top), Math.round(s.getBoundingClientRect().top - i.getBoundingClientRect().top)],
                                 estilo: [fs(b) === fs(n), fs(s) === fs(i)], dx: Math.round(c.getBoundingClientRect().left - r.getBoundingClientRect().left),
                                 fim: Math.round(r.getBoundingClientRect().right - m.right) }; })(),
                      alt: Math.round(r.getBoundingClientRect().height), cols: getComputedStyle(r).gridTemplateColumns }; })(),
      ana: (() => { const r = [...document.querySelectorAll('#ptList .pt-linha')].find((x) => x.querySelector('.pt-name').textContent === 'Ana Clara Ribeiro');
        return r && { sub: r.querySelector('.pt-desc small').textContent, tags: r.querySelectorAll('.pt-tag').length, ult: r.querySelector('.pt-ultc:not(.pt-numc)').textContent,
                      num: [...r.querySelectorAll('.pt-numc b, .pt-numc small')].map((x) => x.textContent).join('|') }; })(),
      sits: document.querySelectorAll('#ptList .pt-st').length,
      alts: [...new Set([...document.querySelectorAll('#ptList .pt-linha')].map((r) => Math.round(r.getBoundingClientRect().height)))].join(),
    }))()`);
    // 39 pacientes; consultas: a soma das registradas (11 + 3 + 1 + 0 e as dos 35); nos últimos 30 dias: a Maria (20) e os de 9 e 18 dias
    const n30 = 1 + [1, 2, 3].filter((i) => i % 3).length, cons = 15 + Array.from({ length: 35 }, (_, k) => (k + 1) % 3).reduce((a, b) => a + b, 0);
    certo(t.cards === 3 && t.rotulos.join() === 'Pacientes,Atendidos em 30 dias,Total de consultas' && t.nums.join() === ['39', String(cons), String(n30)].join(),
          'os números: ' + JSON.stringify(t));
    certo(t.cab === 0, 'a lista não tem cabeçalho nem tabela');
    // no tamanho dos Diagnósticos: nome | 128 | ⋯, 18 em cima e embaixo (18 + 4 + 16 de texto + 36 + 1 da divisória = 75); sem iniciais e sem barra
    // a etiqueta Exemplo (pontas redondas, 22 de altura, 10 de cada lado, a fonte de 12) ao lado do nome; à direita, a 12 px do ⋯,
    // "Última consulta" na linha e no estilo do nome e a data ("26 Out de 2026") na linha e no estilo da idade
    const [ex] = (t.maria && t.maria.tags) || [];
    certo(t.maria && t.maria.tags.length === 1 && /^Exemplo\|22\|/.test(ex) && ex.split('|')[3] === '11px' && ex.split('|')[4] === '10px,10px' && ex.split('|')[5] === '12px',
          'a etiqueta da Maria: ' + JSON.stringify(t.maria && t.maria.tags));
    const pz = t.maria && t.maria.pos;
    certo(pz && pz.b === 'Última' && /^\d{1,2} (Jan|Fev|Mar|Abr|Mai|Jun|Jul|Ago|Set|Out|Nov|Dez) de \d{4}$/.test(pz.s) && pz.linhas.every((x) => Math.abs(x) <= 1) &&
          pz.estilo.every(Boolean) && Math.abs(pz.dx - 2 * (parseFloat(t.maria.cols) + 24)) <= 1 && pz.fim === 0, 'a última consulta na 3ª coluna (depois das consultas), nas linhas do nome e da idade; o ⋯ no fim: ' + JSON.stringify(pz));
    certo(t.maria.num === 'Consultas|11 consultas', 'a coluna do número de consultas: ' + t.maria.num);
    // as colunas começam no mesmo lugar em todas as linhas (também nas sem última consulta), nas linhas do nome e da idade
    const cols = await ev(`(() => { const u = (sel) => [...new Set([...document.querySelectorAll('#ptList .pt-linha')].map((r) => { const x = r.querySelector(sel); return x && x.textContent ? Math.round(x.getBoundingClientRect().left) : null; }).filter((x) => x != null))];
      const r = [...document.querySelectorAll('#ptList .pt-linha')].find((x) => x.querySelector('.pt-name').textContent === 'Ana Clara Ribeiro');
      const nb = r.querySelector('.pt-numc b').getBoundingClientRect(), ns = r.querySelector('.pt-numc small').getBoundingClientRect(),
            n = r.querySelector('.pt-name').getBoundingClientRect(), i = r.querySelector('.pt-desc small').getBoundingClientRect();
      return { ult: u('.pt-ultc:not(.pt-numc) b'), num: u('.pt-numc b'), linhas: [Math.round(nb.top - n.top), Math.round(ns.top - i.top)] }; })()`);
    const larg = parseFloat(t.maria.cols);
    certo(cols.ult.length === 1 && cols.num.length === 1 && Math.abs(cols.ult[0] - cols.num[0] - larg - 24) <= 1 && cols.linhas.every((x) => Math.abs(x) <= 1),
          'as colunas alinhadas (Consultas logo depois do nome, a Última uma coluna depois): ' + JSON.stringify(cols));
    const esq = await ev(`[...new Set([...document.querySelectorAll('#ptList .pt-linha')].map((r) => { const c = r.querySelector('.pt-ultc:not(.pt-numc) b'); return c ? Math.round(c.getBoundingClientRect().left) : null; }).filter((x) => x != null))].join()`);
    const fins = await ev(`[...new Set([...document.querySelectorAll('#ptList .pt-linha .pt-mais')].map((m) => Math.round(m.getBoundingClientRect().right)))].join()`);
    certo(!/,/.test(esq) && !/,/.test(fins), 'a última consulta começa no mesmo lugar em todas as linhas e o ⋯ termina no mesmo: ' + esq + ' / ' + fins);
    certo(t.maria && !t.maria.ini && !t.maria.barra && t.maria.nome === 'Maria SilvaExemplo' && /^\d+ anos$/.test(t.maria.sub) &&
          t.maria.dir === 4 && t.maria.alt === 75 && t.alts === '75' && ((v) => v.length === 4 && v[3] === 32 && Math.abs(v[0] - v[1]) < 1 && Math.abs(v[1] - v[2]) < 1)(t.maria.cols.split(' ').map(parseFloat)),
          'a linha da Maria (e todas com 75): ' + JSON.stringify(t.maria) + ' ' + t.alts);
    certo(t.ana && t.ana.sub === '' && t.ana.tags === 0 && t.ana.ult === 'ÚltimaNenhuma consulta' && t.ana.num === 'Consultas|Nenhuma consulta',
          'sem consultas (e sem idade): a linha de baixo vazia; a última e o número com "Nenhuma consulta": ' + JSON.stringify(t.ana));
    certo(t.sits === 0, 'ainda há selo de situação');
    const alto = await ev(`(() => { const h = document.querySelector('.pt-head'), st = document.getElementById('ptStats'), b = document.getElementById('ptNew');
      return { ids: [...h.querySelectorAll('.hd-actions .hd-btn')].map((x) => x.id).join(), hd: b.classList.contains('hd-btn'), img: b.querySelector('img').getAttribute('src'),
               label: b.getAttribute('aria-label'), pop: b.getAttribute('aria-controls') + '|' + b.getAttribute('aria-expanded') + '|' + b.getAttribute('aria-haspopup'), velho: document.querySelectorAll('.pt-tools, .pt-acao').length,
               vao: Math.round(st.getBoundingClientRect().top - h.getBoundingClientRect().bottom) }; })()`);
    certo(alto.ids === 'ptNew,ptBusca' && alto.hd && alto.img === 'assets/icons/agenda-add.svg?v=3' && alto.label === 'Novo paciente' && alto.pop === 'ptNewRow|false|null' && alto.velho === 0 && alto.vao === 32,
          'o + no alto, antes da lupa (como o do calendário), e os números 32 abaixo: ' + JSON.stringify(alto));
    // o conteúdo começa com a palavra "Pacientes" e termina com o desenho da lupa (10,8 para dentro do botão de 36), nas duas larguras;
    // da lista aos números, 40
    const alinha = async () => ev(`(() => { const tit = document.querySelector('.pt-title'), rg = document.createRange(); rg.selectNodeContents(tit);
      const esq = rg.getBoundingClientRect().left, lupa = document.getElementById('ptBusca').getBoundingClientRect().right - 10.771;
      const st = document.getElementById('ptStats').getBoundingClientRect(), li = document.querySelector('#ptList .pt-linha').getBoundingClientRect(),
            nav = document.querySelector('#ptPag .pt-nav').getBoundingClientRect(), cont = document.querySelector('#ptPag .pt-cont').getBoundingClientRect();
      const d = (x) => Math.round(x * 10) / 10;
      return { st: [d(st.left - esq), d(st.right - lupa)], li: [d(li.left - esq), d(li.right - lupa)], pag: [d(cont.left - esq), d(nav.right - lupa)],
               lista: Math.round(li.top - st.bottom) }; })()`);
    for (const larga of [false, true]) {
      if (larga) { await ev(`document.querySelector('.right').classList.add('collapsed'); 1`); await sleep(200); }
      const al = await alinha();
      certo(await ev(`((v) => v.length === 4 && v[3] === 32 && Math.abs(v[0] - v[1]) < 1 && Math.abs(v[1] - v[2]) < 1)(getComputedStyle(document.querySelector('#ptList .pt-linha')).gridTemplateColumns.split(' ').map(parseFloat))`),
            (larga ? 'sem' : 'com') + ' o assistente, as 3 colunas iguais: ' + await ev(`getComputedStyle(document.querySelector('#ptList .pt-linha')).gridTemplateColumns`));
      certo([...al.st, ...al.li, ...al.pag].every((x) => Math.abs(x) <= 1) && al.lista === 40,
            (larga ? 'sem o assistente' : 'com o assistente') + ': alinhado com o título e a lupa, e 40 até a lista: ' + JSON.stringify(al));
      if (larga) { await ev(`document.querySelector('.right').classList.remove('collapsed'); 1`); await sleep(200); }
    }
    // o rodapé sem a linha de cima e sem o "Linhas por página"
    const rod = await ev(`(() => { const p = document.getElementById('ptPag'); return { linha: getComputedStyle(p).borderTopWidth, sel: p.querySelectorAll('select, .pt-pp').length,
      txt: /Linhas por página/.test(p.textContent) }; })()`);
    certo(rod.linha === '0px' && rod.sel === 0 && !rod.txt, 'o rodapé: ' + JSON.stringify(rod));
    // a linha em cima do rodapé só quando a lista encosta nele: com os 30 passando por baixo, sim; no fim da rolagem
    // (24 de espaço), não; com poucos na tela (a página 2 em uma tela alta), não
    const linha = `document.getElementById('ptPag').classList.contains('linha') && getComputedStyle(document.getElementById('ptPag')).boxShadow !== 'none'`;
    await ate(linha, 2000, 'a linha com a lista passando por baixo do rodapé');
    await ev(`(() => { const v = document.getElementById('ptView'); v.scrollTop = v.scrollHeight; return 1; })()`);
    await ate(`!(${linha})`, 2000, 'sem a linha no fim da rolagem');
    await foto('pacientes-fim.png');
    await ev(`(() => { const v = document.getElementById('ptView'); v.scrollTop = v.scrollHeight - v.clientHeight - 40; return 1; })()`);
    await ate(linha, 2000, 'a linha volta ao subir um pouco');
    await ev(`document.getElementById('ptView').scrollTop = 0; 1`);
    certo(/39 pacientes/.test(t.pag) && /Página 1 de 2/.test(t.pag), 'o rodapé: ' + t.pag);
    await foto('pacientes.png');
    if (process.env.SHOT) { await ev(`document.querySelector('.right').classList.add('collapsed'); 1`); await sleep(200); await foto('pacientes-larga.png');
      await ev(`document.querySelector('.right').classList.remove('collapsed'); 1`); }   // a agenda larga (sem o assistente): todas as colunas
    // páginas: 30 por página; a próxima tem os 9 que faltam
    await ev(`document.querySelector('#ptPag .pt-nav [aria-label="Próxima página"]').click(); 1`);
    await ate(`document.querySelectorAll('#ptList .pt-linha').length === 9 && /Página 2 de 2/.test(document.getElementById('ptPag').textContent)`, 2000, 'a página 2');
    certo(await ev(`document.querySelector('#ptPag .pt-nav [aria-label="Próxima página"]').disabled && document.querySelector('#ptPag .pt-nav [aria-label="Última página"]').disabled`), 'na última, as setas para a frente apagam');
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1600, deviceScaleFactor: 1, mobile: false });
    await ate(`!document.getElementById('ptPag').classList.contains('linha')`, 2000, 'com espaço até o rodapé (9 em uma tela alta), sem a linha');
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    await ate(`document.getElementById('ptPag').classList.contains('linha')`, 2000, 'a tela volta a 900: os 9 encostam no rodapé');
    await ev(`document.querySelector('#ptPag .pt-nav [aria-label="Primeira página"]').click(); 1`);
    await ate(`document.querySelectorAll('#ptList .pt-linha').length === 30 && /Página 1 de 2/.test(document.getElementById('ptPag').textContent)`, 2000, 'de volta à página 1');
    // o ⋯: abrir, renomear; o Excluir só para quem pode (sem anotações, ou a de exemplo)
    const menu = async (nome) => {
      await ev(`(() => { const r = [...document.querySelectorAll('#ptList .pt-linha')].find((x) => x.querySelector('.pt-name').textContent === ${JSON.stringify(nome)}); r.querySelector('.pt-mais').click(); return 1; })()`);
      await ate(`!document.getElementById('ptMenu').hidden`, 2000, 'o menu de ' + nome);
      const itens = await ev(`[...document.querySelectorAll('#ptMenu button')].map((b) => b.textContent).join()`);
      await tecla('Escape');
      await ate(`document.getElementById('ptMenu').hidden`, 2000, 'o Esc fecha o menu');
      return itens;
    };
    certo((await menu('Ana Clara Ribeiro')) === 'Abrir prontuário,Renomear,Excluir', 'sem anotações: pode excluir');
    certo((await menu('Carlos Nunes')) === 'Abrir prontuário,Renomear', 'com prontuário: não exclui');
    // buscar é pela lupa no alto, como no calendário: abre a busca já em Pacientes (o clique e o ⇧⌘F); a página não tem campo
    certo(await ev(`!document.getElementById('ptSearch') && !!document.querySelector('.pt-head #ptBusca')`), 'a lupa no alto, sem o campo na página');
    await clica('#ptBusca');
    await ate(`!document.getElementById('busca').hidden && document.querySelector('#bsAbas .on').dataset.aba === 'pacientes'`, 2000, 'a lupa abre em Pacientes');
    await ev(`(() => { document.getElementById('bsX').click(); return 1; })()`);
    await ate(`document.getElementById('busca').hidden`, 2000, 'fecha');
    const modsF = (await ev(`/Mac|iPhone|iPad/.test(navigator.platform || '')`)) ? 4 + 8 : 2 + 8;
    await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', modifiers: modsF, key: 'F', code: 'KeyF', windowsVirtualKeyCode: 70 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: modsF, key: 'F', code: 'KeyF', windowsVirtualKeyCode: 70 });
    await ate(`!document.getElementById('busca').hidden && document.querySelector('#bsAbas .on').dataset.aba === 'pacientes'`, 2000, 'o ⇧⌘F em Pacientes');
    await ev(`(() => { document.getElementById('bsX').click(); return 1; })()`);
    await ate(`document.getElementById('busca').hidden`, 2000, 'fecha');
    // as páginas ficam presas embaixo da tela
    const fundo = await ev(`(() => { const p = document.getElementById('ptPag').getBoundingClientRect(), v = document.getElementById('ptView').getBoundingClientRect();
      return { pag: Math.round(p.bottom), view: Math.round(v.bottom), larg: Math.round(p.width), vl: Math.round(v.width) }; })()`);
    certo(Math.abs(fundo.pag - fundo.view) <= 1 && Math.abs(fundo.larg - fundo.vl) <= 16, 'o rodapé embaixo, de margem a margem: ' + JSON.stringify(fundo));
    await foto('pacientes-rodape.png');
    await ev(`[...document.querySelectorAll('#ptList .pt-linha')].find((r) => r.querySelector('.pt-name').textContent === 'Joana Prado').querySelector('.pt-desc small').click(); 1`);
    await ate(`window.__abriu.length === 1`, 2000, 'a linha abre o prontuário');
    const a = await ev(`window.__abriu[0]`);
    certo(a.patient_id === 5 && a.patient === 'Joana Prado' && a.from === 'pacientes', 'o prontuário: ' + JSON.stringify(a));
    // o + tem a dica escura do calendário: "Novo paciente" e o ⇧⌘E (o mesmo do Criar evento)
    const macN = await ev(`/Mac|iPhone|iPad/.test(navigator.platform || '')`);
    const centro = await ev(`(() => { const r = document.getElementById('ptNew').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: centro.x, y: centro.y, button: 'none' });
    await ate(`document.querySelector('.nav-tip').classList.contains('on')`, 2000, 'a dica do +');
    const dicaN = await ev(`(() => ({ txt: document.querySelector('.nav-tip span').textContent, kbd: document.querySelector('.nav-tip kbd').textContent,
      ks: document.getElementById('ptNew').getAttribute('aria-keyshortcuts') }))()`);
    certo(dicaN.txt === 'Novo paciente' && dicaN.kbd === (macN ? '⇧⌘E' : 'Ctrl+Shift+E') && dicaN.ks === (macN ? 'Meta+Shift+E' : 'Control+Shift+E'),
          'a dica do +: ' + JSON.stringify(dicaN));
    await foto('pacientes-dica-mais.png');
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 700, y: 600, button: 'none' });
    await ate(`!document.querySelector('.nav-tip').classList.contains('on')`, 2000, 'a dica some');
    const modsE = (macN ? 4 : 2) + 8;
    await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', modifiers: modsE, key: 'E', code: 'KeyE', windowsVirtualKeyCode: 69 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: modsE, key: 'E', code: 'KeyE', windowsVirtualKeyCode: 69 });
    await ate(`!document.getElementById('ptNewRow').hidden && document.activeElement.id === 'ptNewName'`, 2000, 'o ⇧⌘E abre o novo paciente');
    certo(await ev(`document.getElementById('evPop').hidden`), 'o ⇧⌘E em Pacientes abriu o evento da agenda');
    // com o formulário aberto, o ⇧⌘E só volta ao nome (não apaga o que foi digitado, nem abre outra coisa por cima)
    await send('Input.insertText', { text: 'Digitado' });
    await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', modifiers: modsE, key: 'E', code: 'KeyE', windowsVirtualKeyCode: 69 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: modsE, key: 'E', code: 'KeyE', windowsVirtualKeyCode: 69 });
    await sleep(200);
    certo(await ev(`!document.getElementById('ptNewRow').hidden && document.getElementById('evPop').hidden && document.activeElement.id === 'ptNewName' && document.getElementById('ptNewName').value === 'Digitado'`), 'o ⇧⌘E com o formulário aberto');
    await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await ate(`document.getElementById('ptNewRow').hidden && document.activeElement.id === 'ptNew'`, 2000, 'o Esc fecha e volta ao +');
    // com o prontuário aberto por cima de Pacientes (o Voltar volta a ela), o ⇧⌘E e o ⇧⌘F não apertam os botões de baixo
    await ev(`document.querySelector('.stage').classList.add('prontuario'); 1`);
    certo(await ev(`getComputedStyle(document.getElementById('ptNew')).visibility === 'hidden'`), 'Pacientes à vista embaixo do prontuário');
    for (const [k, vk] of [['E', 69], ['F', 70]]) {
      await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', modifiers: modsE, key: k, code: 'Key' + k, windowsVirtualKeyCode: vk });
      await send('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: modsE, key: k, code: 'Key' + k, windowsVirtualKeyCode: vk });
    }
    await sleep(200);
    certo(await ev(`document.getElementById('ptNewRow').hidden && document.getElementById('busca').hidden`), 'o ⇧⌘E/⇧⌘F apertou um botão escondido atrás do prontuário');
    await ev(`document.querySelector('.stage').classList.remove('prontuario'); 1`);
    // o aviso de sessão por cima do novo paciente: o Tab fica com o aviso (o formulário de baixo não puxa o foco)
    await clica('#ptNew');
    await ate(`document.activeElement.id === 'ptNewName'`, 2000, 'a janela do novo paciente (para o aviso)');
    await ev(`document.getElementById('odSession').hidden = false; document.getElementById('odSessionGo').focus(); 1`);
    await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    await sleep(100);
    certo(await ev(`!document.activeElement.closest('#ptNewRow') && !document.getElementById('ptNewRow').hidden`), 'o Tab do aviso de sessão foi para a janela de baixo: ' + await ev(`document.activeElement.id`));
    await ev(`document.getElementById('odSession').hidden = true; 1`);
    await clica('#ptNewX');
    await ate(`document.getElementById('ptNewRow').hidden && document.activeElement.id === 'ptNew'`, 2000, 'fecha');
    // fechar de novo o formulário já fechado (a resposta atrasada do cadastro) não tira o foco de quem está digitando
    await ev(`document.getElementById('biInput').focus(); 1`);
    await clica('#ptNewX');
    await sleep(100);
    certo(await ev(`document.activeElement.id === 'biInput' && document.getElementById('ptNewRow').hidden`), 'fechar o já fechado puxou o foco: ' + await ev(`document.activeElement.id`));
    // novo paciente no lugar do assistente: ocupa a coluna dele (a conversa fica por baixo, fora do Tab e dos atalhos), a
    // tela de Pacientes continua viva (sem inert, sem janela por cima); Esc e o × fecham e devolvem o foco ao +
    await ev(`document.getElementById('biInput').value = 'pergunta guardada'; 1`);
    await clica('#ptNew');
    await ate(`!document.getElementById('ptNewRow').hidden && document.activeElement.id === 'ptNewName'`, 2000, 'o novo paciente');
    const lugar = await ev(`(() => { const f = document.getElementById('ptNewRow').getBoundingClientRect(), r = document.querySelector('.right').getBoundingClientRect();
      const st = (sel) => getComputedStyle(document.querySelector(sel)).visibility;
      return { mesmo: [f.left - r.left, f.top - r.top, f.width - r.width, f.height - r.height].every((x) => Math.abs(x) <= 1), dentro: !!document.getElementById('ptNewRow').closest('.right'),
               inerte: document.querySelector('.stage').inert, modal: document.getElementById('ptNewRow').getAttribute('aria-modal'),
               baixo: [st('.right > .rp-head'), st('#biInput'), st('#rpMsgs')].join(), titulo: document.getElementById('ptNewT').textContent,
               mais: document.getElementById('ptNew').getAttribute('aria-expanded') + '|' + document.getElementById('ptNew').classList.contains('on'),
               auto: ['ptNewName', 'ptNewEmail', 'ptNewPhone', 'ptNewPlano'].map((i) => document.getElementById(i).getAttribute('autocomplete')).join(),
               tipos: [document.getElementById('ptNewEmail').type, document.getElementById('ptNewPhone').type].join(),
               plano: document.getElementById('ptNewPlanoBox').getClientRects().length === 0 }; })()`);
    certo(lugar.mesmo && lugar.dentro && !lugar.inerte && lugar.modal === null && lugar.baixo === 'hidden,hidden,hidden' && lugar.titulo === 'Novo paciente' &&
          lugar.mais === 'true|true' && lugar.auto === 'off,off,off,off' && lugar.tipos === 'email,tel' && lugar.plano,
          'o formulário no lugar do assistente: ' + JSON.stringify(lugar));
    await foto('pacientes-novo.png');
    await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await ate(`document.getElementById('ptNewRow').hidden && document.activeElement.id === 'ptNew' && !document.querySelector('.right').classList.contains('novo')`, 2000, 'o Esc fecha');
    certo(await ev(`getComputedStyle(document.getElementById('biInput')).visibility === 'visible' && document.getElementById('biInput').value === 'pergunta guardada' && document.getElementById('ptNew').getAttribute('aria-expanded') === 'false'`),
          'o assistente volta como estava');
    // o × também fecha
    await clica('#ptNew');
    await ate(`document.activeElement.id === 'ptNewName'`, 2000, 'abre de novo');
    await clica('#ptNewX');
    await ate(`document.getElementById('ptNewRow').hidden && document.activeElement.id === 'ptNew'`, 2000, 'o × fecha');
    // com o assistente recolhido, o + abre a coluna para o formulário e, ao fechar, recolhe de novo
    await ev(`document.getElementById('agExpand').click(); 1`);
    await ate(`document.querySelector('.right').classList.contains('collapsed')`, 2000, 'assistente recolhido');
    await clica('#ptNew');
    await ate(`!document.getElementById('ptNewRow').hidden && !document.querySelector('.right').classList.contains('collapsed') && document.activeElement.id === 'ptNewName'`, 2000, 'o + abre o assistente recolhido');
    await clica('#ptNewX');
    await ate(`document.getElementById('ptNewRow').hidden && document.querySelector('.right').classList.contains('collapsed')`, 2000, 'fechar recolhe de novo');
    await ev(`document.getElementById('agExpand').click(); 1`);
    await ate(`!document.querySelector('.right').classList.contains('collapsed')`, 2000, 'o assistente de volta');
    // abrir um prontuário ou sair de Pacientes fecha o formulário sem chamar o foco do + e, se o assistente estava recolhido,
    // recolhe de novo
    await ev(`(() => { const b = document.getElementById('ptNew'); window.__foco = 0; b.focus = function () { window.__foco++; return HTMLElement.prototype.focus.apply(this, arguments); }; return 1; })()`);
    for (const [saida, faz, volta] of [['o prontuário', `document.querySelector('.stage').classList.add('prontuario')`, `document.querySelector('.stage').classList.remove('prontuario')`],
                                        ['Consultas', `document.getElementById('navConsultas').click()`, `document.getElementById('navPacientes').click()`]]) {
      for (const recolher of [false, true]) {
        if (recolher) { await ev(`document.getElementById('agExpand').click(); 1`); await ate(`document.querySelector('.right').classList.contains('collapsed')`, 2000, 'recolhido'); }
        await clica('#ptNew');
        await ate(`!document.getElementById('ptNewRow').hidden && !document.querySelector('.right').classList.contains('collapsed')`, 2000, 'aberto');
        await ev(`window.__foco = 0; ${faz}; 1`);
        await ate(`document.getElementById('ptNewRow').hidden && !document.querySelector('.right').classList.contains('novo')`, 2000, saida + ' fecha o formulário');
        certo(await ev(`window.__foco === 0 && document.querySelector('.right').classList.contains('collapsed') === ${recolher}`),
              saida + (recolher ? ' (assistente recolhido)' : '') + ': o foco foi ao + ou o assistente não voltou como estava');
        await ev(`${volta}; 1`);
        if (recolher) { await ev(`document.getElementById('agExpand').click(); 1`); await ate(`!document.querySelector('.right').classList.contains('collapsed')`, 2000, 'de volta'); }
        await ate(`document.querySelector('.stage').classList.contains('pacientes') && !document.querySelector('.stage').classList.contains('prontuario')`, 2000, 'de volta a Pacientes');
      }
    }
    await ev(`delete document.getElementById('ptNew').focus; 1`);
    // a resposta atrasada de um cadastro não mexe no formulário aberto de novo para outro paciente
    LENTO_PAC = 700;
    try {
      await clica('#ptNew');
      await ate(`document.activeElement.id === 'ptNewName'`, 2000, 'aberto (lento)');
      await send('Input.insertText', { text: 'Primeiro Lento' });
      await clica('#ptNewSave');
      await ate(`document.getElementById('ptNewSave').disabled`, 2000, 'enviando');
      await clica('#ptNewX');
      await clica('#ptNew');
      await ate(`document.activeElement.id === 'ptNewName' && !document.getElementById('ptNewSave').disabled`, 2000, 'reaberto, o botão livre');
      await send('Input.insertText', { text: 'Segundo' });
      // o primeiro foi criado e a lista recarregou (ele pode estar na página 2: confere o GET depois da resposta)
      let recarregou = false;
      for (const t0 = Date.now(); Date.now() - t0 < 4000 && !recarregou; await sleep(50)) {
        const i = pedidos.findIndex((x) => x.method === 'POST' && x.path === '/patients' && x.body && x.body.name === 'Primeiro Lento');
        recarregou = i >= 0 && pedidos.slice(i + 1).some((x) => x.method === 'GET' && x.path === '/patients');
      }
      certo(recarregou, 'a resposta atrasada não recarregou a lista');
      await sleep(150);
      certo(await ev(`!document.getElementById('ptNewRow').hidden && document.getElementById('ptNewName').value === 'Segundo' && document.getElementById('ptNewErr').hidden`),
            'a resposta atrasada fechou ou mexeu no formulário reaberto');
      await clica('#ptNewX');
    } finally { LENTO_PAC = 0; }
    // sem a migração 0021 (503): o formulário limpa e-mail e atendimento e cria o paciente sem eles no clique seguinte
    FALTA_0021 = true;
    try {
      await clica('#ptNew');
      await ate(`document.activeElement.id === 'ptNewName'`, 2000, 'aberto (sem a 0021)');
      await send('Input.insertText', { text: 'Sem Migracao' });
      await ev(`(() => { document.getElementById('ptNewEmail').value = 'sem@exemplo.invalid'; const c = document.getElementById('ptNewCov'); c.value = 'particular'; c.dispatchEvent(new Event('change', { bubbles: true })); return 1; })()`);
      await clica('#ptNewSave');
      await ate(`/ainda não podem ser salvos/.test(document.getElementById('ptNewErr').textContent) && document.getElementById('ptNewEmail').value === '' && document.getElementById('ptNewCov').value === ''`, 3000, 'o 503 limpa o que não dá para salvar');
      await clica('#ptNewSave');
      await ate(`document.getElementById('ptNewRow').hidden`, 3000, 'criou e fechou');   // (na página 2 da lista: confere o POST)
      const sem = pedidos.filter((x) => x.method === 'POST' && x.path === '/patients' && x.body && x.body.name === 'Sem Migracao');
      certo(sem.length === 2 && sem[0].body.email && sem[0].body.coverage === 'particular' && !sem[1].body.email && !sem[1].body.coverage && !sem[1].body.health_plan,
            'o segundo envio sem e-mail e atendimento: ' + JSON.stringify(sem.map((x) => x.body)));
    } finally { FALTA_0021 = false; }
    // convênio: aparece o plano (e é obrigatório); particular: some o plano. Nada vai ao servidor sem o plano
    await clica('#ptNew');
    await ate(`document.activeElement.id === 'ptNewName'`, 2000, 'abre para criar');
    await send('Input.insertText', { text: 'Beatriz Nova' });
    await ev(`(() => { document.getElementById('ptNewEmail').value = 'beatriz.nova@exemplo.invalid'; document.getElementById('ptNewPhone').value = '(11) 91234-5678'; return 1; })()`);
    // o CPF (fictício, com os dígitos certos): só números, com os pontos e o traço; incompleto não vai ao servidor
    await ev(`document.getElementById('ptNewCpf').focus(); 1`);
    await send('Input.insertText', { text: '5299822' });
    certo(await ev(`document.getElementById('ptNewCpf').value`) === '529.982.2', 'a máscara do CPF pela metade: ' + await ev(`document.getElementById('ptNewCpf').value`));
    const antesCpf = pedidos.filter((x) => x.method === 'POST' && x.path === '/patients').length;
    await clica('#ptNewSave');
    await ate(`document.getElementById('ptNewErr').textContent === 'CPF incompleto.' && document.activeElement.id === 'ptNewCpf' && document.getElementById('ptNewCpf').closest('.fl').classList.contains('bad')`, 2000, 'CPF incompleto');
    certo(pedidos.filter((x) => x.method === 'POST' && x.path === '/patients').length === antesCpf, 'mandou ao servidor com o CPF incompleto');
    await send('Input.insertText', { text: 'x4725' });
    certo(await ev(`document.getElementById('ptNewCpf').value`) === '529.982.247-25', 'a máscara do CPF: ' + await ev(`document.getElementById('ptNewCpf').value`));
    await ev(`(() => { const s = document.getElementById('ptNewCov'); s.value = 'convenio'; s.dispatchEvent(new Event('change', { bubbles: true })); return 1; })()`);
    await ate(`document.getElementById('ptNewPlanoBox').getClientRects().length > 0 && document.activeElement.id === 'ptNewPlano'`, 2000, 'convênio: o plano aparece');
    await foto('pacientes-novo-convenio.png');
    const antes = pedidos.filter((x) => x.method === 'POST' && x.path === '/patients').length;
    await clica('#ptNewSave');
    await ate(`document.getElementById('ptNewErr').textContent === 'Informe o plano do convênio.' && document.activeElement.id === 'ptNewPlano' && document.getElementById('ptNewPlanoBox').classList.contains('bad')`, 2000, 'sem o plano não cria (e o campo fica vermelho)');
    // o visual do login: campos de 84 com raio 24, cinza #F7F8F8 (o da caixa de texto do assistente), o rótulo dentro; o botão preto de 84
    const vis = await ev(`(() => { const c = (i) => getComputedStyle(document.getElementById(i).closest('.fl')), b = getComputedStyle(document.getElementById('ptNewSave'));
      const pe = (() => { const corpo = document.querySelector('#ptNewRow .rp-novo-corpo'), antes = document.getElementById('ptNewSave').getBoundingClientRect().bottom;
        corpo.scrollTop = corpo.scrollHeight; const depois = document.getElementById('ptNewSave').getBoundingClientRect().bottom; corpo.scrollTop = 0;
        return { fixo: Math.abs(antes - depois) < 1, baixo: Math.round(document.getElementById('ptNewRow').getBoundingClientRect().bottom - depois), fora: !corpo.contains(document.getElementById('ptNewSave')) }; })();
      return { pe, cov: [...document.getElementById('ptNewCov').options].map((o) => o.value + ':' + o.textContent).join('|'),
               sexo: [...document.getElementById('ptNewSex').options].map((o) => o.value + ':' + o.textContent).join('|'), radios: document.querySelectorAll('#ptNewRow input[type=radio]').length,
               alt: ['ptNewName', 'ptNewCpf', 'ptNewBirth', 'ptNewSex', 'ptNewEmail', 'ptNewPhone', 'ptNewCov'].map((i) => c(i).height).join(), raio: c('ptNewEmail').borderTopLeftRadius,
               fundo: c('ptNewPhone').backgroundColor, rotulo: !!document.querySelector('#ptNewRow .fl label.fl-label[for="ptNewEmail"]'),
               botao: [b.height, b.backgroundColor, b.borderTopLeftRadius].join('|'),
               titulo: ['fontSize', 'fontWeight', 'color'].map((k) => getComputedStyle(document.getElementById('ptNewT'))[k]).join() === ['fontSize', 'fontWeight', 'color'].map((k) => getComputedStyle(document.querySelector('.right > .rp-head .rp-title'))[k]).join(),
               linha: getComputedStyle(document.getElementById('ptNewRow')).boxShadow === getComputedStyle(document.querySelector('.right')).boxShadow && getComputedStyle(document.querySelector('.right')).boxShadow !== 'none' && ['.rp-head', '.rp-novo-corpo', '.rp-novo-pe'].every((x) => getComputedStyle(document.querySelector('#ptNewRow > ' + x)).backgroundColor === 'rgba(0, 0, 0, 0)'),
               sobra: document.querySelectorAll('#ptNewCancel, #ptNewRow .nv-nota, #ptNewRow .nv-title').length,
               xNoAlto: (() => { const x = document.getElementById('ptNewX').getBoundingClientRect(), r = document.getElementById('ptNewRow').getBoundingClientRect(); return x.top - r.top < 20 && r.right - x.right < 20; })() }; })()`);
    certo(vis.pe.fixo && vis.pe.baixo === 24 && vis.pe.fora && vis.cov === ':Não informado|particular:Particular|convenio:Convênio' && vis.sexo === ':Não informado|F:Feminino|M:Masculino' && vis.radios === 0 &&
          vis.alt === '84px,84px,84px,84px,84px,84px,84px' && vis.raio === '24px' && vis.fundo === 'rgb(247, 248, 248)' && vis.rotulo &&
          vis.botao === '84px|rgb(11, 11, 12)|999px' && vis.titulo && vis.linha && vis.sobra === 0 && vis.xNoAlto,
          'o visual do login (o título do tamanho do do assistente, a linha que divide, só o × no alto, sem as dicas): ' + JSON.stringify(vis));
    // nascimento como no login: só dígitos, as barras entram sozinhas; data impossível não vai ao servidor
    await ev(`document.getElementById('ptNewBirth').focus(); 1`);
    await send('Input.insertText', { text: '31021990' });
    certo(await ev(`document.getElementById('ptNewBirth').value`) === '31/02/1990', 'a máscara do nascimento: ' + await ev(`document.getElementById('ptNewBirth').value`));
    certo(pedidos.filter((x) => x.method === 'POST' && x.path === '/patients').length === antes, 'mandou ao servidor sem o plano');
    await ev(`(() => { const s = document.getElementById('ptNewCov'); s.value = 'particular'; s.dispatchEvent(new Event('change', { bubbles: true })); return 1; })()`);
    await ate(`document.getElementById('ptNewPlanoBox').getClientRects().length === 0 && document.getElementById('ptNewErr').getClientRects().length === 0`, 2000, 'particular: o plano some');
    await ev(`(() => { const s = document.getElementById('ptNewCov'); s.value = 'convenio'; s.dispatchEvent(new Event('change', { bubbles: true })); return 1; })()`);
    await ate(`document.getElementById('ptNewPlanoBox').getClientRects().length > 0 && document.getElementById('ptNewPlano').value === ''`, 2000, 'convênio de novo: o plano vazio');
    await send('Input.insertText', { text: 'Plano Teste' });
    await clica('#ptNewSave');
    await ate(`document.getElementById('ptNewErr').textContent === 'Data de nascimento inválida.' && document.activeElement.id === 'ptNewBirth' && document.getElementById('ptNewBirth').closest('.fl').classList.contains('bad') && !document.getElementById('ptNewPlanoBox').classList.contains('bad')`, 2000, '31/02 não existe');
    certo(pedidos.filter((x) => x.method === 'POST' && x.path === '/patients').length === antes, 'mandou ao servidor com a data inválida');
    await ev(`(() => { const b = document.getElementById('ptNewBirth'); b.value = ''; b.focus(); return 1; })()`);
    await send('Input.insertText', { text: 'ab15/03-1980' });
    certo(await ev(`document.getElementById('ptNewBirth').value`) === '15/03/1980', 'a máscara tira o que não é número: ' + await ev(`document.getElementById('ptNewBirth').value`));
    await ev(`document.getElementById('ptNewPlano').focus(); 1`);
    await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
    await ate(`document.getElementById('ptNewRow').hidden && [...document.querySelectorAll('#ptList .pt-name')].some((e) => e.textContent === 'Beatriz Nova')`, 3000, 'o Enter criou e a lista mostra');
    const post = pedidos.filter((x) => x.method === 'POST' && x.path === '/patients').pop();
    certo(post && post.body.name === 'Beatriz Nova' && post.body.email === 'beatriz.nova@exemplo.invalid' && post.body.phone === '(11) 91234-5678' &&
          post.body.coverage === 'convenio' && post.body.health_plan === 'Plano Teste' && post.body.birth_date === '1980-03-15' && post.body.cpf === '52998224725' && !/Beatriz|beatriz|91234/.test(post.path),
          'o POST do novo paciente (os dados só no corpo): ' + JSON.stringify(post && post.body));
    return `39 pacientes, ${cons} consultas, ${n30} nos 30 dias; no tamanho dos Diagnósticos (3 colunas iguais: nome e idade, "Consultas" e o total, "Última" e a data ou "Nenhuma consulta"; o ⋯ no fim), alinhado com o título e a lupa, espaços 32 e 40; 30 por página, rodapé sem linha; o prontuário por cima, o aviso de sessão e a janela já fechada; páginas presas embaixo; ⋯ com o Excluir só para quem pode; linha abre o prontuário; novo paciente pelo + no alto (ao lado da lupa, dica e ⇧⌘E) no lugar do assistente, com e-mail, telefone e particular/convênio com o plano`;
  }],
];

async function main() {
  for (let i = 0; i < 50; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch (_) {} await sleep(200); }
  await new Promise((ok) => ws.addEventListener('open', ok));
  ws.addEventListener('message', (m) => {
    const j = JSON.parse(m.data);
    if (j.id && espera.has(j.id)) { const w = espera.get(j.id); espera.delete(j.id); j.error ? w.no(new Error(j.error.message)) : w.ok(j.result); return; }
    // pedido que a página cancelou (o prazo do cadastro) já não tem a quem responder: não é erro
    if (j.method === 'Fetch.requestPaused') responde(j.params).catch((e) => { if (!/Invalid InterceptionId/.test(e.message)) erros.push('interceptação: ' + e.message); });
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
