// Cadastro (tela de login → Registro profissional) no Chrome sem tela, sem servidor: a página de verdade (web/) é servida
// pelo próprio Chrome (interceptação do DevTools) e as rotas /auth/* respondem como o servidor. Nada vai para a rede.
//
//     node tests/e2e/cadastro.mjs               (SHOT=/pasta salva o Registro profissional em 1440×780; CHROME=/outro Chrome)
//
// Confere: a etapa da senha não pede mais o nome e não vai ao servidor; o Registro profissional segue o Figma 1178-7176
// (seta no lugar do logo, título em y=155, campos de 84px em 3 linhas, botão #10132C); máscaras de CPF, nascimento, CRM e
// UF; o CRM colado com a UF ("CRM-SP 123.456", "52-1234/RJ", "1234567-P/SP"…) separa os dois; erros nos campos; a seta
// volta para a senha; Criar conta manda tudo num POST só (nada de CPF em URL); a conta pendente mostra a espera; as
// recusas do CFM aparecem no campo certo; o Google com conta nova cai direto no registro; recusada e a confirmar; a
// página de cadastros dos administradores lista, aprova e recusa (com confirmação).
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync, existsSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, extname, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const WEB = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'web');
const ORIG = 'http://cadastro.test';                       // .test nunca resolve: tudo é respondido aqui
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 9910 + Math.floor(Math.random() * 30);
const PROF = mkdtempSync(join(tmpdir(), 'od-e2e-cad-'));
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
  while (Date.now() - t0 < ms) { try { if (await ev(expr)) return; } catch (_) {} await sleep(120); }
  throw new Error('esperou demais: ' + oque);
}
const certo = (cond, msg) => { if (!cond) throw new Error(msg); };

// ----- o servidor, simulado -----
const CPF = '52998224725';
let ME = { logged_in: false, user: null, scribe: false, bloqueio: null };
let START = null;                 // resposta do /auth/signup/start (null = ok com tíquete)
let REG_GOOGLE = null;            // resposta do /auth/google/registro
let PENDENTES = [{ id: '8f14e45f-ceea-467a-9575-1a2b3c4d5e6f', name: 'Ana Lima', crm: '123456', crm_uf: 'SP', pedido_em: '2026-10-30T12:00:00+00:00', outras_contas: 0 },
  { id: '9a14e45f-ceea-467a-9575-1a2b3c4d5e70', name: 'Bia Souza', crm: '4321', crm_uf: 'RJ', pedido_em: '2026-10-30T13:00:00+00:00', outras_contas: 1 }];
let DIALOGOS = 0;                 // confirm() aceitos na página de cadastros (fora dela, diálogo é erro)
const TIPOS = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.woff2': 'font/woff2', '.json': 'application/json', '.ico': 'image/x-icon' };
function rota(method, path, body) {
  if (path === '/me') return [200, ME];
  if (path === '/auth/email/check') return [200, { exists: false, password: false, email_ok: true }];
  if (path === '/auth/signup/start') return START || [200, { ok: true, ticket: 'tk.sig', resend_in: 30, sent: true }];
  if (path === '/auth/signup/verify') return body.code === '123456'
    ? [200, { ok: true, redirect: '/opendoctor-agenda.html?bemvindo=1', bloqueio: 'crm_pendente' }]
    : [400, { error: 'codigo_incorreto', left: 4 }];
  if (path === '/auth/google/registro') return REG_GOOGLE || [200, { ok: true, redirect: '/opendoctor-agenda.html?bemvindo=1' }];
  if (path === '/auth/crm/confirmar') return [200, { ok: true, redirect: '/opendoctor-agenda.html' }];
  if (path === '/admin/cadastros') return [200, { pendentes: PENDENTES, cfm: false }];
  if (path === '/admin/cadastros/aprovar' || path === '/admin/cadastros/recusar') {
    const antes = PENDENTES.length; PENDENTES = PENDENTES.filter((p) => p.id !== body.id);
    return PENDENTES.length < antes ? [200, { ok: true, email_enviado: true }] : [409, { error: 'nao_pendente' }];
  }
  return null;
}
async function responde(p) {
  const u = new URL(p.request.url), method = p.request.method;
  if (u.origin !== ORIG) return send('Fetch.failRequest', { requestId: p.requestId, errorReason: 'BlockedByClient' });
  let body = null; try { body = p.request.postData ? JSON.parse(p.request.postData) : null; } catch (_) {}
  const arq = normalize(join(WEB, decodeURIComponent(u.pathname)));
  let status = 200, tipo = 'application/json', dado;
  if (u.pathname === '/opendoctor-agenda.html') { dado = Buffer.from('<!doctype html><title>agenda</title><p id="agenda">agenda</p>'); tipo = 'text/html'; }
  else if (arq.startsWith(WEB) && extname(arq) && existsSync(arq)) { dado = readFileSync(arq); tipo = TIPOS[extname(arq)] || 'application/octet-stream'; }
  else {
    pedidos.push({ method, path: u.pathname, url: p.request.url, body });
    const r = rota(method, u.pathname, body || {});
    if (r === null) status = 404; else status = r[0];
    dado = Buffer.from(JSON.stringify(r ? r[1] : {}));
  }
  return send('Fetch.fulfillRequest', { requestId: p.requestId, responseCode: status,
    responseHeaders: [{ name: 'Content-Type', value: tipo }], body: dado.toString('base64') });
}

const vis = (s) => ev(`(() => { const e = document.querySelector(${JSON.stringify(s)}); return !!e && !e.hidden && !!e.offsetParent; })()`);
const val = (s) => ev(`document.querySelector(${JSON.stringify(s)}).value`);
const txt = (s) => ev(`(document.querySelector(${JSON.stringify(s)}) || {}).textContent || ''`);
const clica = (s) => ev(`(() => { document.querySelector(${JSON.stringify(s)}).click(); return 1; })()`);
const titulo = () => txt('#title');
// digita como o teclado (um input por caractere) ou cola (um input só, insertFromPaste)
const digita = (s, t) => ev(`(() => { const i = document.querySelector(${JSON.stringify(s)}); i.focus(); i.value = '';
  for (const ch of ${JSON.stringify(t)}) { i.value += ch; i.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: ch })); }
  return i.value; })()`);
const cola = (s, t) => ev(`(() => { const i = document.querySelector(${JSON.stringify(s)}); i.focus(); i.value = ${JSON.stringify(t)};
  i.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertFromPaste' })); return i.value; })()`);
const sai = (s) => ev(`(() => { document.querySelector(${JSON.stringify(s)}).blur(); return 1; })()`);
const posts = (path) => pedidos.filter((r) => r.method === 'POST' && r.path === path);
async function abre(q = '') {
  await send('Page.navigate', { url: ORIG + '/opendoctor-login.html' + q });
  await ate(`document.readyState === 'complete' && !!document.getElementById('email')`, 8000, 'tela de login');
  await sleep(250);
}
async function ateRegistro() {
  await abre();
  await digita('#email', 'nova@clinica.com.br');
  await clica('#go');
  await ate(`!document.getElementById('signupForm').hidden`, 3000, 'etapa da senha');
  await digita('#newPw', 'Abcdef12!');
  await clica('#signupGo');
  await ate(`!document.getElementById('regForm').hidden`, 3000, 'Registro profissional');
}
async function preenche() {
  await digita('#rNome', 'Ana Maria Lima');
  await digita('#rCpf', CPF);
  await digita('#rNasc', '12051985');
  await digita('#rCrm', '123456');
  await digita('#rUf', 'sp');
}
const caixa = (s) => ev(`(() => { const r = document.querySelector(${JSON.stringify(s)}).getBoundingClientRect();
  return { x: Math.round(r.left * 10) / 10, y: Math.round(r.top * 10) / 10, w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10 }; })()`);

const cenarios = [
  ['a senha não pede o nome nem vai ao servidor', async () => {
    await abre();
    await digita('#email', 'nova@clinica.com.br');
    await clica('#go');
    await ate(`!document.getElementById('signupForm').hidden`, 3000, 'etapa da senha');
    certo(await titulo() === 'Crie sua conta', 'título: ' + await titulo());
    certo(!(await ev(`!!document.querySelector('#signupForm #name, #signupForm [autocomplete=name]')`)), 'o nome continua na etapa da senha');
    certo(await txt('#signupGo') === 'Continuar', 'botão: ' + await txt('#signupGo'));
    await digita('#newPw', 'fraca');
    await clica('#signupGo');
    certo(await vis('#newPwErr') && await vis('#signupForm'), 'senha fraca passou');
    await digita('#newPw', 'Abcdef12!');
    await clica('#signupGo');
    await ate(`!document.getElementById('regForm').hidden`, 3000, 'Registro profissional');
    certo(posts('/auth/signup/start').length === 0, 'Continuar foi ao servidor');
    return 'senha → Registro profissional sem nenhum POST';
  }],
  ['Registro profissional como no Figma (1440×780)', async () => {
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 780, deviceScaleFactor: 1, mobile: false });
    await ateRegistro();
    await ev(`document.activeElement.blur(); 1`);
    await sleep(300);
    certo(await titulo() === 'Registro profissional', 'título: ' + await titulo());
    certo(await vis('#back') && !(await vis('.logo')), 'a seta fica no lugar do logo');
    const rotulos = await ev(`[...document.querySelectorAll('#regForm .fl-label')].map((l) => l.textContent)`);
    certo(rotulos.join('|') === 'Nome|CPF|Nascimento|CRM|UF', 'rótulos: ' + rotulos.join('|'));
    certo(await ev(`document.getElementById('rUf').tagName === 'INPUT' && document.getElementById('rUf').type === 'text'`), 'UF não é campo de texto');
    const g = { back: await caixa('#back'), title: await caixa('#title'), nome: await caixa('#rNome'), cpf: await caixa('#rCpf'),
      nasc: await caixa('#rNasc'), crm: await caixa('#rCrm'), uf: await caixa('#rUf'), btn: await caixa('#regGo'), legal: await caixa('.legal') };
    g.legal.y += await ev(`parseFloat(getComputedStyle(document.querySelector('.legal')).paddingTop)`);   // o texto, sem o respiro de cima
    const quer = { back: { x: 803, y: 60, w: 19, h: 18 }, title: { x: 803, y: 155, h: 32 }, nome: { x: 803, y: 243, w: 447, h: 84 },
      cpf: { x: 803, y: 335, w: 219.5, h: 84 }, nasc: { x: 1030.5, y: 335, w: 219.5, h: 84 }, crm: { x: 803, y: 427, w: 219.5, h: 84 },
      uf: { x: 1030.5, y: 427, w: 219.5, h: 84 }, btn: { x: 803, y: 527, w: 447, h: 84 }, legal: { x: 803, y: 688 } };
    const fora = [];
    for (const [k, q] of Object.entries(quer)) for (const [d, v] of Object.entries(q)) if (Math.abs(g[k][d] - v) > 0.6) fora.push(`${k}.${d}=${g[k][d]} (Figma ${v})`);
    certo(!fora.length, 'posições: ' + fora.join(', '));
    const cor = await ev(`getComputedStyle(document.getElementById('regGo')).backgroundColor`);
    certo(cor === 'rgb(16, 19, 44)', 'cor do botão: ' + cor);
    const fonte = await ev(`(() => { const s = getComputedStyle(document.getElementById('title')); return s.fontSize + ' ' + s.fontWeight + ' ' + s.color; })()`);
    certo(fonte === '24px 500 rgb(12, 12, 13)', 'título: ' + fonte);
    certo(await ev(`document.fonts.check('500 24px "Helvetica Now Display"')`), 'fonte Helvetica Now Display não carregou');
    const rot = () => ev(`(() => { const s = getComputedStyle(document.querySelector('label[for=rCpf]')); return s.color + ' ' + s.fontSize; })()`);
    certo(await rot() === 'rgb(0, 0, 0) 14px', 'rótulo vazio: ' + await rot());           // Figma: rótulo preto 14px
    await ev(`document.getElementById('rCpf').focus(); 1`); await sleep(250);
    certo(await rot() === 'rgb(125, 125, 130) 12px', 'rótulo digitando: ' + await rot());  // o rótulo flutuante de sempre
    await ev(`document.activeElement.blur(); 1`); await sleep(250);
    if (process.env.SHOT) {
      const r = await send('Page.captureScreenshot', { format: 'png' });
      writeFileSync(join(process.env.SHOT, 'registro-1440x780.png'), Buffer.from(r.data, 'base64'));
    }
    await send('Emulation.clearDeviceMetricsOverride');
    return 'seta 803,60; título y=155; campos 243/335/427; botão 527 #10132C; texto legal y=688';
  }],
  ['máscaras e o CRM com a UF', async () => {
    await ateRegistro();
    certo(await digita('#rCpf', '529a98224725999') === '529.982.247-25', 'CPF: ' + await val('#rCpf'));
    certo(await digita('#rNasc', '12051985') === '12/05/1985', 'nascimento: ' + await val('#rNasc'));
    certo(await cola('#rNasc', '1985-05-12') === '12/05/1985', 'nascimento ISO: ' + await val('#rNasc'));
    certo(await digita('#rCrm', '123456789') === '1234567', 'CRM até 7: ' + await val('#rCrm'));
    const casos = [['CRM-SP 123456', '123456', 'SP'], ['CRM/SP 123.456', '123456', 'SP'], ['SP 123456', '123456', 'SP'],
      ['123456/SP', '123456', 'SP'], ['123456-SP', '123456', 'SP'], ['52-1234/RJ', '1234', 'RJ'], ['1234567-P/SP', '1234567', 'SP'],
      ['crm-mg 4321', '4321', 'MG']];
    for (const [colado, crm, uf] of casos) {
      await ev(`document.getElementById('rUf').value = ''; 1`);
      await cola('#rCrm', colado);
      certo(await val('#rCrm') === crm && await val('#rUf') === uf, `${colado} → ${await val('#rCrm')} / ${await val('#rUf')}`);
    }
    for (const [digitado, crm, uf] of [['123456/SP', '123456', 'SP'], ['1234567-P/SP', '1234567', 'SP']]) {   // um caractere por vez
      await ev(`document.getElementById('rUf').value = ''; 1`);
      await digita('#rCrm', digitado);
      certo(await val('#rCrm') === crm && await val('#rUf') === uf, `digitado ${digitado} → ${await val('#rCrm')} / ${await val('#rUf')}`);
    }
    await ev(`document.getElementById('rUf').value = ''; 1`);
    await digita('#rCrm', '52-1234'); await sai('#rCrm');
    certo(await val('#rCrm') === '52-1234', 'sem UF, o 52- ficou esperando: ' + await val('#rCrm'));
    await digita('#rUf', 'rj');
    certo(await val('#rUf') === 'RJ' && await val('#rCrm') === '1234', `52-1234 + RJ → ${await val('#rCrm')} / ${await val('#rUf')}`);
    await digita('#rCrm', 'CRM 98765'); await sai('#rCrm');
    certo(await val('#rCrm') === '98765', 'ao sair do campo fica só o número: ' + await val('#rCrm'));
    certo(await digita('#rUf', 's1p2') === 'SP', 'UF: ' + await val('#rUf'));
    return 'CPF, nascimento, CRM e UF com máscara; 8 formatos de CRM com a UF separados';
  }],
  ['erros nos campos e a seta volta para a senha', async () => {
    await ateRegistro();
    const n0 = posts('/auth/signup/start').length;
    await clica('#regGo');
    const vazios = await ev(`['rNomeErr', 'rCpfErr', 'rNascErr', 'rCrmErr', 'rUfErr'].filter((i) => !document.getElementById(i).hidden).length`);
    certo(vazios === 5, 'erros com tudo vazio: ' + vazios);
    await digita('#rNome', 'Ana'); await digita('#rCpf', '52998224724'); await digita('#rNasc', '31021990');
    await digita('#rCrm', '123456'); await digita('#rUf', 'XX');
    await clica('#regGo');
    certo(await txt('#rNomeErr') === 'Digite seu nome completo, com sobrenome.', 'nome: ' + await txt('#rNomeErr'));
    certo(await txt('#rCpfErr') === 'Confira o CPF.' && await txt('#rNascErr') === 'Confira a data de nascimento.', 'CPF/nascimento');
    certo(await txt('#rUfErr') === 'Confira a UF.' && !(await vis('#rCrmErr')), 'UF/CRM');
    certo(await ev(`document.querySelector('#rCpf').closest('.fl').classList.contains('bad')`), 'campo com erro sem a borda vermelha');
    certo(posts('/auth/signup/start').length === n0, 'foi ao servidor com erro');
    if (process.env.SHOT) {
      await ev(`document.activeElement.blur(); 1`); await sleep(200);
      const r = await send('Page.captureScreenshot', { format: 'png' });
      writeFileSync(join(process.env.SHOT, 'registro-erros.png'), Buffer.from(r.data, 'base64'));
    }
    await clica('#back');
    await ate(`!document.getElementById('signupForm').hidden`, 2000, 'voltou para a senha');
    certo(await val('#newPw') === 'Abcdef12!' && await titulo() === 'Crie sua conta', 'a senha se perdeu');
    certo(!(await vis('#back')) && await vis('.logo'), 'a seta ficou fora do Registro');
    await clica('#signupGo');
    await ate(`!document.getElementById('regForm').hidden`, 2000, 'de novo no Registro');
    certo(await val('#rCrm') === '123456', 'os campos se perderam');
    return 'os 5 campos com erro; nada vai ao servidor; a seta volta com a senha guardada';
  }],
  ['Criar conta: um POST só, código e a espera da conferência', async () => {
    await ateRegistro();
    await preenche();
    await clica('#regGo');
    await ate(`!document.getElementById('codeForm').hidden`, 3000, 'etapa do código');
    const st = posts('/auth/signup/start');
    certo(st.length === 1, 'POSTs: ' + st.length);
    const b = st[0].body;
    certo(b.email === 'nova@clinica.com.br' && b.password === 'Abcdef12!' && b.nome === 'Ana Maria Lima' && b.cpf === CPF &&
          b.nascimento === '12/05/1985' && b.crm === '123456' && b.uf === 'SP' && !('especialidade' in b) && !('name' in b), 'corpo: ' + JSON.stringify(b));
    await cola('#otp input', '123456');
    await ate(`document.getElementById('title').textContent === 'Estamos conferindo seu CRM'`, 3000, 'espera: ' + await titulo());
    certo(await vis('#sub') && (await txt('#sub')).includes('CFM'), 'texto da espera: ' + await txt('#sub'));
    certo(await ev(`location.pathname`) === '/opendoctor-login.html', 'foi para o app pendente');
    certo(await vis('[data-step="aguardando"] a[href="/auth/logout"]'), 'sem o Sair');
    if (process.env.SHOT) {
      const r = await send('Page.captureScreenshot', { format: 'png' });
      writeFileSync(join(process.env.SHOT, 'aguardando-1440x780.png'), Buffer.from(r.data, 'base64'));
    }
    return 'signup/start com os 7 campos; código; "Estamos conferindo seu CRM" sem abrir o app';
  }],
  ['recusas do CFM no campo certo', async () => {
    const esperado = [[{ error: 'crm_nao_encontrado' }, '#rCrmErr', 'Não encontramos este CRM no CFM. Confira o número e a UF.'],
      [{ error: 'crm_nome' }, '#rNomeErr', 'O nome não confere com o do CRM. Digite como está no seu registro.'],
      [{ error: 'crm_dados' }, '#alertText', 'O CPF ou a data de nascimento não conferem com o registro deste CRM no CFM.'],
      [{ error: 'crm_irregular' }, '#alertText', 'O CFM não mostra este CRM como regular. O OpenDoctor é só para médicos com inscrição regular.']];
    await ateRegistro();
    await preenche();
    for (const [resp, onde, msg] of esperado) {
      START = [400, resp];
      await clica('#regGo');
      await ate(`(document.querySelector(${JSON.stringify(onde)}).textContent || '') === ${JSON.stringify(msg)}`, 3000, resp.error + ': ' + await txt(onde));
      certo(await vis('#regForm'), 'saiu do Registro');
    }
    START = null;
    return '4 recusas: CRM, nome, CPF/nascimento e situação irregular';
  }],
  ['Google com conta nova cai direto no Registro e cria a conta', async () => {
    await abre('?registro=google');
    await ate(`!document.getElementById('regForm').hidden`, 3000, 'Registro do Google');
    certo(await ev(`location.search`) === '', 'parâmetro ficou na URL: ' + await ev(`location.search`));
    await preenche();
    await clica('#regGo');
    await ate(`location.pathname === '/opendoctor-agenda.html'`, 4000, 'abriu o app');
    const g = posts('/auth/google/registro');
    certo(g.length === 1 && !('email' in g[0].body) && !('password' in g[0].body) && g[0].body.cpf === CPF, 'corpo: ' + JSON.stringify(g[0] && g[0].body));
    await abre('?registro=google');
    await ate(`!document.getElementById('regForm').hidden`, 3000, 'Registro do Google');
    await clica('#back');
    await ate(`!document.getElementById('emailForm').closest('[data-step]').hidden`, 2000, 'a seta voltou para o início');
    return 'registro=google abre o Registro; POST sem e-mail/senha; vai para o app';
  }],
  ['conta recusada e conta a confirmar no CFM', async () => {
    ME = { logged_in: true, user: { id: 'u1' }, scribe: false, bloqueio: 'crm_recusado' };
    await abre();
    await ate(`document.getElementById('title').textContent === 'Não foi possível liberar sua conta'`, 3000, 'recusada: ' + await titulo());
    certo(await ev(`location.pathname`) === '/opendoctor-login.html', 'recusada foi para o app');
    ME = { logged_in: true, user: { id: 'u1' }, scribe: false, bloqueio: 'crm_confirmar' };
    await abre();
    await ate(`document.getElementById('title').textContent === 'Confirme seu registro'`, 3000, 'confirmar: ' + await titulo());
    await digita('#cCpf', CPF); await digita('#cNasc', '12051985');
    await clica('#confGo');
    await ate(`location.pathname === '/opendoctor-agenda.html'`, 4000, 'abriu o app depois de confirmar');
    const c = posts('/auth/crm/confirmar');
    certo(c.length === 1 && c[0].body.cpf === CPF && c[0].body.nascimento === '12/05/1985', 'corpo: ' + JSON.stringify(c[0] && c[0].body));
    ME = { logged_in: false, user: null, scribe: false, bloqueio: null };
    return 'recusada vê a mensagem; a confirmar manda CPF e nascimento e abre o app';
  }],
  ['página de cadastros: lista, aprova e recusa', async () => {
    await send('Page.navigate', { url: ORIG + '/opendoctor-cadastros.html' });
    await ate(`document.querySelectorAll('.card').length === 2`, 5000, 'lista de pendentes');
    const linhas = await ev(`[...document.querySelectorAll('.card .meta')].map((e) => e.textContent.split(' · ')[0])`);
    certo(linhas.join('|') === 'CRM 123456/SP|CRM 4321/RJ', 'linhas: ' + linhas.join('|'));
    certo((await txt('.card:nth-child(2) .warn')).includes('outra conta'), 'sem o alerta de CRM repetido');
    certo(await ev(`document.querySelector('.sub a').href`) === 'https://portal.cfm.org.br/busca-medicos/', 'link do CFM');
    await clica('.card .btn-dark');
    await ate(`document.querySelectorAll('.card').length === 1`, 3000, 'aprovado saiu da lista');
    const ap = posts('/admin/cadastros/aprovar');
    certo(ap.length === 1 && ap[0].body.id === '8f14e45f-ceea-467a-9575-1a2b3c4d5e6f', 'aprovar: ' + JSON.stringify(ap.map((x) => x.body)));
    DIALOGOS = 1;
    await clica('.card .btn-line');
    await ate(`document.querySelectorAll('.card').length === 0`, 3000, 'recusado saiu da lista');
    certo(posts('/admin/cadastros/recusar').length === 1 && DIALOGOS === 0, 'recusar sem confirmar');
    certo((await txt('#msg')).includes('Nenhum outro cadastro esperando'), 'mensagem: ' + await txt('#msg'));
    return 'aprovou Ana (POST com o id), recusou Bia depois do confirm; lista vazia';
  }],
  ['CPF e nascimento nunca em URL', async () => {
    const ruins = pedidos.filter((r) => r.url.includes(CPF) || r.url.includes('529.982') || r.url.includes('1985'));
    certo(!ruins.length, 'na URL: ' + ruins.map((r) => r.url).join(' '));
    return `${pedidos.length} pedidos conferidos`;
  }],
];

async function main() {
  for (let i = 0; i < 50; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch (_) {} await sleep(200); }
  await new Promise((ok) => ws.addEventListener('open', ok));
  ws.addEventListener('message', (m) => {
    const j = JSON.parse(m.data);
    if (j.id && espera.has(j.id)) { const w = espera.get(j.id); espera.delete(j.id); j.error ? w.no(new Error(j.error.message)) : w.ok(j.result); return; }
    if (j.method === 'Fetch.requestPaused') responde(j.params).catch((e) => erros.push('interceptação: ' + e.message));
    if (j.method === 'Page.javascriptDialogOpening') {
      if (DIALOGOS > 0) DIALOGOS--; else erros.push('diálogo: ' + j.params.message);
      send('Page.handleJavaScriptDialog', { accept: true });
    }
    if (j.method === 'Runtime.exceptionThrown') erros.push(j.params.exceptionDetails.exception?.description || j.params.exceptionDetails.text);
  });
  await send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] });
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setFocusEmulationEnabled', { enabled: true });
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
