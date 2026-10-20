import json
import time
import re
import os
import argparse
from z3 import *

# ==============================================================================
# THE PARALLEL SYNTHESIS CLASS (Dynamic Delays & Multi-Dimensional Proofs)
# ==============================================================================
class ParallelCABN_Synthesis:
    def __init__(self, internal_components, external_inputs, experiments_info):
        self.components = internal_components
        self.inputs = external_inputs
        self.experiments = experiments_info
        self.solver = Solver()
        self.interactions = []
        
        self.update_functions = {} 
        self.indefinite_edges = {} 
        
        self.buffers_map = {} 
        self.q = {exp_id: [] for exp_id in self.experiments}
        
        for exp_id, num_steps in self.experiments.items():
            for n in range(num_steps):
                state = {}
                for name in internal_components + external_inputs:
                    state[name] = Bool(f"{name}_{exp_id}_n{n}")
                self.q[exp_id].append(state)

    def add_interaction(self, edge_dict):
        self.interactions.append(edge_dict)
        src, tgt = edge_dict['src'], edge_dict['tgt']
        d_min, d_max = edge_dict['d_min'], edge_dict['d_max']
        
        if not edge_dict.get('definite', True) and (src, tgt) not in self.indefinite_edges:
            self.indefinite_edges[(src, tgt)] = Bool(f"IndefiniteEdge_{src}_{tgt}")
            
        if (src, tgt, d_min, d_max) not in self.buffers_map:
            self.buffers_map[(src, tgt, d_min, d_max)] = {exp_id: [] for exp_id in self.experiments}
            for exp_id, num_steps in self.experiments.items():
                for k in range(1, d_max): 
                    buf_name = f"Buf_{src}_{tgt}_{d_min}_{d_max}_{k}_{exp_id}"
                    self.buffers_map[(src, tgt, d_min, d_max)][exp_id].append(buf_name)
                    for n in range(num_steps):
                        self.q[exp_id][n][buf_name] = Bool(f"{buf_name}_n{n}")

    def set_update_function(self, target, z3_expr):
        if target in self.components:
            self.update_functions[target] = z3_expr

    def print_solver_constraints(self, output_path=None, print_to_console=False):
        assertions = self.solver.assertions()
        if not assertions:
            msg = "SMT constraints: none"
            if print_to_console:
                print(msg)
            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w') as f:
                    f.write(msg + "\n")
            return

        lines = ["\n=== SMT CONSTRAINTS ==="]
        for idx, assertion in enumerate(assertions, 1):
            lines.append(f"[{idx}] {assertion}")
        lines.append("=== END SMT CONSTRAINTS ===\n")

        output = "\n".join(lines)
        if print_to_console:
            print(output)
        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(output)

    def build_constraints(self):
            # 1. DEFINE DYNAMIC INTEGER DELAYS (PER TIME STEP)
            self.dynamic_delay_vars = {exp_id: {} for exp_id in self.experiments}
            for exp_id, num_steps in self.experiments.items():
                for n in range(1, num_steps):
                    self.dynamic_delay_vars[exp_id][n] = {}
                    for edge in self.interactions:
                        src, tgt = edge['src'], edge['tgt']
                        d_min, d_max = edge['d_min'], edge['d_max']
                        if d_min != d_max:
                            # Unique SMT Integer for every single time step
                            d_var = Int(f"Delay_{src}_{tgt}_{exp_id}_step{n}")
                            self.solver.add(d_var >= d_min, d_var <= d_max)
                            self.dynamic_delay_vars[exp_id][n][(src, tgt)] = d_var

            # 1b. ZERO-DELAY ACYCLICITY: selected zero-delay edges must admit a topological order
            zero_edges = [e for e in self.interactions if e['d_min'] == 0]
            if zero_edges:
                nodes = list(self.inputs) + list(self.components)
                for exp_id, num_steps in self.experiments.items():
                    for n in range(1, num_steps):
                        rank = {c: Int(f"Rank_{exp_id}_{n}_{c}") for c in nodes}
                        for e in zero_edges:
                            s_, t_ = e['src'], e['tgt']
                            if e['d_max'] == 0:
                                self.solver.add(rank[s_] < rank[t_])
                            else:
                                self.solver.add(Implies(self.dynamic_delay_vars[exp_id][n][(s_, t_)] == 0,
                                                rank[s_] < rank[t_]))                

            for exp_id, num_steps in self.experiments.items():
                # 2. BUFFER DYNAMICS
                for (src, tgt, d_min, d_max), exp_buffers in self.buffers_map.items():
                    buffers = exp_buffers[exp_id]
                    if not buffers: continue
                    for buf_name in buffers:
                        # Tie buffer to the source's initial state
                        self.solver.add(self.q[exp_id][0][buf_name] == self.q[exp_id][0][src])

                for n in range(num_steps - 1):
                    for (src, tgt, d_min, d_max), exp_buffers in self.buffers_map.items():
                        buffers = exp_buffers[exp_id]
                        if not buffers: continue 
                        self.solver.add(self.q[exp_id][n+1][buffers[0]] == self.q[exp_id][n][src])
                        for k_idx in range(1, len(buffers)):
                            self.solver.add(self.q[exp_id][n+1][buffers[k_idx]] == self.q[exp_id][n][buffers[k_idx-1]])

                # 3. REGULATION DYNAMICS
                for n in range(1, num_steps):
                    for target in self.components:
                        incoming = [i for i in self.interactions if i['tgt'] == target]
                        if target not in self.update_functions:
                            self.solver.add(self.q[exp_id][n][target] == self.q[exp_id][n-1][target])
                            continue

                        substitutions = []
                        target_is_irreversible = False

                        for edge in incoming:
                            src, tgt = edge['src'], edge['tgt']
                            d_min, d_max = edge['d_min'], edge['d_max']
                            if edge.get('irreversible', False): target_is_irreversible = True
                            
                            window = edge.get('active_window', [0, num_steps])
                            is_touching = And(n >= window[0], n <= window[1])
                            buffers = self.buffers_map[(src, tgt, d_min, d_max)][exp_id]

                            if d_min == d_max:
                                k = d_min
                                if k == 0: signal = self.q[exp_id][n][src] if edge.get('type', 1) == -1 else self.q[exp_id][n][src]
                                elif k == 1: signal = self.q[exp_id][n-1][src]
                                else: signal = self.q[exp_id][n-1][buffers[k-2]]
                                effective_signal = And(is_touching, signal)
                            else:
                                mux_options = []
                                # Fetch the delay assigned to this exact time step
                                d_var = self.dynamic_delay_vars[exp_id][n][(src, tgt)]
                                
                                for k in range(d_min, d_max + 1):
                                    if k == 0: signal = self.q[exp_id][n][src] if edge.get('type', 1) == -1 else self.q[exp_id][n][src]
                                    elif k == 1: signal = self.q[exp_id][n-1][src]
                                    else: signal = self.q[exp_id][n-1][buffers[k-2]]
                                    
                                    mux_options.append(And(d_var == k, is_touching, signal))
                                
                                effective_signal = Or(mux_options)

                            if (src, tgt) in self.indefinite_edges:
                                indef_var = self.indefinite_edges[(src, tgt)]
                                effective_signal = And(indef_var, effective_signal)

                            substitutions.append((Bool(src), effective_signal))

                        incoming_srcs = {edge['src'] for edge in incoming}
                        for node in self.inputs + self.components:
                            if node not in incoming_srcs:
                                substitutions.append((Bool(node), self.q[exp_id][n][node]))

                        final_condition = substitute(self.update_functions[target], *substitutions)
                        if target_is_irreversible:
                            final_condition = Or(final_condition, self.q[exp_id][n-1][target])
                            
                        self.solver.add(self.q[exp_id][n][target] == final_condition)

    def run(self, max_solutions=100):
            total_permutations = 0
            all_permutations = []
            all_trajectories = []
            proven_rules = [] 

            print(f"Executing Dynamic Delay Search (Max Solutions: {max_solutions})")
            smt_dump_path = os.path.join("Results_BBM", "smt_constraints_dump.txt")
            self.print_solver_constraints(output_path=smt_dump_path, print_to_console=False)
            start_time = time.time()

            # STEP 1: EXTRACT SOLUTIONS
            while self.solver.check() == sat and total_permutations < max_solutions:
                m = self.solver.model()

                # EXTRACT DYNAMIC DELAYS PER TIME STEP
                current_dynamic_delays = {exp_id: {} for exp_id in self.experiments}
                for exp_id, num_steps in self.experiments.items():
                    for n in range(1, num_steps):
                        current_dynamic_delays[exp_id][n] = {}
                        for (src, tgt), d_var in self.dynamic_delay_vars[exp_id][n].items():
                            current_dynamic_delays[exp_id][n][f"{src}->{tgt}"] = m.evaluate(d_var, model_completion=True).as_long()

                # EXTRACT STRUCTURAL DECISIONS
                current_structure = {}
                for (src, tgt), indef_var in self.indefinite_edges.items():
                    current_structure[f"{src}->{tgt}"] = is_true(m.evaluate(indef_var, model_completion=True))

                experiment_trajectories = {}
                for exp_id, num_steps in self.experiments.items():
                    traj = []
                    for n in range(num_steps):
                        states = [(name, is_true(m.evaluate(self.q[exp_id][n][name], model_completion=True))) for name in self.inputs + self.components]
                        traj.append(states)
                    experiment_trajectories[exp_id] = traj

                all_permutations.append({
                    "solution_id": total_permutations + 1,
                    "dynamic_delays": current_dynamic_delays,
                    "structure": current_structure
                })
                all_trajectories.append(experiment_trajectories)
                total_permutations += 1

                # BLOCKING EXACT DYNAMIC PERMUTATIONS AND STRUCTURE
                block = []
                for exp_id, num_steps in self.experiments.items():
                    for n in range(1, num_steps):
                        for (src, tgt), d_var in self.dynamic_delay_vars[exp_id][n].items():
                            block.append(d_var != current_dynamic_delays[exp_id][n][f"{src}->{tgt}"])
                
                for (src, tgt), indef_var in self.indefinite_edges.items():
                    block.append(indef_var != current_structure[f"{src}->{tgt}"])
                    
                if block:
                    self.solver.add(Or(block))
                else:
                    break

            print(f"\n--- DONE: Extracted {total_permutations} Concrete Models ---")
            
            # STEP 2: HYPOTHESIZE AND PROVE TEMPORAL RIGIDITY (Self-Relationships)
            first_exp = list(self.experiments.keys())[0] if self.experiments else None
            if total_permutations > 1 and first_exp and self.dynamic_delay_vars[first_exp].get(1):
                edges = list(self.dynamic_delay_vars[first_exp][1].keys())
                
                print("\nScanning for Delays That Remain Constant Across All Time Steps")
                for (src, tgt) in edges:
                    edge_name = f"{src}->{tgt}"
                    
                    # 1. Hypothesize: Is it constant in the empirical data?
                    is_empirical_constant = True
                    for p in all_permutations:
                        vals = set()
                        for exp_id, num_steps in self.experiments.items():
                            for n in range(1, num_steps):
                                vals.add(p["dynamic_delays"][exp_id][n][edge_name])
                        if len(vals) > 1:
                            is_empirical_constant = False
                            break
                    
                    # 2. Formally Prove
                    if is_empirical_constant:
                        self.solver.push()
                        base_var = self.dynamic_delay_vars[first_exp][1][(src, tgt)]
                        diff_conditions = []
                        
                        # Break condition: Is there ANY time step in ANY experiment that differs?
                        for exp_id, num_steps in self.experiments.items():
                            for n in range(1, num_steps):
                                var_t = self.dynamic_delay_vars[exp_id][n][(src, tgt)]
                                diff_conditions.append(var_t != base_var)
                                
                        self.solver.add(Or(diff_conditions))
                        if self.solver.check() == unsat:
                            rule = f"Delay of {edge_name} MUST BE CONSTANT across all time steps."
                            print(f"  {rule}")
                            proven_rules.append(rule)
                        self.solver.pop()

                # STEP 3: HYPOTHESIZE AND PROVE RELATIVE SYNCHRONY 
                print("\nScanning for Relative Delay Relationships Between Interactions")
                for i in range(len(edges)):
                    for j in range(i + 1, len(edges)):
                        e1, e2 = edges[i], edges[j]
                        name1, name2 = f"{e1[0]}->{e1[1]}", f"{e2[0]}->{e2[1]}"
                        
                        all_greater, all_less, all_equal = True, True, True
                        
                        # 1. Hypothesize based on empirical models at EVERY time step
                        for p in all_permutations:
                            for exp_id, num_steps in self.experiments.items():
                                for n in range(1, num_steps):
                                    d1 = p["dynamic_delays"][exp_id][n][name1]
                                    d2 = p["dynamic_delays"][exp_id][n][name2]
                                    if d1 <= d2: all_greater = False
                                    if d1 >= d2: all_less = False
                                    if d1 != d2: all_equal = False
                        
                        # 2. Formally Prove
                        if all_greater:
                            self.solver.push()
                            # Break condition: Exists AT LEAST ONE time step where d1 <= d2
                            break_conditions = []
                            for exp_id, num_steps in self.experiments.items():
                                for n in range(1, num_steps):
                                    v1 = self.dynamic_delay_vars[exp_id][n][e1]
                                    v2 = self.dynamic_delay_vars[exp_id][n][e2]
                                    break_conditions.append(v1 <= v2)
                            self.solver.add(Or(break_conditions))
                            if self.solver.check() == unsat:
                                rule = f"{name1} MUST ALWAYS BE GREATER THAN {name2} at every time step."
                                print(f" {rule}")
                                proven_rules.append(rule)
                            self.solver.pop()
                            
                        elif all_less:
                            self.solver.push()
                            break_conditions = []
                            for exp_id, num_steps in self.experiments.items():
                                for n in range(1, num_steps):
                                    v1 = self.dynamic_delay_vars[exp_id][n][e1]
                                    v2 = self.dynamic_delay_vars[exp_id][n][e2]
                                    break_conditions.append(v1 >= v2)
                            self.solver.add(Or(break_conditions))
                            if self.solver.check() == unsat:
                                rule = f"{name1} MUST ALWAYS BE LESS THAN {name2} at every time step."
                                print(f" {rule}")
                                proven_rules.append(rule)
                            self.solver.pop()
                            
                        elif all_equal:
                            self.solver.push()
                            break_conditions = []
                            for exp_id, num_steps in self.experiments.items():
                                for n in range(1, num_steps):
                                    v1 = self.dynamic_delay_vars[exp_id][n][e1]
                                    v2 = self.dynamic_delay_vars[exp_id][n][e2]
                                    break_conditions.append(v1 != v2)
                            self.solver.add(Or(break_conditions))
                            if self.solver.check() == unsat:
                                rule = f"{name1} MUST ALWAYS BE EQUAL TO {name2} at every time step."
                                print(f" {rule}")
                                proven_rules.append(rule)
                            self.solver.pop()

            # STEP 4: HYPOTHESIZE AND PROVE STRUCTURAL NECESSITY
            if total_permutations > 0 and self.indefinite_edges:
                print("\nScanning for Necessity of Indefinite Edges")
                for (src, tgt), indef_var in self.indefinite_edges.items():
                    edge_name = f"{src}->{tgt}"
                    always_present = all(p["structure"][edge_name] is True for p in all_permutations)
                    always_absent = all(p["structure"][edge_name] is False for p in all_permutations)
                    
                    if always_present:
                        self.solver.push()
                        self.solver.add(indef_var == False) 
                        if self.solver.check() == unsat:
                            rule = f"INTERACTION {edge_name} IS STRICTLY NECESSARY"
                            print(f" {rule}")
                            proven_rules.append(rule)
                        self.solver.pop()
                        
                    elif always_absent:
                        self.solver.push()
                        self.solver.add(indef_var == True) 
                        if self.solver.check() == unsat:
                            rule = f"INTERACTION {edge_name} IS STRICTLY PROHIBITED"
                            print(f" {rule}")
                            proven_rules.append(rule)
                        self.solver.pop()

            runtime = time.time() - start_time
            print(f"--- Runtime: {runtime:.4f} seconds ---\n")

            return all_permutations, all_trajectories, proven_rules, runtime

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def parse_bnet_rule_to_z3(equation_str, z3_vars):
    python_expr = equation_str.replace("!", "~")
    python_expr = re.sub(r'\bTrue\b', 'BoolVal(True)', python_expr)
    python_expr = re.sub(r'\bFalse\b', 'BoolVal(False)', python_expr)
    eval_context = {'BoolVal': BoolVal}
    return eval(python_expr, eval_context, z3_vars)

def load_delays_from_rich_config(json_path):
    """
    Properly extracts bounds from the rich JSON schema and the custom flat dictionary.
    """
    edge_delays = {}
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            model_config = json.load(f)
            
            # Handle the flat dictionary format {"src->tgt": [d_min, d_max]}
            if isinstance(model_config, dict) and "interactions" not in model_config:
                for key, bounds in model_config.items():
                    if "->" in key:
                        src, tgt = key.split("->")
                        edge_delays[(src.strip(), tgt.strip())] = (bounds[0], bounds[1])
            else:
                # Handle the original nested format
                interactions = model_config.get("interactions", [])
                for edge in interactions:
                    src = edge.get("src")
                    tgt = edge.get("tgt")
                    if src and tgt:
                        edge_delays[(src.strip(), tgt.strip())] = (edge.get("d_min", 1), edge.get("d_max", 2))
    return edge_delays

def get_delay(src, tgt, edge_delays, def_min=1, def_max=2):
    return edge_delays.get((src, tgt), (def_min, def_max))

# ==============================================================================
# MAIN EXECUTION PIPELINE
# ==============================================================================

if __name__ == "__main__":
    print("Starting execution...")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_file", type=str, default=None)
    parser.add_argument("--models_dir", type=str, default="test_models_BBM")
    parser.add_argument("--model_file", type=str, default="model.bnet")
    parser.add_argument("--model_name", type=str, default=None)
    parser.add_argument("--obs_dir", type=str, default="observations_BBM")
    parser.add_argument("--results_dir", type=str, default="Results_BBM")

    #args = parser.parse_args(['--models_dir', 'test_models_BBM', '--model_file', 'model.bnet','--model_name', '[id-230]__[var-50]__[in-5]__[HEPATOCYTE-GROWTH-FACTOR]', '--obs_dir', 'observations_BBM', '--results_dir', 'Results_BBM'])
    args = parser.parse_args(['--models_dir', 'sea-urchin-embryo', '--model_file', 'model.bnet','--model_name', 'sea_urchin_model', '--obs_dir', 'observations_sea_urchin', '--results_dir', 'Results_BBM'])

    models_to_process = []
    if args.models_dir and os.path.exists(args.models_dir):
        for model_folder_name in os.listdir(args.models_dir):
            if args.model_name and model_folder_name != args.model_name: continue
            model_dir = os.path.join(args.models_dir, model_folder_name)
            if not os.path.isdir(model_dir): continue
            
            bnet_path = os.path.join(model_dir, args.model_file)
            config_path = args.config_file if args.config_file else os.path.join(model_dir, "config.json")
            has_config = os.path.exists(config_path)
            
            models_to_process.append((model_folder_name, model_dir, config_path, has_config, bnet_path))

    for model_folder_name, model_dir, config_path, has_config, bnet_path in models_to_process:
        if not os.path.exists(bnet_path): continue

        print(f"\n\n{'#'*80}")
        print(f"PROCESSING MODEL: {model_folder_name}")
        print(f"Mode: {'JSON Configuration' if has_config else 'Fallback'}")
        print(f"{'#'*80}")

        # Always parse the .bnet file to get components and equations
        equations_raw = {}
        all_sources = set()
        with open(bnet_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("targets") or line.startswith("#"): continue
                if "," not in line: continue
                target, eq = line.split(",", 1)
                target = target.strip()
                equations_raw[target] = eq.strip()
                all_sources.update(set(re.findall(r'\b[a-zA-Z_]\w*\b', eq.strip())) - {'True', 'False'})
        
        components = list(equations_raw.keys())
        external_inputs = list(all_sources - set(components))
        interactions = []

        # Load delays
        edge_delays = load_delays_from_rich_config(config_path) if has_config else {}
        
        for target, eq in equations_raw.items():
            repressors = set(re.findall(r'!\s*([a-zA-Z_]\w*)', eq))
            activators = (set(re.findall(r'(?<![\!\w])([a-zA-Z_]\w*)', eq)) - {'True', 'False'}) - repressors
            
            for act in activators:
                d_min, d_max = get_delay(act, target, edge_delays)
                interactions.append({"src": act, "tgt": target, "type": 1, "d_min": d_min, "d_max": d_max})
            for rep in repressors:
                d_min, d_max = get_delay(rep, target, edge_delays)
                interactions.append({"src": rep, "tgt": target, "type": -1, "d_min": d_min, "d_max": d_max})

        init_false, input_constraints = False, []
        total_simulation_steps, time_resolution = 30, 1
        
        if has_config:
            with open(config_path, 'r') as f:
                model_config = json.load(f)
                if isinstance(model_config, dict) and "interactions" in model_config:
                    init_false = model_config.get("initialize_components_false", False)
                    input_constraints = model_config.get("input_constraints", [])
                    total_simulation_steps = model_config.get("num_steps", 30)
                    time_resolution = model_config.get("time_resolution", 1)

        all_nodes = components + external_inputs
        z3_vars = {name: Bool(name) for name in all_nodes}

        with open(bnet_path, 'r') as f:
            for line in f:
                if "," in line and not line.startswith("targets"):
                    for var in re.findall(r'\b[a-zA-Z_]\w*\b', line.split(",")[1]):
                        if var not in z3_vars and var not in ["True", "False"]:
                            z3_vars[var] = BoolVal(False)

        # Unified Single-File Observation Loader
        obs_path = os.path.join(args.obs_dir, f"{model_folder_name}.json")
        if not os.path.exists(obs_path): 
            print(f"  [!] No observation file found at {obs_path}. Skipping...")
            continue

        with open(obs_path, 'r') as f:
            obs_data = json.load(f)

        experiments_info = {}
        experiment_constraints = {}
        
        trajectories = obs_data.get("observations", {}).get("time_series_trajectories", [])
        for exp_idx, traj in enumerate(trajectories):
            exp_id = f"exp_{exp_idx}"
            
            sim_steps = max(total_simulation_steps, len(traj))
            experiments_info[exp_id] = sim_steps
            
            constraints = []
            for index, states in enumerate(traj):
                actual_t = index * time_resolution
                if actual_t >= sim_steps: break 
                for comp, val in states.items():
                    if val is not None and (comp in components or comp in external_inputs):
                        constraints.append((actual_t, comp, bool(val)))
            experiment_constraints[exp_id] = constraints

        parsed_expressions = {}
        with open(bnet_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("targets") or line.startswith("#"): continue
                if "," not in line: continue
                target, eq = line.split(",", 1)
                target = target.strip()
                if target in components:
                    parsed_expressions[target] = parse_bnet_rule_to_z3(eq.strip(), z3_vars)

        sys = ParallelCABN_Synthesis(components, external_inputs, experiments_info)
        sys.solver.set("timeout", 60000)

        for edge in interactions: sys.add_interaction(edge)
        for target, expr in parsed_expressions.items(): sys.set_update_function(target, expr)

        sys.build_constraints()

        for exp_id, constraints in experiment_constraints.items():
            for ic in input_constraints:
                name = ic["name"]
                if name in z3_vars:
                    for t in range(sys.experiments[exp_id]):
                        val = True if ic["start"] <= t <= ic["end"] else False
                        sys.solver.add(sys.q[exp_id][t][name] == val)
            
            t0_defined = {comp for (t, comp, val) in constraints if t == 0}
            if init_false:
                for comp in components:
                    if comp not in t0_defined:
                        sys.solver.add(sys.q[exp_id][0][comp] == False)
                        
            for t, comp, val in constraints:
                sys.solver.add(sys.q[exp_id][t][comp] == val)

        run_output = sys.run(max_solutions=10)
        
        all_permutations = run_output[0] if run_output else []
        all_trajectories = run_output[1] if run_output and len(run_output) > 1 else []
        proven_rules = run_output[2] if run_output and len(run_output) > 2 else []
        runtime = run_output[3] if run_output and len(run_output) == 4 else None

        if all_permutations:
            model_results_dir = os.path.join(args.results_dir, model_folder_name)
            os.makedirs(model_results_dir, exist_ok=True)
            
            uni_path = os.path.join(model_results_dir, "delay_permutations_non_constant.json")
            with open(uni_path, 'w') as f:
                json.dump(all_permutations, f, indent=4)
            print(f"  -> Saved {len(all_permutations)} permutations to {uni_path}")
            
            traj_path = os.path.join(model_results_dir, "trajectories_non_constant.txt")
            with open(traj_path, 'w') as f:
                f.write(f"TOTAL VALID UNIVERSAL SOLUTIONS: {len(all_trajectories)}\n")
                if runtime is not None: 
                    f.write(f"RUNTIME: {runtime:.4f} seconds\n")
                f.write("\n")
                for sol_idx, exp_trajs in enumerate(all_trajectories, 1):
                    f.write(f"=========================================\nGLOBAL SOLUTION {sol_idx}\n=========================================\n")
                    for exp_id, trajectory in exp_trajs.items():
                        f.write(f"\n--- EXPERIMENT: {exp_id} ---\n")
                        for step, states in enumerate(trajectory):
                            active_components = [gene for gene, is_on in states if is_on]
                            f.write(f"Step {step}: {active_components}\n")
                    f.write("\n")
            print(f"  -> Saved trajectories to {traj_path}")

            rel_path = os.path.join(model_results_dir, "Relationships.txt")
            with open(rel_path, 'w') as f:
                if runtime is not None:
                    f.write(f"RUNTIME: {runtime:.4f} seconds\n\n")
                f.write("=== PROVEN RELATIONSHIPS ===\n")
                if proven_rules:
                    for rule in proven_rules:
                        f.write(f"{rule}\n")
                else:
                    f.write("No universal relationships found.\n")
            print(f"  -> Saved relationships to {rel_path}")