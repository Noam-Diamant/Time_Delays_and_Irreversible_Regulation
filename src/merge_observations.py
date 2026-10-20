import os
import json

target_folder = r"observations_BBM\\[id-230]__[var-50]__[in-5]__[HEPATOCYTE-GROWTH-FACTOR]"
output_file = r"observations_BBM\\[id-230]__[var-50]__[in-5]__[HEPATOCYTE-GROWTH-FACTOR].json"

def merge_specific_model():
    print(f"Scanning {target_folder}...")
    
    if not os.path.exists(target_folder):
        print(f"Error: Could not find the directory {target_folder}")
        return

    combined_trajectories = []
    
    # Use os.listdir instead of glob to avoid the square bracket trap
    obs_files = [
        os.path.join(target_folder, f) 
        for f in os.listdir(target_folder) 
        if f.endswith(".json")
    ]
    obs_files.sort()
    
    if not obs_files:
        print("No JSON files found in that directory!")
        return
        
    for file_path in obs_files:
        with open(file_path, 'r') as f:
            data = json.load(f)
            trajs = data.get("observations", {}).get("time_series_trajectories", [])
            if trajs:
                combined_trajectories.extend(trajs)
                
    # Build the unified single-file JSON
    unified_data = {
        "model_id": "[id-008]__[var-25]__[in-3]__[DEATH-RECEPTOR-SIGNALING]",
        "observations": {
            "time_series_trajectories": combined_trajectories,
            "steady_states": []
        }
    }
    
    # Save it to the root of observations_BBM
    with open(output_file, 'w') as f:
        json.dump(unified_data, f, indent=4)
        
    print(f"  [>] Successfully merged {len(obs_files)} files into -> {output_file}")

if __name__ == "__main__":
    merge_specific_model()