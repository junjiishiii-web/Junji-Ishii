# Configura o Modeler Assistant para rodar como servidor web persistente
# nesta maquina: cria a regra de firewall (acesso pela rede) e a Tarefa
# Agendada que inicia o servidor sozinho sempre que voce logar no Windows.
#
# PRECISA rodar como Administrador:
#   clique direito neste arquivo > "Executar com o PowerShell" (como admin)
#   ou abra um PowerShell como administrador e rode:  .\configurar_servidor_web.ps1

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
    Write-Host "[ERRO] Este script precisa ser executado como Administrador." -ForegroundColor Red
    Write-Host "       Clique direito no arquivo > Executar com o PowerShell (como administrador)."
    exit 1
}

$raiz = $PSScriptRoot
$pythonw = Join-Path $raiz "venv\Scripts\pythonw.exe"
$script = Join-Path $raiz "backend\servidor.py"
$porta = 8001
$nomeTarefa = "ModelerAssistantWeb"
$nomeRegra = "Modeler Assistant Web"

if (-not (Test-Path $pythonw)) {
    Write-Host "[ERRO] Nao encontrei $pythonw" -ForegroundColor Red
    Write-Host "       Rode iniciar_qa_modeler.bat uma vez antes, para criar a venv com as dependencias."
    exit 1
}

Write-Host "[1/2] Configurando regra de firewall (porta $porta)..."
$regraExistente = Get-NetFirewallRule -DisplayName $nomeRegra -ErrorAction SilentlyContinue
if ($regraExistente) {
    Write-Host "      Regra ja existia, mantendo."
} else {
    New-NetFirewallRule -DisplayName $nomeRegra -Direction Inbound -Protocol TCP -LocalPort $porta -Action Allow -Profile Any `
        -Description "Permite acesso ao Modeler Assistant (servidor web local) pela rede" | Out-Null
    Write-Host "      Regra criada."
}

Write-Host "[2/2] Registrando Tarefa Agendada '$nomeTarefa' (inicia ao logar nesta maquina)..."
Unregister-ScheduledTask -TaskName $nomeTarefa -Confirm:$false -ErrorAction SilentlyContinue

$acao    = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$script`"" -WorkingDirectory (Join-Path $raiz "backend")
$gatilho = New-ScheduledTaskTrigger -AtLogOn
$config  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName $nomeTarefa -Action $acao -Trigger $gatilho -Settings $config `
    -Description "Modeler Assistant - servidor web local (multiusuario)" -User $env:USERNAME | Out-Null

Write-Host ""
Write-Host "Pronto! O servidor vai iniciar sozinho no proximo login nesta maquina." -ForegroundColor Green
Write-Host "Para iniciar AGORA sem precisar relogar, rode:"
Write-Host "  Start-ScheduledTask -TaskName '$nomeTarefa'"
Write-Host ""
Write-Host "Endereco pros colegas acessarem:"
Write-Host "  http://$($env:COMPUTERNAME):$porta/app/index.html"
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '169.*' -and $_.IPAddress -ne '127.0.0.1' } |
    ForEach-Object { Write-Host "  http://$($_.IPAddress):$porta/app/index.html" }
