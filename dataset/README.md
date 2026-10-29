# TraceGuard – Dataset & Training Pipeline

## Quick Start

### Prerequisites
- Python 3.10+ with Anaconda/Miniconda
- NVIDIA GPU with 4+ GB VRAM (for GPU training) — *CPU also works*
- CUDA-compatible drivers ([check with `nvidia-smi`](https://developer.nvidia.com/cuda-downloads))

### 1. Set Up the Environment

```bash
# Create conda environment (if not already done)
conda create -n dl python=3.11 -y
conda activate dl

# Install dependencies
pip install -r requirements-gpu.txt

# Install PyTorch with CUDA (separately — ~2.5 GB download)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# Verify GPU access
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

> **Note:** If you have an older NVIDIA driver, replace `cu128` with `cu124` or `cu121`.  
> For CPU-only, just run `pip install torch torchvision torchaudio` (no `--index-url`).

---

### 2. Prepare the Datasets

Place these files in the `dataset/` folder:

| File | Source | Size |
|------|--------|------|
| `CEAS_08.csv` | [Kaggle Phishing Email Dataset](https://www.kaggle.com/datasets/naserabdullahalam/phishing-email-dataset) | ~65 MB |
| `Enron.csv` | Same Kaggle dataset | ~44 MB |
| `Ling.csv` | Same Kaggle dataset | ~9 MB |
| `Nazario.csv` | Same Kaggle dataset | ~7 MB |
| `Nigerian_Fraud.csv` | Same Kaggle dataset | ~9 MB |
| `SpamAssasin.csv` | Same Kaggle dataset | ~14 MB |
| `phishing_email.csv` | Same Kaggle dataset (aggregate — auto-skipped) | ~102 MB |
| `rba_synthetic_100.csv` | RBA login data (synthetic sample) | ~25 KB |
| `firehol_level1.netset` | [FireHOL IP Lists](https://iplists.firehol.org/) | ~72 KB |
| `firehol_level2.netset` | Same FireHOL source | ~340 KB |

---

### 3. Run Preprocessing

```bash
conda activate dl
cd dataset
python run_preprocess.py
```

This runs all three pipelines (FireHOL → Emails → RBA) and outputs to `dataset/processed/`:

| Output | Purpose |
|--------|---------|
| `emails_train.csv` | Training set (54,870 rows, ~50/50 balance) |
| `emails_val.csv` | Validation set (6,859 rows) |
| `emails_test_in_distribution.csv` | In-distribution test (6,859 rows) |
| `emails_test_cross_source.csv` | Cross-source hold-out test (5,678 rows, SpamAssasin) |
| `emails_report.json` | Full preprocessing report |
| `threat_ranges.csv` | Merged FireHOL IP threat ranges (~28K ranges) |
| `threat_ranges_meta.json` | Threat list metadata |
| `rba_logins.csv.gz` | Cleaned RBA login data |
| `rba_report.json` | RBA blind-spot report |

**Run individual steps:**
```bash
python run_preprocess.py                    # all three
python Preprocess.py --steps emails         # emails only
python Preprocess.py --steps firehol        # threat lists only
python Preprocess.py --steps rba            # logins only
```

---

### 4. Train the Model

#### Option A: GPU Training (DistilBERT) — Recommended
```bash
conda activate dl
python train_gpu.py
```

- Fine-tunes **DistilBERT** on the preprocessed email data
- Optimised for **4 GB VRAM** (batch=8, FP16, gradient accumulation)
- Takes ~15-30 minutes on an RTX 3050
- Saves model to `backend/models/distilbert_phish/`

#### Option B: CPU Training (TF-IDF + Logistic Regression) — Fast
```bash
cd ../backend
python scripts/train_text_model.py --dir ../dataset/processed --holdout-file emails_test_cross_source.csv
```

- Trains in ~20 seconds
- Good baseline, fully interpretable
- Saves to `backend/models/text_model.joblib`

Both options save a **backend-compatible model** that works with the existing `get_model().predict()` API.

---

### 5. Verify

```bash
# Check the metrics
cat backend/models/metrics.json

# Run the backend tests
cd backend
pytest tests/ -v
```

---

## Project Structure

```
NPC-TraceGuard/
├── dataset/
│   ├── *.csv, *.netset          # Raw data files
│   ├── Preprocess.py            # Main preprocessing script
│   ├── run_preprocess.py        # One-click runner (handles folder layout)
│   ├── train_gpu.py             # GPU training script (DistilBERT)
│   ├── requirements-gpu.txt     # Python dependencies
│   └── processed/               # Preprocessed outputs (generated)
├── backend/
│   ├── app/engine/text_model.py # Model interface (predict/top_terms)
│   ├── scripts/train_text_model.py  # CPU training script
│   └── models/                  # Saved models & metrics
├── frontend/                    # React + Vite UI
└── README.md
```

## Important Notes

- **No data leakage:** Duplicates are removed across all sources before splitting. The cross-source test (SpamAssasin) is the most credible metric.
- **Same cleaning in production:** The `visible_text()` and `normalise()` functions from `Preprocess.py` must be applied before scoring in production.
- **Label meaning:** Label 1 = phishing/spam/fraud as labelled by dataset authors. Not all are phishing — some are spam (SpamAssasin) or fraud (Nigerian_Fraud).
- **FireHOL refresh:** Re-download and re-run periodically — threat IPs change daily.
- **RBA data:** The included `rba_synthetic_100.csv` is a 100-row sample. For the full dataset (~31M rows), use `--rba-max-rows 1500000`.

