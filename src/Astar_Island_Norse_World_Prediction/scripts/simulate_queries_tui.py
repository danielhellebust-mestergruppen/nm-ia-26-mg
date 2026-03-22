#!/usr/bin/env python3
import sys
import time
import json
import argparse
import numpy as np
from pathlib import Path
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.predictor_attention_unet import build_prediction_tensor_attn_unet
from src.predictor_gnn import build_prediction_tensor_gnn
from src.types import grid_value_to_class_index, NUM_CLASSES

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.table import Table
from rich import box
from rich.columns import Columns

CELL_TYPES = {
    10: ("~", "blue"),           # Ocean
    11: (".", "dim white"),      # Plains (Empty)
    1: ("♮", "bright_yellow"),   # Settlement
    2: ("⚓", "cyan"),           # Port
    3: ("R", "bright_magenta"),  # Ruin
    4: ("♣", "green"),           # Forest
    5: ("▲", "bright_black"),    # Mountain
}

CLASS_TO_GRID = {0: 11, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
CLASS_NAMES = {0: "Empty", 1: "Settlement", 2: "Port", 3: "Ruin", 4: "Forest", 5: "Mountain", 10: "Ocean"}

def get_cell_style(val):
    if val in CELL_TYPES:
        return CELL_TYPES[val]
    return ("?", "white")

def entropy_map(pred: np.ndarray) -> np.ndarray:
    eps = 1e-12
    p = np.clip(pred, eps, 1.0)
    ent = -np.sum(p * np.log(p), axis=-1)
    return ent

def build_grid_text(grid, viewports, next_vp, mode="obs", argmax=None, ent=None, max_ent=1.0):
    h, w = grid.shape
    text = Text()
    
    # Simple header
    header = "   "
    for x in range(0, w, 5):
        header += f"{x:<10}"
    text.append(header[:w*2+3] + "\n", style="dim")
    
    for y in range(h):
        text.append(f"{y:>2} ", style="dim")
        for x in range(w):
            in_vp = any((vy <= y < vy+15 and vx <= x < vx+15) for (vx, vy) in viewports)
            is_next = (next_vp and next_vp[1] <= y < next_vp[1]+15 and next_vp[0] <= x < next_vp[0]+14)
            # Boundary check for next_vp
            is_border = False
            if next_vp:
                vx, vy = next_vp
                if (y == vy or y == vy+14) and (vx <= x < vx+15): is_border = True
                if (x == vx or x == vx+14) and (vy <= y < vy+15): is_border = True
            
            style_prefix = "on red " if is_border else ""
            
            if mode == "entropy" and ent is not None:
                e = ent[y, x] / max_ent
                idx = min(4, int(e * 5))
                chars = ["  ", "░░", "▒▒", "▓▓", "██"]
                text.append(chars[idx], style=style_prefix + "color(196)")
            elif mode == "pred" and argmax is not None:
                val = argmax[y, x]
                color_idx = CLASS_TO_GRID.get(val, 0)
                if grid[y, x] == 10: color_idx = 10
                char, style = get_cell_style(color_idx)
                if color_idx != 10: style = style.replace("dim ", "")
                text.append(char + " ", style=style_prefix + style)
            else:
                char, style = get_cell_style(grid[y, x])
                if not in_vp:
                    style += " dim"
                text.append(char + " ", style=style_prefix + style)
        text.append(f" {y:<2}\n", style="dim")
    return text

def build_model_table():
    table = Table(box=box.SIMPLE, expand=True)
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Status", justify="center")
    table.add_column("Avg", justify="right")
    table.add_column("Δ", justify="right")
    
    models = [
        ("16", "Strong Adaptive Equilibrium", "success", "91.288", "-0.071"),
        ("60", "fixed_power_and_density", "success", "91.129", "-0.114"),
        ("61", "baseline_check", "success", "90.890", "-0.353"),
        ("17", "Regime-Adaptive Trust", "success", "91.073", "-0.286"),
        ("62", "spatial_smoothing", "success", "91.165", "-0.078"),
        ("70", "best_plus_collapse", "success", "91.289", "+0.018"),
        ("73", "temperature_scaling", "success", "91.488", "+0.199"),
    ]
    for m in models:
        color = "green" if m[2] == "success" else "yellow"
        delta_color = "green" if m[4].startswith("+") else "red"
        table.add_row(m[0], m[1], f"[{color}]- {m[2]}[/]", m[3], f"[{delta_color}]{m[4]}[/]")
    return table

def build_vp_contents(grid, viewport, argmax):
    if not viewport: return Text("No viewport active")
    vx, vy = viewport
    # We use argmax for prediction if available, else initial_grid
    contents = {}
    for y in range(vy, vy+15):
        for x in range(vx, vx+15):
            if 0 <= y < 40 and 0 <= x < 40:
                if argmax is not None:
                    val = argmax[y, x]
                    c_idx = CLASS_TO_GRID.get(val, 0)
                    if grid[y, x] == 10: c_idx = 10
                else:
                    c_idx = grid[y, x]
                contents[c_idx] = contents.get(c_idx, 0) + 1
    
    text = Text()
    text.append(f"Viewport Contents ({vx},{vy})->({vx+14},{vy+14})\n", style="bold")
    for val in [10, 11, 1, 2, 4, 5]:
        name = CLASS_NAMES.get(val, "Other")
        count = contents.get(val, 0)
        char, color = get_cell_style(val)
        text.append(f"{char} ", style=color)
        text.append(f"{name:<12} {count:>3} ")
        # Mini bar
        bar_len = int(count / 225 * 20)
        text.append("█" * bar_len, style=color)
        text.append("\n")
    return text

def make_layout() -> Layout:
    layout = Layout(name="root")
    layout.split_column(
        Layout(name="tabs", size=1),
        Layout(name="main")
    )
    layout["main"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="right", ratio=1)
    )
    # Left side: Research Agents & Average Score
    layout["left"].split_column(
        Layout(name="research_agents", ratio=2),
        Layout(name="avg_score", size=6),
        Layout(name="model_details", ratio=2)
    )
    # Right side: Explorer (Map)
    layout["right"].split_column(
        Layout(name="explorer_header", size=4),
        Layout(name="map_view", ratio=4),
        Layout(name="stats_row", size=10)
    )
    layout["stats_row"].split_row(
        Layout(name="legend"),
        Layout(name="vp_contents")
    )
    return layout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--round-id", type=str, help="Round ID to simulate")
    parser.add_argument("--round-file", type=Path, help="Specific round file (falls back to extracting round ID)")
    parser.add_argument("--queries", type=int, default=8)
    parser.add_argument("--phases", type=int, nargs="+", help="Queries per phase e.g., 4 2 2 for Discover, Improve, Confirm")
    parser.add_argument("--loop-all", action="store_true", help="Loop through all available rounds")
    parser.add_argument("--rounds-dir", type=Path, default=Path("data/rounds"))
    # --- Exploration Settings (used if no phases defined) ---
    parser.add_argument("--temperature", type=float, default=1.0, help="Scale logits before entropy (T > 1 softens, T < 1 sharpens)")
    parser.add_argument("--blur-sigma", type=float, default=0.0, help="Gaussian blur sigma for spatial smoothing of utility")
    parser.add_argument("--ocean-penalty", type=float, default=1.0, help="Multiplier for utility on ocean tiles (e.g. 0.1 to avoid oceans)")
    parser.add_argument("--predictor", type=str, choices=["unet", "gnn"], default="unet", help="Which neural predictor to use")
    parser.add_argument("--discount-decay", type=float, default=0.0, help="Soft decay factor for discount around previous queries")
    args = parser.parse_args()

    round_ids = []
    if args.loop_all:
        for f in args.rounds_dir.glob("*_seed0_analysis.json"):
            round_ids.append(f.stem.split('_')[0])
    elif args.round_id:
        round_ids.append(args.round_id)
    elif args.round_file:
        round_ids.append(args.round_file.stem.split('_')[0])
    else:
        print("Must provide --round-id, --round-file, or --loop-all")
        sys.exit(1)

    total_queries = sum(args.phases) if args.phases else args.queries

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
        for round_idx, round_id in enumerate(round_ids):
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

                for step in range(total_queries + 1):
                    current_phase = 0
                    phase_name = "Default"
                    if args.phases:
                        accum = 0
                        for p_idx, p_queries in enumerate(args.phases):
                            accum += p_queries
                            if step < accum:
                                current_phase = p_idx
                                break
                        else:
                            current_phase = len(args.phases) - 1
                            
                        if current_phase == 0:
                            phase_name = "Discover"
                            p_temp = 1.2
                            p_blur = 1.5
                            p_ocean = 0.1
                            p_decay = 1.5
                        elif current_phase == 1:
                            phase_name = "Improve"
                            p_temp = 1.0
                            p_blur = 0.5
                            p_ocean = 0.5
                            p_decay = 0.5
                        else:
                            phase_name = "Confirm"
                            p_temp = 0.8
                            p_blur = 0.0
                            p_ocean = 1.0
                            p_decay = 0.0
                    else:
                        p_temp = args.temperature
                        p_blur = args.blur_sigma
                        p_ocean = args.ocean_penalty
                        p_decay = args.discount_decay

                    if args.predictor == "gnn":
                        pred = build_prediction_tensor_gnn(
                            initial_grid.tolist(), 
                            observations=observations, 
                            floor=1e-5
                        )
                    else:
                        pred = build_prediction_tensor_attn_unet(
                            initial_grid.tolist(), 
                            observations=observations, 
                            floor=1e-5
                        )                    
                    if p_temp != 1.0:
                        logits = np.log(np.clip(pred, 1e-12, 1.0))
                        logits = logits / p_temp
                        pred_exp = np.exp(logits)
                        pred = pred_exp / np.sum(pred_exp, axis=-1, keepdims=True)
                        
                    ent = entropy_map(pred)
                    max_ent = np.max(ent) if np.max(ent) > 0 else 1.0
                    argmax = np.argmax(pred, axis=-1)
                    
                    next_vp = None
                    if step < total_queries:
                        utility = ent * discount
                        
                        if p_ocean != 1.0:
                            ocean_mask = (initial_grid == 10)
                            utility[ocean_mask] *= p_ocean
                            
                        if p_blur > 0:
                            utility = gaussian_filter(utility, sigma=p_blur)
                            
                        best_score = -1
                        for (vx, vy) in vp_candidates:
                            if (vx, vy) in viewports: continue
                            score = np.sum(utility[vy:vy+15, vx:vx+15])
                            if score > best_score:
                                best_score = score
                                next_vp = (vx, vy)
                    
                    layout["research_agents"].update(Panel(
                        Text("X Research Agents - Autonomous AI Experimenters\n", style="bold yellow") + 
                        Text("● g:Gemini Researcher   a:ADK Agent   m:Multi Researcher\n", style="dim") +
                        Text("Google ADK framework agent for systematic algorithm exploration\n", style="italic dim") +
                        Text(f"\n● Running... Round {round_idx+1}/{len(round_ids)} Seed {seed_idx} Step {step}/{total_queries} [{phase_name}]\n", style="green"),
                        title="Research", box=box.HORIZONTALS
                    ))
                    
                    avg_score_text = Text(f"Total: 95  ✓: 94  X: 1  ↑: 13\n↑ Best: 91.488\n", style="yellow")
                    layout["avg_score"].update(Panel(avg_score_text, title="Average Score", box=box.ROUNDED))
                    layout["model_details"].update(build_model_table())
                    
                    explorer_hdr = Text(f"f Astar Island Explorer\n", style="bold yellow")
                    explorer_hdr.append(f"Round {round_idx+1} (active)  ID: {round_id}\n", style="dim")
                    seeds = Text()
                    for i in range(5):
                        style = "black on cyan" if i == seed_idx else "dim"
                        seeds.append(f" Seed {i} ", style=style)
                        seeds.append(" ")
                    explorer_hdr.append(seeds)
                    layout["explorer_header"].update(explorer_hdr)
                    
                    map_txt = build_grid_text(initial_grid, viewports, next_vp, mode="pred", argmax=argmax)
                    layout["map_view"].update(map_txt)
                    
                    legend_txt = Text("R Terrain Legend\n", style="bold yellow")
                    for val in [10, 11, 1, 2, 3, 4, 5]:
                        char, color = get_cell_style(val)
                        name = CLASS_NAMES.get(val, "Unknown")
                        legend_txt.append(f"{char} {name}\n", style=color)
                    
                    covered = np.zeros_like(initial_grid)
                    for vx, vy in viewports:
                        covered[vy:vy+15, vx:vx+15] = 1
                    coverage = np.mean(covered) * 100
                    legend_txt.append(f"\nCoverage: {coverage:.1f}%\n", style="bold yellow")
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
                    
                    if p_decay > 0:
                        y_idx, x_idx = np.indices((h, w))
                        cy, cx = vy + 7.5, vx + 7.5
                        dists = np.sqrt((y_idx - cy)**2 + (x_idx - cx)**2)
                        decay_mask = np.clip(dists / (15.0 * p_decay), 0, 1)
                        discount *= decay_mask
                        discount[vy:vy+15, vx:vx+15] *= 0.0
                    else:
                        discount[vy:vy+15, vx:vx+15] *= 0.0
                    
                time.sleep(1.0)

if __name__ == "__main__":
    main()
