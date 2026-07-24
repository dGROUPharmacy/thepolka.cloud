Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore

$script:model = if ($env:FAIRE_MODEL) { $env:FAIRE_MODEL } else { "llama3.2:3b" }
$script:messages = [System.Collections.ArrayList]::new()

$window = New-Object Windows.Window
$window.Title = "Faire - local AI"
$window.Width = 860
$window.Height = 680
$window.MinWidth = 620
$window.MinHeight = 480
$window.WindowStartupLocation = "CenterScreen"
$window.Background = "#0B1320"

$grid = New-Object Windows.Controls.Grid
@("Auto", "*", "Auto", "Auto") | ForEach-Object {
    $row = New-Object Windows.Controls.RowDefinition
    $row.Height = $_
    [void]$grid.RowDefinitions.Add($row)
}

$header = New-Object Windows.Controls.Border
$header.Background = "#101F31"
$header.Padding = 18
$headerText = New-Object Windows.Controls.TextBlock
$headerText.Text = "FAIRE  /  LOCAL AI  /  $script:model"
$headerText.Foreground = "#BFF9F0"
$headerText.FontSize = 17
$headerText.FontWeight = "Bold"
$header.Child = $headerText
[Windows.Controls.Grid]::SetRow($header, 0)
$grid.Children.Add($header) | Out-Null

$conversation = New-Object Windows.Controls.TextBox
$conversation.Margin = 18
$conversation.Padding = 16
$conversation.Background = "#07101B"
$conversation.Foreground = "#E8F3F1"
$conversation.BorderBrush = "#29465A"
$conversation.FontFamily = "Consolas"
$conversation.FontSize = 14
$conversation.TextWrapping = "Wrap"
$conversation.VerticalScrollBarVisibility = "Auto"
$conversation.IsReadOnly = $true
$conversation.AcceptsReturn = $true
$conversation.Text = "Faire is ready.`r`nModel: $script:model`r`nEverything in this window is sent only to Ollama at 127.0.0.1.`r`n`r`n"
[Windows.Controls.Grid]::SetRow($conversation, 1)
$grid.Children.Add($conversation) | Out-Null

$input = New-Object Windows.Controls.TextBox
$input.Margin = "18,0,18,10"
$input.Padding = 12
$input.MinHeight = 74
$input.AcceptsReturn = $true
$input.TextWrapping = "Wrap"
$input.Background = "#13283B"
$input.Foreground = "White"
$input.BorderBrush = "#477086"
$input.FontSize = 14
[Windows.Controls.Grid]::SetRow($input, 2)
$grid.Children.Add($input) | Out-Null

$bar = New-Object Windows.Controls.DockPanel
$bar.Margin = "18,0,18,18"
$status = New-Object Windows.Controls.TextBlock
$status.Text = "Local-only session"
$status.Foreground = "#8FB5B3"
$status.VerticalAlignment = "Center"
[Windows.Controls.DockPanel]::SetDock($status, "Left")
$bar.Children.Add($status) | Out-Null
$send = New-Object Windows.Controls.Button
$send.Content = "Send to local model"
$send.Padding = "18,10"
$send.Background = "#C8F36B"
$send.Foreground = "#07101B"
$send.BorderThickness = 0
$send.FontWeight = "Bold"
$send.HorizontalAlignment = "Right"
[Windows.Controls.DockPanel]::SetDock($send, "Right")
$bar.Children.Add($send) | Out-Null
[Windows.Controls.Grid]::SetRow($bar, 3)
$grid.Children.Add($bar) | Out-Null

$send.Add_Click({
    $prompt = $input.Text.Trim()
    if (-not $prompt) { return }
    $input.Clear()
    $conversation.AppendText("YOU`r`n$prompt`r`n`r`n")
    $conversation.ScrollToEnd()
    [void]$script:messages.Add(@{ role = "user"; content = $prompt })
    $send.IsEnabled = $false
    $status.Text = "Thinking locally..."
    try {
        $payload = @{ model = $script:model; stream = $false; messages = @($script:messages) } | ConvertTo-Json -Depth 8
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/chat" -Method Post -ContentType "application/json" -Body $payload -TimeoutSec 600
        $answer = [string]$response.message.content
        [void]$script:messages.Add(@{ role = "assistant"; content = $answer })
        $conversation.AppendText("FAIRE`r`n$answer`r`n`r`n")
        $status.Text = "Local-only session"
    } catch {
        $conversation.AppendText("SYSTEM`r`nOllama did not answer. Start Ollama and confirm the model is installed with: ollama pull $script:model`r`n`r`n")
        $status.Text = "Connection unavailable"
    } finally {
        $send.IsEnabled = $true
        $conversation.ScrollToEnd()
        $input.Focus()
    }
})

$window.Content = $grid
$window.Add_ContentRendered({ $input.Focus() })
[void]$window.ShowDialog()
