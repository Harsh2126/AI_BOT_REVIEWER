# GitHub PR Code Review Bot 🤖

Automatically reviews Pull Requests using **Claude claude-sonnet-4-20250514** and posts inline comments + a summary directly on the PR.

## How It Works

```
PR opened / updated
       │
       ▼
GitHub Actions triggers workflow
       │
       ▼
pr_review_bot.py fetches the PR diff via PyGithub
       │
       ▼
Diff is sent to Claude (claude-sonnet-4-20250514)
       │
       ▼
Claude returns JSON: { summary, inline_comments[] }
       │
       ▼
Bot posts a PR Review with inline comments on GitHub
```

## Setup

### 1. Add the Anthropic API Key secret

In your GitHub repository go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name         | Value                          |
|---------------------|--------------------------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key         |

> `GITHUB_TOKEN` is provided automatically by GitHub Actions — no setup needed.

### 2. Copy the files into your repository

```
your-repo/
├── pr_review_bot.py
├── requirements.txt
└── .github/
    └── workflows/
        └── pr-review.yml
```

### 3. Push and open a PR

The bot triggers automatically on every PR `opened`, `synchronize` (new commits pushed), or `reopened` event.

## Configuration

| Constant in `pr_review_bot.py` | Default | Description |
|-------------------------------|---------|-------------|
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Claude model to use |
| `MAX_DIFF_CHARS` | `50000` | Max diff size sent to Claude |

## Output Example

The bot posts a single PR review that looks like:

> **🤖 Claude Code Review**
>
> This PR adds a user authentication module. The overall structure is solid, but there are two security concerns worth addressing before merging.
>
> *(inline comment on `auth.py` line 42)*: Passwords are being logged in plain text. Remove this log statement or hash the value before logging.

## Requirements

- Python 3.11+
- `PyGithub==2.3.0`
- `anthropic==0.28.0`
