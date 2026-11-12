"""Carry photo geometry into every functional editor, without changing electrical nets."""
from .photo_structure import structure_components,scene_version,motion_structure
from ..workflow import attach_workflow


def attach_photo_appearance(project,scene):
    project=attach_workflow(project)
    if not scene:return project
    parts=structure_components(scene)
    if not parts:return project
    photo_ids={p['id'] for p in parts}
    return {**project,'components':[p for p in project.get('components',[]) if p['id'] not in photo_ids]+parts,
        'embeddedVision':{**project.get('embeddedVision',{}),'photo_structure':scene,
            'photo_structure_version':scene_version(scene),'photo_appearance_version':1,
            'photo_assembly':{'version':1,'part_ids':[p['id'] for p in parts],
                'pose_basis':'assembled','explosion':'viewer_only','wiring_preserved':True},
            'focus_photo_on_open':True,'motion_structure':motion_structure(scene)}}
