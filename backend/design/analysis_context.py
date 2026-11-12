"""Keep supplied board references out of visual component identification.

Photographed boards remain observable components. Only the application's board
catalogue and electrical/runtime profiles are deferred until circuit design.
"""
from copy import deepcopy


def component_references(catalog):
    return {'entries':[deepcopy(entry) for entry in catalog['entries']
                       if entry.get('placement') not in {'board','board_artwork_only'}
                       and entry.get('category') not in {'board','boards'}],
            'notice':'부품 이름 비교용 참고 목록입니다. 사진 속 존재·정확한 모델·핀·정격의 근거가 아니며 목록 밖 부품도 허용합니다.'}


def observation_context(mode, assets, workflow, catalog):
    workflow=deepcopy(workflow)
    workflow.pop('board_workflow',None)
    return {'mode':mode,'stage':'component_observation','workflow':workflow,
            'assets':deepcopy(assets),
            'purpose':'보드 선택 참고자료 없이 사진에 실제 보이는 구성품을 먼저 식별합니다. 기능과 회로는 목록 확정 후 설계합니다.',
            'simulator_catalog':component_references(catalog)}
