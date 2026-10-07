/* Versão do Modeler Assistant — ÚNICO lugar para atualizar a cada entrega.
   Regra: MAIOR.MENOR — "menor" sobe com melhorias/correções; "maior" com mudança grande de comportamento.
   A primeira entrada da lista é a versão atual (aparece ao lado do botão Manual e no Manual). */
window.MODELER_VERSOES = [
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
