/* Versão do Modeler Assistant — ÚNICO lugar para atualizar a cada entrega.
   Regra: MAIOR.MENOR — "menor" sobe com melhorias/correções; "maior" com mudança grande de comportamento.
   A primeira entrada da lista é a versão atual (aparece ao lado do botão Manual e no Manual). */
window.MODELER_VERSOES = [
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
