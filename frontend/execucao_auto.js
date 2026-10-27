/* ─── Execução AUTOMÁTICA: o executor local (executor/executor_avaya.py) liga pelo Avaya one-X ───
   O site manda cada CT para http://127.0.0.1:47123/executar, acompanha /execucao e, ao
   terminar, recebe o log da chamada (URA Legado) ou o trace (ROGUE). A conferência e a
   gravação do resultado são as mesmas da conferência manual (conferencia.js), sem janela. */

const EXECUTOR_URL = 'http://127.0.0.1:47123';
const GRAFANA_DS_UID_ROGUE = 'PC9A941E8F2E49454';   // fonte Jaeger do Grafana do ROGUE (do link do Explore)
const GRAFANA_CHATBOT = 'http://10.169.0.216:30300';   // Grafana das evidências do ChatBOT (Conversation Finder; exige login)
let execAuto = { ativo: false, parar: false };
const EXECUTOR_VERSAO_MIN = '1.12';   // versão do executor_avaya.py que este site espera
function _execExecutorAntigo(st) { return !!st && _execVersaoMenor(st.versao || '0', EXECUTOR_VERSAO_MIN); }
const _MSG_EXECUTOR_ANTIGO = '⚠️ O executor desta máquina é de uma versão antiga. Feche a janela dele, baixe de novo em <strong>🤖 Automação → Executor automático</strong> e abra o novo <code>iniciar_executor.bat</code>.';

async function execExecutorStatus() {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 2500);
    const r = await fetch(`${EXECUTOR_URL}/status`, { signal: ctrl.signal });
    clearTimeout(t);
    const j = await r.json();
    return j && j.executor === 'modeler-avaya' ? j : null;
  } catch (e) { return null; }
}

async function _execAtualizarStatusAuto(nPend, nTodos) {
  const el = document.getElementById('execAutoStatus');
  if (!el) return;
  const st = await execExecutorStatus();
  const chat = autoConfig.tipo === 'chatbot';
  const ok = st && (chat || st.onex_aberto) && !_execExecutorAntigo(st);
  el.innerHTML = _execExecutorAntigo(st) ? _MSG_EXECUTOR_ANTIGO : (chat && st) ? `✓ Executor v${escHtml(st.versao)} pronto para o ChatBOT (WhatsApp Web).` : !st
    ? '⚠️ Executor não encontrado nesta máquina. Baixe e inicie o executor na aba <strong>🤖 Automação</strong> (seção “Executor automático”), com o Avaya one-X aberto.'
    : (!st.onex_aberto
      ? `⚠️ Executor v${escHtml(st.versao)} rodando, mas o <strong>Avaya one-X</strong> não está aberto. Abra e faça login.`
      : `✓ Executor v${escHtml(st.versao)} pronto e Avaya one-X aberto.${st.ocupado ? ` (executando ${escHtml(st.ct_atual)})` : ''}`);
  const b1 = document.getElementById('btnAutoPend'), b2 = document.getElementById('btnAutoTodos');
  if (b1) b1.disabled = !ok || !nPend;
  if (b2) b2.disabled = !ok || !nTodos;
}

function _norm2(s) { return String(s || '').toLowerCase().normalize('NFD').replace(/[^a-z0-9]/g, ''); }

// Teclas de cada passo: o DTMF da modelagem ou, quando o passo pede um dado (CPF, CEP…), a massa do CT.
function _execDigitosDoPasso(passo, massa) {
  if (passo.dtmf_sugerido) return passo.dtmf_sugerido;
  const t = _norm2(`${passo.acao} ${passo.estado} ${passo.prompt_id || ''}`);
  if (/cep/.test(t)) return massa.cep;
  if (/numcasa|numerocasa|numeroendereco|numerodaresidencia/.test(t)) return massa.numero;
  if (/contrato|codigonet|codnet/.test(t)) return massa.contrato;
  if (/cnpj/.test(t)) return massa.cnpj || massa.cpf;
  if (/cpf|documento/.test(t)) return massa.cpf;
  return '';
}

// Dado que o bot pede no estado (ColetaCNPJ, ColetaEmail…) -> campo da massa.
function _execCampoMassaDoEstado(estado) {
  const t = _norm2(estado);
  if (/cnpj/.test(t)) return 'cnpj';
  if (/cpf/.test(t)) return 'cpf';
  if (/email/.test(t)) return 'email';
  if (/nasc|datanasc/.test(t)) return 'nascimento';
  if (/celular|telefone|fone|whats/.test(t)) return 'celular';
  if (/nome/.test(t)) return 'nome';
  if (/cep/.test(t)) return 'cep';
  if (/contrato/.test(t)) return 'contrato';
  return '';
}
const _RX_PARECE_REGEX = /[\\^$*+?{}|]|\[0-9|\[a-z]-/i;

// Conversa do ChatBOT: começa com a mensagem inicial ("SIM"); em cada passo, o botão/texto que a SPEC
// aceita naquela transição (coluna "Dígito / Valor") ou, se o bot pediu um dado, o valor da massa.
// Última(s) condição(ões) do caminho do passo: é ela que diz o que o QA faz naquele ponto.
// "Navegar (🏁 Início > API … SIM > ⬇️ Não é elegível > 💣 [No input] Mensagem em formato não suportado)" -> "[No input] …"
function _execCondicaoFinal(acao) {
  const m = /\((.*)\)\s*$/.exec(String(acao || ''));
  const partes = (m ? m[1] : String(acao || '')).split(/\s+>\s+/);
  return partes.slice(-2).join(' > ');
}

function _execPassosChat(roteiro, massa, inicial) {
  const passos = [];
  let iniciou = false;   // a conversa já foi aberta por uma mensagem do QA
  const abrir = () => passos.push({ n: 1, estado: '_Start_', tipo: 'texto', texto: inicial, opcoes: [], esperado: '' });
  roteiro.passos.forEach((p, i) => {
    if (i === 0) return;                                 // _Start_
    if (/^encerrar/i.test(p.acao || '') || p.estado === '-') return;
    const anterior = roteiro.passos[i - 1] || {};
    const textoPrompt = p.prompt_texto && p.prompt_texto !== '—' ? p.prompt_texto : '';
    // "@{semMensagem}" / "Sem mensagem": o esperado é o bot NÃO responder.
    const semResposta = /sem\s*mensagem|semMensagem/i.test(textoPrompt);
    const base = { n: p.n, estado: p.estado, esperado: semResposta ? '' : textoPrompt, sem_resposta: semResposta };
    const cond = _execCondicaoFinal(p.acao);
    let acao;
    if (/no ?input|formato n[aã]o suportado|figurinha|[aá]udio, /i.test(cond)) {
      acao = { tipo: 'invalido', texto: '😀', opcoes: [] };            // entrada inválida: um emoji (não é "Sim")
    } else if (/inten[cç][aã]o n[aã]o identificada|outras inten[cç]|\bnone\b/i.test(cond)) {
      acao = { tipo: 'invalido', texto: 'xqzw', opcoes: [] };          // texto que o bot não entende
    } else if (/sil[eê]ncio/i.test(cond)) {
      acao = { tipo: 'silencio', texto: '', opcoes: [] };
    } else {
      const entradas = p.entradas || [];
      const opcoes = entradas.filter(e => !_RX_PARECE_REGEX.test(e));
      const pedeDado = !opcoes.length || entradas.some(e => _RX_PARECE_REGEX.test(e));
      const campo = _execCampoMassaDoEstado(anterior.estado);
      if (pedeDado && campo) {
        // O bot pede um dado (CPF, CNPJ, nome…): manda a massa; sem massa, o CT para com aviso.
        acao = massa[campo] ? { tipo: 'texto', texto: massa[campo], opcoes: [] } : { tipo: 'falta_massa', campo, texto: '', opcoes: [] };
      } else if (!iniciou && opcoes.some(o => /^sim\b/i.test(o))) {
        acao = { tipo: 'texto', texto: inicial, opcoes: [] };          // o "SIM" que inicia a jornada
      } else if (opcoes.length) {
        acao = { tipo: 'botao', texto: opcoes[0], opcoes };           // clica no botão; o texto é a reserva
      } else {
        acao = { tipo: 'auto', texto: '', opcoes: [] };               // o bot segue sozinho (API, switch)
      }
    }
    // Abertura da conversa: se a 1ª ação do CT não é ela mesma uma mensagem do QA (silêncio, passo
    // automático, falta de massa), a conversa abre com o "SIM". Se for (ex.: entrada inválida), abre com ela.
    if (!iniciou) {
      if (!['texto', 'botao', 'invalido'].includes(acao.tipo)) abrir();
      if (acao.tipo === 'botao') { abrir(); }
      iniciou = true;
    }
    passos.push({ ...base, ...acao });
  });
  if (!iniciou) abrir();
  return passos;
}

function _execPedido(ctId) {
  const tipo = autoConfig.tipo;
  if (tipo === 'chatbot') {
    const roteiro = _autoCasoParaRoteiro(_execCaso(ctId));
    const inicial = _autoValor('chatbot', 'bot_msg_inicial') || 'SIM';
    return {
      ct_id: ctId, tecnologia: 'chatbot',
      bot_numero: String(_autoValor('chatbot', 'bot_numero') || '551136310228').replace(/\D/g, ''),
      mensagem_inicial: inicial,
      espera_resposta: Math.max(30, parseInt(_autoValor('chatbot', 'bot_espera'), 10) || 180),
      grafana_url: _autoValor('chatbot', 'grafana_url') || GRAFANA_CHATBOT,
      sps_esperados: roteiro.sps_esperados || [],
      passos: _execPassosChat(roteiro, massaDoCt(ctId), inicial),
      fim_textos: roteiro.passos.filter(x => x.estado === '_End_' && x.prompt_texto && x.prompt_texto !== '—').map(x => x.prompt_texto),
    };
  }
  const destino = _autoDestinoEscolhido(tipo);
  const roteiro = _autoCasoParaRoteiro(_execCaso(ctId));
  const massa = massaDoCt(ctId);
  return {
    ct_id: ctId,
    tecnologia: tipo,
    numero: String(autoNumeroDiscar(tipo)).replace(/\D/g, ''),
    dtmf_ao_atender: destino && destino.codigo ? destino.codigo : '',
    ura: tipo === 'ura_legado' && destino ? { host: destino.host || destino.nome, ip: destino.ip, node: destino.node } : null,
    ani: _autoValor(tipo, 'ani'),
    passos: roteiro.passos.map(p => ({ n: p.n, estado: p.estado, prompt_id: p.prompt_id, acao: p.acao, digitos: _execDigitosDoPasso(p, massa) || '' })),
    grafana_url: _autoValor('ura_rogue', 'grafana_url') || 'https://grafana-mc1-rogue.hml-sp.claro.internal',
    grafana_ds_uid: GRAFANA_DS_UID_ROGUE,
  };
}

async function execAutoComecar(modo) {
  const casos = _autoCasosSelecionados();
  const filtro = { pendentes: c => _execStatus(c.ct_id) === 'pendente', bloqueados: c => _execStatus(c.ct_id) === 'blocked' }[modo];
  execFila = (filtro ? casos.filter(filtro) : casos).map(c => c.ct_id);
  if (!execFila.length) return;
  execPos = 0;
  execInicio = new Date();
  execAtivo = false;           // a execução guiada não reage à conferência
  execAuto = { ativo: true, parar: false };
  execUltimaFoiAuto = true;
  while (execPos < execFila.length && !execAuto.parar) {
    await _execAutoUmCt(execFila[execPos]);
    execPos++;
  }
  execAuto.ativo = false;
  if (!execAuto.fechado) _execResumo(execAuto.parar);
}

function execAutoParar() {
  execAuto.parar = true;
  const b = document.getElementById('btnPararAuto');
  if (b) { b.disabled = true; b.textContent = '⏳ Parando… (desligando a chamada)'; }
  fetch(`${EXECUTOR_URL}/parar`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => {});
}

function _execAutoTela(ctId, pedido, estado, eventos) {
  if (execAuto.fechado) return;   // o QA fechou a janela: não reabre
  const caso = _execCaso(ctId);
  const faltaMassa = pedido.passos.filter(p => /cpf|cnpj|cep|contrato/i.test(`${p.acao} ${p.estado}`) && !p.digitos);
  _execAbrir(`
    <div class="exec-g-progresso">
      <span>🤖 CT ${execPos + 1} de ${execFila.length}</span>
      <div class="exec-g-barra"><div style="width:${Math.round((execPos / execFila.length) * 100)}%"></div></div>
    </div>
    <h4 class="exec-g-titulo">${escHtml(ctId)} — ${escHtml(caso.estado)} <span class="exec-g-estado">${escHtml(estado)}</span></h4>
    ${pedido.tecnologia === 'chatbot'
      ? `<p class="exec-g-dica">💬 Bot <code>${escHtml(pedido.bot_numero)}</code> · mensagens: <code>${escHtml(pedido.passos.filter(p => p.texto).map(p => p.texto).join(' → ') || '—')}</code></p>`
      : `<p class="exec-g-dica">Discando <code>${escHtml(pedido.numero)}</code>${pedido.dtmf_ao_atender ? ` · esteira <code>${escHtml(pedido.dtmf_ao_atender)}</code>` : ''} ·
      teclas: <code>${escHtml(pedido.passos.filter(p => p.digitos).map(p => p.digitos).join(' → ') || '—')}</code></p>`}
    ${faltaMassa.length ? `<p class="conf-alerta">⚠️ Sem massa para ${faltaMassa.map(p => 'step ' + p.n).join(', ')} — preencha na aba Massa de Testes.</p>` : ''}
    <pre class="exec-g-log">${escHtml((eventos || []).join('\n') || '…')}</pre>
    <div class="exec-g-acoes"><button class="btn-export-pdf exec-g-sec" id="btnPararAuto" onclick="execAutoParar()" ${execAuto.parar ? 'disabled' : ''}>${execAuto.parar ? '⏳ Parando… (desligando a chamada)' : '⏹ Parar a execução'}</button></div>`,
    `🤖 Execução automática — ${ctId}`);
}

async function _execAutoUmCt(ctId) {
  const pedido = _execPedido(ctId);
  _execAutoTela(ctId, pedido, 'enviando ao executor', []);
  let r = null;
  try {
    r = await fetch(`${EXECUTOR_URL}/executar`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pedido) });
  } catch (e) { r = null; }
  if (!r || !r.ok) {
    const j = r ? await r.json().catch(() => ({})) : {};
    execAuto.parar = true;
    _execAutoTela(ctId, pedido, 'erro', [`Executor não respondeu: ${j.erro || 'confira se o executor está aberto'}`]);
    await _aguardar(2500);
    execPos--;   // o CT não foi executado: continua pendente
    return;
  }
  let ex = null;
  for (;;) {
    await _aguardar(1500);
    try { ex = await (await fetch(`${EXECUTOR_URL}/execucao`)).json(); } catch (e) { ex = null; }
    if (!ex) { _execAutoTela(ctId, pedido, 'sem contato com o executor…', []); continue; }
    _execAutoTela(ctId, pedido, { discando: 'discando', em_chamada: 'em chamada', concluida: 'conferindo', erro: 'erro', parado: 'parado' }[ex.estado] || ex.estado, ex.eventos);
    if (ex.estado === 'concluida' || ex.estado === 'erro' || ex.estado === 'parado') break;
  }
  if (ex.estado === 'parado') {   // o QA parou: o CT continua pendente
    salvarDadosExecucao(ctId, 'comments', `[Auto ${new Date().toLocaleTimeString('pt-BR')}] execução parada pelo QA.`);
    return;
  }
  if (ex.estado === 'erro') {
    salvarDadosExecucao(ctId, 'status', 'blocked');
    salvarDadosExecucao(ctId, 'comments', `[Auto] erro na execução: ${ex.erro}`);
    await _aguardar(1500);
    return;
  }
  // Conferência automática com a evidência que o executor trouxe.
  const res = ex.resultado || {};
  if (res.tipo === 'chatbot') {
    const sug = await _execAplicarChat(ctId, pedido, res, ex.eventos || []);
    _execAutoTela(ctId, pedido, `resultado: ${_STATUS_ROTULO[sug] || sug}`, ex.eventos);
    await _aguardar(1500);
    return;
  }
  confSilencioso = true;
  try {
    confEstado = { tipo: autoConfig.tipo, ctId, ura: null, integracao: null, trace: null, chamadas: [], idx: -1 };
    let ok = false;
    if (res.tipo === 'ura_legado' && res.ura_texto) {
      const chs = confSepararChamadas(res.ura_texto);
      if (chs.length) {
        confEstado.ura = { nome: res.ura_arquivo || 'URADebug.txt', texto: res.ura_texto };
        confEstado.integracao = res.integracao_texto ? { nome: res.integracao_arquivo || 'IntegracaoDebug.txt', texto: res.integracao_texto } : null;
        confEstado.chamadas = chs;
        confEstado.idx = 0;
        ok = true;
      }
    } else if (res.tipo === 'ura_rogue' && res.trace) {
      ok = _confUsarTrace(JSON.stringify(res.trace), 'trace (executor)') === true;
      confEstado.ctId = ctId;
    }
    if (ok) {
      const sug = await confAplicar();
      _execAutoTela(ctId, pedido, `resultado: ${_STATUS_ROTULO[sug] || sug}`, ex.eventos);
    } else {
      salvarDadosExecucao(ctId, 'comments', `[Auto ${new Date().toLocaleTimeString('pt-BR')}] chamada feita, sem evidência automática (${res.erro || 'log não encontrado'}) — confira manualmente.`);
      _execAutoTela(ctId, pedido, 'sem evidência automática', ex.eventos);
    }
  } finally {
    confSilencioso = false;
  }
  await _aguardar(1500);
}

/* ─── seção "Executor automático" da aba Automação ─── */
async function renderizarExecutorAuto() {
  const el = document.getElementById('autoExecutor');
  if (!el) return;
  el.innerHTML = `
    ${autoConfig.tipo === 'chatbot'
      ? `<p class="bi-nota">Para a ferramenta <strong>conversar sozinha com o bot</strong> (começa com “SIM”, clica nos botões e manda os dados da massa), rode o executor nesta máquina. Ele abre uma <strong>janela própria do Chrome com o WhatsApp Web</strong>: na 1ª vez, leia o QR code com o celular (WhatsApp › Aparelhos conectados › Conectar aparelho). Depois de cada conversa ele busca o trace no <strong>Grafana do ChatBOT</strong> (${escHtml(_autoValor('chatbot', 'grafana_url') || GRAFANA_CHATBOT)}) para conferir os SPs: na 1ª vez abre o Grafana nessa mesma janela para você <strong>fazer login</strong> (a sessão fica salva; a senha não passa pelo executor nem pelo site). A conversa, o print e o trace viram a evidência de cada CT.</p>`
      : `<p class="bi-nota">Para a ferramenta <strong>ligar sozinha</strong> pelo Avaya one-X e digitar os passos de cada CT, rode o executor nesta máquina (na VPN, com o one-X aberto e logado). Ele não usa o mouse nem o teclado: dá para continuar trabalhando.</p>`}
    <div class="exec-g-ligar">
      <div>
        <div class="exec-g-rotulo">Status</div><div id="autoExecutorStatus" class="exec-g-dica">verificando…</div>
        <div class="exec-g-dica">Versão disponível para download: <strong id="autoExecutorVersaoServidor">…</strong></div>
      </div>
      <a class="btn-export-pdf exec-g-btn-ligar" id="btnBaixarExecutor" href="${API}/api/executor/download" download>⬇️ Baixar executor (.zip)</a>
    </div>
    <ol class="exec-g-dica">
      <li>Baixe o .zip, <strong>extraia</strong> (botão direito › Extrair tudo…) numa pasta (ex.: Documentos\\ModelerExecutor) e dê dois cliques no <code>iniciar_executor.bat</code> <strong>da pasta extraída</strong> — não de dentro do .zip. Na primeira vez ele prepara tudo (precisa do Python instalado).</li>
      <li>Deixe a janela preta aberta. Volte aqui e use <strong>▶ Iniciar execução do plano → 🤖 Automático</strong>.</li>
      <li>Preencha a massa (CPF, CEP, contrato…) na aba <strong>Massa de Testes</strong> para os passos que pedem dados.</li>
    </ol>`;
  // Versão que o servidor entrega no download (o nome do .zip leva a versão).
  let vServidor = '';
  try { vServidor = ((await (await fetch(`${API}/api/executor/versao`, { credentials: 'same-origin' })).json()) || {}).versao || ''; } catch (e) {}
  const vs = document.getElementById('autoExecutorVersaoServidor');
  if (vs) vs.textContent = vServidor ? `v${vServidor}` : '—';
  const b = document.getElementById('btnBaixarExecutor');
  if (b && vServidor) b.textContent = `⬇️ Baixar executor v${vServidor} (.zip)`;

  const st = await execExecutorStatus();
  const s = document.getElementById('autoExecutorStatus');
  const desatualizado = st && vServidor && _execVersaoMenor(st.versao, vServidor);
  if (s) s.innerHTML = _execExecutorAntigo(st) ? _MSG_EXECUTOR_ANTIGO : !st ? '⚪ Executor não está rodando nesta máquina.'
    : (autoConfig.tipo === 'chatbot' ? `🟢 Executor v${escHtml(st.versao)} rodando · ChatBOT pelo WhatsApp Web (janela própria do Chrome)`
      : (st.onex_aberto ? `🟢 Executor v${escHtml(st.versao)} rodando · Avaya one-X aberto` : `🟡 Executor v${escHtml(st.versao)} rodando · abra o Avaya one-X`))
      + (desatualizado ? `<br>⚠️ Há uma versão mais nova (v${escHtml(vServidor)}): feche o executor, baixe de novo e abra o novo <code>iniciar_executor.bat</code>.` : '');
}

// "1.6" < "1.10"? compara número a número.
function _execVersaoMenor(a, b) {
  const pa = String(a || '0').split('.').map(Number), pb = String(b || '0').split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) < (pb[i] || 0);
  }
  return false;
}

