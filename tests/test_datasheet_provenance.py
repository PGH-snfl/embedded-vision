"""Generated metadata must not call library or simulator documentation a datasheet."""
import sexpdata as sx

from backend.circuit.profiles import reference
from backend.datasheet.catalog import CATALOG
from backend.kicad.exporter import children, create_schematic


def test_catalog_sources_are_explicitly_typed():
    assert all(entry.get('source_type') for entry in CATALOG.values())
    assert CATALOG['wp7113id']['source_type'] == 'manufacturer_datasheet'
    assert CATALOG['sim_photoresistor_module']['source_type'] == 'simulation_reference'
    assert CATALOG['resistor_axial']['source_type'] == 'footprint_library'


def test_schematic_separates_datasheets_from_other_references(tmp_path):
    graph, _ = reference('a' * 32, 'esp32_led_button')
    path, _, _, _ = create_schematic(graph, tmp_path)
    root = sx.loads(path.read_text())
    symbols = []
    for symbol in children(root, 'symbol'):
        props = {str(p[1]): p[2] for p in children(symbol, 'property')}
        symbols.append(props)
    led = next(p for p in symbols if p['Reference'] == 'D1')
    resistor = next(p for p in symbols if p['Reference'] == 'R1')
    board = next(p for p in symbols if p['Reference'] == 'U1')
    assert led['Datasheet'] == CATALOG['wp7113id']['source']
    assert led['Reference_Type'] == 'manufacturer_datasheet'
    assert resistor['Datasheet'] == ''
    assert resistor['Reference_Type'] == 'footprint_library'
    assert resistor['Reference_URL'] == CATALOG['resistor_axial']['source']
    assert board['Datasheet'] == ''
    assert board['Reference_Type'] == 'manufacturer_guide'
    assert board['Reference_URL'] == CATALOG['esp32_devkitc_v4']['source']
