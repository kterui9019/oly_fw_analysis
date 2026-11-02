# Creative MONO grain

Workspace's creative MONO grain adds brightness-dependent pseudorandom noise to
luminance. The camera contains matching gains and a matching mask table, and its
CPU configures a hardware combiner. Exact camera pixel arithmetic remains an
inference, not an emulated or measured ISP implementation.

## Desktop algorithm

The inspected OlyPomegranate 16-bit pixel loop uses a separate prepared mask M,
not simply the image's current luminance Y. With Y and M in 0…65535:

```python
state ^= (state << 13) & 0xffffffff
state ^= state >> 17
state ^= (state << 5) & 0xffffffff
state &= 0xffffffff
random_signed = (state & 65535) - 32768
weight = (M + ((M >> 15) & 1)) >> 6
noise = (((gain * weight) >> 10) * random_signed) >> 10
noise = clamp(noise, -6682, 65535)
Y_out = clamp(Y + noise, 0, 65535)
# Cb and Cr pass through in this grain configuration.
```

Negative shifts are arithmetic. This is xorshift32 with shifts 13/17/5, not a
Gaussian generator or a stored photographic texture. The inspected desktop
setup seeds it with 10. Low/Medium/High gains are 110/300/600. The 256-entry mask
curve is zero through index 36, rises to 1023 by 120, then plateaus. Those indices
are internal mask inputs, not independently calibrated final JPEG brightness.

The asymmetric negative clamp and final white clipping can alter mean brightness
at strong settings. No explicit grain-radius control was identified. Apparent
coarseness can change with amplitude, clipping and resizing.

Native desktop pixel tests reproduce the integer formula; full renders also
confirm color can be retained when the separate monochrome conversion is disabled.
A zero-grain control matches the ordinary color render. This does not establish
that the camera hardware has the same seed, PRNG, clipping or rounding.

## Camera parameter path

PEN-F 3101 settings 985/986/987 select per-profile grain; effective setting 984
becomes parameter byte +`1641`, then request byte +`440` through `604c3051`.
Selector `604fb7b8` chooses combiner 31 for stage `0901`, or 32 for `0902`.
Builder `604ea2ba` and register writer `604b5644` upload to `9e000800` or
`9e004800`; gain reaches bank+`a4`.

The gain table at `605fc452` and expanded mask LUT at `60610742` match the desktop
values exactly. The alternate route uses 50/75/100 at `605fc458`. The primary
route obtains a seed sample through a descriptor; the alternate increments a
RAM counter. They are alternative routes, not two successive grain passes.

Mask selection, grain gain and monochrome output are distinct gates. COLOR key
11 and MONO key 12 select different tone and tint controls. A counterfactual
COLOR gate can produce the same grain configuration as MONO, but cannot by itself
schedule the missing mask/image jobs or preserve color through format-specific
forced-mono code.

The [processing-job map](CREATIVE_PROCESSING_JOBS.md) identifies these buffer
relationships. Stock grain Off sets zero gain in the tested list; it does not
remove all MONO intermediate jobs. This concerns creative MONO profiles, not the
separate Grainy Film ART filters.

## COLOR candidate

The [COLOR grain candidate](COLOR_GRAIN.md) adds independent per-profile strength,
a native editor page, acquired settings, and mask/image request routing over the
HSL and RGB tone firmware. Its native CPU checks do not establish physical
JPEG appearance or hardware memory capacity.
