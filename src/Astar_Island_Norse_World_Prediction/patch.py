import re

with open("scripts/simulate_queries_tui.py", "r") as f:
    content = f.read()

old_main = content[content.find("def main():"):]

new_main = """def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--round-id", type=str, help="Round ID to simulate")
    parser.add_argument("--round-file", type=Path, help="Specific round file (falls back to extracting round ID)")
    parser.add_argument("--queries", type=int, default=8)
    parser.add_argument("--rounds-dir", type=Path, default=Path("data/rounds"))
    args = parser.parse_args()

    if args.round_id:
        round_id = args.round_id
    elif args.round_file:
        round_id = args.round_file.stem.split('_')[0]
    else:
        print("Must provide either --round-id or --round-file")
        sys.exit(1)

    console = Console()
    layout = make_layout()
    
    # Mock some data for the left side
    tabs = Text()
    for i, t in enumerate(["Dashboard", "Rounds", "Submit", "Explorer", "Autoiterate", "Research", "Backtest", "Logs", "Settings", "Metrics"]):
        color = "black on yellow" if t == "Research" else "dim"
        tabs.append(f" {i}:{t} ", style=color)
        tabs.append(" ")
    layout["tabs"].update(tabs)

    with Live(layout, console=console, screen=True, refresh_per_second=4):
        for seed_idx in range(5):
            round_file = args.rounds_dir / f"{round_id}_seed{seed_idx}_analysis.json"
            if not round_file.exists():
                continue
                
            data = json.loads(round_file.read_text())
            initial_grid = np.asarray(data["initial_grid"])
            ground_truth = np.asarray(data["ground_truth"])
            
            h, w = initial_grid.shape
            observations = []
            viewports = []
            
            vp_candidates = []
            for y in range(0, max(1, h - 15 + 1), 15):
                for x in range(0, max(1, w - 15 + 1), 15):
                    vp_candidates.append((x, y))
            for x in range(0, max(1, w - 15 + 1), 15):
                vp_candidates.append((x, max(0, h - 15)))
            for y in range(0, max(1, h - 15 + 1), 15):
                vp_candidates.append((max(0, w - 15), y))
            vp_candidates.append((max(0, w - 15), max(0, h - 15)))
            vp_candidates = list(set(vp_candidates))
            
            discount = np.ones((h, w))

            for step in range(args.queries + 1):
                pred = build_prediction_tensor_unet(
                    initial_grid.tolist(), 
                    observations=observations, 
                    floor=1e-5
                )
                ent = entropy_map(pred)
                max_ent = np.max(ent) if np.max(ent) > 0 else 1.0
                argmax = np.argmax(pred, axis=-1)
                
                next_vp = None
                if step < args.queries:
                    utility = ent * discount
                    best_score = -1
                    for (vx, vy) in vp_candidates:
                        if (vx, vy) in viewports: continue
                        score = np.sum(utility[vy:vy+15, vx:vx+15])
                        if score > best_score:
                            best_score = score
                            next_vp = (vx, vy)
                
                # Left Panels
                layout["research_agents"].update(Panel(
                    Text("X Research Agents - Autonomous AI Experimenters\\n", style="bold yellow") + 
                    Text("● g:Gemini Researcher   a:ADK Agent   m:Multi Researcher\\n", style="dim") +
                    Text("Google ADK framework agent for systematic algorithm exploration\\n", style="italic dim") +
                    Text(f"\\n● Running... Seed {seed_idx} Step {step}/{args.queries}\\n", style="green"),
                    title="Research", box=box.HORIZONTALS
                ))
                
                avg_score_text = Text(f"Total: 95  ✓: 94  X: 1  ↑: 13\\n↑ Best: 91.488\\n", style="yellow")
                layout["avg_score"].update(Panel(avg_score_text, title="Average Score", box=box.ROUNDED))
                layout["model_details"].update(build_model_table())
                
                # Right Panels
                explorer_hdr = Text(f"f Astar Island Explorer\\n", style="bold yellow")
                explorer_hdr.append(f"Round #8 (active)  ID: {round_id}\\n", style="dim")
                seeds = Text()
                for i in range(5):
                    style = "black on cyan" if i == seed_idx else "dim"
                    seeds.append(f" Seed {i} ", style=style)
                    seeds.append(" ")
                explorer_hdr.append(seeds)
                layout["explorer_header"].update(explorer_hdr)
                
                map_txt = build_grid_text(initial_grid, viewports, next_vp, mode="pred", argmax=argmax)
                layout["map_view"].update(map_txt)
                
                legend_txt = Text("R Terrain Legend\\n", style="bold yellow")
                for val in [10, 11, 1, 2, 3, 4, 5]:
                    char, color = get_cell_style(val)
                    name = CLASS_NAMES.get(val, "Unknown")
                    legend_txt.append(f"{char} {name}\\n", style=color)
                
                covered = np.zeros_like(initial_grid)
                for vx, vy in viewports:
                    covered[vy:vy+15, vx:vx+15] = 1
                coverage = np.mean(covered) * 100
                legend_txt.append(f"\\nCoverage: {coverage:.1f}%\\n", style="bold yellow")
                layout["legend"].update(legend_txt)
                
                layout["vp_contents"].update(build_vp_contents(initial_grid, next_vp or (viewports[-1] if viewports else None), argmax))
                
                if next_vp is None:
                    break
                    
                time.sleep(2.0)
                
                vx, vy = next_vp
                viewports.append((vx, vy))
                
                gt_vp = ground_truth[vy:vy+15, vx:vx+15]
                obs_grid = np.argmax(gt_vp, axis=-1)
                mapped_grid = np.zeros_like(obs_grid)
                for i, v in CLASS_TO_GRID.items():
                    mapped_grid[obs_grid == i] = v
                ocean_mask = initial_grid[vy:vy+15, vx:vx+15] == 10
                mapped_grid[ocean_mask] = 10
                
                obs = {
                    "viewport": {"x": vx, "y": vy, "w": 15, "h": 15},
                    "grid": mapped_grid.tolist()
                }
                observations.append(obs)
                discount[vy:vy+15, vx:vx+15] *= 0.0
                
            time.sleep(2.0)

if __name__ == "__main__":
    main()
"""

new_content = content.replace(old_main, new_main)

with open("scripts/simulate_queries_tui.py", "w") as f:
    f.write(new_content)
