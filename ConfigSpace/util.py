from collections import deque
import copy

import numpy as np

from ConfigSpace import Configuration


def impute_inactive_values(configuration, strategy='default'):
    """Impute inactive parameters.

    Parameters
    ----------
    strategy : string, optional (default='default')
        The imputation strategy.

        - If 'default', replace inactive parameters by their default.
        - If float, replace inactive parameters by the given float value,
          which should be able to be splitted apart by a tree-based model.
    """
    values = dict()
    for hp_name in configuration:
        value = configuration[hp_name]
        if value is None:

            if strategy == 'default':
                hp = configuration.configuration_space.get_hyperparameter(
                    hp_name)
                new_value = hp.default

            elif isinstance(strategy, float):
                new_value = strategy

            else:
                raise ValueError('Unknown imputation strategy %s' % str(strategy))

            value = new_value

        values[hp_name] = value

    new_configuration = Configuration(configuration.configuration_space,
                                      values=values,
                                      allow_inactive_with_values=True)
    return new_configuration


def get_one_exchange_neighbourhood(configuration, seed):
    """Return all configurations in a one-exchange neighborhood.

    The method is implemented as defined by:
    Frank Hutter, Holger H. Hoos and Kevin Leyton-Brown
    Sequential Model-Based Optimization for General Algorithm Configuration
    In: Proceedings of the conference on Learning and Intelligent OptimizatioN (LION 5)
    """
    random = np.random.RandomState(seed)
    neighbourhood = []
    for i, hp_name in enumerate(configuration):
        number_of_sampled_neighbors = 0
        iteration = 0
        array = configuration.get_array()

        if not np.isfinite(array[i]):
            continue

        while True:
            hp = configuration.configuration_space.get_hyperparameter(hp_name)
            num_neighbors = hp.get_num_neighbors()

            # Obtain neigbors differently for different possible numbers of
            # neighbors
            if num_neighbors == 0:
                break
            elif np.isinf(num_neighbors):
                num_samples = 4 - number_of_sampled_neighbors
                if num_samples <= 0:
                    break
                neighbors = hp.get_neighbors(array[i], random,
                                             number=num_samples)
            else:
                if number_of_sampled_neighbors > 0:
                    break
                neighbors = hp.get_neighbors(array[i], random)

            # Check all newly obtained neigbors
            for neighbor in neighbors:
                new_array = array.copy()
                new_array[i] = neighbor

                # Activate hyperparameters if their parent node got activated
                children = configuration.configuration_space.get_children_of(
                    hp_name)

                if len(children) > 0:
                    to_visit = deque()
                    to_visit.extendleft(children)
                    while len(to_visit) > 0:
                        current = to_visit.pop()
                        current_idx = \
                            configuration.configuration_space.get_idx_by_hyperparameter_name(current.name)
                        current_value = new_array[current_idx]

                        conditions = configuration.configuration_space.\
                            _get_parent_conditions_of(current.name)

                        active = True
                        for condition in conditions:
                            parent_names = [c.parent.name for c in
                                            condition.get_descendant_literal_conditions()]

                            parents = {parent_name: configuration[parent_name] for
                                       parent_name in parent_names}

                            # if one of the parents is None, the hyperparameter cannot be
                            # active! Else we have to check this
                            if any([parent_value is None for parent_value in
                                    parents.values()]):
                                active = False

                            else:
                                if not condition.evaluate(parents):
                                    active = False


                        if active and current_value is None:
                            default = \
                                current._inverse_transform(
                                    current.default)
                            new_array[current_idx] = default
                            children = configuration.configuration_space.get_children_of(
                                current.name)
                            if len(children) > 0:
                                to_visit.extendleft(children)

                        if not active and current_value is not None:
                            new_array[current_idx] = np.NaN


                try:
                    new_configuration = Configuration(
                        configuration.configuration_space, vector=new_array)
                    neighbourhood.append(new_configuration)
                    number_of_sampled_neighbors += 1
                except ValueError as e:
                    pass

                if iteration > 10000:
                    raise ValueError('Infinite loop!')
                iteration += 1

    return neighbourhood



def get_random_neighbor(configuration, seed):
    """Draw a random neighbor by changing one parameter of a configuration.

    * If the parameter is categorical, it changes it to another value.
    * If the parameter is ordinal, it changes it to the next higher or lower
      value.
    * If parameter is a float, draw a random sample

    If changing a parameter activates new parameters or deactivates
    previously active parameters, the configuration will be rejected. If more
    than 10000 configurations were rejected, this function raises a
    ValueError.

    Parameters
    ----------
    configuration : Configuration

    seed : int
        Used to generate a random state.

    Returns
    -------
    Configuration
        The new neighbor.

    """
    random = np.random.RandomState(seed)
    rejected = True
    values = copy.deepcopy(configuration.get_dictionary())

    while rejected:
        # First, choose an active hyperparameter
        active = False
        iteration = 0
        while not active:
            iteration += 1
            if configuration._num_hyperparameters > 1:
                rand_idx = random.randint(0,
                                          configuration._num_hyperparameters - 1)
            else:
                rand_idx = 0

            value = configuration.get_array()[rand_idx]
            if np.isfinite(value):
                active = True

                hp_name = configuration.configuration_space \
                    .get_hyperparameter_by_idx(rand_idx)
                hp = configuration.configuration_space.get_hyperparameter(hp_name)

                # Only choose if there is a possibility of finding a neigboor
                if not hp.has_neighbors():
                    active = False

            if iteration > 10000:
                raise ValueError('Probably caught in an infinite loop.')
        # Get a neighboor and adapt the rest of the configuration if necessary
        neighbor = hp.get_neighbors(value, random, number=1, transform=True)[0]
        previous_value = values[hp.name]
        values[hp.name] = neighbor

        try:
            new_configuration = Configuration(
                configuration.configuration_space, values=values)
            rejected = False
        except ValueError as e:
            values[hp.name] = previous_value

    return new_configuration



