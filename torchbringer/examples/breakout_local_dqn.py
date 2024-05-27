# Based on Mnih, Volodymyr, et al. "Playing atari with deep reinforcement learning." arXiv preprint arXiv:1312.5602 (2013).

import gymnasium as gym
from itertools import count
from aim import Run

import torch
import cv2
import numpy as np

from torchbringer.servers.torchbringer_agent import TorchBringerAgent

class AtariEnv():
    def __init__(self, name, stacked_frames, frames_clipped):
        self.env = gym.make(name)

        self.past_frames = []
        self.stacked_frames = stacked_frames
        self.frames_clipped = frames_clipped
    

    def preprocess_state(self, state):
        return cv2.resize(cv2.cvtColor(state, cv2.COLOR_RGB2GRAY), (110, 84))[:, 13:97]


    def get_current_state(self):
        return np.array(self.past_frames)


    def step(self, action):
        total_reward = 0.0
        for i in range(self.frames_clipped):
            observation, reward, terminated, truncated, info = self.env.step(action)

            if reward > 0:
                reward = 1.0
            if reward < 0:
                reward = -1.0
            total_reward += reward

            if terminated or truncated:
                break

        self.past_frames[:self.stacked_frames-1, :, :] = self.past_frames[1:self.stacked_frames, :, :]
        self.past_frames[self.stacked_frames-1, :, :] = self.preprocess_state(observation)

        return self.get_current_state(), total_reward, terminated, truncated, info


    def reset(self):
        state, info = self.env.reset()
        self.past_frames = np.zeros((self.stacked_frames, 84, 84))
        self.past_frames[:, :, :] = self.preprocess_state(state)

        return self.get_current_state(), info

# if GPU is to be used
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

env = AtariEnv("ALE/Breakout-v5", 4, 4)
state, info = env.reset()

config = {
    "type": "dqn",
    "action_space": {
        "type": "discrete",
        "n": 4
    },
    "gamma": 0.99,
    "tau": 0.005,
    "epsilon": {
        "type": "lin_decrease",
        "start": 1.0,
        "end": 0.1,
        "steps_to_end": 1000000
    },
    "batch_size": 32,
    "grad_clip_value": 100,
    "loss": "smooth_l1_loss",
    "optimizer": {
        "type": "adamw",
        "lr": 1e-4, 
        "amsgrad": True
    },
    "replay_buffer_size": 1000000,
    "network": [
        {
            "type": "conv2d",
            "in_channels": 4,
            "out_channels": 16,
            "kernel_size": 8,
            "stride": 4
        },
        {"type": "relu"},
        {
            "type": "conv2d",
            "in_channels": 16,
            "out_channels": 32,
            "kernel_size": 4,
            "stride": 1
        },
        {"type": "relu"},
        {"type": "flatten"},
        {
            "type": "linear",
            "in_features": 9248, 
            "out_features": 256
        },
        {"type": "relu"},
        {
            "type": "linear",
            "in_features": 256,
            "out_features": 4,
        }
    ]
}

dqn = TorchBringerAgent()
dqn.initialize(config)
run = Run(experiment="DQN Breakout")

run["hparams"] = config

steps_done = 0

if torch.cuda.is_available():
    print("Running on GPU!")
    num_episodes = 600
else:
    print("Running on CPU!")
    num_episodes = 50

for i_episode in range(num_episodes):
    # Initialize the environment and get its state
    state, info = env.reset()
    reward = torch.tensor([0.0], device=device)
    terminal = False

    cummulative_reward = 0.0
    
    state = torch.tensor(state, dtype=torch.float32, device=device).unsqueeze(0)
    for t in count():
        observation, reward, terminated, truncated, _ = env.step(dqn.step(state, reward, terminal).item())
        cummulative_reward += reward

        state = None if terminated else torch.tensor(observation, dtype=torch.float32, device=device).unsqueeze(0) 
        reward = torch.tensor([reward], device=device)
        terminal = terminated or truncated

        if terminal:
            run.track({"Episode reward": cummulative_reward}, step=i_episode)

            dqn.step(state, reward, terminal)
            break

print('Complete')