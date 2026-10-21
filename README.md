# TACAS Artifact: Time Delays and Irreversible Regulation in Boolean Networks

**Paper submission number:** 4490  
**Permanent artifact DOI:** https://doi.org/10.5281/zenodo.23472158

This artifact provides the formal verification and temporal synthesis engine for **cABNs** (context-sensitive / delayed Asynchronous Boolean Networks) with dynamic delays and irreversible regulation, evaluated for TACAS 2027.

## Artifact Badges

We are applying for the following ETAPS Artifact Evaluation badges:
- **Available:** Permanently hosted on Zenodo with a DOI.
- **Functional:** Synthesizes valid dynamic delay configurations and formally proves temporal relationships as described in the paper.
- **Reusable:** Modular, accepts `.bnet` and JSON observations, and runs natively via `uv` as well as inside the offline TACAS VM environment.

---

## 1. Environment & Setup (Virtual Machine / Local)

The artifact is designed to run in a Python 3.10+ environment using [`uv`](https://docs.astral.sh/uv/) (or standard `python3` / `venv`).

### Quick Setup with `uv`

1. **Create and activate the virtual environment:**
   - **Linux / macOS / TACAS VM:**
     ```bash
     uv venv
     source .venv/bin/activate
     ```
   - **Windows (PowerShell):**
     ```powershell
     uv venv
     .venv\Scripts\activate
     ```

2. **Install dependencies:**
   - **Offline / Pre-bundled wheel (inside VM `packages/` directory):**
     ```bash
     uv pip install packages/z3_solver-4.15.4.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
     ```
   - **Online (via PyPI):**
     ```bash
     uv pip install z3-solver
     ```

---

## 2. Directory Structure

```text
TACAS_Artifact/
├── benchmarks/                    # Benchmark models (.bnet, observations .json, config .json)
│   ├── [id-015]__[var-14].../     # Neurotransmitter Signaling Pathway
│   ├── [id-035]__[var-11].../     # BT474 Breast Cell Line (Full)
│   ├── [id-035]... - abstract/    # BT474 Breast Cell Line (Abstract / Quick benchmark)
│   ├── [id-111]__[var-18].../     # Apoptosis
│   ├── [id-133]__[var-8].../      # Root Stem Cell
│   ├── [id-230]__[var-50].../     # Hepatocyte Growth Factor
│   └── Sea Urchin Embryo/         # Sea Urchin Embryo gene regulatory network
├── packages/                      # Pre-downloaded wheels for offline VM evaluation
├── results/                       # Generated outputs, trajectories, and proven relationships
├── src/
│   └── parallel_run_AllUpdateFuncs_varrying_delays.py   # Primary synthesis & analysis engine
└── README.md
```

---

## 3. How to Run the Experiments

Make sure your virtual environment is activated before running.

### A. Quick Smoke Test (Estimated runtime: < 1 second)
To verify solver bindings and execution pipeline:
```bash
python src/parallel_run_AllUpdateFuncs_varrying_delays.py --model_name "abstract"
```
**Expected Output:** Outputs `Executing Dynamic Delay Search`, extracts satisfying models, and creates output files in `results/[id-035]__[var-11]__[in-5]__[BT474-BREAST-CELL-LINE-SHORT-TERM] - abstract/`.

---

### B. Reproducing Paper Results

#### 1. Temporal Relationships & Proof Engine (Table 1)
Run the benchmark models from Table 1 to extract satisfying delay permutations and formally verify universal temporal rules:

- **Root Stem Cell 2010 (`id-133`):**
  ```bash
  python src/parallel_run_AllUpdateFuncs_varrying_delays.py --model_name "id-133"
  ```
- **Neurotransmitter Signaling Pathway (`id-015`):**
  ```bash
  python src/parallel_run_AllUpdateFuncs_varrying_delays.py --model_name "id-015"
  ```
- **Apoptosis (`id-111`):**
  ```bash
  python src/parallel_run_AllUpdateFuncs_varrying_delays.py --model_name "id-111"
  ```

**Verification:** Check `results/<model_folder>/Relationships.txt` to verify the proven ordering rules (e.g., relative synchrony constraints) corresponding to Table 1.

#### 2. Virtual-Edge Experiment (Section 7.4)
Demonstrates synthesis over unobserved intermediate components by comparing full and abstracted formulations:

- **Original BT474 Model:**
  ```bash
  python src/parallel_run_AllUpdateFuncs_varrying_delays.py --model_name "id-035" --exact_model_name
  ```
- **Abstracted Model (Virtual Edges):**
  ```bash
  python src/parallel_run_AllUpdateFuncs_varrying_delays.py --model_name "abstract"
  ```

**Verification:** Compare `delay_permutations_non_constant.json` and `Relationships.txt` between both output folders in `results/` to observe composite delay bounds.

#### 3. Sea Urchin Gene Regulatory Network (Section 7.5)
Runs the comprehensive developmental network to test inconsistency detection:
```bash
python src/parallel_run_AllUpdateFuncs_varrying_delays.py --model_name "Sea Urchin"
```
**Expected Output:** The solver outputs `UNSAT` (unsatisfiable). As stated in Section 7.5, this is the **expected result**, proving that the network model, delay bounds, and observation trajectory are mathematically inconsistent.

---

### C. Batch Execution
To process all models in `benchmarks/` sequentially:
```bash
python src/parallel_run_AllUpdateFuncs_varrying_delays.py --models_dir benchmarks --results_dir results
```

---

## 4. CLI Arguments Reference

| Argument | Default | Description |
|---|---|---|
| `--models_dir` | `benchmarks` | Root folder containing benchmark subfolders. |
| `--model_name` | `None` | Substring filter to target a specific benchmark folder. |
| `--exact_model_name` | `False` | Require `--model_name` to match folder name exactly. |
| `--model_file` | `model.bnet` | Name of the Boolean network definition file in each folder. |
| `--config_file` | `config.json` | Path or name of delay configuration file. |
| `--results_dir` | `results` | Directory where synthesized trajectories and proofs are saved. |

---

## 5. Artifact Outputs & Evaluation Results

For each evaluated benchmark, outputs are saved to `results/<model_folder_name>/`:

- **`delay_permutations_non_constant.json`**: Synthesized dynamic delay configurations satisfying temporal observations.
- **`trajectories_non_constant.txt`**: Complete global execution trajectories across all time steps and active gene states.
- **`Relationships.txt`**: Proven universal delay ordering relationships across all valid trajectories (e.g., `edge_A MUST ALWAYS BE GREATER THAN edge_B`).