# ActivitySim
# See full license in LICENSE.txt.

import os
import logging

import pandas as pd
import numpy as np

from activitysim.core.simulate import read_model_spec
from activitysim.core.interaction_simulate import interaction_simulate

from activitysim.core import simulate
from activitysim.core import tracing
from activitysim.core import pipeline
from activitysim.core import config
from activitysim.core import inject

from activitysim.core.util import reindex

from .util.tour_frequency import process_atwork_subtours

logger = logging.getLogger(__name__)


@inject.injectable()
def atwork_subtour_frequency_spec(configs_dir):
    return read_model_spec(configs_dir, 'atwork_subtour_frequency.csv')


@inject.injectable()
def atwork_subtour_frequency_alternatives(configs_dir):
    # alt file for building tours even though simulation is simple_simulate not interaction_simulate
    f = os.path.join(configs_dir, 'atwork_subtour_frequency_alternatives.csv')
    df = pd.read_csv(f, comment='#')
    df.set_index('alt', inplace=True)
    return df


def add_null_results(trace_label, tours):
    logger.info("Skipping %s: add_null_results" % trace_label)
    tours['atwork_subtour_frequency'] = np.nan
    pipeline.replace_table("tours", tours)


@inject.step()
def atwork_subtour_frequency(tours,
                             persons_merged,
                             atwork_subtour_frequency_spec,
                             atwork_subtour_frequency_alternatives,
                             chunk_size,
                             trace_hh_id):
    """
    This model predicts the frequency of making at-work subtour tours
    (alternatives for this model come from a separate csv file which is
    configured by the user).
    """

    trace_label = 'atwork_subtour_frequency'

    model_settings = config.read_model_settings('atwork_subtour_frequency.yaml')

    tours = tours.to_frame()

    persons_merged = persons_merged.to_frame()

    work_tours = tours[tours.tour_type == 'work']

    # - if no work_tours
    if work_tours.shape[0] == 0:
        add_null_results(trace_label, tours)
        return

    # merge persons into work_tours
    work_tours = pd.merge(work_tours, persons_merged, left_on='person_id', right_index=True)

    logger.info("Running atwork_subtour_frequency with %d work tours" % len(work_tours))

    nest_spec = config.get_logit_model_settings(model_settings)
    constants = config.get_model_constants(model_settings)

    choices = simulate.simple_simulate(
        choosers=work_tours,
        spec=atwork_subtour_frequency_spec,
        nest_spec=nest_spec,
        locals_d=constants,
        chunk_size=chunk_size,
        trace_label=trace_label,
        trace_choice_name='atwork_subtour_frequency')

    # convert indexes to alternative names
    choices = pd.Series(atwork_subtour_frequency_spec.columns[choices.values], index=choices.index)

    tracing.print_summary('atwork_subtour_frequency', choices, value_counts=True)

    # add atwork_subtour_frequency column to tours
    # reindex since we are working with a subset of tours
    tours['atwork_subtour_frequency'] = choices.reindex(tours.index)
    pipeline.replace_table("tours", tours)

    # - create atwork_subtours based on atwork_subtour_frequency choice names
    work_tours = tours[tours.tour_type == 'work']
    assert not work_tours.atwork_subtour_frequency.isnull().any()

    subtours = process_atwork_subtours(work_tours, atwork_subtour_frequency_alternatives)

    tours = pipeline.extend_table("tours", subtours)

    tracing.register_traceable_table('tours', tours)
    pipeline.get_rn_generator().add_channel(subtours, 'tours')

    if trace_hh_id:
        tracing.trace_df(tours,
                         label='atwork_subtour_frequency.tours')
