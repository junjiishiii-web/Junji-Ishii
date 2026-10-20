/* ─── Automação · Etapa 2: conferência de evidência (URA Legado) ───
   O QA liga manualmente e carrega o URADebug_*.txt (e, se quiser, o
   IntegracaoDebug_*.txt) do diretório da URA. A ferramenta separa as
   chamadas do arquivo, acha a chamada pelo ANI/horário e confere os SPs e
   prompts esperados do CT. "Aplicar no CT" grava o status sugerido e anexa
   o trecho da chamada (com tokens mascarados) como evidência.

   Formato da linha do log da URA Legado:
   [19/10/2026][09:45:33][INFO ][MarcarScriptPoint   ][004][0000011637]->texto
     data       hora      nível  função/estado         canal transação     */

const CONF_LINHA = /^\[(\d{2}\/\d{2}\/\d{4})\]\[(\d{2}:\d{2}:\d{2})\]\[[^\]]*\]\[([^\]]*)\]\[(\d+)\]\[(\d+)\]->(.*)$/;

let confEstado = { ctId: '', ura: null, integracao: null, chamadas: [], idx: -1 };

function _confNovaChamada(data, hora, canal, transacao) {
  return {
    data, inicio: hora, fim: hora, canal, transacao,
    ani: '', dnis: '', node: '', logUra: '', logIntegracao: '',
    sps: [], prompts: [], digitos: [], transferencia: null, desligou: false,
    linhas: [],
  };
}

// Separa o arquivo em chamadas. A mesma transação pode reaparecer em outro dia/arquivo,
// então a chamada termina na linha "-----" que a URA grava no fim de cada ligação.
function confSepararChamadas(texto) {
  const chamadas = [];
  const abertas = {};
  let ultima = null;
  texto.split(/\r?\n/).forEach(linha => {
    const m = CONF_LINHA.exec(linha);
    if (!m) {
      if (/^-{20,}\s*$/.test(linha)) {
        Object.keys(abertas).forEach(k => delete abertas[k]);
        ultima = null;
      } else if (ultima && linha.trim()) {
        ultima.linhas.push(linha);   // continuação (JSON/XML de resposta)
      }
      return;
    }
    const [, data, hora, funcao, canal, transacao, msg] = m;
    const chave = canal + '|' + transacao;
    let ch = abertas[chave];
    if (!ch) {
      ch = abertas[chave] = _confNovaChamada(data, hora, canal, transacao);
      chamadas.push(ch);
    }
    ultima = ch;
    ch.fim = hora;
    ch.linhas.push(linha);
    const estado = funcao.trim();
    let r;
    if ((r = /O ScripPoint (\d+) foi marcado/.exec(msg))) ch.sps.push({ codigo: r[1], hora, estado });
    else if ((r = /Vocalizando Prompt - (\S+)/.exec(msg))) ch.prompts.push({ id: r[1], hora, estado });
    else if ((r = /Digitos Coletados - (.*)$/.exec(msg))) { const v = r[1].trim(); if (v) ch.digitos.push({ valor: v, hora, estado }); }
    else if ((r = /Transferindo para: (\S+)(?:\s+após tocar:\s*(.*))?/.exec(msg))) ch.transferencia = { destino: r[1], prompt: (r[2] || '').trim(), hora };
    else if (/DESLIGAMENTO/.test(msg)) ch.desligou = true;
    else if (estado === 'Inicializacao') {
      if ((r = /^ANI\s*:\s*(\S+)/.exec(msg))) ch.ani = r[1];
      else if ((r = /^DNIS\s*:\s*(\S+)/.exec(msg))) ch.dnis = r[1];
      else if ((r = /^Node\s*:\s*(.+)$/.exec(msg))) ch.node = r[1].trim();
      else if ((r = /^Log URA\s*:\s*(.+)$/.exec(msg))) ch.logUra = r[1].trim();
      else if ((r = /^Log Integra\S*\s*:\s*(.+)$/.exec(msg))) ch.logIntegracao = r[1].trim();
    }
  });
  return chamadas.filter(c => c.sps.length || c.prompts.length || c.ani);
}

// Tokens e segredos que as APIs devolvem em claro no log de integração.
function confMascarar(texto) {
  return texto
    .replace(/("?(?:access_token|refresh_token|client_id|client_secret|password|senha|apikey|api_key)"?\s*[:=]\s*"?)([^",\s<]{6,})/gi,
      (_, a, b) => a + b.slice(0, 4) + '****' + b.slice(-4))
    .replace(/(\bToken\s*:\s*)([A-Za-z0-9._-]{12,})/g, (_, a, b) => a + b.slice(0, 4) + '****' + b.slice(-4))
    .replace(/(Bearer\s+)([A-Za-z0-9._-]{12,})/g, (_, a, b) => a + b.slice(0, 4) + '****');
}

function _confDigitos(s) { return String(s || '').replace(/\D/g, ''); }

function _confAniBate(aniLog, aniConfig) {
  const a = _confDigitos(aniLog), b = _confDigitos(aniConfig);
  if (!a || !b) return false;
  const n = Math.min(a.length, b.length, 10);   // compara os 10 últimos (DDD + número)
  return a.slice(-n) === b.slice(-n);
}

function _confPromptBate(esperado, tocados) {
  const e = String(esperado).toLowerCase();
  return tocados.find(p => {
    const t = p.id.toLowerCase();
    return t === e || (e.length >= 4 && t.includes(e)) || (t.length >= 6 && e.includes(t));
  }) || null;
}

function confComparar(roteiroCaso, ch) {
  const marcados = new Set(ch.sps.map(s => s.codigo));
  const sps = roteiroCaso.sps_esperados.map(s => {
    const codigo = (String(s).split('=').pop() || '').trim();
    return { esperado: s, codigo, achou: marcados.has(codigo) };
  });
  const prompts = roteiroCaso.prompts_esperados
    .flatMap(p => String(p).split(/\s*[|,/]\s*/))
    .filter(Boolean)
    .map(p => ({ esperado: p, tocado: _confPromptBate(p, ch.prompts) }));
  const faltandoSp = sps.filter(s => !s.achou).length;
  let sugestao, motivo;
  if (!sps.length) { sugestao = 'pendente'; motivo = 'O CT não tem SP para conferir: confira os prompts e o áudio.'; }
  else if (!faltandoSp) { sugestao = 'ok'; motivo = `Todos os ${sps.length} SP(s) esperados foram marcados.`; }
  else { sugestao = 'nok'; motivo = `${faltandoSp} de ${sps.length} SP(s) esperados NÃO foram marcados.`; }
  return { sps, prompts, sugestao, motivo };
}

/* ─── tela ─── */
function _confDataHoje() {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  return { a: d.getFullYear(), m: p(d.getMonth() + 1), d: p(d.getDate()) };
}
function confCaminhosLog(ura) {
  if (!ura) return null;
  const { a, m, d } = _confDataHoje();
  const base = `\\\\${ura.host || ura.nome}\\lmcti\\Data`;
  return {
    ura: `${base}\\UraLog\\${a}\\${m}\\${d}\\URADebug_${a}-${m}-${d}_${ura.node}_<canal>.txt`,
    integracao: `${base}\\IntegracaoLog\\${a}\\${m}\\${d}\\IntegracaoDebug_${a}-${m}-${d}_${ura.node}_<canal>.txt`,
  };
}

function renderizarConferencia() {
  const raiz = document.getElementById('autoConferencia');
  if (!raiz) return;
  const tipo = autoConfig.tipo;
  if (tipo !== 'ura_legado') {
    raiz.innerHTML = tipo === 'ura_rogue'
      ? `<p class="auto-vazio">Conferência automática do ROGUE (Grafana / Jaeger): em construção. Precisamos do export JSON de um trace para ler os SPs.</p>`
      : '';
    return;
  }
  const casos = _autoCasosSelecionados();
  if (!casos.find(c => c.ct_id === confEstado.ctId)) confEstado.ctId = casos.length ? casos[0].ct_id : '';
  const caminhos = confCaminhosLog(_autoDestinoEscolhido('ura_legado'));
  const ch = confEstado.chamadas[confEstado.idx];

  raiz.innerHTML = `
    <p class="bi-nota">Faça a ligação do CT e carregue os <strong>2 logs</strong> da URA do mesmo dia, node e canal: o <strong>Log URA</strong> (URADebug — SPs, prompts e dígitos) e o <strong>Log Integração</strong> (IntegracaoDebug — chamadas às APIs). A ferramenta acha a sua chamada (pelo ANI e horário) e confere os SPs e prompts esperados.</p>
    ${caminhos ? `<div class="conf-caminho"><strong>Onde estão os logs (hoje):</strong>
        <span>Log URA:</span><code>${escHtml(caminhos.ura)}</code>
        <span>Log Integração:</span><code>${escHtml(caminhos.integracao)}</code>
        <span>&lt;canal&gt; = canal em que a chamada caiu (o número no fim do nome do arquivo). Os dois arquivos têm o mesmo final (data_node_canal).</span></div>`
      : `<p class="auto-vazio">Escolha a URA acima para ver onde ficam os logs.</p>`}
    <div class="auto-grid conf-entrada">
      <label class="auto-campo"><span>CT executado</span>
        <select class="auto-input" onchange="confEscolherCt(this.value)">
          ${casos.map(c => `<option value="${escHtml(c.ct_id)}" ${c.ct_id === confEstado.ctId ? 'selected' : ''}>${escHtml(c.ct_id)} — ${escHtml(c.estado)}</option>`).join('')}
        </select></label>
      <label class="auto-campo"><span>① Log URA (URADebug_….txt)</span>
        <input type="file" class="auto-input" accept=".txt,.log" onchange="confCarregarLog(this, 'ura')" />
        ${confEstado.ura ? `<em class="conf-arq-ok">✓ ${escHtml(confEstado.ura.nome)} — ${confEstado.chamadas.length} chamada(s)</em>` : ''}</label>
      <label class="auto-campo"><span>② Log Integração (IntegracaoDebug_….txt)</span>
        <input type="file" class="auto-input" accept=".txt,.log" onchange="confCarregarLog(this, 'integracao')" />
        ${confEstado.integracao ? `<em class="conf-arq-ok">✓ ${escHtml(confEstado.integracao.nome)}</em>` : ''}</label>
    </div>
    ${_confAvisoArquivos()}
    ${confEstado.chamadas.length ? `
      <label class="auto-campo"><span>Chamada</span>
        <select class="auto-input" onchange="confEscolherChamada(+this.value)">
          ${confEstado.chamadas.map((c, i) => `<option value="${i}" ${i === confEstado.idx ? 'selected' : ''}>${escHtml(`${c.inicio}–${c.fim} · ANI ${c.ani || '?'} · DNIS ${c.dnis || '?'} · ${c.sps.length} SP(s)${c.transferencia ? ' · → ' + c.transferencia.destino : ''} · transação ${+c.transacao}`)}</option>`).join('')}
        </select></label>` : ''}
    <div id="confResultado">${ch && confEstado.ctId ? _confHtmlResultado(ch) : ''}</div>`;
}

function _confHtmlResultado(ch) {
  const caso = (cacheModelagem.casos_teste || []).find(c => c.ct_id === confEstado.ctId);
  if (!caso) return '';
  const r = confComparar(_autoCasoParaRoteiro(caso), ch);
  const rotulo = { ok: 'OK 🟢', nok: 'Não OK 🔴', pendente: 'Conferir manualmente 🟡' }[r.sugestao];
  const linhaSp = s => `<tr class="${s.achou ? 'conf-ok' : 'conf-falta'}"><td>${s.achou ? '✓' : '✗'}</td><td><strong>${escHtml(s.esperado)}</strong></td>
    <td>${s.achou ? escHtml((ch.sps.find(x => x.codigo === s.codigo) || {}).hora || '') : 'não marcado'}</td></tr>`;
  const linhaPrompt = p => `<tr class="${p.tocado ? 'conf-ok' : 'conf-aviso'}"><td>${p.tocado ? '✓' : '?'}</td><td>${escHtml(p.esperado)}</td>
    <td>${p.tocado ? escHtml(`${p.tocado.id} (${p.tocado.hora})`) : 'não identificado no log'}</td></tr>`;
  return `
    <div class="conf-sugestao conf-${r.sugestao}">
      <div><strong>Sugestão: ${rotulo}</strong><br><span>${escHtml(r.motivo)}</span></div>
      <button class="btn-export-pdf" onclick="confAplicar()">Aplicar no ${escHtml(caso.ct_id)} (status + evidência)</button>
    </div>
    ${ch.logUra || ch.logIntegracao ? `<div class="conf-caminho"><strong>Logs desta chamada (gravados pela URA):</strong>
        ${ch.logUra ? `<span>Log URA:</span><code>${escHtml(ch.logUra)}</code>` : ''}
        ${ch.logIntegracao ? `<span>Log Integração:</span><code>${escHtml(ch.logIntegracao)}</code>` : ''}</div>` : ''}
    <div class="conf-colunas">
      <div><h5>SPs esperados</h5>
        <table class="data-table conf-tabela"><tbody>${r.sps.map(linhaSp).join('') || '<tr><td colspan="3">Sem SP no CT.</td></tr>'}</tbody></table></div>
      <div><h5>Prompts esperados</h5>
        <table class="data-table conf-tabela"><tbody>${r.prompts.map(linhaPrompt).join('') || '<tr><td colspan="3">Sem prompt no CT.</td></tr>'}</tbody></table></div>
    </div>
    <details class="conf-detalhe"><summary>O que aconteceu na chamada (${ch.sps.length} SPs, ${ch.prompts.length} prompts, ${ch.digitos.length} digitações)</summary>
      <table class="data-table conf-tabela"><thead><tr><th>Hora</th><th>Estado</th><th>Evento</th></tr></thead><tbody>
        ${[...ch.prompts.map(p => [p.hora, p.estado, '🔊 ' + p.id]),
           ...ch.digitos.map(d => [d.hora, d.estado, '⌨️ digitou ' + d.valor]),
           ...ch.sps.map(s => [s.hora, s.estado, '📍 SP ' + s.codigo]),
           ...(ch.transferencia ? [[ch.transferencia.hora, 'Transferência', `↪ ${ch.transferencia.destino} ${ch.transferencia.prompt}`]] : [])]
          .sort((a, b) => a[0].localeCompare(b[0]))
          .map(([h, e, t]) => `<tr><td>${escHtml(h)}</td><td>${escHtml(e)}</td><td>${escHtml(t)}</td></tr>`).join('')}
      </tbody></table>
    </details>`;
}

/* ─── ações ─── */
function confEscolherCt(ctId) {
  confEstado.ctId = ctId;
  renderizarConferencia();
}
function confEscolherChamada(i) {
  confEstado.idx = i;
  renderizarConferencia();
}

// "URADebug_2026-10-19_3198_4.txt" → "2026-10-19_3198_4" (data_node_canal): os 2 logs da mesma chamada têm o mesmo final.
function _confSufixo(nome) {
  const m = /_(\d{4}-\d{2}-\d{2}_\d+_\d+)\.\w+$/.exec(String(nome || ''));
  return m ? m[1] : '';
}
function _confAvisoArquivos() {
  const { ura, integracao } = confEstado;
  if (!ura && !integracao) return '';
  if (ura && !integracao) return `<p class="conf-alerta">⚠️ Falta o <strong>Log Integração</strong> do mesmo canal (IntegracaoDebug_${escHtml(_confSufixo(ura.nome) || '…')}.txt). Dá para conferir os SPs, mas a evidência fica sem as chamadas às APIs.</p>`;
  if (!ura) return `<p class="conf-alerta">⚠️ Falta o <strong>Log URA</strong> (URADebug_${escHtml(_confSufixo(integracao.nome) || '…')}.txt): é nele que estão os SPs e prompts.</p>`;
  const a = _confSufixo(ura.nome), b = _confSufixo(integracao.nome);
  if (a && b && a !== b) return `<p class="conf-alerta">⚠️ Os 2 logs não são da mesma chamada: Log URA <strong>${escHtml(a)}</strong> × Log Integração <strong>${escHtml(b)}</strong> (data_node_canal). Carregue os arquivos com o mesmo final.</p>`;
  return '';
}

async function confCarregarLog(input, qual) {
  const arq = (input.files || [])[0];
  if (!arq) return;
  // Os logs da URA são gravados em Windows-1252 (acentos).
  const lido = { nome: arq.name, texto: new TextDecoder('windows-1252').decode(await arq.arrayBuffer()) };
  const pareceIntegracao = /integracao/i.test(arq.name);
  if (qual === 'ura' && pareceIntegracao) { alert('Este é o Log Integração. No campo ① carregue o URADebug_….txt.'); input.value = ''; return; }
  if (qual === 'integracao' && /uradebug/i.test(arq.name)) { alert('Este é o Log URA. No campo ② carregue o IntegracaoDebug_….txt.'); input.value = ''; return; }
  if (qual === 'integracao') {
    confEstado.integracao = lido;
    renderizarConferencia();
    return;
  }
  const chamadas = confSepararChamadas(lido.texto);
  if (!chamadas.length) { alert('Não encontrei chamadas neste arquivo. Confira se é o URADebug da URA Legado.'); input.value = ''; return; }
  confEstado.ura = lido;
  confEstado.chamadas = chamadas;
  // A chamada do teste: a última com o ANI configurado (ou a última do arquivo).
  const ani = _autoValor('ura_legado', 'ani');
  let idx = -1;
  chamadas.forEach((c, i) => { if (_confAniBate(c.ani, ani)) idx = i; });
  confEstado.idx = idx >= 0 ? idx : chamadas.length - 1;
  renderizarConferencia();
}

function _confTrechoIntegracao(ch) {
  if (!confEstado.integracao) return '';
  const linhas = [];
  let dentro = false;
  confEstado.integracao.texto.split(/\r?\n/).forEach(l => {
    const m = CONF_LINHA.exec(l);
    if (m) dentro = m[4] === ch.canal && m[5] === ch.transacao && m[1] === ch.data;
    else if (/^-{20,}\s*$/.test(l)) dentro = false;
    if (dentro) linhas.push(l);
  });
  return linhas.join('\n');
}

async function confAplicar() {
  const ch = confEstado.chamadas[confEstado.idx];
  const caso = (cacheModelagem.casos_teste || []).find(c => c.ct_id === confEstado.ctId);
  if (!ch || !caso) return;
  const r = confComparar(_autoCasoParaRoteiro(caso), ch);
  const resumo = [
    `Conferência automática — ${caso.ct_id}`,
    `Chamada: ${ch.data} ${ch.inicio}–${ch.fim} | ANI ${ch.ani} | DNIS ${ch.dnis} | ${ch.node} | canal ${ch.canal} | transação ${+ch.transacao}`,
    `Log URA        : ${ch.logUra || confEstado.ura.nome}`,
    `Log Integração : ${ch.logIntegracao || (confEstado.integracao ? confEstado.integracao.nome : '(não carregado)')}`,
    `Resultado sugerido: ${r.sugestao.toUpperCase()} — ${r.motivo}`,
    '',
    'SPs esperados:',
    ...r.sps.map(s => `  [${s.achou ? 'OK' : 'FALTA'}] ${s.esperado}`),
    'Prompts esperados:',
    ...r.prompts.map(p => `  [${p.tocado ? 'OK' : '??'}] ${p.esperado}${p.tocado ? ' -> ' + p.tocado.id : ''}`),
    `SPs marcados na chamada: ${ch.sps.map(s => s.codigo).join(', ')}`,
    ch.transferencia ? `Transferência: ${ch.transferencia.destino} (${ch.transferencia.prompt})` : 'Sem transferência registrada',
    '',
    '================ LOG DA URA (só esta chamada) ================',
    ch.linhas.join('\n'),
  ];
  const integ = _confTrechoIntegracao(ch);
  if (integ) resumo.push('', '================ LOG DE INTEGRAÇÃO (só esta chamada) ================', integ);
  const texto = confMascarar(resumo.join('\n'));
  const arquivo = new File([texto], `Log_URA_${caso.ct_id}_${ch.data.split('/').reverse().join('')}_${ch.inicio.replace(/:/g, '')}.txt`, { type: 'text/plain' });

  if (r.sugestao !== 'pendente') salvarDadosExecucao(caso.ct_id, 'status', r.sugestao);
  const atual = ((avaliacoesQA[caso.ct_id] || {}).comments || '').trim();
  const nota = `[Auto ${ch.inicio}] ${r.motivo}`;
  salvarDadosExecucao(caso.ct_id, 'comments', atual ? `${atual} | ${nota}` : nota);
  await anexarEvidencias(caso.ct_id, { files: [arquivo], value: '' });
  alert(`${caso.ct_id}: status ${r.sugestao === 'pendente' ? 'mantido' : 'atualizado'} e evidência anexada (aba Execução dos Testes).`);
}
