'''
Created on 2012-02-08

@author: Andrew Roth
'''
from collections import OrderedDict
from pydp.data import GammaData

try:
    from yaml import CDumper as Dumper

except ImportError:
    from yaml import Dumper

import csv
import numpy as np
import os
import random
import yaml

from pyclone.config import get_mutation
from pyclone.utils import make_directory, make_parent_directory

import pyclone.config
import pyclone.post_process.clusters
import pyclone.post_process.plot
import pyclone.pyclone_beta_binomial
import pyclone.pyclone_binomial
import pyclone.trace


def resume_analysis(config_file, num_iters, trace_file):
    config = pyclone.config.PyCloneConfig(config_file)

    trace = pyclone.trace.DiskTrace(trace_file, mode='a')

    trace.mutations = config.mutations

    trace.samples = config.samples

    state = {
        'alpha': trace['alpha'].iloc[-1],
        'labels': trace['/state/labels'],
        'params': trace['/state/params']
    }

    if config.density == 'pyclone_beta_binomial':
        sampler = pyclone.pyclone_beta_binomial.load_sampler(config)

        state['global_params'] = GammaData(trace['beta_binomial_precision'].iloc[-1])

    elif config.density == 'pyclone_binomial':
        sampler = pyclone.pyclone_binomial.load_sampler(config)

        state['global_params'] = None

    else:
        raise Exception('{0} is not a valid density for PyClone.'.format(config.density))

    sampler.state = state

    _run_mcmc(config, num_iters, sampler, trace)

    print(trace['alpha'])

    trace.close()


def run_analysis(config_file, num_iters, trace_file, seed):
    if seed is not None:
        random.seed(seed)

    config = pyclone.config.PyCloneConfig(config_file)

    trace = pyclone.trace.DiskTrace(trace_file, mode='w')

    trace.mutations = config.mutations

    trace.samples = config.samples

    if config.density == 'pyclone_beta_binomial':
        sampler = pyclone.pyclone_beta_binomial.load_sampler(config)

    elif config.density == 'pyclone_binomial':
        sampler = pyclone.pyclone_binomial.load_sampler(config)

    else:
        raise Exception('{0} is not a valid density for PyClone.'.format(config.density))

    sampler.initialise_partition(config.init_method, len(config.data))

    _run_mcmc(config, num_iters, sampler, trace)

    print(trace['alpha'])

    print(trace.labels.iloc[-1])

    cellular_prevalences = trace.cellular_prevalences

    for sample in trace.samples:
        print(sample)
        print(cellular_prevalences[sample].iloc[-1])

    trace.close()


def _run_mcmc(config, num_iters, sampler, trace):
    print('Beginning analysis using:')
    print('{} mutations'.format(len(config.mutations)))
    print('{} sample(s)'.format(len(config.samples)))
    print()

    for i in range(num_iters):
        sampler.interactive_sample(list(config.data.values()))

        state = sampler.state

        trace.update(state)

        if i % 100 == 0:
            print('Iteration: {}'.format(i))
            print('Number of clusters: {}'.format(len(np.unique(state['labels']))))
            print('DP concentration: {}'.format(state['alpha']))
            if state['global_params'] is not None:
                print('Beta-Binomial precision: {}'.format(state['global_params'][0]))
            print()


def setup_analysis(
        density,
        in_files,
        init_method,
        out_dir,
        prior,
        samples,
        tumour_contents,
        config_extras_file=None):

    make_directory(out_dir)

    make_directory(os.path.join(out_dir, 'yaml'))

    mutations_files = OrderedDict()

    if len(samples) == 0:
        samples = [os.path.basename(x).split('.')[0] for x in in_files]

    if len(tumour_contents) == 0:
        tumour_contents = [1.0 for _ in samples]

    tumour_contents = dict(zip(samples, tumour_contents))

    for in_file, sample_id in zip(in_files, samples):
        mutations_files[sample_id] = os.path.join(out_dir, 'yaml', '{}.yaml'.format(sample_id))

        _build_mutations_file(
            in_file,
            mutations_files[sample_id],
            prior
        )

    config_file = os.path.join(out_dir, 'config.yaml')

    _write_config_file(
        config_file,
        density,
        init_method,
        mutations_files,
        tumour_contents,
        config_extras_file=config_extras_file,
    )

    return config_file


def _write_config_file(
        config_file,
        density,
        init_method,
        mutations_files,
        tumour_contents,
        config_extras_file=None):

    config = {}

    config['base_measure_params'] = {'a': 1, 'b': 1}

    config['concentration'] = {
        'value': 1.0,
        'prior': {
            'shape': 1.0,
            'rate': 0.001
        }
    }

    config['density'] = density

    if density == 'pyclone_beta_binomial':
        config['beta_binomial_precision'] = {
            'value': 1000,
            'prior': {
                'shape': 1.0,
                'rate': 0.001
            },
            'proposal': {'precision': 0.01}
        }

    config['init_method'] = init_method

    config['samples'] = {}

    for sample_id in mutations_files:
        config['samples'][sample_id] = {
            'mutations_file': mutations_files[sample_id],
            'tumour_content': {
                'value': tumour_contents[sample_id]
            },
            'error_rate': 0.001
        }

    if config_extras_file is not None:
        config.update(yaml.load(open(config_extras_file)))

    with open(config_file, 'w') as fh:
        yaml.dump(config, fh, default_flow_style=False, Dumper=Dumper)


#=======================================================================================================================
# Input file code
#=======================================================================================================================


def build_mutations_file(args):
    _build_mutations_file(
        args.in_file,
        args.out_file,
        args.prior
    )


def _build_mutations_file(in_file, out_file, prior):
    config = {}

    reader = csv.DictReader(open(in_file), delimiter='\t')

    config['mutations'] = []

    for row in reader:
        mutation_id = row['mutation_id']

        ref_counts = int(row['ref_counts'])

        var_counts = int(row['var_counts'])

        normal_cn = int(row['normal_cn'])

        minor_cn = int(row['minor_cn'])

        major_cn = int(row['major_cn'])

        mutation = get_mutation(
            mutation_id,
            ref_counts,
            var_counts,
            normal_cn,
            minor_cn,
            major_cn,
            prior
        )

        config['mutations'].append(mutation.to_dict())

    make_parent_directory(out_file)

    fh = open(out_file, 'w')

    yaml.dump(config, fh, Dumper=Dumper)

    fh.close()

#=======================================================================================================================
# Post processing code
#=======================================================================================================================


def build_table(config_file, trace_file, out_file, table_format, burnin=0, grid_size=101, max_clusters=100, thin=1):
    config = pyclone.config.PyCloneConfig(config_file)

    trace = pyclone.trace.DiskTrace(trace_file)

    if table_format == 'cluster':
        df = pyclone.post_process.clusters.load_summary_table(
            config,
            trace,
            burnin=burnin,
            grid_size=grid_size,
            max_clusters=max_clusters,
            thin=thin,
        )

    elif table_format == 'loci':
        df = pyclone.post_process.loci.load_table(
            config,
            trace,
            burnin=burnin,
            max_clusters=max_clusters,
            old_style=False,
            thin=thin
        )

    elif table_format == 'old':
        df = pyclone.post_process.loci.load_table(
            config,
            trace,
            burnin=burnin,
            max_clusters=max_clusters,
            old_style=True,
            thin=thin
        )

    df.to_csv(out_file, index=False, sep='\t')

    trace.close()


def plot_clusters(
        config_file,
        trace_file,
        out_file,
        burnin=0,
        grid_size=101,
        plot_format='density',
        max_clusters=100,
        min_cluster_size=0,
        samples=[],
        thin=1):

    config = pyclone.config.PyCloneConfig(config_file)

    trace = pyclone.trace.DiskTrace(trace_file)

    kwargs = {
        'burnin': burnin,
        'grid_size': grid_size,
        'max_clusters': max_clusters,
        'min_cluster_size': min_cluster_size,
        'samples': samples,
        'thin': thin
    }

    if plot_format == 'density':
        pyclone.post_process.plot.clusters.density_plot(config, trace, out_file, **kwargs)

    elif plot_format == 'line':
        pyclone.post_process.plot.clusters.parallel_coordinates_plot(
            config, trace, out_file, **kwargs
        )

    elif plot_format == 'scatter':
        pyclone.post_process.plot.clusters.scatter_plot(
            config, trace, out_file, **kwargs
        )

    trace.close()


def plot_loci(
        config_file,
        trace_file,
        out_file,
        plot_format,
        burnin=0,
        max_clusters=None,
        min_cluster_size=0,
        samples=None,
        thin=1):

    config = pyclone.config.PyCloneConfig(config_file)

    trace = pyclone.trace.DiskTrace(trace_file)

    kwargs = {
        'burnin': burnin,
        'max_clusters': max_clusters,
        'min_cluster_size': min_cluster_size,
        'samples': samples,
        'thin': thin
    }

    if plot_format.startswith('ccf'):
        kwargs['value'] = 'ccf'

    elif plot_format.startswith('vaf'):
        kwargs['value'] = 'vaf'

    if plot_format == 'ccf_density':
        [kwargs.pop(x) for x in list(kwargs.keys()) if 'cluster' in x]

        kwargs.pop('value')

        pyclone.post_process.plot.loci.density_plot(
            trace,
            out_file,
            **kwargs
        )

    elif plot_format in ['ccf_line', 'vaf_line']:
        pyclone.post_process.plot.loci.parallel_coordinates_plot(
            config,
            trace,
            out_file,
            **kwargs
        )

    elif plot_format in ['ccf_scatter', 'vaf_scatter']:
        pyclone.post_process.plot.loci.scatter_plot(
            config,
            trace,
            out_file,
            **kwargs
        )

    elif plot_format == 'similarity_matrix':
        kwargs.pop('samples')

        pyclone.post_process.plot.loci.similarity_matrix_plot(
            trace,
            out_file,
            **kwargs
        )

    trace.close()
