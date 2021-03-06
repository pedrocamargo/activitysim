# ActivitySim
# See full license in LICENSE.txt.

import os
import copy
import string
import pandas as pd
import numpy as np

from activitysim.core import tracing
from activitysim.core import inject
from activitysim.core import simulate

from activitysim.core.assign import evaluate_constants
from activitysim.core.util import assign_in_place

import expressions


"""
At this time, these utilities are mostly for transforming the mode choice
spec, which is more complicated than the other specs, into something that
looks like the other specs.
"""


def tour_mode_choice_spec(model_settings):

    configs_dir = inject.get_injectable('configs_dir')

    assert 'SPEC' in model_settings
    return simulate.read_model_spec(configs_dir, model_settings['SPEC'])


def tour_mode_choice_coeffecients_spec(model_settings):

    configs_dir = inject.get_injectable('configs_dir')

    assert 'COEFFS' in model_settings
    coeffs_file_name = model_settings['COEFFS']

    with open(os.path.join(configs_dir, coeffs_file_name)) as f:
        return pd.read_csv(f, comment='#', index_col='Expression')


def run_tour_mode_choice_simulate(
        choosers,
        spec, tour_purpose, model_settings,
        skims,
        constants,
        nest_spec,
        chunk_size,
        trace_label=None, trace_choice_name=None):
    """
    This is a utility to run a mode choice model for each segment (usually
    segments are tour/trip purposes).  Pass in the tours/trip that need a mode,
    the Skim object, the spec to evaluate with, and any additional expressions
    you want to use in the evaluation of variables.
    """

    omnibus_coefficient_spec = tour_mode_choice_coeffecients_spec(model_settings)
    locals_dict = evaluate_constants(omnibus_coefficient_spec[tour_purpose], constants=constants)
    locals_dict.update(constants)
    locals_dict.update(skims)

    assert ('in_period' not in choosers) and ('out_period' not in choosers)
    in_time = skims['in_time_col_name']
    out_time = skims['out_time_col_name']
    choosers['in_period'] = expressions.skim_time_period_label(choosers[in_time])
    choosers['out_period'] = expressions.skim_time_period_label(choosers[out_time])

    annotate_preprocessors(
        choosers, locals_dict, skims,
        model_settings, trace_label)

    choices = simulate.simple_simulate(
        choosers=choosers,
        spec=spec,
        nest_spec=nest_spec,
        skims=skims,
        locals_d=locals_dict,
        chunk_size=chunk_size,
        trace_label=trace_label,
        trace_choice_name=trace_choice_name)

    alts = spec.columns
    choices = choices.map(dict(zip(range(len(alts)), alts)))

    return choices


def annotate_preprocessors(
        tours_df, locals_dict, skims,
        model_settings, trace_label):

    locals_d = {}
    locals_d.update(locals_dict)
    locals_d.update(skims)

    preprocessor_settings = model_settings.get('preprocessor', [])
    if not isinstance(preprocessor_settings, list):
        assert isinstance(preprocessor_settings, dict)
        preprocessor_settings = [preprocessor_settings]

    simulate.set_skim_wrapper_targets(tours_df, skims)

    annotations = None
    for model_settings in preprocessor_settings:

        results = expressions.compute_columns(
            df=tours_df,
            model_settings=model_settings,
            locals_dict=locals_d,
            trace_label=trace_label)

        assign_in_place(tours_df, results)
