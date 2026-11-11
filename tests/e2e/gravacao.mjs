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
// A tela é o cartão "Consulta" (Figma): no pé (#prRec), "Iniciar consulta" (.cs-go) ou, gravando, "Finalizar" (.cs-fim) acima da
// barra preta (.cs-bar) com o botão redondo .cs-stop (aria-label "Pausar a gravação" / "Continuar gravando"); enviando e gerando,
// .cs-msg na barra; pronta, o player (#csPlay); o "Assinar" da evolução flutua (#csFlut .cs-fim). Não há marca de autorização:
// "Iniciar consulta" grava direto.
// "on": o elemento não está escondido dentro do cartão (vale também com outra aba do prontuário aberta, como o chip antigo).
const UI = `(() => { const q = (s) => document.querySelector(s);
  const on = (e) => { if (!e) return false; for (let x = e; x && !(x.classList && x.classList.contains('pr-panel')); x = x.parentElement) if (x.hidden) return false; return true; };
  const t = (s) => { const e = q(s); return on(e) ? e.textContent.trim() : ''; };
  const stop = q('#prRec .cs-stop'), lab = on(q('#prRec .cs-bar')) && on(stop) ? stop.getAttribute('aria-label') : '', msg = t('#prRec .cs-msg');
  const st = lab === 'Pausar a gravação' ? 'gravando' : lab === 'Continuar gravando' ? (/interrompida/.test(t('#rcAlert')) ? 'interrompida' : 'pausada')
    : msg ? (/Gerando/.test(msg) ? 'gerando' : 'enviando')
    : on(q('#csPlay')) ? 'pronta'
    : [...document.querySelectorAll('#prRec .cs-go')].some(on) ? 'iniciar' : '';
  return { st, msg, tempo: t('#rcTime'), alerta: t('#rcAlert'), nota: t('#rcNote'),
           pill: q('#rcPill') && !q('#rcPill').hidden ? q('#rcPill').textContent.trim() : '',   // fixo: não tem offsetParent
           pontos: q('#rcReview') && !q('#rcReview').hidden ? q('#rcReview').querySelectorAll('.rc-pt').length : 0,
           botoes: [...document.querySelectorAll('#prRec button, #csFlutPe button')].filter((b) => on(b) && !b.hidden)
             .map((b) => (b.textContent.trim() || b.getAttribute('aria-label') || b.title) + (b.disabled ? ' (off)' : '')) }; })()`;
const IDB = `(async () => { const dbs = await indexedDB.databases(); const n = dbs.find((d) => d.name.startsWith('od_gravacao_')); if (!n) return [];
  return await new Promise((ok) => { const q = indexedDB.open(n.name); q.onsuccess = () => { const g = q.result.transaction('seg').objectStore('seg').getAll();
  g.onsuccess = () => { ok(g.result.map((x) => ({ k: x.k, part: !!x.part, pid: x.pid, dead: x.dead || null }))); q.result.close(); }; }; }); })()`;
async function clica(sel, txt, opcional) {                // botão visível e ativo; sem ele, falha aqui (e não num "esperou demais" depois)
  const ok = await ev(`(() => { const b = [...document.querySelectorAll(${JSON.stringify(sel)})].find((x) => !x.disabled && !x.hidden && x.offsetParent !== null && (!${JSON.stringify(txt || '')} || x.textContent.includes(${JSON.stringify(txt || '')}))); if (b) b.click(); return !!b; })()`);
  if (!ok && !opcional) throw new Error(`não achou o botão ${sel}${txt ? ' "' + txt + '"' : ''}`);
  return ok;
}
const est = (s) => `${UI}.st === ${JSON.stringify(s)}`;      // situação do cartão: iniciar, gravando, pausada, interrompida, enviando, gerando, pronta
const PE = `[...document.querySelectorAll('#prRec .cs-go, #prRec .cs-bar')].some((b) => b.offsetParent !== null)`;   // o pé do cartão na tela
// a evolução é só em SOAP: o texto da médica vai nos campos S, O, A e P (o antigo #prNote, texto livre, saiu da tela)
const escreve = (f, txt, soma) => ev(`(() => { const t = document.querySelector('#prSoap textarea[data-f=${f}]'); t.value = ${soma ? 't.value + ' : ''}${JSON.stringify(txt)};
  t.dispatchEvent(new Event('input', { bubbles: true })); return t.value; })()`);
const soap = () => ev(`Object.fromEntries([...document.querySelectorAll('#prSoap textarea[data-f]')].map((t) => [t.getAttribute('data-f'), t.value]))`);
const rede = (on) => send('Network.emulateNetworkConditions', { offline: !on, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });

async function abre(url) {
  await send('Page.navigate', { url: BASE + url });
  await ate(PE, 20000, 'gravador visível');
}
async function grava(url, segundos) {
  if (url) await abre(url);
  await ate(`[...document.querySelectorAll('#prRec .cs-go')].some((b) => b.offsetParent !== null && b.textContent.includes('Iniciar consulta'))`, 10000, 'Iniciar consulta');
  await clica('#prRec .cs-go', 'Iniciar consulta');                               // grava direto, sem marcar autorização
  await ate(est('gravando'), 10000, 'começar a gravar');
  await sleep(segundos * 1000);
}
const fimGravacao = () => clica('#prRec.bar .cs-fim', 'Finalizar');   // gravando: o Finalizar acima da barra encerra e gera
const finalizaEvo = () => clica('#csFlut .cs-fim', 'Assinar');           // pronta: o Assinar que flutua no pé assina a evolução
async function encerra() {
  await fimGravacao();
  await ate(est('pronta'), 60000, 'evolução pronta');
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
    await ate(est('interrompida'), 20000, 'recuperar como interrompida');
    await clica('#prRec .cs-stop[aria-label="Continuar gravando"]'); await ate(est('gravando'), 10000, 'voltar a gravar'); await sleep(10000);
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
    await rede(false); await fimGravacao(); await sleep(1500);
    await rede(true);
    await ev(`window.__openProntuario({ patient_id: 9004, patient: 'x', from: 'pacientes', event_id: 'evB', title: 'Retorno' })`);
    await sleep(12000);
    await ev(`window.__openProntuario({ patient_id: 9003, patient: 'x', from: 'pacientes', event_id: 'evA', title: 'Retorno' })`);
    await ate(est('pronta'), 20000, 'evolução de A pronta'); await sleep(3500);
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
    await ate(est('interrompida'), 15000, 'reencontrar a gravação avulsa');
    return (await ev(UI)).tempo + ' recuperados';
  }],
  ['revisão continua depois de recarregar: pontos, selo e sem duplicar', async () => {
    await grava('/_preview/pr?pid=9003&ev=evC', 20); await encerra(); await sleep(2500);
    const antes = (await ev(UI)).pontos;
    await send('Page.reload', { ignoreCache: true });
    await ate(est('pronta'), 20000, 'tela depois de recarregar'); await sleep(1500);
    const depois = await ev(UI);
    if (!antes || depois.pontos !== antes) throw new Error(`pontos para conferir: ${antes} antes, ${depois.pontos} depois`);
    await escreve('s', ' .', true);
    await sleep(3500);
    const nota = () => estado().then((e) => Object.values(e.evolucoes).find((n) => n.event_id === 'evC'));
    const n = await nota(), vezes = (n.content.match(/Refere boa adesão/g) || []).length;
    if (!n.scribe) throw new Error('o selo sumiu depois de recarregar e editar');
    if (vezes !== 1) throw new Error('texto gerado aparece ' + vezes + ' vezes');
    if (await ev(`[...document.querySelectorAll('button')].some((b) => b.offsetParent !== null && /Gravar mais/.test(b.textContent))`)) throw new Error('voltou o Gravar mais um trecho');
    return `${depois.pontos} pontos mantidos, selo mantido, texto uma vez só, sem o card da consulta gravada`;
  }],
  ['os números da revisão chegam ao finalizar mesmo depois de recarregar', async () => {
    await grava('/_preview/pr?pid=9003&ev=evH', 18); await encerra(); await sleep(2500);
    await send('Page.reload', { ignoreCache: true });
    await ate(est('pronta'), 20000, 'tela depois de recarregar'); await sleep(1500);
    await finalizaEvo(); await sleep(600);
    if (await ev(`!document.getElementById('rcFinal').hidden`)) await finalizaEvo();   // com o aviso na tela, o 2º Assinar assina
    const nota = () => estado().then((e) => Object.values(e.evolucoes).find((n) => n.event_id === 'evH'));
    await ate(`fetch('/_preview/estado').then((r) => r.json()).then((e) => Object.values(e.evolucoes).some((n) => n.event_id === 'evH' && n.timing))`, 15000, 'finalizar');
    const m = ((await nota()).timing || {}).scribe || {};
    if (!(m.gen_s > 0 && m.fim_s >= m.review_s + m.gen_s - 1 && m.mantido_pct > 90 && m.rec_s > 0)) throw new Error('métricas perdidas ao recarregar: ' + JSON.stringify(m));
    return `geração ${m.gen_s} s, do Encerrar ao Finalizar ${m.fim_s} s, mantido ${m.mantido_pct}%`;
  }],
  ['fone desconectado entre consultas: a seguinte grava com o microfone do computador', async () => {
    await grava('/_preview/pr?pid=9003&ev=evA', 3);
    await clica('#prRec button[aria-label^="Pausar"]'); await sleep(1500);
    await ev(`window.__foneDesligado = true`);                                    // AirPods de volta no estojo
    await ev(`window.__openProntuario({ patient_id: 9004, patient: 'x', from: 'pacientes', event_id: 'evB', title: 'Retorno' })`);
    await ate(`${PE} && [...document.querySelectorAll('#prRec .cs-go')].some((b) => b.offsetParent !== null)`, 20000, 'gravador da consulta 2');
    await grava('', 2);                                                            // mesma página: o fone escolhido continua lembrado
    const s = await ev(UI);
    if (s.st !== 'gravando') throw new Error('não gravou: ' + JSON.stringify(s));
    await clica('#prRec button[aria-label^="Pausar"]');
    return 'gravou com o microfone do computador';
  }],
  ['consulta avulsa: a gravação fica na evolução dela e não aparece em outra consulta avulsa', async () => {
    await grava('/_preview/pr?pid=9003', 20);
    await clica('#prRec button[aria-label^="Pausar"]'); await sleep(2500);
    const da9003 = (e) => Object.keys(e.gravacoes).find((k) => e.gravacoes[k].pid === 9003);    // (um envio atrasado do cenário anterior pode criar outra)
    const rec = da9003(await estado());
    await escreve('s', 'Dor lombar há 3 dias.');
    await ate(`fetch('/_preview/estado').then((r) => r.json()).then((e) => e.gravacoes[${JSON.stringify(rec)}].note_id)`, 15000, 'gravação ligada à evolução');
    const e = await estado(), nid = e.gravacoes[rec].note_id;
    const outra = await fetch(BASE + '/prontuario/notes', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_id: 9003, content: 'Outra consulta avulsa.', data: { mode: 'free' } }) }).then((r) => r.json());
    await ev(`window.__openProntuario({ patient_id: 9003, patient: 'x', from: 'pacientes', note_id: ${outra.id} })`);
    await sleep(4000);
    if ((await ev(UI)).st === 'interrompida') throw new Error('a gravação de outra consulta apareceu aqui');
    await ev(`window.__openProntuario({ patient_id: 9003, patient: 'x', from: 'pacientes', note_id: ${nid} })`);
    await ate(est('interrompida'), 15000, 'achar a gravação pela evolução dela');
    return 'ficou na evolução dela e só aparece nela';
  }],
  ['o aviso da IA não tem Desfazer e fecha no X, sem mexer no texto da médica', async () => {
    await abre('/_preview/pr?pid=9003&ev=evD');
    await escreve('s', 'Texto da médica antes.');
    await grava('', 18); await encerra();
    const gerado = await soap();
    if (!gerado.s.startsWith('Texto da médica antes.') || !/Refere boa adesão/.test(gerado.s)) throw new Error('a gravação não entrou depois do texto da médica: ' + JSON.stringify(gerado.s));
    const aviso = await ev(`(() => { const n = document.getElementById('rcNote'), b = document.getElementById('rcNoteBtn');
      return { visivel: !n.hidden, texto: document.getElementById('rcNoteT').textContent, desfazer: !b.hidden && b.offsetParent !== null }; })()`);
    if (!aviso.visivel || !/revise na aba SOAP/.test(aviso.texto) || aviso.desfazer) throw new Error('aviso errado: ' + JSON.stringify(aviso));
    await clica('#rcNoteX'); await sleep(400);
    if (!(await ev(`document.getElementById('rcNote').hidden`))) throw new Error('o X não fechou o aviso');
    if (JSON.stringify(await soap()) !== JSON.stringify(gerado)) throw new Error('fechar o aviso mexeu no texto');
    return 'aviso sem Desfazer; o X fecha e o texto fica como estava';
  }],
  ['destaques do player: cada parte do SOAP no trecho de onde veio, com o card, as setas e o Ouvir', async () => {
    await grava('/_preview/pr?pid=9003&ev=evH', 36); await encerra();
    const mks = await ev(`[...document.querySelectorAll('#csPlay .cs-mk')].map((b) => b.title)`);
    if (!mks.length || mks.some((t) => !['Subjetivo', 'Objetivo', 'Avaliação', 'Plano'].includes(t))) throw new Error('destaques: ' + JSON.stringify(mks));
    await clica('#csPlay .cs-mk');
    const card = await ev(`(() => { const p = document.getElementById('csPop'); return p && { t: p.querySelector('.cs-pop-t').textContent, x: p.querySelector('.cs-pop-x').textContent,
      pg: p.querySelector('.cs-pop-pg span').textContent, on: document.querySelector('#csPlay .cs-mk.on') === document.querySelector('#csPlay .cs-mk') }; })()`);
    if (!card || card.t !== mks[0] || !card.x.trim() || card.pg !== '1 / ' + mks.length || !card.on) throw new Error('card: ' + JSON.stringify(card));
    if (mks.length > 1) {
      await clica('#csPop .cs-pop-pg button:last-child');
      if ((await ev(`document.querySelector('#csPop .cs-pop-t').textContent`)) !== mks[1]) throw new Error('a seta não foi ao próximo destaque');
    }
    await clica('#csPop .cs-pop-ouvir'); await sleep(1200);
    const tocando = await ev(`!document.getElementById('csPop') && document.getElementById('rcPlay').getAttribute('aria-label') === 'Pausar'`);
    if (!tocando) throw new Error('Ouvir não fechou o card e tocou');
    await clica('#rcPlay');
    return mks.length + ' destaques (' + mks.join(', ') + '); card, setas e Ouvir ok';
  }],
  ['um trecho que o servidor sempre erra não trava os outros', async () => {
    await srv('/_preview/sim?erro_seq=1');
    await grava('/_preview/pr?pid=9003&ev=evE', 48);
    const seqs = () => estado().then((e) => (Object.values(e.gravacoes)[0] || { trechos: [] }).trechos.map((t) => t.seq));
    const antes = await seqs(), alerta = (await ev(UI)).alerta;
    if (!antes.includes(2) || antes.includes(1)) throw new Error('a fila travou no trecho com erro: ' + JSON.stringify(antes));
    if (!/servidor não conseguiu/.test(alerta) || /Sem internet/.test(alerta)) throw new Error('aviso errado: ' + alerta);
    await srv('/_preview/sim?erro_seq=');
    await ate(`fetch('/_preview/estado').then((r) => r.json()).then((e) => Object.values(e.gravacoes)[0].trechos.some((t) => t.seq === 1))`, 70000, 'o trecho 1 subir depois');
    await encerra();
    return `trechos ${JSON.stringify(antes)} subiram antes; o 1 subiu quando o servidor voltou`;
  }],
  ['sem armazenamento no navegador, os trechos sobem da memória', async () => {
    await abre('/_preview/pr?pid=9003&ev=evF');
    await ev(`sessionStorage.setItem('e2e_sem_idb', '1')`); await send('Page.reload', { ignoreCache: true }); await sleep(500);
    await ate(PE, 20000, 'gravador');
    if (!(await ev(`!!window.__semIdb`))) throw new Error('o armazenamento não foi desligado');
    await grava('', 20);
    await ate(`fetch('/_preview/estado').then((r) => r.json()).then((e) => Object.values(e.gravacoes).some((g) => g.trechos.length))`, 20000, 'trecho subir da memória');
    await encerra();
    return 'trechos enviados sem o IndexedDB';
  }],
  ['trecho recusado aparece como fora da evolução e o Assinar avisa', async () => {
    await srv('/_preview/sim?recusar_seq=1');
    await grava('/_preview/pr?pid=9003&ev=evG', 34); await encerra();
    const a = (await ev(UI)).alerta;
    if (!/trecho da gravação não entrou/.test(a)) throw new Error('sem aviso do trecho que ficou de fora: ' + a);
    await finalizaEvo(); await sleep(600);
    const f = await ev(`(document.getElementById('rcFinal')||{}).textContent || ''`);
    if (!/não entrou na evolução/.test(f)) throw new Error('o Assinar não avisou: ' + f);
    const fins = await ev(`[...document.querySelectorAll('button')].filter((b) => b.getClientRects().length && /Finalizar|Assinar/.test(b.textContent)).map((b) => b.textContent.trim())`);
    if (fins.join() !== 'Assinar') throw new Error('pronta, com o aviso, deveria haver só o Assinar: ' + fins.join(' | '));
    await finalizaEvo();                                                            // o mesmo Assinar assina mesmo assim
    await ate(`fetch('/_preview/estado').then((r) => r.json()).then((e) => Object.values(e.evolucoes).some((n) => n.event_id === 'evG' && n.timing))`, 15000, 'finalizar mesmo assim');
    return a.slice(0, 70) + '… (só o Assinar; o 2º toque assina)';
  }],
  ['microfone mudo: avisa que não ouviu fala e "Gravar de novo" continua a mesma gravação', async () => {
    await abre('/_preview/pr?pid=9003&ev=evM'); await ev(`window.__mic.mode = 'mudo'`);
    await grava('', 5); await fimGravacao();
    await ate(`/Não ouvimos nenhuma fala/.test((document.getElementById('rcAlert') || {}).textContent || '')`, 20000, 'aviso de que não ouviu fala');
    const s = await ev(UI);
    if (!s.botoes.includes('Gravar de novo') || s.botoes.includes('Gerar de novo')) throw new Error('botões: ' + s.botoes.join(' | '));
    if (/transcrição está guardada/.test(s.alerta)) throw new Error('ainda diz que a transcrição está guardada: ' + s.alerta);
    await ev(`window.__mic.mode = 'voz'`);
    await clica('#prRec .cs-go', 'Gravar de novo'); await ate(est('gravando'), 10000, 'gravar de novo'); await sleep(8000);
    await encerra();
    await ate(`fetch('/_preview/estado').then((r) => r.json()).then((e) => Object.values(e.evolucoes).some((n) => n.event_id === 'evM' && n.content.trim()))`,
      15000, 'a evolução gerada depois de gravar de novo ser salva');
    return 'avisou "Não ouvimos nenhuma fala"; gravou de novo e gerou a evolução';
  }],
  ['trocar o paciente da consulta: a gravação vai para o paciente novo e avisa da do anterior', async () => {
    await grava('/_preview/pr?pid=9003&ev=evP', 6);
    await clica('#prRec button[aria-label^="Pausar"]'); await sleep(2500);
    // o paciente do evento foi corrigido (9003 → 9004) e o prontuário reaberto sem recarregar a página
    await ev(`window.__openProntuario({ patient_id: 9004, patient: 'x', from: 'pacientes', event_id: 'evP', title: 'Retorno' })`);
    await ate(`[...document.querySelectorAll('#prRec .cs-go')].some((b) => b.offsetParent !== null && b.textContent.includes('Iniciar consulta'))`,
      15000, 'gravação nova do paciente novo (e não a pausada do anterior)');
    const a = (await ev(UI)).alerta;
    if (!/gravação de outro paciente/.test(a)) throw new Error('sem aviso da gravação do paciente anterior: ' + a);
    await grava('', 20); await encerra();
    await ate(`fetch('/_preview/estado').then((r) => r.json()).then((e) => Object.values(e.evolucoes).some((n) => n.event_id === 'evP' && n.scribe))`,
      15000, 'salvar a evolução gerada');
    const e = await estado(), g = Object.entries(e.gravacoes).filter(([, x]) => x.event_id === 'evP');
    const nova = g.find(([, x]) => x.pid === 9004), velha = g.find(([, x]) => x.pid === 9003);
    if (!nova || nova[1].status !== 'gerada' || !velha || velha[1].status === 'gerada') throw new Error('gravações: ' + JSON.stringify(g));
    const n = Object.values(e.evolucoes).find((x) => x.pid === 9004 && x.event_id === 'evP');
    if (!n || !n.scribe || JSON.stringify(n.scribe.rec_ids) !== JSON.stringify([nova[0]])) throw new Error('evolução do 9004: ' + JSON.stringify(n));
    if (Object.values(e.evolucoes).some((x) => x.pid === 9003 && x.event_id === 'evP')) throw new Error('a evolução foi para o 9003');
    return 'a do 9004 gerou a evolução dele; a do 9003 ficou com ele, pausada';
  }],
  ['consulta com evolução de outro paciente: o servidor recusa a gravação e a tela pausa e avisa', async () => {
    await abre('/_preview/pr?pid=9003&ev=evQ');
    await ate(`!document.querySelector('#prSoap textarea[data-f=s]').readOnly`, 10000, 'prontuário carregado');
    await escreve('s', 'Evolução escrita para a 9003.');
    await ate(`fetch('/_preview/estado').then((r) => r.json()).then((e) => Object.values(e.evolucoes).some((n) => n.pid === 9003 && n.event_id === 'evQ'))`,
      15000, 'salvar a evolução da 9003');
    await ev(`window.__openProntuario({ patient_id: 9004, patient: 'x', from: 'pacientes', event_id: 'evQ', title: 'Retorno' })`);
    await grava('', 3);
    await ate(`${UI}.alerta.includes('outro paciente') && ${UI}.st === 'pausada'`, 45000, 'pausar e avisar depois da recusa do primeiro trecho');
    const g = Object.values((await estado()).gravacoes);
    if (g.length) throw new Error('a gravação entrou na consulta da 9003: ' + JSON.stringify(g));
    const mortos = (await ev(IDB)).filter((x) => x.dead === 409);
    if (!mortos.length) throw new Error('o trecho recusado não ficou marcado');
    return (await ev(UI)).alerta.slice(0, 80);
  }],
  ['consulta da agenda sem paciente ligado: grava, sobe e "Gerar de novo" funciona', async () => {
    await abre('/_preview/pr?pid=9003&ev=evA');
    // da agenda, um evento só com o nome (sem o cadastro ligado): o prontuário acha o paciente ao carregar
    await ev(`window.__openProntuario({ patient: 'Carlos Eduardo Nunes', from: 'agenda', event_id: 'evN', title: 'Retorno' })`);
    await grava('', 20);
    await srv('/_preview/sim?ia=off'); await fimGravacao();
    await ate(`${UI}.botoes.includes('Gerar de novo')`, 40000, 'a geração falhar (IA fora)');
    await srv('/_preview/sim?ia=on');
    await clica('#prRec .cs-go', 'Gerar de novo');
    await ate(est('pronta'), 60000, 'evolução pronta depois do Gerar de novo');
    const g = Object.values((await estado()).gravacoes);
    if (g.length !== 1 || g[0].pid !== 9004 || g[0].status !== 'gerada' || !g[0].trechos.length) throw new Error('gravação: ' + JSON.stringify(g));
    const ruins = (await ev(IDB)).filter((x) => x.dead || !x.pid);
    if (ruins.length) throw new Error('trecho recusado ou sem paciente: ' + JSON.stringify(ruins));
    return `${g[0].trechos.length} trechos no paciente 9004; gerou de novo`;
  }],
  ['gravação desligada na conta: o áudio guardado há mais de 48 h sai do computador', async () => {
    await ev(`(async () => { const q = indexedDB.open('od_gravacao_00000000-0000-0000-0000-000000000000', 1);
      q.onupgradeneeded = () => q.result.createObjectStore('seg', { keyPath: 'k' });
      const db = await new Promise((ok) => { q.onsuccess = () => ok(q.result); });
      await new Promise((ok) => { const t = db.transaction('seg', 'readwrite'), st = t.objectStore('seg');
        st.put({ k: 'velho:1', rk: 'eevR|9003', recId: 'velho', seq: 1, pid: 9003, created: Date.now() - 49 * 3600e3 });
        st.put({ k: 'novo:1', rk: 'eevR|9003', recId: 'novo', seq: 1, pid: 9003, created: Date.now() - 3600e3 });
        t.oncomplete = ok; });
      db.close(); return 1; })()`);
    await srv('/_preview/sim?gravacao=off');
    await send('Page.navigate', { url: BASE + '/_preview/pr?pid=9003&ev=evR' });
    await ate(`${IDB}.then((l) => l.length && !l.some((x) => x.k === 'velho:1'))`, 15000, 'apagar o áudio de mais de 48 h');
    const l = await ev(IDB);
    if (!l.some((x) => x.k === 'novo:1')) throw new Error('apagou o áudio de menos de 48 h');
    return 'o de 49 h saiu; o de 1 h ficou';
  }],
  ['a Análise (o gráfico e a tabela) fica na aba Análise do painel do Resumo; sem a aba Análise do prontuário e sem os cartões de cima', async () => {
    await send('Page.navigate', { url: BASE + '/_preview/pr?pid=9001&exemplo=1&tab=geral' });
    await ate(`!!document.querySelector('#prTabs [data-tab=geral].on') && !document.querySelector('.pr-panel[data-panel=geral]').hidden`, 20000, 'a aba Resumo');
    await ate(`document.querySelectorAll('#csTable tr').length > 1`, 10000, 'os sinais por consulta desenhados');
    await ev(`document.querySelector('#ovcTabs [data-ct=ana]').click(); 1`);      // a Análise é a última aba do painel
    await ate(`!document.getElementById('ovTop').hidden && !document.getElementById('ovChart').hidden && document.getElementById('ovChart').getClientRects().length > 0`, 10000, 'o gráfico visível na aba Análise');
    // no alto da aba, o resumo da análise (como o parágrafo dos pontos), calculado aqui; embaixo dele, o "Por que … · Perguntar ao assistente"
    const ar = await ev(`(() => { const r = document.getElementById('anaRes'), w = document.getElementById('gqWhy'), p = document.getElementById('anaResP');
      return { vis: r.getClientRects().length > 0, t: r.querySelector('.ovc-ptt').textContent, p: p.textContent,
        antes: !!(r.compareDocumentPosition(document.getElementById('ovTop')) & Node.DOCUMENT_POSITION_FOLLOWING),
        why: r.contains(w) && !document.getElementById('ovTop').contains(w) && !w.hidden && w.getBoundingClientRect().top >= p.getBoundingClientRect().bottom,
        whyT: document.getElementById('gqWhyT').textContent, linhas: document.getElementById('gqWhyT').getClientRects().length && Math.round(document.getElementById('gqWhyT').getBoundingClientRect().height / 22) }; })()`);
    if (!ar.vis || ar.t !== 'Resumo da análise' || !/^Dos \d+ .+ com faixa de referência, (\d+ (está|estão)|nenhum está) na referência/.test(ar.p)
        || !/Desde a primeira medida, (melhorou|melhoraram) /.test(ar.p) || !/A maior variação foi d(o|a|os) .+: de .+ para .+ em \d+ (dias?|mês|meses|anos)\./.test(ar.p) || !ar.antes
        || /\.\./.test(ar.p) || /Glicemia|Temp\.|Creat\./.test(ar.p) || /^Dos 1 /.test(ar.p)
        || !ar.why || !/^Qual o risco (cardiometabólico|renal|cardiometabólico e renal) e o que priorizar\?$/.test(ar.whyT) || ar.linhas !== 1)
      throw new Error('resumo da análise: ' + JSON.stringify(ar));
    // momentos importantes (como no Finance): halo laranja só onde o tratamento mudou ou entrou um diagnóstico; sem o chip em cima;
    // passar o mouse na bolinha mostra o cartão do momento junto dela (a data e o que aconteceu); sair, some
    await ate(`document.querySelectorAll('#ovSvg [data-mom]').length > 0`, 8000, 'os momentos importantes no gráfico');
    const mo = await ev(`(() => { const svg = document.getElementById('ovSvg'), plot = document.getElementById('ovPlot'), n0 = svg.querySelectorAll('[data-mom]').length,
        c = svg.querySelector('[data-mom="0"]').getBoundingClientRect(), cx = c.left + c.width / 2, cy = c.top + c.height / 2;
      plot.dispatchEvent(new MouseEvent('mousemove', { clientX: cx, clientY: cy, bubbles: true }));
      const card = document.getElementById('gqMomC'), aberto = !card.hidden, itens = (card.querySelector('.cs-pop-x') || {}).textContent ? 1 : 0,
        ver = [...card.querySelectorAll('button')].some((b) => b.textContent === 'Ver evolução'), pg = (card.querySelector('.cs-pop-pg span') || {}).textContent,
        forte = svg.querySelector('[data-mom="0"]').getAttribute('fill-opacity'), cr = card.getBoundingClientRect(), perto = Math.abs(cr.left + cr.width / 2 - cx) < 140 || cr.left < cx;
      plot.dispatchEvent(new MouseEvent('mouseleave', { bubbles: false })); plot.dispatchEvent(new Event('mouseleave'));
      return { n0, aberto, itens, ver, pg, forte, perto, fechou: card.hidden, chip: !!document.getElementById('gqMom'), h: Math.round(svg.getBoundingClientRect().height),
        pts: svg.querySelectorAll('circle[r="3"]').length, marca: document.querySelectorAll('#ovRanges button.mom').length }; })()`);
    if (!(mo.n0 > 0 && mo.n0 < 8) || !mo.aberto || !mo.itens || !mo.ver || mo.pg !== '1 / ' + mo.n0 || mo.forte !== '0.38' || !mo.perto || !mo.fechou || mo.chip
        || mo.h !== 240 || mo.pts !== 0 || !mo.marca) throw new Error('momentos importantes: ' + JSON.stringify(mo));
    // as setas do cartão andam só pelos momentos do gráfico e o cartão fica (ele muda de lugar; o cursor não precisa ir junto);
    // sair da bolinha fecha com uma folga (dá para chegar ao cartão); sair do gráfico fecha na hora
    const sm = await ev(`(async () => { const svg = document.getElementById('ovSvg'), plot = document.getElementById('ovPlot'), card = document.getElementById('gqMomC'),
        n0 = svg.querySelectorAll('[data-mom]').length, c = svg.querySelector('[data-mom="0"]').getBoundingClientRect(), r = plot.getBoundingClientRect(),
        bola = { clientX: c.left + c.width / 2, clientY: c.top + c.height / 2, bubbles: true }, vazio = { clientX: r.right - 4, clientY: r.top + 4, bubbles: true },
        espera = (ms) => new Promise((ok) => setTimeout(ok, ms)), pg = () => card.hidden ? 'fechado' : (card.querySelector('.cs-pop-pg span') || {}).textContent;
      plot.dispatchEvent(new MouseEvent('mousemove', bola)); plot.dispatchEvent(new MouseEvent('mousemove', vazio));
      const folga = pg(); await espera(350); const fechou = pg();
      plot.dispatchEvent(new MouseEvent('mousemove', bola)); const lugar = card.style.left + card.style.top;
      card.querySelector('.cs-pop-pg button:last-child').click(); const seta = pg(), parado = card.style.left + card.style.top === lugar;
      plot.dispatchEvent(new MouseEvent('mousemove', vazio)); await espera(350); const fixo = pg();
      plot.dispatchEvent(new Event('mouseleave')); return { n0, folga, fechou, seta, parado, fixo, saiu: pg() }; })()`);
    if (sm.folga !== '1 / ' + sm.n0 || sm.fechou !== 'fechado' || sm.saiu !== 'fechado'
        || (sm.n0 > 1 && (sm.seta !== '2 / ' + sm.n0 || !sm.parado || sm.fixo !== '2 / ' + sm.n0))) throw new Error('setas e folga do cartão do momento: ' + JSON.stringify(sm));
    // a pergunta é do paciente inteiro (não de um sinal): o caso completo, sem o nome, e o pedido de avaliação integrada; só preenche
    await ev(`document.getElementById('gqWhy').click(); 1`);
    const aq = await ev(`(() => { const i = document.getElementById('biInput'), v = i.value, nm = document.getElementById('prName').textContent.trim();
      i.value = ''; i.dispatchEvent(new Event('input', { bubbles: true })); return { v, nm }; })()`);
    const nomeNa = (txt, nm) => nm.split(/\s+/).filter((w) => w.length > 2).some((w) => new RegExp('(^|[^\\p{L}])' + w + '($|[^\\p{L}])', 'iu').test(txt));
    if (!/^(Mulher|Homem|Paciente) de \d+ anos/.test(aq.v) || !/Diagnósticos registrados nas evoluções: /.test(aq.v) || !/Últimos (sinais vitais|exames): /.test(aq.v)
        || !/Fora da faixa de referência: .+\. Faça uma avaliação integrada do caso: /.test(aq.v) || /^Por que|caiu \d/.test(aq.v) || !/intervalo de retorno\.$/.test(aq.v) || aq.v.length > 2000 || !aq.nm || nomeNa(aq.v, aq.nm))
      throw new Error('a pergunta geral ao assistente: ' + JSON.stringify({ nm: aq.nm, n: aq.v.length, v: aq.v.slice(0, 400) }));
    const r = await ev(`(() => { const g = document.querySelector('.pr-panel[data-panel=geral]');
      return { abas: [...document.querySelectorAll('#prTabs [data-tab]')].map((b) => b.dataset.tab).join(), painelAnalise: !!document.querySelector('.pr-panel[data-panel=analise]'),
               dentro: ['ovTop', 'gaTable', 'csSinais'].every((i) => g.contains(document.getElementById(i))) && !document.getElementById('gaFuSec'), vazioRepetido: !!document.getElementById('gaEmpty'),
               titulo: !!document.querySelector('#ovcP-ana #ovAnaSec #ovTop') && !document.querySelector('#ovAnaSec > .ov-h') ? 'Análise' : 'fora da aba',
               // saíram do Resumo os cards de sinais vitais e de exames (as Evoluções recentes e os laudos voltam como abas do painel)
               sairam: ['ovTilesWrap', 'ovLabWrap', 'ovLabTiles', 'ovFeedSec', 'ovPanSec', 'ovDxSec'].filter((i) => document.getElementById(i)).join() }; })()`);
    if (r.abas !== 'geral,atual,prescricoes' || r.painelAnalise || !r.dentro || r.vazioRepetido || r.titulo !== 'Análise' || r.sairam) throw new Error('o Resumo junto: ' + JSON.stringify(r));
    // saíram os cartões de cima: "Faixa no período" e "Sinais e exames na referência" (a rosca e o Perguntar ao assistente)
    if (await ev(`['gaCards', 'gaDonut', 'gaAsk', 'gaBars', 'gaSee'].some((i) => document.getElementById(i))`)) throw new Error('os cartões de cima ainda estão na página');
    return 'a Análise (gráfico e tabela) na aba Análise do painel, sem os cartões de cima';
  }],
  ['o painel do Resumo como a Visão geral do Google Finance: Resumo clínico (pontos, diagnósticos, medicações e alergias), Análise, Evoluções, Exames, Consultas e Prescrições; 40 px em cima e embaixo; sem a aba Histórico', async () => {
    await send('Page.navigate', { url: BASE + '/_preview/pr?pid=9001&exemplo=1&tab=geral' });
    await ate(`!document.getElementById('ovComp').hidden && document.querySelectorAll('#ovDx .ov-dxrow').length > 0`, 20000, 'o painel com os diagnósticos');
    const aba = (t) => ev(`(() => { document.querySelector('#ovcTabs [data-ct=${t}]').click(); return [...document.querySelectorAll('#ovComp .ovc-panel')].filter((p) => !p.hidden).map((p) => p.dataset.cp).join(); })()`);
    // no Resumo clínico, a lista dos Diagnósticos: (o código |) o nome | a linha de baixo
    const lista = (sel) => `[...document.querySelectorAll('${sel} .ov-dxrow')].map((x) => [x.querySelector('.ov-dxcode'), x.querySelector('.ov-dxdesc b'), x.querySelector('.ov-dxdesc small')].filter(Boolean).map((y) => y.textContent).join('|'))`;
    const p = await ev(`(() => ({
      abas: [...document.querySelectorAll('#ovcTabs [role=tab]')].map((b) => b.textContent + (b.getAttribute('aria-selected') === 'true' ? '*' : '')).join(),
      visiveis: [...document.querySelectorAll('#ovComp .ovc-panel')].filter((x) => !x.hidden).map((x) => x.dataset.cp).join(),
      semHistorico: !document.querySelector('.pr-panel[data-panel=consultas]') && !document.querySelector('#prTabs [data-tab=consultas]'),
      dx: ${lista('#ovDx')}, linha: (() => { const x = document.querySelector('#ovDx .ov-dxrow').getBoundingClientRect(); return Math.round(x.height); })(),
      acessos: !document.getElementById('prAccess') && !document.getElementById('prAccessList') }))()`);   // o registro de acessos saiu da tela (o servidor continua registrando)
    if (p.abas !== 'Resumo*,Análise,Evoluções,Consultas,Prescrições' || p.visiveis !== 'sum' || !p.semHistorico || !p.acessos
        || !p.dx.length || !p.dx.every((x) => /^[^|]+\|[A-Z]\d{2}(\.\d+)? · Última vez em \d/.test(x)) || p.linha < 60) throw new Error('painel: ' + JSON.stringify(p));
    // alinhado: os nomes, o texto dos pontos, o cartão e os títulos começam na mesma borda; o bloco dos pontos e as linhas vão até a mesma borda direita
    const al = await ev(`(() => { const P = document.getElementById('ovcP-sum'), b = P.getBoundingClientRect(), x = (e) => Math.round(e.getBoundingClientRect().left - b.left), r = (e) => Math.round(b.right - e.getBoundingClientRect().right);
      const nomes = [...P.querySelectorAll('#ovcSumGrid .ov-dxdesc b')].filter((n) => n.getClientRects().length).map(x);
      return { nomes: [...new Set(nomes)], texto: x(document.getElementById('ovcPP')), titulos: [...new Set([...P.querySelectorAll('.ovc-st')].map(x))],
               dir: [...new Set([P.querySelector('#ovDx .ov-dxrow'), P.querySelector('.pr-sumcol .ov-dxrow')].map(r))] }; })()`);
    if (al.nomes.join() !== '0' || al.texto !== 0 || al.titulos.join() !== '0' || al.dir.join() !== '0') throw new Error('alinhamento do Resumo clínico: ' + JSON.stringify(al));
    // Resumo clínico em seções com título: Diagnósticos, Medicações em uso, Alergias (sem Problemas ativos e sem Evoluções recentes)
    const secoes = await ev(`[...document.querySelectorAll('#ovcSumGrid .ovc-st')].map((t) => t.textContent).join()`);
    if (secoes !== 'Diagnósticos,Medicações em uso,Alergias' || await ev(`!!document.querySelector('#ovcSumGrid [data-k=problems]') || !!document.querySelector('#sumAddTipo option[value=problems]')`)) throw new Error('as seções do Resumo clínico: ' + secoes);
    // nas três abas com texto no alto: 40 px da barra de abas ao título e 40 px do último item até a linha; no Resumo clínico a linha
    // fica logo abaixo do parágrafo, e o cartão começa 40 px depois dela
    const esp = await ev(`(() => { const R = (x) => x.getBoundingClientRect(), era = document.querySelector('#ovcTabs .ovc-tab[aria-selected=true]').dataset.ct, o = {};
      for (const [t, id, ult] of [['sum', 'ovcPersp', 'ovcPP'], ['ana', 'anaRes', 'gqWhy'], ['evo', 'evoRes', 'evoResP']]) {
        document.querySelector('#ovcTabs [data-ct=' + t + ']').click();
        const b = document.getElementById(id), u = document.getElementById(ult), barra = R(document.querySelector('.ovc-tabw')).bottom;
        const lb = t === 'ana' ? document.getElementById('hxExames') : b, lu = t === 'ana' ? lb.querySelector('.ex-gb') : u;   // na Análise a linha fica embaixo do Anexar exame
        const linha = t === 'sum' ? R(u).bottom : R(lb).bottom, fimU = t === 'sum' ? R(u).bottom - parseFloat(getComputedStyle(u).paddingBottom) - parseFloat(getComputedStyle(u).borderBottomWidth) : R(lu).bottom;
        o[t] = [Math.round(R(b.querySelector('.ovc-ptt')).top - barra), Math.round(linha - fimU - 1)];
        if (t === 'sum') o.cartao = Math.round(R(document.querySelector('#ovcPan .gpan-cols')).top - linha);   // as colunas dos pontos, 40 depois da linha
      }
      document.querySelector('#ovcTabs [data-ct=' + era + ']').click(); return o; })()`);
    if (['sum', 'ana', 'evo'].some((t) => esp[t][0] !== 40 || esp[t][1] !== 40) || esp.cartao !== 40) throw new Error('os espaços das abas (título, linha): ' + JSON.stringify(esp));
    // os 3 botões do topo: o texto e até 52 px de cada lado; a pílula na aba escolhida
    const nav = await ev(`(() => { const n = document.getElementById('prTabs'), on = n.querySelector('button.on').getBoundingClientRect(), pl = n.querySelector('.pr-nav-pill').getBoundingClientRect();
      return { pads: [...n.querySelectorAll('button')].map((b) => { const r = document.createRange(); r.selectNodeContents(b); const t = r.getBoundingClientRect(), x = b.getBoundingClientRect(); return [Math.round(t.left - x.left), Math.round(x.right - t.right)]; }),
        pilula: Math.abs(pl.left - on.left) < 1 && Math.abs(pl.width - on.width) < 1, cabe: n.getBoundingClientRect().width <= n.parentElement.getBoundingClientRect().width + 0.5 }; })()`);
    if (!nav.pilula || !nav.cabe || nav.pads.some(([l, r]) => l > 52 || r > 52 || l < 6 || Math.abs(l - r) > 1)) throw new Error('os botões do topo: ' + JSON.stringify(nav));
    const topo1 = await ev(`Math.round(parseFloat(getComputedStyle(document.querySelector('#ovcSumGrid .ovc-st')).paddingTop))`);
    // a linha embaixo dos pontos, 40 px depois das colunas, e Diagnósticos 40 px abaixo dela
    const lp = await ev(`(() => { const R = (x) => x.getBoundingClientRect(), p = document.getElementById('ovcPersp'); return [getComputedStyle(p).borderBottomWidth,
      Math.round(R(p).bottom - 1 - R(document.querySelector('#ovcPan .gpan-cols')).bottom)]; })()`);
    if (topo1 !== 40 || lp[0] !== '1px' || lp[1] !== 40) throw new Error('a linha entre os pontos e Diagnósticos: ' + JSON.stringify([topo1, lp]));
    // os pontos ficam sempre abertos (sem a seta de abrir/fechar): o título, o texto, a barra (na referência / melhorando / fora) e as duas colunas
    const a = await ev(`(() => ({ vis: !document.getElementById('ovcPersp').hidden, aberto: !document.getElementById('ovcPan').hidden && document.getElementById('ovcPan').getClientRects().length > 0,
      seta: !!document.querySelector('#ovcPersp button, #ovcPersp .ovc-chev'), titulo: document.querySelector('#ovcPersp .ovc-ptt').textContent,
      texto: document.getElementById('ovcPP').textContent, barra: document.querySelectorAll('#ovcBar, #ovcRef').length,
      pos: document.querySelectorAll('#ovPanPos li').length, neg: document.querySelectorAll('#ovPanNeg li').length }))()`);
    if (!a.vis || !a.aberto || a.seta || a.titulo !== 'Pontos positivos e de atenção' || !/^Na última medida de .+ na referência/.test(a.texto) || a.barra !== 0
        || !a.pos || !a.neg) throw new Error('pontos: ' + JSON.stringify(a));
    // a linha dos pontos fica só na aba Resumo clínico
    if (await ev(`(() => { document.querySelector('#ovcTabs [data-ct=cs]').click(); const n = document.getElementById('ovcPersp').getClientRects().length; document.querySelector('#ovcTabs [data-ct=sum]').click(); return n || !document.querySelector('#ovcP-sum #ovcPersp'); })()`)) throw new Error('a linha dos pontos aparece fora do Resumo clínico');
    // as setas do teclado trocam de aba (e o foco vai junto)
    await ev(`(() => { const b = document.querySelector('#ovcTabs [data-ct=sum]'); b.focus(); b.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })); return 1; })()`);
    const k1 = await ev(`document.activeElement.dataset.ct + ':' + document.querySelector('#ovcTabs .on').dataset.ct`);
    await ev(`document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true })); 1`);
    const k2 = await ev(`document.activeElement.dataset.ct + ':' + [...document.querySelectorAll('#ovComp .ovc-panel')].filter((x) => !x.hidden).map((x) => x.dataset.cp).join()`);
    if (k1 !== 'ana:ana' || k2 !== 'med:med') throw new Error('teclado nas abas: ' + k1 + ' / ' + k2);
    // Resumo clínico: o tipo à esquerda e o item à direita; o × tira, o "+ Adicionar" põe (salvos no paciente)
    if (await aba('sum') !== 'sum') throw new Error('a aba Resumo clínico não abriu sozinha');
    const rs = await ev(lista('#ovcP-sum .pr-sumcol'));      // só o nome: o tipo é o título da seção
    if (!rs.join(';').startsWith('Losartana 50 mg 12/12h') || !rs.join(';').endsWith('Dipirona;Penicilina') || !rs.includes('Losartana 50 mg 12/12h')
        || await ev(`[...document.querySelectorAll('#ovcP-sum .pr-sumcol .ov-dxrow')].some((x) => !x.querySelector('.ovc-x') || x.querySelector('small'))`)) throw new Error('Resumo clínico: ' + rs.join('; '));
    const alergias = `[...document.querySelectorAll('.pr-sumcol[data-k=allergies] .ov-dxdesc b')].map((b) => b.textContent).join()`;
    await ev(`document.querySelector('.pr-sumcol[data-k=allergies] .ov-dxrow:last-child .ovc-x').click(); 1`);
    await ate(`${alergias} === 'Dipirona'`, 5000, 'tirar a Penicilina');
    if (!await ev(`[...document.querySelectorAll('.pr-desfaz')].some((t) => /Alergia removida: Penicilina/.test(t.textContent) && /Desfazer/.test(t.textContent))`))
      throw new Error('tirar a alergia não mostrou o aviso com Desfazer');
    await sleep(800); if (await ev(alergias) !== 'Dipirona') throw new Error('o servidor não salvou a remoção');   // (se falhar, a página volta o item)
    await ev(`document.getElementById('sumAddBtn').click(); 1`);
    if (await ev(`document.getElementById('sumAdd').hidden || document.activeElement.id !== 'sumAddIn' || document.getElementById('sumAddBtn').getAttribute('aria-expanded') !== 'true'`))
      throw new Error('o "+ Adicionar" não abriu a linha com o cursor no nome');
    await ev(`(() => { const t = document.getElementById('sumAddTipo'); t.value = 'allergies'; t.dispatchEvent(new Event('change')); const i = document.getElementById('sumAddIn'); i.value = 'Penicilina';
      i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); return 1; })()`);
    await ate(`${alergias} === 'Dipirona,Penicilina' && document.getElementById('prAllergyTxt').textContent === 'Alergias: Dipirona, Penicilina' && !document.getElementById('sumAdd').hidden`, 5000, 'pôr a Penicilina de volta (a linha continua aberta)');
    await sleep(800); if (await ev(alergias) !== 'Dipirona,Penicilina') throw new Error('o servidor não salvou a alergia nova');
    await ev(`document.getElementById('sumAddIn').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); 1`);
    if (await ev(`!document.getElementById('sumAdd').hidden || document.getElementById('sumAddBtn').getAttribute('aria-expanded') !== 'false'`)) throw new Error('o Esc não fechou o "+ Adicionar"');
    // Exames (a aba saiu): o "Anexar exame" e a lista dos laudos anexados (Abrir, Ler valores, Excluir) na Análise, antes do gráfico
    await aba('ana');
    await ate(`!!document.querySelector('#ovcP-ana #hxExames #ovFiles') && document.querySelectorAll('#ovFiles .gx-row').length > 0 && document.getElementById('hxExames').getClientRects().length > 0`, 10000, 'os laudos na Análise');
    const acoes = await ev(`[...document.querySelectorAll('#ovFiles .gx-row')[0].querySelectorAll('.gx-acts > *')].map((b) => b.textContent).join()`);
    if (acoes !== 'Abrir,Ler valores,Excluir') throw new Error('ações do laudo: ' + acoes);
    const so = await ev(`(() => { const p = document.getElementById('ovcP-ana'), hx = document.getElementById('hxExames'); return { semAba: !document.querySelector('#ovcTabs [data-ct=ex]') && !document.getElementById('ovcP-ex'),
      anexar: !!hx.querySelector('[data-attach]'), antes: hx.parentElement === p && !!(hx.compareDocumentPosition(document.getElementById('ovAnaSec')) & Node.DOCUMENT_POSITION_FOLLOWING),
      gap: Math.round(document.getElementById('ovAnaSec').getBoundingClientRect().top - hx.getBoundingClientRect().bottom) }; })()`);
    if (!so.semAba || !so.anexar || !so.antes || so.gap !== 40) throw new Error('os exames na Análise, antes do gráfico: ' + JSON.stringify(so));
    // Evoluções: os sinais e exames por consulta (o gráfico de barras na largura da aba e a tabela), que saíram da Análise
    if (await aba('evo') !== 'evo') throw new Error('a aba Evoluções não abriu sozinha');
    // no alto, o resumo das evoluções (como o parágrafo dos pontos), calculado aqui
    const er = await ev(`(() => ({ vis: document.getElementById('evoRes').getClientRects().length > 0, t: document.querySelector('#evoRes .ovc-ptt').textContent,
      p: document.getElementById('evoResP').textContent, antes: !!(document.getElementById('evoRes').compareDocumentPosition(document.getElementById('csSinais')) & Node.DOCUMENT_POSITION_FOLLOWING) }))()`);
    if (!er.vis || er.t !== 'Resumo das evoluções' || !/^\d+ evoluções de [a-z]{3} \d{4} a [a-z]{3} \d{4}; a última em \d{1,2} [a-z]{3} \d{4}/.test(er.p)
        || !/Diagnósticos mais registrados: .+ em \d+ evoluç(ão|ões)/.test(er.p) || /\)\s*\(/.test(er.p) || !/No período, a pressão arterial foi de \d+\/\d+ para \d+\/\d+ mmHg/.test(er.p) || !er.antes) throw new Error('resumo das evoluções: ' + JSON.stringify(er));
    await ate(`document.querySelectorAll('#csSvg rect').length > 0 && document.getElementById('csSvg').getBoundingClientRect().width > 200`, 5000, 'o gráfico das consultas na aba');
    const cs = await ev(`(() => ({ aqui: !!document.querySelector('#ovcP-evo #csSinais #csChart') && !document.querySelector('#ovAnaSec #csSinais'),
      linhas: document.querySelectorAll('#csTable tr').length, larg: Math.round(document.getElementById('csSvg').getBoundingClientRect().width),
      painel: Math.round(document.getElementById('ovcP-evo').getBoundingClientRect().width),
      vb: Math.round(document.getElementById('csSvg').viewBox.baseVal.width), cw: document.getElementById('csSvg').clientWidth }))()`);
    // desenhado na largura da aba (não na de reserva, 540, de quando a aba estava escondida)
    if (!cs.aqui || cs.linhas < 2 || cs.larg < cs.painel - 80 || Math.abs(cs.vb - cs.cw) > 1) throw new Error('Evoluções: ' + JSON.stringify(cs));
    // Medicamentos: o histórico de receitas (saiu da aba Prescrições)
    if (await aba('med') !== 'med') throw new Error('a aba Prescrições não abriu sozinha');
    const md = await ev(`(() => ({ aqui: !!document.querySelector('#ovcP-med #rhBox #rhList'), visivel: document.getElementById('rhBox').getClientRects().length > 0,
      naPresc: !!document.querySelector('.pr-panel[data-panel=prescricoes] #rhBox'), cabecalho: !!document.querySelector('#rhBox .pr-histbar') || !!document.getElementById('rhQ') }))()`);
    if (!md.aqui || !md.visivel || md.naPresc || md.cabecalho) throw new Error('Prescrições: ' + JSON.stringify(md));
    // duas tabelas: os medicamentos em uso (os do resumo clínico, com a posologia da última receita) e o histórico
    const t2 = await ev(`(() => ({ r1: (document.querySelector('#rmList .pr-tgroup') || {}).textContent, r2: (document.querySelector('#rhList .pr-tgroup') || {}).textContent,
      uso: [...document.querySelectorAll('#rmList .rh-item')].map((r) => r.querySelector('.pr-tdate').firstChild.textContent + '|' + r.querySelector('.rh-pos').textContent),
      meds: document.querySelectorAll('.pr-sumcol[data-k=medications] .ov-sumrow:not(.none)').length }))()`);
    if (t2.r1 !== 'Medicamentos em uso' || t2.r2 !== 'Histórico' || t2.uso.length !== t2.meds || !t2.uso.length || !t2.uso.some((x) => /^Losartana 50 mg\|.*12\/12/.test(x)))
      throw new Error('as duas tabelas das Prescrições: ' + JSON.stringify(t2));
    // Consultas: a linha de uma evolução finalizada abre o cartão dela
    await aba('cs');
    await ev(`document.querySelector('#ovcP-cs #prVisits .pr-trow[aria-expanded]').click(); 1`);
    await ate(`!!document.querySelector('#ovcP-cs #prVisits .pr-item.hc') && !document.getElementById('ovcP-cs').hidden`, 5000, 'o cartão da evolução em Consultas');
    if (await ev(`!!document.getElementById('ovFeed') || [...document.querySelectorAll('#ovcSumGrid .ovc-st')].some((t) => t.textContent === 'Evoluções recentes')`)) throw new Error('a lista Evoluções recentes ainda está no Resumo clínico');
    // Consultas: a lista (com a busca) que era do Histórico
    if (await ev(`document.querySelectorAll('#ovcP-cs #prVisits .pr-trow').length < 2 || !!document.querySelector('#ovcP-cs #prHistQ')`)) throw new Error('a lista de Consultas não está na aba (ou a busca voltou)');
    // as setas das abas: só quando as abas não cabem, e só do lado onde há mais abas
    const s2 = await ev(`(() => { const b = document.getElementById('ovcTabs'); return { cabe: b.scrollWidth <= b.clientWidth + 1, l: !document.getElementById('ovcScL').hidden, r: !document.getElementById('ovcScR').hidden, x: b.scrollLeft, max: b.scrollWidth - b.clientWidth }; })()`);
    if (s2.cabe ? (s2.l || s2.r) : ((s2.l !== (s2.x > 1)) || (s2.r !== (s2.x < s2.max - 1)))) throw new Error('setas das abas: ' + JSON.stringify(s2));
    return `${p.dx.length} diagnósticos, pontos (${a.pos} positivos, ${a.neg} de atenção), ${rs.length} itens do resumo, laudos (${acoes}); tirar/pôr alergia salvo; teclado e setas${s2.cabe ? ' (as abas cabem)' : ''}`;
  }],
  ['a paciente de exemplo continua com a demonstração', async () => {
    await send('Page.navigate', { url: BASE + '/_preview/pr?pid=9001&ev=evnext' });
    await ate(`[...document.querySelectorAll('#prRec .cs-go')].some((b) => b.offsetParent !== null && !b.disabled)`, 20000, 'gravador');
    await sleep(1500);                                                              // (a gravação real, se fosse ligar, já teria aparecido)
    if (await ev(`!!document.querySelector('#prRec .cs-nota')`)) throw new Error('não está na demonstração');
    await clica('#prRec .cs-go', 'Iniciar consulta');
    await ate(`/dona Maria/.test(document.getElementById('rcTx').textContent)`, 15000, 'o roteiro da demonstração');
    if (await ev(`window.__mic.tracks.length`)) throw new Error('a demonstração ligou o microfone');
    await clica('#prRec .cs-stop[aria-label="Pausar a gravação"]');
    return 'demonstração (roteiro fictício, sem microfone)';
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
    navigator.mediaDevices.getUserMedia = async (c) => {                    // fala sintética: 3,2 s de som e 0,8 s de pausa
      const ex = c && c.audio && c.audio.deviceId && c.audio.deviceId.exact;
      if (window.__foneDesligado && ex === 'fone-bt') throw new DOMException('Requested device not found', 'OverconstrainedError');
      const ac = new AudioContext(), dst = ac.createMediaStreamDestination(), sr = ac.sampleRate, len = Math.round(sr * 4);
      const buf = ac.createBuffer(1, len, sr), d = buf.getChannelData(0); let s = 7;
      const mudo = window.__mic.mode === 'mudo';                             // microfone que só entrega silêncio
      for (let i = 0; i < len; i++) { s = (s * 16807) % 2147483647; d[i] = !mudo && i < sr * 3.2 ? (s / 2147483647 - 0.5) * 0.5 * (0.6 + 0.4 * Math.sin(i / sr * 25)) : 0; }
      const src = ac.createBufferSource(); src.buffer = buf; src.loop = true; src.connect(dst); src.start();
      const t = dst.stream.getAudioTracks()[0]; t.getSettings = () => ({ deviceId: window.__foneDesligado ? 'embutido' : 'fone-bt' });
      window.__mic.tracks.push(t); return dst.stream;
    };
    navigator.mediaDevices.enumerateDevices = async () => [{ kind: 'audioinput', deviceId: 'teste1', label: 'Microfone de teste', groupId: 'g' }];
    try { if (sessionStorage.getItem('e2e_sem_idb')) {                      // simula disco cheio: o IndexedDB não abre
      window.__semIdb = true;
      indexedDB.open = function () { const r = {}; setTimeout(() => { r.error = new Error('cota'); r.onerror && r.onerror(); }, 0); return r; };
    } } catch (_) {}
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
      if (process.env.FOTOS) try { const f = await send('Page.captureScreenshot', { format: 'png' });
        (await import('node:fs')).writeFileSync(join(process.env.FOTOS, `cenario-${i + 1}.png`), Buffer.from(f.data, 'base64')); } catch (_) {}
    }
  }
  if (erros.length) { falhas++; log('✗ erros de JavaScript na página:\n  ' + erros.join('\n  ')); }
  log(falhas ? `\n${falhas} falha(s)` : '\ntudo certo');
  return falhas;
}
main().then((f) => { fim(); process.exit(f ? 1 : 0); }, (e) => { console.error('erro:', e.message); fim(); process.exit(2); });
