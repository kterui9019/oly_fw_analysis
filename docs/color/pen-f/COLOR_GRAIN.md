# COLOR film grain candidate

PEN-F build 3101 has a separate grain strength for each of COLOR1, COLOR2, and
COLOR3. The values are Off, Low, Medium, and High. They use the native grain
amplitudes. Grain is shared by the ALL, R, G, and B tone channels.

## Camera controls

Open the COLOR tone editor and press INFO through shadow/highlight, middle,
black/white, and Grain. Both command dials and the arrow buttons adjust grain.
The rear dial retains its native direction. A held OK sets grain to Off.
Delete is consumed on the Grain page and does not change a tone channel.
Pressing INFO from Grain returns to ALL shadow/highlight.

The footer shows `Grain Off`, `Grain Low`, `Grain Medium`, or `Grain High`,
followed by the temporary `R` diagnostic code and the native INFO icon. The Grain page does not draw a tone curve.
The other pages retain their ALL/R/G/B curves and Delete channel switching.

## Stored and acquired state

Each profile uses one native part1 cell, 985, 986, or 987. The word is
`0xf7524e00 | level`, where level is 0 through 3. Other words decode to Off,
including the native default values 0, 3, and 1. Native MONO uses part0 and
remains independent. The existing native bank operations carry part1 through
all nine banks and the full default reset. The 54 native mode filters use
these property IDs only in part0.

The asynchronous GUI request retains the registered tone property 967, 970,
or 973 and carries the complete grain word. Its destination does not depend
on the page or profile selected when the request completes. The manager
recognizes the exact grain marker. Ordinary native signed tone values,
including -7 through -1, keep the original manager path.

Publication reads the twelve existing tone words and three grain words through
the same committed HSL publication lifecycle. The source occupies 60 bytes at
`60427c30`. The first 48 bytes retain their existing tone layout. Each of the
40 large and five compact image owners has a separate acquired grain word.
For the preview callback `6051fbcc`, constructor metadata identifies the acquired owner.
For the recording callback `605335e3`, job offset 8 points to a descriptor whose
offset 124 holds the owner. Both routes validate that owner and require COLOR
mode 11. The constructor copies its grain word to job offset 14960 before selecting
and initializing the native job list. Allocation is 14964 bytes, and the final
native clear covers 56 bytes from offset 14908. Conversion hooks also copy the
word for their existing paths. A valid capture job keeps its constructor
snapshot if its large owner is reused before conversion. Compact-owner copies
remain updateable. A later UI edit cannot change the grain of an acquired
photograph. Unrecognized owner pointers and unloaded conversion clear the
grain trailer. RAW development
uses the existing selected-profile acquisition and non-COLOR clear path.

External settings export, Wi-Fi recipes, and ORF extension records do not yet
carry the new grain word. Physical power-cycle persistence has not been tested
for this candidate. The native bank storage and reset paths have bounded
execution evidence.

## Processing requests

For a COLOR job with valid nonzero acquired grain, the selector writes its
level to the existing job byte `+0x1665` (5733). Native conversion later
overwrites that byte. Preparation restores it from the job trailer before
request packing. The selector bypasses the initial ordinary COLOR
classification and enters the existing MONO job selection branch. The native
format guards remain in that branch. The job itself keeps COLOR mode 11 and
its original flags. In particular, the MONO `200000` flag is not added.

The ordinary route submits four requests.

| Stage | Mode | Purpose |
|---|---:|---|
| `0900` | 12 | Native MONO brightness mask with LUT `60610742` |
| `0901` | 11 | COLOR image with combiner 31 and acquired grain strength |
| `f005` | 11 | Existing late creative shading |
| `0000` | 11 | Final output and JPEG routing |

A wrapper at the five existing kind0 packer enqueue calls changes only a
COLOR `0900` mask request with a valid nonzero grain byte to mode 12. The
shared job is unchanged. Native mask processing therefore bypasses custom
HSL, ALL, and RGB transforms. The COLOR image request retains those edits and
its chroma. A stage-scoped combiner admission enables the native grain unit
for COLOR. It checks kind0 before reading the longer request's grain byte.

The native alternate selector uses stage `0902` and combiner 32. Its existing
50/75/100 gain table remains unchanged. The ordinary route uses 110/300/600.
The alternate path's user-facing meaning remains unknown. Off preserves the
ordinary COLOR request path. MONO and other tested picture modes retain their
request bytes, including the latest main branch's subtle shading calibration.

## Placement and evidence

The candidate stays within the existing section8 end `6115c800`. It adds no
new loader extent. The relocated RGB fallback, settings-ID table, and queue
gate use the checked section1 gap `601caa04..601caa50`. Resident constructor
and preparation gates use checked section1 and section3 gaps. The UI dispatch and unloaded job-clear stubs share those resident gaps.
Resident selection and combiner gates use section3 gaps `6069b26c..6069b2b0` and
`6069b7b9..6069b800`. Every placement checks the exact FF preimage and its
capacity. Late-code entry gates retain the section-loaded bit checks.

`tools/penf_grain_candidate_probe.py` executes the assembled decode, native
storage/reset, acquisition, conversion, GUI manager, input methods, viewer,
request builders, combiner configuration, and both MMIO upload banks.
`tools/penf_grain_order_probe.py` provides the native-order fixture. It acquires
grain, changes the UI, registers metadata,
selects the constructor list, executes the conversion window that overwrites
the grain byte, prepares the job, and submits the already-selected list.
The full converter and camera capture are not exercised by that preview fixture.
`tools/penf_grain_recording_probe.py` executes the native recording header
producer `60531e16`, the constructor through native list selection, and recording
converter `60531fdb` up to preparation. Off selects ordinary COLOR development.
Low, Medium, and High select the native mask, grain image, and late shading
entries before conversion. The matrix covers all three profiles, later profile
edits, and owner reacquisition after construction. The converter must retain
the captured grain, including tagged Off. MONO and another picture mode keep
the same job bytes as the unhooked native constructor. Selection uses native
dimension and service paths. Heap allocation, logging, physical buffer lookup,
and the capture inputs are explicit models. The strength helper is checked
separately after the converter reaches preparation.
Compact conversion retains its existing copy behavior, but its constructor
producer has not been shown to select COLOR grain early. The native common image
builder verifies that nonneutral HSL, ALL, and RGB edits leave the mask
unchanged while changing the COLOR image stages.

The request fixture models successful allocation, dimensions, parameter
availability, and queue acceptance. The isolated grain configuration supplies
an explicit synthetic seed descriptor because the request fixture has no
sensor descriptor. Viewer fixtures model lower GUI services and execute the
native updater and publication. These checks do not emulate ISP pixels, JPEG
output, hardware completion, physical LCD timing, or the camera's total memory
budget. The ordinary mask and image route requests approximately 96.2 MiB of
intermediate buffers. Physical camera qualification remains pending.

Run the reproducible probe with the pinned decoded firmware and MN103 tools.

```sh
PYTHONPATH=tools python3 tools/penf_grain_candidate_probe.py --out generated/grain-check
PYTHONPATH=tools python3 tools/penf_grain_recording_probe.py generated/grain-recording-check
python3 -m unittest discover -s tests -p 'test_penf_grain_candidate.py' -v
```

The firmware is built through the existing
[tone candidate builder](../../../patches/tone/pen-f/README.md), retaining HSL,
RGB tone, and subtle shading. Building performs no camera access.
