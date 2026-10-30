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
// cada item da receita: "nome dose | quantidade"
const linhas = `[...document.querySelectorAll('#rxBody .rx-row')].map((b) => b.querySelector('.rx-n').textContent + ' | ' + b.querySelector('.rx-q').textContent)`;
const n = (sel) => `document.querySelectorAll(${JSON.stringify(sel)}).length`;
const certo = (cond, msg) => { if (!cond) throw new Error(msg); };
const dialogos = [];                                       // confirm()/alert() que a página abriu (a receita não abre nenhum)

async function limpa() {
  recusa = null; dialogos.length = 0;
  await srv('/_preview/reset'); await medico({ name: 'Dra. Teste', crm: '123456', crm_uf: 'SP', consultorio_endereco: 'Rua A, 1', receita_papel: '' });
  await send('Page.navigate', { url: BASE + '/health' }); await sleep(250);
  await ev(`(() => { sessionStorage.clear(); localStorage.clear(); return 1; })()`);
}
async function abre(exemplo = true) {
  await send('Page.navigate', { url: BASE + '/_preview/pr?pid=9001&tab=prescricoes' + (exemplo ? '&exemplo=1' : '') });
  await ate(`document.querySelectorAll('.rxc-linha.ia').length > 0`, 20000, 'sugestões');
  await ate(`!!document.querySelector('#rxNew .fz-in') && !document.querySelector('#rxNew .fz-in').disabled`, 8000, 'barra de adicionar');
}
const tecla = (sel, k) => ev(`(() => { document.querySelector(${JSON.stringify(sel)}).dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(k)}, bubbles: true })); return 1; })()`);
// a barra "Adicionar medicamento": digita e dá Enter (o Enter vale para o primeiro resultado quando ele chega)
async function busca(t) {
  await ev(`(() => { const q = document.querySelector('#rxNew .fz-in'); q.focus(); q.value = ${JSON.stringify(t)}; q.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
}
// um remédio pela barra; o foco vai para a posologia dele, Enter → quantidade, Enter → de volta para a barra
async function item(t, pos, qtd, alergia = false) {
  const antes = await ev(n('#rxBody .rx-row'));
  await busca(t); await tecla('#rxNew .fz-in', 'Enter');
  if (alergia) {
    await ate(`(document.querySelector('#rxNew .fz-row.on .fz-vs') || {}).textContent === 'Enter de novo para adicionar'`, 6000, 'alergia pede o 2º Enter');
    certo(await ev(n('#rxBody .rx-row')) === antes, 'com alergia, o 1º Enter não adiciona');
    await tecla('#rxNew .fz-in', 'Enter');
  }
  await ate(n('#rxBody .rx-row') + ' === ' + (antes + 1), 8000, 'entrou ' + t);
  await ate(`document.activeElement.classList.contains('rxc-pos')`, 3000, 'o foco foi para a posologia');
  if (pos == null) return;
  await ev(`(() => { const p = document.activeElement; p.textContent = ${JSON.stringify(pos)}; p.dispatchEvent(new Event('input', { bubbles: true }));
    p.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); return 1; })()`);
  certo(await ev(`document.activeElement.classList.contains('rx-q')`), 'Enter na posologia leva à quantidade');
  if (qtd != null) await ev(`(() => { const q = document.activeElement; q.textContent = ${JSON.stringify(qtd)}; q.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
  await ev(`(() => { document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); return 1; })()`);
  certo(await ev(`document.activeElement === document.querySelector('#rxNew .fz-in')`), 'Enter na quantidade volta para a barra');
}
// o rascunho salva sozinho (300 ms depois de digitar, 600 ms depois de mudar): espera a gravação começar e terminar
const salvo = async () => { await sleep(1100); await ate(`document.getElementById('rxSt').textContent === 'rascunho salvo'`, 8000, 'rascunho salvo'); };
// Emitir: a confirmação aparece na própria receita (nunca confirm()); "Emitir e imprimir" emite
async function emite() {
  await ev(`(() => { window.__folhas = null; document.body.classList.remove('rxp'); document.activeElement.blur(); document.getElementById('rxEmit').click(); return 1; })()`);
  await ate(`!document.querySelector('.rxc-conf').hidden || !document.getElementById('rxMsg').hidden`, 5000, 'confirmação ou recado');
  if (await ev(`!document.querySelector('.rxc-conf').hidden`)) {
    certo(await ev(`document.activeElement === document.getElementById('rxConfirma')`), 'o foco vai para "Emitir e imprimir"');
    await ev(`document.getElementById('rxConfirma').click()`);
    await ate(`window.__folhas !== null || !document.getElementById('rxMsg').hidden`, 10000, 'emitir');
  }
  certo(!dialogos.includes('confirm'), 'a receita não usa confirm()');
}
const sg = (nome) => `[...document.querySelectorAll('.rxc-linha.ia')].find((r) => r.querySelector('.rxc-linha-t').textContent.toLowerCase().startsWith(${JSON.stringify(nome.toLowerCase())}))`;
// o cursor no fim (ou no começo) de um trecho editável da receita
const cursor = (sel, fim) => ev(`(() => { const c = ${sel}; c.focus(); const r = document.createRange(); r.selectNodeContents(c); r.collapse(${!fim});
  const s = getSelection(); s.removeAllRanges(); s.addRange(r); return 1; })()`);
const emUso = async () => (await srv('/patients')).patients.find((p) => p.id === 9001).medications.split('\n');
// Histórico (visual da tabela de Consultas, uma linha por remédio): ação da receita i (no cabeçalho dela)
const acaoRh = (t, i = 0) => ev(`(() => { [...[...document.querySelectorAll('#rhList .rh-head')][${i}].querySelectorAll('.rh-acts button')]
  .find((b) => b.textContent === ${JSON.stringify(t)}).click(); return 1; })()`);
// "Usar nesta consulta" na linha do remédio (na i-ésima linha com esse nome)
const usaRh = (nome) => ev(`(() => { [...document.querySelectorAll('#rhList .rh-item')].find((r) => r.querySelector('.pr-tdate').textContent.startsWith(${JSON.stringify(nome)}))
  .querySelector('button').click(); return 1; })()`);
const daApi = () => ev(`fetch('/prontuario/receitas?patient_id=9001').then((r) => r.json()).then((j) => j.receitas.map((r) => [r.tipo, r.status, r.itens.map((i) => i.nome).join('+'), r.motivo_cancelamento || '', r.itens]))`);
const linha = (nome) => `[...document.querySelectorAll('#rxBody .rx-row')].find((r) => r.querySelector('.rx-n').textContent.startsWith(${JSON.stringify(nome)}))`;
// prontuário avulso: escreve a evolução (S) e espera o salvar automático (é quando ela passa a existir)
async function evolucao(txt) {
  await ev(`(() => { const t = document.querySelector('#prSoap textarea[data-f=s]'); t.value = ${JSON.stringify(txt)}; t.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
  await ate(`/^Salvo às/.test(document.getElementById('prStatus').textContent)`, 10000, 'evolução salva');
}
const notas = (st) => `fetch('/prontuario/receitas?patient_id=9001').then((r) => r.json()).then((j) => j.receitas.filter((r) => r.status === ${JSON.stringify(st)}).map((r) => r.note_id))`;
const semConsulta = `[...document.querySelectorAll('#rhList .rh-hs')].some((t) => t.textContent.includes('Sem consulta'))`;

const cenarios = [
  ['renovar o uso contínuo da última receita em um clique', async () => {
    await abre();
    const faixa = await ev(`[...document.querySelectorAll('.rxc-linha.renova .rxc-linha-t')].map((t) => t.textContent).join(' · ')`);
    certo(faixa === 'Losartana 50 mg · Metformina 850 mg · Atorvastatina 20 mg', 'uma linha por remédio: ' + faixa);
    for (let k = 0; k < 3; k++) { await ev(`document.querySelector('.rxc-linha.renova .rxc-bt').click()`); await sleep(250); }
    await salvo();
    const l = await ev(linhas);
    certo(l.join('; ') === 'Losartana 50 mg | 60 comprimidos; Metformina 850 mg | 60 comprimidos; Atorvastatina 20 mg | 30 comprimidos', 'renovados: ' + l.join('; '));
    certo(await ev(`[...document.querySelectorAll('#rxBody .rxc-pos')].every((p) => /uso contínuo$/.test(p.textContent))`), 'posologia da última vez, com uso contínuo');
    certo(await ev(`!document.querySelector('.rxc-linha.renova') && document.activeElement === document.getElementById('rxEmit')`), 'as linhas somem e o foco vai para Emitir');
    const d = (await daApi()).find((r) => r[1] === 'rascunho');
    certo(d && d[4].length === 3 && d[4].every((x) => x.continuo), 'rascunho salvo com os 3 de uso contínuo');
    await emite(); await ate(n('#rxBody .rx-row') + ' === 0', 6000, 'receita vazia depois de emitir');
    certo(await ev(`!document.querySelector('.rxc-linha.renova')`), 'depois de emitir, o Renovar não volta');
    return '3 remédios com a posologia da última vez e a quantidade de 30 dias';
  }],
  ['adicionar pela busca: dose, alergia, sugestões e quantidade calculada', async () => {
    await abre(false);
    await busca('amox 500'); await ate(n('#rxNew .fz-row') + ' > 0', 6000, 'resultados');
    const r = await ev(`[...document.querySelectorAll('#rxNew .fz-row')].map((b) => b.querySelector('.fz-t').textContent)`);
    certo(r[0] === 'Amoxicilina 500 mg' && r.every((t) => / 500 mg/.test(t)), 'a dose filtra: ' + r.join(' | '));
    certo(await ev(`document.querySelector('#rxNew .fz-row .fz-vs.al').textContent`) === 'Alergia: Penicilina', 'alergia no resultado');
    await ev(`(() => { const q = document.querySelector('#rxNew .fz-in'); q.value = ''; q.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
    await item('amox 500', null, null, true);
    const l = linha('Amoxicilina 500 mg');
    certo(await ev(`${l}.querySelector('.rxc-forma').textContent`) === 'cápsula, uso oral', 'forma e via');
    // a posologia entra em modelo com lacunas; a 1ª já selecionada, Tab vai à próxima
    const sel = `(() => { const p = document.activeElement, s = getSelection(), r = s.getRangeAt(0), a = document.createRange();
      a.selectNodeContents(p); a.setEnd(r.startContainer, r.startOffset); return [p.textContent, s.toString(), a.toString().length]; })()`;
    let [v, s0, i0] = await ev(sel);
    certo(v === 'Tomar 1 cápsula a cada _ horas, por _ dias.' && s0 === '_', 'modelo com a 1ª lacuna selecionada: ' + v);
    const escreve = (t) => ev(`document.execCommand('insertText', false, ${JSON.stringify(t)})`);
    await escreve('8'); await tecla('#rxBody .rx-row:last-child .rxc-pos', 'Tab');
    const [, s1, i1] = await ev(sel); certo(s1 === '_' && i1 > i0, 'Tab foi para a 2ª lacuna');
    await escreve('7');
    certo(await ev(`${l}.querySelector('.rxc-pos').textContent`) === 'Tomar 1 cápsula a cada 8 horas, por 7 dias.', 'posologia completa');
    certo(await ev(`${l}.querySelector('.rx-q').textContent === '21 cápsulas' && !${l}.querySelector('.rxc-calc').hidden`), 'quantidade calculada: 21 cápsulas');
    const casos = [['1 cápsula de 12/12 h, uso contínuo', '60 cápsulas'], ['2 cápsulas ao dia por 10 dias', '20 cápsulas'],
                   ['1,5 cápsula a cada 12 horas por 5 dias', '15 cápsulas'], ['1 cápsula se dor', '30 cápsulas'], ['5 mL de 8/8 h por 5 dias', '30 cápsulas']];
    for (const [pos, q] of casos) {
      const v = await ev(`(() => { const p = ${l}.querySelector('.rxc-pos'); p.textContent = ${JSON.stringify(pos)}; p.dispatchEvent(new Event('input', { bubbles: true })); return ${l}.querySelector('.rx-q').textContent; })()`);
      certo(v === q, `"${pos}" → ${v} (esperado ${q})`);
    }
    await ate(`document.querySelector('.rxc-avisos').innerText.includes('Amoxicilina 500 mg: Alergia registrada: Penicilina') &&
      document.querySelector('.rxc-avisos').innerText.includes('Antimicrobiano: sai numa receita separada') && ${l}.querySelector('.rxc-chip').classList.contains('al')`, 6000,
      'avisos na lista e a etiqueta vermelha');
    certo(await ev(`document.querySelector('.rxc-resumo').textContent`) === 'Sai 1 receita de antimicrobiano (2 vias)', 'o que vai sair');
    return 'amox 500 → modelo com lacunas, 8 · Tab · 7 → 21 cápsulas; tabela da quantidade ok';
  }],
  ['marca pela busca entra como "Marca (substância)", com a embalagem', async () => {
    await abre(false); await busca('glifage 850'); await ate(n('#rxNew .fz-row') + ' > 0', 6000, 'resultados');
    const r = await ev(`[...document.querySelectorAll('#rxNew .fz-row')].map((b) => b.querySelector('.fz-t').textContent + ' / ' + b.querySelector('.fz-s').textContent)[0]`);
    certo(r === 'Glifage (cloridrato de metformina) 850 mg / comprimido revestido · Merck', 'resultado: ' + r);
    await item('glifage 850', '1 comprimido de 12/12 h, uso contínuo'); await salvo();
    const l = await ev(linhas);
    certo(l[0] === 'Glifage (cloridrato de metformina) 850 mg | 60 comprimidos', 'na receita: ' + l.join('; '));
    return l[0];
  }],
  ['excluir pelo × e desfazer', async () => {
    await abre(false);
    await item('losartana 50', '1 comprimido de 12/12 h, uso contínuo'); await item('metformina 850', '1 comprimido 2x/dia, uso contínuo');
    await item('atorvastatina 20', '1 comprimido à noite, uso contínuo'); await salvo();
    certo((await ev(linhas)).length === 3, '3 itens na receita');
    await ev(`${linha('Cloridrato de metformina')}.querySelector('.rx-x').click()`); await salvo();
    certo(!(await daApi()).find((r) => r[1] === 'rascunho')[2].includes('metformina'), 'o rascunho salvo ficou sem a metformina');
    await ev(`document.querySelector('.pr-toast.pr-desfaz button').click()`); await salvo();
    const l = await ev(linhas); certo(l.length === 3 && l[1].startsWith('Cloridrato de metformina'), 'desfazer volta no mesmo lugar: ' + l.join('; '));
    return 'saiu, salvou sem ela e voltou no lugar';
  }],
  ['Backspace na posologia vazia tira o remédio; setas andam entre as linhas', async () => {
    await abre(false); await item('losartana 50', '1 comprimido de 12/12 h, uso contínuo'); await item('omeprazol 20', '1 cápsula em jejum por 30 dias'); await salvo();
    const p = (i) => `document.querySelectorAll('#rxBody .rxc-pos')[${i}]`;
    await cursor(p(0), true); await tecla('#rxBody .rx-row:first-child .rxc-pos', 'ArrowRight');
    certo(await ev(`document.activeElement === document.querySelectorAll('#rxBody .rx-q')[0]`), '→ no fim da posologia vai para a quantidade');
    await cursor(`document.querySelectorAll('#rxBody .rx-q')[0]`, true);
    await ev(`(() => { document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })); return 1; })()`);
    certo(await ev(`document.activeElement === ${p(1)}`), '↓ no fim da quantidade vai para o próximo remédio');
    await cursor(p(1), false);
    await ev(`(() => { document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true })); return 1; })()`);
    certo(await ev(`document.activeElement === document.querySelectorAll('#rxBody .rx-q')[0]`), '↑ no começo volta para o trecho anterior');
    await ev(`(() => { const c = ${p(1)}; c.textContent = ''; c.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`); await cursor(p(1), false);
    await ev(`(() => { document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true })); return 1; })()`);
    await ate(n('#rxBody .rx-row') + ' === 1', 3000, 'Backspace tirou o omeprazol'); await salvo();
    await ev(`document.querySelector('.pr-toast.pr-desfaz button').click()`);
    await ate(n('#rxBody .rx-row') + ' === 2', 3000, 'Desfazer voltou');
    return 'setas entre posologia, quantidade e o próximo; Backspace tira e Desfazer volta';
  }],
  ['orientações: texto livre salvo, volta ao recarregar e sai impresso', async () => {
    await abre(false); await item('losartana 50', '1 comprimido de 12/12 h, uso contínuo');
    await ev(`(() => { const o = document.querySelector('.rxc-ori'); o.focus(); o.value = 'Beber bastante água.\\nRetorno em 30 dias.'; o.dispatchEvent(new Event('input', { bubbles: true })); return 1; })()`);
    await salvo();
    certo((await daApi()).find((r) => r[1] === 'rascunho') && (await srv('/prontuario/receitas?patient_id=9001')).receitas[0].orientacoes === 'Beber bastante água.\nRetorno em 30 dias.', 'salvo no rascunho');
    await send('Page.reload'); await sleep(500);
    await ate(`!!document.querySelector('.rxc-ori') && document.querySelector('.rxc-ori').value === 'Beber bastante água.\\nRetorno em 30 dias.'`, 15000, 'voltou ao recarregar');
    await ate(`!!document.querySelector('#rxNew .fz-in') && !document.querySelector('#rxNew .fz-in').disabled`, 8000, 'busca');
    await sleep(1500);                                     // o preview ainda clica na aba por 1 s depois de carregar
    await emite(); await ate(`window.__folhas !== null`, 8000, 'folha');
    const t = await ev(`document.getElementById('rxPrint').innerText`);
    certo(t.includes('Orientações') && t.includes('Beber bastante água.') && t.includes('Retorno em 30 dias.'), 'na folha: ' + t.slice(0, 300));
    return 'salvas, recarregadas e impressas';
  }],
  ['remédio que já está na receita: Enter leva até ele', async () => {
    await abre(false); await item('losartana 50', '1 comprimido de 12/12 h');
    await busca('losartana 50'); await ate(n('#rxNew .fz-row') + ' > 0', 6000, 'resultados');
    certo(await ev(`document.querySelector('#rxNew .fz-row .fz-vs.ja').textContent`) === 'Já na receita', 'marca "Já na receita"');
    await tecla('#rxNew .fz-in', 'Enter');
    await ate(`document.activeElement.classList.contains('rxc-pos')`, 3000, 'foco no item');
    certo(await ev(n('#rxBody .rx-row')) === 1, 'não repetiu');
    return 'não repete; o foco vai para a posologia dele';
  }],
  ['lacuna sem preencher não emite: diz o quê e leva o cursor até ela', async () => {
    await abre(false); await item('losartana 50'); await salvo();
    await emite();
    const m = await ev(`document.getElementById('rxMsg').innerText`);
    certo(m.startsWith('Complete a posologia de Losartana potássica 50 mg'), 'recado: ' + m);
    certo(await ev(`(() => { const p = document.activeElement; return p.classList.contains('rxc-pos') && p.classList.contains('falta') && getSelection().toString() === '_'; })()`),
      'cursor na lacuna, marcado');
    certo(!(await daApi()).some((r) => r[1] === 'emitida'), 'nada emitido');
    return 'recado e foco na posologia que falta';
  }],
  ['emitir sem CRM pede os dados; com os dados separa e imprime em vias', async () => {
    await medico({ crm: '' }); await abre(false); await item('losartana 50', '1 comprimido de 12/12 h, uso contínuo');
    await item('azitromicina 500', '1 comprimido ao dia por 3 dias'); await salvo();
    await emite(); const m = await ev(`document.getElementById('rxMsg').innerText`);
    certo(m.includes('complete seus dados') && m.includes('CRM'), 'recado de dados do médico: ' + m);
    await medico({ crm: '123456' }); await emite();
    await ate(`window.__folhas !== null`, 8000, 'folhas');
    const f = await ev(`window.__folhas`);
    certo(f.join('|') === 'Receita|Receita de antimicrobiano · 1ª via · retida na farmácia|Receita de antimicrobiano · 2ª via · paciente', 'folhas: ' + f.join('|'));
    const t = await ev(`document.getElementById('rxPrint').innerText`);
    certo(t.includes('Losartana potássica 50 mg, comprimido revestido') && t.includes('3 comprimidos'), 'a forma e a quantidade calculada na folha');
    await ate(n('#rxBody .rx-row') + ' === 0', 5000, 'rascunho vazio depois de emitir');
    const api = await daApi(); certo(api.filter((r) => r[1] === 'emitida' && r[2].includes('Azitromicina')).length === 1, 'antimicrobiano emitido à parte');
    return f.length + ' folhas: simples + antimicrobiano em 2 vias, com a forma';
  }],
  ['o que exige talão não sai', async () => {
    await abre(false); await item('clonazepam 2', '1 comprimido à noite', '30 comprimidos');
    await ate(`document.querySelector('.rxc-avisos').innerText.includes('Notificação de Receita B') && document.querySelector('#rxBody .rxc-chip').classList.contains('al')`, 6000, 'aviso de talão'); await salvo();
    await emite(); const m = await ev(`document.getElementById('rxMsg').innerText`);
    certo(m.includes('talão') && m.includes('Clonazepam'), 'recusou: ' + m);
    certo(!(await daApi()).some((r) => r[1] === 'emitida'), 'nada emitido');
    return 'recusado, com o recado do talão';
  }],
  ['controle especial em 2 vias, com comprador e fornecedor', async () => {
    await abre(false); await item('sertralina 50', '1 comprimido pela manhã, uso contínuo'); await salvo();
    await ate(`document.querySelector('.rxc-resumo').textContent === 'Sai 1 receita de controle especial (2 vias)'`, 6000, 'o que vai sair');
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
    await abre(false); await item('losartana 50', '1 comprimido de 12/12 h, uso contínuo');
    await item('omeprazol 20', '1 cápsula em jejum por 30 dias'); await salvo();
    const antes = await ev(linhas);
    await send('Page.reload'); await sleep(500);
    await ate(`!!document.getElementById('rxBody') && document.querySelectorAll('#rxBody .rx-row').length === 2`, 15000, 'rascunho depois de recarregar');
    const depois = await ev(linhas); certo(depois.join() === antes.join(), 'igual: ' + depois.join('; '));
    return depois.map((l) => l.split(' | ')[0]).join(', ') + ' voltaram';
  }],
  ['receitas emitidas aparecem no card da consulta no Histórico', async () => {
    await abre();
    await ev(`document.querySelector('#prTabs [data-tab=consultas]').click()`); await sleep(500);
    await ev(`(() => { const r = [...document.querySelectorAll('.pr-trow')].find((x) => x.offsetParent !== null && /Retorno/.test(x.innerText)); r.click(); return 1; })()`);
    await ate(`[...document.querySelectorAll('.pr-item.hc .hc-sp')].some((x) => /Receita simples · emitida/.test(x.textContent))`, 6000, 'receita no card');
    return 'seção "Receita simples · emitida em …" no card';
  }],
  ['prontuário avulso: a receita emitida antes da evolução entra nela (card do Histórico e PDF)', async () => {
    await abre(false); await item('losartana 50', '1 comprimido de 12/12 h, uso contínuo'); await salvo();
    await emite(); await ate(`window.__folhas !== null`, 8000, 'folha');
    certo((await ev(notas('emitida'))).join() === '', 'emitida sem consulta: a evolução ainda não existe');
    await evolucao('Renovação das receitas de uso contínuo.');
    await ate(`${notas('emitida')}.then((n) => n.length === 1 && n[0] > 0)`, 8000, 'a receita ligada à evolução salva');
    await ate(`!${semConsulta} && [...document.querySelectorAll('#rhList .rh-hs')].some((t) => t.textContent.includes('Evolução avulsa'))`, 5000,
      'o Histórico de receitas diz a evolução, não "Sem consulta"');
    // outra vez no prontuário (pela lista de Pacientes): a evolução de antes, com a receita, no card e no PDF
    await ev(`window.__openProntuario({ patient_id: 9001, patient: 'Maria Silva', from: 'pacientes' })`);
    await ate(`[...document.querySelectorAll('#prVisits .pr-trow[aria-expanded]')].length === 1`, 8000, 'a evolução de antes no Histórico');
    await ev(`document.querySelector('#prTabs [data-tab=consultas]').click()`); await sleep(300);
    await ev(`document.querySelector('#prVisits .pr-trow[aria-expanded]').click()`);
    await ate(`[...document.querySelectorAll('.pr-item.hc .hc-sp')].some((x) => /Receita simples · emitida/.test(x.textContent))`, 6000, 'receita no card');
    await ev(`(() => { [...document.querySelectorAll('.pr-item.hc')].forEach((c) => c.remove()); document.getElementById('prExport').click(); return 1; })()`);
    await ate(`[...document.querySelectorAll('#prVisits .pr-item.hc .hc-sp')].some((x) => /Receita simples · emitida/.test(x.textContent))`, 6000, 'receita no PDF');
    return 'ligada ao salvar a evolução; no card e no PDF';
  }],
  ['prontuário avulso: o rascunho feito antes da evolução passa a ser dela e sai nela', async () => {
    await abre(false); await item('omeprazol 20', '1 cápsula em jejum por 30 dias'); await salvo();
    certo((await ev(notas('rascunho'))).join() === '', 'rascunho sem consulta');
    await evolucao('Dor epigástrica há 1 semana.');
    await ate(`${notas('rascunho')}.then((n) => n.length === 1 && n[0] > 0)`, 8000, 'o rascunho ligado à evolução salva');
    const [nid] = await ev(notas('rascunho'));
    await emite(); await ate(`window.__folhas !== null`, 8000, 'folha');
    certo((await ev(notas('emitida'))).join() === String(nid), 'emitida na evolução');
    return 'rascunho e receita emitida na evolução ' + nid;
  }],
  ['prontuário avulso: o rascunho que já estava sem consulta sai na evolução escrita aqui', async () => {
    await srv('/prontuario/receitas', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ patient_id: 9001,
      itens: [{ nome: 'Losartana potássica', dose: '50 mg', posologia: '1 comprimido de 12/12 h, uso contínuo', quantidade: '60 comprimidos' }] }) });
    await abre(false); await ate(n('#rxBody .rx-row') + ' === 1', 8000, 'o rascunho sem consulta aberto aqui');
    await evolucao('Renovação.');
    certo((await ev(notas('rascunho'))).join() === '', 'salvar a evolução não pega o rascunho que não é desta consulta');
    await emite(); await ate(`window.__folhas !== null`, 8000, 'folha');
    await ate(`${notas('emitida')}.then((n) => n.length === 1 && n[0] > 0)`, 5000, 'emitida na evolução escrita aqui');
    certo(!(await ev(semConsulta)), 'o Histórico de receitas não diz "Sem consulta"');
    return 'emitido na evolução aberta';
  }],
  ['depois de emitir, oferece atualizar as medicações em uso', async () => {
    await abre(); await item('metformina 1000', '1 comprimido de 12/12 h, uso contínuo'); await salvo();
    await emite(); await ate(`!document.getElementById('rxSync').hidden`, 6000, 'oferta de atualizar');
    const t = await ev(`document.getElementById('rxSync').innerText`);
    certo(/Metformina 850 mg 2x\/dia → Cloridrato de metformina 1000 mg/.test(t), 'oferta: ' + t);
    await ev(`[...document.querySelectorAll('#rxSync button')].find((b) => b.textContent === 'Atualizar').click()`);
    await ate(`document.getElementById('rxSync').hidden`, 3000, 'fechou a oferta'); await sleep(400);
    const u = await emUso();
    certo(u.some((x) => x.startsWith('Cloridrato de metformina 1000 mg')) && !u.some((x) => x.startsWith('Metformina 850')) && u.includes('Losartana 50 mg 12/12h'), 'em uso: ' + u.join('; '));
    return 'trocou a dose da metformina nas medicações em uso';
  }],
  ['possíveis prescrições: 2 linhas no bloco de cima; Adicionar leva à posologia', async () => {
    await abre();
    certo(await ev(n('.rxc-linha.ia')) === 2 && await ev(`!!${sg('Dapagliflozina')} && !!${sg('Semaglutida')}`), 'só 2 remédios novos');
    certo(await ev(`[...document.querySelectorAll('.rxc-linha.ia button')].map((b) => b.textContent.trim()).join('|')`) === 'Adicionar|Adicionar', 'só o Adicionar');
    certo(await ev(`!document.getElementById('rnBox')`), 'o cartão antigo saiu');
    await ev(`${sg('Dapagliflozina')}.querySelector('.rxc-bt').click()`); await salvo();
    certo((await ev(linhas)).some((l) => l.startsWith('Dapagliflozina 10 mg')), 'foi para a receita');
    certo(await ev(`document.activeElement === ${linha('Dapagliflozina')}.querySelector('.rxc-pos')`), 'o foco foi para a posologia dela, para revisar');
    certo(await ev(`!${sg('Dapagliflozina')} && !!${sg('Semaglutida')}`), 'a linha da sugestão que entrou some');
    return 'Dapagliflozina e Semaglutida; Adicionar leva à posologia';
  }],
  ['histórico aparece mesmo sem receitas, avisando que ainda não há', async () => {
    await abre(false);
    certo(await ev(`!document.getElementById('rhBox').hidden && document.getElementById('rhList').innerText.includes('Nenhuma receita emitida para este paciente ainda')`),
      'o Histórico fica à vista, vazio');
    certo(await ev(`document.getElementById('rhQ').hidden`), 'sem a busca enquanto não há receita');
    return 'Histórico à vista, com o aviso de que ainda não há receita';
  }],
  ['histórico de receitas: busca por remédio e escolha dos itens', async () => {
    await abre(); await ate(n('#rhList .rh-item') + ' > 0', 5000, 'histórico');
    certo(await ev(`document.querySelector('#rhBox .gh-t').textContent === 'Histórico' && !document.getElementById('rtBox')`), 'um cartão só, Histórico');
    const bh = (t) => ev(`(() => { const q = document.getElementById('rhQ'); q.value = ${JSON.stringify(t)}; q.dispatchEvent(new Event('input', { bubbles: true }));
      return document.querySelectorAll('#rhList .rh-item').length; })()`);
    certo(await bh('parac') === 1 && await ev(n('#rhList .rh-head')) === 1, 'a busca acha só a linha do paracetamol, com a receita dela');
    certo(await bh('xyz') === 0 && (await ev(`document.getElementById('rhList').innerText`)).includes('Nenhuma receita'), 'sem resultado avisa');
    await bh('');
    await usaRh('Losartana'); await usaRh('Atorvastatina'); await salvo();     // a escolha é linha a linha
    const l = (await ev(linhas)).map((x) => x.split(' | ')[0]).join(', ');
    certo(l === 'Losartana 50 mg, Atorvastatina 20 mg', 'foram só os escolhidos: ' + l);
    certo(await ev(`[...document.querySelectorAll('#rhList .rh-item')].filter((r) => r.innerText.includes('Na receita')).length`) >= 2, 'as linhas viram "Na receita"');
    return l + ' (a Metformina ficou de fora)';
  }],
  ['receita em A5 quando escolhido em Configurações', async () => {
    await medico({ receita_papel: 'A5' }); await abre(false); await item('losartana 50', '1 comprimido de 12/12 h, uso contínuo'); await salvo();
    await emite(); await ate(`window.__folhas !== null`, 8000, 'folha');
    certo(await ev(`document.getElementById('rxPapel').textContent.includes('size:A5') && document.getElementById('rxPrint').classList.contains('a5')`), 'folha em A5');
    await ev(`(() => { window.dispatchEvent(new Event('afterprint')); return 1; })()`);
    certo(await ev(`document.getElementById('rxPapel').textContent === '' && !document.body.classList.contains('rxp')`), 'o A5 sai depois de imprimir (o PDF do prontuário continua A4)');
    return 'A5 na receita; volta ao normal depois';
  }],
  ['nome e forma longos da base (Pneumovax 23, Foraseq): salva, emite e sai inteiro no papel', async () => {
    await medico({ receita_papel: 'A5' }); await abre(false);
    const pos = 'Conforme orientação médica; observar reações e retornar se houver febre, dor ou vermelhidão no local. '.repeat(4).trim();
    const [pn] = (await srv('/prontuario/remedios/busca?q=pneumovax')).itens, [fs] = (await srv('/prontuario/remedios/busca?q=foraseq')).itens;
    await item('pneumovax', pos); await item('foraseq', pos, '1 caixa'); await salvo();    // antes: "não salvou" (forma do Foraseq > 80)
    const d = (await daApi()).find((r) => r[1] === 'rascunho');
    certo(d && d[2] === pn.nome + '+' + fs.nome && pn.nome.length > 1000, 'rascunho com os dois: ' + (d ? d[2].slice(0, 80) : ''));
    await emite(); await ate(`window.__folhas !== null`, 8000, 'folha');
    const t = await ev(`document.getElementById('rxPrint').innerText`);
    const bs = [pn, fs].map((p) => [p.nome, p.apresentacoes[0].dose].filter(Boolean).join(' ') + ', ' + p.apresentacoes[0].forma);
    certo(bs.every((b) => t.includes(b)) && t.split(pos).length === 3, 'na folha, inteiros: ' + t.slice(0, 200));
    // no papel: palavra longa quebra dentro da largura da folha A5 (128 mm = 484 px)...
    await send('Emulation.setEmulatedMedia', { media: 'print' });
    const fora = await ev(`(() => { const box = document.getElementById('rxPrint'), b = box.querySelector('ol li b'), s = document.createElement('span');
      box.style.width = '484px'; s.textContent = ' ' + 'X'.repeat(300); b.appendChild(s);
      const lis = [...box.querySelectorAll('ol li')], r = lis.filter((li) => li.scrollWidth > li.clientWidth).length;
      s.remove(); box.style.width = ''; return lis.length && lis[0].clientWidth ? r : -1; })()`);
    await send('Emulation.setEmulatedMedia', { media: '' });
    certo(fora === 0, fora < 0 ? 'a folha não estava montada para imprimir' : fora + ' item(ns) saem da largura da folha');
    // ...e o PDF da folha (A5: 420 pt de largura) passa de uma página, sem cortar o fim
    const pdf = Buffer.from((await send('Page.printToPDF', { preferCSSPageSize: true })).data, 'base64').toString('latin1');
    const pags = Math.max(...[...pdf.matchAll(/\/Count (\d+)/g)].map((m) => +m[1])), larg = (pdf.match(/\/MediaBox \[0 0 ([\d.]+)/) || [])[1];
    certo(pags >= 2 && Math.round(+larg) === 420, `o PDF tem ${pags} página(s) de ${larg} pt`);
    return `${pn.nome.length} e ${fs.apresentacoes[0].forma.length} caracteres inteiros; PDF A5 com ${pags} páginas`;
  }],
];

async function main() {
  for (let i = 0; i < 50; i++) { try { const l = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch (_) {} await sleep(200); }
  await new Promise((ok) => ws.addEventListener('open', ok));
  ws.addEventListener('message', (m) => {
    const j = JSON.parse(m.data);
    if (j.id && espera.has(j.id)) { const w = espera.get(j.id); espera.delete(j.id); j.error ? w.no(new Error(j.error.message)) : w.ok(j.result); return; }
    if (j.method === 'Page.javascriptDialogOpening') { dialogos.push(j.params.type); send('Page.handleJavaScriptDialog', { accept: !(recusa && recusa.test(j.params.message)), promptText: resposta }); }
    if (j.method === 'Runtime.exceptionThrown') erros.push(j.params.exceptionDetails.exception?.description || j.params.exceptionDetails.text);
  });
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setFocusEmulationEnabled', { enabled: true });   // o foco funciona como numa janela de verdade
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
