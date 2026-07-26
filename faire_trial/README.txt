FAIRE SCREENSAVER OS — WINDOWS TRIAL
====================================

WHAT THIS IS
Faire is a full-screen black screensaver canvas with a single drifting orb.
The orb is the only thing on screen at idle. Click it to open the Faire
command panel; click it again, press Escape, or use the persistent "Faire
chat" tab at the bottom of the screen to reopen it any time - the chat is
never permanently hidden behind other cards. Capabilities appear as Faire
native scrapbook objects while the black canvas remains visible. Modern web
portals retain independent sessions and appear on a tab shelf, so several can
stay open without blank windows covering one another. Faire itself requires
no cloud account, API key, or paid tokens.

START
1. Optionally double-click Check-Setup.cmd.
2. Double-click Start-Faire.cmd.
3. Click the drifting orb to open the command prompt.
4. Type help to see the built-in commands.

EXPERIENCE COMMANDS
- build a browser
- show the globe in real satellite
- clear canvas
- build a website called Aurora
- weather in <city>  (opens as a pinned portal inside Faire)
- google search for <anything>  (opens as a pinned portal inside Faire)
- find <artist or subject> on YouTube
- find me YouTube videos about <subject>
- file explorer
- new document
- create project called <name>
- back up project <name>
- open Zoom
- open Google Drive
- show me the <site> homepage  (recognizes common sites; otherwise searches for it)
- checklist / plan / summarize / clean / risks / privacy - works with or without a colon
- Enter runs the command; Shift+Enter adds a line break
- Escape closes the prompt (press again, with the prompt already closed, to exit Faire)
- F11 toggles full-screen/windowed mode
- Clicking the orb again also closes the prompt

Live weather, satellite imagery, web browsing, YouTube, Zoom, and Google Drive
require an Internet connection. The canvas, local documents, file browser,
builders, notes, and built-in Faire engine work offline.

BUILT-IN TOOLS
- plan: structured delivery plan
- checklist: operational checklist
- summarize: concise extract from supplied text
- clean: whitespace and punctuation cleanup
- risks: dependency, privacy, access, and reliability review
- privacy: privacy-policy starter points
- note: session-only local notes shown as thumbtacked paper
- files: browse recent local files without leaving the canvas
- documents: write and save text under FaireWorkspace\Documents
- local intelligence: automatically uses a model found on localhost
- smart routing: a local model can turn improvised language into native Faire actions
- automatic filing: Projects, Documents, Notes, Research, Media, Code, Sessions, Exports, and Backups

PRIVACY
Built-in commands, notes, local files, and documents stay on the computer.
Weather and web features contact the sites the user explicitly requests.
Optional LLM chat connects only to 127.0.0.1 on the local machine. Faire does
not require a cloud AI service or transmit prompts to a paid model API.

REQUIREMENTS
- Windows 10 or newer
- Windows PowerShell 5.1+
- Microsoft Edge WebView2 Runtime for modern portals (normally included with current Windows; Faire has a compatibility fallback)

IMPORTANT CAPABILITY NOTE
Faire always includes its deterministic offline engine. If an Ollama-compatible
local runtime is available at 127.0.0.1:11434, Faire automatically uses the
first installed model for richer private conversation and natural-language
tool routing. Set FAIRE_LOCAL_MODEL to select a different installed model.
No cloud API key or paid tokens are involved.

FAIRE FILESYSTEM
Faire automatically creates FaireWorkspace and files work by category. Say
"create project called <name>" to activate a project. New notes, documents,
research, media, code, and exports are then stored under that project.
Conversations are recorded under Sessions. Say "back up project <name>" to
create a timestamped ZIP under Backups.

The runtime and model weights are not embedded in this trial ZIP. A fully
bundled edition is possible, but model weights typically add several gigabytes;
the final package must therefore choose a hardware tier before shipping.

This is a Faire desktop trial, not a replacement operating system.
REAL WINDOWS SCREENSAVER
------------------------
FAIRE now includes FaireOS.scr, a genuine Windows screensaver executable.

To install it:
1. Right-click Install-Screensaver.cmd and choose Run as administrator.
2. Select FaireOS in Windows Screen Saver Settings.

Windows launches FaireOS.scr with the standard /s screensaver switch. The
same interactive FAIRE canvas, orb, chat, native widgets, video cards, and
browser portals remain available. Press Escape to leave FAIRE. The installer
keeps the complete runtime in C:\ProgramData\FaireOS and registers FaireOS.scr
in the Windows screensaver directory so it remains configurable from the
normal Windows Screen Saver Settings panel.

Screensaver interaction:
- Single-click the orb, cards, tabs, and controls to navigate FAIRE.
- Double-click quickly anywhere on the FAIRE canvas to exit the screensaver.
- Escape also exits.
