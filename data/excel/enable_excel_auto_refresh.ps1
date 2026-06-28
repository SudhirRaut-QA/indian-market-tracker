param(
    [string]$CsvPath = "",
    [string]$XlsxPath = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\.." )).Path

if (-not $CsvPath) {
    $CsvPath = (Get-ChildItem -Path $PSScriptRoot -Filter "upcoming_dividends_full_*.csv" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1).FullName
}
if (-not $CsvPath -or -not (Test-Path $CsvPath)) {
    throw "No CSV found. Pass -CsvPath explicitly."
}
$CsvPath = (Resolve-Path $CsvPath).Path

if (-not $XlsxPath) {
    $XlsxPath = [System.IO.Path]::ChangeExtension($CsvPath, ".xlsx")
}
if (-not (Test-Path $XlsxPath)) {
    throw "XLSX file not found: $XlsxPath"
}
$XlsxPath = (Resolve-Path $XlsxPath).Path

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$rebuildScript = (Resolve-Path (Join-Path $PSScriptRoot "rebuild_upcoming_dividends.py")).Path
if (-not (Test-Path $rebuildScript)) {
    throw "Rebuild script not found: $rebuildScript"
}

$xlsmPath = [System.IO.Path]::ChangeExtension($XlsxPath, ".xlsm")

$vba = @"
Option Explicit

Private Sub Workbook_Open()
    On Error GoTo SafeExit
    Application.ScreenUpdating = False
    Application.DisplayAlerts = False

    RebuildDividendData
    LoadCsvIntoFirstSheet

SafeExit:
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True
End Sub

Private Sub RebuildDividendData()
    Dim shellObj As Object
    Dim rc As Long
    Dim cmd As String
    Dim pyCmd As String

    pyCmd = ""python""
    If Dir(ThisWorkbook.Path & ""\..\..\.venv\Scripts\python.exe"") <> "" Then
        pyCmd = """""" & ThisWorkbook.Path & ""\..\..\.venv\Scripts\python.exe"" & """"""
    End If

    cmd = ""cmd /c cd /d """""" & ThisWorkbook.Path & """""" && "" & pyCmd & "" """"rebuild_upcoming_dividends.py"""" --days-ahead 45 --throttle 0.15""

    Set shellObj = CreateObject(""WScript.Shell"")
    rc = shellObj.Run(cmd, 0, True)
End Sub

Private Sub LoadCsvIntoFirstSheet()
    Dim csvWb As Workbook
    Dim srcWs As Worksheet
    Dim dstWs As Worksheet

    Set dstWs = ThisWorkbook.Worksheets(1)

    Application.EnableEvents = False
    dstWs.Cells.Clear

    Set csvWb = Workbooks.Open(ThisWorkbook.Path & ""\upcoming_dividends_latest.csv"")
    Set srcWs = csvWb.Worksheets(1)

    srcWs.UsedRange.Copy
    dstWs.Range(""A1"").PasteSpecial xlPasteValues

    csvWb.Close SaveChanges:=False
    Application.CutCopyMode = False

    dstWs.Columns.AutoFit
    ThisWorkbook.Save
    Application.EnableEvents = True
End Sub
"@

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

$wb = $null
$macroInjected = $false
$macroBlockedReason = ""
try {
    try {
        $wb = $excel.Workbooks.Open($XlsxPath)
    }
    catch {
        # If XLSX is locked/open elsewhere, bootstrap workbook from CSV instead.
        $wb = $excel.Workbooks.Open($CsvPath)
    }

    # Save as macro-enabled workbook.
    $wb.SaveAs($xlsmPath, 52)

    # Inject Workbook_Open macro.
    try {
        $vbProject = $wb.VBProject
        if ($null -eq $vbProject) {
            throw "VBProject is unavailable (likely blocked by Excel security settings)."
        }
        $vbComp = $vbProject.VBComponents.Item("ThisWorkbook")
        $codeModule = $vbComp.CodeModule
        if ($codeModule.CountOfLines -gt 0) {
            $codeModule.DeleteLines(1, $codeModule.CountOfLines)
        }
        $codeModule.AddFromString($vba)
        $macroInjected = $true
    }
    catch {
        $macroBlockedReason = $_.Exception.Message
    }

    $wb.Save()
    Write-Output "AUTO_REFRESH_WORKBOOK=$xlsmPath"
    if ($macroInjected) {
        Write-Output "MACRO_INJECTION=SUCCESS"
    }
    else {
        Write-Output "MACRO_INJECTION=BLOCKED"
        Write-Output "MACRO_INJECTION_REASON=$macroBlockedReason"
        Write-Output "Enable Excel setting: Trust Center > Trust Center Settings > Macro Settings > Trust access to the VBA project object model"
    }
}
finally {
    if ($wb -ne $null) {
        $wb.Close($true)
    }
    $excel.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
}
