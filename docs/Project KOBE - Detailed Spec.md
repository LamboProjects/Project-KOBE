# Project KOBE
## Detailed Planning Spec and Phased Roadmap

**Owner:** Lambert  
**Assistant Identity:** KOBE  
**Document Type:** Planning and Architecture Spec  
**Status:** Planning artifact — body reflects pre-build intent; implementation has diverged in places. See callout below.  
**Primary Build Environment:** Windows desktop  
**Primary Brain/Agent Stack:** OpenClaw + Claude via Claude Code  

---

> ### Implementation status (as of Phase 5)
>
> Phases 1–5 of the roadmap below are **shipped** on `origin/main`. Phase 6 (polish) and Phase 7 (holographic fan) are still planned.
>
> - §6 *Software Architecture Overview* and §7 *Recommended Core Tech Stack* are live — see `docs/ARCHITECTURE.md` for the module/event map that actually got built.
> - §8 *User Experience Design* (voice principles + confirmation model) is implemented via `src/kobe/actions/confirmation.py`.
> - §9 *HUD Specification* is live at `127.0.0.1:8765` (`src/kobe/hud/`).
> - §11 *Screen Vision* and §12 *Gesture Layer* (or equivalent sections) are live under `src/kobe/vision/` and `src/kobe/gestures/` respectively.
> - Hardware in §5 is accurate **except** the GPU: the live machine is an **RTX 3050 Ti Laptop · 4 GB VRAM**, not the 3060 originally targeted.
>
> The spec body is preserved as a planning artifact — don't treat any stale wording here as a contradiction of the shipped code.

---

# 1. Executive Summary

Project KOBE is a desk-based, voice-first AI assistant inspired by the usability and atmosphere of JARVIS, but tailored to Lambert's real workflow, hardware, and budget.

The goal is not just to create a novelty voice bot. The goal is to create a **polished, daily-use assistant system** that feels present, visually cohesive, and practically useful.

KOBE should eventually provide:

- Wake-word voice interaction
- Natural voice replies
- A persistent futuristic HUD on a dedicated second monitor
- Optional holographic fan output for ambient visuals and 3D content
- On-demand screen understanding
- Simple gesture control
- PC automation
- Bambu Lab P1S printer monitoring and control
- Spotify and Steam integration
- Discord-based alerts and optional voice-channel integration
- Expansion path for smart home control and additional user profiles later

The recommended approach is to build KOBE in **clear phases**, prioritizing reliability and daily usefulness before high-flash visual extras.

---

# 2. Project Vision

## 2.1 Core Vision

Build KOBE as a **Windows-based personal AI command center** that lives at Lambert's desk and operates through three primary layers:

1. **Voice** — natural conversational interface
2. **Visual HUD** — always-on system presence on a dedicated display
3. **Control Layer** — app actions, printer control, media control, and later gestures/smart devices

## 2.2 Design Philosophy

KOBE should feel:

- Fast
- Reliable
- Calm
- Futuristic
- Useful every day
- Polished enough to feel intentional, not experimental

KOBE should **not** feel like:

- A clunky chatbot with voice attached
- An overcomplicated home automation mess
- A gimmicky sci-fi screen saver with no practical utility

---

# 3. Locked Decisions and Confirmed Requirements

## 3.1 Identity and Interaction

- Assistant name: **KOBE**
- Inspiration: JARVIS-level polish and presence
- Personality: Same overall personality as current assistant, warm and capable, with occasional dry wit
- Response style: concise, polished, natural
- Language: English primary
- Translation support: yes, when explicitly requested

## 3.2 Voice Activation

Supported wake phrases:

- **Hey KOBE**
- **OK KOBE**

Interaction behavior:

- Barge-in supported, user can interrupt KOBE while it is speaking
- Always-on listening should be available as an option
- Listening mode should be toggleable
- Physical mute should exist eventually
- Software mute should exist as well
- KOBE should only respond when spoken to, not proactively chat on its own

## 3.3 Platform and Use Context

- Primary platform: **Windows PC**
- GPU: **RTX 3060**
- Use environment: at the desk only
- Runtime expectation: active when Lambert is at the desk and using the PC
- Audio hardware: USB microphone + dedicated speakers
- Display setup: two monitors, with one dedicated to KOBE HUD
- Room: bedroom

## 3.4 Display and Interaction Style

- Main KOBE display: dedicated second monitor
- Display mode: always-on
- Style: techy, holographic, clean
- Optional future display: desk-mounted holographic fan
- Gesture control: yes, but simple first
- On-demand screen understanding: yes

## 3.5 Software/Integration Targets

Primary app integrations:

- Spotify
- Steam
- VS Code
- Bambu Studio
- FreeCAD preferred as free CAD tool
- Discord on PC

Printer integration target:

- Bambu Lab P1S
- Same network access available
- Local and cloud integration both acceptable

Smart home:

- Current device: smart plug
- Future: lights and more devices

## 3.6 Safety and Control Preferences

- Destructive or important actions require confirmation
- Just one user for now
- Architecture should allow future support for Jasmine/profile expansion later

## 3.7 Budget

- Hardware budget: under approximately **$1000** for the broader build
- Ongoing software/API budget tolerance: up to **$75/month** if the result is polished and worth it

---

# 4. Recommended Experience Goals

## 4.1 What “Close to JARVIS” Means in Practice

To get close to a JARVIS-like experience in real life, KOBE must excel at:

- Fast response time
- Low-friction voice activation
- Strong TTS quality
- Calm concise delivery
- A visually coherent interface that is always present
- Tight integration into real tasks, especially PC control and printer workflows

The best version of KOBE is not a movie prop. It is a **daily-use operating layer** over Lambert's digital environment.

## 4.2 Daily Use Cases

High-value practical use cases include:

- Launching common apps by voice
- Reading and summarizing visible screen content on request
- Checking Bambu print status hands-free
- Alerting when a print finishes or fails
- Controlling Spotify by voice
- Launching games from Steam
- Switching between work and entertainment states
- Showing persistent status and context on the dedicated HUD

---

# 5. Hardware Architecture

## 5.1 Core Hardware

### Windows PC
This is the main compute node.

Responsibilities:

- Run STT locally
- Run wake word detection
- Run local UI/HUD
- Run gesture recognition
- Handle app automation
- Interface with OpenClaw/Claude
- Interface with printer and media systems

### GPU: RTX 3060
This is a strong asset.

Benefits:

- Enables local `faster-whisper` with good performance
- Reduces dependence on cloud STT
- Improves latency and privacy
- Makes the voice loop more practical for real use

### Dedicated KOBE Monitor
This should be treated as KOBE's persistent visual presence.

Primary uses:

- HUD
- Status widgets
- Voice transcript
- Active response display
- Printer dashboard
- Media display
- System state indicators

Recommended role:

- Fullscreen KOBE UI, always on
- Not just a window, but a persistent command display

### USB Microphone
Already available.

Requirement:

- Clear enough for near-field wake word + STT capture
- Should support software mute and ideally easy physical mute in workflow

### Dedicated Speakers
Already available.

Requirement:

- Clear speech playback
- Good separation from mic if possible to minimize echo
- Tuned for voice clarity over bass-heavy output

---

## 5.2 Recommended Add-On Hardware

### Webcam for Gesture Tracking
**Recommendation:** Logitech C922  
**Upgrade Option:** Logitech Brio 4K

Reasoning:

- Widely supported
- Good image quality for hand tracking
- Strong value and reliability
- Suitable for MediaPipe-based simple gesture control

Use cases:

- Swipe gestures
- Point/select
- Confirm/dismiss
- Control visual modules on HUD
- Gesture-linked holographic fan behavior later

### Physical Mute / Push Button
Recommended eventually.

Options:

- USB mute button
- Stream Deck mini-style control
- Custom ESP32 or Arduino desk button later

Use cases:

- Hard mute mic
- Push-to-talk mode toggle
- Manual wake or confirm input

### Holographic Fan
Recommended later, not early MVP.

Recommended class:

- 65 cm WiFi/app-controlled holographic fan
- Mid-range consumer model that supports custom media upload

Suggested usage:

- KOBE logo animation
- Music-reactive visuals
- 3D model display
- Printer visualization
- Gesture-reactive ambient output

### Optional Future Projector
This should come after the monitor HUD is proven useful.

---

# 6. Software Architecture Overview

## 6.1 High-Level System Layers

KOBE should be designed as six coordinated layers:

1. **Wake Layer**
2. **Voice Layer**
3. **Reasoning/Brain Layer**
4. **Execution Layer**
5. **Visual Layer**
6. **Peripheral Integration Layer**

---

## 6.2 Layer Details

### 6.2.1 Wake Layer
Purpose:

- Listen for wake phrases
- Support mute/toggle states
- Minimize false triggers

Recommended technology:

- **OpenWakeWord**

Requirements:

- Supports “Hey KOBE” and “OK KOBE”
- Works well with desktop mic setup
- Can be paused or disabled
- Works in always-on and manual modes

### 6.2.2 Voice Layer
Purpose:

- Convert speech to text
- Convert responses to speech
- Handle interruption/barge-in cleanly

#### STT Recommendation
Primary:

- **faster-whisper**, local, GPU-accelerated

Why:

- Lower recurring cost
- Better privacy
- Good quality
- Suitable with RTX 3060

Fallback or optional hybrid:

- OpenAI Whisper API for backup or edge cases

#### TTS Recommendation
Primary polished option:

- **ElevenLabs**

Reason:

- Most natural voice quality
- Best chance of a “real” presence

Secondary option:

- **OpenAI TTS**

Reason:

- Fast and high quality
- Simpler integration path in some cases

TTS behavior requirements:

- Calm, polished, natural
- Can be interrupted mid-response
- Shorter responses by default in voice mode
- Occasional dry wit okay, but not overdone

### 6.2.3 Reasoning/Brain Layer
Purpose:

- Understand requests
- Maintain context
- Route tools/actions
- Generate concise voice responses

Recommended architecture:

- **OpenClaw + Claude**, with planning and orchestration work done in Claude Code

Reason:

- Existing tool ecosystem already available
- Memory and integrations already fit the broader assistant vision
- Easier to extend later than building a standalone custom LLM orchestration stack from scratch

### 6.2.4 Execution Layer
Purpose:

- Perform desktop actions
- Query integrations
- Return state to the UI and speech layer

Responsibilities:

- Launch apps
- Control media
- Query printer
- Confirm destructive actions
- Potentially inspect screen content on request
- Support Discord alerts/messages where relevant

### 6.2.5 Visual Layer
Purpose:

- Make KOBE visually present and informative
- Show system state and context continuously

Recommended implementation pattern:

- Fullscreen local desktop app or web-based local app on dedicated monitor
- Electron or local browser-based app both acceptable

### 6.2.6 Peripheral Integration Layer
Purpose:

- Connect to printer
- Connect to Spotify/Steam/Discord
- Connect to webcam/gesture layer
- Future smart home devices
- Future holographic fan output

---

# 7. Recommended Core Tech Stack

## 7.1 Voice and Wake

- Wake word: **OpenWakeWord**
- STT: **faster-whisper**
- TTS primary: **ElevenLabs**
- TTS backup/alternate: **OpenAI TTS**
- Audio routing: local Windows audio handling

## 7.2 Brain and Orchestration

- OpenClaw
- Claude/Claude Code
- Local orchestration layer written around KOBE components

## 7.3 UI and HUD

Recommended options:

### Option A, Electron-based HUD
Pros:

- Desktop-like feel
- Easy fullscreen kiosk behavior
- Easy packaging later

Cons:

- Slightly heavier stack

### Option B, Local web app
Pros:

- Faster to prototype
- Easy visual iteration
- Easy integration with local APIs/websockets

Cons:

- Slightly more manual window management depending on setup

Recommendation:

- Start with a **local web app** for speed of iteration
- Convert to Electron later if desired

## 7.4 Gesture Layer

- Webcam: C922 or Brio
- Tracking: **MediaPipe Hands**
- Gesture recognition: custom simple gesture mapping

## 7.5 CAD Tooling

- **FreeCAD** as primary free CAD software
- Onshape as optional later convenience layer

## 7.6 Printer Layer

- Bambu local network access where possible
- Cloud as optional convenience or fallback path
- Bambu Studio as launch/control companion

---

# 8. User Experience Design

## 8.1 Voice Experience Principles

KOBE should sound:

- Calm
- Clear
- Competent
- Brief by default
- Natural, not robotic

KOBE should not ramble in voice mode.

Voice-first response style examples:

- “Done.”
- “Opening VS Code.”
- “Your print is 63 percent complete, about 42 minutes remaining.”
- “I can do that, but I need your confirmation first.”

## 8.2 Confirmation Model

KOBE should require confirmation before:

- Canceling a print
- Closing major apps unexpectedly
- Sending messages
- Triggering actions that can lose work or have side effects

Recommended spoken pattern:

- “I can cancel the print. Confirm?”
- “That will close Bambu Studio. Proceed?”

Confirmation methods can include:

- Voice
- Gesture
- Screen button
- Physical button later

## 8.3 Visual Tone

Recommended visual theme:

- Dark background
- Deep blue
- Cyan highlights
- White text
- Amber/orange for warnings and alerts

Reasoning:

- Feels futuristic without becoming cheesy
- More readable in a bedroom setup
- More sustainable for long-term daily use than a loud movie color palette

---

# 9. HUD Specification

## 9.1 Purpose of the HUD

The HUD is the visual embodiment of KOBE.

It should make the assistant feel present even when silent. It should also make key information glanceable without needing to ask every time.

## 9.2 HUD Mode

- Dedicated second monitor
- Always on
- Fullscreen or kiosk-like layout
- Minimal mouse/keyboard dependence once running

## 9.3 Core HUD Modules

### Persistent Modules
These should nearly always be visible in some form:

- Current time/date
- KOBE state: muted / idle / listening / thinking / speaking
- Current mic status
- Current active app or context indicator
- System health indicator
- Current printer quick status
- Spotify quick status
- Discord quick status if relevant

### Dynamic Modules
These appear contextually:

- Live voice transcript
- Assistant response panel
- App launch overlay
- Screen-analysis summary
- Print dashboard details
- Gesture hint overlay
- Confirmation prompt panel

### Printer Module
Should eventually display:

- Printer state
- Progress percent
- Time remaining
- Print name
- AMS status if available
- Camera preview if feasible
- Error/warning badge

### Media Module
Should display:

- Current track name
- Artist
- Playback state
- Playlist/mode
- Optional visualizer tie-in for fan later

### Utility Module
Optional later:

- CPU/GPU/system usage
- Current workflow mode (work/gaming/printing)
- Quick app buttons

## 9.4 HUD Behavior Principles

- Clean and readable from a distance
- Responsive transitions
- No cluttered sci-fi noise for its own sake
- Important events should be visually obvious
- Idle mode should still look alive, but subdued

---

# 10. Holographic Fan Concept Specification

## 10.1 Role of the Fan

The holographic fan should be treated as a **secondary spectacle and ambient information surface**, not the primary interface.

## 10.2 Intended Content

Potential display modes:

- KOBE rotating logo
- Simple 3D model spin/preview
- Music-reactive visuals during Spotify playback
- Bambu print status visuals
- Gesture-linked feedback animations

## 10.3 Recommended Integration Strategy

Do not make the fan critical to system usability.

Instead:

- Build main HUD first
- Create a simple media pipeline for the fan later
- Mirror selected status outputs, not all UI complexity

## 10.4 Why This Matters

This prevents the project from turning into a hardware rabbit hole before the main assistant works well.

---

# 11. Gesture Control Specification

## 11.1 Approach

Start with **simple gestures only**.

Avoid ambitious cinematic control schemes in early phases.

## 11.2 Recommended Initial Gesture Set

- Swipe left
- Swipe right
- Point/select
- Confirm
- Dismiss/back

## 11.3 Intended Use Cases

- Switch HUD panels
- Accept or reject confirmation dialogs
- Move through printer/media views
- Trigger specific display modes
- Interact with holographic fan content later

## 11.4 Technical Guidance

Gesture reliability matters more than gesture variety.

A small set of gestures that works well is better than an impressive demo that misfires constantly.

---

# 12. Screen Vision Specification

## 12.1 Desired Capability

KOBE should be able to inspect the screen or active window on request.

Examples:

- “What’s on my screen?”
- “Summarize this page.”
- “What error is this?”
- “Read the print settings on screen.”

## 12.2 Scope

This should be **on-demand**, not constantly surveilling.

## 12.3 Usefulness

This feature will be especially valuable for:

- Coding help in VS Code
- Printer setting review in Bambu Studio
- CAD troubleshooting
- Reading dialogs, errors, or settings

---

# 13. PC Automation Specification

## 13.1 Initial Scope

KOBE should support basic desktop commands such as:

- Open app
- Close app with confirmation where needed
- Focus/switch app
- Control volume
- Control media playback
- Launch Steam games
- Open websites or tools

## 13.2 High-Priority Apps

- Spotify
- Steam
- VS Code
- Bambu Studio
- FreeCAD
- Other 3D software later if added

## 13.3 Expansion Scope

Later expansions can include:

- File search
- Script execution
- Window management
- Workflow macros
- Context-sensitive actions based on active app

---

# 14. Bambu Lab P1S Integration Specification

## 14.1 Importance

This is one of the highest-value integrations in the entire project.

KOBE should become a hands-free printer companion.

## 14.2 Must-Have Features

- Check print status by voice
- Show print progress on HUD
- Give print finished alerts
- Give print failure alerts
- Send Discord alerts for key events
- Speak printer status on request

## 14.3 Control Features

With confirmation required:

- Pause print
- Resume print
- Cancel print

## 14.4 Desired Dashboard Fields

- Print name
- Progress percent
- Time remaining
- Current status
- AMS / filament information if available
- Camera feed if feasible
- Error state / warnings

## 14.5 Example Commands

- “Hey KOBE, how’s my print doing?”
- “OK KOBE, pause the print.”
- “Hey KOBE, show the printer dashboard.”
- “OK KOBE, cancel the print.” → requires confirmation

---

# 15. Spotify and Entertainment Specification

## 15.1 Spotify Goals

Support both practical control and fun ambient integration.

Features:

- Play/pause
- Next/previous
- Volume control
- Start playlists
- Mood-style requests if feasible later
- Show current song on HUD
- Tie music state to fan visuals later

## 15.2 Steam Goals

Features:

- Launch games by voice
- Track playtime or session state where feasible
- Show current game context later
- Expand later to wishlist/deal awareness if desired

## 15.3 Anime/Streaming Goals

For now, this should be lower priority.

Because Netflix/Crunchyroll direct automation and structured tracking can be inconsistent, anime support should likely come later through:

- AniList or MyAnimeList integration
- Watch progress assistant features
- Recommendation tracking

This should not block the core KOBE build.

---

# 16. Discord Integration Specification

## 16.1 Current Role

Discord should be treated as an auxiliary communication layer.

## 16.2 High-Value Uses

- Printer finished/failed alerts
- Optional text summaries
- Optional voice-channel experiments later
- Fallback remote notification path

## 16.3 Recommended Priority

Start with alert delivery, not deep Discord automation.

---

# 17. Smart Home Expansion Path

## 17.1 Current Devices

- Smart plug

## 17.2 Expected Future Devices

- Smart lights
- Additional smart devices later

## 17.3 Recommendation

Keep smart home support out of MVP except for clean architectural allowance.

Reason:

- It is easy to lose focus and turn this into a generic home assistant
- KOBE should first be exceptional at the desk use case

---

# 18. Recommended Free and Paid Tool Strategy

## 18.1 Best Cost-Performance Mix

### Local / Free
- Wake word: OpenWakeWord
- STT: faster-whisper on RTX 3060
- Gesture tracking: MediaPipe
- CAD: FreeCAD

### Paid where polish matters most
- TTS: ElevenLabs preferred
- Optional TTS fallback: OpenAI TTS

This aligns well with Lambert's budget tolerance and desire for polish.

## 18.2 Monthly Cost Outlook

Expected likely spend, depending on usage:

- $0 to low-cost for STT if local only
- TTS spend depends on response volume
- Within the allowed $75/month budget if managed properly

---

# 19. Risks and Constraints

## 19.1 Main Technical Risks

### Voice Latency
Potential bottleneck:

- Wake detection → STT → model → TTS chain may feel sluggish if not tuned carefully

Mitigation:

- Local STT
- Concise voice responses
- Tight routing logic

### False Wake Triggers
Potential issue:

- Always-on systems can trigger accidentally

Mitigation:

- Good wake phrase tuning
- Mute mode
- Push-to-talk or manual mode fallback

### Echo / Audio Feedback
Potential issue:

- Speakers and mic in same room can cause re-triggering or poor capture

Mitigation:

- Proper mic placement
- Speaker tuning
- Echo cancellation strategies
- Push-to-talk fallback if needed

### Gesture Reliability
Potential issue:

- Gesture systems can feel cool but frustrating if too ambitious

Mitigation:

- Keep initial gesture set small
- Treat gestures as enhancement, not core dependency

### UI Overbuild
Potential issue:

- Spending too much time making the HUD flashy before the assistant is useful

Mitigation:

- Build core voice first
- Add polished UI after workflow value is established

### Printer API/Control Edge Cases
Potential issue:

- Local/cloud differences, inconsistent telemetry, or control constraints

Mitigation:

- Phase printer work carefully
- Separate status features from control features

---

# 20. Architecture Principles for Claude Code Build

## 20.1 Build Principles

Claude Code should be guided to build KOBE with these principles:

- Modular architecture
- Clean boundaries between voice, UI, integrations, and automation
- Config-driven behavior where possible
- Confirmation layer for destructive actions
- Event-driven updates for HUD and alerts
- Local-first where practical
- Replaceable providers for TTS/STT when possible

## 20.2 Modules to Design Around

Suggested architecture modules:

- `wake_service`
- `stt_service`
- `tts_service`
- `conversation_router`
- `action_executor`
- `hud_frontend`
- `hud_backend`
- `printer_integration`
- `spotify_integration`
- `steam_integration`
- `discord_alerts`
- `gesture_service`
- `screen_vision_service`
- `confirmation_manager`
- `settings/profile_manager`

Even if implementation names differ, the architecture should think this way.

---

# 21. Recommended Phased Roadmap

## Phase 1: Core Voice MVP
**Goal:** KOBE can hear, think, and speak reliably on the PC.

### Deliverables
- Wake word detection
- Local STT
- TTS output
- Barge-in interruption
- Mute toggle
- Physical mute support planned or scaffolded
- Basic voice-command routing
- Basic app launching

### Success Criteria
- KOBE responds quickly and consistently
- Commands like app launching work reliably
- Voice experience already feels useful

### Example end-state for Phase 1
- “Hey KOBE, open Spotify.”
- “OK KOBE, open VS Code.”
- “Hey KOBE, what’s on my screen?”

---

## Phase 2: HUD MVP
**Goal:** Give KOBE persistent visual presence on the second monitor.

### Deliverables
- Fullscreen always-on HUD
- State indicators
- Transcript display
- Response panel
- Basic widgets for media/system state
- Visual theme established

### Success Criteria
- KOBE feels like a live desktop system, not just a voice utility
- UI is readable and attractive

---

## Phase 3: Productivity and Printer Integration
**Goal:** Make KOBE materially useful in daily workflows.

### Deliverables
- Bambu printer dashboard
- Voice queries for print state
- Voice + Discord completion/failure alerts
- Pause/resume/cancel with confirmation
- App automation improvements
- Better desktop action support
- Spotify control improvements
- Steam launch integration

### Success Criteria
- KOBE becomes part of actual printing and desktop workflow
- Printer visibility is strong and convenient

---

## Phase 4: Screen Vision and Context Awareness
**Goal:** Increase usefulness during active work.

### Deliverables
- On-demand screen inspection
- Better active-app context behavior
- Improved workflow help for coding/CAD/printing

### Success Criteria
- KOBE can help interpret what is currently on screen in a practical way

---

## Phase 5: Gesture Control
**Goal:** Add a second natural interaction channel without hurting reliability.

### Deliverables
- Webcam integration
- Simple gestures
- Panel navigation by gesture
- Gesture confirmation/dismissal

### Success Criteria
- Gesture features are genuinely usable and not frustrating

---

## Phase 6: Premium Polish
**Goal:** Make the whole system feel cohesive and premium.

### Deliverables
- TTS tuning
- Better animations
- Better visual states
- Voice/persona refinement
- Smoother command handoff behavior
- Better Discord integration
- Smart home hooks prepared

### Success Criteria
- KOBE feels polished and intentional

---

## Phase 7: Holographic Fan Integration
**Goal:** Add spectacle and ambient visual presence.

### Deliverables
- Fan content pipeline
- KOBE logo visuals
- 3D model playback
- Music mode
- Printer status mode
- Gesture-linked effects

### Success Criteria
- Fan enhances the system without becoming the main dependency

---

# 22. Recommended Build Order

The recommended implementation order is:

1. Voice pipeline
2. Wake words
3. TTS quality and interruption
4. Basic command execution
5. HUD foundation
6. Printer integration
7. Discord alerts
8. Screen vision
9. Gesture control
10. Premium polish
11. Holographic fan support
12. Smart home expansion

This is the highest-probability path to a working and impressive system.

---

# 23. Definition of MVP

A real MVP for KOBE should include:

- Wake word support
- Reliable voice capture
- Natural TTS
- App launching
- Basic screen inspection on request
- Always-on second monitor HUD
- Core printer visibility
- Confirmation flows

If those pieces work well together, KOBE will already feel significantly more real than most hobby voice assistants.

---

# 24. What Not to Do Too Early

Avoid these traps in the early build:

- Over-designing the holographic fan before core voice works
- Building complex gesture vocabulary too soon
- Spending weeks on animations before printer/app utility exists
- Turning the project into a full home automation platform too early
- Supporting too many integrations before the architecture is stable

The project should stay focused on a polished desk-based assistant first.

---

# 25. Final Recommendation

The strongest path forward is:

**Build KOBE first as a high-quality desk assistant with excellent voice, a strong HUD, and deep printer/app integration.**

That path gets closest to a believable JARVIS-like experience because it creates:

- presence
- utility
- visual identity
- smooth control
- real daily value

Once those are solid, the gesture and holographic layers become enhancements instead of distractions.

---

# 26. Claude Code Planning Prompt

Use the following prompt in Claude Code to continue planning or begin architecture work:

```md
Build a detailed architecture and implementation plan for Project KOBE, a Windows-based desk AI assistant inspired by JARVIS.

Requirements:
- Wake words: “Hey KOBE” and “OK KOBE”
- Runs on a Windows PC with RTX 3060
- Uses local faster-whisper for STT
- Uses high-quality TTS, preferably ElevenLabs, with OpenAI TTS as backup
- Supports barge-in interruption
- Includes software mute and future physical mute button support
- Uses a dedicated second monitor for an always-on holographic-style HUD
- Supports on-demand screen vision
- Integrates with Spotify, Steam, VS Code, Bambu Studio, and FreeCAD
- Includes deep Bambu Lab P1S integration with voice queries, HUD display, alerts, and pause/resume/cancel with confirmation
- Sends Discord alerts for printer events
- Supports simple gesture control via webcam and MediaPipe
- Plans for future holographic fan integration
- Single user for now, but should be architected so future multi-profile support is possible
- Must require confirmation before destructive actions

I want:
- system architecture
- module breakdown
- phased roadmap
- suggested project structure
- provider recommendations
- risk analysis
- MVP definition
- implementation order

Do not start coding until the architecture is clear and approved.
```

---

# 27. Next Step Recommendation

Immediate next step:

**Use this document as the master planning brief in Claude Code, and ask it to convert this into a formal architecture package with folder structure, module contracts, event flows, and component interfaces before any implementation begins.**

That will keep the build clean and prevent rework later.
