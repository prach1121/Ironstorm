# Ironstorm — 3D FPS (Python + pygame)

![Version](https://img.shields.io/badge/version-v1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5.2%2B-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![Status](https://img.shields.io/badge/status-stable-brightgreen)

A raycasting 3D first-person shooter written in Python with **pygame-ce**.
12 weapons, animated enemies, particles, recoil, reloads and more.

---

## Table of contents

1. [Requirements](#requirements)
2. [Install & Run](#install--run)
3. [Controls](#controls)
4. [Git: Get the code (clone / pull)](#git-get-the-code-clone--pull)
5. [Git: Upload your changes (push)](#git-upload-your-changes-push)
6. [Git: Tags & Releases](#git-tags--releases)
7. [First-time upload to GitHub](#first-time-upload-to-github)
8. [Badges (shields.io)](#badges-shieldsio)

---

## Requirements

- Python 3.9+
- [pygame-ce](https://pypi.org/project/pygame-ce/) (use `pygame-ce`, **not** `pygame`, for newer Python versions)


Shortcuts:

| OS             | How                       |
| -------------- | ------------------------- |
| Windows        | Double-click `run.bat`    |
| Linux / macOS  | `./run.sh`                |

> If you have the old `pygame` installed, remove it first: `pip uninstall -y pygame`
> (`run.bat` does this automatically).

## Controls

| Key / Mouse                         | Action                          |
| ----------------------------------- | ------------------------------- |
| `W` `A` `S` `D`                     | Move                            |
| Mouse                               | Aim                             |
| Left click                          | Shoot                           |
| `Shift`                             | Sprint                          |
| `R`                                 | Reload (also restarts when dead)|
| `1`-`9`, `0`, `-`, `=`              | Select weapon (12 weapons)      |
| `Q` / `E` or mouse wheel            | Previous / next weapon          |
| `ESC`                               | Pause / quit                    |

---

## Git: Get the code (clone / pull)

### Clone (first time)

```bash
git clone https://github.com/<prach1121>/Ironstorm.git
```

### Pull (get the latest changes)

```bash
git pull origin main
```

If you have local changes and `pull` complains, either commit them first or stash them:

```bash
git stash          # save local changes temporarily
git pull origin main
git stash pop      # bring your changes back
```

---

## Project structure

```
.
├── main.py            # the whole game
├── requirements.txt   # pygame-ce
├── run.bat            # Windows launcher
├── run.sh             # Linux/macOS launcher
├── README.md
├── .gitignore
└── .gitattributes
```
