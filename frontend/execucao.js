/* ─── Execução guiada do plano de testes ───
   "▶ Iniciar execução do plano" (aba Automação / Execução dos Testes) percorre os CTs
   selecionados; "▶ Executar" (em cada CT) roda só aquele. Para cada CT mostra o número a
   discar (formato Avaya), o código da esteira (ROGUE) e as teclas/prompts de cada passo.
   O QA liga (o 📞 abre o discador do computador, ex.: Avaya one-X, se ele atende links
   tel:), segue os passos e clica em "Terminei a ligação": abre a conferência do CT, que
   busca a evidência sozinha (URA Legado: pasta autorizada). Ao aplicar o resultado, segue
   para o próximo CT. A ligação em si ainda é feita pelo QA (a discagem automática é a etapa 4). */

let execFila = [];      // ct_ids a executar
let execPos = 0;
let execInicio = null;  // Date do início, para o resumo
let execAtivo = false;

function _execCaso(ctId) {
  return ((cacheModelagem && cacheModelagem.casos_teste) || []).find(c => c.ct_id === ctId) || null;
}
function _execStatus(ctId) {
  return ((avaliacoesQA[ctId] || {}).status) || 'pendente';
}

// Antes de começar: tecnologia e URA/esteira escolhidas (a ligação e a evidência dependem delas).
function _execProntoParaComecar() {
  const tipo = autoConfig.tipo;
  if (tipo !== 'ura_legado' && tipo !== 'ura_rogue') {
    return tipo === 'chatbot'
      ? 'A execução guiada do ChatBOT ainda não está disponível.'
      : 'Escolha a tecnologia (URA Legado ou URA ROGUE) na aba 🤖 Automação.';
  }
  if (!_autoDestinoEscolhido(tipo)) return `Escolha ${tipo === 'ura_rogue' ? 'a esteira' : 'a URA'} na aba 🤖 Automação.`;
  return '';
}

/* ─── entrada ─── */
function execIniciarPlano() {
  if (!cacheModelagem) return;
  const falta = _execProntoParaComecar();
  const casos = _autoCasosSelecionados();
  const pendentes = casos.filter(c => _execStatus(c.ct_id) === 'pendente');
  _execAbrir(`
    <h4 class="exec-g-titulo">▶ Executar o plano de testes</h4>
    ${falta ? `<p class="conf-alerta">⚠️ ${falta}</p><button class="btn-export-pdf" onclick="execFechar(); confIrParaAutomacao();">Ir para a aba Automação</button>` : `
    <p class="bi-nota">${escHtml(AUTO_TIPOS[autoConfig.tipo].rotulo)} · ${escHtml(_autoDestinoEscolhido(autoConfig.tipo).nome)} · discar <strong>${escHtml(autoNumeroDiscar(autoConfig.tipo))}</strong></p>
    <p class="bi-nota">A ferramenta mostra um CT por vez: você liga, segue os passos e clica em <strong>Terminei a ligação</strong>; ela busca a evidência, confere e grava o resultado, e passa para o próximo. Dá para pular, pausar e retomar depois.</p>
    <div class="exec-g-opcoes">
      <button class="btn-export-pdf" ${pendentes.length ? '' : 'disabled'} onclick="execComecar('pendentes')">▶ Só os pendentes (${pendentes.length})</button>
      <button class="btn-export-pdf exec-g-sec" ${casos.length ? '' : 'disabled'} onclick="execComecar('todos')">▶ Todos os selecionados (${casos.length})</button>
    </div>
    <p class="exec-g-dica">Os CTs do plano são os marcados em “CTs que entram no roteiro”, na aba Automação.</p>`}`);
}

function execComecar(modo) {
  const casos = _autoCasosSelecionados();
  execFila = (modo === 'pendentes' ? casos.filter(c => _execStatus(c.ct_id) === 'pendente') : casos).map(c => c.ct_id);
  if (!execFila.length) return;
  execPos = 0;
  execInicio = new Date();
  execAtivo = true;
  _execMostrarCt();
}

function execExecutarCt(ctId) {
  if (!cacheModelagem || !_execCaso(ctId)) return;
  const falta = _execProntoParaComecar();
  if (falta) {
    _execAbrir(`<h4 class="exec-g-titulo">▶ Executar ${escHtml(ctId)}</h4><p class="conf-alerta">⚠️ ${falta}</p>
      <button class="btn-export-pdf" onclick="execFechar(); confIrParaAutomacao();">Ir para a aba Automação</button>`);
    return;
  }
  execFila = [ctId];
  execPos = 0;
  execInicio = new Date();
  execAtivo = true;
  _execMostrarCt();
}

/* ─── tela de um CT ─── */
function _execMostrarCt() {
  const ctId = execFila[execPos];
  const caso = _execCaso(ctId);
  if (!caso) { _execProximo(); return; }
  const tipo = autoConfig.tipo;
  const destino = _autoDestinoEscolhido(tipo);
  const numero = autoNumeroDiscar(tipo);
  const digitos = String(numero).replace(/\D/g, '');
  const roteiro = _autoCasoParaRoteiro(caso);
  const status = _execStatus(ctId);
  const total = execFila.length;
  const feitos = execFila.filter(id => _execStatus(id) !== 'pendente').length;

  const passos = roteiro.passos.map(p => `
    <tr>
      <td>${p.n}</td>
      <td>${escHtml(p.acao)}${p.dtmf_sugerido ? ` <span class="exec-g-tecla" title="Tecla a digitar">⌨️ ${escHtml(p.dtmf_sugerido)}</span>` : ''}</td>
      <td><span class="step-state">${escHtml(p.estado)}</span></td>
      <td>${p.prompt_id ? `<div class="step-prompt-id">${escHtml(p.prompt_id)}</div>` : ''}<div class="exec-g-ouvir">${escHtml(p.resultado_esperado || '')}</div></td>
    </tr>`).join('');

  _execAbrir(`
    <div class="exec-g-progresso">
      <span>CT ${execPos + 1} de ${total}${total > 1 ? ` · ${feitos} com resultado` : ''}</span>
      <div class="exec-g-barra"><div style="width:${Math.round((execPos / total) * 100)}%"></div></div>
    </div>
    <h4 class="exec-g-titulo">${escHtml(ctId)} — ${escHtml(caso.estado)}
      <span class="eval-select ${status}" style="font-size:11px;padding:2px 8px;">${escHtml(_STATUS_ROTULO[status] || status)}</span></h4>
    <p class="exec-g-gherkin">${escHtml(caso.gherkin)}</p>
    <p class="exec-g-prereq"><strong>Pré-requisito:</strong> ${escHtml(caso.pre_requisito || '—')}</p>

    <div class="exec-g-ligar">
      <div>
        <div class="exec-g-rotulo">1. Ligue para ${escHtml(destino.nome)}</div>
        <div class="exec-g-numero">${escHtml(numero)}</div>
        <small>Digite no Avaya: <code>${escHtml(digitos)}</code>${destino.codigo ? ` · ao atender, digite o código da esteira <code>${escHtml(destino.codigo)}</code>` : ''}</small>
      </div>
      <a class="btn-export-pdf exec-g-btn-ligar" href="tel:${escHtml(digitos)}" title="Abre o discador do computador (ex.: Avaya one-X), se ele estiver configurado para links de telefone">📞 Ligar</a>
    </div>

    <div class="exec-g-rotulo">2. Siga os passos (teclas e o que deve tocar)</div>
    <div class="history-table-wrap"><table class="data-table exec-g-passos">
      <thead><tr><th style="width:44px;">Step</th><th>Ação</th><th style="width:170px;">Estado</th><th>O que deve tocar / resultado</th></tr></thead>
      <tbody>${passos || '<tr><td colspan="4">Sem steps neste CT.</td></tr>'}</tbody>
    </table></div>
    <p class="exec-g-dica">SPs que serão conferidos: <code>${escHtml(roteiro.sps_esperados.join(', ') || '—')}</code></p>

    <div class="exec-g-acoes">
      <button class="btn-export-pdf" onclick="execTerminei()">✓ Terminei a ligação — conferir evidência</button>
      ${total > 1 ? `<button class="btn-export-pdf exec-g-sec" onclick="execPular()">Pular este CT ⏭</button>` : ''}
      ${total > 1 && execPos > 0 ? `<button class="btn-export-pdf exec-g-sec" onclick="execVoltar()">⏮ Anterior</button>` : ''}
      <button class="btn-export-pdf exec-g-sec" onclick="execEncerrar()">${total > 1 ? 'Pausar / encerrar' : 'Fechar'}</button>
    </div>`, `▶ Execução — ${ctId}`);
}

function execTerminei() {
  const ctId = execFila[execPos];
  document.getElementById('execModal').classList.remove('aberto');
  confAbrirModal(ctId);
  // URA Legado com a pasta já autorizada: busca a chamada sem precisar de outro clique.
  if (autoConfig.tipo === 'ura_legado') {
    const ura = _autoDestinoEscolhido('ura_legado');
    const ani = _autoValor('ura_legado', 'ani') || confEstado.aniBusca;
    if (ura && confPastas[ura.id] && _confDigitos(ani).length >= 8) confBuscarNaPasta();
  }
}

// Chamado pela conferência ao fechar (conferencia.js): volta para a execução.
function execAposConferencia(ctId) {
  if (!execAtivo || execFila[execPos] !== ctId) return;
  if (_execStatus(ctId) !== 'pendente') _execProximo();
  else _execMostrarCt();   // fechou sem aplicar: continua no mesmo CT
}

function _execProximo() {
  execPos++;
  if (execPos >= execFila.length) _execResumo();
  else _execMostrarCt();
}
function execPular() { _execProximo(); }
function execVoltar() { if (execPos > 0) { execPos--; _execMostrarCt(); } }

function execEncerrar() {
  if (execFila.length > 1) _execResumo(true);
  else execFechar();
}

function _execResumo(pausado) {
  const cont = { ok: 0, nok: 0, blocked: 0, pendente: 0 };
  execFila.forEach(id => { cont[_execStatus(id)] = (cont[_execStatus(id)] || 0) + 1; });
  const min = execInicio ? Math.max(1, Math.round((Date.now() - execInicio) / 60000)) : 0;
  const pend = execFila.filter(id => _execStatus(id) === 'pendente');
  execAtivo = false;
  _execAbrir(`
    <h4 class="exec-g-titulo">${pausado ? '⏸ Execução pausada' : '🏁 Execução concluída'}</h4>
    <div class="exec-g-resumo">
      <div class="ok"><strong>${cont.ok}</strong>OK</div>
      <div class="nok"><strong>${cont.nok}</strong>Não OK</div>
      <div class="blocked"><strong>${cont.blocked}</strong>Bloqueado</div>
      <div class="pendente"><strong>${cont.pendente}</strong>Pendente</div>
    </div>
    <p class="bi-nota">${execFila.length} CT(s) no plano · ${min} min. Os resultados e evidências estão na aba <strong>Execução dos Testes</strong>; exporte o PDF + ZIP ao terminar.</p>
    ${pend.length ? `<p class="exec-g-dica">Pendentes: ${pend.map(escHtml).join(', ')}</p>` : ''}
    <div class="exec-g-acoes">
      ${pend.length ? `<button class="btn-export-pdf" onclick="execComecar('pendentes')">▶ Continuar pelos pendentes (${pend.length})</button>` : ''}
      <button class="btn-export-pdf exec-g-sec" onclick="execFechar()">Fechar</button>
    </div>`, 'Resumo da execução');
}

/* ─── janela ─── */
function _execAbrir(html, titulo) {
  document.getElementById('execModalTitulo').textContent = titulo || '▶ Execução do plano de testes';
  document.getElementById('execModalCorpo').innerHTML = html;
  document.getElementById('execModal').classList.add('aberto');
  document.getElementById('execModalCorpo').scrollTop = 0;
}
function execFechar() {
  execAtivo = false;
  document.getElementById('execModal').classList.remove('aberto');
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && document.getElementById('execModal') && document.getElementById('execModal').classList.contains('aberto')) execEncerrar();
});
