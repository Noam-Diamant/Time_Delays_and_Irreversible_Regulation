# Time Delays and Irreversible Regulation (Docker)

## Build

```bash

docker build -t time-delays-artifact:latest .
mkdir -p logs_docker results_docker
```

## Smoke test (abstract benchmark)

```bash

docker run --rm \
  -v "$(pwd)/logs_docker:/app/logs_docker" \
  -v "$(pwd)/results_docker:/app/results_docker" \
  time-delays-artifact:latest \
  ./run_readme_experiments.sh smoke
```

Log: `logs_docker/smoke_abstract.log`  
Results: `results_docker/[id-035]__[var-11]__[in-5]__[BT474-BREAST-CELL-LINE-SHORT-TERM] - abstract/`

## All experiments

```bash

docker run --rm \
  -v "$(pwd)/logs_docker:/app/logs_docker" \
  -v "$(pwd)/results_docker:/app/results_docker" \
  time-delays-artifact:latest
```

Logs: `logs_docker/*.log`  
Results: `results_docker/<benchmark-folder>/`
