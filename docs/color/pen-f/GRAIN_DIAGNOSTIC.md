# COLOR grain diagnostic

This temporary build records whether five existing CPU paths observed COLOR High grain. It does not change the grain algorithm or establish that grain appears in a JPEG. The five digits are independent facts accumulated during the resident-load session. They need not describe the same photograph.

## Run a camera trial

1. Install the temporary diagnostic build using the existing manual update procedure.
2. Fully power cycle the camera. Select a COLOR profile and set Grain to High.
3. Open Grain and record the five digits after `D` in the footer. For example, `Grain High D00000 @A028@` displays five zeros.
4. Leave the editor, take one JPEG, and wait for capture to finish.
5. Open Grain again and record the five digits. Report both codes, the COLOR profile, whether the camera completed capture normally, and whether the JPEG shows grain.
6. For another trial, fully power cycle first. Keep the profile and Grain setting unchanged during each trial.

If the initial code already contains a one, that digit cannot distinguish the subsequent capture. The actual cold-boot lifecycle has not been verified on a camera. The initial reading makes retained evidence visible.

## Interpret the code

The digits are ordered as follows.

1. A High grain word was acquired into an owner row.
2. A High grain word was copied into a job.
3. COLOR selection decoded High.
4. A COLOR High stage `0x900` mask request reached the existing enqueue hook.
5. The combiner accepted a COLOR High kind-0 request at stage `0x901` or `0x902`.

A digit changes from zero to one when its observation occurs and remains one until the resident section is reloaded. Repeated observations leave it at one. For example, `D11110` records the first four observations but not the fifth. `D11111` records all five observations, but does not prove that they belonged to the same capture or that the image hardware completed processing or added visible grain. The fifth digit records CPU admission. It does not verify seed access, nonzero gain, hardware upload, a usable mask, or final pixels. An observer can see a mixture of older and newer facts while capture is active.

## Reproduce offline checks

Build the diagnostic and retain a graph from the pre-diagnostic Delete-fix revision. Then run the differential probe with the two graph directories in that order. Both directories need `main.bin` and `placement.json`.

```sh
PYTHONPATH=tools python3 tools/penf_grain_diagnostic_probe.py /path/to/pre-diagnostic/candidate /path/to/diagnostic/candidate
python3 -m unittest tests.test_penf_grain_candidate.FilmGrainTests.test_all_diagnostic_footer_patterns_and_levels
python3 -m unittest tests.test_penf_grain_candidate.FilmGrainTests.test_unmapped_late_code_and_reuse_are_neutral
python3 -m unittest tests.test_penf_tone_hsl_delete
```

The differential probe compares native observer continuations, registers, flags, request bytes, calls, and job state. The footer test covers all 32 digit patterns at each displayed level, including termination, metadata, and buffer guards. The loader fixture models storage and completion services. It checks that resident loading initializes the bytes and that a section 8 reload retains them. These checks do not test the physical camera, LCD fit, memory headroom, hardware completion, or JPEG pixels.
