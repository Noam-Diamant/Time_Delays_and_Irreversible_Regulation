# TACAS Artifact

Artifact evaluation code for time delays and irreversible regulation in Boolean network models.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed (Python package and environment manager)

## Setup

1. **Create virtual environment:**
   ```powershell
   uv venv
   ```

2. **Activate the environment:**
   - **Windows (PowerShell):**
     ```powershell
     .venv\Scripts\activate
     ```
   - **Linux / macOS:**
     ```bash
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```powershell
   uv pip install z3-solver
   ```

## Running

With the environment activated:

```powershell
python src/parallel_run_AllUpdateFuncs_varrying_delays.py --model_name "abstract" --models_dir benchmarks --results_dir results
```

## Results

Output files will be generated under the `results/` folder:
- `delay_permutations_non_constant.json`
- `trajectories_non_constant.txt`
- `Relationships.txt`
