from environments import CartPoleTriple
from algorithms.ilqr import iLQR
import numpy as np
import matplotlib.pyplot as plt


def c_k(x, u):
    x1, x2, x3, x4, x5, x6, x7, x8 = x
    u1, = u
    c =  0.5*(5.*x1**2 + 10.*x2**2 + 10.*x3**2 + 10.*x4**2) + .1*u1**2
    return c


def c_N(x):
    x1, x2, x3, x4, x5, x6, x7, x8 = x
    c = 0.5*(100.*x1**2 + 100.*x2**2 + 100.*x3**2 + 100.*x4**2 + 10.*x5**2 + 10.*x6**2 + 10.*x7**2 + 10.*x8**2)
    return c


x0 = [0, np.pi, np.pi, np.pi, 0, 0, 0, 0]

cartPole = CartPoleTriple(c_k, x0)
t = 3.5
dt = 0.005


path = '../../../results/ilqr/cart_pole_triple/'
controller = iLQR(cartPole, t, dt, constrained=True, fcost=None, path=path, maxIters=500)

controller.run_optim()

controller.plot()
plt.show()
controller.animation()