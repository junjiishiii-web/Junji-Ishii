/* Versão do Modeler Assistant — ÚNICO lugar para atualizar a cada entrega.
   Regra: MAIOR.MENOR — "menor" sobe com melhorias/correções; "maior" com mudança grande de comportamento.
   A primeira entrada da lista é a versão atual (aparece ao lado do botão Manual e no Manual). */
window.MODELER_VERSOES = [
  {
    numero: '2.35',
    data: '20/10/2026',
    itens: [
      'Massa de Testes: o detalhamento da "Condição da massa" também aparece em modelagens salvas antes da 2.34 (montado a partir do cenário do EEP e dos passos do CT), sem precisar gerar de novo. Condições divergentes do cenário ficam em vermelho.',
    ],
  },
  {
    numero: '2.34',
    data: '20/10/2026',
    itens: [
      'Massa de Testes: a coluna "Condição da massa" diz como o cliente/chaves precisam estar em cada CT — perfil do ANI, restrições (linha, AfterHours, MPL…), a linha do cenário do EEP (grupo, critério ex.: cablingtype = 0, cliente Claro Móvel, crédito, target esperado) e as condições da SPEC no caminho que dependem do cliente (DNIS, chaves ativadas/desativadas, regras de segmento, RTDM…). Também no xlsx (Massa_Testes).',
      'Quando o caminho da SPEC contradiz o cenário do EEP (ex.: cenário "Crédito Reprovado" passando por "Crédito APROVADO"), a condição aparece marcada como ⚠️ Divergente do cenário.',
      'Correção no motor: as regras que preferem o ramo "Else"/padrão e reconhecem chave "não"/desligada não funcionavam (caractere inválido na expressão); voltam a valer.',
    ],
  },
  {
    numero: '2.33',
    data: '20/10/2026',
    itens: [
      'Automação (etapa 4) — execução automática pelo Avaya one-X: baixe o executor na aba 🤖 Automação (seção "Executor automático"), rode o iniciar_executor.bat e use ▶ Iniciar execução do plano → 🤖 Automático. Para cada CT o executor disca, digita o código da esteira (ROGUE), acompanha o log da URA em tempo real e digita as teclas de cada passo quando a URA toca o prompt (URA Legado), desliga e devolve o log da chamada; o site confere os SPs e grava status e evidência sozinho, e passa para o próximo CT.',
      'Massa de Testes: cada CT ganhou campos de CPF/CNPJ, Contrato, CEP e Nº da casa (salvos), e uma massa padrão para todos; a automação digita esses dados quando o passo pede.',
      'Segurança do executor: só aceita comandos do Modeler Assistant e só disca para os números das URAs de homologação cadastradas.',
    ],
  },
  {
    numero: '2.32',
    data: '20/10/2026',
    itens: [
      'Automação: removidos os campos Ambiente, Origem da ligação e Número de origem (ANI) da configuração. O ANI fica só na conferência ("ANI que ligou"), lembrado depois da primeira vez.',
    ],
  },
  {
    numero: '2.31',
    data: '20/10/2026',
    itens: [
      'Execução guiada: o botão 📞 Ligar virou 📋 Copiar número — o Avaya one-X não abre links de telefone (o Windows oferecia Chrome/Edge/Skype). Copie e, no one-X, clique em "Insira um nome ou número", Ctrl+V e Enter.',
    ],
  },
  {
    numero: '2.30',
    data: '20/10/2026',
    itens: [
      'Correção: "Erro ao cruzar as documentações no servidor: Resposta de progresso inválida". Quando o servidor gratuito reinicia no meio da modelagem (troca de versão, dormir/acordar), a tela agora espera ele voltar e, se a modelagem se perdeu, reenvia a SPEC/EEP e recomeça sozinha.',
      'Tela inicial: o quadro de upload ficou mais largo — o seletor "Transferência Pura (IDs do EEP)" não vaza mais e o nome do EEP aparece inteiro.',
    ],
  },
  {
    numero: '2.29',
    data: '20/10/2026',
    itens: [
      'Automação: ▶ Iniciar execução do plano (aba Automação e Execução dos Testes) e ▶ Executar em cada CT. Um CT por vez: número a discar, código da esteira (ROGUE), teclas e prompts de cada passo; ao clicar em "Terminei a ligação" a conferência abre já buscando a evidência e, ao aplicar, segue para o próximo CT. Pular, voltar, pausar e resumo final (OK / Não OK / pendentes).',
      'Número a discar travado e no formato do Avaya (00 + DDD): 0031 2108-6950, 0019 2137-5400, ROGUE 0021 3616-1194 216915 (o código 216915 faz parte da discagem; é o contato "Rogue Esteiras" do Avaya). O botão 📋 Copiar número copia o número para colar no Avaya one-X.',
    ],
  },
  {
    numero: '2.28',
    data: '20/10/2026',
    itens: [
      'Projeto COM navegação alterada na SPEC e tabela de cenários/targets de transferência no EEP: além dos CTs de navegação do projeto, cada cenário/target ganha o seu CT de transferência ATH (todos os targets são validados). Antes só saíam os CTs de navegação (ex.: 9 CTs, sem cobrir os 22 targets).',
    ],
  },
  {
    numero: '2.27',
    data: '20/10/2026',
    itens: [
      'Projeto de transferência detectado automaticamente: se o EEP traz a tabela de cenários com IDs/targets e o projeto não aparece no versionamento da SPEC, a modelagem vira de TRANSFERÊNCIA (1 CT por cenário, todos os targets) mesmo com o seletor em "Alteração de SPEC". Antes saíam só alguns CTs, pelo modo por IVR.',
      'Plano B de leitura: se a estrutura da tabela do EEP não for reconhecida, os IDs/targets são lidos da lista de números após o cabeçalho "Target".',
    ],
  },
  {
    numero: '2.26',
    data: '20/10/2026',
    itens: [
      'Transferência Pura (projeto sem alteração de navegação): lê a tabela de cenários com TARGET/VDN/ID de transferência do EEP (PDF, docx ou xlsx) e gera 1 CT por cenário, percorrendo a SPEC (que serve só de base de navegação) pelo caminho mais fácil até a transferência ATH e validando o ID esperado. Resumo no padrão do Jira ("Dado Ind.Atend.101 do Grupo 1…, Quando … na transferencia para ATH, Então é direcionado para taxonomia 2730835") e último step "Encerrar a chamada e validar o target". O IVR do projeto não precisa estar no versionamento da SPEC.',
    ],
  },
  {
    numero: '2.25',
    data: '20/10/2026',
    itens: [
      'ROGUE sem download: favorito ➜ Enviar ao Modeler (arraste o botão da conferência para a barra de favoritos). Com o trace aberto no Grafana, um clique lê o trace e copia; no Modeler, 📋 Colar trace do Grafana carrega e confere. Se a aba do Grafana foi aberta pelo link do Modeler, o trace chega sozinho. O download manual (Inspect → Data → Download) continua disponível.',
    ],
  },
  {
    numero: '2.24',
    data: '20/10/2026',
    itens: [
      'Automação (etapa 3, sem instalar nada) — URA Legado: botão 📁 Buscar minha chamada. Na primeira vez o Chrome/Edge pede a pasta \\\\URA\\lmcti\\Data (fica lembrada); depois a ferramenta abre UraLog\\AAAA\\MM\\DD sozinha, procura o ANI em todos os canais do dia, carrega o Log URA e o Log Integração do mesmo canal e mostra a chamada mais recente já conferida. Precisa estar na VPN. O carregamento manual continua disponível.',
      'ROGUE: link direto para o Conversation Finder das últimas 3 horas.',
    ],
  },
  {
    numero: '2.23',
    data: '20/10/2026',
    itens: [
      'Execução dos Testes: cada CT ganhou o botão 🔎 Conferir evidência (ao lado de Anexar evidência). Ele abre a conferência já no CT — carregue o log da URA Legado ou o trace do ROGUE, veja os SPs/prompts conferidos e confirme: status, comentário e evidências caem no próprio CT, sem trocar de aba. A tecnologia e a URA/esteira vêm da aba 🤖 Automação.',
    ],
  },
  {
    numero: '2.22',
    data: '20/10/2026',
    itens: [
      'Automação (etapa 2) — conferência do ROGUE: carregue o trace da conversa exportado do Grafana (Conversation Finder → ConversationId → Inspect → Data → Download). A ferramenta lê estados, SPs de transição e de prompt, prompts tocados, saídas escolhidas e transferência (inclusive CRN → TLV no mesmo trace), confere com o esperado do CT e sugere OK / Não OK. "Aplicar no CT" anexa o resumo da jornada e o JSON do trace como evidência.',
    ],
  },
  {
    numero: '2.21',
    data: '20/10/2026',
    itens: [
      'Automação (etapa 2) — conferência da URA Legado: depois de ligar, carregue os 2 logs da chamada — Log URA (UraLog\...\URADebug_AAAA-MM-DD_node_canal.txt) e Log Integração (IntegracaoLog\...\IntegracaoDebug_AAAA-MM-DD_node_canal.txt), cada um no seu campo; a ferramenta avisa se não forem do mesmo dia/node/canal. A ferramenta separa as chamadas do arquivo, acha a sua pelo ANI, confere os SPs e prompts esperados do CT e sugere OK / Não OK. "Aplicar no CT" grava o status e anexa o trecho da chamada como evidência (tokens mascarados).',
      'Ao escolher a URA Legado, o caminho dos logs (\\\\URA\\lmcti\\Data\\UraLog\\AAAA\\MM\\DD\\URADebug_AAAA-MM-DD_node_canal.txt) é preenchido; no ROGUE, o Grafana (Conversation Finder / Jaeger).',
    ],
  },
  {
    numero: '2.20',
    data: '20/10/2026',
    itens: [
      'Automação: em URA Legado, escolha a URA que recebe as chamadas (BHZNETUR95, BHZNETUR96, BHZETAECUR98, BHZNETAECUR99 ou CPSNETUR99, com IP e Node); em URA ROGUE, escolha a esteira do CRN (Principal ou Esteira 1-A a 9-I, com o código HML). O número a discar é preenchido sozinho e a URA/esteira vai para o roteiro.',
    ],
  },
  {
    numero: '2.19',
    data: '20/10/2026',
    itens: [
      'Nova aba 🤖 Automação (etapa 1): escolha a tecnologia (URA Legado, URA ROGUE ou ChatBOT WhatsApp), preencha os dados de execução (número/VDN, origem Avaya ou celular, ANI, diretório dos logs da URA ou URL do Grafana, outras informações) e gere o roteiro de automação (.json) com os steps, DTMFs, prompts e SPs esperados dos CTs escolhidos.',
    ],
  },
  {
    numero: '2.18',
    data: '20/10/2026',
    itens: [
      'Prompts: SPECs em que a tabela de prompts tem as colunas "Fala" e "Texto" (a "Fala" vazia ou só com "...") agora têm o prompt lido da coluna com conteúdo real. Antes esses estados ficavam sem prompt, e os steps mostravam só o SP (ex.: RecusaContato com spt=29 e nenhum nome/conteúdo de prompt). Todo step de estado com prompt passa a mostrar o nome (ID) e o conteúdo.',
    ],
  },
  {
    numero: '2.17',
    data: '19/10/2026',
    itens: [
      'Mapear 100% da SPEC: deixe o campo IVR vazio (sem EEP) ou escreva "Mapear 100%" para modelar TODOS os estados e TODAS as saídas da SPEC, sem filtrar por IVR/versão (inclui todos os prompts ainda não ouvidos em algum CT). Não gera bloco regressivo (tudo é testado).',
      'Telas e exportações preparadas para milhares de CTs: os cenários são carregados em lotes ao rolar a página e o xlsx aceita até 20 mil CTs.',
    ],
  },
  {
    numero: '2.16',
    data: '16/10/2026',
    itens: [
      'EEP opcional: incidentes/correções sem escopo podem ser modelados só com a SPEC + código IVR (obrigatório nesse caso). Objetivo, regras e escopo saem do versionamento da SPEC, com aviso nas lacunas e em Revisão Necessária.',
    ],
  },
  {
    numero: '2.15',
    data: '15/10/2026',
    itens: [
      'Correção: nomes de chave e frases como "BasesConsultaMotorTecnico"/"visita técnica" não são mais lidos como a opção de menu "técnico" — isso bloqueava o caminho até estados como MenuPrincipalSemCompras e deixava SPs (ex.: 2470) sem CT.',
      'Prompts com SP novo (ex.: spp=2476 do INI_MP): o step mostra o SP da transição E o SP do prompt, e o SP novo tocado por qualquer step conta como coberto pelo CT.',
    ],
  },
  {
    numero: '2.14',
    data: '15/10/2026',
    itens: [
      'Jornada até o desfecho: todo CT de transição que muda de estado passa a seguir a SPEC até a transferência/fim (ex.: DTMF 9 → SwitchAutoDiagnostico (spt=2465) → TransferMaisProtocolo, com o prompt "Certo_A"), escolhendo o ramo que chega mais rápido ao desfecho; antes o CT parava no SP de passagem.',
      'Condicionais novas: o ramo OPOSTO (irmão no mesmo grupo, ex.: "chave ATIVADA E não tem visita" x "chave DESATIVADA OU já tem visita") passa a ser validado junto, com o SP legado (fica na seção de SPs existentes, não nas marcações novas). Só para decisões de poucos ramos, no máximo 2 por grupo.',
      'Prompt completo: quando o prompt do estado é só um trecho de uma montagem por concat (ex.: MenuPrincipal_CM "INI"), o step mostra o texto completo do exemplo da SPEC ("EXEMPLO 1: DE INI SEM CLARO GAMING"), com as opções do menu; REJ/SIL/RPT idem.',
    ],
  },
  {
    numero: '2.13',
    data: '15/10/2026',
    itens: [
      'Estados por onde o CT só PASSA (ex.: MenuPrincipal): usa o caminho mais fácil — poucas condicionais, ramo padrão ("Else" / "Código base" / "Demais segmentos"), chaves desativadas e sem segmentos/pilotos (ex.: NetGaming). O ponto de validação continua sendo o estado alterado.',
      'Os steps passam a usar exatamente as transições escolhidas pelo caminho (antes um CT ANI Não podia mostrar um salto "ANI SIM > … Cliente NET Gaming" que não combina com a jornada).',
      'ANI Não segue pela identificação (CPF/CNPJ/Contrato) e toca o prompt correspondente (ex.: DTMF_INI_AniNao); ANI Sim segue a própria jornada (sem identificação) e toca o prompt ANI Sim.',
    ],
  },
  {
    numero: '2.12',
    data: '15/10/2026',
    itens: [
      'Caminho de entrada: os CTs passam a seguir a entrada NATIVA da URA (ex.: CRN "Entrada normal > Entrou pelo DNIS 0800 → Saudacao → …") em vez de um hand-off vindo de outra URA (ex.: "Atendimento Televendas > Veio do estado MenuRentabilizacao"), que antes aparecia só por ser o caminho mais curto.',
      'Regressão: um CT por hand-off de outra URA confirma que o estado alterado também funciona quando a chamada vem de outra URA.',
    ],
  },
  {
    numero: '2.11',
    data: '13/10/2026',
    itens: [
      'Planejamento: o objetivo agora vem da seção "OBJETIVO DO PROJETO" do EEP (também em modelos antigos com títulos numerados e em maiúsculas), sem misturar outras seções; escopo, justificativa e "fora do escopo" do EEP também são lidos.',
    ],
  },
  {
    numero: '2.10',
    data: '13/10/2026',
    itens: [
      'Marcações de BI: duas seções claramente separadas — ① marcações NOVAS do projeto e ② marcações EXISTENTES (produção) conferidas na regressão, com contadores, descrição do SP e títulos próprios no xlsx.',
    ],
  },
  {
    numero: '2.9',
    data: '13/10/2026',
    itens: [
      'Marcações de BI: os SPs já existentes em produção conferidos pelos CTs regressivos aparecem numa seção própria, separada das marcações novas do projeto (também no xlsx).',
    ],
  },
  {
    numero: '2.8',
    data: '13/10/2026',
    itens: [
      'Marcações de BI: projeto sem marcações na VersionamentoBI (só alteração de prompts) passa a mostrar a aba vazia — SPs antigos que aparecem nos CTs não são mais listados como marcações do projeto.',
      'CTs regressivos continuam conferindo SPs já existentes em produção, mas eles não entram na lista de marcações do projeto (ver 2.9).',
    ],
  },
  {
    numero: '2.7',
    data: '13/10/2026',
    itens: [
      'Regressão baseada em risco: além dos 2 CTs fixos, passa a cobrir (com limites) as saídas legadas dos estados alterados, entradas alternativas, cliente ANI Sim e chaves desativadas citadas nas condições.',
      'CTs regressivos deixam de ser marcados como "SP pendente" (o objetivo deles é provar que nada mudou).',
    ],
  },
  {
    numero: '2.6',
    data: '13/10/2026',
    itens: [
      'Estados com montagem por concat (ex.: MenuDinamicoTecnico): quando o versionamento cita concat/tempo de silêncio, cada variação de montagem descrita nos "Exemplo ..." vira CT (por perfil de produtos e por chave), com as escadas REJ, RPT e SIL agrupadas.',
      'Linhas do versionamento sem cor não saem mais do escopo (só as cores passam a identificar células alteradas).',
    ],
  },
  {
    numero: '2.5',
    data: '13/10/2026',
    itens: [
      'Prompts em amarelo nas abas de estado voltam a ser mapeados quando a cor das linhas do versionamento (ex.: amarelo) é diferente da cor do cabeçalho do bloco: a cor das linhas passa a contar como cor do projeto.',
    ],
  },
  {
    numero: '2.4',
    data: '13/10/2026',
    itens: [
      'Projetos sem ScriptPoint novo (só alteração/inclusão de prompts, ex.: IVR-173251): testa o que o versionamento cita (prompts, chaves e DTMFs) em vez de todas as ramificações do estado — a modelagem caiu de 182 para cerca de 60 CTs na SPEC de teste.',
      'Prompts citados no versionamento ("*_AgendamentoDeVT") entram na validação de fraseologia mesmo sem cor na célula.',
      'Quando só algumas linhas do bloco do projeto estão pintadas (ex.: amarelo), o escopo passa a ser só as pintadas; os estados em branco são listados em Revisão Necessária.',
    ],
  },
  {
    numero: '2.3',
    data: '13/10/2026',
    itens: [
      'Correção: SPECs em que as linhas do bloco têm "Merge em" + data (ex.: NET) voltaram a ser lidas — a versão 2.1 ia parar o bloco nessas linhas e gerava 0 CTs.',
      'CT que marca um SP sem trocar de estado (ex.: digitar * no PegaCPF) agora traz o step com a AÇÃO que gera a marcação — antes mostrava o SP sem dizer como provocá-lo.',
    ],
  },
  {
    numero: '2.2',
    data: '13/10/2026',
    itens: [
      'Prompts novos (células na cor da versão) passam a ser validados: 1 CT por INI, por escada REJ e por escada SIL de cada variante (ex.: Casa/Empresa), com o texto de cada tentativa.',
      'Reconhece cabeçalhos de prompts e transições de outras SPECs ("Nome da gravação", "Texto a gravar", "Resultados", "Marcação de BI").',
    ],
  },
  {
    numero: '2.1',
    data: '13/10/2026',
    itens: [
      'SPEC ClaroEmpresas: reconhece as abas VersionControl/VersionControlBI (antes o projeto saía com 0 CTs).',
      'Blocos de versionamento colados (sem linha em branco) deixam de misturar o título do bloco com os estados.',
      'Coluna de ScriptPoint sem cabeçalho nas transições passa a ser lida (SPs que antes ficavam sem CT).',
    ],
  },
  {
    numero: '2.0',
    data: '06/10/2026',
    itens: [
      'REJ/SIL/INV/INC: um CT por escada de tentativas, com o prompt de cada tentativa e a jornada seguida até o fim (transferência, encerramento, mudança de estado).',
      'Todos os blocos do mesmo IVR são lidos; o IVR é descoberto pelo nome do projeto no EEP; sem plano B silencioso quando o IVR não existe na SPEC (aviso explicando o motivo).',
      'Novas abas: Marcações de BI (com o estado da marcação), Execução dos Testes (status, bug, evidências, barra de evolução, PDF e ZIP) e Planejamento detalhado.',
      'Trabalho salvo automaticamente no navegador (F5 e dia seguinte); só "Nova Modelagem" apaga.',
      'Exportar xlsx e PDF independentes da sessão do servidor.',
      'Manual do usuário dentro da ferramenta e número de versão.',
    ],
  },
  {
    numero: '1.2',
    data: '30/09/2026',
    itens: [
      'Ajustes do motor: ScriptPoints dos prompts (REJ/SIL/INI), colunas numeradas de condição, Gherkin limitado a 255 caracteres, massa de testes com requisitos reais.',
    ],
  },
  {
    numero: '1.1',
    data: '25/08/2026',
    itens: [
      'Upload mais seguro: detecção de arquivo truncado/corrompido, conversão de SPEC .xlsb, confirmação real do envio.',
      'Removida a importação por link do Google Sheets.',
    ],
  },
  {
    numero: '1.0',
    data: '24/08/2026',
    itens: ['Versão inicial na web: SPEC + EEP geram a modelagem BDD/Gherkin, abas de resultado e exportação em xlsx.'],
  },
];
window.MODELER_VERSAO = window.MODELER_VERSOES[0];
