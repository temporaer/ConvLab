# Modified by Microsoft Corporation.
# Licensed under the MIT license.

from abc import ABC, abstractmethod

import numpy as np
import pydash as ps

from convlab.agent.net import net_util
from convlab.lib import logger, util
from convlab.lib.decorator import lab_api

logger = logger.get_logger(__name__)

# Modified by Microsoft Corporation.
# Licensed under the MIT license.

class Algorithm(ABC):
    '''
    Abstract class ancestor to all Algorithms,
    specifies the necessary design blueprint for agent to work in Lab.
    Mostly, implement just the abstract methods and properties.
    '''

    def __init__(self, agent, global_nets=None):
        '''
        @param {*} agent is the container for algorithm and related components, and interfaces with env.
        '''
        self.agent = agent
        self.algorithm_spec = agent.agent_spec['algorithm']
        self.name = self.algorithm_spec['name']
        self.net_spec = agent.agent_spec.get('net', None)
        if ps.get(agent.agent_spec, 'memory'):
            self.memory_spec = agent.agent_spec['memory']
        self.body = self.agent.body
        self.init_algorithm_params()
        self.init_nets(global_nets)
        logger.info(util.self_desc(self))

    @abstractmethod
    @lab_api
    def init_algorithm_params(self):
        '''Initialize other algorithm parameters'''
        raise NotImplementedError

    @abstractmethod
    @lab_api
    def init_nets(self, global_nets=None):
        '''Initialize the neural network from the spec'''
        raise NotImplementedError

    @lab_api
    def post_init_nets(self):
        '''
        Method to conditionally load models.
        Call at the end of init_nets() after setting self.net_names
        '''
        assert hasattr(self, 'net_names')
        if util.in_eval_lab_modes():
            logger.info(f'Loaded algorithm models for lab_mode: {util.get_lab_mode()}')
            self.load()
        else:
            logger.info(f'Initialized algorithm models for lab_mode: {util.get_lab_mode()}')

    @lab_api
    def calc_pdparam(self, x, evaluate=True, net=None):
        '''
        To get the pdparam for action policy sampling, do a forward pass of the appropriate net, and pick the correct outputs.
        The pdparam will be the logits for discrete prob. dist., or the mean and std for continuous prob. dist.
        '''
        raise NotImplementedError

    def nanflat_to_data_a(self, data_name, nanflat_data_a):
        '''Reshape nanflat_data_a, e.g. action_a, from a single pass back into the API-conforming data_a'''
        data_names = (data_name,)
        data_a, = self.agent.agent_space.aeb_space.init_data_s(data_names, a=self.agent.a)
        for body, data in zip(self.agent.nanflat_body_a, nanflat_data_a):
            e, b = body.e, body.b
            data_a[(e, b)] = data
        return data_a

    @lab_api
    def act(self, state):
        '''Standard act method.'''
        raise NotImplementedError
        return action

    @abstractmethod
    @lab_api
    def sample(self):
        '''Samples a batch from memory'''
        raise NotImplementedError
        return batch

    @abstractmethod
    @lab_api
    def train(self):
        '''Implement algorithm train, or throw NotImplementedError'''
        if util.in_eval_lab_modes():
            return np.nan
        raise NotImplementedError

    @abstractmethod
    @lab_api
    def update(self):
        '''Implement algorithm update, or throw NotImplementedError'''
        raise NotImplementedError

    @lab_api
    def save(self, ckpt=None):
        '''Save net models for algorithm given the required property self.net_names'''
        if not hasattr(self, 'net_names'):
            logger.info('No net declared in self.net_names in init_nets(); no models to save.')
        else:
            net_util.save_algorithm(self, ckpt=ckpt)

    @lab_api
    def load(self):
        '''Load net models for algorithm given the required property self.net_names'''
        if not hasattr(self, 'net_names'):
            logger.info('No net declared in self.net_names in init_nets(); no models to load.')
        else:
            net_util.load_algorithm(self)
        # set decayable variables to final values
        for k, v in vars(self).items():
            if k.endswith('_scheduler'):
                var_name = k.replace('_scheduler', '')
                if hasattr(v, 'end_val'):
                    setattr(self.body, var_name, v.end_val)

    # NOTE optional extension for multi-agent-env

    @lab_api
    def space_act(self, state_a):
        '''Interface-level agent act method for all its bodies. Resolves state to state; get action and compose into action.'''
        data_names = ('action',)
        action_a, = self.agent.agent_space.aeb_space.init_data_s(data_names, a=self.agent.a)
        for eb, body in util.ndenumerate_nonan(self.agent.body_a):
            state = state_a[eb]
            self.body = body
            action_a[eb] = self.act(state)
        # set body reference back to default
        self.body = self.agent.nanflat_body_a[0]
        return action_a

    @lab_api
    def space_sample(self):
        '''Samples a batch from memory'''
        batches = []
        for body in self.agent.nanflat_body_a:
            self.body = body
            batches.append(self.sample())
        # set body reference back to default
        self.body = self.agent.nanflat_body_a[0]
        batch = util.concat_batches(batches)
        batch = util.to_torch_batch(batch, self.net.device, self.body.memory.is_episodic)
        return batch

    @lab_api
    def space_train(self):
        if util.in_eval_lab_modes():
            return np.nan
        losses = []
        for body in self.agent.nanflat_body_a:
            self.body = body
            losses.append(self.train())
        # set body reference back to default
        self.body = self.agent.nanflat_body_a[0]
        loss_a = self.nanflat_to_data_a('loss', losses)
        return loss_a

    @lab_api
    def space_update(self):
        explore_vars = []
        for body in self.agent.nanflat_body_a:
            self.body = body
            explore_vars.append(self.update())
        # set body reference back to default
        self.body = self.agent.nanflat_body_a[0]
        explore_var_a = self.nanflat_to_data_a('explore_var', explore_vars)
        return explore_var_a
