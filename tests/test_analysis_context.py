from copy import deepcopy

from backend.design.analysis_context import observation_context
from backend.design.simulator_catalog import load_simulator_catalog
from backend.workflow import workflow_stamp


def test_component_observation_filters_board_references_without_mutating_catalog():
    catalog=load_simulator_catalog();workflow=workflow_stamp()
    original_catalog=deepcopy(catalog);original_workflow=deepcopy(workflow)
    assets=[{'id':'image','filename':'observed-board.png'}]
    context=observation_context('photo',assets,workflow,catalog)
    assert 'board_workflow' not in context['workflow']
    assert 'board_profiles' not in context and 'implementation_catalog' not in context
    allowed=[e for e in catalog['entries'] if e['placement'] not in {'board','board_artwork_only'} and e['category'] not in {'board','boards'}]
    assert context['simulator_catalog']['entries']==allowed
    assert len(allowed)<len(catalog['entries'])
    assert catalog==original_catalog and workflow==original_workflow
    # Observed names and source files are evidence, not board references to hide.
    assert context['assets']==assets
    context['assets'][0]['filename']='changed'
    assert assets[0]['filename']=='observed-board.png'
