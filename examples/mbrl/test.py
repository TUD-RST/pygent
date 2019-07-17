from pygent.environments import CartPole
from pygent.algorithms.ddpg import DDPG
from pygent.algorithms.mbrl import MBRL
from pygent.data import DataSet
from pygent.helpers import mapAngles
import numpy as np
import torch
import torch.nn as nn
# define the incremental cost
def c_k(x, u):
    x1, x2, x3, x4 = x
    u1, = u
    c = 0.5*x1**2 + x2**2 + 0.02*x3**2 + 0.05*x4**2 + 0.05*u1**2
    return c

def c_N(x):
    x1, x2, x3, x4 = x
    c = 100*x1**2 + 100*x2**2 + 10*x3**2 + 10*x4**2
    return c

# define the function, that represents the initial value distribution p(x_0)
def p_x0():
    x0 = [np.random.uniform(-0.01, 0.01), np.random.uniform(0.99*np.pi, 1.01*np.pi), 0, 0]
    return x0



t = 10 # time of an episode
dt = 0.02 # time step-size

env = CartPole(c_k, p_x0, dt)


env.terminal_cost = 200 # define the terminal cost if x(k+1) is a terminal state

path = '../../../results/mbrl'  # path, where results are saved

rl_algorithm = MBRL(env, t, dt, path=path) # instance of the DDPG algorithm

rl_algorithm.run_learning(1e6)
