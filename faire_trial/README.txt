FAIRE WINDOWS OFFLINE CHAT TRIAL
================================

WHAT THIS IS
An inspectable Windows desktop chat shell for a local Ollama model. Faire sends
prompts only to http://127.0.0.1:11434 on your own computer.

FIRST-TIME SETUP
1. Install Ollama for Windows:
   https://ollama.com/download/windows
2. Open PowerShell and download a model:
   ollama pull llama3.2:3b
3. Double-click Check-Setup.cmd.
4. Double-click Start-Faire.cmd.

OFFLINE USE
Ollama and the model must be installed while online. After the model download
finishes, this trial can chat without an internet connection.

MODEL SELECTION
The default model is llama3.2:3b. To choose another installed model:
  $env:FAIRE_MODEL="your-model-name"
  .\Start-Faire.ps1

PRIVACY
The trial does not contact ThePolka.Cloud. It calls only the local Ollama API.
Review the PowerShell source before running it. Conversation history exists only
in memory and is discarded when the window closes.

REQUIREMENTS
- Windows 10 or newer
- Windows PowerShell 5.1+
- Ollama
- A locally downloaded model
- Hardware sufficient for the selected model

This is a Faire desktop trial, not a replacement operating system.
