package main

import (
    "bufio"
    "fmt"
    "os"
    "os/exec"
    "path/filepath"
    "strings"
)

const psScript = `$ErrorActionPreference = 'Continue'
try { $Host.UI.RawUI.WindowTitle = 'DoobieLogic Local AI Launcher' } catch {}

$logDir = Join-Path $env:LOCALAPPDATA 'DoobieLogic\logs'
$logPath = Join-Path $logDir 'local-ai-launcher.log'
try {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    Start-Transcript -Path $logPath -Append -ErrorAction SilentlyContinue | Out-Null
} catch {}

function Write-Section([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 62) -ForegroundColor DarkCyan
    Write-Host ('  ' + $Text) -ForegroundColor Cyan
    Write-Host ('=' * 62) -ForegroundColor DarkCyan
}

function Test-Ollama {
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -Method Get -TimeoutSec 3
        return $true
    } catch { return $false }
}

function Find-Ollama {
    $cmd = Get-Command 'ollama.exe' -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'),
        (Join-Path $env:LOCALAPPDATA 'Ollama\ollama.exe'),
        (Join-Path $env:ProgramFiles 'Ollama\ollama.exe')
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

function Finish([int]$Code) {
    Write-Host ''
    Write-Host ('Diagnostic log: ' + $logPath) -ForegroundColor DarkGray
    try { Stop-Transcript | Out-Null } catch {}
    Write-Host ''
    Read-Host 'Press Enter to close'
    exit $Code
}

try {
    Clear-Host
    Write-Host 'DoobieLogic Local AI' -ForegroundColor Cyan
    Write-Host 'Workstation runtime launcher v3' -ForegroundColor DarkGray
    Write-Host ''
    Write-Host 'Generation model : qwen3:14b'
    Write-Host 'Embedding model  : embeddinggemma:latest'
    Write-Host 'Ollama endpoint   : http://127.0.0.1:11434'
    Write-Host 'Tunnel service    : cloudflared / doobielogic-ai'

    Write-Section '1. Ollama runtime'
    $ollamaPath = Find-Ollama
    if (Test-Ollama) {
        Write-Host '[OK] Ollama is already listening on port 11434.' -ForegroundColor Green
    } else {
        if (-not $ollamaPath) {
            Write-Host '[ERROR] Ollama was not found on this computer.' -ForegroundColor Red
            Write-Host 'Install Ollama for Windows, then run this launcher again.' -ForegroundColor Yellow
            Finish 1
        }
        Write-Host ('Starting Ollama from: ' + $ollamaPath) -ForegroundColor Yellow
        try { Start-Process -FilePath $ollamaPath -ArgumentList 'serve' -WindowStyle Hidden | Out-Null }
        catch {
            Write-Host ('[ERROR] Could not start Ollama: ' + $_.Exception.Message) -ForegroundColor Red
            Finish 1
        }
        $ready = $false
        for ($i = 0; $i -lt 20; $i++) {
            Start-Sleep -Seconds 1
            if (Test-Ollama) { $ready = $true; break }
            Write-Host -NoNewline '.' -ForegroundColor DarkGray
        }
        Write-Host ''
        if (-not $ready) {
            Write-Host '[ERROR] Ollama did not become ready on port 11434.' -ForegroundColor Red
            Write-Host 'Check Task Manager for Ollama and make sure another process is not blocking the port.' -ForegroundColor Yellow
            Finish 1
        }
        Write-Host '[OK] Ollama started successfully.' -ForegroundColor Green
    }

    Write-Section '2. DoobieLogic models'
    $modelNames = @()
    try {
        $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -Method Get -TimeoutSec 5
        if ($tags.models) { $modelNames = @($tags.models | ForEach-Object { $_.name }) }
    } catch {
        Write-Host ('[WARN] Could not read Ollama model list: ' + $_.Exception.Message) -ForegroundColor Yellow
    }
    $generationFound = $false
    $embeddingFound = $false
    foreach ($name in $modelNames) {
        if ($name -eq 'qwen3:14b' -or $name -eq 'qwen3:14b-latest') { $generationFound = $true }
        if ($name -eq 'embeddinggemma:latest' -or $name -eq 'embeddinggemma') { $embeddingFound = $true }
    }
    if ($generationFound) {
        Write-Host '[OK] qwen3:14b is installed.' -ForegroundColor Green
    } else {
        Write-Host '[WARN] qwen3:14b is not installed.' -ForegroundColor Yellow
        if ($ollamaPath) { Write-Host ('       Install with: & "' + $ollamaPath + '" pull qwen3:14b') }
        else { Write-Host '       Install with: ollama pull qwen3:14b' }
    }
    if ($embeddingFound) {
        Write-Host '[OK] embeddinggemma:latest is installed.' -ForegroundColor Green
    } else {
        Write-Host '[WARN] embeddinggemma:latest is not installed.' -ForegroundColor Yellow
        if ($ollamaPath) { Write-Host ('       Install with: & "' + $ollamaPath + '" pull embeddinggemma:latest') }
        else { Write-Host '       Install with: ollama pull embeddinggemma:latest' }
    }

    Write-Section '3. Cloudflare tunnel service'
    $tunnelReady = $false
    $svc = Get-Service -Name 'cloudflared' -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host '[WARN] Windows service "cloudflared" was not found.' -ForegroundColor Yellow
        Write-Host '       Local AI will work on this PC, but hosted DoobieLogic cannot reach it through the production tunnel.'
    } elseif ($svc.Status -eq 'Running') {
        Write-Host '[OK] cloudflared service is running.' -ForegroundColor Green
        $tunnelReady = $true
    } else {
        Write-Host ('cloudflared service is ' + $svc.Status + '. Attempting to start it...') -ForegroundColor Yellow
        try {
            Start-Service -Name 'cloudflared' -ErrorAction Stop
            Start-Sleep -Seconds 2
            $svc = Get-Service -Name 'cloudflared' -ErrorAction SilentlyContinue
            if ($svc -and $svc.Status -eq 'Running') {
                Write-Host '[OK] cloudflared service started.' -ForegroundColor Green
                $tunnelReady = $true
            }
        } catch {
            Write-Host '[WARN] Starting cloudflared may require Administrator permission.' -ForegroundColor Yellow
            Write-Host '       A Windows UAC prompt will appear. Approve it to start the tunnel.'
            $elevated = "Start-Service -Name 'cloudflared'; Start-Sleep -Seconds 2"
            try {
                $encodedBytes = [System.Text.Encoding]::Unicode.GetBytes($elevated)
                $encodedCommand = [Convert]::ToBase64String($encodedBytes)
                $p = Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand',$encodedCommand) -Wait -PassThru
                $svc = Get-Service -Name 'cloudflared' -ErrorAction SilentlyContinue
                if ($svc -and $svc.Status -eq 'Running') {
                    Write-Host '[OK] cloudflared service started with Administrator permission.' -ForegroundColor Green
                    $tunnelReady = $true
                } else {
                    Write-Host '[WARN] cloudflared is still not running.' -ForegroundColor Yellow
                }
            } catch {
                Write-Host '[WARN] Administrator request was cancelled or failed.' -ForegroundColor Yellow
            }
        }
    }

    Write-Section '4. Final health check'
    $apiReady = $false
    try {
        $models = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/v1/models' -Method Get -TimeoutSec 5
        if ($models) { $apiReady = $true }
    } catch {
        Write-Host ('[ERROR] Ollama /v1/models check failed: ' + $_.Exception.Message) -ForegroundColor Red
    }
    if ($apiReady -and $generationFound -and $embeddingFound) {
        Write-Host '[READY] DoobieLogic local AI is online.' -ForegroundColor Green
        if ($tunnelReady) { Write-Host '[READY] Cloudflare tunnel service is online for hosted DoobieLogic.' -ForegroundColor Green }
        else { Write-Host '[LOCAL ONLY] AI is running locally, but the tunnel is not confirmed.' -ForegroundColor Yellow }
        Finish 0
    } elseif ($apiReady) {
        Write-Host '[PARTIAL] Ollama is online, but one or more required models are missing.' -ForegroundColor Yellow
        Write-Host 'Install the missing model(s) shown above, then run this launcher again.'
        Finish 2
    } else {
        Write-Host '[ERROR] The OpenAI-compatible Ollama endpoint did not pass its health check.' -ForegroundColor Red
        Finish 1
    }
} catch {
    Write-Host ''
    Write-Host ('[FATAL] ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
    Finish 1
}
`

func pause(msg string) {
    fmt.Println()
    fmt.Print(msg)
    _, _ = bufio.NewReader(os.Stdin).ReadString('\n')
}

func main() {
    fmt.Println("DoobieLogic Local AI Launcher v3")
    fmt.Println("Starting Windows PowerShell...")

    scriptPath := filepath.Join(os.TempDir(), "DoobieLogic_Local_AI_Launcher.ps1")
    script := strings.ReplaceAll(psScript, "\n", "\r\n")
    if err := os.WriteFile(scriptPath, []byte(script), 0600); err != nil {
        fmt.Printf("\nERROR: Could not create the PowerShell launcher script:\n%v\n", err)
        pause("Press Enter to close...")
        return
    }

    cmd := exec.Command("powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath)
    cmd.Stdin = os.Stdin
    cmd.Stdout = os.Stdout
    cmd.Stderr = os.Stderr

    err := cmd.Run()
    if err != nil {
        fmt.Printf("\nPowerShell finished with: %v\n", err)
        fmt.Println("The launcher window will stay open so the error above can be read.")
        pause("Press Enter to close...")
        return
    }

    fmt.Println("\nPowerShell launcher finished successfully.")
    pause("Press Enter to close...")
}
