# IRON STORM — 3D FPS (Python + pygame)

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

## Install & Run

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>

pip install -r requirements.txt
python main.py
```

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
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
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

### Get a specific version (tag)

```bash
git fetch --tags
git checkout v1.0.0        # use that version
git checkout main          # go back to latest
```

---

## Git: Upload your changes (push)

```bash
# 1. See what changed
git status

# 2. Stage the files
git add .                  # or: git add main.py

# 3. Commit with a message
git commit -m "Describe what you changed"

# 4. Get the latest first (avoids conflicts)
git pull origin main

# 5. Push to GitHub
git push origin main
```

> Tip: if it is your first push of a new branch, use `git push -u origin <branch>`.
> After that, plain `git push` / `git pull` works.

---

## Git: Tags & Releases

Tags mark a version (for example `v1.0.0`). We use [Semantic Versioning](https://semver.org/):
`MAJOR.MINOR.PATCH`.

### Create a tag

```bash
# Annotated tag (recommended)
git tag -a v1.0.0 -m "IRON STORM v1.0.0 - first release"

# See all tags
git tag
git show v1.0.0
```

### Push tags to GitHub

```bash
git push origin v1.0.0     # push one tag
git push origin --tags     # push all tags
```

### Delete a tag (if you made a mistake)

```bash
git tag -d v1.0.0                   # delete locally
git push origin --delete v1.0.0     # delete on GitHub
```

### Make a GitHub Release (optional)

1. Open your repo on GitHub → **Releases** → **Draft a new release**.
2. Choose the tag `v1.0.0`.
3. Add a title and notes → **Publish release**.

---

## First-time upload to GitHub

If this folder is not on GitHub yet:

1. Create a new **empty** repository on <https://github.com/new>
   (do not add a README, `.gitignore` or license there).
2. In this folder run:

```bash
git init                      # skip if a .git folder already exists
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main

# push the tag too
git push origin v1.0.0
```

### Authentication

GitHub no longer accepts account passwords for `git push`. Use one of:

- **Personal Access Token** (Settings → Developer settings → Tokens) as the password, or
- **GitHub CLI**: `gh auth login`, or
- **SSH key**: use `git@github.com:<your-username>/<your-repo>.git` as the remote URL.

---

## Badges (shields.io)

Badges are small images from [shields.io](https://img.shields.io/badge/). Static format:

```markdown
![Label](https://img.shields.io/badge/<label>-<message>-<color>)
```

Example: `https://img.shields.io/badge/version-v1.0.0-blue`

After the repo is on GitHub, you can use **dynamic** badges that read your real tag/release automatically
(replace `<your-username>` and `<your-repo>`):

```markdown
![Latest tag](https://img.shields.io/github/v/tag/<your-username>/<your-repo>)
![Latest release](https://img.shields.io/github/v/release/<your-username>/<your-repo>)
![Stars](https://img.shields.io/github/stars/<your-username>/<your-repo>)
![License](https://img.shields.io/github/license/<your-username>/<your-repo>)
```

> When you create a new tag (for example `v1.1.0`), update the static `version-v1.0.0` badge at the top,
> or switch it to the dynamic `github/v/tag` badge so it updates itself.

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
