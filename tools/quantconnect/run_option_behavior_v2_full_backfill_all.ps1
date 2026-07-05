$ErrorActionPreference = "Stop"

$Template = "tools\quantconnect\signalforge_option_behavior_v2_algorithm_template.py"
$FullBatchDir = "artifacts\qc_option_behavior_v2_backfill_batches_20210601_20260531_full"

if (-not (Test-Path $FullBatchDir)) {
  throw "Full batch dir not found: $FullBatchDir"
}

# Verify template has required v2 writer + clear support.
$TemplateText = Get-Content $Template -Raw

if ($TemplateText -notmatch "rows = \[self\._ensure_v2_output_row\(r\) for r in self\.rows\]") {
  throw "Template missing forced v2 writer row conversion"
}

if ($TemplateText -notmatch "_clear_entire_object_store") {
  throw "Template missing full ObjectStore clear helper"
}

if ($TemplateText -notmatch "clear_object_store_on_start") {
  throw "Template missing clear_object_store_on_start flag"
}

$FullRunId = "v2full_" + (Get-Date -Format "yyyyMMdd_HHmmss")
$RenderedRoot = "artifacts\qc_option_behavior_v2_full_run_$FullRunId"
$StatusPath = Join-Path $RenderedRoot "submission_status.csv"
$TranscriptPath = Join-Path $RenderedRoot "submission_transcript.log"

New-Item -ItemType Directory -Force $RenderedRoot | Out-Null

Start-Transcript -Path $TranscriptPath -Append

try {
  "`n=== SignalForge option behavior v2 full run ==="
  "FullRunId: $FullRunId"
  "RenderedRoot: $RenderedRoot"
  "StatusPath: $StatusPath"
  "TranscriptPath: $TranscriptPath"

  "`n=== rendering all batches ==="

  $BatchFiles = Get-ChildItem $FullBatchDir -Filter "qc_option_behavior_v2_batch_*.json" | Sort-Object Name
  $BatchIndex = 0

  foreach ($File in $BatchFiles) {
    $BatchIndex += 1

    $BaseName = $File.BaseName
    $RunDir = Join-Path $RenderedRoot $BaseName
    $RunBatch = Join-Path $RunDir "$BaseName`_$FullRunId.json"

    New-Item -ItemType Directory -Force $RunDir | Out-Null

    $Batch = Get-Content $File.FullName -Raw | ConvertFrom-Json
    $Batch.batch_id = "$BaseName`_$FullRunId"

    # Full ObjectStore clear only once, at the beginning of the full run.
    $Batch | Add-Member -NotePropertyName clear_object_store_on_start -NotePropertyValue ($BatchIndex -eq 1) -Force

    $Batch | ConvertTo-Json -Depth 100 | Set-Content $RunBatch -Encoding UTF8

    python tools\quantconnect\option_behavior_v2_qc_rest_runner.py `
      --template $Template `
      --batch $RunBatch `
      --rendered-output "$RunDir\main.py" `
      --payload-output-dir "$RunDir\payload_chunks" `
      --payload-chunk-size 60000

    if ($LASTEXITCODE -ne 0) {
      throw "Render failed for $RunBatch"
    }
  }

  "`n=== verifying rendered files ==="

  $BadRendered = Get-ChildItem $RenderedRoot -Recurse -Filter "main.py" |
    Where-Object {
      $Text = Get-Content $_.FullName -Raw

      ($Text -notmatch "_clear_entire_object_store") -or
      ($Text -notmatch "clear_object_store_on_start") -or
      ($Text -notmatch "rows = \[self\._ensure_v2_output_row\(r\) for r in self\.rows\]") -or
      ($Text -match "rows = self\.rows")
    }

  if ($BadRendered.Count -gt 0) {
    "`nBAD RENDERED FILES:"
    $BadRendered | Select-Object FullName | Format-Table -AutoSize
    throw "Rendered verification failed"
  }

  "`nRendered verification passed"

  "`n=== verifying clear flag ==="

  $RenderedBatchFiles = Get-ChildItem $RenderedRoot -Recurse -Filter "*_$FullRunId.json" | Sort-Object FullName

  $ClearFlagTable = foreach ($BatchFile in $RenderedBatchFiles) {
    $Batch = Get-Content $BatchFile.FullName -Raw | ConvertFrom-Json
    [PSCustomObject]@{
      File = $BatchFile.Name
      BatchId = $Batch.batch_id
      ClearObjectStoreOnStart = $Batch.clear_object_store_on_start
    }
  }

  $ClearFlagTable | Format-Table -AutoSize

  $ClearCount = @($ClearFlagTable | Where-Object { $_.ClearObjectStoreOnStart -eq $true }).Count
  if ($ClearCount -ne 1) {
    throw "Expected exactly one clear_object_store_on_start=true batch, found $ClearCount"
  }

  if ($ClearFlagTable[0].ClearObjectStoreOnStart -ne $true) {
    throw "First batch does not have clear_object_store_on_start=true"
  }

  "`n=== submitting all batches sequentially ==="

  "timestamp,batch_index,batch_id,run_batch,exit_code,state" | Set-Content $StatusPath -Encoding UTF8

  $SubmitIndex = 0

  foreach ($BatchFile in $RenderedBatchFiles) {
    $SubmitIndex += 1

    $RunBatch = $BatchFile.FullName
    $RunDir = Split-Path $RunBatch -Parent
    $BatchId = [IO.Path]::GetFileNameWithoutExtension($RunBatch)

    "`n=== submitting $SubmitIndex / $($RenderedBatchFiles.Count): $BatchId ==="

    python tools\quantconnect\option_behavior_v2_qc_rest_runner.py `
      --template $Template `
      --batch $RunBatch `
      --rendered-output "$RunDir\main.py" `
      --payload-output-dir "$RunDir\payload_chunks" `
      --payload-chunk-size 60000 `
      --backtest-name "sf_option_behavior_v2_$BatchId" `
      --submit `
      --monitor-backtest `
      --backtest-poll-seconds 60

    $ExitCode = $LASTEXITCODE
    $State = if ($ExitCode -eq 0) { "submitted_or_completed" } else { "failed" }
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    "`"$Timestamp`",$SubmitIndex,`"$BatchId`",`"$RunBatch`",$ExitCode,`"$State`"" |
      Add-Content $StatusPath -Encoding UTF8

    if ($SubmitIndex -eq 1 -and $ExitCode -ne 0) {
      throw "First batch failed. Stopping because first batch is responsible for clearing ObjectStore."
    }

    if ($ExitCode -ne 0) {
      "WARNING: batch failed but continuing: $BatchId"
    }
  }

  "`n=== full submission loop finished ==="
  "FullRunId: $FullRunId"
  "RenderedRoot: $RenderedRoot"
  "StatusPath: $StatusPath"
  "TranscriptPath: $TranscriptPath"
}
finally {
  Stop-Transcript
}
