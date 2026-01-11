# Cisco Packet Tracer MultiLanguageTranslator　
<img width="1124" height="739" alt="image" src="https://github.com/user-attachments/assets/b943dd7e-dfdd-4f4b-b7d7-3e0f68c3c68f" />

This repository provides a command-line tool and GitHub Actions workflow to:

* Translate Qt Linguist `.ts` files using Azure OpenAI
* Preserve placeholders and XML/HTML tags
* Generate translated `.ts` files
* Compile `.ptl` (Qt binary translation file) using `lrelease`
* Publish results as GitHub Releases

The tool is designed for **software UI localization**, especially for IT / networking products.

## Packet Tracer Installation Resources

You can download Cisco Packet Tracer from the official Cisco Networking Academy resources page:

🔗 **Cisco Packet Tracer download & resources**
[https://www.netacad.com/resources/lab/cisco-packet-tracer-resources](https://www.netacad.com/resources/lab/cisco-packet-tracer-resources)

### How to Install Cisco Packet Tracer

1. Visit the **Cisco Packet Tracer download page** linked above.
2. Log in or sign up for a *Cisco Networking Academy* account.
3. Scroll to your desired platform (Windows / macOS / Linux) and download the installer.
4. Run the installer and follow the on-screen steps to install Packet Tracer on your system.

## Installing and Changing Languages in Packet Tracer

Packet Tracer’s UI uses language files (`.ptl`) that can be added or selected within the software:

### Basic Language Installation / Change

1. Place the `.ptl` language file in the Packet Tracer `languages` folder (inside the Packet Tracer installation directory).
2. Start Packet Tracer.
3. Go to **Options → Preferences** (or `Ctrl+R` / `Cmd+R`).
4. Under the **Languages** list, select your language.
5. Click **Change Language** and restart Packet Tracer to apply. 

> Note: [Article](https://hetare-nw.net/archives/995)

### Creating or Installing Custom Translations

If you want localized UI files not officially distributed:

* Community posts and guides explain how to create or install `.ptl` files by editing the language folder and selecting the new language from Preferences.

## Features

* ✅ Async translation with configurable concurrency
* ✅ Progress reporting and periodic auto-save
* ✅ Retry & timeout handling
* ✅ Technical-term–aware system prompt (avoids literal mistranslation)
* ✅ Qt `.ptl` generation via official Qt tools
* ✅ GitHub Actions workflow with manual execution
* ✅ Outputs both `.ts` and `.ptl` as Release assets

---

## Requirements

### Local execution

* Python **3.11+**
* Azure OpenAI resource
* Qt `lrelease` (Qt Linguist tools)

### GitHub Actions

* No local Qt installation required
  (Qt is installed automatically via `aqtinstall` in the workflow)

---

## Installation (Local)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## Environment Variables

Create a `.env` file or export the following variables:

```env
AZURE_OPENAI_API_KEY=your_api_key
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=your-deployment-name
```

---

## Usage (CLI)

### Basic translation

```bash
python src/main.py template.ts \
  -o template.ja_JP.ts \
  --language ja_JP \
  --target-name Japanese
```

### Translate and generate PTL

```bash
python src/main.py template.ts \
  -o template.ja_JP.ts \
  --ptl-out template.ja_JP.ptl
```

### Advanced options

```bash
python src/main.py template.ts \
  -o template.ja_JP.ts \
  --concurrency 10 \
  --progress-every 50 \
  --save-every 200 \
  --timeout-sec 60 \
  --max-retries 6
```

### Export-only (PTL from existing TS)

```bash
python src/main.py template.ja_JP.ts \
  --export-only \
  --ptl-out template.ja_JP.ptl
```

---

## System Prompt (Translation Rules)

The translator uses a strict system prompt to avoid incorrect literal translations.

Key rules:

* Preserve placeholders exactly (`%1`, `{0}`, `${var}`, etc.)
* Preserve XML/HTML tags
* Do not add explanations
* Output only translated text
* Treat IT / networking terms as technical terms
  (e.g. `Firewall` → `Firewall` / `ファイアウォール`, **never** `火炎`)

---

## GitHub Actions Workflow

This repository includes a workflow that:

* Runs manually (`workflow_dispatch`)
* Installs Qt using `aqtinstall`
* Translates `.ts`
* Generates `.ptl`
* Publishes both files as a GitHub Release

### Required GitHub Secrets

| Name                      | Description           |
| ------------------------- | --------------------- |
| `AZURE_OPENAI_API_KEY`    | Azure OpenAI API key  |
| `AZURE_OPENAI_ENDPOINT`   | Azure OpenAI endpoint |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name       |

No Personal Access Token is required.
`GITHUB_TOKEN` with `contents: write` permission is sufficient.

---

## Output Files

| File                     | Description                    |
| ------------------------ | ------------------------------ |
| `*.ts`                   | Qt Linguist translation source |
| `*.ptl`                  | Qt binary translation file     |
| `*.partial`              | Auto-saved intermediate TS     |
| `translate_failed.jsonl` | Failed translation log         |

---

## Notes

* On Ubuntu 24.04, `lrelease` is **not available via apt**
* The workflow installs official Qt binaries using `aqtinstall`
* `$GITHUB_PATH` is updated correctly across workflow steps
* `.ptl` generation is guaranteed before Release publication

