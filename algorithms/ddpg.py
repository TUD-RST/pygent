import numpy as np
import torch
import torch.nn as nn
import matplotlib.pyplot as plt
import os
import pickle
import inspect
from shutil import copyfile

# pygent
from agents import Agent
from data import DataSet
from algorithms.core import Algorithm
from nn_models import Actor, Critic
from helpers import OUnoise


class DDPG(Algorithm):
    """ Deep Deterministic Policy Gradient - Implementation based on PyTorch (https://pytorch.org)

    Paper: Lillicrap, Timothy P. et al. “Continuous control with deep reinforcement learning.”

    Link: https://arxiv.org/abs/1509.02971

    Attributes:
        xDim (int): state dimension (input dimension of the policy network)
        uDim (int): control/action dimension (output dimension of the policy network)
        uMax (list): control/action limits (uMin = - uMax)
        batch_size (int): size of the minibatch used for training
        agent (Agent):
        a_lr = actor (policy) learning rate
        c_lr = critic (q-function) learning rate
        R (DataSet): data set for storing transition tuples
        plotInterval (int)
        checkInterval (int)
        path (string)
        costScale (int): scale of the cost function (numerical advantage)
        warm_up (int): number of random samples, before training begins

    """

    def __init__(self, environment, t, dt, plotInterval=50, nData=1e6, path='../Results/DDPG/', checkInterval=50,
                 evalPolicyInterval=100, costScale=None, warm_up=5e4, actor_lr=1e-4, critic_lr=1e-3, tau=0.001, batch_size=64,
                 noise_scale=False, terminalQ=True):
        xDim = environment.oDim
        uDim = environment.uDim
        uMax = environment.uMax
        self.batch_size = batch_size
        agent = ActorCriticDDPG(xDim, uDim, torch.Tensor(uMax), dt, batch_size=self.batch_size, actor_lr=actor_lr,
                            critic_lr=critic_lr, tau=tau, noise_scale=noise_scale)
        super(DDPG, self).__init__(environment, agent, t, dt)
        self.R = DataSet(nData)
        self.plotInterval = plotInterval  # inter
        self.evalPolicyInterval = evalPolicyInterval
        self.checkInterval = checkInterval  # checkpoint interval
        self.path = path
        if costScale == None:
            self.costScale = 1/dt
        else:
            self.costScale = costScale
        self.warm_up = warm_up
        if not os.path.isdir(path):
            os.makedirs(path)
        if not os.path.isdir(path + 'plots/'):
            os.makedirs(path + 'plots/')
        if not os.path.isdir(path + 'animations/'):
            os.makedirs(path + 'animations/')
        if not os.path.isdir(path + 'data/'):
            os.makedirs(path + 'data/')
        copyfile(inspect.stack()[-1][1], path + 'exec_script.py')
        self.expCost = []
        self.episode_steps = []
        self.terminalQ = terminalQ

    def run_episode(self):
        """ Run a training episode. If terminal state is reached, episode stops."""

        print('Started episode ', self.episode)
        tt = np.arange(0, self.t, self.dt)
        cost = []  # list of incremental costs
        disc_cost = [] # discounted cost

        # reset environment/agent to initial state, delete history
        self.environment.reset(self.environment.x0)
        self.agent.reset()

        for i, t in enumerate(tt):
            # agent computes control/action
            if self.R.data.__len__() >= self.warm_up:
                u = self.agent.take_noisy_action(self.dt, self.environment.o)
            elif self.evalPolicyInterval % self.episode == 0:
                u = self.agent.take_action(self.dt, self.environment.o)
            else:
                u = self.agent.take_random_action(self.dt)
            # simulation of environment
            c = self.environment.step(self.dt, u)*self.costScale
            cost.append(c)
            disc_cost.append(c*self.agent.gamma**i)
            
            # store transition in data set (x_, u, x, c)
            transition = ({'x_': self.environment.o_, 'u': self.agent.u, 'x': self.environment.o,
                           'c': [c], 't': [self.environment.terminated*self.terminalQ]})

            # add sample to data set
            self.R.force_add_sample(transition)

            # training of the policy network (agent)
            if self.R.data.__len__() >= self.warm_up:
                self.agent.training(self.R)

            # check if environment terminated
            if self.environment.terminated:
                print('Environment terminated!')
                break

        # store the mean of the incremental cost
        self.meanCost.append(np.mean(cost))
        self.totalCost.append(np.sum(disc_cost))
        # todo: create a function in environments, that returns x0, o0
        x = self.environment.observe(self.environment.history[0, :])
        self.expCost.append(self.agent.expCost(x))
        self.episode_steps.append(i)
        self.episode += 1
        pass

    def run_controller(self, x0):
        """ Run an episode, where the policy network is evaluated. """

        print('Started episode ', self.episode)
        tt = np.arange(0, self.t, self.dt)
        cost = []  # list of incremental costs

        # reset environment/agent to initial state, delete history
        self.environment.reset(x0)
        self.agent.reset()

        for i, t in enumerate(tt):
            # agent computes control/action
            u = self.agent.take_action(self.dt, self.environment.o)

            # simulation of environment
            c = self.environment.step(self.dt, u)
            cost.append(c)

            # check if environment terminated
            if self.environment.terminated:
                print('Environment terminated!')
                break
        pass

    def run_learning(self, n):
        """ Learning process.

            Args:
                n (int): number of episodes
        """

        for k in range(1, n + 1):
            self.run_episode()
            # plot environment after episode finished
            print('Samples: ', self.R.data.__len__())
            if k % 10 == 0:
                self.learning_curve()
            if k % self.checkInterval == 0:
                self.save()
                # if self.meanCost[-1] < 0.01: # goal reached
            if k % self.plotInterval == 0:
                self.plot()
                self.animation()
        pass

    def save(self):
        """ Save neural network parameters and data set. """

        # save network parameters
        torch.save({'actor1': self.agent.actor1.state_dict(),
                    'actor2': self.agent.actor2.state_dict(),
                    'critic1': self.agent.critic1.state_dict(),
                    'critic2': self.agent.critic2.state_dict()}, self.path + 'data/checkpoint.pth')

        # save data set
        self.R.save(self.path + 'data/dataSet.p')

        # save learning curve data
        learning_curve_dict = {'totalCost': self.totalCost, 'meanCost':self.meanCost,
                               'expCost': self.expCost, 'episode_steps': self.episode_steps}

        pickle.dump(learning_curve_dict, open(self.path + 'data/learning_curve.p', 'wb'))
        print('Network parameters, data set and learning curve saved.')
        pass

    def load(self):
        """ Load neural network parameters and data set. """

        # load network parameters
        if os.path.isfile(self.path + 'data/checkpoint.pth'):
            checkpoint = torch.load(self.path + 'data/checkpoint.pth')
            self.agent.actor1.load_state_dict(checkpoint['actor1'])
            self.agent.actor2.load_state_dict(checkpoint['actor2'])
            self.agent.critic1.load_state_dict(checkpoint['critic1'])
            self.agent.critic2.load_state_dict(checkpoint['critic2'])
            print('Loaded neural network parameters!')
        else:
            print('Could not load neural network parameters!')

        # load data set
        if os.path.isfile(self.path + 'data/dataSet.p'):
            self.R.load(self.path + 'data/dataSet.p')
            print('Loaded data set!')
        else:
            print('No data set found!')

        # load learning curve
        if os.path.isfile(self.path + 'data/learning_curve.p'):
            learning_curve_dict = pickle.load(open(self.path + 'data/learning_curve.p', 'rb'))
            self.meanCost = learning_curve_dict['meanCost']
            self.totalCost = learning_curve_dict['totalCost']
            self.expCost = learning_curve_dict['expCost']
            self.episode_steps = learning_curve_dict['episode_steps']
            self.episode = self.meanCost.__len__() + 1
            print('Loaded learning curve data!')
        else:
            print('No learning curve data found!')
        self.run_controller(self.environment.x0)
        pass

    def plot(self):
        """ Plots the environment's and agent's history. """

        self.environment.plot()
        plt.savefig(self.path + 'plots/' + str(self.episode - 1) + '_environment.pdf')
        try:
            plt.savefig(self.path + 'plots/' + str(self.episode - 1) + '_environment.pgf')
        except:
            pass
        self.agent.plot()
        plt.savefig(self.path + 'plots/' + str(self.episode - 1) + '_agent.pdf')
        try:
            plt.savefig(self.path + 'plots/' + str(self.episode - 1) + '_agent.pgf')
        except:
            pass
        plt.close('all')
        pass

    def animation(self):
        """ Animation of the environment (if available). """

        ani = self.environment.animation()
        if ani != None:
            try:
                ani.save(self.path + 'animations/' + str(self.episode - 1) + '_animation.mp4', fps=1 / self.dt)
            except:
                ani.save(self.path + 'animations/' + str(self.episode - 1) + '_animation.gif', fps=1 / self.dt)
        plt.close('all')
        pass

    def learning_curve(self):
        """ Plot of the learning curve. """

        fig, ax = plt.subplots(2, 1, dpi=150, sharex=True)
        #x = np.arange(1, self.episode)
        x = np.linspace(1, self.R.data.__len__(), self.episode-1)
        x = np.cumsum(self.episode_steps)

        ax[0].step(x, self.meanCost, 'b', lw=1, label=r'$\frac{1}{N}\sum_{k=0}^N c_k$')
        ax[0].legend(loc='upper left')
        ax[0].grid(True)
        ax[1].step(x, self.totalCost, 'b', lw=1, label=r'$\sum_{k=0}^N\gamma^k c_k$')
        ax[1].step(x, self.expCost, 'r', lw=1, label=r'$\hat{V}(x_0)$')
        ax[1].grid(True)
        ax[1].legend(loc='upper left')
        plt.xlabel(r'Number of Samples')
        plt.savefig(self.path + 'learning_curve.pdf')
        try:
            plt.savefig(self.path + 'learning_curve.pgf')
        except:
            pass
        # todo: save learning curve data
        # todo: plot expected return
        plt.close('all')
        pass


class ActorCriticDDPG(Agent):
    """ Actor-Critic agent. (Specialized for the DDPG algorithm.)

    Critic: Q(x,u), Q-network (multi-layer-perceptron)

    Actor: mu(x), policy network (multi-layer-perceptron)


        Attributes:
            xDim (int): state dimension (input dimension of the policy network)
            uDim (int): control/action dimension (output dimension of the policy network)
            uMax (list): control/action limits (uMin = - uMax)
            actor1 (Actor): policy network for training
            actor2 (Actor): policy network for targets
            critic1 (Critic): Q-network for training
            critic2 (Critic): Q-network for targets
            gamma (float): discount factor
            tau (float): blend factor
            optimCritic (torch.optim.Adam): optimizer for the critic (Q-network)
            optimActor (torch.optim.Adam): optimizer for the actor (policy network)
            noise (OUnoise): noise process for control/action noise
            batch_size (int): size of the minibatch used for training

    """

    def __init__(self, xDim, uDim, uMax, dt, batch_size=64, gamma=0.99, tau=0.001, actor_lr=1e-4, critic_lr=1e-3,
                noise_scale=False):
        super(ActorCriticDDPG, self).__init__(uDim)
        self.xDim = xDim
        self.uMax = uMax
        self.actor1 = Actor(xDim, uDim, uMax)
        self.actor2 = Actor(xDim, uDim, uMax)
        self.blend_hard(self.actor1, self.actor2)  # equate parameters of actor networks
        self.critic1 = Critic(xDim, uDim)
        self.critic2 = Critic(xDim, uDim)
        self.blend_hard(self.critic1, self.critic2)  # equate parameters of critic networks
        self.gamma = gamma  # discount factor
        self.tau = tau  # blend factor
        self.optimCritic = torch.optim.Adam(self.critic1.parameters(), lr=critic_lr, weight_decay=1e-2)
        self.optimActor = torch.optim.Adam(self.actor1.parameters(), lr=actor_lr)
        self.noise = OUnoise(uDim, dt)  # exploration noise
        self.batch_size = batch_size
        self.noise_scale = noise_scale

    def training(self, dataSet):
        """ Training of the Q-network and policy network.

            Args:
                dataSet (DataSet): data set of transition tuples
        """

        # loss function (mean squared error)
        criterion = nn.MSELoss()

        # create training data/targets
        x_Inputs, uInputs, qTargets = self.training_data(dataSet)

        for epoch in range(1):  # loop over the dataset multiple times
            # output of the Q-network
            qOutputs = self.critic1(x_Inputs, uInputs)
            qOutputs = torch.squeeze(qOutputs)

            # output of the policy network
            muOutputs = self.actor1(x_Inputs)

            self.train() # train mode on (batch normalization)

            # definition of loss functions
            lossCritic = criterion(qOutputs, qTargets)
            lossActor = self.critic1(x_Inputs, muOutputs).mean()  # *-1 when using rewards instead of costs

            # train Q-network
            self.optimCritic.zero_grad()  # delete gradients
            lossCritic.backward()  # error back-propagation
            self.optimCritic.step()  # gradient descent step

            # train policy network
            self.optimActor.zero_grad()  # delete gradients
            lossActor.backward()  # error back-propagation
            self.optimActor.step()  # gradient descent step

            # blend target networks
            self.blend(self.critic1, self.critic2)
            self.blend(self.actor1, self.actor2)

            self.eval() # eval mode on (batch normalization)
        pass

    def train(self):
        """ Set Q-networks and policy networks to 'train' mode.
        Only needed, when networks have a batch normalization layer. """

        self.actor1.train()
        self.actor2.train()
        self.critic1.train()
        self.critic2.train()
        pass

    def eval(self):
        """ Set Q-networks and policy networks to 'eval' mode.
            Only needed, when networks have a batch normalization layer. """

        self.actor1.eval()
        self.actor2.eval()
        self.critic1.eval()
        self.critic2.eval()
        pass

    def blend(self, source, target):
        """ Blend parameters of a target neural network with parameters from a source network.

            Args:
                source (torch.nn.Module): source neural network
                target (torch.nn.Module): target neural network
        """

        for wTarget, wSource in zip(target.parameters(), source.parameters()):
            wTarget.data.copy_(self.tau * wSource.data + (1.0 - self.tau) * wTarget.data)
        pass

    def blend_hard(self, source, target):
        """ Copy parameters from one neural network to another.

                    Args:
                        source (torch.nn.Module): source neural network
                        target (torch.nn.Module): target neural network
        """

        for wTarget, wSource in zip(target.parameters(), source.parameters()):
            wTarget.data.copy_(wSource.data)
        pass

    def take_action(self, dt, x):
        """ Compute the control/action of the policy network (actor).

            Args:
                dt (float): stepsize
                x (ndarray, list): state (input of policy network)

            Returns:
                u (ndarray): control/action
        """

        self.eval()
        x = torch.Tensor([x])
        self.u = np.asarray(self.actor1(x).detach())[0]
        self.history = np.concatenate((self.history, np.array([self.u])))  # save current action in history
        self.tt.extend([self.tt[-1] + dt])  # increment simulation time
        return self.u

    def take_noisy_action(self, dt, x):
        """ Compute the noisy control/action of the policy network (actor).

            Args:
                dt (float): stepsize
                x (ndarray, list): state (input of policy network)

            Returns:
                u (ndarray): noisy control/action
        """

        self.eval()
        x = torch.Tensor([x])
        noise = self.noise.sample()
        u = np.asarray(self.actor1(x).detach())[0] + (1 - self.noise_scale)*noise + self.noise_scale*self.uMax.numpy()*noise
        self.u = np.clip(u, -self.uMax.numpy(), self.uMax.numpy())
        self.history = np.concatenate((self.history, np.array([self.u])))  # save current action in history
        self.tt.extend([self.tt[-1] + dt])  # increment simulation time
        return self.u

    def take_random_action(self, dt):
        """ Compute a random control/action (actor).

            Args:
                dt (float): stepsize
                x (ndarray, list): state (input of policy network)

            Returns:
                u (ndarray): noisy control/action
        """

        self.u = np.random.uniform(-self.uMax, self.uMax, self.uDim)
        self.history = np.concatenate((self.history, np.array([self.u])))  # save current action in history
        self.tt.extend([self.tt[-1] + dt])  # increment simulation time
        return self.u

    def training_data(self, dataSet):
        """ Create training data for the critc (Q-network).

            Args:
                dataSet (DataSet): data set with transition tuples

            Returns:
                x_Inputs (torch.Tensor): state tensor
                uInputs (torch.Tensor): control/action tensor
                qTargets (torch.Tensor): target value tensor for the Q-network
        """

        batch = dataSet.minibatch(self.batch_size)
        x_Inputs = torch.Tensor([sample['x_'] for sample in batch])
        xInputs = torch.Tensor([sample['x'] for sample in batch])
        uInputs = torch.Tensor([sample['u'] for sample in batch])
        costs = torch.Tensor([sample['c'] for sample in batch])
        terminated = torch.Tensor([sample['t'] for sample in batch])
        self.eval()  # evaluation mode (for batch normalization)
        nextQ = self.critic2(xInputs, self.actor2(xInputs)).detach()
        qTargets = costs + self.gamma*(1 - terminated)*nextQ
        qTargets = torch.squeeze(qTargets)
        return x_Inputs, uInputs, qTargets

    def expCost(self, x):
        """ Returns the current estimate for V(x). """
        x = torch.Tensor([x])
        V = self.critic1(x, self.actor1(x)).detach()
        return V