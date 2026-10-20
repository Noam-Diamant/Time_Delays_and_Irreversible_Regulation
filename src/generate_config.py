import os
import re
import json
import random
import argparse

# ==============================================================================
# RANDOMIZATION PARAMETERS
# ==============================================================================
MAX_DELAY = 3               # Maximum possible delay bound (e.g., d_max can go up to 3)
PROB_INDEFINITE = 0.2       # 20% chance an edge is flagged as "definite": false
PROB_IRREVERSIBLE = 0.1     # 10% chance an edge is flagged as "irreversible": true

def parse_and_generate(models_dir, model_file="model.bnet"):
    print(f"Scanning directory: {models_dir} for {model_file}...")
    
    if not os.path.exists(models_dir):
        print(f"Directory {models_dir} not found.")
        return

    processed_count = 0

    for model_folder in os.listdir(models_dir):
        model_dir = os.path.join(models_dir, model_folder)
        if not os.path.isdir(model_dir):
            continue

        bnet_path = os.path.join(model_dir, model_file)
        if not os.path.exists(bnet_path):
            continue

        print(f"  [>] Generating random config for: {model_folder}")
        
        equations_raw = {}
        all_sources = set()
        
        # 1. Parse the .bnet file
        with open(bnet_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("targets") or line.startswith("#"): 
                    continue
                if "," not in line: 
                    continue
                
                target, eq = line.split(",", 1)
                target = target.strip()
                eq = eq.strip()
                equations_raw[target] = eq
                
                # Extract all variables
                vars_in_eq = set(re.findall(r'\b[a-zA-Z_]\w*\b', eq)) - {'True', 'False'}
                all_sources.update(vars_in_eq)
                
        internal_components = list(equations_raw.keys())
        external_inputs = list(all_sources - set(internal_components))
        interactions = []

        # 2. Synthesize Random Interactions
        for target, eq in equations_raw.items():
            # Basic heuristic to separate repressors from activators
            repressors = set(re.findall(r'!\s*([a-zA-Z_]\w*)', eq))
            activators = (set(re.findall(r'(?<![\!\w])([a-zA-Z_]\w*)', eq)) - {'True', 'False'}) - repressors
            
            all_edges = [(act, 1) for act in activators] + [(rep, -1) for rep in repressors]
            
            for src, edge_type in all_edges:
                # Randomize Delays (e.g., 1 to MAX_DELAY)
                d_min = random.randint(1, MAX_DELAY)
                d_max = random.randint(d_min, MAX_DELAY)
                
                # Randomize Structural Properties
                is_definite = random.random() > PROB_INDEFINITE
                is_irreversible = random.random() < PROB_IRREVERSIBLE
                
                edge_dict = {
                    "src": src,
                    "tgt": target,
                    "type": edge_type,
                    "d_min": d_min,
                    "d_max": d_max,
                    "definite": is_definite
                }
                
                if is_irreversible:
                    edge_dict["irreversible"] = True
                    
                interactions.append(edge_dict)

        # 3. Build the JSON structure
        config_data = {
            "num_steps": 30,
            "time_resolution": 1,
            "initialize_components_false": True,
            "internal_components": internal_components,
            "external_inputs": external_inputs,
            "interactions": interactions,
            "input_constraints": [],
            "state_constraints": []
        }

        # 4. Save the config.json
        config_path = os.path.join(model_dir, "config.json")
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=4)
            
        processed_count += 1

    print(f"\nSuccessfully generated {processed_count} randomized config.json files.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate random configs for BBM models.")
    parser.add_argument("--models_dir", type=str, default="test_models_BBM", help="Directory containing BBM model subfolders")
    args = parser.parse_args()
    
    parse_and_generate(args.models_dir)