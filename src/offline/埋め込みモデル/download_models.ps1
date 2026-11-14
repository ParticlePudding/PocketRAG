# 埋め込みモデルのダウンロード（インターネットにつながるPCで1回だけ実行）
#   モデルをダウンロード.bat から実行するか、PowerShellで次のように実行します。
#   .\download_models.ps1              … 軽量（ruri-v3-30m）と高精度（bge-m3）の両方
#   .\download_models.ps1 -Model ruri  … 軽量のみ
#   .\download_models.ps1 -Gpu         … GPU向けの fp16 版も取る（容量が増えます）
param(
  [ValidateSet('all', 'ruri', 'bge')][string]$Model = 'all',
  [switch]$Gpu
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

$catalog = [ordered]@{
  ruri = @{ Repo = 'sirasagi62/ruri-v3-30m-ONNX'; Dir = 'ruri-v3-30m'; Note = '軽量・日本語特化（名古屋大学 ruri-v3-30m）' }
  bge  = @{ Repo = 'Xenova/bge-m3';               Dir = 'bge-m3';      Note = '高精度・多言語（BAAI bge-m3）' }
}
$baseFiles = @('config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', '1_Pooling/config.json')
$cpuPref = @('onnx/model_quantized.onnx', 'onnx/model_int8.onnx', 'onnx/model_uint8.onnx', 'onnx/model.onnx', 'onnx/model_fp16.onnx')
$hasCurl = [bool](Get-Command curl.exe -ErrorAction SilentlyContinue)

function Get-HfFile([string]$repo, [string]$file, [string]$dest) {
  $url = "https://huggingface.co/$repo/resolve/main/$file"
  $out = Join-Path $dest ($file -replace '/', '\')
  New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null
  if (Test-Path $out) { Write-Host "  （取得済み）$file"; return }
  Write-Host "  取得中: $file"
  $tmp = "$out.part"
  if ($hasCurl) {
    & curl.exe -L --fail --progress-bar -o $tmp $url
    if ($LASTEXITCODE -ne 0) { throw "ダウンロードに失敗しました: $url" }
  } else {
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
  }
  Move-Item -Force $tmp $out
}

if ($Model -eq 'all') { $keys = @($catalog.Keys) } else { $keys = @($Model) }
foreach ($k in $keys) {
  $m = $catalog[$k]
  Write-Host ''
  Write-Host "== $($m.Dir) : $($m.Note) =="
  $info = Invoke-RestMethod -Uri "https://huggingface.co/api/models/$($m.Repo)" -UseBasicParsing
  $names = @($info.siblings | ForEach-Object { $_.rfilename })
  $files = @($baseFiles | Where-Object { $names -contains $_ })
  if ($files -notcontains 'tokenizer.json') { Write-Warning "tokenizer.json が見つかりません（$($m.Repo)）" }
  $onnx = $cpuPref | Where-Object { $names -contains $_ } | Select-Object -First 1
  if (-not $onnx) { throw "ONNXファイルが見つかりません（$($m.Repo)）" }
  $files += $onnx
  if ($Gpu -and ($names -contains 'onnx/model_fp16.onnx') -and ($files -notcontains 'onnx/model_fp16.onnx')) { $files += 'onnx/model_fp16.onnx' }
  foreach ($f in @($files)) { $files += @($names | Where-Object { $_ -like "$($f)_data*" }) }   # 大きいモデルの外部データ
  $dest = Join-Path $root $m.Dir
  foreach ($f in $files) { Get-HfFile $m.Repo $f $dest }
}
Write-Host ''
Write-Host '完了しました。できたモデルのフォルダを社内PCにコピーし、'
Write-Host '各ツールの「モデルフォルダを追加…」でモデルのフォルダを選んでください。'
