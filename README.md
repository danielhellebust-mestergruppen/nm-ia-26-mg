# NM i AI 2026 - Master Workspace

Welcome to the central monorepo for the NM i AI 2026 competitions. This repository is configured to provide an interactive, reproducible, and end-to-end framework for all three primary tasks:

1.  **NorgesGruppen Data Object Detection & Classification**
2.  **Tripletex AI Accounting Agent**
3.  **Astar Island Norse World Prediction**

A single orchestrator script (`run.py`) manages dependencies, triggers workflows, and trains models across all three projects to ensure standardized, reproducible results.

---

## 🚀 Quick Start

### 1. Prerequisites
Before getting started, ensure you have the following installed on your system:
*   **Python 3.10+** (Recommended: 3.12)
*   [Git](https://git-scm.com/)
*   (Optional but recommended) A dedicated Python virtual environment.

### 2. Setup the Workspace
Clone this repository and set up your Python environment:

```bash
# Clone the repository
git clone <your-repo-url>
cd nm-i-ai-26-mg

# Create and activate a virtual environment (Windows)
python -m venv .venv
.venv\Scripts\activate

# Or on macOS/Linux:
# python3 -m venv .venv
# source .venv/bin/activate
```

### 3. Run the Orchestrator
To avoid manually running scripts from different folders, this repository uses a central interactive CLI:

```bash
python run.py
```
This script acts as the command center for the entire workspace. It automatically checks and installs project-specific dependencies (`ultralytics`, `fastapi`, `numpy`, etc.) only when you trigger a workflow that requires them.

---

## 🛠️ Project Configuration & Usage

### 🛒 NorgesGruppen (Object Detection & Classification)
*Located in `src/NorgesGruppen_Data_Object_Detection`*

This pipeline uses YOLOv8 to detect products on shelves and subsequently classify them.

**Reproducing Results via `run.py`:**
1.  **Step 1: Download Datasets:** Merges the Kaggle `sku-110k` dataset with internal NorgesGruppen data to create an 80/10/10 split.
    *   *Note: Ensure your `KAGGLE_USERNAME` and `KAGGLE_KEY` environment variables are set to authenticate the download.*
2.  **Step 2: Download Pre-Trained Models:** Optionally download the current State-of-the-Art weights (submission_v9) directly from Hugging Face if you wish to skip training.
3.  **Steps 3 & 4: Train Models:** Prompts you for the desired YOLO architecture size (Nano, Small, Medium, Large, X-Large), epochs, and image sizes, and begins training.
4.  **Step 5: Validate Models:** Tests your `best.pt` weights against the validation set and outputs metrics (mAP50-95 and Top-1 Accuracy).
5.  **Step 6: Create Submission Zip:** Exports the PyTorch `.pt` models to optimized `.onnx` formats and bundles them alongside the runner scripts into a `submission.zip` file, ready for grading.

---

### 💼 Tripletex AI Accounting Agent
*Located in `src/Tripletex_AI_Accounting_Agent`*

An autonomous AI agent designed to ingest, classify, and extract metadata from incoming financial documents (receipts, invoices, etc.) using LLMs and traditional parsing.

**Reproducing Results via `run.py`:**
1.  Select **Run Tripletex AI Accounting Agent (FastAPI)** from the main menu.
2.  The script will verify requirements and boot up the local Uvicorn development server on `http://0.0.0.0:8000`.
3.  *Note:* The agent relies on external APIs (like Gemini or OpenAI). Ensure you configure your API keys by renaming `config.py.example` to `config.py` (if applicable) or exporting the required environment variables.

---

### 🗺️ Astar Island Norse World Prediction
*Located in `src/Astar_Island_Norse_World_Prediction`*

A sophisticated geospatial machine-learning pipeline that uses a Socio-Economic Attention U-Net to predict unrevealed land classifications in a competitive, grid-based environment.

**Reproducing Results via `run.py`:**
1.  Select **Run Astar Island Prediction Lab** from the main menu.
2.  You will be presented with an Astar-specific submenu:
    *   **Backfill Completed Rounds / Replays:** Fetches historical API data to build the training dataset.
    *   **Train Socio-UNet Predictor:** Re-trains the current SOTA U-Net architecture on the downloaded data.
    *   **Simulate Queries (TUI):** Launches an interactive Terminal UI to visualize the predictor's confidence maps and attention gates locally.
    *   **Run Active Round (Two Stage Workflow):** Connects to the live API, computes the optimal query allocation, requests data, and submits the final predictions for the current active round.
3.  *Authentication:* Running live API requests requires the API token. You must set the `AINM_BEARER_TOKEN` environment variable before executing the workflow.

---

## 🔒 Security & Best Practices
*   **API Keys:** Never commit `.env` files, API keys, Hugging Face tokens, or Kaggle credentials. Always set them via your shell environment (`export HF_TOKEN=...` or `$env:HF_TOKEN="..."`).
*   **Virtual Environments:** Always use a `.venv` to prevent dependency conflicts between `ultralytics` (PyTorch) and the FastAPI/Astar pipelines.
*   **Data Storage:** Downloaded datasets and generated `.pt`/`.onnx` files are automatically `.gitignore`'d to keep the repository clean.

## 🤝 Need Help?
If you encounter missing dependencies that the orchestrator failed to catch, manually install them from the respective project folder:
```bash
pip install -r src/<Project_Folder>/requirements.txt
```