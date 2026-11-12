"""Non-persistent candidate designs; these do not certify observed behavior."""
from pydantic import ValidationError

from .function import constrain
from .hypotheses import as_design_target
from .proposals import propose


def candidate_previews(inventory, candidates, allow_completion=False):
    previews = []
    for candidate in candidates:
        try:
            # Selecting a hypothesis is a user action elsewhere. A preview must
            # remain inferred, and must not save a function target or review.
            intent = as_design_target(candidate).model_copy(update={'status': 'INFERRED'})
            result = constrain(propose(inventory,function_kind=intent.kind,allow_completion=allow_completion), intent)
        except (ValueError, ValidationError):
            continue
        if not result['proposals']:
            continue
        proposal = result['proposals'][0]
        # The photographed behavior can be broader than the concrete recipe.
        proposal['inferred_behavior'] = candidate['output_behavior']
        proposal['reason'] = proposal['reason'].replace(
            '선택한 동작과 일치하는 연결·코드 규칙을 사용합니다.',
            '추정한 동작에 맞는 연결·코드 규칙을 사용합니다.',
        )
        previews.append({'candidate_id': candidate['id'], 'title': candidate['title'],
                         'proposal': proposal})
    return previews
