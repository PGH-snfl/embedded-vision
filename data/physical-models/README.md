# Product presentation models

These models display the parts selected in the proposed circuit. Their presence
does not confirm that the same product was identified in an input photograph.
Electrical simulation and component recognition are separate from these models.

## Sources and attribution

- Raspberry Pi 4 Model B: [official mechanical drawing](https://datasheets.raspberrypi.com/rpi4/raspberry-pi-4-mechanical-drawing.pdf).
  Outline 85 × 56 mm; connector and mounting-hole locations follow the drawing.
  The drawing is linked, not redistributed here.
- Adafruit DC & Stepper Motor HAT #2348, **Rev A**:
  [original PCB repository](https://github.com/adafruit/Adafruit-DC-Stepper-Motor-HAT-PCB).
  `hat-rev-a.brd`, `hat-README.md`, `hat-license.txt` preserve the original PCB,
  attribution and license. The bundled revision has a 65 × 56.5 mm outline.
- Adafruit Motor Shield **V2.3**:
  [original PCB repository](https://github.com/adafruit/Adafruit-Motor-Shield-V2-PCB).
  `shield-v2.3.brd`, `shield-README.md`, `shield-license.txt` preserve the original
  PCB, attribution and license. Outline 68.58 × 53.34 mm.
- Adafruit DC motor in micro servo body #2941:
  [manufacturer product page](https://www.adafruit.com/product/2941).
  Published overall dimensions 32.3 × 12.3 × 29.9 mm; blue servo-shaped housing,
  white shaft, **two motor wires**. This is not a three-wire positional servo.

Adafruit PCB layouts are by Adafruit Industries / Limor Fried, licensed under
Creative Commons Attribution-ShareAlike 3.0. See the full bundled license and
README files. The derived board layout JSON and corresponding board models are
adaptations distributed under that same license. Changes: extracted millimetre
coordinates, centred the origin, inverted the drawing Y axis for scene Z, and
reconstructed simplified component bodies with procedural geometry.

## Reproduction and limits

Run `python scripts/build_physical_model_data.py` to regenerate the CAD layout
JSON. It records SHA-256 hashes of the bundled originals. Pin holes, connector
pad positions and component positions on the Adafruit boards come from those
files. Rendering uses simplified body heights, corners, silkscreen and leads;
terminal entry points use the pad location plus a 3.6 mm front-face offset.
This is an assembly illustration, not manufacturing CAD or a clearance check.

GPIO40 is a whole 40-pin Pi/HAT mating connector. Its dashed connection in the
exploded editor view is not one jumper and does not resolve forty separate nets.
The Motor Shield can be displayed separately while editing connections. In the
assembled layout it mounts above the Uno and the header connections are shown
as mating connectors rather than separate jumpers.

Motor DC supplies and USB-C supplies have no verified exact product model in
the current circuit proposal. Their grey/white generic bodies and illustrative
sizes must not be interpreted as confirmed dimensions or ratings.

Existing native pin IDs, connections and code remain the circuit source of
truth. Visual port positions do not rewrite the underlying 2D wire coordinates.
