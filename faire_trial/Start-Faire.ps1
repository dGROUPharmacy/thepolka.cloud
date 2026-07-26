$ErrorActionPreference = "Stop"

try {

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms

# Prefer the modern Edge-powered WebView2 control bundled with Faire. The
# legacy WPF WebBrowser remains only as a compatibility fallback.
$script:webView2Available = $false
try {
    $faireLib = Join-Path $PSScriptRoot "lib"
    [void][System.Reflection.Assembly]::LoadFrom((Join-Path $faireLib "Microsoft.Web.WebView2.Core.dll"))
    [void][System.Reflection.Assembly]::LoadFrom((Join-Path $faireLib "Microsoft.Web.WebView2.Wpf.dll"))
    $script:webView2Available = $true
} catch {
    $script:webView2Available = $false
}

# The WPF WebBrowser control hosts the old Internet Explorer engine, and by
# default that engine renders every page in IE7 "quirks" mode for ANY
# process that isn't specifically registered otherwise - regardless of what
# IE version is actually installed. Modern sites come back blank/broken
# under that emulation. This registers the current host process (and the
# common ways this script gets launched) for real IE11 edge-mode rendering,
# which is required for embedded pages to load correctly. It only touches
# the current user's registry hive, and only adds an emulation entry - it
# does not change system-wide IE settings.
function Set-FaireBrowserEmulation {
    $exeNames = @(
        [System.IO.Path]::GetFileName([System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName),
        "powershell.exe",
        "powershell_ise.exe"
    ) | Select-Object -Unique
    $keyPath = "HKCU:\SOFTWARE\Microsoft\Internet Explorer\Main\FeatureControl\FEATURE_BROWSER_EMULATION"
    try {
        if (-not (Test-Path $keyPath)) {
            New-Item -Path $keyPath -Force | Out-Null
        }
        foreach ($exeName in $exeNames) {
            New-ItemProperty -Path $keyPath -Name $exeName -PropertyType DWord -Value 11001 -Force | Out-Null
        }
    } catch {
        # Non-fatal: worst case, embedded pages fall back to old rendering.
    }
}
Set-FaireBrowserEmulation

function Get-FaireLocalModelResponse {
    param([string]$Prompt)

    # Faire speaks to a model only on localhost. No API key, paid tokens, or
    # cloud account is required. If no local runtime is present, the built-in
    # deterministic Faire engine continues to work exactly as before.
    try {
        $models = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
        $modelName = if ($env:FAIRE_LOCAL_MODEL) {
            $env:FAIRE_LOCAL_MODEL
        } elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot "faire-model.txt")) {
            (Get-Content -LiteralPath (Join-Path $PSScriptRoot "faire-model.txt") -Raw).Trim()
        } elseif ($models.models.Count -gt 0) {
            [string]$models.models[0].name
        } else {
            return $null
        }
        $payload = @{
            model = $modelName
            stream = $false
            keep_alive = "30m"
            think = $false
            options = @{ num_predict = 220; temperature = 0.5 }
            messages = @(
                @{
                    role = "system"
                    content = "You are Faire, the private local intelligence inside FAIRE OS. Be concise, warm, capable, and honest. Never claim an action happened unless the host application confirms it. Prefer helping the user complete work without leaving the Faire canvas."
                },
                @{ role = "user"; content = "$Prompt`n/no_think" }
            )
        } | ConvertTo-Json -Depth 6
        $result = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/chat" -Method Post -ContentType "application/json" -Body $payload -TimeoutSec 90
        if ($result.message.content) {
            $script:lastLocalModel = $modelName
            return [string]$result.message.content
        }
    } catch {
        return $null
    }
    return $null
}

function Get-FaireLocalIntent {
    param([string]$Prompt)
    try {
        $models = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
        $modelName = if ($env:FAIRE_LOCAL_MODEL) { $env:FAIRE_LOCAL_MODEL }
            elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot "faire-model.txt")) { (Get-Content -LiteralPath (Join-Path $PSScriptRoot "faire-model.txt") -Raw).Trim() }
            elseif ($models.models.Count -gt 0) { [string]$models.models[0].name }
            else { return $null }
        $routerPrompt = @"
Convert the user's request into exactly one JSON object and no markdown.
Allowed actions:
chat, web_search, open_url, youtube_search, youtube_play, weather,
new_document, files, note, zoom, drive, create_project, backup_project.
Schema: {"action":"one action","argument":"short argument","reply":"short confirmation"}
Use chat when no computer action is appropriate.
User request: $Prompt
"@
        $payload = @{
            model = $modelName
            stream = $false
            keep_alive = "30m"
            think = $false
            format = "json"
            options = @{ num_predict = 80; temperature = 0.1 }
            messages = @(
                @{ role = "system"; content = "You route natural language into safe FAIRE OS actions. Return one valid JSON object only." },
                @{ role = "user"; content = "$routerPrompt`n/no_think" }
            )
        } | ConvertTo-Json -Depth 6
        $result = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/chat" -Method Post -ContentType "application/json" -Body $payload -TimeoutSec 45
        if ($result.message.content) {
            $script:lastLocalModel = $modelName
            return ([string]$result.message.content | ConvertFrom-Json)
        }
    } catch { return $null }
    return $null
}

function Get-FaireYouTubeVideoId {
    param([string]$Query)
    try {
        $uri = "https://www.youtube.com/results?search_query=" + [Uri]::EscapeDataString($Query)
        $headers = @{ "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36" }
        $html = (Invoke-WebRequest -UseBasicParsing -Uri $uri -Headers $headers -TimeoutSec 15).Content
        $match = [regex]::Match($html, '"videoId":"([a-zA-Z0-9_-]{11})"')
        if ($match.Success) { return $match.Groups[1].Value }
    } catch { }
    return $null
}

function Show-FaireVideoWidget {
    param([string]$Query, [string]$VideoId)

    if (-not $VideoId) {
        Show-FaireNote -Text "I could not resolve a playable YouTube video for `"$Query`" yet. Try a more specific title or artist." -Heading "VIDEO NOT FOUND"
        return $false
    }

    $card = New-Object System.Windows.Controls.Border
    $card.Width = [Math]::Min(720, [Math]::Max(500, $window.ActualWidth * 0.43))
    $card.Height = [Math]::Min(520, [Math]::Max(360, $window.ActualHeight * 0.52))
    $card.Background = "#F20A0910"
    $card.BorderBrush = "#CCFF8FD6"
    $card.BorderThickness = 1.5
    $card.CornerRadius = 14
    $card.Padding = 9
    $card.RenderTransform = New-Object System.Windows.Media.RotateTransform(0.45)

    $videoShadow = New-Object System.Windows.Media.Effects.DropShadowEffect
    $videoShadow.Color = [System.Windows.Media.Colors]::Black
    $videoShadow.BlurRadius = 42
    $videoShadow.ShadowDepth = 12
    $videoShadow.Opacity = 0.82
    $card.Effect = $videoShadow

    $layout = New-Object System.Windows.Controls.Grid
    $headRow = New-Object System.Windows.Controls.RowDefinition
    $headRow.Height = "48"
    $bodyRow = New-Object System.Windows.Controls.RowDefinition
    $bodyRow.Height = "*"
    [void]$layout.RowDefinitions.Add($headRow)
    [void]$layout.RowDefinitions.Add($bodyRow)

    $head = New-Object System.Windows.Controls.Grid
    $head.Background = "#FF111019"
    $label = New-Object System.Windows.Controls.TextBlock
    $label.Text = "FAIRE VIDEO  /  $Query"
    $label.Foreground = "#FFF8F1"
    $label.FontFamily = "Consolas"
    $label.FontWeight = "Bold"
    $label.FontSize = 12
    $label.Margin = "18,0,55,0"
    $label.VerticalAlignment = "Center"
    $head.Children.Add($label) | Out-Null
    $close = New-FaireCloseButton -Target $card
    $close.HorizontalAlignment = "Right"
    $close.Margin = "0,0,8,0"
    $head.Children.Add($close) | Out-Null
    [System.Windows.Controls.Grid]::SetRow($head, 0)
    $layout.Children.Add($head) | Out-Null

    if ($script:webView2Available) {
        $player = New-Object Microsoft.Web.WebView2.Wpf.WebView2
        $player.CreationProperties = New-Object Microsoft.Web.WebView2.Wpf.CoreWebView2CreationProperties
        $player.CreationProperties.UserDataFolder = Join-Path $env:LOCALAPPDATA "FaireOS\WebView2"
        $embedUrl = "https://www.youtube-nocookie.com/embed/$VideoId`?autoplay=1&playsinline=1&rel=0"
        $player.Add_Loaded({
            try { $player.Source = [Uri]$embedUrl } catch { }
        }.GetNewClosure())
    } else {
        $player = New-Object System.Windows.Controls.WebBrowser
        $embedUrl = "https://www.youtube-nocookie.com/embed/$VideoId`?autoplay=1&playsinline=1&rel=0"
        $player.Add_Loaded({
            try { $player.Navigate([Uri]$embedUrl) } catch { }
        }.GetNewClosure())
    }
    [System.Windows.Controls.Grid]::SetRow($player, 1)
    $layout.Children.Add($player) | Out-Null
    $card.Child = $layout
    $objectBoard.Children.Add($card) | Out-Null
    [System.Windows.Controls.Canvas]::SetLeft($card, [Math]::Max(30, $window.ActualWidth - $card.Width - 50))
    [System.Windows.Controls.Canvas]::SetTop($card, 62)
    [System.Windows.Controls.Canvas]::SetZIndex($card, 2600)
    Update-FaireLayout -SideWidth $card.Width
    return $true
}

function Get-FaireResponse {
    param([string]$Prompt)

    $text = $Prompt.Trim()
    $lower = $text.ToLowerInvariant()

    if ($lower -match '^(help|what can you do)\??$') {
        return @"
  Faire always runs without a cloud API or paid tokens.
  If a local model is installed, Faire uses it privately for smarter chat.

Try:
  build a browser
  show the globe in real satellite
  build a website called Aurora
  checklist: launch a small website
  plan: prepare a product demonstration
  summarize: paste text here
  clean: paste writing here
  risks: describe a project
  privacy: describe the information you collect
  note: something to remember during this session
"@
    }

    if ($lower.StartsWith("note:")) {
        $note = $text.Substring(5).Trim()
        if ($note) {
            [void]$script:notes.Add($note)
            $savedNote = Save-FaireArtifact -Category "Notes" -Name ("Note " + (Get-Date -Format "yyyy-MM-dd HHmmss")) -Content $note
            return "Pinned and filed locally. You now have $($script:notes.Count) note(s). Saved to $savedNote"
        }
        return "Add text after ``note:``."
    }

    if ($lower -match '^(notes|show notes)\??$') {
        if ($script:notes.Count -eq 0) { return "No session notes yet." }
        return (($script:notes | ForEach-Object { "- $_" }) -join "`r`n")
    }

    $knownCommandWords = "checklist|plan|summarize|clean|risks|privacy"
    if ($lower -match "^($knownCommandWords)\s*:?\s*(.*)$") {
        $command = $Matches[1]
        $body = $Matches[2].Trim()
    } else {
        $command = ""
        $body = $text
    }

    switch ($command) {
        "checklist" {
            return @"
Checklist: $body
- Define the result and the person responsible.
- Inventory files, access, dependencies, and constraints.
- Create the smallest working version.
- Test the primary path and one failure path.
- Record evidence: time, result, and relevant log.
- Back up the last working state.
- Publish or hand off with a rollback instruction.
"@
        }
        "plan" {
            return @"
Plan: $body
1. Outcome - write one measurable completion statement.
2. Inputs - list the files, people, systems, and permissions required.
3. Build - complete the smallest independently testable unit.
4. Verify - test behavior, accessibility, privacy, and recovery.
5. Release - preserve the working version, then publish.
6. Operate - schedule health checks and retain evidence.
"@
        }
        "summarize" {
            if (-not $body) { return "Paste text after ``summarize:``." }
            $sentences = [regex]::Split($body, '(?<=[.!?])\s+') | Where-Object { $_.Trim() }
            $selected = $sentences | Select-Object -First 3
            return "Concise extract:`r`n- " + (($selected | ForEach-Object { $_.Trim() }) -join "`r`n- ")
        }
        "clean" {
            if (-not $body) { return "Paste writing after ``clean:``." }
            $cleaned = [regex]::Replace($body, '\s+', ' ').Trim()
            $cleaned = [regex]::Replace($cleaned, '\s+([,.;:!?])', '$1')
            if ($cleaned.Length -gt 0) {
                $cleaned = $cleaned.Substring(0,1).ToUpperInvariant() + $cleaned.Substring(1)
            }
            return "Cleaned copy:`r`n$cleaned"
        }
        "risks" {
            return @"
Risk review: $body
- Dependency risk: identify anything that must be online or separately installed.
- Data risk: minimize collection and avoid storing secrets in logs.
- Access risk: use least privilege and test account recovery.
- Reliability risk: add a health check, timeout, and rollback path.
- Trust risk: distinguish verified operation from proposed capability.
- Maintenance risk: assign ownership and a recurring review date.
"@
        }
        "privacy" {
            return @"
Privacy starter for: $body
- Collect only information necessary for the stated service.
- State what is collected, why, where it is stored, and how long it is retained.
- Do not sell or disclose data without a clear legal basis and notice.
- Provide a method to request access, correction, or deletion.
- Protect stored information and document incident response.
- Obtain qualified legal review before treating this as a final policy.
"@
        }
    }

    return "Faire Standalone is ready. Use a command such as ``plan:``, ``checklist:``, ``summarize:``, ``clean:``, ``risks:``, ``privacy:``, or ``note:``. Type ``help`` for examples, or say ``build a browser`` / ``show the globe in real satellite`` / ``build a website called <name>``."
}

$script:faireWorkspace = Join-Path $PSScriptRoot "FaireWorkspace"

function Initialize-FaireFileSystem {
    foreach ($folder in @("Inbox","Projects","Documents","Notes","Research","Media","Code","Sessions","Exports","Backups")) {
        New-Item -ItemType Directory -Path (Join-Path $script:faireWorkspace $folder) -Force | Out-Null
    }
}

function Get-FaireSafeName {
    param([string]$Name)
    $safe = [regex]::Replace($Name, '[^a-zA-Z0-9 _-]', '').Trim()
    if (-not $safe) { $safe = "Untitled" }
    return $safe
}

function New-FaireProject {
    param([string]$Name)
    $safe = Get-FaireSafeName $Name
    $root = Join-Path (Join-Path $script:faireWorkspace "Projects") $safe
    foreach ($folder in @("Documents","Notes","Research","Media","Code","Exports","Backups")) {
        New-Item -ItemType Directory -Path (Join-Path $root $folder) -Force | Out-Null
    }
    $manifest = @{
        name = $safe
        created = (Get-Date).ToString("o")
        managedBy = "FAIRE OS"
    } | ConvertTo-Json
    Set-Content -LiteralPath (Join-Path $root "faire-project.json") -Value $manifest -Encoding UTF8
    $script:activeProject = $safe
    return $root
}

function Save-FaireArtifact {
    param([string]$Category, [string]$Name, [string]$Content)
    $safeCategory = if ($Category -in @("Documents","Notes","Research","Media","Code","Exports")) { $Category } else { "Inbox" }
    $base = if ($script:activeProject) {
        Join-Path (Join-Path (Join-Path $script:faireWorkspace "Projects") $script:activeProject) $safeCategory
    } else {
        Join-Path $script:faireWorkspace $safeCategory
    }
    New-Item -ItemType Directory -Path $base -Force | Out-Null
    $safeName = Get-FaireSafeName $Name
    $path = Join-Path $base ($safeName + ".txt")
    Set-Content -LiteralPath $path -Value $Content -Encoding UTF8
    return $path
}

function Backup-FaireProject {
    param([string]$Name)
    $safe = Get-FaireSafeName $(if ($Name) { $Name } else { $script:activeProject })
    $source = Join-Path (Join-Path $script:faireWorkspace "Projects") $safe
    if (-not (Test-Path -LiteralPath $source)) { return $null }
    $backupFolder = Join-Path $script:faireWorkspace "Backups"
    $destination = Join-Path $backupFolder ($safe + "-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".zip")
    Compress-Archive -LiteralPath $source -DestinationPath $destination -CompressionLevel Optimal
    return $destination
}

function Write-FaireSessionLog {
    param([string]$Prompt, [string]$Response)
    try {
        $path = Join-Path (Join-Path $script:faireWorkspace "Sessions") ((Get-Date -Format "yyyy-MM-dd") + ".log")
        Add-Content -LiteralPath $path -Value "[$(Get-Date -Format 'HH:mm:ss')] YOU: $Prompt`r`nFAIRE: $Response`r`n" -Encoding UTF8
    } catch { }
}

Initialize-FaireFileSystem
$script:notes = [System.Collections.ArrayList]::new()
$script:promptOpen = $false

# ---------------------------------------------------------------------------
# Window shell - true screensaver behavior: black canvas, nothing else, until
# the orb is clicked.
# ---------------------------------------------------------------------------
$window = New-Object System.Windows.Window
$window.Title = "Faire Screensaver OS"
$window.Width = 860
$window.Height = 680
$window.MinWidth = 620
$window.MinHeight = 480
$window.WindowStartupLocation = "CenterScreen"
$window.Background = "#000000"
if ($env:FAIRE_TEST_WINDOWED -eq "1") {
    $window.WindowStyle = "SingleBorderWindow"
    $window.WindowState = "Normal"
    $window.Width = 1280
    $window.Height = 800
    $window.ResizeMode = "CanResize"
} else {
    $window.WindowStyle = "None"
    $window.WindowState = "Maximized"
    $window.ResizeMode = "NoResize"
}

$grid = New-Object System.Windows.Controls.Grid

$ambient = New-Object System.Windows.Controls.Canvas
$ambient.Background = "#000000"
[System.Windows.Controls.Grid]::SetRowSpan($ambient, 4)
$grid.Children.Add($ambient) | Out-Null

$satellite = New-Object System.Windows.Controls.Image
$satellite.Stretch = "Uniform"
$satellite.Opacity = 0
$satellite.IsHitTestVisible = $false
[System.Windows.Controls.Grid]::SetRowSpan($satellite, 4)
$grid.Children.Add($satellite) | Out-Null

# In-ecosystem object board. Web pages, notes, and media controls live here
# instead of opening a second application over Faire.
$objectBoard = New-Object System.Windows.Controls.Canvas
$objectBoard.Background = $null
$objectBoard.IsHitTestVisible = $true
[System.Windows.Controls.Grid]::SetRowSpan($objectBoard, 4)
$grid.Children.Add($objectBoard) | Out-Null

# A single live web surface is displayed at a time. Its siblings remain
# available as Luxe tabs. This avoids native browser airspace conflicts while
# still letting Faire hold many independent browsing sessions.
$portalShelf = New-Object System.Windows.Controls.Border
$portalShelf.Background = "#E615111C"
$portalShelf.BorderBrush = "#668FD6FF"
$portalShelf.BorderThickness = 1
$portalShelf.CornerRadius = 18
$portalShelf.Padding = "8,5"
$portalShelf.Visibility = "Collapsed"
$portalShelfPanel = New-Object System.Windows.Controls.WrapPanel
$portalShelfPanel.Orientation = "Horizontal"
$portalShelf.Child = $portalShelfPanel
$objectBoard.Children.Add($portalShelf) | Out-Null
[System.Windows.Controls.Canvas]::SetLeft($portalShelf, 28)
[System.Windows.Controls.Canvas]::SetTop($portalShelf, 24)
[System.Windows.Controls.Canvas]::SetZIndex($portalShelf, 4000)
$script:webPortalEntries = [System.Collections.ArrayList]::new()

function Select-FairePortal {
    param($Entry)
    foreach ($item in @($script:webPortalEntries)) {
        $item.Portal.Visibility = "Collapsed"
        $item.Tab.Background = "#221F1726"
        $item.Tab.Foreground = "#B8AEC7"
    }
    if ($Entry) {
        $Entry.Portal.Visibility = "Visible"
        $Entry.Tab.Background = "#CCFF8FD6"
        $Entry.Tab.Foreground = "#170B22"
        [System.Windows.Controls.Canvas]::SetZIndex($Entry.Portal, 3000)
        $script:lastWebBrowser = $Entry.Browser
    }
}

function Update-FaireLayout {
    param([double]$SideWidth = 0)
    if ($SideWidth -gt 0 -and $window.ActualWidth -lt 1600) {
        $terminal.Width = [Math]::Max(540, $window.ActualWidth - $SideWidth - 120)
        $terminal.HorizontalAlignment = "Left"
        $terminal.Margin = "28,0,0,0"
    } else {
        $terminal.Width = 860
        $terminal.HorizontalAlignment = "Center"
        $terminal.Margin = 0
    }
}

function New-FaireCloseButton {
    param([System.Windows.UIElement]$Target)
    $button = New-Object System.Windows.Controls.Button
    $button.Content = [char]0x00D7
    $button.Width = 30
    $button.Height = 30
    $button.Padding = 0
    $button.Background = "#22FFFFFF"
    $button.Foreground = "#FFF8F1"
    $button.BorderThickness = 0
    $button.FontSize = 20
    $button.Cursor = [System.Windows.Input.Cursors]::Hand
    $button.Add_Click({
        $Target.Visibility = "Collapsed"
        Update-FaireLayout
        Open-FairePrompt
    }.GetNewClosure())
    return $button
}

function Show-FaireWebPortal {
    param([string]$Url, [string]$Title = "web")

    foreach ($existing in @($script:webPortalEntries)) {
        $existing.Portal.Visibility = "Collapsed"
        $existing.Tab.Background = "#221F1726"
        $existing.Tab.Foreground = "#B8AEC7"
    }

    $portal = New-Object System.Windows.Controls.Border
    $portal.Width = [Math]::Min(560, [Math]::Max(390, $window.ActualWidth * 0.30))
    $portal.Height = [Math]::Min(680, [Math]::Max(480, $window.ActualHeight * 0.64))
    $portal.MaxWidth = 560
    $portal.MaxHeight = 680
    $portalPaper = New-Object System.Windows.Media.LinearGradientBrush
    $portalPaper.StartPoint = "0,0"
    $portalPaper.EndPoint = "1,1"
    $portalPaper.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0xFF,0xFC,0xF5), 0))) | Out-Null
    $portalPaper.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0xE9,0xE0,0xD3), 1))) | Out-Null
    $portal.Background = $portalPaper
    $portalEdge = New-Object System.Windows.Media.LinearGradientBrush
    $portalEdge.StartPoint = "0,0"
    $portalEdge.EndPoint = "1,1"
    $portalEdge.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0xFF,0x8F,0xD6), 0))) | Out-Null
    $portalEdge.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0x8F,0xD6,0xFF), 1))) | Out-Null
    $portal.BorderBrush = $portalEdge
    $portal.BorderThickness = 1.5
    $portal.CornerRadius = 9
    $portal.Padding = 9
    $portal.RenderTransform = New-Object System.Windows.Media.RotateTransform(-0.35)
    $shadow = New-Object System.Windows.Media.Effects.DropShadowEffect
    $shadow.Color = [System.Windows.Media.Colors]::Black
    $shadow.BlurRadius = 42
    $shadow.ShadowDepth = 12
    $shadow.Opacity = 0.82
    $portal.Effect = $shadow

    $portalGrid = New-Object System.Windows.Controls.Grid
    $headRow = New-Object System.Windows.Controls.RowDefinition
    $headRow.Height = "48"
    $bodyRow = New-Object System.Windows.Controls.RowDefinition
    $bodyRow.Height = "*"
    [void]$portalGrid.RowDefinitions.Add($headRow)
    [void]$portalGrid.RowDefinitions.Add($bodyRow)

    $portalHead = New-Object System.Windows.Controls.Grid
    $portalHead.Background = "#F20B0A10"
    $portalHead.Margin = "0,0,0,7"
    $portalTitle = New-Object System.Windows.Controls.TextBlock
    $portalTitle.Text = "FAIRE PORTAL  /  $Title"
    $portalTitle.Foreground = "#FFF9F2"
    $portalTitle.FontFamily = "Consolas"
    $portalTitle.FontSize = 12
    $portalTitle.FontWeight = "Bold"
    $portalTitle.Margin = "20,0,55,0"
    $portalTitle.VerticalAlignment = "Center"
    $portalHead.Children.Add($portalTitle) | Out-Null
    $brassPin = New-Object System.Windows.Shapes.Ellipse
    $brassPin.Width = 16
    $brassPin.Height = 16
    $brassPin.HorizontalAlignment = "Center"
    $brassPin.VerticalAlignment = "Top"
    $brassPin.Margin = "0,-7,0,0"
    $brassPin.Fill = "#E9C66B"
    $brassPin.Stroke = "#FFF1B1"
    $brassPin.StrokeThickness = 1
    $pinShadow = New-Object System.Windows.Media.Effects.DropShadowEffect
    $pinShadow.Color = [System.Windows.Media.Colors]::Black
    $pinShadow.BlurRadius = 8
    $pinShadow.ShadowDepth = 3
    $brassPin.Effect = $pinShadow
    $portalHead.Children.Add($brassPin) | Out-Null
    $close = New-FaireCloseButton -Target $portal
    $close.HorizontalAlignment = "Right"
    $close.Margin = "0,0,9,0"
    $portalHead.Children.Add($close) | Out-Null
    [System.Windows.Controls.Grid]::SetRow($portalHead, 0)
    $portalGrid.Children.Add($portalHead) | Out-Null

    if ($script:webView2Available) {
        $browser = New-Object Microsoft.Web.WebView2.Wpf.WebView2
        $browser.CreationProperties = New-Object Microsoft.Web.WebView2.Wpf.CoreWebView2CreationProperties
        $browser.CreationProperties.UserDataFolder = Join-Path $env:LOCALAPPDATA "FaireOS\WebView2"
    } else {
        $browser = New-Object System.Windows.Controls.WebBrowser
        $silenceBrowser = {
            try {
                $flags = [System.Reflection.BindingFlags]::Instance -bor [System.Reflection.BindingFlags]::NonPublic
                $field = $browser.GetType().GetField("_axIWebBrowser2", $flags)
                if ($field) {
                    $activeBrowser = $field.GetValue($browser)
                    if ($activeBrowser) { $activeBrowser.Silent = $true }
                }
            } catch { }
        }.GetNewClosure()
        $browser.Add_Navigated($silenceBrowser)
        $browser.Add_LoadCompleted($silenceBrowser)
    }
    [System.Windows.Controls.Grid]::SetRow($browser, 1)
    $portalGrid.Children.Add($browser) | Out-Null
    $portal.Child = $portalGrid
    $objectBoard.Children.Add($portal) | Out-Null

    if (-not $script:webPortals) { $script:webPortals = [System.Collections.ArrayList]::new() }
    [void]$script:webPortals.Add($portal)
    $script:portalCount = if ($script:portalCount) { $script:portalCount + 1 } else { 1 }
    $stagger = (($script:portalCount - 1) % 6) * 26
    [System.Windows.Controls.Canvas]::SetLeft($portal, [Math]::Max(20, $window.ActualWidth - $portal.Width - 42 - $stagger))
    [System.Windows.Controls.Canvas]::SetTop($portal, 54 + $stagger)
    [System.Windows.Controls.Canvas]::SetZIndex($portal, 100 + $script:portalCount)

    if ($script:webView2Available) {
        $browser.Source = [Uri]$Url
    } else {
        $browser.Navigate([Uri]$Url)
    }
    $script:lastWebBrowser = $browser

    $tab = New-Object System.Windows.Controls.Button
    $tab.Content = if ($Title.Length -gt 22) { $Title.Substring(0,22) + [char]0x2026 } else { $Title }
    $tab.Padding = "13,6"
    $tab.Margin = "3,0"
    $tab.BorderThickness = 0
    $tab.Background = "#CCFF8FD6"
    $tab.Foreground = "#170B22"
    $tab.FontFamily = "Segoe UI Semibold"
    $tab.FontSize = 11
    $tab.Cursor = [System.Windows.Input.Cursors]::Hand
    $entry = [pscustomobject]@{ Portal=$portal; Browser=$browser; Tab=$tab; Title=$Title }
    [void]$script:webPortalEntries.Add($entry)
    $script:lastPortalEntry = $entry
    $portalShelfPanel.Children.Add($tab) | Out-Null
    $portalShelf.Visibility = "Visible"
    $tab.Add_Click({ Select-FairePortal -Entry $entry }.GetNewClosure())
    $close.Add_Click({
        [void]$objectBoard.Children.Remove($portal)
        [void]$portalShelfPanel.Children.Remove($tab)
        [void]$script:webPortalEntries.Remove($entry)
        if ($script:webPortalEntries.Count -gt 0) {
            Select-FairePortal -Entry $script:webPortalEntries[$script:webPortalEntries.Count - 1]
        } else {
            $portalShelf.Visibility = "Collapsed"
        }
    }.GetNewClosure())
    # The scrapbook clipping belongs in the surrounding black canvas. The
    # pink-and-blue Faire command panel remains exactly centered.
    Update-FaireLayout -SideWidth $portal.Width
    Open-FairePrompt
}

function Show-FaireNote {
    param([string]$Text, [string]$Heading = "NOTE")
    $paper = New-Object System.Windows.Controls.Border
    $paper.Width = 340
    $paper.MinHeight = 220
    $notePaper = New-Object System.Windows.Media.LinearGradientBrush
    $notePaper.StartPoint = "0,0"
    $notePaper.EndPoint = "1,1"
    $notePaper.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0xFF,0xF5,0xBC), 0))) | Out-Null
    $notePaper.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0xE8,0xD5,0x82), 1))) | Out-Null
    $paper.Background = $notePaper
    $paper.BorderBrush = "#E8C75F"
    $paper.BorderThickness = 1
    $paper.Padding = "28,34,28,26"
    $paper.RenderTransformOrigin = "0.5,0.5"
    $paper.RenderTransform = New-Object System.Windows.Media.RotateTransform(1.8)
    $paper.Cursor = [System.Windows.Input.Cursors]::Hand
    $shadow = New-Object System.Windows.Media.Effects.DropShadowEffect
    $shadow.Color = [System.Windows.Media.Colors]::Black
    $shadow.BlurRadius = 34
    $shadow.ShadowDepth = 11
    $shadow.Opacity = 0.72
    $paper.Effect = $shadow
    $stack = New-Object System.Windows.Controls.StackPanel
    $pin = New-Object System.Windows.Controls.TextBlock
    $pin.Text = [char]0x25CF
    $pin.Foreground = "#B71F45"
    $pin.FontSize = 25
    $pin.HorizontalAlignment = "Center"
    $pin.Margin = "0,-31,0,9"
    $stack.Children.Add($pin) | Out-Null
    $label = New-Object System.Windows.Controls.TextBlock
    $label.Text = $Heading
    $label.Foreground = "#665521"
    $label.FontFamily = "Consolas"
    $label.FontWeight = "Bold"
    $label.FontSize = 12
    $stack.Children.Add($label) | Out-Null
    $copy = New-Object System.Windows.Controls.TextBlock
    $copy.Text = $Text
    $copy.Foreground = "#272216"
    $copy.FontFamily = "Segoe Print"
    $copy.FontSize = 17
    $copy.TextWrapping = "Wrap"
    $copy.Margin = "0,12,0,0"
    $stack.Children.Add($copy) | Out-Null
    $paper.Child = $stack
    $paper.Add_MouseLeftButtonDown({
        $objectBoard.Children.Remove($paper)
        Open-FairePrompt
    }.GetNewClosure())
    $objectBoard.Children.Add($paper) | Out-Null
    $script:noteCount = if ($script:noteCount) { $script:noteCount + 1 } else { 1 }
    $noteStagger = (($script:noteCount - 1) % 5) * 30
    [System.Windows.Controls.Canvas]::SetLeft($paper, 44 + $noteStagger)
    [System.Windows.Controls.Canvas]::SetTop($paper, 60 + $noteStagger)
    $terminal.HorizontalAlignment = "Center"
    $terminal.Margin = 0
    Open-FairePrompt
}

function Show-FaireIdeaBoard {
    param([string]$Text, [string]$Heading = "FAIRE IDEAS")

    $pieces = @(
        $Text -split "(?:\r?\n)+|(?<=[.!?])\s+" |
        ForEach-Object { ($_ -replace '^\s*(?:[-*]|\d+[.)])\s*', '').Trim() } |
        Where-Object { $_ }
    )
    if ($pieces.Count -lt 2) {
        Show-FaireNote -Text $Text -Heading $Heading
        return
    }

    $colors = @("#FFFFB8DD", "#FFBDEEFF", "#FFFFE39A", "#FFC9F4D5")
    $angles = @(-2.0, 1.4, -0.7, 2.1)
    $startX = 36
    $startY = 64
    for ($i = 0; $i -lt [Math]::Min(4, $pieces.Count); $i++) {
        $idea = New-Object System.Windows.Controls.Border
        $idea.Width = 260
        $idea.MinHeight = 155
        $idea.Background = $colors[$i]
        $idea.BorderBrush = "#44FFFFFF"
        $idea.BorderThickness = 1
        $idea.Padding = "22,24,22,20"
        $idea.RenderTransform = New-Object System.Windows.Media.RotateTransform($angles[$i])
        $idea.Cursor = [System.Windows.Input.Cursors]::Hand
        $ideaShadow = New-Object System.Windows.Media.Effects.DropShadowEffect
        $ideaShadow.Color = [System.Windows.Media.Colors]::Black
        $ideaShadow.BlurRadius = 28
        $ideaShadow.ShadowDepth = 9
        $ideaShadow.Opacity = 0.68
        $idea.Effect = $ideaShadow

        $ideaStack = New-Object System.Windows.Controls.StackPanel
        $ideaLabel = New-Object System.Windows.Controls.TextBlock
        $ideaLabel.Text = if ($i -eq 0) { $Heading } else { "IDEA " + ($i + 1) }
        $ideaLabel.Foreground = "#6B3D68"
        $ideaLabel.FontFamily = "Consolas"
        $ideaLabel.FontWeight = "Bold"
        $ideaLabel.FontSize = 11
        $ideaStack.Children.Add($ideaLabel) | Out-Null
        $ideaText = New-Object System.Windows.Controls.TextBlock
        $ideaText.Text = $pieces[$i]
        $ideaText.Foreground = "#211B25"
        $ideaText.FontFamily = "Segoe Print"
        $ideaText.FontSize = 15
        $ideaText.TextWrapping = "Wrap"
        $ideaText.Margin = "0,10,0,0"
        $ideaStack.Children.Add($ideaText) | Out-Null
        $idea.Child = $ideaStack
        $idea.Add_MouseLeftButtonDown({
            [void]$objectBoard.Children.Remove($idea)
            $commandInput.Focus()
        }.GetNewClosure())
        $objectBoard.Children.Add($idea) | Out-Null
        [System.Windows.Controls.Canvas]::SetLeft($idea, $startX + (($i % 2) * 278))
        [System.Windows.Controls.Canvas]::SetTop($idea, $startY + ([Math]::Floor($i / 2) * 178))
        [System.Windows.Controls.Canvas]::SetZIndex($idea, 2300 + $i)
    }
    Open-FairePrompt
}

function Show-FaireSearchScrap {
    param([string]$Query)

    if ($script:searchScrap) {
        [void]$objectBoard.Children.Remove($script:searchScrap)
    }

    $scrap = New-Object System.Windows.Controls.Border
    $scrap.Width = 390
    $scrap.Height = 540
    $scrap.Background = "#EEE7D7"
    $scrap.BorderBrush = "#8E8069"
    $scrap.BorderThickness = 1
    $scrap.Padding = "22,18"
    $scrap.RenderTransformOrigin = "0.5,0.5"
    $scrap.RenderTransform = New-Object System.Windows.Media.RotateTransform(0.7)
    $scrap.Cursor = [System.Windows.Input.Cursors]::Arrow
    $scrapShadow = New-Object System.Windows.Media.Effects.DropShadowEffect
    $scrapShadow.Color = [System.Windows.Media.Colors]::Black
    $scrapShadow.BlurRadius = 28
    $scrapShadow.ShadowDepth = 9
    $scrapShadow.Opacity = 0.72
    $scrap.Effect = $scrapShadow

    $layout = New-Object System.Windows.Controls.Grid
    $topRow = New-Object System.Windows.Controls.RowDefinition
    $topRow.Height = "Auto"
    $resultsRow = New-Object System.Windows.Controls.RowDefinition
    $resultsRow.Height = "*"
    [void]$layout.RowDefinitions.Add($topRow)
    [void]$layout.RowDefinitions.Add($resultsRow)

    $top = New-Object System.Windows.Controls.Grid
    $heading = New-Object System.Windows.Controls.TextBlock
    $heading.Text = "SEARCH CLIPPING`r`n$Query"
    $heading.Foreground = "#29241D"
    $heading.FontFamily = "Consolas"
    $heading.FontWeight = "Bold"
    $heading.FontSize = 14
    $heading.Margin = "0,4,42,14"
    $heading.TextWrapping = "Wrap"
    $top.Children.Add($heading) | Out-Null
    $close = New-FaireCloseButton -Target $scrap
    $close.Background = "#3329241D"
    $close.Foreground = "#29241D"
    $close.HorizontalAlignment = "Right"
    $close.VerticalAlignment = "Top"
    $top.Children.Add($close) | Out-Null
    [System.Windows.Controls.Grid]::SetRow($top, 0)
    $layout.Children.Add($top) | Out-Null

    $resultStack = New-Object System.Windows.Controls.StackPanel
    try {
        # Bing's RSS endpoint returns plain XML. Rendering it as native WPF
        # text avoids the legacy browser and all webpage script-error dialogs.
        $feedUrl = "https://www.bing.com/search?format=rss&q=" + [Uri]::EscapeDataString($Query)
        [xml]$feed = (Invoke-WebRequest -UseBasicParsing -Uri $feedUrl -TimeoutSec 12).Content
        $items = @($feed.rss.channel.item | Select-Object -First 5)
        if ($items.Count -eq 0) { throw "No search results were returned." }
        foreach ($item in $items) {
            $resultTitle = New-Object System.Windows.Controls.TextBlock
            $resultTitle.Text = [string]$item.title
            $resultTitle.Foreground = "#392D72"
            $resultTitle.FontFamily = "Segoe UI Semibold"
            $resultTitle.FontSize = 14
            $resultTitle.TextWrapping = "Wrap"
            $resultStack.Children.Add($resultTitle) | Out-Null

            $description = [regex]::Replace([string]$item.description, '<[^>]+>', '')
            $resultCopy = New-Object System.Windows.Controls.TextBlock
            $resultCopy.Text = [System.Net.WebUtility]::HtmlDecode($description)
            $resultCopy.Foreground = "#3C3730"
            $resultCopy.FontFamily = "Segoe UI"
            $resultCopy.FontSize = 12
            $resultCopy.TextWrapping = "Wrap"
            $resultCopy.Margin = "0,3,0,14"
            $resultStack.Children.Add($resultCopy) | Out-Null
        }
    } catch {
        $failure = New-Object System.Windows.Controls.TextBlock
        $failure.Text = "The search clipping could not reach the web.`r`n`r`nCheck the Internet connection and try again."
        $failure.Foreground = "#5A332D"
        $failure.FontFamily = "Segoe UI"
        $failure.FontSize = 14
        $failure.TextWrapping = "Wrap"
        $failure.Margin = "0,14,0,0"
        $resultStack.Children.Add($failure) | Out-Null
    }

    $scroll = New-Object System.Windows.Controls.ScrollViewer
    $scroll.VerticalScrollBarVisibility = "Auto"
    $scroll.HorizontalScrollBarVisibility = "Disabled"
    $scroll.Content = $resultStack
    [System.Windows.Controls.Grid]::SetRow($scroll, 1)
    $layout.Children.Add($scroll) | Out-Null
    $scrap.Child = $layout
    $objectBoard.Children.Add($scrap) | Out-Null
    $script:searchScrap = $scrap
    [System.Windows.Controls.Canvas]::SetLeft($scrap, [Math]::Max(20, $window.ActualWidth - $scrap.Width - 42))
    [System.Windows.Controls.Canvas]::SetTop($scrap, [Math]::Max(60, $window.ActualHeight - $scrap.Height - 40))

    $terminal.HorizontalAlignment = "Center"
    $terminal.Margin = 0
    Open-FairePrompt
}

function Show-FaireMediaCard {
    param([string]$Label)
    if ($script:mediaCard) { $objectBoard.Children.Remove($script:mediaCard) }
    $card = New-Object System.Windows.Controls.Border
    $mediaPaper = New-Object System.Windows.Media.LinearGradientBrush
    $mediaPaper.StartPoint = "0,0"
    $mediaPaper.EndPoint = "1,0"
    $mediaPaper.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0xFF,0xD9,0x78), 0))) | Out-Null
    $mediaPaper.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0xF0,0xB8,0xD9), 1))) | Out-Null
    $card.Background = $mediaPaper
    $card.BorderBrush = "#FFE9A8"
    $card.BorderThickness = 1.4
    $card.CornerRadius = 7
    $card.Padding = "18,13"
    $card.RenderTransform = New-Object System.Windows.Media.RotateTransform(-1.5)
    $mediaShadow = New-Object System.Windows.Media.Effects.DropShadowEffect
    $mediaShadow.Color = [System.Windows.Media.Colors]::Black
    $mediaShadow.BlurRadius = 25
    $mediaShadow.ShadowDepth = 8
    $mediaShadow.Opacity = 0.68
    $card.Effect = $mediaShadow
    $row = New-Object System.Windows.Controls.StackPanel
    $row.Orientation = "Horizontal"
    $toggle = New-Object System.Windows.Controls.Button
    $toggle.Content = [char]0x23F8
    $toggle.Width = 42
    $toggle.Height = 42
    $toggle.Background = "#1B1B1B"
    $toggle.Foreground = "White"
    $toggle.BorderThickness = 0
    $toggle.FontSize = 19
    $toggle.ToolTip = "Play / pause"
    $toggle.Add_Click({
        if ($script:lastWebBrowser) {
            $script:lastWebBrowser.Focus() | Out-Null
            if ($script:webView2Available -and $script:lastWebBrowser.CoreWebView2) {
                [void]$script:lastWebBrowser.CoreWebView2.ExecuteScriptAsync(
                    "var v=document.querySelector('video'); if(v){if(v.paused){v.play();}else{v.pause();}}"
                )
            } else {
                [System.Windows.Forms.SendKeys]::SendWait(" ")
            }
        }
        if ($toggle.Content -eq [char]0x23F8) {
            $toggle.Content = [char]0x25B6
        } else {
            $toggle.Content = [char]0x23F8
        }
    }.GetNewClosure())
    $row.Children.Add($toggle) | Out-Null
    $caption = New-Object System.Windows.Controls.TextBlock
    $caption.Text = $Label
    $caption.Foreground = "#201B0E"
    $caption.FontFamily = "Segoe UI Semibold"
    $caption.FontSize = 14
    $caption.VerticalAlignment = "Center"
    $caption.Margin = "13,0,8,0"
    $row.Children.Add($caption) | Out-Null
    $card.Child = $row
    $objectBoard.Children.Add($card) | Out-Null
    $script:mediaCard = $card
    [System.Windows.Controls.Canvas]::SetLeft($card, 48)
    [System.Windows.Controls.Canvas]::SetTop($card, [Math]::Max(60, $window.ActualHeight - 125))
}

function Show-FaireWeatherWidget {
    param([string]$Location)

    try {
        $lookupName = if ($Location -eq "current location") { "Los Angeles" } else { $Location }
        $geoUri = "https://geocoding-api.open-meteo.com/v1/search?count=1&language=en&format=json&name=" + [Uri]::EscapeDataString($lookupName)
        $geo = Invoke-RestMethod -Uri $geoUri -TimeoutSec 12
        if (-not $geo.results -or $geo.results.Count -eq 0) { throw "Location not found." }
        $match = $geo.results[0]
        $forecastUri = "https://api.open-meteo.com/v1/forecast?latitude=$($match.latitude)&longitude=$($match.longitude)&current=temperature_2m,apparent_temperature,is_day,weather_code,wind_speed_10m,wind_direction_10m&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=auto"
        $forecast = Invoke-RestMethod -Uri $forecastUri -TimeoutSec 12
        $current = $forecast.current
        $place = if ($match.admin1) { "$($match.name), $($match.admin1)" } else { [string]$match.name }
        $code = [int]$current.weather_code
        $condition = switch ($code) {
            0 { "Clear" }
            1 { "Mostly clear" }
            2 { "Partly cloudy" }
            3 { "Overcast" }
            { $_ -in 45,48 } { "Fog" }
            { $_ -in 51,53,55,56,57 } { "Drizzle" }
            { $_ -in 61,63,65,66,67,80,81,82 } { "Rain" }
            { $_ -in 71,73,75,77,85,86 } { "Snow" }
            { $_ -in 95,96,99 } { "Thunderstorm" }
            default { "Current conditions" }
        }
        $icon = if ($code -in 95,96,99) { [char]0x26A1 }
            elseif ($code -in 71,73,75,77,85,86) { [char]0x2744 }
            elseif ($code -in 51,53,55,56,57,61,63,65,66,67,80,81,82) { [char]0x2614 }
            elseif ($code -in 2,3,45,48) { [char]0x2601 }
            elseif ([int]$current.is_day -eq 0) { [char]0x263E }
            else { [char]0x2600 }
        $tempF = [Math]::Round([double]$current.temperature_2m)
        $feelsF = [Math]::Round([double]$current.apparent_temperature)
        $windMph = [Math]::Round([double]$current.wind_speed_10m)
        $windDegrees = [double]$current.wind_direction_10m
        $directions = @("N","NE","E","SE","S","SW","W","NW")
        $windDirection = $directions[[int]([Math]::Round($windDegrees / 45) % 8)]

        $card = New-Object System.Windows.Controls.Border
        $card.Width = 330
        $card.Background = "#ED10121B"
        $weatherEdge = New-Object System.Windows.Media.LinearGradientBrush
        $weatherEdge.StartPoint = "0,0"
        $weatherEdge.EndPoint = "1,1"
        $weatherEdge.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0xFF,0xD7,0x72), 0))) | Out-Null
        $weatherEdge.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0x8F,0xD6,0xFF), 1))) | Out-Null
        $card.BorderBrush = $weatherEdge
        $card.BorderThickness = 1.4
        $card.CornerRadius = 22
        $card.Padding = "24,20"
        $card.RenderTransform = New-Object System.Windows.Media.RotateTransform(-0.8)
        $weatherShadow = New-Object System.Windows.Media.Effects.DropShadowEffect
        $weatherShadow.Color = [System.Windows.Media.Colors]::Black
        $weatherShadow.BlurRadius = 34
        $weatherShadow.ShadowDepth = 10
        $weatherShadow.Opacity = 0.74
        $card.Effect = $weatherShadow

        $stack = New-Object System.Windows.Controls.StackPanel
        $placeText = New-Object System.Windows.Controls.TextBlock
        $placeText.Text = $place.ToUpperInvariant()
        $placeText.Foreground = "#AFA8C2"
        $placeText.FontFamily = "Consolas"
        $placeText.FontSize = 12
        $stack.Children.Add($placeText) | Out-Null

        $hero = New-Object System.Windows.Controls.DockPanel
        $hero.Margin = "0,10,0,6"
        $weatherIcon = New-Object System.Windows.Controls.TextBlock
        $weatherIcon.Text = $icon
        $weatherIcon.FontFamily = "Segoe UI Symbol"
        $weatherIcon.FontSize = 62
        $weatherIcon.Foreground = "#FFD772"
        $weatherIcon.Margin = "0,0,22,0"
        [System.Windows.Controls.DockPanel]::SetDock($weatherIcon, "Left")
        $hero.Children.Add($weatherIcon) | Out-Null
        $temp = New-Object System.Windows.Controls.TextBlock
        $temp.Text = "$tempF$([char]0x00B0)F"
        $temp.Foreground = "White"
        $temp.FontFamily = "Segoe UI Light"
        $temp.FontSize = 52
        $temp.VerticalAlignment = "Center"
        $hero.Children.Add($temp) | Out-Null
        $stack.Children.Add($hero) | Out-Null

        $detail = New-Object System.Windows.Controls.TextBlock
        $detail.Text = "$condition`r`nWind $windDirection  $windMph mph  |  Feels like $feelsF$([char]0x00B0)F"
        $detail.Foreground = "#E9E3F2"
        $detail.FontFamily = "Segoe UI"
        $detail.FontSize = 14
        $detail.TextWrapping = "Wrap"
        $stack.Children.Add($detail) | Out-Null
        $hintText = New-Object System.Windows.Controls.TextBlock
        $hintText.Text = "click to dismiss"
        $hintText.Foreground = "#716A82"
        $hintText.FontSize = 10
        $hintText.Margin = "0,14,0,0"
        $stack.Children.Add($hintText) | Out-Null
        $card.Child = $stack
        $card.Add_MouseLeftButtonDown({
            [void]$objectBoard.Children.Remove($card)
            $commandInput.Focus()
        }.GetNewClosure())
        $objectBoard.Children.Add($card) | Out-Null
        [System.Windows.Controls.Canvas]::SetLeft($card, 48)
        [System.Windows.Controls.Canvas]::SetTop($card, [Math]::Max(70, $window.ActualHeight - 360))
        [System.Windows.Controls.Canvas]::SetZIndex($card, 2500)
        return "$condition, $tempF degrees Fahrenheit in $place. Wind $windDirection at $windMph miles per hour."
    } catch {
        $errorCard = New-Object System.Windows.Controls.Border
        $errorCard.Width = 330
        $errorCard.Background = "#ED10121B"
        $errorCard.BorderBrush = "#CC8FD6FF"
        $errorCard.BorderThickness = 1.4
        $errorCard.CornerRadius = 22
        $errorCard.Padding = "24,20"
        $errorStack = New-Object System.Windows.Controls.StackPanel
        $errorIcon = New-Object System.Windows.Controls.TextBlock
        $errorIcon.Text = [char]0x2601
        $errorIcon.FontFamily = "Segoe UI Symbol"
        $errorIcon.FontSize = 52
        $errorIcon.Foreground = "#8FD6FF"
        $errorStack.Children.Add($errorIcon) | Out-Null
        $errorTitle = New-Object System.Windows.Controls.TextBlock
        $errorTitle.Text = "WEATHER / $($Location.ToUpperInvariant())"
        $errorTitle.Foreground = "White"
        $errorTitle.FontFamily = "Consolas"
        $errorTitle.FontWeight = "Bold"
        $errorTitle.Margin = "0,8,0,8"
        $errorStack.Children.Add($errorTitle) | Out-Null
        $errorDetail = New-Object System.Windows.Controls.TextBlock
        $errorDetail.Text = "Live conditions are temporarily unavailable.`r`nThe weather card is ready to refresh."
        $errorDetail.Foreground = "#DCD6E8"
        $errorDetail.TextWrapping = "Wrap"
        $errorStack.Children.Add($errorDetail) | Out-Null
        $errorCard.Child = $errorStack
        $errorCard.Add_MouseLeftButtonDown({
            [void]$objectBoard.Children.Remove($errorCard)
            $commandInput.Focus()
        }.GetNewClosure())
        $objectBoard.Children.Add($errorCard) | Out-Null
        [System.Windows.Controls.Canvas]::SetLeft($errorCard, 48)
        [System.Windows.Controls.Canvas]::SetTop($errorCard, [Math]::Max(70, $window.ActualHeight - 330))
        [System.Windows.Controls.Canvas]::SetZIndex($errorCard, 2500)
        return "I made the weather card, but live conditions for $Location are temporarily unavailable."
    }
}

function Show-FaireDocumentEditor {
    param([string]$InitialText = "", [string]$DocumentName = "Untitled")

    $editorCard = New-Object System.Windows.Controls.Border
    $editorCard.Width = [Math]::Min(580, [Math]::Max(440, $window.ActualWidth * 0.34))
    $editorCard.Height = [Math]::Min(660, [Math]::Max(500, $window.ActualHeight * 0.68))
    $editorCard.Background = "#FFF9EE"
    $editorCard.BorderBrush = "#CCFF8FD6"
    $editorCard.BorderThickness = 1.5
    $editorCard.CornerRadius = 8
    $editorCard.Padding = "20"
    $editorCard.RenderTransform = New-Object System.Windows.Media.RotateTransform(0.4)

    $layout = New-Object System.Windows.Controls.Grid
    @("Auto","*","Auto") | ForEach-Object {
        $row = New-Object System.Windows.Controls.RowDefinition
        $row.Height = $_
        [void]$layout.RowDefinitions.Add($row)
    }
    $title = New-Object System.Windows.Controls.TextBlock
    $title.Text = "FAIRE DOCUMENT  /  $DocumentName"
    $title.Foreground = "#29222E"
    $title.FontFamily = "Consolas"
    $title.FontWeight = "Bold"
    $title.FontSize = 13
    $title.Margin = "0,0,0,14"
    $layout.Children.Add($title) | Out-Null

    $editor = New-Object System.Windows.Controls.TextBox
    $editor.Text = $InitialText
    $editor.AcceptsReturn = $true
    $editor.AcceptsTab = $true
    $editor.TextWrapping = "Wrap"
    $editor.VerticalScrollBarVisibility = "Auto"
    $editor.Background = "#00FFFFFF"
    $editor.Foreground = "#211B23"
    $editor.BorderThickness = 0
    $editor.FontFamily = "Segoe UI"
    $editor.FontSize = 16
    [System.Windows.Controls.Grid]::SetRow($editor, 1)
    $layout.Children.Add($editor) | Out-Null

    $actions = New-Object System.Windows.Controls.DockPanel
    $actions.Margin = "0,14,0,0"
    $save = New-Object System.Windows.Controls.Button
    $save.Content = "Save inside Faire"
    $save.Padding = "18,9"
    $save.Background = "#FF8FD6"
    $save.Foreground = "#170B22"
    $save.BorderThickness = 0
    $save.FontWeight = "Bold"
    $save.Add_Click({
        $safeDocName = if ($DocumentName -and $DocumentName -ne "Untitled") { $DocumentName } else { "Faire Document " + (Get-Date -Format "yyyy-MM-dd HHmm") }
        $docPath = Save-FaireArtifact -Category "Documents" -Name $safeDocName -Content $editor.Text
        $title.Text = "SAVED  /  $docPath"
    }.GetNewClosure())
    $actions.Children.Add($save) | Out-Null
    $closeEditor = New-Object System.Windows.Controls.Button
    $closeEditor.Content = "Done"
    $closeEditor.Padding = "18,9"
    $closeEditor.Margin = "8,0,0,0"
    $closeEditor.Background = "#22170B22"
    $closeEditor.Foreground = "#29222E"
    $closeEditor.BorderThickness = 0
    $closeEditor.Add_Click({
        [void]$objectBoard.Children.Remove($editorCard)
        $commandInput.Focus()
    }.GetNewClosure())
    $actions.Children.Add($closeEditor) | Out-Null
    [System.Windows.Controls.Grid]::SetRow($actions, 2)
    $layout.Children.Add($actions) | Out-Null
    $editorCard.Child = $layout
    $objectBoard.Children.Add($editorCard) | Out-Null
    [System.Windows.Controls.Canvas]::SetLeft($editorCard, [Math]::Max(28, $window.ActualWidth - $editorCard.Width - 46))
    [System.Windows.Controls.Canvas]::SetTop($editorCard, 70)
    [System.Windows.Controls.Canvas]::SetZIndex($editorCard, 2800)
    $editor.Focus()
}

function Show-FaireFileExplorer {
    $explorer = New-Object System.Windows.Controls.Border
    $explorer.Width = 430
    $explorer.Height = 560
    $explorer.Background = "#F7F0E5"
    $explorer.BorderBrush = "#AA8FD6FF"
    $explorer.BorderThickness = 1.4
    $explorer.CornerRadius = 10
    $explorer.Padding = "22"
    $explorer.RenderTransform = New-Object System.Windows.Media.RotateTransform(-0.5)
    $stack = New-Object System.Windows.Controls.StackPanel
    $heading = New-Object System.Windows.Controls.TextBlock
    $heading.Text = "FAIRE FILES"
    $heading.Foreground = "#28202C"
    $heading.FontFamily = "Consolas"
    $heading.FontWeight = "Bold"
    $heading.FontSize = 15
    $heading.Margin = "0,0,0,14"
    $stack.Children.Add($heading) | Out-Null

    $scroll = New-Object System.Windows.Controls.ScrollViewer
    $scroll.Height = 440
    $scroll.VerticalScrollBarVisibility = "Auto"
    $files = New-Object System.Windows.Controls.StackPanel
    $roots = @(
        [Environment]::GetFolderPath("MyDocuments"),
        (Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads"),
        (Join-Path $PSScriptRoot "FaireWorkspace")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    foreach ($root in $roots) {
        $rootLabel = New-Object System.Windows.Controls.TextBlock
        $rootLabel.Text = $root
        $rootLabel.Foreground = "#8A6480"
        $rootLabel.FontSize = 10
        $rootLabel.Margin = "0,10,0,5"
        $files.Children.Add($rootLabel) | Out-Null
        foreach ($file in @(Get-ChildItem -LiteralPath $root -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 8)) {
            $fileButton = New-Object System.Windows.Controls.Button
            $fileButton.Content = $file.Name
            $fileButton.HorizontalContentAlignment = "Left"
            $fileButton.Padding = "10,7"
            $fileButton.Margin = "0,2"
            $fileButton.Background = "#0FFFFFFF"
            $fileButton.Foreground = "#28202C"
            $fileButton.BorderThickness = 0
            $fileButton.Cursor = [System.Windows.Input.Cursors]::Hand
            $filePath = $file.FullName
            $fileBase = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
            $fileButton.Add_Click({
                $text = ""
                if ([System.IO.Path]::GetExtension($filePath) -match '^\.(txt|md|log|csv|json|ps1|html|css|js)$') {
                    $text = Get-Content -LiteralPath $filePath -Raw -ErrorAction SilentlyContinue
                } else {
                    $text = "This file is listed safely inside Faire.`r`n`r`n$filePath`r`n`r`nRich document preview support can be added without opening an external application."
                }
                Show-FaireDocumentEditor -InitialText $text -DocumentName $fileBase
            }.GetNewClosure())
            $files.Children.Add($fileButton) | Out-Null
        }
    }
    $scroll.Content = $files
    $stack.Children.Add($scroll) | Out-Null
    $dismiss = New-Object System.Windows.Controls.Button
    $dismiss.Content = "Close files"
    $dismiss.Padding = "12,8"
    $dismiss.Background = "#22170B22"
    $dismiss.Foreground = "#28202C"
    $dismiss.BorderThickness = 0
    $dismiss.Add_Click({ [void]$objectBoard.Children.Remove($explorer); $commandInput.Focus() }.GetNewClosure())
    $stack.Children.Add($dismiss) | Out-Null
    $explorer.Child = $stack
    $objectBoard.Children.Add($explorer) | Out-Null
    [System.Windows.Controls.Canvas]::SetLeft($explorer, 42)
    [System.Windows.Controls.Canvas]::SetTop($explorer, 70)
    [System.Windows.Controls.Canvas]::SetZIndex($explorer, 2800)
}

# --- The orb: the only thing visible on the idle screensaver canvas. ---
$halo = New-Object System.Windows.Shapes.Ellipse
$halo.Width = 520
$halo.Height = 520
$halo.Opacity = 0.18
$halo.Stroke = "#66BFF9F0"
$halo.StrokeThickness = 2
$halo.IsHitTestVisible = $false
$ambient.Children.Add($halo) | Out-Null

$orb = New-Object System.Windows.Shapes.Ellipse
$orb.Width = 420
$orb.Height = 420
$orb.Opacity = 0.60
$orbBrush = New-Object System.Windows.Media.RadialGradientBrush
$orbBrush.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0xC8,0xB8,0xFF), 0))) | Out-Null
$orbBrush.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0x7B,0x61,0xFF), 0.55))) | Out-Null
$orbBrush.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0x10,0x20,0x40), 0.85))) | Out-Null
$orbBrush.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0x00,0x00,0x00), 1))) | Out-Null
$orb.Fill = $orbBrush
$orb.Cursor = [System.Windows.Input.Cursors]::Hand
$orb.ToolTip = "Click to open Faire"
$ambient.Children.Add($orb) | Out-Null

$script:orbHover = $false
$orb.Add_MouseEnter({ $script:orbHover = $true })
$orb.Add_MouseLeave({ $script:orbHover = $false })

$spark = New-Object System.Windows.Shapes.Ellipse
$spark.Width = 13
$spark.Height = 13
$spark.Fill = "#FFFFFF"
$spark.Opacity = 0.86
$sparkGlow = New-Object System.Windows.Media.Effects.DropShadowEffect
$sparkGlow.Color = [System.Windows.Media.Color]::FromRgb(0xBF,0xF9,0xF0)
$sparkGlow.BlurRadius = 24
$sparkGlow.ShadowDepth = 0
$spark.Effect = $sparkGlow
$spark.IsHitTestVisible = $false
$ambient.Children.Add($spark) | Out-Null

# A quiet hint, the way an old screensaver shows a clock in the corner. It
# fades out once the prompt is open.
$hint = New-Object System.Windows.Controls.TextBlock
$hint.Text = "click the orb"
$hint.Foreground = "#4FBFF9F0"
$hint.FontFamily = "Consolas"
$hint.FontSize = 13
$hint.HorizontalAlignment = "Center"
$hint.VerticalAlignment = "Bottom"
$hint.Margin = "0,0,0,28"
$hint.IsHitTestVisible = $false
[System.Windows.Controls.Grid]::SetRowSpan($hint, 4)
$grid.Children.Add($hint) | Out-Null

# ---------------------------------------------------------------------------
# The "command prompt" - collapsed until the orb is clicked, then it opens
# like a terminal window centered over the black canvas.
# ---------------------------------------------------------------------------
$terminal = New-Object System.Windows.Controls.Border
$terminal.Width = 860
$terminal.Height = 600
$terminal.MaxWidth = 1300
$terminal.MaxHeight = 880
$terminal.HorizontalAlignment = "Center"
$terminal.VerticalAlignment = "Center"
$panelBg = New-Object System.Windows.Media.LinearGradientBrush
$panelBg.StartPoint = "0,0"
$panelBg.EndPoint = "1,1"
$panelBg.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromArgb(0xE3,0x22,0x14,0x2C), 0))) | Out-Null
$panelBg.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromArgb(0xE3,0x14,0x1C,0x30), 1))) | Out-Null
$terminal.Background = $panelBg
$panelBorder = New-Object System.Windows.Media.LinearGradientBrush
$panelBorder.StartPoint = "0,0"
$panelBorder.EndPoint = "1,0"
$panelBorder.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromArgb(0xAA,0xFF,0x8F,0xD6), 0))) | Out-Null
$panelBorder.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromArgb(0xAA,0x8F,0xD6,0xFF), 1))) | Out-Null
$terminal.BorderBrush = $panelBorder
$terminal.BorderThickness = 1.4
$terminal.CornerRadius = 26
$terminal.Padding = 4
$terminalGlow = New-Object System.Windows.Media.Effects.DropShadowEffect
$terminalGlow.Color = [System.Windows.Media.Color]::FromRgb(0xC7,0x9A,0xFF)
$terminalGlow.BlurRadius = 60
$terminalGlow.ShadowDepth = 0
$terminalGlow.Opacity = 0.45
$terminal.Effect = $terminalGlow
$terminal.Visibility = "Collapsed"
$terminal.RenderTransformOrigin = "0.5,0.5"
$script:terminalScale = New-Object System.Windows.Media.ScaleTransform(0.9, 0.9)
$terminal.RenderTransform = $script:terminalScale
$terminal.Opacity = 0
[System.Windows.Controls.Grid]::SetRowSpan($terminal, 4)
$grid.Children.Add($terminal) | Out-Null

$termGrid = New-Object System.Windows.Controls.Grid
$termGrid.Margin = 22
@("Auto", "*", "Auto", "Auto") | ForEach-Object {
    $row = New-Object System.Windows.Controls.RowDefinition
    $row.Height = $_
    [void]$termGrid.RowDefinitions.Add($row)
}
$terminal.Child = $termGrid

$header = New-Object System.Windows.Controls.DockPanel
$header.Margin = "4,0,4,14"
$headerDot = New-Object System.Windows.Shapes.Ellipse
$headerDot.Width = 11
$headerDot.Height = 11
$headerDotBrush = New-Object System.Windows.Media.LinearGradientBrush
$headerDotBrush.StartPoint = "0,0"
$headerDotBrush.EndPoint = "1,1"
$headerDotBrush.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0xFF,0x8F,0xD6), 0))) | Out-Null
$headerDotBrush.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0x8F,0xD6,0xFF), 1))) | Out-Null
$headerDot.Fill = $headerDotBrush
$headerDot.VerticalAlignment = "Center"
$headerDot.Margin = "0,0,10,0"
[System.Windows.Controls.DockPanel]::SetDock($headerDot, "Left")
$header.Children.Add($headerDot) | Out-Null
$headerText = New-Object System.Windows.Controls.TextBlock
$headerText.Text = "Faire"
$headerText.Foreground = "#F3EEFF"
$headerText.FontFamily = "Segoe UI Semibold"
$headerText.FontSize = 18
$headerText.VerticalAlignment = "Center"
$header.Children.Add($headerText) | Out-Null
$headerSub = New-Object System.Windows.Controls.TextBlock
$headerSub.Text = "ask me anything"
$headerSub.Foreground = "#8FD6FF"
$headerSub.FontFamily = "Segoe UI"
$headerSub.FontSize = 12
$headerSub.Margin = "10,3,0,0"
$headerSub.VerticalAlignment = "Center"
$header.Children.Add($headerSub) | Out-Null
[System.Windows.Controls.Grid]::SetRow($header, 0)
$termGrid.Children.Add($header) | Out-Null

$conversation = New-Object System.Windows.Controls.TextBox
$conversation.Margin = "4,0,4,14"
$conversation.Padding = 14
$conversation.Background = "Transparent"
$conversation.BorderThickness = 0
$conversation.Foreground = "#EDE9FF"
$conversation.FontFamily = "Segoe UI"
$conversation.FontSize = 14
$conversation.TextWrapping = "Wrap"
$conversation.VerticalScrollBarVisibility = "Auto"
$conversation.IsReadOnly = $true
$conversation.AcceptsReturn = $true
$conversation.Text = "Faire is ready.`r`nTry: build a browser`r`nTry: show the globe in real satellite`r`nTry: weather in <city>`r`nTry: google search for <anything>`r`nTry: show me the <site> homepage`r`nTry: build a website called Aurora`r`nTry: help`r`n`r`n"
[System.Windows.Controls.Grid]::SetRow($conversation, 1)
$termGrid.Children.Add($conversation) | Out-Null

$inputPill = New-Object System.Windows.Controls.Border
$inputPill.Margin = "4,0,4,14"
$inputPill.CornerRadius = 22
$inputPillBg = New-Object System.Windows.Media.LinearGradientBrush
$inputPillBg.StartPoint = "0,0"
$inputPillBg.EndPoint = "1,0"
$inputPillBg.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromArgb(0x66,0xFF,0x8F,0xD6), 0))) | Out-Null
$inputPillBg.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromArgb(0x66,0x8F,0xD6,0xFF), 1))) | Out-Null
$inputPill.BorderBrush = $inputPillBg
$inputPill.BorderThickness = 1.2
$inputPill.Background = "#3D0E0E18"
$inputRow = New-Object System.Windows.Controls.DockPanel
$inputRow.Margin = "18,4,8,4"
$prompt = New-Object System.Windows.Controls.TextBlock
$prompt.Text = ">"
$prompt.Foreground = "#FF8FD6"
$prompt.FontFamily = "Segoe UI Semibold"
$prompt.VerticalAlignment = "Center"
$prompt.Margin = "0,0,10,0"
[System.Windows.Controls.DockPanel]::SetDock($prompt, "Left")
$inputRow.Children.Add($prompt) | Out-Null

$commandInput = New-Object System.Windows.Controls.TextBox
$commandInput.Padding = "4,10"
$commandInput.MinHeight = 40
$commandInput.AcceptsReturn = $false
$commandInput.TextWrapping = "NoWrap"
$commandInput.Background = "Transparent"
$commandInput.Foreground = "White"
$commandInput.CaretBrush = "#FF8FD6"
$commandInput.BorderThickness = 0
$commandInput.FontFamily = "Segoe UI"
$commandInput.FontSize = 14
$commandInput.VerticalContentAlignment = "Center"
$inputRow.Children.Add($commandInput) | Out-Null
$inputPill.Child = $inputRow
[System.Windows.Controls.Grid]::SetRow($inputPill, 2)
$termGrid.Children.Add($inputPill) | Out-Null

$bar = New-Object System.Windows.Controls.DockPanel
$bar.Margin = "4,0,4,0"
$status = New-Object System.Windows.Controls.TextBlock
$status.Text = "Esc closes  ·  F11 full-screen"
$status.Foreground = "#8A7FA8"
$status.FontFamily = "Segoe UI"
$status.FontSize = 11
$status.VerticalAlignment = "Center"
[System.Windows.Controls.DockPanel]::SetDock($status, "Left")
$bar.Children.Add($status) | Out-Null

$send = New-Object System.Windows.Controls.Border
$send.CornerRadius = 18
$send.Padding = "22,10"
$send.Cursor = [System.Windows.Input.Cursors]::Hand
$sendBg = New-Object System.Windows.Media.LinearGradientBrush
$sendBg.StartPoint = "0,0"
$sendBg.EndPoint = "1,0"
$sendBg.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0xFF,0x8F,0xD6), 0))) | Out-Null
$sendBg.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromRgb(0x8F,0xD6,0xFF), 1))) | Out-Null
$send.Background = $sendBg
$sendLabel = New-Object System.Windows.Controls.TextBlock
$sendLabel.Text = "Send"
$sendLabel.Foreground = "#170B22"
$sendLabel.FontFamily = "Segoe UI Semibold"
$sendLabel.FontSize = 13
$send.Child = $sendLabel
$send.HorizontalAlignment = "Right"
[System.Windows.Controls.DockPanel]::SetDock($send, "Right")
$bar.Children.Add($send) | Out-Null
[System.Windows.Controls.Grid]::SetRow($bar, 3)
$termGrid.Children.Add($bar) | Out-Null

# ---------------------------------------------------------------------------
# Behavior
# ---------------------------------------------------------------------------
function Open-FairePrompt {
    $script:promptOpen = $true
    $terminal.Visibility = "Visible"
    $hint.Visibility = "Collapsed"
    if ($script:chatTabLabel) { $script:chatTabLabel.Text = "Hide chat" }

    $fadeIn = New-Object System.Windows.Media.Animation.DoubleAnimation
    $fadeIn.From = 0.0
    $fadeIn.To = 1.0
    $fadeIn.Duration = New-Object System.Windows.Duration([TimeSpan]::FromMilliseconds(220))
    $terminal.BeginAnimation([System.Windows.UIElement]::OpacityProperty, $fadeIn)

    $scaleIn = New-Object System.Windows.Media.Animation.DoubleAnimation
    $scaleIn.From = 0.9
    $scaleIn.To = 1.0
    $scaleIn.Duration = New-Object System.Windows.Duration([TimeSpan]::FromMilliseconds(260))
    $scaleEase = New-Object System.Windows.Media.Animation.BackEase
    $scaleEase.EasingMode = "EaseOut"
    $scaleEase.Amplitude = 0.35
    $scaleIn.EasingFunction = $scaleEase
    $script:terminalScale.BeginAnimation([System.Windows.Media.ScaleTransform]::ScaleXProperty, $scaleIn)
    $script:terminalScale.BeginAnimation([System.Windows.Media.ScaleTransform]::ScaleYProperty, $scaleIn)

    $commandInput.Focus()
}

function Close-FairePrompt {
    $script:promptOpen = $false
    $hint.Visibility = "Visible"
    if ($script:chatTabLabel) { $script:chatTabLabel.Text = "Faire chat" }

    $fadeOut = New-Object System.Windows.Media.Animation.DoubleAnimation
    $fadeOut.From = 1.0
    $fadeOut.To = 0.0
    $fadeOut.Duration = New-Object System.Windows.Duration([TimeSpan]::FromMilliseconds(160))
    $fadeOut.Add_Completed({ $terminal.Visibility = "Collapsed" })
    $terminal.BeginAnimation([System.Windows.UIElement]::OpacityProperty, $fadeOut)
}

$orb.Add_MouseLeftButtonDown({
    if ($script:promptOpen) { Close-FairePrompt } else { Open-FairePrompt }
})

$send.Add_MouseLeftButtonDown({
    & $runCommand
})

$runCommand = {
    try {
    $commandText = $commandInput.Text.Trim()
    if (-not $commandText) { return }
    $commandInput.Clear()
    $conversation.AppendText("YOU`r`n$commandText`r`n`r`n")
    $lowerPrompt = $commandText.ToLowerInvariant()
    if ($lowerPrompt -match '^(create|start|make)( a)?( new)? project( called| named)?\s+(.+)$') {
        $projectName = $Matches[5].Trim()
        $projectPath = New-FaireProject -Name $projectName
        $answer = "Created and activated project $projectName. Faire will now file documents, notes, research, media, code, exports, and backups under $projectPath"
        Show-FaireNote -Text $answer -Heading "PROJECT CREATED"
    } elseif ($lowerPrompt -match '^(back up|backup)( my| the)?( project)?\s*(.*)$') {
        $backupName = $Matches[4].Trim()
        $backupPath = Backup-FaireProject -Name $backupName
        $answer = if ($backupPath) { "Backup complete: $backupPath" } else { "I couldn't find that project to back up. Say `"create project called <name>`" first." }
        Show-FaireNote -Text $answer -Heading "FAIRE BACKUP"
    } elseif ($lowerPrompt -match '^(open |show )?(file explorer|files)$|^find (a )?file') {
        Show-FaireFileExplorer
        $answer = "Your files are arranged inside Faire."
    } elseif ($lowerPrompt -match '^(new|create|open|write)( a)? (word )?document|^start writing') {
        $documentName = if ($lowerPrompt -match '(called|named)\s+(.+)$') { $Matches[2].Trim() } else { "Untitled" }
        Show-FaireDocumentEditor -DocumentName $documentName
        $answer = "A new Faire document is ready."
    } elseif ($lowerPrompt -match 'zoom( meeting| call)?|open zoom') {
        Show-FaireWebPortal -Url "https://app.zoom.us/wc" -Title "Zoom"
        $answer = "Zoom is ready in a Faire portal. Camera and microphone access remain under your control."
    } elseif ($lowerPrompt -match 'google drive|open drive|drive document') {
        Show-FaireWebPortal -Url "https://drive.google.com" -Title "Google Drive"
        $answer = "Google Drive is ready in a Faire portal."
    } elseif ($lowerPrompt -match 'build (a )?browser|open (a )?browser') {
        Show-FaireWebPortal -Url "https://thepolka.cloud/" -Title "browser"
        $answer = "The browser is pinned to Faire's canvas. Close it with the × on the card."
    } elseif ($lowerPrompt -match 'show (me )?(the )?globe|real satellite|satellite globe') {
        try {
            $imageUri = New-Object System.Uri("https://cdn.star.nesdis.noaa.gov/GOES19/ABI/FD/GEOCOLOR/1808x1808.jpg")
            $bitmap = New-Object System.Windows.Media.Imaging.BitmapImage
            $bitmap.BeginInit()
            $bitmap.CacheOption = "OnLoad"
            $bitmap.UriSource = $imageUri
            $bitmap.EndInit()
            $satellite.Source = $bitmap
            $satellite.Opacity = 0.82
            $terminal.Opacity = 0.9
            $answer = "Live NOAA GOES-19 GeoColor is illuminating the canvas. Say ``clear canvas`` to return to black."
        } catch {
            Show-FaireWebPortal -Url "https://www.star.nesdis.noaa.gov/GOES/fulldisk_band.php?band=GEOCOLOR&length=24&sat=G16" -Title "NOAA satellite"
            $answer = "The NOAA source is showing in a Faire portal because the canvas image could not load."
        }
    } elseif ($lowerPrompt -match '^clear canvas$|^go dark$') {
        $satellite.Source = $null
        $satellite.Opacity = 0
        $terminal.Opacity = 1
        $answer = "Canvas cleared."
    } elseif ($lowerPrompt -match 'build (a )?website( called| named)?\s*(.*)$') {
        $siteName = if ($Matches[3]) { $Matches[3].Trim() } else { "Faire Site" }
        $safeName = [regex]::Replace($siteName, '[^a-zA-Z0-9_-]', '-').Trim('-')
        if (-not $safeName) { $safeName = "faire-site" }
        $workspace = Join-Path $PSScriptRoot "FaireWorkspace"
        $siteFolder = Join-Path $workspace $safeName
        New-Item -ItemType Directory -Path $siteFolder -Force | Out-Null
        $html = @"
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>$siteName</title><style>body{margin:0;background:#050505;color:#fff;font-family:system-ui;display:grid;place-items:center;min-height:100vh}main{text-align:center}h1{font-size:clamp(3rem,10vw,8rem);margin:0;background:linear-gradient(90deg,#bff9f0,#7b61ff);-webkit-background-clip:text;color:transparent}p{color:#aaa}</style></head>
<body><main><h1>$siteName</h1><p>Built locally in Faire Screensaver OS.</p></main></body></html>
"@
        Set-Content -LiteralPath (Join-Path $siteFolder "index.html") -Value $html -Encoding UTF8
        Show-FaireWebPortal -Url ([Uri](Join-Path $siteFolder "index.html")).AbsoluteUri -Title $siteName
        $answer = "Built $siteName and pinned it to the Faire canvas. Files: $siteFolder"
    } elseif ($lowerPrompt -match '^find( me)?( some)?( youtube)? videos?\s+(about|for|of)\s+(.+)$') {
        $videoQuery = $Matches[5].Trim()
        $videoId = Get-FaireYouTubeVideoId -Query $videoQuery
        $shown = Show-FaireVideoWidget -Query $videoQuery -VideoId $videoId
        $answer = if ($shown) { "I found a video about $videoQuery and opened it in a dedicated Faire player." } else { "I couldn't resolve a playable video about $videoQuery yet." }
    } elseif ($lowerPrompt -match '^(find|show|play)\s+(.+?)\s+on\s+youtube$') {
        $videoQuery = $Matches[2].Trim()
        $videoId = Get-FaireYouTubeVideoId -Query $videoQuery
        $shown = Show-FaireVideoWidget -Query $videoQuery -VideoId $videoId
        $answer = if ($shown) { "Playing $videoQuery in a dedicated Faire video card." } else { "I couldn't resolve a playable YouTube video for $videoQuery yet." }
    } elseif ($lowerPrompt -match '^(play|listen to)\s+(.+)$') {
        $track = $Matches[2].Trim()
        $trackId = Get-FaireYouTubeVideoId -Query $track
        $shown = Show-FaireVideoWidget -Query $track -VideoId $trackId
        if ($shown) { Show-FaireMediaCard -Label $track }
        $answer = if ($shown) { "Music is contained in Faire. The small sticky control keeps play/pause at hand." } else { "I couldn't resolve that track yet." }
    } elseif ($lowerPrompt -match '^(?:(?:what(?:''s| is)|check|show me|get)\s+)?(?:the\s+)?(?:weather|forecast)(?:\s+(?:in|for|at))?\s*(?<location>.*?)\s*\??$') {
        $location = $Matches['location'].Trim()
        if (-not $location) { $location = "current location" }
        $answer = Show-FaireWeatherWidget -Location $location
    } elseif ($lowerPrompt -match '^(google search( results)? for|search google for|search for)\s+(.+)$') {
        $query = $Matches[3].Trim()
        $searchUrl = "https://lite.duckduckgo.com/lite/?q=" + [Uri]::EscapeDataString($query)
        Show-FaireWebPortal -Url $searchUrl -Title "search / $query"
        $answer = "Search results for `"$query`" are pinned inside Faire."
    } elseif ($lowerPrompt -match '^(show me|open|go to|pull up)\s+(the\s+)?(.+?)\s*(homepage|website|site|page)?$') {
        $target = $Matches[3].Trim()
        $knownSites = @{
            facebook  = "https://www.facebook.com"
            google    = "https://www.google.com"
            amazon    = "https://www.amazon.com"
            youtube   = "https://www.youtube.com"
            wikipedia = "https://www.wikipedia.org"
            linkedin  = "https://www.linkedin.com"
            instagram = "https://www.instagram.com"
            twitter   = "https://x.com"
            x         = "https://x.com"
            reddit    = "https://www.reddit.com"
            googledrive = "https://drive.google.com"
            zoom      = "https://app.zoom.us/wc"
        }
        $key = ($target -replace '[^a-z0-9]', '')
        if ($knownSites.ContainsKey($key)) {
            Show-FaireWebPortal -Url $knownSites[$key] -Title $target
            $answer = "Opened $target inside Faire."
        } elseif ($target -match '\.[a-z]{2,}(/.*)?$') {
            $siteUrl = if ($target -match '^https?://') { $target } else { "https://$target" }
            Show-FaireWebPortal -Url $siteUrl -Title $target
            $answer = "Opened $target inside Faire."
        } else {
            $searchUrl = "https://lite.duckduckgo.com/lite/?q=" + [Uri]::EscapeDataString($target)
            Show-FaireWebPortal -Url $searchUrl -Title "search / $target"
            $answer = "I didn't recognize `"$target`" as a site, so its search results are pinned inside Faire."
        }
    } else {
        $headerSub.Text = "thinking locally..."
        [System.Windows.Forms.Application]::DoEvents()
        $intent = Get-FaireLocalIntent -Prompt $commandText
        $intentHandled = $false
        if ($intent -and $intent.action -and $intent.action -ne "chat") {
            $argument = [string]$intent.argument
            switch ([string]$intent.action) {
                "web_search" {
                    Show-FaireWebPortal -Url ("https://lite.duckduckgo.com/lite/?q=" + [Uri]::EscapeDataString($argument)) -Title "search / $argument"
                    $intentHandled = $true
                }
                "open_url" {
                    $url = if ($argument -match '^https?://') { $argument } elseif ($argument -match '\.') { "https://$argument" } else { "https://lite.duckduckgo.com/lite/?q=" + [Uri]::EscapeDataString($argument) }
                    Show-FaireWebPortal -Url $url -Title $argument
                    $intentHandled = $true
                }
                "youtube_search" {
                    $id = Get-FaireYouTubeVideoId -Query $argument
                    [void](Show-FaireVideoWidget -Query $argument -VideoId $id)
                    $intentHandled = $true
                }
                "youtube_play" {
                    $id = Get-FaireYouTubeVideoId -Query $argument
                    [void](Show-FaireVideoWidget -Query $argument -VideoId $id)
                    $intentHandled = $true
                }
                "weather" {
                    $answer = Show-FaireWeatherWidget -Location $argument
                    $intentHandled = $true
                }
                "new_document" {
                    Show-FaireDocumentEditor -DocumentName $(if ($argument) { $argument } else { "Untitled" })
                    $intentHandled = $true
                }
                "files" {
                    Show-FaireFileExplorer
                    $intentHandled = $true
                }
                "note" {
                    [void]$script:notes.Add($argument)
                    [void](Save-FaireArtifact -Category "Notes" -Name ("Note " + (Get-Date -Format "yyyy-MM-dd HHmmss")) -Content $argument)
                    Show-FaireNote -Text $argument -Heading "PINNED NOTE"
                    $intentHandled = $true
                }
                "zoom" {
                    Show-FaireWebPortal -Url "https://app.zoom.us/wc" -Title "Zoom"
                    $intentHandled = $true
                }
                "drive" {
                    Show-FaireWebPortal -Url "https://drive.google.com" -Title "Google Drive"
                    $intentHandled = $true
                }
                "create_project" {
                    $path = New-FaireProject -Name $argument
                    Show-FaireNote -Text "Active project: $argument`r`n$path" -Heading "PROJECT CREATED"
                    $intentHandled = $true
                }
                "backup_project" {
                    $path = Backup-FaireProject -Name $argument
                    Show-FaireNote -Text $(if ($path) { "Backup complete:`r`n$path" } else { "Project not found." }) -Heading "FAIRE BACKUP"
                    $intentHandled = $true
                }
            }
            if ($intentHandled -and -not $answer) {
                $answer = if ($intent.reply) { [string]$intent.reply } else { "Done inside Faire." }
            }
        }
        if (-not $intentHandled) {
            $answer = Get-FaireLocalModelResponse -Prompt $commandText
            if (-not $answer) { $answer = Get-FaireResponse -Prompt $commandText }
        }
        if (-not $intentHandled -and $lowerPrompt.StartsWith("note:") -and $commandText.Substring(5).Trim()) {
            Show-FaireNote -Text $commandText.Substring(5).Trim() -Heading "PINNED NOTE"
        } elseif (-not $intentHandled -and $lowerPrompt -match '^(notes|show notes)\??$' -and $script:notes.Count -gt 0) {
            Show-FaireNote -Text (($script:notes | ForEach-Object { ([char]0x2022) + " " + $_ }) -join "`r`n") -Heading "SESSION NOTES"
        } elseif (-not $intentHandled) {
            $cardHeading = if ($commandText.Length -gt 28) { $commandText.Substring(0,28).Trim() + "..." } else { $commandText }
            if ($lowerPrompt -match '\b(ideas?|brainstorm|options?|concepts?|ways to)\b') {
                Show-FaireIdeaBoard -Text $answer -Heading ("FAIRE / " + $cardHeading.ToUpperInvariant())
            } else {
                Show-FaireNote -Text $answer -Heading ("FAIRE / " + $cardHeading.ToUpperInvariant())
            }
        }
        $headerSub.Text = if ($script:lastLocalModel) { "private local model / $($script:lastLocalModel)" } else { "ask me anything" }
    }
    Write-FaireSessionLog -Prompt $commandText -Response $answer
    $conversation.AppendText("FAIRE`r`n$answer`r`n`r`n")
    $conversation.ScrollToEnd()
    $commandInput.Focus()
    } catch {
        $failureText = "That request hit a Faire component error, but the OS stayed open. " + $_.Exception.Message
        try {
            Write-FaireSessionLog -Prompt $commandText -Response $failureText
            $conversation.AppendText("FAIRE`r`n$failureText`r`n`r`n")
            $conversation.ScrollToEnd()
            Show-FaireNote -Text $failureText -Heading "FAIRE RECOVERED"
            $headerSub.Text = "ready after recovery"
            $commandInput.Focus()
        } catch { }
    }
}

$commandInput.Add_KeyDown({
    if ($_.Key -eq "Return" -and -not [System.Windows.Input.Keyboard]::Modifiers.HasFlag([System.Windows.Input.ModifierKeys]::Shift)) {
        $_.Handled = $true
        & $runCommand
    }
})

# ---------------------------------------------------------------------------
# Persistent chat access - added last so it always renders above every other
# card/portal/note, regardless of what else is open or where the orb has
# drifted to. This is the guaranteed way back to chat; the orb still works
# too when it's reachable, but this never gets buried.
# ---------------------------------------------------------------------------
$chatTab = New-Object System.Windows.Controls.Border
$chatTab.CornerRadius = 20
$chatTab.Padding = "18,10"
$chatTab.HorizontalAlignment = "Center"
$chatTab.VerticalAlignment = "Bottom"
$chatTab.Margin = "0,0,0,20"
$chatTab.Cursor = [System.Windows.Input.Cursors]::Hand
$chatTabBg = New-Object System.Windows.Media.LinearGradientBrush
$chatTabBg.StartPoint = "0,0"
$chatTabBg.EndPoint = "1,0"
$chatTabBg.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromArgb(0xE6,0xFF,0x8F,0xD6), 0))) | Out-Null
$chatTabBg.GradientStops.Add((New-Object System.Windows.Media.GradientStop([System.Windows.Media.Color]::FromArgb(0xE6,0x8F,0xD6,0xFF), 1))) | Out-Null
$chatTab.Background = $chatTabBg
$chatTabGlow = New-Object System.Windows.Media.Effects.DropShadowEffect
$chatTabGlow.Color = [System.Windows.Media.Color]::FromRgb(0xC7,0x9A,0xFF)
$chatTabGlow.BlurRadius = 26
$chatTabGlow.ShadowDepth = 0
$chatTabGlow.Opacity = 0.6
$chatTab.Effect = $chatTabGlow
$chatTabLabel = New-Object System.Windows.Controls.TextBlock
$chatTabLabel.Text = "Faire chat"
$chatTabLabel.Foreground = "#170B22"
$chatTabLabel.FontFamily = "Segoe UI Semibold"
$chatTabLabel.FontSize = 13
$chatTab.Child = $chatTabLabel
$script:chatTabLabel = $chatTabLabel
$chatTab.Add_MouseLeftButtonDown({
    if ($script:promptOpen) { Close-FairePrompt } else { Open-FairePrompt }
})
$grid.Children.Add($chatTab) | Out-Null

$window.Content = $grid
$window.Add_KeyDown({
    if ($_.Key -eq "Escape") {
        if ($script:promptOpen) { Close-FairePrompt } else { $window.Close() }
    }
    if ($_.Key -eq "F11") {
        if ($window.WindowState -eq "Maximized") {
            $window.WindowStyle = "SingleBorderWindow"
            $window.WindowState = "Normal"
        } else {
            $window.WindowStyle = "None"
            $window.WindowState = "Maximized"
        }
    }
})

$angle = 0.0
$timer = New-Object System.Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromMilliseconds(40)
$timer.Add_Tick({
    if (-not $script:orbHover) {
        $script:angle = ($script:angle + 0.003)
    }
    $x = (($window.ActualWidth - $orb.Width) / 2) + [Math]::Sin($script:angle) * 60
    $y = (($window.ActualHeight - $orb.Height) / 2) + [Math]::Cos($script:angle * 0.73) * 40
    $breath = 1 + [Math]::Sin($script:angle * 1.8) * 0.04
    $orb.RenderTransformOrigin = "0.5,0.5"
    $orb.RenderTransform = New-Object System.Windows.Media.ScaleTransform($breath, $breath)
    [System.Windows.Controls.Canvas]::SetLeft($orb, $x)
    [System.Windows.Controls.Canvas]::SetTop($orb, $y)
    if (-not $script:orbHover) {
        $orb.Opacity = 0.50 + ([Math]::Sin($script:angle * 1.8) + 1) * 0.10
    } else {
        $orb.Opacity = 0.75
    }
    [System.Windows.Controls.Canvas]::SetLeft($halo, $x - 50 + [Math]::Sin($script:angle * 0.41) * 22)
    [System.Windows.Controls.Canvas]::SetTop($halo, $y - 50 + [Math]::Cos($script:angle * 0.37) * 18)
    $halo.Opacity = 0.10 + ([Math]::Cos($script:angle * 1.1) + 1) * 0.07
    if (-not $script:orbHover) {
        $sparkX = $x + 210 + [Math]::Cos($script:angle * 3.1) * (150 + 20 * [Math]::Sin($script:angle))
        $sparkY = $y + 210 + [Math]::Sin($script:angle * 2.3) * (100 + 25 * [Math]::Cos($script:angle * 0.7))
        [System.Windows.Controls.Canvas]::SetLeft($spark, $sparkX)
        [System.Windows.Controls.Canvas]::SetTop($spark, $sparkY)
    }
})
$window.Add_ContentRendered({
    $script:angle = 0.0
    $timer.Start()
})
$window.Add_Closed({ $timer.Stop() })
$window.Add_KeyDown({
    if ($_.Key -eq [System.Windows.Input.Key]::Escape) {
        $window.Close()
    }
})
if ($env:FAIRE_SCREENSAVER -eq "1") {
    # Preserve every normal single click for FAIRE navigation. Windows'
    # native double-click timing determines the deliberate exit gesture.
    $window.Add_MouseDoubleClick({
        $_.Handled = $true
        $window.Close()
    })
}
[void]$window.ShowDialog()

} catch {
    Write-Host ""
    Write-Host "Faire failed to start." -ForegroundColor Red
    Write-Host "----------------------------------------------------" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Location:" -ForegroundColor Red
    Write-Host $_.InvocationInfo.PositionMessage
    Write-Host "----------------------------------------------------" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close this window"
    exit 1
}
