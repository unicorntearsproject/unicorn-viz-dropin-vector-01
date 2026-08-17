"""Disco Ball — a real mirror-ball club rendered as a raymarched scene.

The signature of a mirror ball is not the ball, it is the **room**: hundreds of
quantised facets throwing sweeping squares of coloured light across every
surface.  This effect projects those for real — the direction from the ball to
each surface point is transformed into ball-local space, quantised onto the
same facet grid the ball is tiled with, and hashed per facet — so the dots
sweep the floor and walls in exact lockstep with the ball's spin, and change
when the tile counts change.

On top of that: a lit dance floor whose tiles fire in a beat-driven cascade
outward from the centre, rotating volumetric light shafts anchored to the ball,
a chrome ball with sharp grout and prismatic facet tints, and drips of neon
running down the walls.

Four scenes, cycled without immediate repeats, each with its own palette, room
treatment and beam character:

* **Classic club** — warm gold spots, dense facets, checkerboard dance floor.
* **Laser cathedral** — tall saturated room, hard prismatic shafts, sparse
  heavy facets.
* **Neon grid** — Tron-style glowing wireframe room, cyan/magenta dots.
* **Liquid chrome** — iridescent dispersion, mirrored floor, soft wide beams.

Audio reactivity:
  - bass    -> ball swell + bob, dance-floor pulse, shaft thickness
  - mid     -> facet tint drift, wall drip flow, room glow
  - treble  -> facet sparkle, specular bloom, dot shimmer
  - beat    -> strobe, floor cascade, camera kick, palette shift

Randomised per activation: scene, palette hue, facet counts, ball spin phase
and axis, camera path phase, and ``self.time`` — no two runs look alike from
frame 0.

Config keys (under ``[effects.DiscoBall]``):
    speed, zoom, reactivity, num_tiles_u, num_tiles_v, rotation_speed,
    laser_intensity
"""
from __future__ import annotations

import moderngl
import numpy as np

from unicornviz.effects.base import AudioData, BaseEffect

_NSTYLE = 4

_VERT = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330

uniform float iTime;
uniform vec2  iResolution;
uniform float iBass;
uniform float iMid;
uniform float iTreble;
uniform float iBeat;
uniform float iStrobe;
uniform float iSpeed;
uniform float iNumTilesU;
uniform float iNumTilesV;
uniform float iRotationSpeed;
uniform float iLaserIntensity;
uniform float iZoom;
uniform float iHue;
uniform float iSpin;        // CPU-integrated ball spin (audio-speed safe)
uniform float iCam;         // CPU-integrated camera drift phase
uniform float iTilt;        // per-activation ball tilt axis
uniform int   iStyle;

in vec2  v_uv;
out vec4 fragColor;

#define PI  3.14159265
#define TAU 6.28318530

const float FLOOR_Y   = -2.2;
const float CEIL_Y    =  3.4;
const float WALL_X    =  6.0;
const float WALL_Z    = -7.0;
// Projected-dot grid density relative to the ball's visible facets.
const float DOT_MULT  =  3.5;

float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}
vec3 palette(float t) { return 0.5 + 0.5 * cos(TAU * (t + vec3(0.0, 0.33, 0.67))); }

mat3 rotY(float a) { float s = sin(a), c = cos(a); return mat3(c,0,s, 0,1,0, -s,0,c); }
mat3 rotX(float a) { float s = sin(a), c = cos(a); return mat3(1,0,0, 0,c,-s, 0,s,c); }

// Scene tint: every style pulls from the shared palette but lands somewhere
// distinct, so a scene change is unmistakable.
vec3 sceneTint(float t) {
    if (iStyle == 0) return mix(palette(iHue + t), vec3(1.0, 0.82, 0.45), 0.45);
    if (iStyle == 1) return palette(iHue + t * 1.6 + 0.15);
    if (iStyle == 2) return mix(palette(iHue + t), vec3(0.15, 0.95, 1.0), 0.50);
    return mix(palette(iHue + t * 0.7), vec3(0.80, 0.86, 1.0), 0.35);
}

bool hitSphere(vec3 ro, vec3 rd, float r, out float t) {
    float b = dot(ro, rd);
    float c = dot(ro, ro) - r * r;
    float h = b * b - c;
    if (h < 0.0) return false;
    t = -b - sqrt(h);
    return t > 0.001;
}

// Quantise a direction onto the facet grid; returns the facet id and the
// in-facet offset so callers can draw a hard-edged square.
void facetN(vec3 dir, vec2 counts, out vec2 id, out vec2 f) {
    float theta = atan(dir.x, dir.z);
    float phi   = acos(clamp(dir.y, -1.0, 1.0));
    vec2 uv = vec2(theta / TAU * counts.x, phi / PI * counts.y);
    id = floor(uv);
    f  = fract(uv) - 0.5;
}
void facet(vec3 dir, out vec2 id, out vec2 f) {
    facetN(dir, vec2(iNumTilesU, iNumTilesV), id, f);
}

vec3 facetNormal(vec3 dir) {
    vec2 id, f;
    facet(dir, id, f);
    float tu = (id.x + 0.5) / iNumTilesU * TAU;
    float tv = (id.y + 0.5) / iNumTilesV * PI;
    float st = sin(tv);
    return normalize(vec3(st * sin(tu), cos(tv), st * cos(tu)));
}

// The projected mirror-ball light: squares of colour thrown onto a surface.
// `p` is the world point, `ballRot` the ball's current orientation.
vec3 discoDots(vec3 p, mat3 ballRot, float t, float shade) {
    vec3 d = normalize(p);                    // ball sits at the origin
    vec3 dl = transpose(ballRot) * d;
    // The projection uses a much finer grid than the ball's *visible* facets:
    // a real ball carries far more tiles than can be resolved on it at this
    // size, and matching the two 1:1 throws room-filling slabs of colour
    // instead of the crisp little squares that make the effect read.
    vec2 id, f;
    facetN(dl, vec2(iNumTilesU, iNumTilesV) * DOT_MULT, id, f);
    float h = hash21(id + 3.7);
    // Only a fraction of facets catch the key light at any moment; which ones
    // drifts slowly so the field keeps churning.
    float lit = step(0.62 - iBass * 0.10, fract(h + t * 0.05));
    if (lit < 0.5) return vec3(0.0);
    float sq = smoothstep(0.42, 0.26, max(abs(f.x), abs(f.y)));
    float dist = length(p);
    float fall = 9.0 / (2.0 + dist * dist);
    vec3 c = palette(iHue + h * 0.8 + t * 0.03);
    if (iStyle == 2) c = mix(c, vec3(0.2, 1.0, 1.0), 0.45);
    if (iStyle == 3) c = mix(c, vec3(0.9, 0.9, 1.0), 0.30);
    return c * sq * fall * shade * (0.55 + iTreble * 0.9 + iBeat * 0.5);
}

// Lit dance floor: checkerboard cells with a beat cascade rippling outward.
vec3 danceFloor(vec2 xz, float t) {
    vec2 cell = floor(xz * 0.7);
    float h = hash21(cell);
    float r = length(xz);
    // Cascade front expands from the centre on every beat.
    float front = (1.0 - iBeat) * 9.0;
    float wave = exp(-pow(r - front, 2.0) * 0.55) * iBeat;
    float lit = step(0.45, fract(h * 3.0 + floor(t * 1.3) * 0.37));
    vec3 c = sceneTint(h * 0.6);
    float base = iStyle == 3 ? 0.05 : 0.16;
    vec2 g = abs(fract(xz * 0.7) - 0.5);
    float grout = smoothstep(0.02, 0.06, min(g.x, g.y));
    return c * (base * lit + wave * 1.5) * grout * (0.6 + iBass * 0.9);
}

// Room trace: nearest of floor / ceiling / three walls.
bool traceRoom(vec3 ro, vec3 rd, out vec3 p, out vec3 n, out float kind) {
    float best = 1e9;
    kind = -1.0;
    float tt;
    if (abs(rd.y) > 1e-4) {
        tt = (FLOOR_Y - ro.y) / rd.y;
        if (tt > 0.001 && tt < best) { best = tt; n = vec3(0, 1, 0); kind = 0.0; }
        tt = (CEIL_Y - ro.y) / rd.y;
        if (tt > 0.001 && tt < best) { best = tt; n = vec3(0, -1, 0); kind = 1.0; }
    }
    if (abs(rd.x) > 1e-4) {
        tt = (-WALL_X - ro.x) / rd.x;
        if (tt > 0.001 && tt < best) { best = tt; n = vec3(1, 0, 0); kind = 2.0; }
        tt = ( WALL_X - ro.x) / rd.x;
        if (tt > 0.001 && tt < best) { best = tt; n = vec3(-1, 0, 0); kind = 2.0; }
    }
    if (abs(rd.z) > 1e-4) {
        tt = (WALL_Z - ro.z) / rd.z;
        if (tt > 0.001 && tt < best) { best = tt; n = vec3(0, 0, 1); kind = 2.0; }
    }
    if (kind < 0.0) return false;
    p = ro + rd * best;
    return true;
}

vec3 roomSurface(vec3 p, vec3 n, float kind, mat3 ballRot, float t) {
    vec3 col = (iStyle == 1) ? vec3(0.010, 0.008, 0.020)
             : (iStyle == 2) ? vec3(0.004, 0.012, 0.020)
                             : vec3(0.014, 0.011, 0.018);

    if (kind == 0.0) {
        col += danceFloor(p.xz, t);
    } else if (kind == 2.0) {
        // Wall panelling, plus neon drips running down it.
        vec2 w = (abs(n.x) > 0.5) ? p.zy : p.xy;
        float panel = smoothstep(0.03, 0.0, abs(fract(w.x * 0.35) - 0.5) - 0.47);
        col += sceneTint(0.3) * panel * (0.05 + iMid * 0.10);
        float lane = floor(w.x * 6.0);
        float lh = hash21(vec2(lane, 11.0));
        float flow = fract(t * (0.06 + lh * 0.16) + lh);
        float dripY = CEIL_Y - flow * (CEIL_Y - FLOOR_Y);
        float dl = smoothstep(0.05, 0.0, abs(fract(w.x * 6.0) - 0.5) * 0.16)
                 * smoothstep(1.2, 0.0, dripY - w.y) * step(w.y, dripY);
        col += sceneTint(lh) * dl * (0.35 + iMid * 0.6);
    } else {
        float rig = smoothstep(0.06, 0.0, abs(fract(p.x * 0.25) - 0.5) - 0.44);
        col += sceneTint(0.6) * rig * 0.05;
    }

    float shade = (kind == 0.0) ? 1.0 : 0.75;
    col += discoDots(p, ballRot, t, shade);
    return col;
}

// Rotating shafts anchored on the ball, in screen space around its centre.
vec3 lightShafts(vec2 sp, float t) {
    float r = length(sp);
    float a = atan(sp.y, sp.x);
    float blades = (iStyle == 1) ? 7.0 : (iStyle == 3) ? 4.0 : 6.0;
    float sharp = (iStyle == 1) ? 22.0 : (iStyle == 3) ? 5.0 : 11.0;
    float beam = pow(max(0.0, 0.5 + 0.5 * sin(a * blades + iSpin * 1.7)), sharp);
    float fall = exp(-r * (1.5 - iBass * 0.35)) * smoothstep(0.02, 0.25, r);
    vec3 c = sceneTint(0.15 + sin(t * 0.11) * 0.2);
    return c * beam * fall * (0.55 + iBass * 1.1) * iLaserIntensity;
}

void main() {
    vec2 uv = (v_uv * 2.0 - 1.0) * vec2(iResolution.x / iResolution.y, 1.0);
    uv /= max(iZoom, 0.01);

    float t = iTime * iSpeed;
    float tb = mod(iTime, 600.0);

    float kick = iBeat * 0.05;
    vec3 ro = vec3(sin(iCam * 0.35) * 1.5 + kick * sin(tb * 21.0),
                   0.45 + sin(iCam * 0.23) * 0.35 + kick * cos(tb * 17.0),
                   4.3 + cos(iCam * 0.29) * 0.7);
    vec3 target = vec3(0.0, 0.15 + sin(iCam * 0.4) * 0.2, 0.0);
    vec3 fwd = normalize(target - ro);
    vec3 rgt = normalize(cross(fwd, vec3(0, 1, 0)));
    vec3 up  = cross(rgt, fwd);
    vec3 rd  = normalize(fwd + uv.x * rgt + uv.y * up);

    // Ball breathes with the bass and bobs on the beat.
    float ballR = 1.0 + iBass * 0.10 + iBeat * 0.04;
    mat3 ballRot = rotY(iSpin) * rotX(iTilt + iSpin * 0.31);

    vec3 col;
    float tHit;
    float ballHit = 0.0;
    if (hitSphere(ro, rd, ballR, tHit)) {
        ballHit = 1.0;
        vec3 p  = ro + rd * tHit;
        vec3 nS = normalize(p);
        vec3 nLocal = transpose(ballRot) * nS;
        vec3 nT = normalize(ballRot * facetNormal(nLocal));

        vec2 fid, ff;
        facet(nLocal, fid, ff);
        float fh = hash21(fid);

        // Hard grout between facets — the old build blended them into a soft
        // bubble, which is exactly what stopped it reading as a mirror ball.
        float grout = smoothstep(0.50, 0.40, max(abs(ff.x), abs(ff.y)));

        vec3 refl = reflect(rd, nT);
        vec3 rp, rn; float rkind;
        vec3 rcol = vec3(0.02);
        if (traceRoom(p + nT * 0.01, refl, rp, rn, rkind)) {
            rcol = roomSurface(rp, rn, rkind, ballRot, t) * 1.7;
        }
        rcol += sceneTint(fh * 0.9) * 0.16;                     // facet tint
        rcol *= 0.45 + 0.85 * fh;                               // per-facet gain

        vec3 lDir = normalize(vec3(0.3, 1.0, 0.4));
        float spec = pow(max(0.0, dot(refl, lDir)), 48.0) * (1.0 + iTreble * 2.5);
        float fres = pow(1.0 - abs(dot(rd, nT)), 3.5);

        col = rcol * grout + vec3(0.004) * (1.0 - grout);
        col += vec3(1.0, 0.95, 0.85) * spec * grout;
        col += sceneTint(fh + 0.3) * fres * (0.35 + iMid * 0.8);
        // Prismatic dispersion on the rim reads as chrome.
        col += vec3(fres * fres) * palette(iHue + nT.x * 0.5 + nT.y * 0.3) * 0.5;
        col += iBeat * 0.30 * sceneTint(0.5) * grout;
    } else {
        vec3 p, n; float kind;
        if (traceRoom(ro, rd, p, n, kind)) {
            col = roomSurface(p, n, kind, ballRot, t);
        } else {
            col = vec3(0.008, 0.006, 0.014);
        }
    }

    // Shafts are anchored on the ball's screen position (it sits at the world
    // origin, so its screen offset is just the camera-space projection).
    // Shafts are haze in the air *around* the ball, so the ball occludes them
    // — without this the beams peak exactly on the ball's screen position and
    // wash its facets back into the glassy blob this used to be.
    vec2 ballScreen = vec2(dot(-ro, rgt), dot(-ro, up)) / max(dot(-ro, fwd), 0.001);
    col += lightShafts(uv - ballScreen, t) * mix(1.0, 0.12, ballHit);

    // Beat strobe across the whole room.
    col += sceneTint(0.8) * iStrobe * 0.35;

    float vig = smoothstep(1.55, 0.25, length(v_uv - 0.5));
    col *= vig;
    col = col / (col + 0.85);
    col = pow(max(col, 0.0), vec3(0.82));
    fragColor = vec4(col, 1.0);
}
"""


class DiscoBall(BaseEffect):
    """Audio-reactive mirror-ball club: real projected facet light, lit floor."""

    NAME = 'Disco Ball'
    AUTHOR = 'unicorn-viz drop-in'
    TAGS = ['vector', 'disco', 'reflections', 'chill', 'groovy', 'intense']
    PING_PONG_FRIENDS = ['Vector', '3D Cube', 'Laser Tunnel', 'Audio Spectrum']

    # Scene shown by the previous instance, so a fresh activation never opens
    # on the same one twice running.
    _last_style: int | None = None

    def _init(self) -> None:
        self.parameters = {
            'speed': float(self.config.get('speed', 1.0)),
            'zoom': float(self.config.get('zoom', 1.0)),
            'reactivity': float(self.config.get('reactivity', 1.3)),
            'num_tiles_u': float(self.config.get('num_tiles_u', 18)),
            'num_tiles_v': float(self.config.get('num_tiles_v', 12)),
            'rotation_speed': float(self.config.get('rotation_speed', 1.0)),
            'laser_intensity': float(self.config.get('laser_intensity', 1.0)),
        }
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad(self._prog)

        self._bass = self._mid = self._treble = 0.0
        self._beat = 0.0
        self._strobe = 0.0

        # Per-activation randomisation (the 1.x build had none at all, so every
        # run opened on an identical frame).
        choices = [s for s in range(_NSTYLE) if s != DiscoBall._last_style]
        self._style = int(self.rng.choice(choices))
        DiscoBall._last_style = self._style
        self._style_timer = float(self.rng.uniform(16.0, 28.0))
        self._hue = float(self.rng.uniform(0.0, 1.0))
        self._tilt = float(self.rng.uniform(0.0, 6.28))
        self._spin = float(self.rng.uniform(0.0, 6.28))
        self._cam = float(self.rng.uniform(0.0, 100.0))
        self._tiles_u = float(self.rng.integers(14, 24))
        self._tiles_v = float(self.rng.integers(9, 15))

    def _choose_style(self) -> None:
        choices = [s for s in range(_NSTYLE) if s != self._style]
        self._style = int(self.rng.choice(choices))
        DiscoBall._last_style = self._style
        self._style_timer = float(self.rng.uniform(16.0, 28.0))
        self._hue = float((self._hue + self.rng.uniform(0.15, 0.4)) % 1.0)
        self._tiles_u = float(self.rng.integers(14, 24))
        self._tiles_v = float(self.rng.integers(9, 15))

    def update(self, dt: float, audio: AudioData) -> None:
        """Advance audio envelopes, ball spin and the scene timer."""
        super().update(dt, audio)
        react = max(0.05, float(self.parameters['reactivity']))
        self._bass = float(np.clip(audio.bass_n * react, 0.0, 2.0))
        self._mid = float(np.clip(audio.mid_n * react, 0.0, 2.0))
        self._treble = float(np.clip(audio.treble_n * react, 0.0, 2.0))
        if audio.beat > 0.5:
            self._beat = 1.0
            self._strobe = 1.0
            self._hue = float((self._hue + self.rng.uniform(0.01, 0.05)) % 1.0)
        self._beat = max(0.0, self._beat - dt * 2.6)
        self._strobe = max(0.0, self._strobe - dt * 7.0)

        speed = max(0.05, float(self.parameters['speed']))
        # CPU-integrated so audio modulates the *rate*: multiplying an
        # ever-growing iTime by a per-frame audio value teleports the phase.
        self._spin = (self._spin + dt * speed * max(0.05, self.parameters['rotation_speed'])
                      * (0.5 + self._bass * 0.9)) % 1000.0
        self._cam = (self._cam + dt * speed * 0.45) % 1000.0

        self._style_timer -= dt
        if self._style_timer <= 0.0:
            self._choose_style()

    def _set(self, name: str, value) -> None:
        try:
            self._prog[name].value = value
        except KeyError:
            pass

    def render(self) -> None:
        """Upload scene state and draw the club."""
        self._set('iTime', float(self.time))
        self._set('iResolution', (float(self.width), float(self.height)))
        self._set('iBass', self._bass)
        self._set('iMid', self._mid)
        self._set('iTreble', self._treble)
        self._set('iBeat', self._beat)
        self._set('iStrobe', self._strobe)
        self._set('iSpeed', max(0.05, float(self.parameters['speed'])))
        self._set('iNumTilesU', max(6.0, self._tiles_u))
        self._set('iNumTilesV', max(4.0, self._tiles_v))
        self._set('iRotationSpeed', max(0.05, float(self.parameters['rotation_speed'])))
        self._set('iLaserIntensity', max(0.0, float(self.parameters['laser_intensity'])))
        self._set('iZoom', max(0.1, float(self.parameters['zoom'])))
        self._set('iHue', float(self._hue))
        self._set('iSpin', float(self._spin))
        self._set('iCam', float(self._cam))
        self._set('iTilt', float(self._tilt))
        self._set('iStyle', int(self._style))
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
