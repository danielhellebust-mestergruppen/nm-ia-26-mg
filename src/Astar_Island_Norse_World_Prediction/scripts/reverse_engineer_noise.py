#!/usr/bin/env python3
"""
EXPERIMENTAL: Procedural Noise Reverse-Engineering (The Hacker Route)
Since Astar Island is procedurally generated using PRNG and noise functions (like Perlin/Simplex),
this script attempts to treat the initial 40x40 grid as an "optimization target" and uses
Gradient Descent to find the latent noise seed or procedural parameters that generated the island.

If we can guess the noise parameters that created the island, we can theoretically 
simulate the entire 50-year game forward deterministically with 100% accuracy, bypassing
the need for neural networks entirely.
"""

import argparse
import json
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

class MockIslandGenerator(nn.Module):
    """
    A differentiable approximation of the Astar Island procedural generator.
    In a real scenario, this would be a heavily engineered cellular automata
    or a continuous noise function (like a differentiable Perlin noise).
    """
    def __init__(self, latent_dim=16):
        super().__init__()
        # We assume the island is generated from a small vector of latent parameters (seed)
        self.latent_to_grid = nn.Sequential(
            nn.Linear(latent_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 40 * 40 * 6), # 6 classes per tile
        )
        
    def forward(self, latent_vector):
        x = self.latent_to_grid(latent_vector)
        x = x.view(-1, 6, 40, 40)
        return torch.softmax(x, dim=1)

def reverse_engineer_grid(initial_grid: np.ndarray, steps=1000):
    print("Initiating Reverse-Engineering Sequence...")
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    # Target grid as a one-hot tensor
    h, w = initial_grid.shape
    target = torch.zeros(1, 6, h, w, device=device)
    for y in range(h):
        for x in range(w):
            v = initial_grid[y, x]
            c = {0:0, 10:0, 11:0, 1:1, 2:2, 3:3, 4:4, 5:5}.get(int(v), 0)
            target[0, c, y, x] = 1.0
            
    # The Model (our differentiable proxy for the game engine)
    generator = MockIslandGenerator().to(device)
    
    # The Latent Seed (What we are trying to guess)
    # We use gradient descent to alter the seed until the generator outputs our target grid
    latent_seed = torch.randn(1, 16, device=device, requires_grad=True)
    
    optimizer = optim.Adam([latent_seed], lr=0.05)
    criterion = nn.MSELoss()
    
    for step in range(steps):
        optimizer.zero_grad()
        
        # Generate an island from our current guessed seed
        simulated_island = generator(latent_seed)
        
        # How far off is our simulated island from the actual target island?
        loss = criterion(simulated_island, target)
        
        loss.backward()
        optimizer.step()
        
        if (step+1) % 200 == 0:
            print(f"Hacking Step {step+1}/{steps} | Loss: {loss.item():.4f}")
            
    print(f"\nFinal Guessed Latent Seed Vector: {latent_seed[0].detach().cpu().numpy()[:4]}...")
    print("If this loss reaches 0.0, we have successfully reverse-engineered the Astar Island procedural generator!")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds-dir", default="data/rounds", type=str)
    args = parser.parse_args()
    
    rounds_dir = Path(args.rounds_dir)
    files = list(rounds_dir.glob("*_analysis.json"))
    if not files:
        print("No rounds found.")
        return
        
    fp = files[-1] # Pick the most recent round
    data = json.loads(fp.read_text())
    initial_grid = np.asarray(data["initial_grid"])
    
    print(f"Targeting Round: {data['round_id']}")
    reverse_engineer_grid(initial_grid)

if __name__ == "__main__":
    main()
