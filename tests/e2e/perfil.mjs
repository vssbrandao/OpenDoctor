// Perfil no Chrome sem tela, sem servidor: as páginas de verdade (web/) são servidas pelo próprio Chrome (interceptação do
// DevTools) e as rotas respondem com uma conta fictícia. Nada vai para a rede (endereços externos são recusados).
//
//     node tests/e2e/perfil.mjs                 (SHOT=/pasta salva o Perfil em 1440×780; CHROME=/caminho para outro Chrome)
//
// Confere: o Perfil mostra nome, e-mail, CRM | UF (com "Conferido no cadastro") e especialidade, só para ver, e diz só o
// que muda em Configurações; o que a conta não tem some; enquanto carrega e no erro não aparece campo vazio; erro ao
// carregar (e o banco fora do ar: /me 503 com /me/medico 401, em qualquer ordem) avisa e tenta de novo; a sessão que
// acabou leva ao login, que volta ao Perfil; o
// Sair vai a /auth/logout e cai no login; Excluir conta abre a confirmação, que só acende com o e-mail da conta (sem
// diferença de maiúsculas e espaços), fecha sem pedir nada (Cancelar, Esc, fora da janela), avisa quando o servidor
// recusa e, confirmada, manda só o e-mail num POST JSON e sai pelo /auth/logout; o menu lateral de todas as telas tem o Perfil logo depois de Configurações (e
// leva a ele), aberto e recolhido; o botão do menu mostra a dica "Alternar barra lateral" com o atalho (⇧⌘S) no
// mouseover, sem sair da tela, e o atalho recolhe e abre o menu (menos com uma janela aberta).
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
let MEDICO, CONFERIDO, FALHA_MEDICO, SEM_SESSAO, BANCO_FORA, LENTO_ME, LENTO_MEDICO, EXCLUIR, LENTO_EXCLUIR;
function zera() {
  MEDICO = { name: 'Dra. Ana Souza', crm: '123456', crm_uf: 'SP', especialidade: 'Clínica médica', consultorio_endereco: 'Rua A, 1',
             consultorio_telefone: '(11) 3333-4444', receita_papel: 'A4' };
  CONFERIDO = true; FALHA_MEDICO = 0; SEM_SESSAO = false; BANCO_FORA = false; LENTO_ME = 0; LENTO_MEDICO = 0; pedidos.length = 0;
  EXCLUIR = [200, { ok: true }]; LENTO_EXCLUIR = 0;         // a resposta do POST /me/excluir (e a demora dela)
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
  if (path === '/me/excluir' && method === 'POST') { if (EXCLUIR[0] === 200) SEM_SESSAO = true; return EXCLUIR; }
  if (path === '/calendar/events' && method === 'GET') return [200, { logged_in: true, connected: null, events: [] }];
  if (path === '/patients' && method === 'GET') return [200, { patients: [], more: false }];
  if (path === '/integrations/status') return [200, { logged_in: true, providers: {} }];
  return null;
}
async function responde(p) {
  const u = new URL(p.request.url), method = p.request.method;
  if (u.origin !== ORIG) return send('Fetch.failRequest', { requestId: p.requestId, errorReason: 'BlockedByClient' });
  pedidos.push({ method, path: u.pathname, search: u.search, tipo: p.resourceType, corpo: p.request.postData || null,
                 ct: p.request.headers['Content-Type'] || p.request.headers['content-type'] || '' });
  if (u.pathname === '/me/excluir' && EXCLUIR === 'rede') return send('Fetch.failRequest', { requestId: p.requestId, errorReason: 'ConnectionReset' });
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
    if (LENTO_EXCLUIR && u.pathname === '/me/excluir') await sleep(LENTO_EXCLUIR);
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
    certo(await ev(`[...document.querySelectorAll('#pfCampos .fl-input')].every((i) => i.readOnly)`), 'dado da conta editável no Perfil');
    certo(await ev(`document.getElementById('pfFoot').hidden`), 'o rodapé do status ficou depois de carregar');
    // o menu: Perfil marcado, logo depois de Configurações, que leva a Configurações
    const menu = await ev(`(() => { const p = document.querySelector('.nav .item[data-tip="Perfil"]'), c = p && p.previousElementSibling;
      return { ativo: p.classList.contains('active'), href: p.getAttribute('data-href'), antes: c && c.getAttribute('data-tip'), cfg: c && c.getAttribute('data-href'),
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
    certo(uf.vazio && uf.fundo === 'rgb(247, 248, 248)' && uf.topo === '32.2px' && uf.letra === '14px' && !uf.crm, 'UF vazia: ' + JSON.stringify(uf));
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
  ['Excluir conta: apagado até os dados chegarem; a janela só acende com o e-mail da conta e fecha sem pedir nada', async () => {
    zera(); LENTO_MEDICO = 1200;
    await abre('opendoctor-perfil.html');
    certo(await ev(`document.getElementById('pfExAbre').disabled`), 'Excluir conta aceso antes dos dados');
    await ate(carregou, 4000, 'dados do Perfil');
    certo(!(await ev(`document.getElementById('pfExAbre').disabled`)), 'Excluir conta apagado depois dos dados');
    const digita = (t) => ev(`(() => { const i = document.getElementById('pfExEmail'); i.value = ${JSON.stringify(t)};
      i.dispatchEvent(new Event('input', { bubbles: true })); return document.getElementById('pfExGo').disabled; })()`);
    const aberta = () => ev(`!document.getElementById('pfExModal').hidden`);
    await clica('#pfExAbre');
    certo(await aberta() && await ev(`document.activeElement.id`) === 'pfExEmail', 'a janela não abriu com o foco no e-mail');
    certo(await ev(`document.querySelector('.stage').inert`), 'a página de trás não ficou inerte');
    const tab = (shift) => ev(`(() => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: ${shift}, bubbles: true, cancelable: true })); return document.activeElement.id; })()`);
    await ev(`document.getElementById('pfExNao').focus(), 1`);
    certo(await tab(false) === 'pfExEmail', 'o Tab saiu da janela depois do Cancelar');
    certo(await tab(true) === 'pfExNao', 'o Shift+Tab saiu da janela antes do e-mail');
    certo(await ev(`document.getElementById('pfExGo').disabled`), 'botão aceso sem e-mail');
    certo(await digita('outra@example.invalid') && await digita('ana.souza@example') && await digita(''), 'acendeu com e-mail errado');
    certo(!(await digita('  ANA.Souza@Example.INVALID ')), 'não acendeu com o e-mail da conta em maiúsculas e com espaços');
    await foto('perfil-excluir.png');
    // clique dentro do cartão e a seleção arrastada até fora não fecham
    await ev(`(() => { document.querySelector('#pfExForm p').dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      document.querySelector('#pfExForm p').dispatchEvent(new MouseEvent('click', { bubbles: true })); return 1; })()`);
    certo(await aberta(), 'o clique dentro da janela fechou');
    await ev(`(() => { document.getElementById('pfExEmail').dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      document.getElementById('pfExModal').dispatchEvent(new MouseEvent('click', { bubbles: true })); return 1; })()`);
    certo(await aberta() && await ev(`document.getElementById('pfExEmail').value`) !== '', 'arrastar a seleção do e-mail até fora fechou');
    await clica('#pfExNao');
    certo(!(await aberta()) && await ev(`document.activeElement.id`) === 'pfExAbre', 'Cancelar não fechou');
    certo(!(await ev(`document.querySelector('.stage').inert`)), 'a página de trás ficou inerte depois de fechar');
    await clica('#pfExAbre');
    certo(await ev(`document.getElementById('pfExEmail').value`) === '' && await ev(`document.getElementById('pfExGo').disabled`), 'reabriu com o e-mail anterior');
    await ev(`(() => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); return 1; })()`);
    certo(!(await aberta()), 'Esc não fechou');
    await clica('#pfExAbre');
    await ev(`(() => { const m = document.getElementById('pfExModal'); m.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      m.dispatchEvent(new MouseEvent('click', { bubbles: true })); return 1; })()`);
    certo(!(await aberta()), 'o clique fora da janela não fechou');
    await clica('#pfExAbre'); await digita('ana.souza@example.invalid');
    await ev(`(() => { document.getElementById('pfExEmail').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); return 1; })()`);
    certo(!pedidos.some((r) => r.path === '/me/excluir'), 'pediu a exclusão sem confirmar');
    return 'apagado enquanto carrega; acende só com o e-mail da conta (maiúsculas e espaços valem); Cancelar, Esc e fora fecham sem pedir';
  }],
  ['Excluir conta: o servidor recusa (e-mail, limite, sessão, erro, rede) — avisa, não sai e deixa tentar de novo', async () => {
    const casos = [[[400, { error: 'email_nao_confere' }], 'O e-mail não confere com o da conta.'],
                   [[429, { error: 'limite_ip' }], 'Muitas tentativas. Aguarde um pouco e tente de novo.'],
                   [[401, { error: 'não autenticado' }], 'Sua sessão terminou. Entre de novo para excluir a conta.'],
                   [[503, { error: 'indisponivel' }], 'Não foi possível excluir agora. Tente de novo.'],
                   [[500, { error: 'erro' }], 'Não foi possível excluir agora. Tente de novo.'],
                   ['rede', 'Não foi possível excluir agora. Tente de novo.']];
    for (const [resp, msg] of casos) {
      const rot = resp === 'rede' ? 'rede' : resp[0];
      zera(); EXCLUIR = resp;
      await abre('opendoctor-perfil.html');
      await ate(carregou, 4000, 'dados do Perfil');
      await clica('#pfExAbre');
      await ev(`(() => { const i = document.getElementById('pfExEmail'); i.value = 'ana.souza@example.invalid'; i.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
      await ev(`(() => { document.getElementById('pfExForm').requestSubmit(); return 1; })()`);
      await ate(`!document.getElementById('pfExSt').hidden`, 4000, 'aviso de ' + rot);
      certo(await txt('#pfExSt') === msg, `${rot}: "${await txt('#pfExSt')}"`);
      certo(await ev(`location.pathname`) === '/opendoctor-perfil.html' && !(await ev(`document.getElementById('pfExModal').hidden`)), `${rot}: saiu da página`);
      certo(!(await ev(`document.getElementById('pfExGo').disabled`)) && await txt('#pfExGo') === 'Excluir conta', `${rot}: não deixa tentar de novo`);
      certo(pedidos.filter((r) => r.path === '/auth/logout').length === 0, `${rot}: foi ao logout`);
    }
    return casos.map((c) => c[0] === 'rede' ? 'rede' : c[0][0]).join(', ') + ': aviso na janela, na mesma página, botão de volta';
  }],
  ['Excluir conta: confirmada, manda só o e-mail num POST JSON e sai pelo /auth/logout', async () => {
    zera(); LENTO_EXCLUIR = 1200;
    await abre('opendoctor-perfil.html');
    await ate(carregou, 4000, 'dados do Perfil');
    await clica('#pfExAbre');
    await ev(`(() => { const i = document.getElementById('pfExEmail'); i.value = 'Ana.Souza@example.invalid'; i.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
    await ev(`(() => { document.getElementById('pfExForm').requestSubmit(); return 1; })()`);
    await ate(`document.getElementById('pfExGo').textContent === 'Excluindo…'`, 1000, 'Excluindo…');
    const durante = await ev(`(() => { const n = getComputedStyle(document.getElementById('pfExNao')); return { fundo: n.backgroundColor, go: document.getElementById('pfExGo').disabled, nao: document.getElementById('pfExNao').disabled }; })()`);
    certo(durante.go && durante.nao && durante.fundo === 'rgba(0, 0, 0, 0)', 'durante o envio: ' + JSON.stringify(durante));
    await ev(`(() => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); return 1; })()`);
    certo(!(await ev(`document.getElementById('pfExModal').hidden`)), 'o Esc fechou a janela durante o envio');
    await ate(`location.pathname === '/opendoctor-login.html'`, 4000, 'login depois de excluir');
    const ex = pedidos.filter((r) => r.path === '/me/excluir'), saiu = pedidos.filter((r) => r.path === '/auth/logout');
    certo(ex.length === 1 && ex[0].method === 'POST' && /application\/json/.test(ex[0].ct), 'pedido: ' + JSON.stringify(ex));
    certo(JSON.stringify(JSON.parse(ex[0].corpo)) === JSON.stringify({ email: 'Ana.Souza@example.invalid' }), 'corpo: ' + ex[0].corpo);
    certo(!ex[0].search, 'algo na URL da exclusão: ' + ex[0].search);
    certo(saiu.length === 1 && saiu[0].tipo === 'Document', 'não saiu pelo /auth/logout: ' + JSON.stringify(saiu));
    return 'POST /me/excluir {email} (JSON, nada na URL) → /auth/logout → login';
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
      const m = await ev(`(() => { const p = document.querySelectorAll('.nav .item[data-tip="Perfil"]'), c = p[0] && p[0].previousElementSibling;
        const r = p[0] && p[0].getBoundingClientRect(), rc = c && c.getBoundingClientRect(), ic = p[0] && p[0].querySelector('.ico svg').getBoundingClientRect();
        return { n: p.length, antes: c && c.getAttribute('data-tip'), href: p[0] && p[0].getAttribute('data-href'), ativo: p[0] && p[0].classList.contains('active'),
                 rotulo: p[0] && getComputedStyle(p[0].lastElementChild).display, h: r && r.height, hc: rc && rc.height, w: r && r.width,
                 x: r && r.x, xc: rc && rc.x, ico: ic && [ic.width, ic.height], vao: r && rc && r.top - rc.bottom }; })()`);
      certo(m.n === 1 && m.antes === 'Configurações' && m.href === 'opendoctor-perfil.html' && !m.ativo, `${pagina}: ` + JSON.stringify(m));
      certo(m.h === m.hc && m.x === m.xc && m.vao === 4 && m.ico[0] === 16 && m.ico[1] === 16, `${pagina}: tamanho no menu ` + JSON.stringify(m));
      certo(recolhido ? (m.rotulo === 'none' && m.w === 40) : m.rotulo !== 'none', `${pagina} ${recolhido ? 'recolhido' : 'aberto'}: ` + JSON.stringify(m));
      await clica('.nav .item[data-tip="Perfil"]');
      await ate(`location.pathname === '/opendoctor-perfil.html'`, 4000, `${pagina} → Perfil`);
      await ate(carregou, 4000, 'dados do Perfil');
      if (recolhido) certo(await ev(`document.querySelector('.nav').classList.contains('collapsed')`), 'o Perfil abriu o menu recolhido');
      vistas.push(pagina.replace('opendoctor-', '').replace('.html', '') + (recolhido ? ' (recolhido)' : ''));
    }
    await ev(`localStorage.setItem('od_nav_collapsed', '0'); 1`);
    return vistas.join(', ') + ' → Perfil';
  }],
  ['o botão do menu mostra "Alternar barra lateral" com o atalho no mouseover, e o atalho recolhe e abre o menu', async () => {
    const mac = await ev(`/Mac|iPhone|iPad/.test(navigator.platform || '')`);
    const mods = (mac ? 4 : 2) + 8;                              // ⌘ (ou Ctrl) + Shift
    const tecla = async (key, code, vk, m = 0) => {
      await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', modifiers: m, key, code, windowsVirtualKeyCode: vk });
      await send('Input.dispatchKeyEvent', { type: 'keyUp', modifiers: m, key, code, windowsVirtualKeyCode: vk });
    };
    const atalho = () => tecla('S', 'KeyS', 83, mods);
    const mouse = (x, y, type = 'mouseMoved') => send('Input.dispatchMouseEvent', { type, x, y, button: type === 'mouseMoved' ? 'none' : 'left', clickCount: 1 });
    const recolhido = () => ev(`document.querySelector('.nav').classList.contains('collapsed')`);
    const ligada = `document.querySelector('.nav-tip').classList.contains('on')`;
    const dica = `(() => { const b = document.getElementById('navToggle'), t = b.getBoundingClientRect(), p = document.querySelector('.nav-tip'),
        r = p.getBoundingClientRect(), k = p.querySelector('kbd').getBoundingClientRect(), s = p.querySelector('span').getBoundingClientRect();
      return { on: p.classList.contains('on'), vis: getComputedStyle(p).visibility, n: document.querySelectorAll('.nav-tip').length,
               title: b.getAttribute('title'), texto: s && p.querySelector('span').textContent, atalho: p.querySelector('kbd').textContent,
               h: r.height, kh: k.height, kdir: Math.round(r.right - k.right), vao: Math.round(r.top - t.bottom),
               centro: Math.round(r.left + r.width / 2 - (t.left + t.width / 2)), esq: Math.round(r.left), dir: Math.round(innerWidth - r.right),
               fundo: getComputedStyle(p).backgroundColor, bx: t.left + t.width / 2, by: t.top + t.height / 2 }; })()`;
    const vistas = [];
    for (const pagina of ['opendoctor-agenda.html', 'opendoctor-integracao.html', 'opendoctor-configuracoes.html', 'opendoctor-perfil.html']) {
      zera();
      await ev(`localStorage.setItem('od_nav_collapsed', '0'); 1`);
      await abre(pagina);
      await mouse(700, 400);
      for (const fechado of [false, true]) {
        const onde = `${pagina} ${fechado ? 'recolhido' : 'aberto'}`;
        await ate(`getComputedStyle(document.querySelector('.nav-tip')).visibility === 'hidden'`, 1000, `${onde}: dica escondida`);
        await sleep(350);                                         // passou a janela em que a dica vem sem espera (do vizinho)
        let d = await ev(dica);
        certo(d.n === 1 && !d.on && d.vis === 'hidden' && d.title === null, `${onde}: antes do mouse ` + JSON.stringify(d));
        await mouse(d.bx, d.by);
        await sleep(150);
        certo(!(await ev(ligada)), `${onde}: a dica apareceu sem a espera`);
        await ate(ligada, 2000, `${onde}: dica no mouseover`);
        d = await ev(dica);
        certo(d.texto === 'Alternar barra lateral' && d.atalho === (mac ? '⇧⌘S' : 'Ctrl+Shift+S') && d.fundo === 'rgb(15, 15, 15)',
              `${onde}: texto ` + JSON.stringify(d));
        certo(d.h === 30 && d.kh === 18 && d.kdir === 6 && d.vao === 6 && d.esq >= 8 && d.dir >= 8, `${onde}: medidas ` + JSON.stringify(d));
        // aberto, centrada no botão; recolhido, o botão fica na beira e a dica encosta a 8 px da tela
        certo(fechado ? d.esq === 8 : Math.abs(d.centro) <= 1, `${onde}: posição ` + JSON.stringify(d));
        await mouse(700, 400);
        await ate(`!(${ligada})`, 1000, `${onde}: a dica some ao sair`);
        await atalho();
        await ate(`document.querySelector('.nav').classList.contains('collapsed') === ${!fechado}`, 1000, `${onde}: o atalho`);
        certo(await ev(`localStorage.getItem('od_nav_collapsed')`) === (fechado ? '0' : '1'), `${onde}: o atalho guarda a escolha`);
      }
      vistas.push(pagina.replace('opendoctor-', '').replace('.html', ''));
    }
    // no Perfil: clicar esconde a dica (o botão muda de lugar); Esc esconde; com a janela de excluir aberta, o atalho não mexe
    await ate(carregou, 4000, 'dados do Perfil');
    let d = await ev(dica);
    await mouse(d.bx, d.by);
    await ate(ligada, 2000, 'dica antes do clique');
    if (process.env.SHOT) {
      const r = await send('Page.captureScreenshot', { format: 'png', clip: { x: d.bx - 130, y: 0, width: 260, height: 100, scale: 2 } });
      writeFileSync(join(process.env.SHOT, 'dica-menu.png'), Buffer.from(r.data, 'base64'));
    }
    await mouse(d.bx, d.by, 'mousePressed'); await mouse(d.bx, d.by, 'mouseReleased');
    await ate(`!(${ligada})`, 1000, 'a dica some no clique');
    certo(await recolhido(), 'o clique recolheu o menu');
    d = await ev(dica);
    await mouse(700, 400); await mouse(d.bx, d.by);
    await ate(ligada, 2000, 'dica de novo');
    await tecla('Escape', 'Escape', 27);
    await ate(`!(${ligada})`, 1000, 'Esc esconde a dica');
    await mouse(700, 400);
    await clica('#pfExAbre');
    await ate(`!document.getElementById('pfExModal').hidden`, 2000, 'janela de excluir');
    await atalho();
    await sleep(200);
    certo(await recolhido() && !(await ev(`document.getElementById('pfExModal').hidden`)), 'o atalho mexeu no menu com a janela aberta');
    await clica('#pfExNao');
    await atalho();
    await ate(`!document.querySelector('.nav').classList.contains('collapsed')`, 1000, 'o atalho depois de fechar a janela');
    await ev(`localStorage.setItem('od_nav_collapsed', '0'); 1`);
    return vistas.join(', ') + ' (aberto e recolhido); clique, Esc e a janela aberta';
  }],
  ['menu retraído: cada ícone mostra a dica escura com o nome, à direita do menu; aberto, nenhuma (o nome já está escrito)', async () => {
    const mouse = (x, y) => send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none' });
    const ligada = `document.querySelector('.nav-tip').classList.contains('on')`;
    const NOMES = ['Consultas', 'Buscar', 'Pacientes', 'Prescrições', 'Integrações', 'Configurações', 'Perfil'];
    const item = (nome) => ev(`(() => { const b = document.querySelector('.nav .item[data-tip=${JSON.stringify(nome)}]'), r = b.getBoundingClientRect(),
        n = document.querySelector('.nav').getBoundingClientRect(), p = document.querySelector('.nav-tip'), t = p.getBoundingClientRect(), cs = getComputedStyle(p);
      return { on: p.classList.contains('on'), texto: p.querySelector('span').textContent, title: b.getAttribute('title'),
               atalho: getComputedStyle(p.querySelector('kbd')).display, pad: [cs.paddingLeft, cs.paddingRight], h: t.height,
               vao: Math.round(t.left - n.right), meio: Math.round(t.top + t.height / 2 - (r.top + r.height / 2)),
               bx: r.left + r.width / 2, by: r.top + r.height / 2 }; })()`);
    const vistas = [];
    for (const pagina of ['opendoctor-agenda.html', 'opendoctor-integracao.html', 'opendoctor-configuracoes.html', 'opendoctor-perfil.html']) {
      zera();
      await ev(`localStorage.setItem('od_nav_collapsed', '1'); 1`);
      await abre(pagina);
      await mouse(900, 500);
      certo(await ev(`document.querySelector('.nav').classList.contains('collapsed')`), `${pagina}: o menu não abriu retraído`);
      certo(await ev(`document.querySelectorAll('.nav .item[data-tip]').length === 7 && !document.querySelector('.nav .item[title]')`),
            `${pagina}: itens do menu sem data-tip ou ainda com title`);
      // o Buscar abre a busca: na agenda, a janela; nas outras telas, leva à agenda com ela aberta (#buscar, sem dado nenhum)
      const busca = await ev(`(() => { const b = document.querySelector('.nav .item[data-tip="Buscar"]'); return b && { id: b.id, href: b.getAttribute('data-href') }; })()`);
      certo(busca && (pagina === 'opendoctor-agenda.html' ? busca.id === 'navBuscar' && !busca.href : busca.href === 'opendoctor-agenda.html#buscar'),
            `${pagina}: o Buscar do menu ` + JSON.stringify(busca));
      for (const [i, nome] of NOMES.entries()) {
        let d = await item(nome);
        await mouse(d.bx, d.by);
        if (i === 0) await ate(ligada, 2000, `${pagina}: dica do ${nome}`);
        else {                                                    // de um ícone ao vizinho: sem a espera
          await sleep(120);
          certo(await ev(ligada), `${pagina}: a dica do ${nome} esperou`);
        }
        d = await item(nome);
        certo(d.texto === nome && d.title === null && d.atalho === 'none' && d.pad.join() === '14px,14px' && d.h === 30 &&
              d.vao === 6 && Math.abs(d.meio) <= 1, `${pagina} ${nome}: ` + JSON.stringify(d));
      }
      if (pagina === 'opendoctor-perfil.html' && process.env.SHOT) {
        const r = await send('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: 260, height: 400, scale: 2 } });
        writeFileSync(join(process.env.SHOT, 'dica-menu-retraido.png'), Buffer.from(r.data, 'base64'));
      }
      await mouse(900, 500);
      await ate(`!(${ligada})`, 1000, `${pagina}: a dica some ao sair`);
      // aberto: o nome está escrito, nenhuma dica
      await ev(`localStorage.setItem('od_nav_collapsed', '0'); 1`);
      await abre(pagina);
      const d = await item('Perfil');
      await mouse(d.bx, d.by);
      await sleep(700);
      certo(!(await ev(ligada)), `${pagina}: dica com o menu aberto`);
      await mouse(900, 500);
      vistas.push(pagina.replace('opendoctor-', '').replace('.html', ''));
    }
    return vistas.join(', ') + ': 7 ícones com o nome à direita; do vizinho sem espera; aberto, nada';
  }],
  ['no Perfil, "Configurações" (no texto e no menu) leva a Configurações', async () => {
    zera();
    await abre('opendoctor-perfil.html');
    await ate(carregou, 4000, 'dados do Perfil');
    await clica('.cfg-sub a.cfg-back');
    await ate(`location.pathname === '/opendoctor-configuracoes.html'`, 4000, 'Configurações pelo texto');
    await abre('opendoctor-perfil.html');
    await clica('.nav .item[data-tip="Configurações"]');
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
