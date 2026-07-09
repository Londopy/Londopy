<div align="center"> 
     
[![Typing SVG](https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=30&pause=1000&color=D97706&center=true&vCenter=true&random=false&width=720&lines=hey+%E2%80%94+i'm+london;python+%2B+rust+%2F+ship+a+lot;climber+%C2%B7+skier+%C2%B7+surfer+%C2%B7+wfr;build+because+the+problem+is+interesting)](https://git.io/typing-svg)

<img src="https://komarev.com/ghpvc/?username=Londopy&style=flat-square&color=D97706&label=profile+views"/>
&nbsp;
<img src="https://img.shields.io/badge/PyPI-7_packages_shipped-4A7B3E?style=flat-square&logo=pypi&logoColor=white"/>
&nbsp;
<img src="https://img.shields.io/badge/stack-Python_%2F_Rust-7A5C3A?style=flat-square"/>

### 🌐 &nbsp; [**londopy.github.io**](https://londopy.github.io)

*the full, filterable project index — grouped by domain, with per-project writeups*

</div>

---

## 👋 &nbsp; about

I build tools for **climbing**, **medicine**, **Windows internals**, and **myself**. California kid, freshman in college, writing Python between surf sessions and rock climbs. Most of what's here started because something annoyed me on a trail or in the field — a rope question, a pre-hospital protocol, a screen-capture API doing something I didn't ask for — so I built the tool.

Rust and Python, mostly. Half of it is libraries, half is GUIs, occasionally it's a Rust core that makes the whole thing 100× faster.

> **into right now** — climbing rope dynamics · pre-hospital med tooling · Windows internals · geospatial / OSINT
>
> **outside the keyboard** — skiing the sierras · surfing the coast · WFR field practice · trad climbing anywhere I can drive to

**reach me →** discord `_londo`

---

## 🛠️ &nbsp; featured

> Four I'm proudest of. The **[full index of 18 projects across 9 domains lives on the site »](https://londopy.github.io)** — filterable by tag and language, with writeups.

### 🖥️ &nbsp; [capture-bypass](https://github.com/Londopy/capture-bypass) — Windows screen-capture bypass
[![Rust](https://img.shields.io/badge/core-Rust-7A5C3A?style=flat-square&logo=rust&logoColor=white)](https://github.com/Londopy/capture-bypass) [![Windows 10/11](https://img.shields.io/badge/Windows-10%2F11-4A7B3E?style=flat-square&logo=windows&logoColor=white)](https://github.com/Londopy/capture-bypass) [![writeup »](https://img.shields.io/badge/writeup-%C2%BB-D97706?style=flat-square)](https://londopy.github.io/projects/capture-bypass/)

DLL-injection tool that clears `WDA_EXCLUDEFROMCAPTURE` on Windows 10/11. Multi-crate workspace, egui GUI, Inno installer.

### 🧠 &nbsp; [akribia](https://github.com/Londopy/akribia) — precision-weighted Bayesian brain model
[![Python](https://img.shields.io/badge/core-Python-7A5C3A?style=flat-square&logo=python&logoColor=white)](https://github.com/Londopy/akribia) [![live demo »](https://img.shields.io/badge/live-demo-D97706?style=flat-square)](https://londopy.github.io/akribia/)

Computational model of precision-weighted Bayesian inference across autism, ADHD, and PPCS — with a live in-browser demo.

### 💊 &nbsp; [drugdose](https://github.com/Londopy/drugdose) — EMS & clinical dosing calculator
[![PyPI](https://img.shields.io/pypi/v/drugdose?color=D97706&style=flat-square)](https://pypi.org/project/drugdose/) [![49 drugs](https://img.shields.io/badge/database-49_drugs-4A7B3E?style=flat-square)](https://github.com/Londopy/drugdose) [![writeup »](https://img.shields.io/badge/writeup-%C2%BB-7A5C3A?style=flat-square)](https://londopy.github.io/projects/drugdose/)

Weight-based dosing, a 49-drug bundled database, and 39 interaction rules with severity + management guidance. Pure Python.

### 🧗 &nbsp; [ropesim](https://github.com/Londopy/ropesim) — climbing-rope physics engine
[![PyPI](https://img.shields.io/pypi/v/ropesim?color=D97706&style=flat-square)](https://pypi.org/project/ropesim/) [![Rust](https://img.shields.io/badge/core-Rust-7A5C3A?style=flat-square&logo=rust&logoColor=white)](https://github.com/Londopy/ropesim) [![writeup »](https://img.shields.io/badge/writeup-%C2%BB-4A7B3E?style=flat-square)](https://londopy.github.io/projects/ropesim/)

UIAA / EN 892 impact-force modelling — damped-spring RK4 core in Rust via PyO3 / Maturin, with a PySide6 3D GUI.

<div align="center">


</div>

---

## 📦 &nbsp; the stack

```bash
londo@dev:~$ env | grep STACK
```

```ini
LANGUAGES        = Python · Rust · TypeScript · C++ · Bash
BUILD_AND_SHIP   = PyPI · Maturin · PyO3 · GitHub Actions · PyInstaller · Cargo workspaces
DATA_AND_VIZ     = NumPy · Pandas · Matplotlib · Seaborn · Folium · Vispy
GUI              = PySide6 · Qt · Tkinter · pystray · pywin32
INFRA            = SQLite · Win / Linux / macOS · DLL injection · Win32
CREATIVE         = Nuke · Maya · After Effects · Premiere · AutoCAD · Houdini
```

---

## 🧭 &nbsp; how the work clusters


```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#FAF6EC','primaryTextColor':'#2A2418','primaryBorderColor':'#7A5C3A','lineColor':'#7A5C3A','tertiaryColor':'#FFF8EC'}}}%%
mindmap
  root((London))
    Climbing & physics
      ropesim
      Rust + PyO3
      damped-spring RK4
      PySide6 + Vispy
    Pre-hospital med
      drugdose
      vitalscore
      WFR field tooling
    Windows internals
      capture-bypass
      HideDesktopApps
      DLL injection
      Win32 + pywin32
    Geographic / OSINT
      pygeospy
      SAR grids
      EXIF + terrain
    Languages
      Python
      Rust · PyO3 · Maturin
      C++
    Off-keyboard
      trad climbing
      backcountry skiing
      surfing
      WFR
```

---

```bash
londo@dev:~$ contributions --animate
```

> Snake eats my commit graph daily. Looks better with the dark theme on.
<div align="center">

![snake animation](https://raw.githubusercontent.com/Londopy/Londopy/output/github-contribution-grid-snake-dark.svg)

</div>

---

<div align="center">

```
freshman year. just getting started.
```

discord: `_londo`

</div>
