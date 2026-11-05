// Perfil no Chrome sem tela, sem servidor: as páginas de verdade (web/) são servidas pelo próprio Chrome (interceptação do
// DevTools) e as rotas respondem com uma conta fictícia. Nada vai para a rede (endereços externos são recusados).
//
//     node tests/e2e/perfil.mjs                 (SHOT=/pasta salva o Perfil em 1440×780; CHROME=/caminho para outro Chrome)
//
// Confere: o Perfil mostra nome, e-mail, CRM | UF (com "Conferido no cadastro") e especialidade, só para ver, e diz só o
// que muda em Configurações; o que a conta não tem some; enquanto carrega e no erro não aparece campo vazio; erro ao
// carregar (e o banco fora do ar: /me 503 com /me/medico 401, em qualquer ordem) avisa e tenta de novo; a sessão que
// acabou leva ao login, que volta ao Perfil; o
// Sair vai a /auth/logout e cai no login; o menu lateral de todas as telas tem o Perfil logo depois de Configurações (e
// leva a ele), aberto e recolhido.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync, existsSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, extname, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const WEB = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'web');
const ORIG = 'http://perfil.test';                         // .test nunca resolve: tudo é respondido aqui
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9910 + Math.floor(Math.random() * 40);
const PROF = mkdtempSync(join(tmpdir(), 'od-e2e-pf-'));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(...a);

const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${PROF}`, '--window-size=1440,780',
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

// ----- a conta fictícia -----
const CONTA = { id: 'u-teste', email: 'ana.souza@example.invalid', name: 'Ana Souza', picture: null, crm_status: 'verificado', crm_fonte: 'cfm' };
let MEDICO, CONFERIDO, FALHA_MEDICO, SEM_SESSAO, BANCO_FORA, LENTO_ME, LENTO_MEDICO;
function zera() {
  MEDICO = { name: 'Dra. Ana Souza', crm: '123456', crm_uf: 'SP', especialidade: 'Clínica médica', consultorio_endereco: 'Rua A, 1',
             consultorio_telefone: '(11) 3333-4444', receita_papel: 'A4' };
  CONFERIDO = true; FALHA_MEDICO = 0; SEM_SESSAO = false; BANCO_FORA = false; LENTO_ME = 0; LENTO_MEDICO = 0; pedidos.length = 0;
}
zera();
const TIPOS = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.woff2': 'font/woff2', '.woff': 'font/woff', '.json': 'application/json', '.ico': 'image/x-icon' };
// [status, corpo]; null = 404
function rota(method, path) {
  // banco fora do ar, como o servidor: o /me não sabe da sessão (503) e o guarda das rotas não acha o usuário (401)
  if (path === '/me' && BANCO_FORA) return [503, { error: 'indisponivel' }];
  if (path === '/me/medico' && BANCO_FORA) return [401, { error: 'não autenticado' }];
  if (path === '/me') return [200, SEM_SESSAO ? { logged_in: false, user: null, scribe: false, bloqueio: null, boas_vindas: false }
                                              : { logged_in: true, user: CONTA, scribe: false, bloqueio: null, boas_vindas: false }];
  if (path === '/me/medico' && method === 'GET') {
    if (SEM_SESSAO) return [401, { error: 'login necessário' }];
    if (FALHA_MEDICO > 0) { FALHA_MEDICO--; return [500, { error: 'erro' }]; }
    return [200, { medico: MEDICO, faltam: [], crm_conferido: CONFERIDO }];
  }
  if (path === '/calendar/events' && method === 'GET') return [200, { logged_in: true, connected: null, events: [] }];
  if (path === '/patients' && method === 'GET') return [200, { patients: [], more: false }];
  if (path === '/integrations/status') return [200, { logged_in: true, providers: {} }];
  return null;
}
async function responde(p) {
  const u = new URL(p.request.url), method = p.request.method;
  if (u.origin !== ORIG) return send('Fetch.failRequest', { requestId: p.requestId, errorReason: 'BlockedByClient' });
  pedidos.push({ method, path: u.pathname, search: u.search, tipo: p.resourceType });
  if (u.pathname === '/auth/logout') {                     // como o servidor: apaga a sessão e manda ao login
    SEM_SESSAO = true;
    return send('Fetch.fulfillRequest', { requestId: p.requestId, responseCode: 307,
      responseHeaders: [{ name: 'Location', value: '/opendoctor-login.html' }], body: '' });
  }
  const arq = normalize(join(WEB, decodeURIComponent(u.pathname)));
  let status = 200, tipo = 'application/json', dado;
  if (arq.startsWith(WEB) && extname(arq) && existsSync(arq)) { dado = readFileSync(arq); tipo = TIPOS[extname(arq)] || 'application/octet-stream'; }
  else {
    if (LENTO_ME && u.pathname === '/me') await sleep(LENTO_ME);
    if (LENTO_MEDICO && u.pathname === '/me/medico') await sleep(LENTO_MEDICO);
    const r = rota(method, u.pathname);
    if (r === null) status = 404; else status = r[0];
    dado = Buffer.from(JSON.stringify(r ? r[1] : {}));
  }
  return send('Fetch.fulfillRequest', { requestId: p.requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: tipo }], body: dado.toString('base64') });
}

const vis = (s) => `(() => { const e = document.querySelector(${JSON.stringify(s)}); return !!e && !e.hidden && !!e.offsetParent; })()`;
const val = (s) => ev(`document.querySelector(${JSON.stringify(s)}).value`);
const txt = (s) => ev(`(document.querySelector(${JSON.stringify(s)}) || {}).textContent || ''`);
const clica = (s) => ev(`(() => { document.querySelector(${JSON.stringify(s)}).click(); return 1; })()`);
const caixa = (s) => ev(`(() => { const r = document.querySelector(${JSON.stringify(s)}).getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; })()`);
async function foto(nome) {
  if (!process.env.SHOT) return;
  const r = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(process.env.SHOT, nome), Buffer.from(r.data, 'base64'));
}
let n = 0;
async function abre(pagina) {
  await send('Page.navigate', { url: `${ORIG}/${pagina}?n=${++n}` });
  await ate(`document.readyState === 'complete' && location.search === '?n=${n}'`, 5000, pagina);
}
const carregou = `document.getElementById('pfFoot').hidden || document.getElementById('pfSt').classList.contains('err')`;

const cenarios = [
  ['Perfil: nome, e-mail, CRM | UF conferido e especialidade, só para ver', async () => {
    zera();
    await abre('opendoctor-perfil.html');
    await ate(carregou, 4000, 'dados do Perfil');
    certo(await txt('.cfg-title') === 'Perfil', 'título: ' + await txt('.cfg-title'));
    certo(await val('#pfNome') === 'Dra. Ana Souza', 'nome: ' + await val('#pfNome'));      // o nome de Configurações (vai na receita)
    certo(await val('#pfEmail') === CONTA.email, 'e-mail: ' + await val('#pfEmail'));
    certo(await val('#pfCrm') === '123456' && await val('#pfUf') === 'SP', 'CRM/UF');
    certo(await ev(vis('#pfCrmH')) && await txt('#pfCrmH') === 'Conferido no cadastro', 'sem "Conferido no cadastro"');
    certo(await ev(vis('#pfEspF')) && await val('#pfEsp') === 'Clínica médica', 'especialidade');
    certo(await txt('#pfSub') === 'A especialidade muda em Configurações', 'subtítulo da conta conferida: ' + await txt('#pfSub'));
    certo(await ev(`document.querySelector('#pfSub a').getAttribute('href')`) === 'opendoctor-configuracoes.html', 'link do subtítulo');
    certo(await ev(`[...document.querySelectorAll('.fl-input')].every((i) => i.readOnly)`), 'campo editável no Perfil');
    certo(await ev(`document.getElementById('pfFoot').hidden`), 'o rodapé do status ficou depois de carregar');
    // o menu: Perfil marcado, logo depois de Configurações, que leva a Configurações
    const menu = await ev(`(() => { const p = document.querySelector('.nav .item[title="Perfil"]'), c = p && p.previousElementSibling;
      return { ativo: p.classList.contains('active'), href: p.getAttribute('data-href'), antes: c && c.title, cfg: c && c.getAttribute('data-href'),
               ativos: document.querySelectorAll('.nav .item.active').length }; })()`);
    certo(menu.ativo && !menu.href && menu.antes === 'Configurações' && menu.cfg === 'opendoctor-configuracoes.html' && menu.ativos === 1,
      'menu: ' + JSON.stringify(menu));
    // as medidas de Configurações: coluna de 516, cartões de canto 40, botão de 64
    const col = await caixa('.cfg'), btn = await caixa('#pfLogout');
    certo(col.w === 516 && btn.h === 64, 'medidas: ' + JSON.stringify({ col, btn }));
    certo(await ev(`getComputedStyle(document.getElementById('pfDados')).borderTopLeftRadius`) === '40px', 'canto do cartão');
    certo(!pedidos.some((r) => r.method !== 'GET'), 'o Perfil gravou algo: ' + JSON.stringify(pedidos.filter((r) => r.method !== 'GET')));
    await foto('perfil.png');
    return 'Dra. Ana Souza, e-mail, CRM 123456/SP conferido, especialidade; tudo só leitura; Perfil marcado no menu';
  }],
  ['o que a conta não tem some (sem especialidade, CRM não conferido, sem CRM)', async () => {
    zera(); MEDICO.especialidade = ''; CONFERIDO = false;
    await abre('opendoctor-perfil.html');
    await ate(carregou, 4000, 'dados do Perfil');
    certo(!(await ev(vis('#pfEspF'))), 'especialidade vazia aparece');
    certo(await ev(vis('#pfCrmF')) && !(await ev(vis('#pfCrmH'))), 'CRM não conferido com "Conferido no cadastro"');
    certo(await txt('#pfSub') === 'Nome, CRM e especialidade mudam em Configurações', 'subtítulo da conta não conferida: ' + await txt('#pfSub'));
    certo(!(await ev(`document.getElementById('pfUfC').classList.contains('vazio')`)), 'UF preenchida com cara de vazia');
    MEDICO.crm_uf = '';                                      // conta antiga com o CRM sem a UF: a metade vazia é a de Configurações
    await abre('opendoctor-perfil.html');
    await ate(carregou, 4000, 'dados do Perfil');
    const uf = await ev(`(() => { const b = document.getElementById('pfUfC'), l = b.querySelector('.fl-label'), s = getComputedStyle(b), sl = getComputedStyle(l);
      return { vazio: b.classList.contains('vazio'), fundo: s.backgroundColor, topo: sl.top, letra: sl.fontSize, crm: document.getElementById('pfCrmC').classList.contains('vazio') }; })()`);
    certo(uf.vazio && uf.fundo === 'rgb(244, 244, 246)' && uf.topo === '32.2px' && uf.letra === '14px' && !uf.crm, 'UF vazia: ' + JSON.stringify(uf));
    await foto('perfil-crm-sem-uf.png');
    MEDICO.crm = ''; MEDICO.crm_uf = ''; MEDICO.name = '';
    await abre('opendoctor-perfil.html');
    await ate(carregou, 4000, 'dados do Perfil');
    certo(!(await ev(vis('#pfCrmF'))), 'CRM vazio aparece');
    certo(await val('#pfNome') === 'Ana Souza', 'sem o nome de Configurações, o da conta: ' + await val('#pfNome'));
    await foto('perfil-sem-crm.png');
    return 'sem especialidade e sem CRM, os campos somem; sem o nome da receita, vale o da conta';
  }],
  ['erro ao carregar: avisa e tenta de novo', async () => {
    zera(); FALHA_MEDICO = 1;
    await abre('opendoctor-perfil.html');
    await ate(`document.getElementById('pfSt').classList.contains('err')`, 4000, 'aviso de erro');
    certo(await txt('#pfSt') === 'Não foi possível carregar seus dados.' && await txt('#pfRetry') === 'Tentar de novo', 'aviso: ' + await txt('#pfSt'));
    certo(!(await ev(vis('#pfCampos'))), 'no erro aparecem campos vazios');
    await clica('#pfRetry');
    await ate(`document.getElementById('pfFoot').hidden`, 4000, 'carregar de novo');
    certo(await val('#pfNome') === 'Dra. Ana Souza', 'não carregou na 2ª vez');
    return '"Não foi possível carregar seus dados." + Tentar de novo, que carrega';
  }],
  ['enquanto carrega, só o "Carregando…" (nenhum campo vazio); o cartão Sair já está lá', async () => {
    zera(); LENTO_MEDICO = 1500;
    await abre('opendoctor-perfil.html');
    await ate(`document.getElementById('pfSt').textContent === 'Carregando…'`, 1000, 'Carregando…');
    certo(!(await ev(vis('#pfCampos'))) && await ev(vis('#pfLogout')), 'carregando: campos à vista ou sem o Sair');
    await foto('perfil-carregando.png');
    await ate(carregou, 4000, 'dados do Perfil');
    certo(await ev(vis('#pfCampos')) && await val('#pfNome') === 'Dra. Ana Souza', 'depois de carregar');
    return 'carregando: só o status e o Sair; depois, os dados';
  }],
  ['banco fora do ar (/me 503 e /me/medico 401, em qualquer ordem): "Não foi possível", nunca "sessão terminou"', async () => {
    const vistos = [];
    for (const [lentoMe, lentoMed] of [[0, 600], [600, 0]]) {
      zera(); BANCO_FORA = true; LENTO_ME = lentoMe; LENTO_MEDICO = lentoMed;
      await abre('opendoctor-perfil.html');
      await ate(`document.getElementById('pfSt').classList.contains('err')`, 4000, 'aviso de erro');
      await sleep(800);                                      // a outra resposta também chegou
      certo(await txt('#pfSt') === 'Não foi possível carregar seus dados.' && await txt('#pfRetry') === 'Tentar de novo',
        `${lentoMe ? '/me depois' : '/me antes'}: ` + await txt('#pfSt'));
      vistos.push(lentoMe ? '401 antes do 503' : '503 antes do 401');
      BANCO_FORA = false;                                    // o banco voltou: Tentar de novo carrega
      await clica('#pfRetry');
      await ate(`document.getElementById('pfFoot').hidden`, 4000, 'carregar com o banco de volta');
    }
    return vistos.join(' e ') + ': "Não foi possível carregar seus dados." + Tentar de novo, que carrega com o banco de volta';
  }],
  ['sessão que acabou: "Entrar de novo" leva ao login, que volta ao Perfil', async () => {
    zera(); SEM_SESSAO = true;
    await abre('opendoctor-perfil.html');
    await ate(`document.getElementById('pfSt').classList.contains('err')`, 4000, 'aviso de sessão');
    certo(await txt('#pfSt') === 'Sua sessão terminou.' && await txt('#pfRetry') === 'Entrar de novo', 'aviso: ' + await txt('#pfSt'));
    await clica('#pfRetry');
    await ate(`location.pathname === '/opendoctor-login.html'`, 4000, 'login');
    const s = await ev('location.search');
    certo(s === '?next=%2Fopendoctor-perfil.html', 'destino depois do login: ' + s);
    return 'login com next=/opendoctor-perfil.html';
  }],
  ['Sair: vai a /auth/logout e cai no login', async () => {
    zera();
    await abre('opendoctor-perfil.html');
    await ate(carregou, 4000, 'dados do Perfil');
    certo(await txt('#pfLogout') === 'Sair', 'botão: ' + await txt('#pfLogout'));
    await clica('#pfLogout');
    await ate(`location.pathname === '/opendoctor-login.html'`, 4000, 'login depois do Sair');
    const saiu = pedidos.filter((r) => r.path === '/auth/logout');
    certo(saiu.length === 1 && saiu[0].method === 'GET' && saiu[0].tipo === 'Document', 'pedido de sair: ' + JSON.stringify(saiu));
    return 'GET /auth/logout como navegação (o servidor apaga a sessão) → login';
  }],
  ['o menu de todas as telas tem o Perfil logo depois de Configurações e leva a ele (aberto e recolhido)', async () => {
    const vistas = [];
    for (const [pagina, recolhido] of [['opendoctor-agenda.html', false], ['opendoctor-integracao.html', false],
                                       ['opendoctor-configuracoes.html', false], ['opendoctor-configuracoes.html', true],
                                       ['opendoctor-agenda.html', true]]) {
      zera();
      await ev(`localStorage.setItem('od_nav_collapsed', '${recolhido ? 1 : 0}'); 1`);
      await abre(pagina);
      const m = await ev(`(() => { const p = document.querySelectorAll('.nav .item[title="Perfil"]'), c = p[0] && p[0].previousElementSibling;
        const r = p[0] && p[0].getBoundingClientRect(), rc = c && c.getBoundingClientRect(), ic = p[0] && p[0].querySelector('.ico svg').getBoundingClientRect();
        return { n: p.length, antes: c && c.title, href: p[0] && p[0].getAttribute('data-href'), ativo: p[0] && p[0].classList.contains('active'),
                 rotulo: p[0] && getComputedStyle(p[0].lastElementChild).display, h: r && r.height, hc: rc && rc.height, w: r && r.width,
                 x: r && r.x, xc: rc && rc.x, ico: ic && [ic.width, ic.height], vao: r && rc && r.top - rc.bottom }; })()`);
      certo(m.n === 1 && m.antes === 'Configurações' && m.href === 'opendoctor-perfil.html' && !m.ativo, `${pagina}: ` + JSON.stringify(m));
      certo(m.h === m.hc && m.x === m.xc && m.vao === 4 && m.ico[0] === 16 && m.ico[1] === 16, `${pagina}: tamanho no menu ` + JSON.stringify(m));
      certo(recolhido ? (m.rotulo === 'none' && m.w === 40) : m.rotulo !== 'none', `${pagina} ${recolhido ? 'recolhido' : 'aberto'}: ` + JSON.stringify(m));
      await clica('.nav .item[title="Perfil"]');
      await ate(`location.pathname === '/opendoctor-perfil.html'`, 4000, `${pagina} → Perfil`);
      await ate(carregou, 4000, 'dados do Perfil');
      if (recolhido) certo(await ev(`document.querySelector('.nav').classList.contains('collapsed')`), 'o Perfil abriu o menu recolhido');
      vistas.push(pagina.replace('opendoctor-', '').replace('.html', '') + (recolhido ? ' (recolhido)' : ''));
    }
    await ev(`localStorage.setItem('od_nav_collapsed', '0'); 1`);
    return vistas.join(', ') + ' → Perfil';
  }],
  ['no Perfil, "Configurações" (no texto e no menu) leva a Configurações', async () => {
    zera();
    await abre('opendoctor-perfil.html');
    await ate(carregou, 4000, 'dados do Perfil');
    await clica('.cfg-sub a.cfg-back');
    await ate(`location.pathname === '/opendoctor-configuracoes.html'`, 4000, 'Configurações pelo texto');
    await abre('opendoctor-perfil.html');
    await clica('.nav .item[title="Configurações"]');
    await ate(`location.pathname === '/opendoctor-configuracoes.html'`, 4000, 'Configurações pelo menu');
    return 'pelo texto e pelo menu';
  }],
];

async function main() {
  for (let i = 0; i < 50; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch (_) {} await sleep(200); }
  await new Promise((ok) => ws.addEventListener('open', ok));
  ws.addEventListener('message', (m) => {
    const j = JSON.parse(m.data);
    if (j.id && espera.has(j.id)) { const w = espera.get(j.id); espera.delete(j.id); j.error ? w.no(new Error(j.error.message)) : w.ok(j.result); return; }
    if (j.method === 'Fetch.requestPaused') responde(j.params).catch((e) => { if (!/Invalid InterceptionId/.test(e.message)) erros.push('interceptação: ' + e.message); });
    if (j.method === 'Page.javascriptDialogOpening') { erros.push('diálogo: ' + j.params.message); send('Page.handleJavaScriptDialog', { accept: true }); }
    if (j.method === 'Runtime.exceptionThrown') erros.push(j.params.exceptionDetails.exception?.description || j.params.exceptionDetails.text);
  });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] });
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setTimezoneOverride', { timezoneId: 'America/Sao_Paulo' });
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 780, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: ORIG + '/opendoctor-perfil.html' });
  await sleep(500);
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
