/* ─── Automação de Testes (Etapa 1) ─────────────────────────
   Aba "Automação": escolhe a tecnologia (URA Legado, URA ROGUE ou ChatBOT),
   guarda as informações de execução e monta o ROTEIRO DE AUTOMAÇÃO (JSON)
   a partir dos CTs da modelagem. O roteiro é a entrada das próximas etapas
   (conferência de evidências e o executor local que roda na VPN).

   - A configuração (servidor, Grafana, números…) fica salva neste navegador
     e vale para as próximas modelagens. NUNCA guarda senha: o acesso com
     senha será pedido pelo executor local.
   - A seleção de CTs fica junto da modelagem (some com "Nova Modelagem"). */

const AUTO_FORMATO = 'modeler-automacao';
const AUTO_VERSAO_FORMATO = 1;
const AUTO_CHAVE_CONFIG = 'modeler_automacao_config';

const AUTO_TIPOS = {
  ura_legado: {
    rotulo: 'URA Legado',
    icone: '☎️',
    resumo: 'Ligação pelo Avaya ou celular. Evidência: arquivo .txt no diretório da URA (via VPN).',
  },
  ura_rogue: {
    rotulo: 'URA ROGUE',
    icone: '📈',
    resumo: 'Ligação pelo Avaya ou celular. Evidência: Grafana (via VPN).',
  },
  chatbot: {
    rotulo: 'ChatBOT WhatsApp',
    icone: '💬',
    resumo: 'Conversa pelo WhatsApp (web). Evidência: provavelmente Grafana (a confirmar).',
  },
};

// Para onde as chamadas vão. URA Legado: cada URA tem o seu número. ROGUE (CRN):
// um único número e um código por esteira de homologação.
// Telefones no formato discado pelo Avaya: 00 + DDD + número (ex.: 0031 2108-6950 → 003121086950).
// "host" = nome da máquina na rede quando difere do nome exibido (usado no caminho dos logs).
const AUTO_DESTINOS = {
  ura_legado: {
    titulo: 'URA que vai receber as chamadas',
    itens: [
      { id: 'BHZNETUR95', nome: 'BHZNETUR95', ip: '10.0.132.19', node: '3095', telefone: '0031 2108-6290' },
      { id: 'BHZNETUR96', nome: 'BHZNETUR96', ip: '10.227.1.181', node: '3096', telefone: '0031 2108-6490' },
      { id: 'BHZETAECUR98', nome: 'BHZETAECUR98', host: 'BHZNETAECUR98', ip: '172.23.30.145', node: '3198', telefone: '0031 2108-6950' },
      { id: 'BHZNETAECUR99', nome: 'BHZNETAECUR99', ip: '172.23.30.146', node: '3199', telefone: '0031 2108-9290' },
      { id: 'CPSNETUR99', nome: 'CPSNETUR99', ip: '172.19.1.29', node: '1899', telefone: '0019 2137-5400' },
    ],
  },
  ura_rogue: {
    titulo: 'Esteira do CRN (HML)',
    instrucao: 'Ligue para 0021 3616-1194 216915 (contato "Rogue Esteiras" no Avaya) e, quando atender, digite o código da esteira (ex.: Principal = 2200339).',
    itens: [
      { id: 'principal', nome: 'CRN - Principal', codigo: '2200339' },
      ...'ABCDEFGHI'.split('').map((letra, i) => (
        { id: `esteira_${letra}`, nome: `CRN - Esteira ${i + 1} - ${letra}`, codigo: `22${i + 1}0339` }
      )),
    ].map(e => ({ ...e, telefone: '0021 3616-1194 216915' })),
  },
};

function _autoDestinoEscolhido(tipo) {
  const lista = AUTO_DESTINOS[tipo];
  if (!lista) return null;
  const id = _autoValor(tipo, 'destino');
  return lista.itens.find(d => d.id === id) || null;
}

// Campos por grupo. "tipos" = em quais tecnologias o campo aparece; "obrigatorio" = conta para o "pronto para gerar".
const AUTO_CAMPOS = [
  // Chamada / conversa
  { id: 'numero_destino', grupo: 'geral', rotulo: 'Número a discar', dica: 'preenchido ao escolher a URA / esteira', tipos: ['ura_legado', 'ura_rogue'], obrigatorio: true },
  { id: 'bot_numero', grupo: 'geral', rotulo: 'Número do bot no WhatsApp', dica: 'ex.: +55 11 9xxxx-xxxx', tipos: ['chatbot'], obrigatorio: true },
  { id: 'bot_origem', grupo: 'geral', rotulo: 'Número de teste que conversa', tipos: ['chatbot'], obrigatorio: true },
  { id: 'bot_canal', grupo: 'geral', rotulo: 'Canal', tipo: 'select', opcoes: ['WhatsApp Web', 'WhatsApp no celular', 'API / simulador web'], tipos: ['chatbot'], obrigatorio: true },
  { id: 'bot_msg_inicial', grupo: 'geral', rotulo: 'Mensagem que inicia a conversa', dica: 'SIM', tipos: ['chatbot'] },
  { id: 'bot_espera', grupo: 'geral', rotulo: 'Tempo máximo esperando a resposta do bot (segundos)', dica: '180', tipos: ['chatbot'] },
  { id: 'massa_padrao', grupo: 'geral', rotulo: 'Massa padrão (CPF / CNPJ / contrato)', dica: 'usada quando o CT não tiver massa própria', tipos: '*' },
  { id: 'intervalo', grupo: 'geral', rotulo: 'Intervalo entre CTs (segundos)', dica: '30', tipos: '*' },

  // Evidência: URA Legado
  { id: 'ura_acesso', grupo: 'evidencia', rotulo: 'Forma de acesso ao diretório', tipo: 'select', opcoes: ['A confirmar', 'SSH / SFTP', 'Pasta de rede Windows (SMB)', 'FTP', 'Outro'], tipos: ['ura_legado'] },
  { id: 'ura_diretorio', grupo: 'evidencia', rotulo: 'Log URA — pasta', dica: '\\\\URA\\lmcti\\Data\\UraLog\\AAAA\\MM\\DD\\', tipos: ['ura_legado'], obrigatorio: true },
  { id: 'ura_padrao_arquivo', grupo: 'evidencia', rotulo: 'Log URA — arquivo', dica: 'URADebug_AAAA-MM-DD_<node>_<canal>.txt', tipos: ['ura_legado'] },
  { id: 'ura_diretorio_integracao', grupo: 'evidencia', rotulo: 'Log Integração — pasta', dica: '\\\\URA\\lmcti\\Data\\IntegracaoLog\\AAAA\\MM\\DD\\', tipos: ['ura_legado'], obrigatorio: true },
  { id: 'ura_padrao_integracao', grupo: 'evidencia', rotulo: 'Log Integração — arquivo', dica: 'IntegracaoDebug_AAAA-MM-DD_<node>_<canal>.txt', tipos: ['ura_legado'] },
  { id: 'ura_usuario', grupo: 'evidencia', rotulo: 'Usuário de acesso (sem senha)', tipos: ['ura_legado'] },
  { id: 'ura_chave_busca', grupo: 'evidencia', rotulo: 'Como achar a chamada no log', dica: 'ex.: ANI, UCID, horário', tipos: ['ura_legado'] },

  // Evidência: Grafana (ROGUE e, provavelmente, ChatBOT)
  { id: 'grafana_url', grupo: 'evidencia', rotulo: 'URL do Grafana', dica: 'https://grafana…', tipos: ['ura_rogue', 'chatbot'], obrigatorio: ['ura_rogue'] },
  { id: 'grafana_painel', grupo: 'evidencia', rotulo: 'Link do painel / Explore usado na evidência', tipos: ['ura_rogue', 'chatbot'] },
  { id: 'grafana_fonte', grupo: 'evidencia', rotulo: 'Fonte de dados', tipo: 'select', opcoes: ['A confirmar', 'Jaeger (traces)', 'Loki', 'Elasticsearch / OpenSearch', 'Prometheus', 'Banco SQL', 'Outra'], tipos: ['ura_rogue', 'chatbot'] },
  { id: 'grafana_chave_busca', grupo: 'evidencia', rotulo: 'Campo que identifica a chamada / conversa', dica: 'ex.: ani, callId, sessionId', tipos: ['ura_rogue', 'chatbot'] },
  { id: 'fuso', grupo: 'evidencia', rotulo: 'Fuso horário dos registros', tipo: 'select', opcoes: ['America/Sao_Paulo (BRT)', 'UTC'], tipos: ['ura_rogue', 'chatbot', 'ura_legado'] },

  { id: 'observacoes', grupo: 'outros', rotulo: 'Outras informações importantes', tipo: 'textarea', dica: 'Tudo o que um QA novo precisaria saber para executar: horários da janela de teste, pré-condições, quem libera massa, particularidades do ambiente…', tipos: '*' },
];

let autoConfig = { tipo: '', valores: {} };   // valores[tipo][campo]
let autoSelecao = null;                       // Set de ct_id selecionados (null = todos)
let autoFiltro = 'todos';

function _autoCarregarConfig() {
  try {
    const bruto = localStorage.getItem(AUTO_CHAVE_CONFIG);
    if (bruto) {
      const c = JSON.parse(bruto);
      if (c && typeof c === 'object') autoConfig = { tipo: c.tipo || '', valores: c.valores || {} };
    }
  } catch (e) { /* navegador sem storage: segue só em memória */ }
}
function _autoSalvarConfig() {
  try { localStorage.setItem(AUTO_CHAVE_CONFIG, JSON.stringify(autoConfig)); } catch (e) {}
}
async function _autoSalvarSelecao() {
  if (!cacheModelagem) return;
  try { await dbPut('estado', autoSelecao ? [...autoSelecao] : null, 'automacao_sel'); } catch (e) {}
}

function _autoCampoAtivo(campo, tipo) {
  return campo.tipos === '*' || campo.tipos.includes(tipo);
}
function _autoObrigatorio(campo, tipo) {
  if (!campo.obrigatorio) return false;
  return campo.obrigatorio === true ? true : campo.obrigatorio.includes(tipo);
}
function _autoValor(tipo, id) {
  return ((autoConfig.valores[tipo] || {})[id] || '').toString();
}

/* ─── extração do que o executor precisa de cada CT ─── */
function _autoSp(v) {
  if (!v) return null;
  if (Array.isArray(v)) return v.length >= 2 && v[1] ? `${v[0]}=${v[1]}` : null;
  return String(v);
}
function _autoDtmf(acao) {
  const m = /(?:dtmf|digit\w*|tecl\w*|op[cç][aã]o)\D{0,6}([0-9*#]{1,6})/i.exec(acao || '');
  return m ? m[1] : null;
}
function _autoCasoParaRoteiro(caso) {
  const sps = new Set();
  const prompts = [];
  (caso.sp_final || '').split(',').map(s => s.trim()).filter(Boolean).forEach(s => sps.add(s));
  const passos = (caso.steps || []).map((st, i) => {
    const sp = _autoSp(st.sp);
    const spPrompt = _autoSp(st.sp_prompt);
    if (sp) sps.add(sp);
    if (spPrompt) sps.add(spPrompt);
    const promptId = st.prompt_id && st.prompt_id !== '—' ? st.prompt_id : null;
    if (promptId && !prompts.includes(promptId)) prompts.push(promptId);
    const passo = {
      n: Number(st.step_num) || i + 1,
      acao: st.acao || '',
      estado: st.estado || '',
      prompt_id: promptId,
      resultado_esperado: st.resultado !== undefined ? st.resultado : (st.prompt_texto || ''),
      sp: sp,
      sp_prompt: spPrompt,
      entradas: Array.isArray(st.entradas) ? st.entradas : [],   // ChatBOT: o que mandar/clicar (SPEC "Dígito / Valor")
      prompt_texto: st.prompt_texto || '',
    };
    const dtmf = _autoDtmf(st.acao);
    if (dtmf) passo.dtmf_sugerido = dtmf;
    return passo;
  });
  return {
    ct_id: caso.ct_id,
    bloco: caso.bloco,
    bloco_nome: caso.bloco_nome,
    regressivo: !!caso.regressivo,
    estado_validado: caso.estado,
    gherkin: caso.gherkin,
    perfil: caso.perfil,
    pre_requisito: caso.pre_requisito,
    requisitos_massa: caso.requisitos_massa || '',
    sps_esperados: [...sps],
    prompts_esperados: prompts,
    passos: passos,
  };
}

function _autoCasosFiltrados() {
  const casos = (cacheModelagem && cacheModelagem.casos_teste) || [];
  if (autoFiltro === 'novos') return casos.filter(c => !c.regressivo);
  if (autoFiltro === 'regressivos') return casos.filter(c => c.regressivo);
  if (autoFiltro === 'pendentes') return casos.filter(c => ((avaliacoesQA[c.ct_id] || {}).status || 'pendente') === 'pendente');
  return casos;
}
function _autoSelecionado(ctId) {
  return !autoSelecao || autoSelecao.has(ctId);
}
function _autoCasosSelecionados() {
  return ((cacheModelagem && cacheModelagem.casos_teste) || []).filter(c => _autoSelecionado(c.ct_id));
}

/* ─── renderização ─── */
function renderizarAutomacao() {
  const raiz = document.getElementById('automacaoConteudo');
  if (!raiz) return;
  const tipo = autoConfig.tipo;

  const cartoes = Object.entries(AUTO_TIPOS).map(([chave, t]) => `
    <label class="auto-tipo ${tipo === chave ? 'ativo' : ''}">
      <input type="radio" name="autoTipo" value="${chave}" ${tipo === chave ? 'checked' : ''} onchange="autoEscolherTipo('${chave}')" />
      <span class="auto-tipo-icone">${t.icone}</span>
      <span class="auto-tipo-nome">${escHtml(t.rotulo)}</span>
      <span class="auto-tipo-resumo">${escHtml(t.resumo)}</span>
    </label>`).join('');

  const NUMEROS = '①②③④⑤⑥⑦⑧';
  let secao = 0;
  const proximoNumero = () => NUMEROS[secao++];
  const numTecnologia = proximoNumero();

  let corpo = '';
  if (!tipo) {
    corpo = `<p class="auto-vazio">Escolha acima a tecnologia que será testada para ver os campos de execução.</p>`;
  } else {
    const destinos = AUTO_DESTINOS[tipo];
    if (destinos) {
      const escolhido = _autoValor(tipo, 'destino');
      corpo += `<section class="auto-secao">
        <h4 class="auto-secao-titulo">${proximoNumero()} ${escHtml(destinos.titulo)}<span class="auto-obrig" title="Obrigatório">*</span></h4>
        ${destinos.instrucao ? `<p class="bi-nota">${escHtml(destinos.instrucao)}</p>` : ''}
        <div class="auto-destinos">${destinos.itens.map(d => `
          <button type="button" class="auto-destino ${escolhido === d.id ? 'ativo' : ''}" onclick="autoEscolherDestino('${escHtml(d.id)}')">
            <span class="auto-destino-nome">${escHtml(d.nome)}</span>
            ${d.ip
              ? `<span class="auto-destino-det">IP ${escHtml(d.ip)}</span><span class="auto-destino-det">Node ${escHtml(d.node)}</span>`
              : `<span class="auto-destino-det">Código ${escHtml(d.codigo)}</span>`}
          </button>`).join('')}
        </div>
      </section>`;
    }
    const grupos = [
      ['geral', tipo === 'chatbot' ? 'Conversa' : 'Ligação'],
      ['evidencia', 'Onde buscar a evidência'],
      ['outros', 'Informações adicionais'],
    ];
    corpo += grupos.map(([g, titulo]) => {
      const campos = AUTO_CAMPOS.filter(c => c.grupo === g && _autoCampoAtivo(c, tipo));
      if (!campos.length) return '';
      return `<section class="auto-secao">
        <h4 class="auto-secao-titulo">${proximoNumero()} ${titulo}</h4>
        <div class="auto-grid">${campos.map(c => _autoHtmlCampo(c, tipo)).join('')}</div>
      </section>`;
    }).join('');
    corpo += `<p class="auto-aviso">🔒 Não coloque <strong>senhas</strong> aqui. Estes dados ficam salvos só neste navegador; o acesso com senha (VPN, servidor da URA, Grafana) será pedido pelo executor local, na sua máquina.</p>`;
  }

  raiz.innerHTML = `
    <section class="auto-secao">
      <h4 class="auto-secao-titulo">${numTecnologia} Tecnologia a testar</h4>
      <div class="auto-tipos">${cartoes}</div>
    </section>
    ${corpo}
    <section class="auto-secao">
      <h4 class="auto-secao-titulo">${proximoNumero()} CTs que entram no roteiro <span class="bi-contador" id="autoContSel"></span></h4>
      <div class="auto-filtros">
        ${[['todos', 'Todos'], ['novos', 'Só novos'], ['regressivos', 'Só regressivos'], ['pendentes', 'Só pendentes na execução']]
          .map(([f, r]) => `<button class="auto-filtro ${autoFiltro === f ? 'ativo' : ''}" onclick="autoFiltrar('${f}')">${r}</button>`).join('')}
        <span class="auto-filtros-sep"></span>
        <button class="auto-filtro" onclick="autoMarcarVisiveis(true)">Marcar visíveis</button>
        <button class="auto-filtro" onclick="autoMarcarVisiveis(false)">Desmarcar visíveis</button>
      </div>
      <div class="history-table-wrap auto-tabela-wrap"><table class="data-table">
        <thead><tr>
          <th style="width:36px;"></th><th style="width:90px;">CT</th><th style="width:110px;">Tipo</th>
          <th>Estado validado</th><th style="width:220px;">SPs esperados</th><th style="width:70px;">Steps</th><th style="width:96px;"></th>
        </tr></thead>
        <tbody id="autoTabelaCts"></tbody>
      </table></div>
    </section>
    <section class="auto-secao auto-rodape">
      <div id="autoProntidao" class="auto-prontidao"></div>
      <div class="auto-rodape-botoes">
        <button class="btn-export-pdf btn-iniciar-plano" onclick="execIniciarPlano()">▶ Iniciar execução do plano</button>
        <button class="btn-export-pdf exec-g-sec" id="btnAutoRoteiro" onclick="autoBaixarRoteiro()">⬇️ Gerar roteiro (.json)</button>
      </div>
    </section>
    ${tipo ? `<section class="auto-secao conf-secao">
      <h4 class="auto-secao-titulo">${proximoNumero()} Executor automático (${tipo === 'chatbot' ? 'WhatsApp Web' : 'Avaya one-X'}) <span class="auto-etapa">Etapa 4</span></h4>
      <div id="autoExecutor"></div>
    </section>` : ''}
    ${tipo === 'ura_legado' || tipo === 'ura_rogue' ? `<section class="auto-secao conf-secao">
      <h4 class="auto-secao-titulo">${proximoNumero()} Conferir evidência da ligação <span class="auto-etapa">Etapa 2</span></h4>
      <div id="autoConferencia"></div>
    </section>` : ''}`;

  _autoRenderTabela();
  _autoAtualizarProntidao();
  if (typeof renderizarExecutorAuto === 'function') renderizarExecutorAuto();
}

// Número a discar sempre vem da URA / esteira escolhida (travado).
function autoNumeroDiscar(tipo) {
  const d = _autoDestinoEscolhido(tipo);
  return d && d.telefone ? d.telefone : _autoValor(tipo, 'numero_destino');
}

function _autoHtmlCampo(c, tipo) {
  if (c.id === 'numero_destino' && _autoDestinoEscolhido(tipo)) {
    return `<label class="auto-campo"><span>${escHtml(c.rotulo)}</span>
      <input type="text" class="auto-input auto-travado" id="auto-${c.id}" value="${escHtml(autoNumeroDiscar(tipo))}" readonly
        title="Preenchido pela ${tipo === 'ura_rogue' ? 'esteira' : 'URA'} escolhida" />
      <small class="auto-nota-campo">🔒 preenchido pela ${tipo === 'ura_rogue' ? 'esteira' : 'URA'} escolhida (formato Avaya: 00 + DDD)</small></label>`;
  }
  const v = _autoValor(tipo, c.id);
  const obrig = _autoObrigatorio(c, tipo) ? '<span class="auto-obrig" title="Obrigatório">*</span>' : '';
  const attrs = `id="auto-${c.id}" oninput="autoAlterarCampo('${c.id}', this.value)" onchange="autoAlterarCampo('${c.id}', this.value)"`;
  let controle;
  if (c.tipo === 'select') {
    controle = `<select class="auto-input" ${attrs}>
      <option value="">— escolha —</option>
      ${c.opcoes.map(o => `<option ${o === v ? 'selected' : ''}>${escHtml(o)}</option>`).join('')}
    </select>`;
  } else if (c.tipo === 'textarea') {
    controle = `<textarea class="auto-input" rows="4" placeholder="${escHtml(c.dica || '')}" ${attrs}>${escHtml(v)}</textarea>`;
  } else {
    controle = `<input type="text" class="auto-input" value="${escHtml(v)}" placeholder="${escHtml(c.dica || '')}" autocomplete="off" ${attrs} />`;
  }
  return `<label class="auto-campo ${c.tipo === 'textarea' ? 'largo' : ''}"><span>${escHtml(c.rotulo)}${obrig}</span>${controle}</label>`;
}

function _autoRenderTabela() {
  const corpo = document.getElementById('autoTabelaCts');
  if (!corpo) return;
  const casos = _autoCasosFiltrados();
  if (!casos.length) {
    corpo.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#888;padding:16px;">Nenhum CT neste filtro.</td></tr>`;
  } else {
    // Milhares de CTs (Mapear 100%): a tabela mostra os 500 primeiros do filtro; a seleção vale para todos.
    const LIMITE = 500;
    corpo.innerHTML = casos.slice(0, LIMITE).map(c => {
      const r = _autoCasoParaRoteiro(c);
      const id = escHtml(c.ct_id);
      return `<tr>
        <td><input type="checkbox" ${_autoSelecionado(c.ct_id) ? 'checked' : ''} onchange="autoMarcarCt('${id}', this.checked)" /></td>
        <td><strong>${id}</strong></td>
        <td>${c.regressivo ? 'Regressivo' : 'Novo'}</td>
        <td>${escHtml(c.estado)}</td>
        <td class="auto-sps">${escHtml(r.sps_esperados.join(', ') || '—')}</td>
        <td>${r.passos.length}</td>
        <td><button class="btn-evid" onclick="execExecutarCt('${id}')" title="Executar só este CT">▶ Executar</button></td>
      </tr>`;
    }).join('') + (casos.length > LIMITE
      ? `<tr><td colspan="7" style="text-align:center;color:#666;padding:10px;">… e mais ${casos.length - LIMITE} CTs (use os filtros e “Marcar/Desmarcar visíveis” — vale para todos do filtro).</td></tr>`
      : '');
  }
  const total = ((cacheModelagem && cacheModelagem.casos_teste) || []).length;
  const cont = document.getElementById('autoContSel');
  if (cont) cont.textContent = `${_autoCasosSelecionados().length} de ${total}`;
  if (typeof renderizarConferencia === 'function') renderizarConferencia();
}

function _autoPendencias() {
  const tipo = autoConfig.tipo;
  if (!tipo) return ['Escolha a tecnologia a testar'];
  const faltando = AUTO_CAMPOS
    .filter(c => _autoCampoAtivo(c, tipo) && _autoObrigatorio(c, tipo) && !(c.id === 'numero_destino' ? autoNumeroDiscar(tipo) : _autoValor(tipo, c.id)).trim())
    .map(c => c.rotulo);
  if (AUTO_DESTINOS[tipo] && !_autoDestinoEscolhido(tipo)) faltando.unshift(AUTO_DESTINOS[tipo].titulo);
  if (!_autoCasosSelecionados().length) faltando.push('Selecione ao menos 1 CT');
  return faltando;
}
function _autoAtualizarProntidao() {
  const el = document.getElementById('autoProntidao');
  if (!el) return;
  const pend = _autoPendencias();
  el.className = 'auto-prontidao ' + (pend.length ? 'pendente' : 'ok');
  el.innerHTML = pend.length
    ? `<strong>Falta preencher:</strong> ${pend.map(escHtml).join(' · ')}<br><span>Dá para gerar o roteiro assim mesmo; os campos vazios vão marcados como pendentes.</span>`
    : `<strong>✓ Pronto.</strong> Configuração completa e ${_autoCasosSelecionados().length} CT(s) selecionados.`;
}

/* ─── ações da tela ─── */
function autoEscolherTipo(tipo) {
  autoConfig.tipo = tipo;
  _autoSalvarConfig();
  renderizarAutomacao();
}
// Escolher a URA / esteira já preenche o número a discar (continua editável).
function autoEscolherDestino(id) {
  const tipo = autoConfig.tipo;
  if (!AUTO_DESTINOS[tipo]) return;
  const valores = (autoConfig.valores[tipo] = autoConfig.valores[tipo] || {});
  valores.destino = id;
  const d = _autoDestinoEscolhido(tipo);
  if (d && d.telefone) valores.numero_destino = d.telefone;
  // URA Legado: os logs ficam numa pasta de rede da própria URA, separados por dia, node e canal.
  if (d && tipo === 'ura_legado') {
    valores.ura_acesso = 'Pasta de rede Windows (SMB)';
    valores.ura_diretorio = `\\\\${d.host || d.nome}\\lmcti\\Data\\UraLog\\AAAA\\MM\\DD\\`;
    valores.ura_padrao_arquivo = `URADebug_AAAA-MM-DD_${d.node}_<canal>.txt`;
    valores.ura_diretorio_integracao = `\\\\${d.host || d.nome}\\lmcti\\Data\\IntegracaoLog\\AAAA\\MM\\DD\\`;
    valores.ura_padrao_integracao = `IntegracaoDebug_AAAA-MM-DD_${d.node}_<canal>.txt`;
    if (!valores.ura_chave_busca) valores.ura_chave_busca = 'ANI + horário da ligação';
  }
  // ROGUE: a chamada é achada no Conversation Finder (From = ANI + horário) e aberta como trace no Jaeger.
  if (d && tipo === 'ura_rogue' && !valores.grafana_url) {
    valores.grafana_url = 'https://grafana-mc1-rogue.hml-sp.claro.internal';
    valores.grafana_painel = 'https://grafana-mc1-rogue.hml-sp.claro.internal/d/OBHSegzGK/conversation-finder?orgId=1';
    valores.grafana_fonte = 'Jaeger (traces)';
    valores.grafana_chave_busca = 'From (ANI) + horário → ConversationId → trace';
  }
  _autoSalvarConfig();
  renderizarAutomacao();
}
function autoAlterarCampo(id, valor) {
  const tipo = autoConfig.tipo;
  if (!tipo) return;
  (autoConfig.valores[tipo] = autoConfig.valores[tipo] || {})[id] = valor;
  _autoSalvarConfig();
  _autoAtualizarProntidao();
  // O ANI da configuração alimenta o "ANI que ligou" da conferência (se o QA não digitou outro lá).
  if (id === 'ani' && typeof confEstado !== 'undefined' && !confEstado.aniBusca) {
    document.querySelectorAll('#confAni').forEach(el => { el.value = valor; });
  }
}
function autoFiltrar(f) {
  autoFiltro = f;
  document.querySelectorAll('.auto-filtros .auto-filtro').forEach(b => b.classList.toggle('ativo', b.getAttribute('onclick') === `autoFiltrar('${f}')`));
  _autoRenderTabela();
}
function _autoGarantirSelecao() {
  if (!autoSelecao) autoSelecao = new Set(((cacheModelagem && cacheModelagem.casos_teste) || []).map(c => c.ct_id));
}
function autoMarcarCt(ctId, marcado) {
  _autoGarantirSelecao();
  if (marcado) autoSelecao.add(ctId); else autoSelecao.delete(ctId);
  _autoSalvarSelecao();
  _autoRenderTabela();
  _autoAtualizarProntidao();
}
function autoMarcarVisiveis(marcado) {
  _autoGarantirSelecao();
  _autoCasosFiltrados().forEach(c => { if (marcado) autoSelecao.add(c.ct_id); else autoSelecao.delete(c.ct_id); });
  _autoSalvarSelecao();
  _autoRenderTabela();
  _autoAtualizarProntidao();
}

function autoBaixarRoteiro() {
  if (!cacheModelagem) return;
  const tipo = autoConfig.tipo;
  if (!tipo) { alert('Escolha a tecnologia a testar (URA Legado, URA ROGUE ou ChatBOT).'); return; }
  const casos = _autoCasosSelecionados();
  if (!casos.length) { alert('Selecione ao menos 1 CT.'); return; }

  const config = {};
  AUTO_CAMPOS.filter(c => _autoCampoAtivo(c, tipo)).forEach(c => { config[c.id] = _autoValor(tipo, c.id).trim(); });
  if (config.numero_destino !== undefined) config.numero_destino = autoNumeroDiscar(tipo);
  const destino = _autoDestinoEscolhido(tipo);
  // Como o executor abre a chamada: ROGUE disca o número único e, ao atender, digita o código da esteira.
  const discagem = tipo === 'chatbot' ? null : {
    numero: config.numero_destino || (destino && destino.telefone) || '',
    digitos: String(config.numero_destino || (destino && destino.telefone) || '').replace(/\D/g, ''),
    dtmf_ao_atender: (destino && destino.codigo) || null,
  };
  const roteiro = {
    formato: AUTO_FORMATO,
    versao_formato: AUTO_VERSAO_FORMATO,
    gerado_em: new Date().toISOString(),
    modeler_versao: (window.MODELER_VERSAO || {}).numero || '',
    projeto: cacheModelagem.jira_ivr || '',
    tecnologia: tipo,
    tecnologia_rotulo: AUTO_TIPOS[tipo].rotulo,
    destino: destino,
    discagem: discagem,
    config: config,
    pendencias: _autoPendencias(),
    total_cts: casos.length,
    casos: casos.map(_autoCasoParaRoteiro),
  };

  const projeto = String(roteiro.projeto || 'projeto').replace(/[^\w.-]+/g, '_').slice(0, 60);
  const nome = `Roteiro_Automacao_${projeto}_${tipo}.json`;
  const url = URL.createObjectURL(new Blob([JSON.stringify(roteiro, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

/* ─── ciclo de vida (chamado pelo index.html) ─── */
async function iniciarAutomacao(restaurando) {
  _autoCarregarConfig();
  autoFiltro = 'todos';
  autoSelecao = null;
  if (restaurando) {
    try {
      const sel = await dbGet('estado', 'automacao_sel');
      const ids = new Set(((cacheModelagem && cacheModelagem.casos_teste) || []).map(c => c.ct_id));
      // Seleção de outra modelagem (nenhum CT em comum) não vale: volta a "todos".
      if (Array.isArray(sel) && sel.some(id => ids.has(id))) autoSelecao = new Set(sel.filter(id => ids.has(id)));
    } catch (e) {}
  }
  renderizarAutomacao();
}
function limparAutomacao() {
  autoSelecao = null;
  autoFiltro = 'todos';
}
