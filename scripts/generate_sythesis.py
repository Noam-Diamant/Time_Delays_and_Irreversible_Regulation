import random
import re
import json
import argparse
from pathlib import Path

class BnetSimulator:
    def __init__(self, bnet_text):
        """Initializes the network by parsing a .bnet formatted string."""
        self.rules = self._parse_bnet(bnet_text)
        self.genes = list(self.rules.keys())

    def _parse_bnet(self, bnet_text):
        """Parses the .bnet string and converts it into Python evaluation rules."""
        rules_text = {}
        all_nodes = set()
        
        for line in bnet_text.strip().split('\n'):
            if line.startswith('targets') or line.startswith('[source') or not line.strip():
                continue
            
            target, rule = line.split(',', 1)
            target = target.strip()
            rule = rule.strip()
            
            # Convert Boolean operators to Python equivalents
            rule = rule.replace('!', ' not ')
            rule = rule.replace('&', ' and ')
            rule = rule.replace('|', ' or ')
            
            rules_text[target] = rule
            all_nodes.add(target)
            
            # Extract all variables to identify input nodes
            vars_in_rule = set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', rule))
            vars_in_rule -= {'not', 'and', 'or'}
            all_nodes.update(vars_in_rule)
            
        rules = {}
        for node in all_nodes:
            if node in rules_text:
                rules[node] = lambda state, r=rules_text[node]: bool(eval(r, {}, state))
            else:
                # Input node: holds its initial state constant
                rules[node] = lambda state, n=node: state[n]
                
        return rules

    def step(self, current_state):
        """Calculates the next state of the network."""
        return {gene: self.rules[gene](current_state) for gene in self.genes}

    def generate_random_trajectories(self, num_samples=5, steps=10):
        """Generates multiple trajectories starting from random initial states."""
        trajectories = []
        for _ in range(num_samples):
            # Random initial state for all nodes (including inputs)
            state = {gene: random.choice([True, False]) for gene in self.genes}
            trajectory = [state]
            
            for _ in range(steps):
                next_state = self.step(state)
                trajectory.append(next_state)
                state = next_state
                
            trajectories.append(trajectory)
        return trajectories

    def sample_steady_states(self, samples=1000, max_steps=50):
        """Uses Monte Carlo sampling to find point attractors."""
        steady_states = []
        seen_signatures = set()
        
        for _ in range(samples):
            current_state = {gene: random.choice([True, False]) for gene in self.genes}
            
            for _ in range(max_steps):
                next_state = self.step(current_state)
                if next_state == current_state:
                    state_signature = tuple(sorted(current_state.items()))
                    if state_signature not in seen_signatures:
                        seen_signatures.add(state_signature)
                        steady_states.append(current_state)
                    break
                current_state = next_state
                
        return steady_states

def format_for_json_sparse(state_dict, keep_prob=0.3):
    """
    Converts boolean states to 1/0 integers.
    Randomly assigns 'None' (null in JSON) based on keep_prob to simulate missing data.
    """
    sparse_state = {}
    for gene, is_on in state_dict.items():
        if random.random() < keep_prob:
            sparse_state[gene] = int(is_on)
        else:
            sparse_state[gene] = None 
    return sparse_state

def export_observations_to_json(model_id, trajectories, steady_states, output_filepath, keep_prob=0.3):
    """Bundles sparse observations and writes them to a JSON file."""
    
    # Apply sparsity mask to trajectories
    formatted_trajectories = [
        [format_for_json_sparse(state, keep_prob) for state in traj] for traj in trajectories
    ]
    
    # Apply sparsity mask to steady states
    formatted_steady_states = [
        format_for_json_sparse(state, keep_prob) for state in steady_states
    ]

    output_data = {
        "model_id": model_id,
        "observations": {
            "time_series_trajectories": formatted_trajectories,
            "steady_states": formatted_steady_states
        }
    }

    with open(output_filepath, 'w') as json_file:
        json.dump(output_data, json_file, indent=4)


# ==========================================
# Batch Processing Execution
# ==========================================
if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="Generate Sparse Observations for BNET Models.")
    parser.add_argument("--models_dir", type=str, default="test_models_BBM")
    parser.add_argument("--obs_dir", type=str, default="observations_BBM")
    parser.add_argument("--model_name", type=str, default=None, help="Specific model to run")
    args = parser.parse_args()
    args = parser.parse_args(['--models_dir', 'test_models_BBM', '--obs_dir', 'observations_BBM', '--model_name', '[id-230]__[var-50]__[in-5]__[HEPATOCYTE-GROWTH-FACTOR]'])

    # Parameters for the simulation
    NUM_TRAJECTORIES = 10
    STEPS_PER_TRAJ = 15       
    MONTE_CARLO_SAMPLES = 100 
    
    # Multi-Experiment & Sparsity Parameters
    NUM_EXPERIMENTS = 1       
    KEEP_PROBABILITY = 0.5   
    # ---------------------

    input_path = Path(args.models_dir)
    output_path = Path(args.obs_dir)
    
    if not input_path.exists() or not input_path.is_dir():
        print(f"Error: The input directory '{args.models_dir}' was not found.")
        exit(1)

    output_path.mkdir(parents=True, exist_ok=True)

    print(f"Scanning directory: {input_path.absolute()}")
    print(f"Output directory: {output_path.absolute()}\n")
    
    bnet_files = list(input_path.rglob("*.bnet"))
    
    if not bnet_files:
        print("No .bnet files found in the specified input directory.")
        exit(0)
        
    models_processed = 0
    
    for bnet_path in bnet_files:
        model_folder = bnet_path.parent
        model_id = model_folder.name
        
        # Skip if a specific model was requested and this isn't it
        if args.model_name and model_id != args.model_name:
            continue
            
        models_processed += 1
        print(f"Processing Model: {model_id}")
        
        try:
            with open(bnet_path, 'r') as f:
                bnet_text = f.read()
                
            simulator = BnetSimulator(bnet_text)
            
            # Create a dedicated subdirectory for this model's observations
            model_obs_dir = output_path / model_id
            model_obs_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate distinct trajectories once and share the same model sampling across experiments
            trajectories = simulator.generate_random_trajectories(
                num_samples=NUM_TRAJECTORIES, 
                steps=STEPS_PER_TRAJ
            )
            steady_states = simulator.sample_steady_states(samples=MONTE_CARLO_SAMPLES)
            
            for exp_idx in range(1, NUM_EXPERIMENTS + 1):
                trajectory = [trajectories[exp_idx - 1]]
                output_filename = f"{model_id}_observations_{exp_idx}.json"
                output_filepath = model_obs_dir / output_filename
                
                export_observations_to_json(
                    model_id, 
                    trajectory, 
                    steady_states, 
                    output_filepath, 
                    keep_prob=KEEP_PROBABILITY
                )
                
            print(f"  -> Generated {NUM_EXPERIMENTS} sparse experiments in: {model_obs_dir.name}/\n")
            
        except Exception as e:
            print(f"  -> [ERROR] Failed to process {model_id}. Reason: {e}\n")
            
    if models_processed == 0:
        if args.model_name:
            print(f"Warning: Model '{args.model_name}' was not found in {args.models_dir}.")
        else:
            print("No models were processed.")
    else:
        print("Batch processing complete!")