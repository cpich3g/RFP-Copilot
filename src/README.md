# Streamlit Experience

The Streamlit front end exposes three primary workspaces from the navigation pane:

1. **Bid Comparison Intelligence** (`pages/1_Bid_Comparison.py`)
   - Upload one or more supplier bid files (CSV/XLSX/JSON).
   - Optionally upload an RFP anchor file to seed target prices or SLA thresholds.
   - Adjust weighting sliders to prioritise price, quality, compliance, sustainability, and more.
   - Inspect the normalised comparison table, Plotly score visualisations, and agent-generated summary.
   - Explore alternative scenarios in the What-if Sandbox; every run is logged for later export.
   - Download a bundled ZIP containing Markdown, PDF, and CSV artefacts.

2. **Negotiation Strategy Copilot** (`pages/2_Negotiation_Strategy.py`)
   - Select a supplier from history or upload a JSON profile describing capabilities and prior lessons.
   - Pull stubbed market benchmarks (replace with a live integration when ready).
   - Capture objectives and constraints (target price, SLA, warranty, penalties, and more).
   - Generate an AI pre-brief leveraging Microsoft Agent Framework for synthesised insights.
   - Run a live negotiation copilot with chat-style updates and optional voice capture via WebRTC.
   - Log outcomes, concessions, and lessons learned to evolve future strategies.

3. **Multi-Agent Analysis Chat** (`pages/chat.py`)
   - Continues to provide the orchestrated multi-agent conversation driven by summarised RFP/proposal insights.
   - Automatically evaluates every uploaded vendor proposal, captures each agent’s findings, and produces a ranked comparison with a recommended winner.
   - Agent replies now stream into the chat UI so analysts can follow reasoning in real time.

## Azure OpenAI Authentication

By default the application now authenticates to Azure OpenAI using `DefaultAzureCredential`, which enables Managed Identity or Azure CLI sign-ins without storing secrets. If a token cannot be acquired, the app automatically falls back to `AZURE_OPENAI_API_KEY` (when provided). To force API-key based authentication in all cases, set `AZURE_OPENAI_AUTH_MODE=api_key` alongside `AZURE_OPENAI_API_KEY`.

## Settings Drawer

All pages share a consistent drawer on the left-hand sidebar for global settings (LLM provider, telemetry, theme). Page-specific toggles (for example, outlier handling in bid comparison and voice enablement during negotiation) live beneath the shared controls.

## Voice Capture

When enabled on the negotiation page, a `streamlit-webrtc` session captures audio in push-to-talk mode. Integrate Azure Cognitive Services Speech (credentials already supported by `requirements.txt`) to transform captured audio into text and append it to the live transcript.

## Docker & GitHub Container Registry (GHCR)

This project includes a Dockerfile and a GitHub Actions workflow to automatically build and publish the container image to GitHub Container Registry.

### Local Docker Build

To build and run the container locally:

1. Navigate to the `src` directory:

   ```bash
   cd src
   ```

2. Build the image:

   ```bash
   docker build -t rfp-copilot .
   ```

3. Run the container (ensure you have a `.env` file in `src/` or pass environment variables):

   ```bash
   docker run -p 8501:8501 --env-file .env rfp-copilot
   ```

### GitHub Actions Workflow

The workflow is defined in `.github/workflows/docker-publish.yml`. It triggers on:

- Pushes to the `main` branch.
- Creation of tags starting with `v*` (e.g., `v1.0.0`).
- Pull requests to `main` (builds but does not push).

To enable this:

1. Ensure GitHub Actions is enabled in your repository settings.
2. The workflow uses `GITHUB_TOKEN` to authenticate with GHCR, so no extra secrets are needed for the registry.
3. If your `agent-framework` dependency is in a private feed, you may need to update the Dockerfile and workflow to authenticate with that feed.

### Using the Image

#### 1. Run Locally with Docker

To run the image you just pushed (or pulled from GHCR) locally:

1. **Authenticate** (if you haven't already):

   ```powershell
   docker login ghcr.io -u <your-github-username>
   ```

2. **Run the container**:
   Make sure you have your `.env` file ready in the `src` folder.

   ```powershell
   docker run -p 8501:8501 --env-file src/.env ghcr.io/cpich3g/rfp-copilot:latest
   ```

   Access the app at `http://localhost:8501`.

#### 2. Deploy to Azure Container Apps (ACA)

You can deploy this image directly to Azure Container Apps.

##### Option A: Using Azure CLI (Quickest)

1. **Create a Resource Group** (if needed):

   ```powershell
   az group create --name rfp-copilot-rg --location eastus
   ```

2. **Create the Container App**:
   Replace `<GITHUB_PAT>` with your GitHub Personal Access Token (must have `read:packages` scope).

   ```powershell
   az containerapp up `
     --name rfp-copilot `
     --resource-group rfp-copilot-rg `
     --image ghcr.io/cpich3g/rfp-copilot:latest `
     --ingress external `
     --target-port 8501 `
     --registry-server ghcr.io `
     --registry-username cpich3g `
     --registry-password <GITHUB_PAT> `
     --env-vars AZURE_OPENAI_API_KEY=... AZURE_OPENAI_ENDPOINT=...
   ```

   *Note: Pass all required environment variables from your `.env` file using the `--env-vars` flag (space-separated `KEY=VALUE`).*

##### Option B: Using the `infra/` Bicep files (Infrastructure as Code)

Your project is already set up with `azd` (Azure Developer CLI) structure. By default, `azd up` builds the code from source. To use your GHCR image instead:

1. Modify `azure.yaml` to point to the image instead of the Dockerfile (optional, if you want `azd` to manage it).
2. Or, manually update the deployment to pull from GHCR by configuring the container registry secrets in the Azure Portal after deployment.
