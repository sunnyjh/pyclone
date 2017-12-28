'''
Created on 2013-04-23

@author: Andrew Roth
'''
import os
import pandas as pd
import warnings

warnings.filterwarnings('ignore', category=pd.io.pytables.PerformanceWarning)


class DiskTrace(object):

    def __init__(self, file_name, mode='r'):
        if mode == 'w':
            if os.path.exists(file_name):
                raise Exception('Trace file {} exists. Remove the file or specify another location.'.format(file_name))

        self._store = pd.HDFStore(file_name, complevel=9, mode=mode)

        if mode == 'w':
            self._idx = 0

        else:
            self._idx = len(self['alpha'])

    def __getitem__(self, key):
        return self._store[key]

    @property
    def cancer_cell_fractions(self):
        result = {}

        for sample in self.samples:
            key = 'params/{}'.format(sample)

            result[sample] = self[key].pivot(values='value', columns='mutation_id', index='idx')

        return result

    @property
    def labels(self):
        return self['labels'].pivot(values='value', columns='mutation_id', index='idx')

    @property
    def mutations(self):
        return self._store['mutations']

    @mutations.setter
    def mutations(self, value):
        self._store['mutations'] = pd.Series(value)

    @property
    def samples(self):
        return self._store['samples']

    @samples.setter
    def samples(self, value):
        self._store['samples'] = pd.Series(value)

    def close(self):
        self._store.close()

    def update(self, state):
        self._store.append('alpha', pd.Series({self._idx: state['alpha']}))

        if state['global_params'] is not None:
            precision = float(state['global_params'].x)

            self._store.append('beta_binomial_precision', pd.Series({self._idx: precision}))

        labels = pd.DataFrame({'mutation_id': self.mutations, 'value': state['labels']})

        labels['idx'] = self._idx

        self._store.append('labels', labels)

        for sample in self.samples:
            sample_params = [data_point_param[sample].x for data_point_param in state['params']]

            sample_params = pd.DataFrame({'mutation_id': self.mutations, 'value': sample_params})

            sample_params['idx'] = self._idx

            self._store.append('params/{}'.format(sample), sample_params)

        self._store['/state/labels'] = pd.Series(state['labels'], index=self.mutations)

        self._store['/state/params'] = pd.Series(state['params'], index=self.mutations)

        self._idx += 1
