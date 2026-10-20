/* ─── Automação · Etapa 2: conferência de evidência (URA Legado e ROGUE) ───
   O QA liga manualmente e carrega o URADebug_*.txt (e, se quiser, o
   IntegracaoDebug_*.txt) do diretório da URA. A ferramenta separa as
   chamadas do arquivo, acha a chamada pelo ANI/horário e confere os SPs e
   prompts esperados do CT. "Aplicar no CT" grava o status sugerido e anexa
   o trecho da chamada (com tokens mascarados) como evidência.

   Formato da linha do log da URA Legado:
   [19/10/2026][09:45:33][INFO ][MarcarScriptPoint   ][004][0000011637]->texto
     data       hora      nível  função/estado         canal transação     */

const CONF_LINHA = /^\[(\d{2}\/\d{2}\/\d{4})\]\[(\d{2}:\d{2}:\d{2})\]\[[^\]]*\]\[([^\]]*)\]\[(\d+)\]\[(\d+)\]->(.*)$/;

let confEstado = { tipo: '', ctId: '', ura: null, integracao: null, trace: null, chamadas: [], idx: -1 };

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
  // Sem "_" e caixa: a SPEC escreve "MenuDesambiguaTLVCRN_INI", o ROGUE "CRN_IDX_NaoCliente_MenuDesambiguaTLVCRNIni".
  const norm = s => String(s).toLowerCase().replace(/[^a-z0-9]/g, '');
  const en = norm(e);
  return tocados.find(p => {
    const t = p.id.toLowerCase(), tn = norm(p.id);
    return t === e || (e.length >= 4 && t.includes(e)) || (t.length >= 6 && e.includes(t))
      || (en.length >= 6 && tn.includes(en));
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

// CT fixo quando a conferência é aberta pelo botão do próprio CT (aba Execução dos Testes).
let confModalCt = '';

function renderizarConferencia() {
  const raiz = document.getElementById(confModalCt ? 'confModalCorpo' : 'autoConferencia');
  if (!raiz) return;
  const tipo = autoConfig.tipo;
  // Trocou de tecnologia: o que foi carregado para a outra não vale aqui.
  if (confEstado.tipo !== tipo) confEstado = { tipo, ctId: confEstado.ctId, ura: null, integracao: null, trace: null, chamadas: [], idx: -1 };
  if (tipo !== 'ura_legado' && tipo !== 'ura_rogue') {
    raiz.innerHTML = confModalCt
      ? `<p class="conf-alerta">⚠️ ${tipo === 'chatbot' ? 'A conferência do ChatBOT ainda não está disponível.' : 'Escolha primeiro a tecnologia (URA Legado ou URA ROGUE) e a URA / esteira na aba <strong>🤖 Automação</strong>.'}</p>
         <button class="btn-export-pdf" onclick="confIrParaAutomacao()">Ir para a aba Automação</button>`
      : '';
    return;
  }
  const casos = _autoCasosSelecionados();
  const ch = confEstado.chamadas[confEstado.idx];
  let seletorCt;
  if (confModalCt) {
    confEstado.ctId = confModalCt;
    const c = (cacheModelagem.casos_teste || []).find(x => x.ct_id === confModalCt) || {};
    const destino = _autoDestinoEscolhido(tipo);
    seletorCt = `<div class="auto-campo"><span>CT executado</span>
        <div class="conf-ct-fixo"><strong>${escHtml(confModalCt)}</strong> — ${escHtml(c.estado || '')}
          <small>${escHtml(AUTO_TIPOS[tipo].rotulo)}${destino ? ' · ' + escHtml(destino.nome) : ''}</small></div></div>`;
  } else {
    if (!casos.find(c => c.ct_id === confEstado.ctId)) confEstado.ctId = casos.length ? casos[0].ct_id : '';
    seletorCt = `<label class="auto-campo"><span>CT executado</span>
        <select class="auto-input" onchange="confEscolherCt(this.value)">
          ${casos.map(c => `<option value="${escHtml(c.ct_id)}" ${c.ct_id === confEstado.ctId ? 'selected' : ''}>${escHtml(c.ct_id)} — ${escHtml(c.estado)}</option>`).join('')}
        </select></label>`;
  }

  if (tipo === 'ura_rogue') {
    const grafana = (_autoValor('ura_rogue', 'grafana_url') || 'https://grafana-mc1-rogue.hml-sp.claro.internal').replace(/\/+$/, '');
    const finder = (/^https?:\/\//.test(_autoValor('ura_rogue', 'grafana_painel'))
      ? _autoValor('ura_rogue', 'grafana_painel')
      : `${grafana}/d/OBHSegzGK/conversation-finder?orgId=1`).replace(/[?&](from|to)=[^&]*/g, '') + '&from=now-3h&to=now';
    raiz.innerHTML = `
      <p class="bi-nota">Faça a ligação do CT e traga o <strong>trace</strong> da conversa do Grafana. A ferramenta lê os estados, os SPs (transição e prompt) e os prompts tocados e confere com o esperado do CT.</p>
      <div class="auto-grid conf-entrada">${seletorCt}</div>
      <div class="conf-auto">
        <div class="conf-caminho conf-passos"><strong>Na VPN:</strong>
          <span>1. <a href="${escHtml(finder)}" target="grafana_rogue" rel="opener">Abrir o Conversation Finder (últimas 3 horas) ↗</a> e ache a ligação pelo <strong>From</strong> (ANI) e horário.</span>
          <span>2. Clique no <strong>ConversationId</strong> para abrir o trace.</span>
          <span>3. Com o trace aberto, clique no favorito <strong>➜ Enviar ao Modeler</strong>.</span>
          <span>4. Volte aqui e clique em <strong>📋 Colar trace do Grafana</strong> (se a aba do Grafana foi aberta pelo link acima, o trace já chega sozinho).</span></div>
        <div class="conf-auto-linha conf-auto-linha-rogue">
          <button class="btn-export-pdf conf-auto-btn" onclick="confColarTrace()">📋 Colar trace do Grafana</button>
          <span class="conf-favorito">Ainda não tem o favorito? Arraste este botão para a barra de favoritos:
            <a class="conf-bookmarklet" href="${escHtml(confBookmarklet())}" onclick="alert('Arraste este botão para a barra de favoritos (Ctrl+Shift+B mostra a barra). Depois, clique nele com o trace aberto no Grafana.'); return false;">➜ Enviar ao Modeler</a></span>
        </div>
        ${confEstado.statusBusca ? `<div class="conf-auto-status">${confEstado.statusBusca}</div>` : ''}
        <div class="conf-colar" id="confColarArea" hidden>
          <textarea class="auto-input" rows="2" placeholder="Clique aqui e cole com Ctrl+V" onpaste="confColarEvento(event)"></textarea></div>
      </div>
      <details class="conf-manual" ${confEstado.trace && confEstado.trace.manual ? 'open' : ''}>
        <summary>Carregar o trace manualmente (.json)</summary>
        <p class="bi-nota">No trace do Grafana: <strong>Inspect → Data → Download</strong> e carregue o arquivo.</p>
        <label class="auto-campo"><span>Trace da conversa (.json)</span>
          <input type="file" class="auto-input" accept=".json" onchange="confCarregarTrace(this)" /></label>
      </details>
      ${confEstado.trace ? `<p class="conf-arquivos"><em class="conf-arq-ok">✓ ${escHtml(confEstado.trace.nome)}</em></p>` : ''}
      <div id="confResultado">${ch && confEstado.ctId ? _confHtmlResultado(ch) : ''}</div>`;
    return;
  }

  _confCarregarPastasSalvas();
  const uraDestino = _autoDestinoEscolhido('ura_legado');
  const caminhos = confCaminhosLog(uraDestino);
  const pasta = uraDestino ? confPastas[uraDestino.id] : null;
  const pastaData = uraDestino ? `\\\\${uraDestino.host || uraDestino.nome}\\lmcti\\Data` : '';
  raiz.innerHTML = `
    <p class="bi-nota">Faça a ligação do CT e clique em <strong>Buscar minha chamada</strong>: a ferramenta abre a pasta da URA, acha a sua chamada pelo ANI (em todos os canais do dia) e carrega os <strong>2 logs</strong> — Log URA (SPs, prompts, dígitos) e Log Integração (APIs). Precisa estar na VPN e usar Chrome ou Edge.</p>
    <div class="auto-grid conf-entrada">${seletorCt}</div>
    ${uraDestino ? `<div class="conf-auto">
        <div class="conf-auto-linha">
          <label class="auto-campo"><span>Dia da ligação</span>
            <input type="date" class="auto-input" id="confDia" value="${escHtml(confEstado.dia || _confHojeIso())}" onchange="confEstado.dia = this.value" /></label>
          <label class="auto-campo"><span>ANI que ligou</span>
            <input type="text" class="auto-input" id="confAni" value="${escHtml(confEstado.aniBusca || _autoValor('ura_legado', 'ani'))}" placeholder="ex.: 11948049798" oninput="confEstado.aniBusca = this.value; autoAlterarCampo('ani', this.value)" /></label>
          <button class="btn-export-pdf conf-auto-btn" onclick="confBuscarNaPasta()">📁 Buscar minha chamada</button>
        </div>
        <div class="conf-auto-pasta">${pasta
          ? `Pasta autorizada: <strong>${escHtml(pasta.name)}</strong> de ${escHtml(uraDestino.nome)} · <a href="#" onclick="confTrocarPasta(); return false;">trocar pasta</a>`
          : `Na primeira busca o navegador pede a pasta: cole <code>${escHtml(pastaData)}</code> na barra de endereço da janela, abra e clique em <em>Selecionar pasta</em> → <em>Permitir</em>. Ela fica lembrada para as próximas.`}</div>
        ${confEstado.statusBusca ? `<div class="conf-auto-status">${confEstado.statusBusca}</div>` : ''}
      </div>` : `<p class="auto-vazio">Escolha a URA na aba Automação para buscar os logs.</p>`}
    <details class="conf-manual" ${confEstado.ura && !confEstado.viaPasta ? 'open' : ''}>
    <summary>Carregar os logs manualmente</summary>
    ${caminhos ? `<div class="conf-caminho"><strong>Onde estão os logs (hoje):</strong>
        <span>Log URA:</span><code>${escHtml(caminhos.ura)}</code>
        <span>Log Integração:</span><code>${escHtml(caminhos.integracao)}</code>
        <span>&lt;canal&gt; = canal em que a chamada caiu (o número no fim do nome do arquivo). Os dois arquivos têm o mesmo final (data_node_canal).</span></div>`
      : ''}
    <div class="auto-grid conf-entrada">
      <label class="auto-campo"><span>① Log URA (URADebug_….txt)</span>
        <input type="file" class="auto-input" accept=".txt,.log" onchange="confCarregarLog(this, 'ura')" />
        ${confEstado.ura ? `<em class="conf-arq-ok">✓ ${escHtml(confEstado.ura.nome)} — ${confEstado.chamadas.length} chamada(s)</em>` : ''}</label>
      <label class="auto-campo"><span>② Log Integração (IntegracaoDebug_….txt)</span>
        <input type="file" class="auto-input" accept=".txt,.log" onchange="confCarregarLog(this, 'integracao')" />
        ${confEstado.integracao ? `<em class="conf-arq-ok">✓ ${escHtml(confEstado.integracao.nome)}</em>` : ''}</label>
    </div>
    </details>
    ${_confAvisoArquivos()}
    ${confEstado.chamadas.length ? `
      <label class="auto-campo"><span>Chamada</span>
        <select class="auto-input" onchange="confEscolherChamada(+this.value)">
          ${confEstado.chamadas.map((c, i) => `<option value="${i}" ${i === confEstado.idx ? 'selected' : ''}>${escHtml(`${c.inicio}–${c.fim} · ANI ${c.ani || '?'} · DNIS ${c.dnis || '?'} · ${c.sps.length} SP(s)${c.transferencia ? ' · → ' + c.transferencia.destino : ''} · canal ${+c.canal} · transação ${+c.transacao}`)}</option>`).join('')}
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
    ${ch.resumo ? `<p class="conf-arquivos">${escHtml(ch.resumo)}</p>` : ''}
    <details class="conf-detalhe"><summary>O que aconteceu na chamada (${ch.sps.length} SPs, ${ch.prompts.length} prompts, ${ch.digitos.length} ${ch.origem === 'rogue' ? 'saídas escolhidas' : 'digitações'})</summary>
      <table class="data-table conf-tabela"><thead><tr><th>Hora</th><th>Estado</th><th>Evento</th></tr></thead><tbody>
        ${[...ch.prompts.map(p => [p.hora, p.estado, '🔊 ' + p.id]),
           ...ch.digitos.map(d => [d.hora, d.estado, d.rotulo || '⌨️ digitou ' + d.valor]),
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
  // Busca na pasta: cada chamada traz os seus 2 arquivos (podem ser de canais diferentes).
  const ch = confEstado.chamadas[i];
  if (ch && ch._arquivos) { confEstado.ura = ch._arquivos.ura; confEstado.integracao = ch._arquivos.integracao; }
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
  confEstado.viaPasta = false;
  confEstado.statusBusca = '';
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
  const rogue = ch.origem === 'rogue';
  const origem = rogue
    ? [`Chamada (ROGUE): ${ch.data} ${ch.inicio}–${ch.fim} | ANI ${ch.ani} | DNIS ${ch.dnis} | ${ch.node}`,
       `Trace          : ${ch.traceId} (${confEstado.trace.nome})`,
       `Conversation   : ${ch.transacao}`]
    : [`Chamada: ${ch.data} ${ch.inicio}–${ch.fim} | ANI ${ch.ani} | DNIS ${ch.dnis} | ${ch.node} | canal ${ch.canal} | transação ${+ch.transacao}`,
       `Log URA        : ${ch.logUra || confEstado.ura.nome}`,
       `Log Integração : ${ch.logIntegracao || (confEstado.integracao ? confEstado.integracao.nome : '(não carregado)')}`];
  const resumo = [
    `Conferência automática — ${caso.ct_id}`,
    ...origem,
    `Resultado sugerido: ${r.sugestao.toUpperCase()} — ${r.motivo}`,
    '',
    'SPs esperados:',
    ...r.sps.map(s => `  [${s.achou ? 'OK' : 'FALTA'}] ${s.esperado}`),
    'Prompts esperados:',
    ...r.prompts.map(p => `  [${p.tocado ? 'OK' : '??'}] ${p.esperado}${p.tocado ? ' -> ' + p.tocado.id : ''}`),
    `SPs marcados na chamada: ${ch.sps.map(s => s.codigo).join(', ')}`,
    ch.transferencia ? `Transferência: ${ch.transferencia.destino} (${ch.transferencia.prompt})` : 'Sem transferência registrada',
    '',
    rogue ? '================ JORNADA NO ROGUE (trace) ================' : '================ LOG DA URA (só esta chamada) ================',
    ch.linhas.join('\n'),
  ];
  const integ = rogue ? '' : _confTrechoIntegracao(ch);
  if (integ) resumo.push('', '================ LOG DE INTEGRAÇÃO (só esta chamada) ================', integ);
  const texto = confMascarar(resumo.join('\n'));
  const carimbo = `${ch.data.split('/').reverse().join('')}_${ch.inicio.replace(/:/g, '')}`;
  const arquivos = [new File([texto], `${rogue ? 'Rogue' : 'Log_URA'}_${caso.ct_id}_${carimbo}.txt`, { type: 'text/plain' })];
  // ROGUE: o trace original (JSON do Grafana) também vai como evidência.
  if (rogue) arquivos.push(new File([confMascarar(confEstado.trace.texto)], `Rogue_${caso.ct_id}_${carimbo}_trace_${ch.traceId}.json`, { type: 'application/json' }));

  if (r.sugestao !== 'pendente') salvarDadosExecucao(caso.ct_id, 'status', r.sugestao);
  const atual = ((avaliacoesQA[caso.ct_id] || {}).comments || '').trim();
  const nota = `[Auto ${ch.inicio}] ${r.motivo}`;
  salvarDadosExecucao(caso.ct_id, 'comments', atual ? `${atual} | ${nota}` : nota);
  await anexarEvidencias(caso.ct_id, { files: arquivos, value: '' });
  const msg = `${caso.ct_id}: status ${r.sugestao === 'pendente' ? 'mantido' : 'atualizado'} e ${arquivos.length} evidência(s) anexada(s)`;
  if (confModalCt) { confFecharModal(); _confAvisoRapido(msg + '.'); }
  else alert(msg + ' (aba Execução dos Testes).');
}

/* ─── janela aberta pelo botão "🔎 Conferir evidência" do CT ─── */
function confAbrirModal(ctId) {
  confModalCt = ctId;
  document.getElementById('confModalTitulo').textContent = `🔎 Conferir evidência — ${ctId}`;
  document.getElementById('confModal').classList.add('aberto');
  renderizarConferencia();
}
function confFecharModal() {
  const ctId = confModalCt;
  confModalCt = '';
  document.getElementById('confModal').classList.remove('aberto');
  document.getElementById('confModalCorpo').innerHTML = '';
  renderizarConferencia();
  // Aberta pela execução guiada (execucao.js): volta para ela.
  if (ctId && typeof execAposConferencia === 'function') execAposConferencia(ctId);
}
function confIrParaAutomacao() {
  confFecharModal();
  const btn = [...document.querySelectorAll('#tabBar .tab-btn')].find(b => (b.getAttribute('onclick') || '').includes("'tabAutomacao'"));
  if (btn) switchExcelTab('tabAutomacao', btn);
}
function _confAvisoRapido(texto) {
  const el = document.createElement('div');
  el.className = 'conf-toast';
  el.textContent = '✓ ' + texto;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}
document.addEventListener('keydown', e => { if (e.key === 'Escape' && confModalCt) confFecharModal(); });

/* ─── ROGUE: trace do Jaeger exportado do Grafana ───
   Cada passo da conversa é um span "Dialog" com o estado (condition.state), o SP da
   transição (sessionContext.spTransition = "8416 - CRN_IDX_..."), o SP + nome do prompt
   (sessionContext.spPrompt = "4476 - CRN_IDX_Identificacao_PedeIDDtmfIniRdm") e a saída
   escolhida (sessionContext.tag_transfer_<Estado>_<n>). Uma ligação pode passar por
   mais de um projeto (ex.: claro-crn-ura → claro-tlv-ura) no mesmo trace. */

// Aceita o "Inspect → Data → Download" do Grafana (data frame) e o JSON nativo do Jaeger.
function _confSpansDoTrace(json) {
  const paraMapa = lista => {
    const m = {};
    (lista || []).forEach(t => { if (t && t.key !== undefined) m[t.key] = t.value; });
    return m;
  };
  const spans = [];
  const quadros = Array.isArray(json) ? json : [json];
  quadros.forEach(q => {
    if (q && q.schema && q.data && Array.isArray(q.schema.fields)) {
      const nomes = q.schema.fields.map(f => f.name);
      const col = n => q.data.values[nomes.indexOf(n)] || [];
      const total = (q.data.values[0] || []).length;
      for (let i = 0; i < total; i++) {
        spans.push({
          traceId: col('traceID')[i], servico: col('serviceName')[i] || '', operacao: col('operationName')[i] || '',
          inicioMs: Number(col('startTime')[i]),
          tags: paraMapa(col('tags')[i]),
          logs: paraMapa((col('logs')[i] || []).flatMap(l => l.fields || [])),
        });
      }
    }
  });
  if (!spans.length && json && Array.isArray(json.data)) {
    json.data.forEach(t => (t.spans || []).forEach(s => spans.push({
      traceId: s.traceID, servico: ((t.processes || {})[s.processID] || {}).serviceName || '', operacao: s.operationName || '',
      inicioMs: Number(s.startTime) / 1000,   // Jaeger nativo: microssegundos
      tags: paraMapa(s.tags), logs: paraMapa((s.logs || []).flatMap(l => l.fields || [])),
    })));
  }
  return spans.filter(s => isFinite(s.inicioMs)).sort((a, b) => a.inicioMs - b.inicioMs);
}

function confLerTraceRogue(json) {
  const spans = _confSpansDoTrace(json);
  if (!spans.length) return null;
  const p = n => String(n).padStart(2, '0');
  const hora = ms => { const d = new Date(ms); return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };
  const dataDe = ms => { const d = new Date(ms); return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`; };
  const tag = (s, k) => { const v = s.tags['sessionContext.' + k] ?? s.tags[k] ?? s.logs[k]; return v === undefined || v === null ? '' : String(v); };
  const codigoNome = v => { const m = /^\s*(\d+)\s*-\s*(.*)$/.exec(v || ''); return m ? { codigo: m[1], nome: m[2].trim() } : null; };

  const ch = _confNovaChamada(dataDe(spans[0].inicioMs), hora(spans[0].inicioMs), '', '');
  ch.origem = 'rogue';
  ch.traceId = spans[0].traceId || '';
  ch.fim = hora(spans[spans.length - 1].inicioMs);
  const projetos = [], conversas = [], ramais = [];
  const vistos = new Set();
  let ultimaChave = '';
  spans.forEach(s => {
    const h = hora(s.inicioMs);
    const proj = s.tags.project, conv = tag(s, 'conversationId'), ramal = tag(s, 'Extension');
    if (proj && !projetos.includes(proj)) projetos.push(proj);
    if (conv && !conversas.includes(conv)) conversas.push(conv);
    if (ramal && !ramais.includes(ramal)) ramais.push(ramal);
    if (!ch.ani) ch.ani = _confDigitos(tag(s, 'ani') || tag(s, 'fromName'));
    if (!ch.dnis) ch.dnis = tag(s, 'dnis');
    if (s.servico !== 'Dialog') return;

    const estado = s.tags['condition.state'] || '';
    const trans = codigoNome(tag(s, 'spTransition'));
    const prompt = codigoNome(tag(s, 'spPrompt'));
    const novasSaidas = Object.keys(s.tags)
      .map(k => /^(?:sessionContext\.)?tag_transfer_(.+)_(\d+)$/.exec(k))
      .filter(m => m && !vistos.has(m[1] + '|' + m[2]));
    novasSaidas.forEach(m => vistos.add(m[1] + '|' + m[2]));
    // O span de "Transferencia" repete o último SP: só entra o que mudou.
    const chave = `${trans && trans.codigo}|${prompt && prompt.codigo}`;
    const repetido = chave === ultimaChave;
    ultimaChave = chave;

    const partes = [];
    if (trans && !repetido) { ch.sps.push({ codigo: trans.codigo, hora: h, estado, nome: trans.nome }); partes.push(`SP transição ${trans.codigo} - ${trans.nome}`); }
    if (prompt && !repetido) {
      ch.sps.push({ codigo: prompt.codigo, hora: h, estado, nome: prompt.nome });
      ch.prompts.push({ id: prompt.nome, hora: h, estado });
      partes.push(`prompt ${prompt.codigo} - ${prompt.nome}`);
    }
    novasSaidas.forEach(m => {
      ch.digitos.push({ valor: m[2], hora: h, estado: m[1], rotulo: `↪ saída ${m[2]} do estado ${m[1]}` });
      partes.push(`saída ${m[2]} de ${m[1]}`);
    });
    if (/^transfer/i.test(estado)) {
      ch.transferencia = { destino: tag(s, 'transfer'), prompt: '', hora: h };
      partes.push(`TRANSFERÊNCIA ${tag(s, 'transfer')}`);
    }
    if (partes.length) ch.linhas.push(`${h} | ${estado || '—'} | ${partes.join(' | ')}`);
  });
  ch.transacao = conversas.join(', ');
  ch.node = 'ROGUE ' + (projetos.join(' → ') || '');
  ch.resumo = `Trace ${ch.traceId} · ${projetos.join(' → ')}${ramais.length ? ` · ramal(is) ${ramais.join(' → ')}` : ''} · ${conversas.length} conversa(s)`;
  return ch;
}

// Usa um trace (texto JSON do download do Grafana, do Jaeger ou o pacote do favorito). true = carregou.
function _confUsarTrace(texto, nome, manual) {
  let json;
  try { json = JSON.parse(texto); } catch (e) { return 'O conteúdo não é um JSON de trace.'; }
  if (json && json.formato === 'modeler-trace-rogue') {   // pacote do favorito "➜ Enviar ao Modeler"
    nome = `trace ${json.traceId} (Grafana)`;
    json = json.trace;
    texto = JSON.stringify(json, null, 2);
  }
  const ch = confLerTraceRogue(json);
  if (!ch || !ch.sps.length) return 'Não encontrei a jornada da conversa neste trace. Confira se é o trace da ligação (Explore → Jaeger).';
  const ani = _autoValor('ura_rogue', 'ani');
  if (ani && ch.ani && !_confAniBate(ch.ani, ani)
      && !confirm(`O ANI do trace (${ch.ani}) é diferente do ANI configurado (${ani}). Usar este trace mesmo assim?`)) return '';
  confEstado.trace = { nome, texto, manual: !!manual };
  confEstado.chamadas = [ch];
  confEstado.idx = 0;
  confEstado.statusBusca = `✓ Trace ${escHtml(ch.traceId)} carregado — ${escHtml(ch.inicio)}, ANI ${escHtml(ch.ani)}.`;
  renderizarConferencia();
  return true;
}

async function confCarregarTrace(input) {
  const arq = (input.files || [])[0];
  if (!arq) return;
  const r = _confUsarTrace(await arq.text(), arq.name, true);
  if (r !== true) { if (r) alert(r); input.value = ''; }
}

// "📋 Colar trace do Grafana": lê a área de transferência (o navegador pode pedir permissão).
async function confColarTrace() {
  let texto = '';
  try { texto = await navigator.clipboard.readText(); } catch (e) { texto = ''; }
  if (!texto) {
    // Sem permissão para ler: o QA cola com Ctrl+V na caixinha.
    _confStatus('Cole o trace com <strong>Ctrl+V</strong> na caixa abaixo (o navegador não deixou ler a área de transferência).');
    const area = document.querySelector(`#${confModalCt ? 'confModalCorpo' : 'autoConferencia'} #confColarArea`);
    if (area) { area.hidden = false; area.querySelector('textarea').focus(); }
    return;
  }
  const r = _confUsarTrace(texto, 'trace colado');
  if (r !== true && r) _confStatus('⚠️ ' + escHtml(r) + ' Clique no favorito <strong>➜ Enviar ao Modeler</strong> com o trace aberto e tente de novo.');
}
function confColarEvento(ev) {
  ev.preventDefault();
  const r = _confUsarTrace((ev.clipboardData || window.clipboardData).getData('text'), 'trace colado');
  if (r !== true && r) _confStatus('⚠️ ' + escHtml(r));
}

// O favorito manda o trace por postMessage quando a aba do Grafana foi aberta pelo link do Modeler.
window.addEventListener('message', ev => {
  const d = ev.data;
  if (!d || d.formato !== 'modeler-trace-rogue' || autoConfig.tipo !== 'ura_rogue') return;
  let origemGrafana = '';
  try { origemGrafana = new URL(_autoValor('ura_rogue', 'grafana_url') || 'https://grafana-mc1-rogue.hml-sp.claro.internal').origin; } catch (e) {}
  if (ev.origin !== origemGrafana) return;   // só aceita do Grafana configurado
  if (_confUsarTrace(JSON.stringify(d), '') === true) _confAvisoRapido(`Trace ${d.traceId} recebido do Grafana.`);
});

/* ─── Favorito "➜ Enviar ao Modeler" (roda na página do Grafana) ───
   Lê o id do trace da URL do Explore, busca o trace pela sessão do próprio
   Grafana (proxy do Jaeger; se não der, /api/ds/query) e entrega ao Modeler:
   postMessage para a aba que abriu o Grafana + cópia para a área de
   transferência; sem cópia, baixa o arquivo. Sem comentários de linha (vira URL). */
function _confFavorito(MODELER) {
  (async () => {
    const aviso = (t, ok) => {
      const d = document.createElement('div');
      d.textContent = t;
      d.style.cssText = 'position:fixed;z-index:99999;right:20px;bottom:20px;max-width:440px;padding:12px 16px;border-radius:6px;font:600 13px sans-serif;color:#fff;box-shadow:0 4px 16px rgba(0,0,0,.4);background:' + (ok ? '#245C10' : '#9b1c1c');
      document.body.appendChild(d);
      setTimeout(() => d.remove(), 8000);
    };
    try {
      const u = decodeURIComponent(location.href);
      const m = u.match(/"query"\s*:\s*"([0-9a-fA-F]{16,32})"/) || u.match(/\/trace\/([0-9a-fA-F]{16,32})/) || u.match(/traceId=([0-9a-fA-F]{16,32})/i);
      if (!m) { aviso('Modeler: abra o trace da conversa (clique no ConversationId) antes de usar o favorito.'); return; }
      const id = m[1];
      const fontes = Object.values(((window.grafanaBootData || {}).settings || {}).datasources || {});
      const dm = u.match(/"datasource"\s*:\s*"([^"]+)"/) || u.match(/"datasource"\s*:\s*\{[^}]*"uid"\s*:\s*"([^"]+)"/) || u.match(/\["[^"]*","[^"]*","([^"]+)"/);
      const ds = (dm && fontes.find(f => f.uid === dm[1] || f.name === dm[1])) || fontes.find(f => f.type === 'jaeger');
      if (!ds) { aviso('Modeler: não achei a fonte de dados Jaeger neste Grafana.'); return; }
      let trace = null;
      try {
        const r = await fetch('/api/datasources/proxy/uid/' + ds.uid + '/api/traces/' + id, { credentials: 'include' });
        if (r.ok) { const j = await r.json(); if (j && j.data && j.data.length) trace = j; }
      } catch (e) {}
      if (!trace) {
        const r = await fetch('/api/ds/query', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ queries: [{ refId: 'A', datasource: { uid: ds.uid, type: ds.type }, query: id }], from: 'now-30d', to: 'now' }) });
        const j = await r.json();
        trace = (((j || {}).results || {}).A || {}).frames || null;
      }
      if (!trace) { aviso('Modeler: não consegui ler o trace ' + id + '.'); return; }
      const pacote = { formato: 'modeler-trace-rogue', versao: 1, traceId: id, origem: location.href, trace };
      const texto = JSON.stringify(pacote);
      let entregue = false;
      try { if (window.opener) { window.opener.postMessage(pacote, MODELER); entregue = true; } } catch (e) {}
      let copiado = false;
      try { await navigator.clipboard.writeText(texto); copiado = true; } catch (e) {}
      if (!copiado) {
        try { const t = document.createElement('textarea'); t.value = texto; document.body.appendChild(t); t.select(); copiado = document.execCommand('copy'); t.remove(); } catch (e) {}
      }
      if (!copiado && !entregue) {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([texto], { type: 'application/json' }));
        a.download = 'trace_' + id + '.json';
        a.click();
        aviso('Modeler: trace ' + id + ' baixado (trace_' + id + '.json). Carregue no Modeler em "Carregar o trace manualmente".', true);
        return;
      }
      aviso('✓ Trace ' + id + (copiado ? ' copiado. Volte ao Modeler e clique em "📋 Colar trace do Grafana".' : ' enviado ao Modeler.'), true);
    } catch (e) { aviso('Modeler: erro ao ler o trace (' + e.message + ').'); }
  })();
}
function confBookmarklet() {
  return 'javascript:' + encodeURIComponent(`(${_confFavorito.toString()})(${JSON.stringify(location.origin)})`);
}

/* ─── Etapa 3 (sem instalar nada): busca automática na pasta da URA Legado ───
   Chrome/Edge leem uma pasta que o QA autoriza uma vez (File System Access API).
   O QA escolhe \\URA\lmcti\Data; a ferramenta abre UraLog\AAAA\MM\DD, lê os
   URADebug do node da URA (todos os canais), acha as chamadas do ANI e carrega o
   IntegracaoDebug do mesmo canal. A autorização fica guardada neste navegador
   (o navegador pode pedir "Permitir" de novo em outra sessão). */

let confPastas = {};             // uraId → FileSystemDirectoryHandle autorizado
let _confPastasLidas = false;

function _confHojeIso() {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// As pastas autorizadas antes ficam no IndexedDB; carrega uma vez e redesenha.
async function _confCarregarPastasSalvas() {
  if (_confPastasLidas) return;
  _confPastasLidas = true;
  try {
    for (const u of AUTO_DESTINOS.ura_legado.itens) {
      const h = await dbGet('estado', 'pasta_ura_' + u.id);
      if (h) confPastas[u.id] = h;
    }
    if (Object.keys(confPastas).length) renderizarConferencia();
  } catch (e) { /* sem IndexedDB: pede a pasta a cada sessão */ }
}

async function confTrocarPasta() {
  const ura = _autoDestinoEscolhido('ura_legado');
  if (!ura) return;
  delete confPastas[ura.id];
  try { await dbDelete('estado', 'pasta_ura_' + ura.id); } catch (e) {}
  confEstado.statusBusca = '';
  renderizarConferencia();
}

function _confStatus(html) {
  confEstado.statusBusca = html;
  const el = document.querySelector(`#${confModalCt ? 'confModalCorpo' : 'autoConferencia'} .conf-auto-status`);
  if (el) el.innerHTML = html; else renderizarConferencia();
}

async function _confSubpasta(dir, nome) {
  try { return await dir.getDirectoryHandle(nome); } catch (e) { return null; }
}

// Aceita a pasta Data, a lmcti ou a raiz do compartilhamento.
async function _confAcharData(raiz) {
  if (await _confSubpasta(raiz, 'UraLog')) return raiz;
  const data = await _confSubpasta(raiz, 'Data');
  if (data && await _confSubpasta(data, 'UraLog')) return data;
  const lmcti = await _confSubpasta(raiz, 'lmcti');
  const data2 = lmcti && await _confSubpasta(lmcti, 'Data');
  if (data2 && await _confSubpasta(data2, 'UraLog')) return data2;
  return null;
}

async function _confAbrirCaminho(dir, partes) {
  for (const p of partes) { dir = await _confSubpasta(dir, p); if (!dir) return null; }
  return dir;
}

async function _confLerTexto(fileHandle) {
  const arq = await fileHandle.getFile();
  return new TextDecoder('windows-1252').decode(await arq.arrayBuffer());
}

async function confBuscarNaPasta() {
  const ura = _autoDestinoEscolhido('ura_legado');
  if (!ura) return;
  if (!window.showDirectoryPicker) {
    _confStatus('⚠️ Este navegador não deixa abrir pastas. Use o <strong>Chrome</strong> ou o <strong>Edge</strong>, ou carregue os logs manualmente abaixo.');
    return;
  }
  const aniEl = document.querySelector(`#${confModalCt ? 'confModalCorpo' : 'autoConferencia'} #confAni`);
  const diaEl = document.querySelector(`#${confModalCt ? 'confModalCorpo' : 'autoConferencia'} #confDia`);
  const ani = _confDigitos(aniEl ? aniEl.value : '');
  const dia = (diaEl && diaEl.value) || _confHojeIso();
  confEstado.aniBusca = aniEl ? aniEl.value : '';
  confEstado.dia = dia;
  if (ani.length < 8) { _confStatus('⚠️ Informe o ANI que fez a ligação (DDD + número).'); return; }

  // 1. Pasta autorizada (pede na primeira vez; a permissão exige o clique do botão).
  let raiz = confPastas[ura.id];
  try {
    if (!raiz) raiz = await window.showDirectoryPicker({ id: 'ura_' + ura.node, mode: 'read' });
    if ((await raiz.queryPermission({ mode: 'read' })) !== 'granted'
        && (await raiz.requestPermission({ mode: 'read' })) !== 'granted') {
      _confStatus('⚠️ Sem permissão para ler a pasta. Clique de novo e escolha <em>Permitir</em>.');
      return;
    }
  } catch (e) {
    if (e && e.name === 'AbortError') return;   // fechou a janela de escolha
    _confStatus(`⚠️ Não foi possível abrir a pasta (${escHtml(e && e.message || e)}). Confira a VPN ou carregue os logs manualmente.`);
    return;
  }
  const data = await _confAcharData(raiz);
  if (!data) {
    _confStatus(`⚠️ A pasta escolhida (<strong>${escHtml(raiz.name)}</strong>) não tem <code>UraLog</code>. Escolha <code>\\\\${escHtml(ura.host || ura.nome)}\\lmcti\\Data</code> — <a href="#" onclick="confTrocarPasta(); return false;">trocar pasta</a>.`);
    return;
  }
  confPastas[ura.id] = raiz;
  try { await dbPut('estado', raiz, 'pasta_ura_' + ura.id); } catch (e) {}

  // 2. Arquivos do dia deste node (um por canal).
  const [a, m, d] = dia.split('-');
  const dirUra = await _confAbrirCaminho(data, ['UraLog', a, m, d]);
  if (!dirUra) { _confStatus(`⚠️ Não há logs em <code>UraLog\\${a}\\${m}\\${d}</code> nesta URA. Confira o dia da ligação.`); return; }
  const padrao = new RegExp(`^URADebug_${a}-${m}-${d}_${ura.node}_(\\d+)\\.txt$`, 'i');
  const arquivos = [];
  for await (const [nome, h] of dirUra.entries()) if (h.kind === 'file' && padrao.test(nome)) arquivos.push([nome, h]);
  if (!arquivos.length) { _confStatus(`⚠️ Nenhum URADebug do node ${escHtml(ura.node)} em ${d}/${m}/${a}.`); return; }

  // 3. Procura o ANI em todos os canais (filtro rápido pelo texto antes de separar as chamadas).
  const achadas = [];
  const fimAni = ani.slice(-8);
  let lidos = 0;
  for (const [nome, h] of arquivos) {
    _confStatus(`⏳ Procurando o ANI ${escHtml(ani)} — ${++lidos} de ${arquivos.length} arquivo(s)…`);
    let texto;
    try { texto = await _confLerTexto(h); } catch (e) { continue; }
    if (!texto.includes(fimAni)) continue;
    const doAni = confSepararChamadas(texto).filter(c => _confAniBate(c.ani, ani));
    if (!doAni.length) continue;
    const arqUra = { nome, texto };
    let arqInteg = null;
    const sufixo = _confSufixo(nome);
    const dirInt = await _confAbrirCaminho(data, ['IntegracaoLog', a, m, d]);
    if (dirInt && sufixo) {
      try {
        const nomeInt = `IntegracaoDebug_${sufixo}.txt`;
        arqInteg = { nome: nomeInt, texto: await _confLerTexto(await dirInt.getFileHandle(nomeInt)) };
      } catch (e) { arqInteg = null; }
    }
    doAni.forEach(c => { c._arquivos = { ura: arqUra, integracao: arqInteg }; achadas.push(c); });
  }
  if (!achadas.length) {
    _confStatus(`⚠️ Nenhuma chamada do ANI <strong>${escHtml(ani)}</strong> em ${arquivos.length} arquivo(s) de ${d}/${m}/${a} (${escHtml(ura.nome)}). Confira o ANI, o dia e se a ligação caiu nesta URA.`);
    return;
  }
  // A mais recente primeiro: em geral é a ligação que acabou de ser feita.
  achadas.sort((x, y) => y.inicio.localeCompare(x.inicio));
  confEstado.chamadas = achadas;
  confEstado.viaPasta = true;
  confEstado.statusBusca = `✓ ${achadas.length} chamada(s) do ANI ${escHtml(ani)} em ${d}/${m}/${a}` +
    ` (canal ${[...new Set(achadas.map(c => +c.canal))].join(', ')}). Mostrando a mais recente; troque na lista se precisar.`;
  confEscolherChamada(0);
}
