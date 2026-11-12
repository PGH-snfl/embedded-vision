"""Select bounded prototypes for explicitly selected, semantically matching goals.

Classification is based on the proposed behavior, never a claim that a
photographed circuit or its original firmware has been recovered.
"""
import re


def prototype_kind(candidate):
    if not candidate or candidate.get('kind') != 'unsupported':
        return None
    text = ' '.join(str(candidate.get(k, '')) for k in ('title', 'input_behavior', 'output_behavior')).casefold()
    if re.search(r'보행|이족|2족|두.?발|다리|biped|humanoid|legged|walking',text):return None
    # Do not quietly turn scheduled watering, following or parking into one of
    # these simpler designs. Extra capabilities need their own implementation.
    if re.search(r'주차|parking|드론|비행|drone|flight', text):
        return None
    if re.search(r'장애물|obstacle', text) and re.search(r'회피|avoid', text):
        return 'obstacle_rover'
    if re.search(r'토양|흙|soil|moisture', text) and re.search(r'급수|물주|watering|irrigat', text):
        if re.search(r'일정|시간표|schedule|timer', text):
            return None
        return 'watering'
    if re.search(r'거리|distance', text) and re.search(r'표시|display|indicator', text):
        if re.search(r'추종|follow|주행|로봇|robot|rover|회피|avoid', text):
            return None
        return 'distance_indicator'
    return None
