# ActivitySim
# See full license in LICENSE.txt.

import logging
import os

import pandas as pd

from activitysim.core import simulate as asim
from activitysim.core import tracing
from activitysim.core import pipeline
from activitysim.core import config
from activitysim.core import inject

from .util.cdap import run_cdap
from .util import expressions

logger = logging.getLogger(__name__)


@inject.injectable()
def cdap_indiv_spec(configs_dir):
    """
    spec to compute the activity utilities for each individual hh member
    with no interactions with other household members taken into account
    """
    return asim.read_model_spec(configs_dir, 'cdap_indiv_and_hhsize1.csv')


@inject.injectable()
def cdap_interaction_coefficients(configs_dir):
    """
    Rules and coefficients for generating interaction specs for different household sizes
    """
    f = os.path.join(configs_dir, 'cdap_interaction_coefficients.csv')
    return pd.read_csv(f, comment='#')


@inject.injectable()
def cdap_fixed_relative_proportions(configs_dir):
    """
    spec to compute/specify the relative proportions of each activity (M, N, H)
    that should be used to choose activities for additional household members
    not handled by CDAP

    This spec is handled much like an activitysim logit utility spec,
    EXCEPT that the values computed are relative proportions, not utilities
    (i.e. values are not exponentiated before being normalized to probabilities summing to 1.0)
    """
    return asim.read_model_spec(configs_dir, 'cdap_fixed_relative_proportions.csv')


@inject.step()
def cdap_simulate(persons_merged, persons, households,
                  cdap_indiv_spec,
                  cdap_interaction_coefficients,
                  cdap_fixed_relative_proportions,
                  chunk_size, trace_hh_id):
    """
    CDAP stands for Coordinated Daily Activity Pattern, which is a choice of
    high-level activity pattern for each person, in a coordinated way with other
    members of a person's household.

    Because Python requires vectorization of computation, there are some specialized
    routines in the cdap directory of activitysim for this purpose.  This module
    simply applies those utilities using the simulation framework.
    """

    trace_label = 'cdap'
    model_settings = config.read_model_settings('cdap.yaml')

    persons_merged = persons_merged.to_frame()

    constants = config.get_model_constants(model_settings)

    logger.info("Running cdap_simulate with %d persons" % len(persons_merged.index))

    choices = run_cdap(persons=persons_merged,
                       cdap_indiv_spec=cdap_indiv_spec,
                       cdap_interaction_coefficients=cdap_interaction_coefficients,
                       cdap_fixed_relative_proportions=cdap_fixed_relative_proportions,
                       locals_d=constants,
                       chunk_size=chunk_size,
                       trace_hh_id=trace_hh_id,
                       trace_label=trace_label)

    # - assign results to persons table and annotate
    persons = persons.to_frame()

    choices = choices.reindex(persons.index)
    persons['cdap_activity'] = choices.cdap_activity
    persons['cdap_rank'] = choices.cdap_rank

    expressions.assign_columns(
        df=persons,
        model_settings=model_settings.get('annotate_persons'),
        trace_label=tracing.extend_trace_label(trace_label, 'annotate_persons'))

    pipeline.replace_table("persons", persons)

    # - annotate households table
    households = households.to_frame()
    expressions.assign_columns(
        df=households,
        model_settings=model_settings.get('annotate_households'),
        trace_label=tracing.extend_trace_label(trace_label, 'annotate_households'))
    pipeline.replace_table("households", households)

    tracing.print_summary('cdap_activity', persons.cdap_activity, value_counts=True)
    print pd.crosstab(persons.ptype, persons.cdap_activity, margins=True)

    if trace_hh_id:

        tracing.trace_df(inject.get_table('persons_merged').to_frame(),
                         label="cdap",
                         columns=['ptype', 'cdap_rank', 'cdap_activity'],
                         warn_if_empty=True)
