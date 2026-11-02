# Creative shading and highlight protection

Creative **Shading Effect** is an artistic vignette, separate from lens **Shading
Compensation**. Negative values blend toward black; positive values toward white.
For negative shading, this is multiplication toward black, not subtraction of a
fixed brightness amount. Chroma is blended about its neutral value as well.

## Stock controls and geometry

PEN-F's five nonzero steps cover the strong end of Workspace's control. Its
import rule maps camera value c to `sign(c) × 2 × (abs(c)+10)`, with zero unchanged:

| Camera magnitude | Workspace label | Camera coordinate-scale word | Workspace radial amount |
| ---: | ---: | ---: | ---: |
| 1 | 22 | 928 | 824 |
| 2 | 24 | 952 | 876 |
| 3 | 26 | 976 | 928 |
| 4 | 28 | 1000 | 976 |
| 5 | 30 | 1024 | 1024 |

These are not pixel-exact equivalents. Camera callback `604c9168` selects the
word from `605fc45e`, computes `q=floor(1048576/word)`, and scales **both spatial
coordinate increments** by `1024/q`. Workspace scales the squared radial
coordinate directly. Their approximate relation is
`amount ≈ 1024 × (1024/q)²`.

Mask generation `604aa202 → 604aa00c` uses a 64-entry curve at `605fc340` and a
128×128 camera mask, later resampled. The curve matches Workspace's data.
Changing strength changes the spatial extent of this falloff. Workspace's
geometry normalizes the horizontal and vertical coordinates separately, producing
elliptical contours in a non-square frame; this is not an equal-radius pixel-space
circle. Camera resampling details remain a separate qualification.

The camera's encoded CMIO T contains another copy of the shading data. Changing
the capture table does not automatically change RAW-development metadata or
live-view mapping (`602fc73a`).

## Gentler steps in the tone candidate

The [current tone build](../../../patches/tone/pen-f/README.md) replaces the
capture table at `605fc45e` for **both signs**. With the old magnitude-one
radial amount defined as 10, the new five steps target 2/4/6/8/10. Zero and
the native white/black blend selection retain their stock behavior.

| Camera magnitude (either sign) | Target relative strength | Coordinate word | Actual relative radial amount |
| ---: | ---: | ---: | ---: |
| 1 | 2 | 415 | 1.998 |
| 2 | 4 | 587 | 3.996 |
| 3 | 6 | 719 | 5.996 |
| 4 | 8 | 830 | 7.991 |
| 5 | 10 | 928 | 10.000 |

Calibration accounts for the native integer reciprocal: with
`q_old = floor(1048576/928)` and `q_new = floor(1048576/word)`, the relative
squared radial amount is `(q_old/q_new)^2`. Scaling the coordinate words
directly by 20/40/60/80/100% would square those percentages and make the lower
steps excessively weak. New magnitude five uses exactly the old magnitude-one
word. These ratios describe geometry, not linear pixel brightness or perceived
strength; the native nonlinear falloff curve is unchanged.

`tools/penf_shading_candidate.py` checks the original five words before replacing
only those ten bytes. The tone builder records the calibration and source hash.
Tests cover all signed steps, zero and invalid levels through both native
request layouts, as well as the native coordinate-scale block. The container
test restores the stock table in memory and checks the previous RGB-tone main
hash, establishing that no other main-payload bytes changed.

This change covers the capture table. The live-view enum mapping and encoded
CMIO T/RAW-development metadata are unchanged; preview and external RAW
development are not qualified to match the weaker captured effect. Physical
camera/JPEG appearance has not been tested. The pinned HSL-only release builder
continues to reproduce its original package.

## Pipeline position

Workspace applies creative shading to developed image data, after its ordinary
color/tone work. In-camera COLOR attaches the mask to the main development
request, so its exact position among ISP units is not proven by CPU setup order.
MONO has a separate shading request whose input is already developed. See
[processing jobs](CREATIVE_PROCESSING_JOBS.md).

A similar SOOC/Workspace appearance supports corresponding processing, but does
not independently establish identical internal brightness domains.

## Rational highlight protection

A desktop prototype preserves highlights with a per-pixel rational shoulder.
For normalized developed luminance y, protection p, midpoint m and radial
retained-image weight g:

```text
k = (m / (1-m))²
h = p × y² / (y² + k × (1-y)²)
g_effective = g + (1-g) × h
output = blend(original, black, retained_weight=g_effective)
```

At full protection, h reaches one half at y=m, has zero slope at black and white,
and preserves white. Output meets the unmodified image with slope one at white.
This is a modified Reinhard-shaped response on brightness odds, not an inversion
of the Olympus tone curve or reconstruction of clipped HDR highlights.

Higher m protects fewer midtones and makes the vignette stronger there. It also
increases the local-contrast peak. Stronger radial scaling is a different control;
values outside the supported −30…+30 Workspace range are not automatically valid
camera settings.

One useful desktop calibration is midpoint 0.8, full protection, power 1, with
Workspace magnitudes 6/12/18/24/30. Their radial amounts are 412/567/721/876/1024.
Approximate camera coordinate words are 650/762/859/947/1024. These are derived
starting values, not physically qualified camera tuning.

## Reusing the combiner

At midpoint 0.8, `h(y)=y²/(y²+16(1-y)²)`. Two existing blend operations can form:

```text
G = h(y) × (1-g) + white × g
output = G × original
```

Original desktop combiner instructions reproduce these blends over a grid of
brightness/radial values; their difference from the prototype is below half an
8-bit channel step in that grid. The camera uploads matching stock white/black
combiner configurations, and native tone upload accepts a 256-knot protection LUT.

This establishes arithmetic/configuration compatibility, not a complete camera
implementation. Producing h(y) is another operation. Its input must already have
the intended tone applied; replacing the early grain mask gives h(u), not h(T(u)).
Late-LUT routing, extra buffers, scheduling, cleanup and physical ISP behavior
remain unresolved. No camera highlight-protection effect is claimed by these
configuration tests.
