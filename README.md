# vector-01 — Unicorn Viz effect pack

**Version 0.10.0**


Geometric / 3D / line-art visuals: 3D Cube, Vector, Disco Ball, Laser Tunnel.

## Changelog

- **0.10.0** — Disco Ball 2.0. The old build put a translucent, softly-blended
  sphere in an almost empty room; the tiles barely registered and none of the
  signature mirror-ball light reached any surface.

  - **The room is the effect now.** The direction from the ball to every
    surface point is transformed into ball-local space, quantised onto a facet
    grid and hashed per facet, so real squares of coloured light sweep the
    floor, walls and ceiling in exact lockstep with the ball's spin. The
    projection deliberately uses a **finer grid than the ball's visible
    facets** — a real ball carries far more tiles than can be resolved on it at
    this size, and matching them 1:1 throws room-filling slabs instead of crisp
    dots.
  - **Hard grout between facets.** The facets were blended into a soft gradient
    before, which is exactly what made it read as a soap bubble instead of a
    mirror ball.
  - **The ball occludes the light shafts.** The rotating shafts are anchored on
    the ball's screen position, so drawing them over it peaked the beams right
    on its facets and washed them out.
  - Added a lit dance floor with a beat-driven cascade rippling outward from
    the centre, neon drips running down the walls, and a proper enclosed room
    (floor/ceiling/three walls) for the dots to land on.
  - **Four scenes**, cycled without immediate repeats: classic club, laser
    cathedral, neon grid, liquid chrome — each with its own palette, room
    treatment and beam character.
  - **Added per-activation randomisation.** The 1.x build called `self.rng`
    exactly zero times, so every run opened on an identical frame, against the
    pack-wide requirement. Scene, hue, facet counts, spin phase, ball tilt axis
    and camera phase are now all randomised, and ball spin is CPU-integrated so
    audio modulates the rate instead of multiplying an ever-growing `iTime`.
  - Added a `reactivity` dial alongside the existing speed/zoom/tiles/rotation/
    laser ones.

- **0.9.1** — Vector: wire-edge sparkle glints restored — the hash time term is mod()-wrapped (audit 2026-08-03 §8 Class B; the layer was precision-dead for roughly two-thirds of instances from frame 0).
- **0.9.0** — initial versioned release.
