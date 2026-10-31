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
// espera confere o /me a cada 30 s com a aba à vista (relógio curto no teste) e abre o app quando liberada; o aviso do
// Google com e-mail não verificado; o nascimento sem preenchimento automático; a página de cadastros dos administradores
// lista (com o e-mail), aprova e recusa (com confirmação) e libera sem confirmar as aprovadas à mão presas no CFM.
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
let PENDENTES = [{ id: '8f14e45f-ceea-467a-9575-1a2b3c4d5e6f', name: 'Ana Lima', email: 'ana@clinica.com.br', crm: '123456', crm_uf: 'SP', pedido_em: '2026-10-30T12:00:00+00:00', outras_contas: 0 },
  { id: '9a14e45f-ceea-467a-9575-1a2b3c4d5e70', name: 'Bia Souza', email: '<img src=x>bia@clinica.com.br', crm: '4321', crm_uf: 'RJ', pedido_em: '2026-10-30T13:00:00+00:00', outras_contas: 1 }];
// aprovadas à mão sem a confirmação no CFM (a 2ª com o limite de confirmações do dia esgotado)
let MANUAIS = [{ id: '7b14e45f-ceea-467a-9575-1a2b3c4d5e71', name: 'Caio Rocha', email: 'caio@clinica.com.br', crm: '777', crm_uf: 'MG', aprovado_em: '2026-10-29T12:00:00+00:00', falhas: 0 },
  { id: '6c14e45f-ceea-467a-9575-1a2b3c4d5e72', name: 'Dora Reis', email: 'dora@clinica.com.br', crm: '888', crm_uf: 'BA', aprovado_em: '2026-10-29T13:00:00+00:00', falhas: 5 }];
let DISPENSA = true;              // a migração 0019 já está no banco
let DIALOGOS = 0;                 // confirm() aceitos na página de cadastros (fora dela, diálogo é erro)
let RECUSAS = 0;                  // confirm() respondidos com "Cancelar"
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
  if (path === '/admin/cadastros') return [200, { pendentes: PENDENTES, manuais: MANUAIS, dispensa: DISPENSA, cfm: true, limite_falhas: 5 }];
  if (path === '/admin/cadastros/liberar') {
    if (!DISPENSA) return [503, { error: 'migracao_pendente' }];
    const antes = MANUAIS.length; MANUAIS = MANUAIS.filter((p) => p.id !== body.id);
    return MANUAIS.length < antes ? [200, { ok: true }] : [409, { error: 'nao_manual' }];
  }
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
// teclado de verdade (DevTools): teclas especiais e texto digitado no campo com o foco
const TECLAS = { Enter: [13, '\r'], Backspace: [8, ''], Delete: [46, ''] };
async function tecla(key) {
  const [vk, text] = TECLAS[key];
  await send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key, code: key, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
  if (text) await send('Input.dispatchKeyEvent', { type: 'char', key, code: key, text, unmodifiedText: text, windowsVirtualKeyCode: vk });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key, code: key, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
  await sleep(30);
}
async function escreve(t) { for (const ch of t) { await send('Input.insertText', { text: ch }); await sleep(5); } }
const foca = (s, pos) => ev(`(() => { const i = document.querySelector(${JSON.stringify(s)}); i.focus();
  ${pos == null ? '' : `i.setSelectionRange(${pos}, ${pos});`} return 1; })()`);
const cursor = (s) => ev(`document.querySelector(${JSON.stringify(s)}).selectionStart`);
const focado = () => ev(`document.activeElement && document.activeElement.id`);
const errosVisiveis = () => ev(`[...document.querySelectorAll('#regForm .err')].filter((e) => !e.hidden).map((e) => e.id)`);
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
    // mais de 7 dígitos: nada é cortado sem aviso (zeros à esquerda não contam, como no servidor)
    certo(await digita('#rCrm', '123456789') === '123456789' && await txt('#rCrmErr') === 'Confira o CRM.', 'CRM com 9 dígitos: ' + await val('#rCrm') + ' / ' + await txt('#rCrmErr'));
    certo(await cola('#rCrm', '00123456') === '123456' && !(await vis('#rCrmErr')), 'CRM com zeros à esquerda: ' + await val('#rCrm'));
    certo(await digita('#rCrm', '0001234') === '0001234', 'CRM de 7 com zeros: ' + await val('#rCrm'));
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
    certo(await txt('#rCpfErr') === 'Confira o CPF.' && await txt('#rNascErr') === 'Confira a data.', 'CPF/nascimento');
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
    const esperado = [[{ error: 'crm_nao_encontrado' }, '#rCrmUfErr', 'Não achamos este CRM no CFM. Confira o número e a UF.'],
      [{ error: 'crm_nome' }, '#rNomeErr', 'O nome não confere com o do CFM. Digite como no registro.'],
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
    certo(await ev(`location.search`) === '?registro=google', 'o registro=google saiu da URL: ' + await ev(`location.search`));
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
    await ate(`document.querySelectorAll('#list .card').length === 2`, 5000, 'lista de pendentes');
    const linhas = await ev(`[...document.querySelectorAll('#list .card .meta:not(.email)')].map((e) => e.textContent.split(' · ')[0])`);
    certo(linhas.join('|') === 'CRM 123456/SP|CRM 4321/RJ', 'linhas: ' + linhas.join('|'));
    const emails = await ev(`[...document.querySelectorAll('#list .card .email')].map((e) => e.textContent)`);
    certo(emails.join('|') === 'ana@clinica.com.br|<img src=x>bia@clinica.com.br', 'e-mails: ' + emails.join('|'));
    certo(await ev(`document.querySelectorAll('.card img').length`) === 0, 'o e-mail virou HTML');          // texto, nunca HTML
    certo((await txt('#list .card:nth-child(2) .warn')).includes('outra conta'), 'sem o alerta de CRM repetido');
    certo(await ev(`document.querySelector('.sub a').href`) === 'https://portal.cfm.org.br/busca-medicos/', 'link do CFM');
    await clica('#list .card .btn-dark');
    await ate(`document.querySelectorAll('#list .card').length === 1`, 3000, 'aprovado saiu da lista');
    const ap = posts('/admin/cadastros/aprovar');
    certo(ap.length === 1 && ap[0].body.id === '8f14e45f-ceea-467a-9575-1a2b3c4d5e6f', 'aprovar: ' + JSON.stringify(ap.map((x) => x.body)));
    DIALOGOS = 1;
    await clica('#list .card .btn-line');
    await ate(`document.querySelectorAll('#list .card').length === 0`, 3000, 'recusado saiu da lista');
    certo(posts('/admin/cadastros/recusar').length === 1 && DIALOGOS === 0, 'recusar sem confirmar');
    certo((await txt('#msg')).includes('Nenhum outro cadastro esperando'), 'mensagem: ' + await txt('#msg'));
    certo(await ev(`document.querySelectorAll('#manuais .card').length`) === 2, 'as aprovadas à mão sumiram junto');
    return 'aprovou Ana (POST com o id), recusou Bia depois do confirm; e-mails como texto; lista vazia';
  }],
  ['página de cadastros: aprovados à mão sem confirmação no CFM e "Liberar sem confirmar"', async () => {
    await send('Page.navigate', { url: ORIG + '/opendoctor-cadastros.html' });
    await ate(`document.querySelectorAll('#manuais .card').length === 2`, 5000, 'lista dos aprovados à mão');
    certo(await txt('#manuaisSec h2') === 'Aprovados à mão, sem confirmação no CFM', 'título: ' + await txt('#manuaisSec h2'));
    const m = await ev(`[...document.querySelectorAll('#manuais .card')].map((c) => [...c.querySelectorAll('.nome, .meta, .warn')].map((e) => e.textContent).join(' / '))`);
    certo(m[0].startsWith('Caio Rocha / caio@clinica.com.br / CRM 777/MG · aprovado em ') && !m[0].includes('confirma'), 'Caio: ' + m[0]);
    certo(m[1].includes('dora@clinica.com.br') && m[1].includes('5 confirmações não bateram no CFM nas últimas 24 h: chegou ao limite do dia.'), 'Dora: ' + m[1]);
    certo(!(await vis('#semChave')), 'aviso de "sem chave" com a chave configurada');
    const n0 = posts('/admin/cadastros/liberar').length;
    RECUSAS = 1;
    await clica('#manuais .card:nth-child(2) .btn-line');                 // confirm() com "Cancelar": nada vai ao servidor
    await sleep(300);
    certo(RECUSAS === 0 && posts('/admin/cadastros/liberar').length === n0, 'liberou sem o confirm');
    DIALOGOS = 1;
    await clica('#manuais .card:nth-child(2) .btn-line');
    await ate(`document.querySelectorAll('#manuais .card').length === 1`, 3000, 'liberada saiu da lista');
    const lb = posts('/admin/cadastros/liberar');
    certo(lb.length === n0 + 1 && lb[lb.length - 1].body.id === '6c14e45f-ceea-467a-9575-1a2b3c4d5e72' && DIALOGOS === 0, 'liberar: ' + JSON.stringify(lb.map((x) => x.body)));
    certo((await txt('#msg2')).startsWith('Liberado.'), 'mensagem: ' + await txt('#msg2'));
    // sem a migração 0019: os botões ficam desligados e a página diz o que falta
    DISPENSA = false;
    await send('Page.navigate', { url: ORIG + '/opendoctor-cadastros.html' });
    await ate(`document.querySelectorAll('#manuais .card').length === 1`, 5000, 'lista sem a 0019');
    certo(await ev(`document.querySelector('#manuais .btn-line').disabled`), 'botão ligado sem a migração');
    certo((await txt('#msg2')).includes('migração 0019'), 'sem o aviso da migração: ' + await txt('#msg2'));
    DISPENSA = true;
    return 'nome, e-mail, CRM/UF, aprovação e falhas; confirm antes de liberar; sem a 0019 o botão fica desligado';
  }],
  ['o erro de um envio anterior não fica na tela junto com o novo', async () => {
    await ateRegistro();
    await preenche();
    START = [400, { error: 'crm_nao_encontrado' }];
    await clica('#regGo');
    await ate(`!document.getElementById('rCrmUfErr').hidden`, 3000, 'erro do CRM/UF');
    const borda = () => ev(`['rCrm', 'rUf'].map((i) => document.getElementById(i).closest('.fl').classList.contains('bad')).join()`);
    certo(await borda() === 'true,true', 'CRM e UF sem a borda vermelha: ' + await borda());
    await digita('#rUf', 'RJ');                                              // a mensagem fala da UF também
    certo(!(await vis('#rCrmUfErr')) && await borda() === 'false,false', 'trocar a UF não limpou o erro do CRM');
    START = [400, { error: 'crm_nome' }];
    await clica('#regGo');
    await ate(`!document.getElementById('rNomeErr').hidden`, 3000, 'erro do nome');
    certo((await errosVisiveis()).join() === 'rNomeErr', 'erros juntos: ' + (await errosVisiveis()).join());
    START = [400, { error: 'crm_dados' }];
    await clica('#regGo');                                                   // corrigiu o nome? o erro dele some no envio
    await ate(`!document.getElementById('alert').hidden`, 3000, 'alerta de CPF/nascimento');
    certo((await errosVisiveis()).length === 0, 'erro velho ficou: ' + (await errosVisiveis()).join());
    START = [400, { error: 'crm_nao_encontrado' }];
    await clica('#regGo');
    await ate(`!document.getElementById('rCrmUfErr').hidden`, 3000, 'erro do CRM/UF de novo');
    await digita('#rCrm', '654321');
    certo(!(await vis('#rCrmUfErr')), 'editar o CRM não limpou o erro');
    START = null;
    return 'cada envio limpa os erros do anterior; mexer no CRM ou na UF tira o "não achamos"';
  }],
  ['Enter passa para o campo seguinte; só o da UF envia', async () => {
    await ateRegistro();
    const n0 = posts('/auth/signup/start').length;
    await foca('#rNome'); await escreve('Ana Maria Lima');
    await tecla('Enter');
    certo(await focado() === 'rCpf' && !(await errosVisiveis()).length, `Enter no Nome: foco ${await focado()}, erros ${await errosVisiveis()}`);
    await escreve(CPF); await tecla('Enter');
    certo(await focado() === 'rNasc', 'Enter no CPF: ' + await focado());
    await escreve('12051985'); await tecla('Enter');
    certo(await focado() === 'rCrm', 'Enter no nascimento: ' + await focado());
    await escreve('123456/SP'); await tecla('Enter');
    certo(await focado() === 'rUf' && await val('#rUf') === 'SP' && await val('#rCrm') === '123456', 'Enter no CRM: ' + await focado());
    certo(posts('/auth/signup/start').length === n0 && !(await errosVisiveis()).length, 'enviou ou validou antes da UF');
    await tecla('Enter');
    await ate(`!document.getElementById('codeForm').hidden`, 3000, 'Enter na UF envia');
    certo(posts('/auth/signup/start').length === n0 + 1, 'Enter na UF não enviou');
    return 'Nome → CPF → Nascimento → CRM → UF com Enter, sem erros; Enter na UF manda o cadastro';
  }],
  ['máscaras com o cursor no lugar, data com 1 dígito e CRM sem espaço', async () => {
    await ateRegistro();
    await cola('#rCpf', '52998224725');
    await foca('#rCpf', 5); await tecla('Backspace');                 // apaga o 9 depois do ponto
    certo(await val('#rCpf') === '529.822.472-5' && await cursor('#rCpf') === 3, `meio do CPF: ${await val('#rCpf')} cursor ${await cursor('#rCpf')}`);
    await cola('#rCpf', '52998224725');
    await foca('#rCpf', 4); await tecla('Backspace');                 // logo depois do ponto: apaga o dígito antes dele
    certo(await val('#rCpf') === '529.822.472-5' && await cursor('#rCpf') === 2, `depois do ponto: ${await val('#rCpf')} cursor ${await cursor('#rCpf')}`);
    await foca('#rCpf', 3); await escreve('9');                        // digitar no meio também não pula para o fim
    certo(await val('#rCpf') === '529.982.247-25' && await cursor('#rCpf') === 5, `digitou no meio: ${await val('#rCpf')} cursor ${await cursor('#rCpf')}`);
    await ev(`document.getElementById('rNasc').value = ''; 1`);
    await foca('#rNasc'); await escreve('1/5/1985');
    certo(await val('#rNasc') === '01/05/1985', 'data com 1 dígito: ' + await val('#rNasc'));
    await ev(`document.getElementById('rNasc').value = ''; 1`);
    await foca('#rNasc'); await escreve('12/11/1985');
    certo(await val('#rNasc') === '12/11/1985', 'data com 2 dígitos e barras: ' + await val('#rNasc'));
    certo(await cola('#rNasc', '3/9/1980') === '03/09/1980', 'data colada com 1 dígito: ' + await val('#rNasc'));
    await ev(`document.getElementById('rCrm').value = ''; document.getElementById('rUf').value = ''; 1`);
    await foca('#rCrm');
    const vistos = [];
    for (const ch of 'CRM-SP 123456') { await escreve(ch); vistos.push(await val('#rCrm')); }
    certo(vistos.every((v) => v === v.trim()), 'espaço na ponta do CRM: ' + JSON.stringify(vistos));
    certo(await val('#rCrm') === '123456' && await val('#rUf') === 'SP', `CRM-SP 123456 → ${await val('#rCrm')} / ${await val('#rUf')}`);
    return 'Backspace no meio e depois do ponto; 1/5/1985 → 01/05/1985; CRM digitado sem espaço na ponta';
  }],
  ['nome colado com o acento separado e com apóstrofo', async () => {
    await ateRegistro();
    await preenche();
    await cola('#rNome', 'José Conceição D’Ávila Jr.');      // NFD, como no PDF/macOS
    await clica('#regGo');
    await ate(`!document.getElementById('codeForm').hidden`, 3000, 'nome NFD recusado: ' + await txt('#rNomeErr'));
    const b = posts('/auth/signup/start').slice(-1)[0].body;
    certo(b.nome === 'José Conceição D’Ávila Jr.' && b.nome === b.nome.normalize('NFC'), 'nome no POST: ' + JSON.stringify(b.nome));
    return 'nome em NFD aceito e enviado em NFC';
  }],
  ['depois de criar a conta, o Voltar não reabre o Registro nem mostra o CPF', async () => {
    await ateRegistro();
    await preenche();
    await clica('#regGo');
    await ate(`!document.getElementById('codeForm').hidden`, 3000, 'etapa do código');
    await cola('#otp input', '123456');
    await ate(`document.getElementById('title').textContent === 'Estamos conferindo seu CRM'`, 3000, 'espera');
    for (let i = 0; i < 3; i++) {
      await ev(`history.back(); 1`); await sleep(300);
      certo(await titulo() === 'Estamos conferindo seu CRM', `Voltar ${i + 1}: ${await titulo()}`);
    }
    const vazios = await ev(`['rCpf', 'rNasc', 'newPw'].map((i) => document.getElementById(i).value).join('|')`);
    certo(vazios === '||', 'CPF/nascimento/senha ficaram na página: ' + vazios);
    return 'Voltar 3× continua na espera; CPF, nascimento e senha limpos';
  }],
  ['Google: recarregar e voltar não perdem a etapa nem a página de origem', async () => {
    await abre('?registro=google&next=%2Fopendoctor-configuracoes.html');
    await ate(`!document.getElementById('regForm').hidden`, 3000, 'Registro do Google');
    await send('Page.reload');
    await ate(`document.readyState === 'complete' && !document.getElementById('regForm').hidden`, 5000, 'recarregou e perdeu o Registro: ' + await titulo());
    certo(await titulo() === 'Registro profissional', 'título depois de recarregar: ' + await titulo());
    certo((await ev(`document.getElementById('google').getAttribute('href')`)).includes('next=%2Fopendoctor-configuracoes.html'), 'o botão do Google perdeu o next');
    await clica('#back');
    await ate(`!document.getElementById('emailForm').closest('[data-step]').hidden`, 2000, 'a seta voltou para o início');
    certo(await ev(`location.search`) === '?next=%2Fopendoctor-configuracoes.html', 'URL depois da seta: ' + await ev(`location.search`));
    certo((await ev(`document.getElementById('google').getAttribute('href')`)).includes('next=%2Fopendoctor-configuracoes.html'), 'o next se perdeu na seta');
    REG_GOOGLE = [200, { ok: true, redirect: '/opendoctor-agenda.html?bemvindo=1', bloqueio: 'crm_pendente' }];
    await abre('?registro=google');
    await ate(`!document.getElementById('regForm').hidden`, 3000, 'Registro do Google');
    await preenche(); await clica('#regGo');
    await ate(`document.getElementById('title').textContent === 'Estamos conferindo seu CRM'`, 3000, 'espera do Google');
    certo(await ev(`location.search`) === '', 'conta criada e o registro=google ficou na URL: ' + await ev(`location.search`));
    REG_GOOGLE = null;
    return 'registro=google e next ficam até a conta existir; recarregar mantém o Registro; a seta tira só o registro';
  }],
  ['mensagens das meias colunas numa linha só; o "não achamos" embaixo de CRM e UF', async () => {
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 780, deviceScaleFactor: 1, mobile: false });
    await ateRegistro();
    await clica('#regGo');
    const alturas = await ev(`['rNomeErr', 'rCpfErr', 'rNascErr', 'rCrmErr', 'rUfErr'].map((i) => Math.round(document.getElementById(i).getBoundingClientRect().height))`);
    certo(alturas.every((h) => h > 0 && h <= 20), 'erros com mais de uma linha: ' + alturas.join(','));
    const linhas = await ev(`(() => { const y = (i) => document.getElementById(i).getBoundingClientRect().top;
      return [y('rCpfErr') === y('rNascErr'), y('rCrmErr') === y('rUfErr')]; })()`);
    certo(linhas.join() === 'true,true', 'erros da mesma linha em alturas diferentes');
    if (process.env.SHOT) {
      await ev(`document.activeElement.blur(); 1`); await sleep(200);
      const r = await send('Page.captureScreenshot', { format: 'png' });
      writeFileSync(join(process.env.SHOT, 'registro-todos-erros.png'), Buffer.from(r.data, 'base64'));
    }
    await preenche();
    START = [400, { error: 'crm_nao_encontrado' }];
    await clica('#regGo');
    await ate(`!document.getElementById('rCrmUfErr').hidden`, 3000, 'erro do CRM/UF');
    const e = await caixa('#rCrmUfErr'), f = await caixa('#rCrm');
    certo(e.h <= 20 && e.w === 447 && e.x === 803 && e.y > f.y + f.h, 'o "não achamos" fora do lugar: ' + JSON.stringify(e));
    START = [400, { error: 'crm_nome' }];
    await clica('#regGo');
    await ate(`!document.getElementById('rNomeErr').hidden`, 3000, 'erro do nome');
    certo((await caixa('#rNomeErr')).h <= 20, 'o erro do nome quebrou a linha');
    START = null;
    await send('Emulation.clearDeviceMetricsOverride');
    return `5 erros com ${alturas.join('/')} px; "não achamos" numa linha de 447 px embaixo de CRM | UF`;
  }],
  ['as outras etapas continuam com o visual novo (logo 34 px, "Bem-vindo à", botão #10132C)', async () => {
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 780, deviceScaleFactor: 1, mobile: false });
    await abre();
    const logo = await ev(`(() => { const l = document.querySelector('.logo'); const r = l.getBoundingClientRect();
      return { src: l.getAttribute('src'), w: r.width, y: r.top }; })()`);
    certo(logo.src === 'assets/login/logo-simbolo.svg' && logo.w === 34 && logo.y === 60, 'logo: ' + JSON.stringify(logo));
    certo(await titulo() === 'Bem-vindo à OpenDoctor' && (await caixa('#title')).y === 171, 'título: ' + await titulo() + ' ' + JSON.stringify(await caixa('#title')));
    certo(await ev(`getComputedStyle(document.getElementById('go')).backgroundColor`) === 'rgb(16, 19, 44)', 'botão do e-mail');
    certo(!(await ev(`[...document.styleSheets].some((s) => [...s.cssRules].some((r) => /btn-reg/.test(r.cssText)))`)), '.btn-reg ainda existe');
    ME = { logged_in: true, user: { id: 'u1' }, scribe: false, bloqueio: 'crm_confirmar' };
    await abre();
    await ate(`!document.getElementById('confForm').hidden`, 3000, 'confirmar');
    const cor = await ev(`getComputedStyle(document.getElementById('confGo')).backgroundColor`);
    ME = { logged_in: false, user: null, scribe: false, bloqueio: null };
    certo(cor === 'rgb(16, 19, 44)', 'botão da confirmação: ' + cor);
    await send('Emulation.clearDeviceMetricsOverride');
    return 'logo-simbolo 34 px em y=60; título y=171; botões #10132C; sem .btn-reg';
  }],
  ['a espera confere o /me a cada 30 s com a aba à vista e abre o app quando liberada', async () => {
    // relógio do teste: o intervalo da página (OD_ESPERA_MS, 30 s de verdade) vira 250 ms; a aba "escondida" é simulada
    const { identifier } = await send('Page.addScriptToEvaluateOnNewDocument', { source: `window.OD_ESPERA_MS = 250;
      (() => { let h = false;
        Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => (h ? 'hidden' : 'visible') });
        Object.defineProperty(document, 'hidden', { configurable: true, get: () => h });
        window.__aba = (esc) => { h = esc; document.dispatchEvent(new Event('visibilitychange')); }; })();` });
    const mes = () => pedidos.filter((r) => r.method === 'GET' && r.path === '/me').length;
    try {
      // cadastro novo pendente: o destino do login (bemvindo=1) fica guardado para quando liberar
      await ateRegistro();
      await preenche();
      await clica('#regGo');
      await ate(`!document.getElementById('codeForm').hidden`, 3000, 'etapa do código');
      ME = { logged_in: true, user: { id: 'u1' }, scribe: false, bloqueio: 'crm_pendente' };
      await cola('#otp input', '123456');
      await ate(`document.getElementById('title').textContent === 'Estamos conferindo seu CRM'`, 3000, 'espera');
      const m0 = mes();
      await sleep(1100);
      certo(mes() - m0 >= 3 && mes() - m0 <= 5, `conferências do /me em 1,1 s com 250 ms: ${mes() - m0}`);
      certo(await titulo() === 'Estamos conferindo seu CRM', 'ainda pendente e saiu da espera: ' + await titulo());
      await ev(`window.__aba(true); 1`);                                         // aba escondida: para
      await sleep(200);                                                          // (o pedido que já tinha saído chega aqui)
      const m1 = mes();
      await sleep(900);
      certo(mes() === m1, `conferiu com a aba escondida: ${mes() - m1}`);
      await ev(`window.__aba(false); 1`);                                        // voltou: confere logo (passou do intervalo)
      await sleep(200);
      certo(mes() >= m1 + 1, `não voltou a conferir com a aba à vista: ${mes() - m1}`);
      ME = { logged_in: true, user: { id: 'u1' }, scribe: false, bloqueio: null };   // o administrador aprovou
      await ate(`location.pathname === '/opendoctor-agenda.html'`, 3000, 'liberada e não abriu o app');
      certo(await ev(`location.search`) === '?bemvindo=1', 'destino diferente do login: ' + await ev(`location.search`));
      // recarregou a espera (sem o destino do login) e foi recusada: mostra a recusa e para de conferir
      ME = { logged_in: true, user: { id: 'u1' }, scribe: false, bloqueio: 'crm_pendente' };
      await abre('?next=%2F%2Fmal.example%2Fx');
      await ate(`document.getElementById('title').textContent === 'Estamos conferindo seu CRM'`, 3000, 'espera ao recarregar');
      ME = { logged_in: true, user: { id: 'u1' }, scribe: false, bloqueio: 'crm_recusado' };
      await ate(`document.getElementById('title').textContent === 'Não foi possível liberar sua conta'`, 3000, 'recusa: ' + await titulo());
      const m2 = mes();
      await sleep(700);
      certo(mes() === m2 && await ev(`location.pathname`) === '/opendoctor-login.html', 'continuou conferindo depois da recusa');
      // liberada depois de abrir com um next de fora: vai para a agenda (a mesma regra de auth.safe_next)
      ME = { logged_in: true, user: { id: 'u1' }, scribe: false, bloqueio: 'crm_pendente' };
      await abre('?next=%2F%2Fmal.example%2Fx');
      await ate(`document.getElementById('title').textContent === 'Estamos conferindo seu CRM'`, 3000, 'espera de novo');
      ME = { logged_in: true, user: { id: 'u1' }, scribe: false, bloqueio: null };
      await ate(`location.pathname === '/opendoctor-agenda.html'`, 3000, 'liberada com o next de fora');
      certo(await ev(`location.origin + location.search`) === ORIG, 'next de fora: ' + await ev(`location.href`));
    } finally {
      await send('Page.removeScriptToEvaluateOnNewDocument', { identifier });
    }
    // sem o relógio do teste, o intervalo é de 30 s
    const { identifier: id2 } = await send('Page.addScriptToEvaluateOnNewDocument', { source: `window.__esperas = [];
      (() => { const st = window.setTimeout; window.setTimeout = (f, ms, ...a) => { window.__esperas.push(ms); return st(f, ms, ...a); }; })();` });
    try {
      ME = { logged_in: true, user: { id: 'u1' }, scribe: false, bloqueio: 'crm_pendente' };
      await abre();
      await ate(`document.getElementById('title').textContent === 'Estamos conferindo seu CRM'`, 3000, 'espera (30 s)');
      const esperas = await ev(`window.__esperas`);
      certo(esperas.some((ms) => ms > 29000 && ms <= 30000), 'intervalos: ' + JSON.stringify(esperas));
    } finally {
      await send('Page.removeScriptToEvaluateOnNewDocument', { identifier: id2 });
    }
    return '/me a cada intervalo, parado com a aba escondida, de volta ao voltar; liberada vai ao destino do login; recusada para';
  }],
  ['Google com e-mail não verificado e o nascimento sem preenchimento automático', async () => {
    await abre('?erro=google_nao_verificado&next=%2Fopendoctor-configuracoes.html');
    certo(await vis('#alert') && await txt('#alertText') === 'Esse e-mail não foi verificado pelo Google.', 'mensagem: ' + await txt('#alertText'));
    certo(!(await ev(`document.getElementById('alert').classList.contains('info')`)), 'o aviso devia sair em vermelho (erro), não em cinza');
    certo(await vis('#emailForm') && await titulo() === 'Bem-vindo à OpenDoctor', 'não ficou na tela inicial: ' + await titulo());
    certo(await ev(`location.search`) === '?next=%2Fopendoctor-configuracoes.html', 'o erro ficou na URL: ' + await ev(`location.search`));
    const ac = await ev(`['rNasc', 'cNasc'].map((i) => document.getElementById(i).getAttribute('autocomplete')).join()`);
    certo(ac === 'off,off', 'autocomplete do nascimento: ' + ac);
    return 'aviso "Esse e-mail não foi verificado pelo Google." na tela inicial; nascimento com autocomplete=off';
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
      if (RECUSAS > 0) { RECUSAS--; send('Page.handleJavaScriptDialog', { accept: false }); return; }
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
    START = null; REG_GOOGLE = null; ME = { logged_in: false, user: null, scribe: false, bloqueio: null };   // um cenário não herda o outro
    try { const r = await fn(); log(`✓ ${nome} (${Math.round((Date.now() - t0) / 1000)} s): ${r}`); }
    catch (e) { falhas++; log(`✗ ${nome}: ${e.message}`); }
  }
  if (erros.length) { falhas++; log('✗ erros na página:\n  ' + erros.join('\n  ')); }
  log(falhas ? `\n${falhas} falha(s)` : '\ntudo certo');
  return falhas;
}
main().then((f) => { fim(); process.exit(f ? 1 : 0); }, (e) => { console.error('erro:', e.message); fim(); process.exit(2); });
