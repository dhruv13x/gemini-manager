# GM AI Automation Tool

<div align="center">
  <img src="https://raw.githubusercontent.com/dhruv13x/gemini-manager/main/gemini-manager_logo.png" alt="gemini-manager logo" width="200"/>
</div>

<div align="center">

[![Build status](https://github.com/dhruv13x/gemini-manager/actions/workflows/publish.yml/badge.svg)](https://github.com/dhruv13x/gemini-manager/actions/workflows/publish.yml)
[![PyPI version](https://img.shields.io/pypi/v/gemini-manager.svg)](https://pypi.org/project/gemini-manager/)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/badge/linting-ruff-yellow.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Maintenance](https://img.shields.io/badge/maintenance-active-green.svg)](https://github.com/dhruv13x/gemini-manager/graphs/commit-activity)

</div>

**The Swiss Army Knife for GM AI Automation - Backups, Cloud Sync, and Account Management.**

`gemini-manager` is a powerful, "batteries-included" command-line interface designed to supercharge your GM AI experience. It handles backups (Local, S3, B2), synchronizes data across devices, manages multiple profiles, and intelligently tracks account usage to bypass rate limits.

---

## 2. ⚡ Quick Start (The "5-Minute Rule")

### Prerequisites
- **Python**: 3.8 or higher. (Compatible up to 3.13)
- **Optional**: Docker, [AWS CLI](https://aws.amazon.com/cli/), or [Backblaze B2 CLI](https://www.backblaze.com/b2/docs/quick_command_line.html) for credentials management.

### Install

We recommend using `uv` for fast, reproducible installs, but standard `pip` works too.

```bash
# Install from PyPI
uv pip install gemini-manager  # or pip install gemini-manager

# Or install from source
uv pip install .  # or pip install .
```

### Run

Get up and running immediately. Copy and paste this to initialize and use the tool:

```bash
# 1. Run the interactive setup wizard
gm config --init

# 2. Run your first local backup
gm backup

# 3. Push your backup to the cloud
gm sync push

# 4. Check the account dashboard
gm cooldown --cloud

# 5. Get a smart account recommendation
gm recommend
```

---

## 3. ✨ Features (The "Why")

### Core Capabilities
*   **🛡️ God Level Backups**: Securely backup your configuration and chat history to **Local**, **AWS S3**, or **Backblaze B2** storage. Supports **GPG Encryption** for sensitive data.
*   **🌍 Machine-Time Adaptive**: Automatically detects and uses your system's local timezone for all calculations and displays. No more manual IST/UTC conversions.
*   **☁️ Unified Cloud Sync**: Seamlessly `push` and `pull` backups between your local machine and the cloud.
*   **💬 Chat History Management**: Backup, restore, resume, and clean up temporary chat history with precision.

### Smart Automation
*   **⏱️ Smart Session Tracking**: Tracks "First Used" timestamps to accurately predict GM's 24-hour rolling quota resets.
*   **🧠 Intelligent Rotation**: Automatically recommends the "healthiest" account based on session start times and Least Recently Used (LRU) logic.
*   **🛡️ Accident Protection**: Safeguards your session data by preventing accidental account switches from resetting your 24-hour quota clock.

### Diagnostics & Management
*   **📊 Visual Analytics**: View beautiful, terminal-based bar charts of your usage history and account health (over the last 7 days).
*   **🩺 Doctor Mode**: Built-in diagnostic tool to validate your environment, dependencies, and configuration health.
*   **🧹 Auto-Pruning**: Automatically cleans up old backups and temporary files to keep your storage efficient.
*   **👥 Profile Management**: Export and import entire user profiles and their corresponding settings.

---

## 4. 🛠️ Configuration (The "How")

You can configure `gemini-manager` using **Environment Variables**, **CLI Arguments**, or the **Interactive Config** (`gm config --init`).

**Priority Order**: CLI Arguments > Environment Variables > `.env` / Doppler > Saved Config (`~/.gemini-manager/settings.json`)

### Environment Variables

| Name | Description | Default | Required |
| :--- | :--- | :--- | :--- |
| `GEMINI_AWS_ACCESS_KEY_ID` | AWS Access Key ID for S3. | None | No (for S3) |
| `GEMINI_AWS_SECRET_ACCESS_KEY` | AWS Secret Access Key for S3. | None | No (for S3) |
| `GEMINI_S3_BUCKET` | AWS S3 Bucket Name. | None | No (for S3) |
| `GEMINI_S3_REGION` | AWS Region. | `us-east-1` | No |
| `GEMINI_B2_KEY_ID` | Backblaze B2 Application Key ID. | None | No (for B2) |
| `GEMINI_B2_APP_KEY` | Backblaze B2 Application Key. | None | No (for B2) |
| `GEMINI_B2_BUCKET` | Backblaze B2 Bucket Name. | None | No (for B2) |
| `GEMINI_BACKUP_PASSWORD` | Password for GPG encryption. | None | No (for `--encrypt`) |
| `DOPPLER_TOKEN` | Token for Doppler secrets management. | None | No |

### CLI Arguments

Below are some of the most powerful and common CLI flags available. Run `gm --help` or `gm <command> --help` for a full list.

| Flag / Command | Description |
| :--- | :--- |
| `gm backup --encrypt` | Encrypt the backup archive using GPG. |
| `gm restore --auto` | Automatically select and restore the latest backup for the best available account. |
| `gm prune --cloud-only` | Only remove old backups from cloud storage, keeping local copies. |
| `gm cooldown --reset-all` | **DANGER**: Wipe all cooldown data (local and cloud). |
| `gm --profile <name>` | Specify a configuration profile to use (e.g., work, personal). |
| `gm check-integrity` | Verify integrity of current configuration against the latest backup. |

---

## 5. 🏗️ Architecture

The `gemini-manager` is built with modularity and extensibility in mind.

```text
src/gemini_manager/
├── cli.py             # 🚀 Entry Point & Argument Routing
├── config.py          # ⚙️ Global Constants & Paths
├── backup.py          # 📦 Backup Logic (Local & Cloud dispatch)
├── restore.py         # ♻️ Restore Logic (Auto-selection & Session logs)
├── cooldown.py        # ❄️ Master Dashboard & Adaptive Time Logic
├── recommend.py       # 🧠 Recommendation Engine (Session-aware)
├── sync.py            # 🔄 Unified Sync (Push/Pull)
├── cloud_factory.py   # ☁️ Cloud Provider Abstract Factory
├── stats.py           # 📊 Visualization Module
├── chat.py            # 💬 Chat management and restoration
└── profile.py         # 👥 Configuration profiles
```

### Flow
1.  **User Input**: CLI args are parsed by `args.py` and routed by `cli.py`.
2.  **Configuration**: Settings are loaded from `settings_cli.py` (merging Env, CLI, Doppler, and Config).
3.  **Action**:
    - **Backup**: Compresses `~/.gemini-manager`, encrypts (optional), and uploads via `CloudFactory`.
    - **Restore**: Fetches list from cloud/local, decrypts, and extracts to `~/.gemini-manager`.
    - **Recommendation**: Queries `cooldown.py` for account status and selects the LRU "Ready" account.
4.  **Persistence**: Usage stats and cooldowns are saved to JSON files in `~/.gemini-manager`.

---

## 6. 🐞 Troubleshooting (New in V3)

| Error Message | Possible Cause | Solution |
| :--- | :--- | :--- |
| `ModuleNotFoundError: No module named 'gemini_manager'` | Installation issue. | Run `uv pip install -e .` or ensure you are in the correct venv. |
| `gpg: decryption failed: No secret key` | Missing GPG key or wrong password. | Ensure `GEMINI_BACKUP_PASSWORD` is set or the GPG key is imported. |
| `ClientError: An error occurred (403) ...` | AWS/B2 Credentials invalid. | Check your `GEMINI_*` env vars, `.env`, or Doppler secrets. |
| `Permission denied: '~/.gemini-manager'` | File permission issues. | Run `chown -R $USER ~/.gemini-manager` or check directory permissions. |
| `[WARN] Found DOPPLER_TOKEN but failed to fetch secrets` | Network or Invalid Token. | Check network connectivity and verify `DOPPLER_TOKEN` validity. |

**Debug Mode**: Currently, you can increase verbosity by inspecting the logs or running with standard python tracebacks enabled (default).

---

## 7. 🤝 Contributing

We welcome contributions! Whether it's reporting a bug, suggesting a feature, or writing code.

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed instructions.

1.  **Setup Dev Environment**: `uv pip install -e .[dev]`
2.  **Run Tests**: `uv run pytest tests/`
3.  **Lint Code**: `uv run ruff check src`
4.  **Submit PR**: Follow the guidelines in the contributing guide.

---

## 8. 🗺️ Roadmap

*   **Phase 1 (Completed)**: Core Backup/Restore, Multi-Cloud (S3/B2), Sync, Auto-Updates.
*   **Phase 2 (Completed)**: Machine-Time Adaptation, Session Tracking, Smart Rotation.
*   **Phase 3 (Upcoming)**:
    *   🔔 **Webhooks**: Slack/Discord notifications for backup status.
    *   🐍 **Python SDK**: Import `gemini_manager` as a library in your own scripts.
*   **Phase 4 (Vision)**: AI-driven anomaly detection and self-healing infrastructure.

See [ROADMAP.md](ROADMAP.md) for the full detailed vision.
