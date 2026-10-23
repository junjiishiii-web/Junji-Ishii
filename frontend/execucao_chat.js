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

function _chatComparar(pedido, conversa) {
  const textoBot = conversa.filter(m => m.de === 'bot').map(m => `${m.texto} ${(m.botoes || []).join(' ')}`).join(' ');
  const palavrasBot = new Set(_chatPalavras(textoBot));
  const itens = pedido.passos.filter(p => p.esperado).map(p => {
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

async function _execAplicarChat(ctId, pedido, res, eventos) {
  const conversa = res.conversa || [];
  const r = _chatComparar(pedido, conversa);
  const agora = new Date();
  const p2 = n => String(n).padStart(2, '0');
  const carimbo = `${agora.getFullYear()}${p2(agora.getMonth() + 1)}${p2(agora.getDate())}_${p2(agora.getHours())}${p2(agora.getMinutes())}${p2(agora.getSeconds())}`;
  const umaLinha = t => String(t || '').replace(/\s+/g, ' ').trim();
  const linhas = [
    `Conferência automática — ${ctId} (ChatBOT ${pedido.bot_numero})`,
    `Resultado sugerido: ${r.sugestao.toUpperCase()} — ${r.motivo}`,
    '',
    'Respostas esperadas do bot:',
    ...r.itens.map(i => `  [${i.achou ? 'OK' : 'FALTA'}] step ${i.n} (${i.estado}): ${umaLinha(i.esperado).slice(0, 160)}`),
    '',
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
  if (r.sugestao !== 'pendente') salvarDadosExecucao(ctId, 'status', r.sugestao);
  const atual = ((avaliacoesQA[ctId] || {}).comments || '').trim();
  const nota = `[Auto ${agora.toLocaleTimeString('pt-BR')}] ${r.motivo}`;
  salvarDadosExecucao(ctId, 'comments', atual ? `${atual} | ${nota}` : nota);
  await anexarEvidencias(ctId, { files: arquivos, value: '' });
  return r.sugestao;
}
