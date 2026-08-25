<#
Converte um arquivo .xlsb (Pasta de Trabalho Binaria do Excel) para .xlsx
usando o proprio Excel instalado na maquina (COM automation) — sem
precisar instalar nada, sem depender do servidor. Preserva 100% da
formatacao/cor, porque quem faz a conversao e o Excel de verdade.

Uso:
  1) Arraste um arquivo .xlsb em cima deste script (ou do .bat ao lado), OU
  2) Rode direto: powershell -File ConverterXLSB.ps1 -CaminhoArquivo "C:\caminho\arquivo.xlsb"
  3) Sem nenhum argumento, abre uma janela pra voce escolher o arquivo.

O arquivo convertido (.xlsx) e salvo na MESMA pasta do .xlsb original.
#>
param(
    [Parameter(Mandatory = $false)]
    [string]$CaminhoArquivo
)

if (-not $CaminhoArquivo) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Filter = "Excel Binary Workbook (*.xlsb)|*.xlsb"
    $dialog.Title = "Selecione o arquivo .xlsb para converter"
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        Write-Host "Nenhum arquivo selecionado. Cancelado."
        exit 0
    }
    $CaminhoArquivo = $dialog.FileName
}

if (-not (Test-Path -LiteralPath $CaminhoArquivo)) {
    Write-Host "Arquivo nao encontrado: $CaminhoArquivo" -ForegroundColor Red
    Read-Host "Pressione Enter para fechar"
    exit 1
}

if ([System.IO.Path]::GetExtension($CaminhoArquivo).ToLower() -ne ".xlsb") {
    Write-Host "Isso nao parece um arquivo .xlsb: $CaminhoArquivo" -ForegroundColor Red
    Read-Host "Pressione Enter para fechar"
    exit 1
}

$CaminhoArquivo = (Resolve-Path -LiteralPath $CaminhoArquivo).Path
$CaminhoSaida = [System.IO.Path]::ChangeExtension($CaminhoArquivo, ".xlsx")

Write-Host "Abrindo Excel (pode levar alguns segundos)..."
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

try {
    $workbook = $excel.Workbooks.Open($CaminhoArquivo)
    Write-Host "Convertendo para .xlsx..."
    # 51 = xlOpenXMLWorkbook (.xlsx)
    $workbook.SaveAs($CaminhoSaida, 51)
    $workbook.Close($false)
    Write-Host ""
    Write-Host "Convertido com sucesso:" -ForegroundColor Green
    Write-Host $CaminhoSaida -ForegroundColor Green
}
catch {
    Write-Host "Erro ao converter: $_" -ForegroundColor Red
}
finally {
    $excel.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

Write-Host ""
Write-Host "Pronto! Envie o arquivo .xlsx gerado no Modeler Assistant."
Read-Host "Pressione Enter para fechar"
