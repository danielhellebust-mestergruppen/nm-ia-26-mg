#!/usr/bin/env python3
"""
True Active Learning via Reinforcement Learning (RL) skeleton.
Instead of using entropy or manually crafted heuristics to pick queries,
this script trains an RL Agent (e.g., via PPO) to play a "mini-game".

The Mini-Game:
- State: The current probability map (40x40x6), the distance to coast, and current budget.
- Action: A coordinate (x, y) to place a 15x15 viewport.
- Reward: The delta in the Weighted KL Divergence (the competition metric)
          between the prediction before the query and after the query.
          
The agent naturally learns optimal search strategies (like two-pass, coastal tracing, 
or avoiding overlapping queries) simply by maximizing the mathematical score.
"""

import argparse
import json
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
from typing import List, Tuple

# We would import our UNet or GNN predictor here
# from src.predictor_unet import build_prediction_tensor_unet
from src.scoring import weighted_kl, entropy

class AstarEnvironment:
    """
    Simulates the Astar Island environment for the RL Agent.
    """
    def __init__(self, initial_grid: np.ndarray, ground_truth: np.ndarray, max_budget: int = 50):
        self.initial_grid = initial_grid
        self.ground_truth = ground_truth
        self.max_budget = max_budget
        self.reset()
        
    def reset(self):
        self.budget_remaining = self.max_budget
        self.observations = []
        # Initial prediction without any observations
        self.current_pred = self._get_prediction(self.observations)
        self.current_score = weighted_kl(self.ground_truth, self.current_pred)
        return self._get_state()
        
    def _get_prediction(self, obs: List[dict]) -> np.ndarray:
        # In practice, call build_prediction_tensor_unet/gnn here
        # Return a dummy 40x40x6 prediction for skeleton purposes
        return np.ones((40, 40, 6)) / 6.0
        
    def _get_state(self) -> np.ndarray:
        # State representation for the RL agent (e.g., current prediction map, budget)
        state_tensor = np.concatenate([
            self.current_pred, 
            np.full((40, 40, 1), self.budget_remaining / self.max_budget)
        ], axis=-1)
        return state_tensor

    def step(self, action_x: int, action_y: int) -> Tuple[np.ndarray, float, bool, dict]:
        """
        Executes an action (query placement), returns (next_state, reward, done, info)
        """
        if self.budget_remaining <= 0:
            return self._get_state(), 0.0, True, {}
            
        # 1. Gather observation from ground truth
        h, w = self.initial_grid.shape
        y2, x2 = min(h, action_y + 15), min(w, action_x + 15)
        gt_vp = self.ground_truth[action_y:y2, action_x:x2]
        
        # Simulate argmax observation
        obs_grid = np.argmax(gt_vp, axis=-1)
        
        # 2. Add to observations
        self.observations.append({
            "viewport": {"x": action_x, "y": action_y, "w": 15, "h": 15},
            "grid": obs_grid.tolist()
        })
        
        self.budget_remaining -= 1
        
        # 3. Get new prediction
        new_pred = self._get_prediction(self.observations)
        
        # 4. Calculate reward (KL Divergence Improvement)
        new_score = weighted_kl(self.ground_truth, new_pred)
        reward = self.current_score - new_score # Positive reward if score (divergence) decreases
        
        self.current_pred = new_pred
        self.current_score = new_score
        
        done = (self.budget_remaining <= 0)
        
        return self._get_state(), float(reward), done, {"score": new_score}

class QueryPolicyAgent(nn.Module):
    """
    A simple Policy Network for predicting the next best query location.
    """
    def __init__(self, in_channels=7):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.MaxPool2d(2),
            nn.ReLU(),
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Flatten(),
            nn.Linear(128, 40 * 40) # Predicts logits over the 40x40 grid
        )
        
    def forward(self, state):
        # state: (B, H, W, C)
        x = state.permute(0, 3, 1, 2).float() # (B, C, H, W)
        logits = self.net(x)
        return logits # (B, 1600)

def main():
    parser = argparse.ArgumentParser(description="Skeleton for training an RL agent.")
    parser.add_argument("--rounds-dir", default="data/rounds", type=str)
    args = parser.parse_args()
    
    print("Initializing RL Agent (Skeleton).")
    agent = QueryPolicyAgent()
    optimizer = torch.optim.Adam(agent.parameters(), lr=1e-4)
    
    print("If implemented fully, this script would:")
    print("1. Load historical rounds to act as training environments.")
    print("2. Run PPO (Proximal Policy Optimization) rollouts:")
    print("   a. Agent proposes queries.")
    print("   b. UNet/GNN predictor generates updated maps.")
    print("   c. Calculate Weighted KL Divergence reward.")
    print("3. Backpropagate to optimize the agent's query strategy.")
    print("This enforces a mathematically optimal search without human bias.")

if __name__ == "__main__":
    main()
