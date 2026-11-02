# COLOR grain visibility investigation

The user reports that COLOR Grain High is invisible in both live view and saved
JPEG on the first grain candidate, commit `b907623`. This issue is unresolved.
The HSL Delete fix changes only event-pointer preservation and does not change
grain processing.

## Bounded native observations

The manager writes `0xf7524e03` to the selected part1 property, 985, 986, or 987,
and publishes it to the selected grain source word. Executing each profile's
native callback through post-change entry `607607a1` retains both words.
Continuation beyond that entry needs camera state absent from the fixture.
The explicit native bank storage tests preserve tagged words across nine banks.
The 54 mode-filter definitions include these IDs; complete mode transitions
were not executed.

On two inspected native capture paths, conversion at `6052010f`, including the
custom trailer-copy hook, precedes preparation at `604c20ce` and selection at
`604c542d`. This establishes call order, not the identity or contents of an
actual camera's acquired owner.

Under a synthetic request and seed descriptor, the native combiner caller
`604aaacd` selects grain, sets the ICM enable flags, and writes gain 600 through
dispatcher `604b4933` into both hardware register banks. The test does not
execute ISP pixels, hardware completion, or JPEG output.

## Gaps in the request fixture

The generated MONO and COLOR requests both lack the seed descriptor at request
offset 212. Passing that COLOR request directly to the grain builder faults at
`604ea6ef` when it reads a sample through the empty descriptor. Earlier successful
configuration tests explicitly supply a synthetic descriptor. This is a fixture
gap shared with native MONO, not evidence that the camera has an empty descriptor.

The full engine has a bypass for source format family 1 with a nonzero request
word at offset 812. Generated requests have zero there. Actual camera requests
have not been captured, so the bypass cannot be accepted or excluded as the
cause of the report.

Toggling the MONO flag `0x200000` in a neutral-tint COLOR fixture leaves all four
request packets identical. It does not supply the seed descriptor or change
offset 812 in that fixture. This does not cover nonneutral tint or real capture.

## Remaining evidence

The CPU tests cannot determine whether the camera acquires the expected grain
word, takes these processing paths, or produces a usable brightness mask.
The user has since confirmed that native MONO grain is visible on the same
camera. The [official PEN-F Japanese manual](https://download.omsystem.com/pages/inst/penf/manual_penf_JPN.pdf#page=66)
states on page 66 that the native grain effect is not reflected in live view.
That statement concerns native MONO and does not establish the expected live
view behavior of this COLOR implementation.

A further native context, owner, and engine execution through `604aa595`
used format `0x0105` in both modes. With explicit synthetic seed and service
allocation models, the 16,384-byte mask configuration and 164-byte grain ICM
configuration were equal, with gain 600. Actual camera requests, processing,
and JPEG pixels remain unknown. No strength, mode, or flag change is justified
by these observations. The temporary [diagnostic](GRAIN_DIAGNOSTIC.md) observes
the existing algorithm without changing it.
