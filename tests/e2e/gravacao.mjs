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
// .cs-msg na barra; pronta, o player (#csPlay); o Finalizar da evolução flutua (#csFlut .cs-fim). Não há marca de autorização:
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
const finalizaEvo = () => clica('#csFlut .cs-fim', 'Finalizar');         // pronta: o Finalizar que flutua no pé finaliza a evolução
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
    if (await ev(`!document.getElementById('rcFinal').hidden`)) await finalizaEvo();   // com o aviso na tela, o 2º Finalizar finaliza
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
  ['trecho recusado aparece como fora da evolução e o Finalizar avisa', async () => {
    await srv('/_preview/sim?recusar_seq=1');
    await grava('/_preview/pr?pid=9003&ev=evG', 34); await encerra();
    const a = (await ev(UI)).alerta;
    if (!/trecho da gravação não entrou/.test(a)) throw new Error('sem aviso do trecho que ficou de fora: ' + a);
    await finalizaEvo(); await sleep(600);
    const f = await ev(`(document.getElementById('rcFinal')||{}).textContent || ''`);
    if (!/não entrou na evolução/.test(f)) throw new Error('o Finalizar não avisou: ' + f);
    const fins = await ev(`[...document.querySelectorAll('button')].filter((b) => b.getClientRects().length && /Finalizar/.test(b.textContent)).map((b) => b.textContent.trim())`);
    if (fins.join() !== 'Finalizar') throw new Error('com o aviso, deveria haver um Finalizar só: ' + fins.join(' | '));
    await finalizaEvo();                                                            // o mesmo Finalizar finaliza mesmo assim
    await ate(`fetch('/_preview/estado').then((r) => r.json()).then((e) => Object.values(e.evolucoes).some((n) => n.event_id === 'evG' && n.timing))`, 15000, 'finalizar mesmo assim');
    return a.slice(0, 70) + '… (um Finalizar só; o 2º toque finaliza)';
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
      for (let i = 0; i < len; i++) { s = (s * 16807) % 2147483647; d[i] = i < sr * 3.2 ? (s / 2147483647 - 0.5) * 0.5 * (0.6 + 0.4 * Math.sin(i / sr * 25)) : 0; }
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
