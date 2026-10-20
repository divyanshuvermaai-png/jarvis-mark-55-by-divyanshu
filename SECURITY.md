# Security Policy — JARVIS Mark 55

**Project:** JARVIS Mark 55 (Mark-LV)  
**Creator & Maintainer:** Divyanshu Verma ([Divyanshu Industries](https://github.com/divyanshuvermaai-png))  
**Contact:** [divyanshuverma.ai@gmail.com](mailto:divyanshuverma.ai@gmail.com)  

---

## 1. Reporting a Vulnerability

If you discover a security vulnerability or potential exploit in JARVIS Mark 55, please report it **privately and responsibly**. Do not disclose vulnerabilities in public GitHub issues, discussions, pull requests, or social media channels until the maintainer has had a reasonable opportunity to review and address the issue.

### Preferred Reporting Channels:
1. **GitHub Private Security Advisory:**  
   Submit a private advisory via [GitHub Security Advisories](https://github.com/divyanshuvermaai-png/jarvis-mark-55-by-divyanshu/security/advisories) (if enabled for the repository).
2. **Direct Email:**  
   Send an encrypted or direct email to **[divyanshuverma.ai@gmail.com](mailto:divyanshuverma.ai@gmail.com)** with the subject line:  
   `[SECURITY VULNERABILITY] JARVIS Mark 55 — <Brief Summary>`

### What to Include in Your Report:
- A clear description of the vulnerability and its potential impact.
- Step-by-step reproduction instructions or a minimal proof-of-concept (PoC).
- The affected component (e.g., `actions/`, `core/`, `dashboard/`, `plugins/`, or configuration parser).
- The operating system and Python version where the issue was observed.
- Any proposed remediation or mitigation steps.

---

## 2. Confidentiality & Sensitive Information Warning

When reporting an issue or filing bug reports:
- **Never include real API keys, OAuth tokens, passwords, session tokens, or personal credentials.**
- **Never paste personal memory files (`memory/long_term.json`), chat transcripts containing private data, or unredacted screenshots.**
- If providing configuration or logs, sanitize all secrets, file paths containing usernames, and personal identifiers before transmission.

---

## 3. Scope of Security Coverage

JARVIS Mark 55 is an autonomous desktop environment that interacts with system APIs, processes, external AI providers, and local filesystems. Security considerations and reportable areas include:

- **Local Computer Control & Execution:** Execution safeguards in `actions/computer_control.py`, `actions/desktop.py`, and `actions/file_controller.py`.
- **Destructive Action Protections:** Verification and bypass vulnerabilities in the confirmation dialog (`core/confirm.py`).
- **Remote Web Dashboard:** Authentication, TLS configuration, token handling, and websocket security in `dashboard/server.py`.
- **Browser Automation:** Unintended execution or privilege abuse in `actions/browser_control.py` via Playwright.
- **Plugin Sandboxing & MCP Bridges:** Potential code injection or unauthorized tool invocation in `plugins/` and `core/action_loader.py`.
- **Configuration & Secrets Handling:** Storage and handling of API keys in `config/api_keys.json` and memory persistence.

### Out of Scope:
- Attacks requiring physical access to an unlocked host machine.
- Vulnerabilities in third-party services or APIs (e.g., Google Gemini API, Groq Cloud API, Telegram API) beyond the control of this client.
- Malicious modifications made to user-created custom plugins or third-party unvetted code dropped into `plugins/`.
- Social engineering or phishing targeting end users.

---

## 4. Response & Remediation Expectations

JARVIS Mark 55 is an independently developed project by Divyanshu Verma. While reported security issues are taken seriously and prioritized for review:
- **No strict response-time SLA or resolution timeline is guaranteed.**
- There is currently no paid bug-bounty program or monetary compensation for vulnerability disclosures.
- Vulnerability reports will be investigated, verified, and patched on a best-effort basis in subsequent updates.
- Credit and acknowledgement will gladly be provided in release notes and documentation upon request once a fix has landed.

Thank you for helping keep JARVIS Mark 55 and its users safe.
