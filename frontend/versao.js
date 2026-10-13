/* Versão do Modeler Assistant — ÚNICO lugar para atualizar a cada entrega.
   Regra: MAIOR.MENOR — "menor" sobe com melhorias/correções; "maior" com mudança grande de comportamento.
   A primeira entrada da lista é a versão atual (aparece ao lado do botão Manual e no Manual). */
window.MODELER_VERSOES = [
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
