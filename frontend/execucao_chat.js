/* ─── ChatBOT: conferência da conversa (sem Grafana) ───
   O executor (executor_avaya.py, modo chatbot) conversa com o bot pelo WhatsApp Web e devolve a
   conversa + um print. Para cada passo com resposta esperada (texto do prompt na SPEC), procura as
   primeiras palavras significativas dele nas mensagens do bot: todas achadas = OK, alguma faltando =
   Não OK. Evidências do CT: a conversa (.txt) e o print (.png). */

function _chatPalavras(s) {
  return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .split(/[^a-z0-9]+/).filter(Boolean);
}

// Tira variáveis (@{nome}), marcações ([submit|…], ##instrução) e formatação; fica com as 6 primeiras palavras.
function _chatTrecho(texto) {
  const limpo = String(texto || '')
    .replace(/@\{[^}]*\}/g, ' ')
    .replace(/\[[^\]]*\]/g, ' ')
    .replace(/##[^\n]*/g, ' ')
    .replace(/[*_~>]/g, ' ');
  return _chatPalavras(limpo).filter(w => w.length > 2).slice(0, 6);
}

function _chatComparar(pedido, conversa, passosExec) {
  const textoBot = conversa.filter(m => m.de === 'bot').map(m => `${m.texto} ${(m.botoes || []).join(' ')}`).join(' ');
  const palavrasBot = new Set(_chatPalavras(textoBot));
  const exec = {};
  (passosExec || []).forEach(x => { exec[x.n] = x; });
  const itens = pedido.passos.filter(p => p.esperado || p.sem_resposta).map(p => {
    if (p.sem_resposta) {
      // Esperado: o bot NÃO responde ("@{semMensagem}"). Conta como OK se ele ficou calado nesse passo.
      const x = exec[p.n];
      return { n: p.n, estado: p.estado, esperado: '(o bot não deve responder)', achou: !!x && !x.novas };
    }
    const trecho = _chatTrecho(p.esperado);
    const achadas = trecho.filter(w => palavrasBot.has(w)).length;
    return { n: p.n, estado: p.estado, esperado: p.esperado, achou: trecho.length ? achadas / trecho.length >= 0.67 : true };
  });
  const falta = itens.filter(i => !i.achou).length;
  const sugestao = !itens.length ? 'pendente' : (falta ? 'nok' : 'ok');
  const motivo = !itens.length ? 'O CT não tem resposta esperada do bot para conferir.'
    : (falta ? `${falta} de ${itens.length} resposta(s) esperada(s) do bot NÃO apareceram.`
      : `Todas as ${itens.length} respostas esperadas do bot apareceram.`);
  return { itens, sugestao, motivo };
}

// SPs esperados do CT x SPs marcados no trace do Grafana (mesma leitura do ROGUE: spTransition/spPrompt).
function _chatCompararSps(pedido, trace) {
  const ch = trace ? confLerTraceRogue(trace) : null;
  if (!ch) return null;
  const marcados = new Set(ch.sps.map(s => s.codigo));
  const sps = (pedido.sps_esperados || []).map(s => {
    const codigo = (String(s).split('=').pop() || '').trim();
    return { esperado: s, codigo, achou: marcados.has(codigo) };
  });
  return { ch, sps, faltando: sps.filter(s => !s.achou).length };
}

// Link do Explore do Grafana que abre o trace da conversa (mesmo formato do link que o QA usa).
function linkGrafanaTrace(grafana, fonteUid, traceId) {
  if (!grafana || !traceId) return '';
  const uid = fonteUid || GRAFANA_DS_UID_ROGUE;
  const panes = { gmg: { datasource: uid, queries: [{ query: traceId, refId: 'A', datasource: { type: 'jaeger', uid } }], range: { from: 'now-30d', to: 'now' } } };
  return `${String(grafana).replace(/\/+$/, '')}/explore?schemaVersion=1&panes=${encodeURIComponent(JSON.stringify(panes))}&orgId=1`;
}

async function _execAplicarChat(ctId, pedido, res, eventos) {
  const conversa = res.conversa || [];
  const r = _chatComparar(pedido, conversa, res.passos_exec);
  const rs = _chatCompararSps(pedido, res.trace);
  if (rs && rs.sps.length) {
    // Com o trace, os SPs também decidem: faltou SP = Não OK.
    if (rs.faltando) { r.sugestao = 'nok'; r.motivo += ` ${rs.faltando} de ${rs.sps.length} SP(s) esperados NÃO foram marcados no Grafana.`; }
    else { r.motivo += ` Todos os ${rs.sps.length} SP(s) esperados foram marcados no Grafana.`; if (r.sugestao === 'pendente') r.sugestao = 'ok'; }
  }
  const agora = new Date();
  const p2 = n => String(n).padStart(2, '0');
  const carimbo = `${agora.getFullYear()}${p2(agora.getMonth() + 1)}${p2(agora.getDate())}_${p2(agora.getHours())}${p2(agora.getMinutes())}${p2(agora.getSeconds())}`;
  const umaLinha = t => String(t || '').replace(/\s+/g, ' ').trim();
  const link = rs ? linkGrafanaTrace(res.grafana_url || pedido.grafana_url, res.trace_fonte_uid, rs.ch.traceId) : '';
  const linhas = [
    `Conferência automática — ${ctId} (ChatBOT ${pedido.bot_numero})`,
    `Resultado sugerido: ${r.sugestao.toUpperCase()} — ${r.motivo}`,
    ...(link ? [`Link do trace no Grafana: ${link}`] : []),
    '',
    'Respostas esperadas do bot:',
    ...r.itens.map(i => `  [${i.achou ? 'OK' : 'FALTA'}] step ${i.n} (${i.estado}): ${umaLinha(i.esperado).slice(0, 160)}`),
    '',
    ...(rs ? ['SPs esperados (Grafana):', ...rs.sps.map(s => `  [${s.achou ? 'OK' : 'FALTA'}] ${s.esperado}`),
      `SPs marcados no trace ${rs.ch.traceId}: ${rs.ch.sps.map(s => s.codigo).join(', ')}`, '',
      '================ JORNADA NO GRAFANA (trace) ================', ...rs.ch.linhas, '']
      : ['SPs: trace do Grafana não obtido (conferência só pela conversa).', '']),
    '================ CONVERSA ================',
    ...conversa.map(m => `${m.hora || ''} ${m.de === 'bot' ? 'BOT' : 'QA '}: ${umaLinha(m.texto)}${(m.botoes || []).length ? `  [botões: ${m.botoes.join(' | ')}]` : ''}`),
    '',
    '================ EXECUTOR ================',
    ...eventos,
  ];
  const arquivos = [new File([linhas.join('\n')], `ChatBOT_${ctId}_${carimbo}.txt`, { type: 'text/plain' })];
  if (res.print_png_b64) {
    const bin = Uint8Array.from(atob(res.print_png_b64), c => c.charCodeAt(0));
    arquivos.push(new File([bin], `ChatBOT_${ctId}_${carimbo}.png`, { type: 'image/png' }));
  }
  if (res.trace) {
    arquivos.push(new File([JSON.stringify(res.trace, null, 1)], `ChatBOT_${ctId}_${carimbo}_trace${rs ? '_' + rs.ch.traceId : ''}.json`, { type: 'application/json' }));
  }
  if (r.sugestao !== 'pendente') salvarDadosExecucao(ctId, 'status', r.sugestao);
  const atual = semNotasAuto((avaliacoesQA[ctId] || {}).comments);
  const nota = `[Auto ${agora.toLocaleTimeString('pt-BR')}] ${r.motivo}`;
  salvarDadosExecucao(ctId, 'comments', atual ? `${atual} | ${nota}` : nota);
  await removerEvidenciasAuto(ctId);
  await anexarEvidencias(ctId, { files: arquivos, value: '' });
  return r.sugestao;
}

/* ─── Repetir um CT substitui o que a automação gravou antes ─── */
// (Grafana_ = link do trace colado à mão: é da conversa anterior, então sai junto quando o CT roda de novo.)
const _PREFIXOS_EVID_AUTO = ['ChatBOT_', 'Log_URA_', 'Rogue_', 'Grafana_'];

// Evidências geradas pela automação/conferência (os anexos feitos à mão pelo QA ficam).
async function removerEvidenciasAuto(ctId) {
  const antigas = (evidenciasPorCT[ctId] || []).filter(e => _PREFIXOS_EVID_AUTO.some(p => String(e.nome || '').startsWith(p)));
  for (const e of antigas) await removerEvidencia(ctId, e.id);
}

// Tira do comentário as notas "[Auto …]" de execuções anteriores (o texto do QA fica).
function semNotasAuto(comentario) {
  return String(comentario || '').split(/\s*\|\s*/).filter(p => p && !/^\[Auto\b/.test(p)).join(' | ').trim();
}

/* ─── "🔎 Conferir evidência" no ChatBOT: mostra o print e a conversa da última execução ─── */
const _RX_LINK_GRAFANA = /^Link do trace no Grafana: (\S+)/m;

// Link do trace colado à mão pelo QA (Grafana aberto na aba dele): vira a evidência Grafana_<CT>_link.txt.
function _chatHtmlLinkManual(ctId) {
  return `<div class="bi-nota" id="chatLinkManual">📈 <strong>Link do trace no Grafana</strong> (cole o link do Explore desta conversa, aberto na sua aba do Grafana):
    <div style="display:flex;gap:6px;margin-top:4px;flex-wrap:wrap">
      <input type="url" class="auto-input" id="chatLinkInput" style="flex:1;min-width:220px" placeholder="http://10.169.0.216:30300/explore?…" />
      <button type="button" class="btn-export-pdf" onclick="chatSalvarLinkGrafana('${escHtml(ctId)}')">Salvar link</button>
    </div><span id="chatLinkMsg"></span></div>`;
}

async function chatSalvarLinkGrafana(ctId) {
  const inp = document.getElementById('chatLinkInput');
  const msg = document.getElementById('chatLinkMsg');
  const url = String(inp && inp.value || '').trim();
  if (!/^https?:\/\/\S+$/.test(url)) { if (msg) msg.textContent = ' ⚠️ Cole um link começando com http:// ou https://'; return; }
  const raiz = inp.closest('#chatLinkManual').parentElement;
  const antigos = (evidenciasPorCT[ctId] || []).filter(e => /^Grafana_/.test(e.nome || ''));
  for (const e of antigos) await removerEvidencia(ctId, e.id);
  const texto = `Link do trace no Grafana: ${url}\nCT: ${ctId}\nInformado manualmente pelo QA em ${new Date().toLocaleString('pt-BR')}\n`;
  await anexarEvidencias(ctId, { files: [new File([texto], `Grafana_${ctId}_link.txt`, { type: 'text/plain' })], value: '' });
  chatMostrarEvidencia(raiz, ctId);
}

function _chatMostrarLink(el, url, manual) {
  if (!el || !/^https?:\/\//.test(url)) return;
  const p = document.createElement('p');
  p.className = 'bi-nota';
  p.innerHTML = `📈 <a href="${escHtml(url)}" target="_blank" rel="noopener">Abrir o trace desta conversa no Grafana ↗</a>${manual ? ' (link colado à mão)' : ''}`;
  el.before(p);
}

function chatMostrarEvidencia(raiz, ctId) {
  const lista = evidenciasPorCT[ctId] || [];
  const png = [...lista].reverse().find(e => /^ChatBOT_.*\.png$/i.test(e.nome || ''));
  const txt = [...lista].reverse().find(e => /^ChatBOT_.*\.txt$/i.test(e.nome || ''));
  const linkManual = [...lista].reverse().find(e => /^Grafana_.*\.txt$/i.test(e.nome || ''));
  const mostrarManual = () => linkManual && linkManual.blob.text().then(t => {
    const m = _RX_LINK_GRAFANA.exec(t);
    if (m) _chatMostrarLink(document.getElementById('chatLinkManual'), m[1], true);
  });
  if (!png && !txt) {
    raiz.innerHTML = `<p class="conf-alerta">⚠️ Este CT ainda não tem evidência do ChatBOT. Use <strong>▶ Executar → 💬 Conversar e executar</strong> (com o executor aberto) para gerar a conversa e o print.</p>${_chatHtmlLinkManual(ctId)}`;
    mostrarManual();
    return;
  }
  const st = avaliacoesQA[ctId] || {};
  raiz.innerHTML = `
    <p class="bi-nota">Status: <strong>${escHtml(_STATUS_ROTULO[st.status] || 'Pendente')}</strong>${st.comments ? ` · ${escHtml(st.comments)}` : ''}</p>
    ${png ? `<div class="chat-evid-print"><img id="chatEvidImg" alt="Print da conversa com o bot" /></div>` : ''}
    ${_chatHtmlLinkManual(ctId)}
    ${txt ? `<details class="conf-detalhe" open><summary>Conversa e conferência (${escHtml(txt.nome)})</summary><pre class="exec-g-log" id="chatEvidTxt">carregando…</pre></details>` : ''}`;
  if (png) {
    const url = URL.createObjectURL(png.blob);
    const img = document.getElementById('chatEvidImg');
    img.onload = () => setTimeout(() => URL.revokeObjectURL(url), 1000);
    img.src = url;
  }
  // Link do trace: o colado à mão vale; senão, o que a execução automática gravou no .txt.
  mostrarManual();
  if (txt) txt.blob.text().then(t => {
    const el = document.getElementById('chatEvidTxt');
    if (el) el.textContent = t;
    const m = _RX_LINK_GRAFANA.exec(t);
    if (m && !linkManual) _chatMostrarLink(document.getElementById('chatLinkManual'), m[1], false);
  });
}
