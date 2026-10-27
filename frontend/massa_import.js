/* ─── Importar massa de teste de uma planilha em formato livre ───
   O servidor (/api/massa/ler) devolve as massas encontradas, cada uma com VALORES (cpf, cep, numero…) e uma
   DESCRIÇÃO (título do bloco, colunas de texto da linha, texto vizinho). Aqui cada CT recebe a massa cuja
   descrição combina com a "Condição da massa" dele (grupo/cabeamento, cliente móvel, crédito…), usando
   linhas diferentes para CTs diferentes. Antes de gravar, uma prévia mostra o que foi para cada CT. */

const _MASSA_GRUPOS = [
  { id: 'endereco', campos: ['cep', 'numero'], rotulo: 'Endereço (CEP / nº)' },
  { id: 'documento', campos: ['cpf', 'cnpj'], rotulo: 'Documento (CPF / CNPJ)' },
  { id: 'outros', campos: ['contrato', 'nome', 'email', 'nascimento', 'celular'], rotulo: 'Outros dados' },
];
let _massaPrevia = null;   // { porCt: {ct: {campos, origens, avisos}}, sobras: [...] }

function _mNorm(s) {
  return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
}

// Características que ligam massa e CT. null = o texto não fala disso.
function _mTracos(texto) {
  const t = ' ' + _mNorm(texto) + ' ';
  const tr = { movel: null, credito: null, grupo: null };
  if (/ nao (cliente )?(claro )?movel | nao cliente /.test(t)) tr.movel = false;
  else if (/ movel | cliente claro /.test(t)) tr.movel = true;
  if (/ reprovad/.test(t)) tr.credito = 'rep';
  else if (/ aprovad/.test(t)) tr.credito = 'apr';
  if (/ alto valor /.test(t)) tr.grupo = 'alto_valor';
  else if (/ cep (e )?numero cabead/.test(t)) tr.grupo = 'cep_numero_cabeado';
  else if (/ nao cabead/.test(t)) tr.grupo = 'nao_cabeado';
  else if (/ cabead/.test(t)) tr.grupo = 'cabeado';
  else if (/ timeout /.test(t)) tr.grupo = 'timeout';
  else if (/ brownfield /.test(t)) tr.grupo = 'brownfield';
  return tr;
}

function _mCondicoesCt(caso) {
  const itens = (caso.condicoes_massa && caso.condicoes_massa.length) ? caso.condicoes_massa : condicoesMassaDoNavegador(caso);
  const pega = rx => itens.filter(i => rx.test(i.rotulo)).map(i => i.valor).join(' ');
  return {
    itens,
    grupo: _mTracos(`${pega(/grupo/i)} ${pega(/crit[eé]rio/i)}`).grupo,
    movel: _mTracos(pega(/m[oó]vel/i)).movel,
    credito: /n[aã]o se aplica/i.test(pega(/cr[eé]dito/i)) ? null : _mTracos(pega(/cr[eé]dito/i)).credito,
    texto: itens.map(i => i.valor).join(' '),
  };
}

// Pontuação massa x CT para um grupo de campos. -Infinity = contradiz (não pode usar).
function _mPontuar(cand, ct, grupoCampos) {
  const tr = cand.tracos;
  let pontos = 0;
  const comparar = (a, b, peso) => {
    if (a === null || b === null) return 0;
    return a === b ? peso : -Infinity;
  };
  if (grupoCampos === 'endereco') pontos += comparar(tr.grupo, ct.grupo, 3);
  if (grupoCampos === 'documento') {
    pontos += comparar(tr.movel, ct.movel, 2);
    pontos += comparar(tr.credito, ct.credito, 2);
  }
  if (grupoCampos === 'outros') {
    pontos += comparar(tr.movel, ct.movel, 1) + comparar(tr.credito, ct.credito, 1) + comparar(tr.grupo, ct.grupo, 1);
  }
  if (pontos === -Infinity) return pontos;
  // Palavras em comum (ajuda nos formatos livres).
  const pc = new Set(_mNorm(cand.desc).split(' ').filter(w => w.length > 3));
  const comum = _mNorm(ct.texto).split(' ').filter(w => w.length > 3 && pc.has(w));
  return pontos + Math.min(new Set(comum).size, 4) * 0.25;
}

async function massaImportar(input) {
  const arq = (input.files || [])[0];
  input.value = '';
  if (!arq || !cacheModelagem) return;
  const fd = new FormData();
  fd.append('file', arq, arq.name);
  let res;
  try {
    const r = await fetch(`${API}/api/massa/ler`, { method: 'POST', body: fd, credentials: 'same-origin' });
    res = await r.json();
    if (!r.ok) throw new Error(res.detail || `HTTP ${r.status}`);
  } catch (e) {
    alert('Não consegui ler a planilha de massa: ' + (e.message || e));
    return;
  }
  // Candidatos: uma massa por linha de cada bloco.
  const cands = [];
  (res.abas || []).forEach(aba => (aba.blocos || []).forEach((b, bi) => (b.linhas || []).forEach((ln, li) => {
    const valores = {};
    Object.keys(ln).forEach(k => { if (!k.startsWith('_') && ln[k]) valores[k] = String(ln[k]); });
    const desc = [b.titulo, ln._desc].filter(Boolean).join(' · ') || '';
    cands.push({ id: `${aba.nome}|${bi}|${li}`, valores, desc, tracos: _mTracos(desc), origem: `${aba.nome}${b.celula ? ' ' + b.celula : ''}${desc ? ' — ' + desc : ''}`, usos: 0 });
  })));
  if (!cands.length) {
    alert('Não encontrei massa (CPF, CNPJ, CEP, contrato…) nesta planilha.');
    return;
  }
  const casos = cacheModelagem.casos_teste || [];
  const porCt = {};
  casos.forEach(caso => {
    const ct = _mCondicoesCt(caso);
    const atrib = { campos: {}, origens: [], avisos: [] };
    _MASSA_GRUPOS.forEach(g => {
      const comCampos = cands.filter(c => g.campos.some(k => c.valores[k]));
      if (!comCampos.length) return;
      let melhor = -Infinity, escolhidos = [];
      comCampos.forEach(c => {
        const p = _mPontuar(c, ct, g.id);
        if (p > melhor) { melhor = p; escolhidos = [c]; } else if (p === melhor) escolhidos.push(c);
      });
      if (melhor <= 0) {                                   // nada combina com segurança
        if (g.id !== 'outros') atrib.avisos.push(`sem massa de ${g.rotulo.toLowerCase()} que combine com a condição`);
        return;
      }
      const c = escolhidos.sort((a, b) => a.usos - b.usos)[0];   // linhas diferentes para CTs diferentes
      c.usos++;
      g.campos.forEach(k => { if (c.valores[k]) atrib.campos[k] = c.valores[k]; });
      atrib.origens.push(c.origem);
    });
    porCt[caso.ct_id] = atrib;
  });
  _massaPrevia = { porCt, sobras: cands.filter(c => !c.usos), arquivo: arq.name };
  _massaMostrarPrevia();
}

function _massaMostrarPrevia() {
  const { porCt, sobras, arquivo } = _massaPrevia;
  const casos = cacheModelagem.casos_teste || [];
  const comMassa = casos.filter(c => Object.keys(porCt[c.ct_id].campos).length).length;
  const resumoCond = caso => {
    const ct = _mCondicoesCt(caso);
    return ct.itens.filter(i => /grupo|m[oó]vel|cr[eé]dito|target/i.test(i.rotulo)).map(i => `${i.rotulo}: ${i.valor}`).join(' · ')
      || ct.itens.slice(0, 2).map(i => i.valor).join(' · ');
  };
  const linhas = casos.map(caso => {
    const a = porCt[caso.ct_id];
    const valores = Object.entries(a.campos).map(([k, v]) => `<strong>${escHtml(k)}</strong> ${escHtml(v)}`).join(' · ');
    return `<tr class="${a.avisos.length ? 'massa-prev-aviso' : ''}">
      <td><strong>${escHtml(caso.ct_id)}</strong></td>
      <td class="massa-prev-cond">${escHtml(resumoCond(caso))}</td>
      <td>${valores || '<em>—</em>'}${a.avisos.length ? `<div class="massa-prev-alerta">⚠️ ${a.avisos.map(escHtml).join('; ')}</div>` : ''}</td>
      <td class="massa-prev-origem">${a.origens.map(escHtml).join('<br>')}</td></tr>`;
  }).join('');
  const html = `
    <p class="bi-nota">Arquivo <strong>${escHtml(arquivo)}</strong>: <strong>${comMassa} de ${casos.length}</strong> CT(s) receberam massa.
      Cada CT recebe a massa cuja descrição (título do bloco ou colunas da linha) combina com a condição dele; CTs diferentes recebem linhas diferentes.
      Ao aplicar, a massa vira a <strong>massa própria</strong> do CT (substitui os campos importados; os outros ficam).</p>
    <div class="history-table-wrap massa-prev-tabela"><table class="data-table">
      <thead><tr><th style="width:70px;">CT</th><th>Condição da massa</th><th>Massa sugerida</th><th style="width:260px;">De onde veio</th></tr></thead>
      <tbody>${linhas}</tbody></table></div>
    ${sobras.length ? `<details class="conf-detalhe"><summary>${sobras.length} massa(s) da planilha não usada(s)</summary>
      <ul class="massa-condicoes">${sobras.slice(0, 80).map(c => `<li>${Object.entries(c.valores).map(([k, v]) => `${escHtml(k)} ${escHtml(v)}`).join(' · ')} — ${escHtml(c.origem)}</li>`).join('')}</ul></details>` : ''}
    <div class="exec-g-acoes"><button class="btn-export-pdf btn-iniciar-plano" onclick="massaAplicarPrevia()">✓ Aplicar a massa nos ${comMassa} CT(s)</button></div>`;
  let modal = document.getElementById('massaModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'massaModal';
    modal.className = 'conf-modal';
    modal.innerHTML = `<div class="conf-modal-janela"><div class="conf-modal-topo"><h3>📎 Importar massa de teste</h3>
      <button class="manual-fechar" onclick="massaFecharPrevia()" title="Fechar (Esc)">✕ Fechar</button></div>
      <div class="conf-modal-corpo" id="massaModalCorpo"></div></div>`;
    modal.addEventListener('click', e => { if (e.target === modal) massaFecharPrevia(); });
    document.body.appendChild(modal);
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && modal.classList.contains('aberto')) massaFecharPrevia(); });
  }
  document.getElementById('massaModalCorpo').innerHTML = html;
  modal.classList.add('aberto');
}

function massaFecharPrevia() {
  const m = document.getElementById('massaModal');
  if (m) m.classList.remove('aberto');
}

function massaAplicarPrevia() {
  if (!_massaPrevia) return;
  let n = 0;
  Object.entries(_massaPrevia.porCt).forEach(([ctId, a]) => {
    if (!Object.keys(a.campos).length) return;
    if (!avaliacoesQA[ctId]) avaliacoesQA[ctId] = { status: 'pendente', comments: '' };
    avaliacoesQA[ctId].massa = { ...(avaliacoesQA[ctId].massa || {}), ...a.campos };
    // Atualiza os campos na tabela da aba Massa de Testes.
    Object.entries(a.campos).forEach(([campo, valor]) => {
      const inp = document.querySelector(`#massaTableBody input[oninput="salvarMassa('${ctId}', '${campo}', this.value)"]`);
      if (inp) inp.value = valor;
    });
    n++;
  });
  agendarSalvarEstado();
  massaFecharPrevia();
  _confAvisoRapido(`Massa aplicada em ${n} CT(s).`);
}
