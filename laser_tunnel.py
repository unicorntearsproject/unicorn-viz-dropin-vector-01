"""
Laser Tunnel — an outrun-grade neon polygon tunnel you fly straight through.

A single-pass fragment effect built around a wireframe n-gon tunnel (the
"TUNNEL" thumbnail on the unicorn-viz splash is the visual target): glowing
polygon rings racing toward the viewer, radial laser spokes connecting them,
a hard neon bloom on every edge, streaking warp-speed sparks rushing past,
and — on every beat — a **laser pulse** that rockets down the tube, a
chromatic-aberration punch, an FOV kick, and a hard roll-spin recoil.

Audio-reactive (deliberately aggressive — every band drives something):
  - bass    → FOV/zoom punch, ring brightness swell, flight-speed floor
  - mid     → hue rotation speed, spoke rotation speed
  - treble  → warp-spark density/speed, edge glow sharpness
  - beat    → laser pulse down the tube, roll-spin recoil, chromatic punch

Fully randomized at start: per-instance ``iSeed`` re-rolls the spark field, a
discrete **polygon side count** (5-10) is drawn per activation, a **palette
variant** (outrun magenta/cyan, laser-red/amber, matrix green/cyan, or full
spectrum) is drawn per activation, spin direction is rolled per instance, and
``self.time`` starts at a random phase — no two flights look alike from
frame 0. Tweakables (speed, intensity, zoom, spin_gain, strobe) ride live
from config / MIDI / the control room.
"""
from __future__ import annotations

import moderngl

from unicornviz.effects.base import BaseEffect, AudioData

_VERT = """
#version 330
in vec2 in_vert;
out vec2 v_pos;
void main() {
    v_pos = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330
// Laser Tunnel — neon polygon tunnel, laser spokes, beat-driven pulse race.
uniform float iTime;
uniform vec2  iResolution;
uniform float iBass;
uniform float iMid;
uniform float iTreble;
uniform float iPulse;     // beat laser-pulse envelope [0,1], 1 = just fired
uniform float iKick;      // beat roll/FOV recoil envelope [0,1]
uniform float iSeed;      // per-instance spark-field offset
uniform float iSpeed;
uniform float iIntensity;
uniform float iZoomGain;
uniform float iSpinGain;
uniform float iStrobeGain;
uniform float iPalette;   // 0 outrun, 1 laser-red, 2 matrix, 3 spectrum
uniform float iSides;     // polygon side count (5..10)
uniform float iSpin;      // spin direction (+1 / -1)
in  vec2 v_pos;
out vec4 fragColor;

#define PI  3.14159265359
#define TAU 6.28318530718

float hash11(float n) { return fract(sin(n * 78.233 + iSeed) * 43758.5453); }
float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21) + iSeed);
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

vec3 palette(float t) {
    if (iPalette < 0.5) {
        // outrun: magenta <-> cyan
        return mix(vec3(1.0, 0.10, 0.65), vec3(0.10, 0.85, 1.0), 0.5 + 0.5 * sin(t * TAU));
    } else if (iPalette < 1.5) {
        // laser-red / amber danger
        return mix(vec3(1.0, 0.05, 0.10), vec3(1.0, 0.65, 0.05), 0.5 + 0.5 * sin(t * TAU));
    } else if (iPalette < 2.5) {
        // matrix green / cyan
        return mix(vec3(0.05, 1.0, 0.35), vec3(0.10, 0.85, 0.9), 0.5 + 0.5 * sin(t * TAU));
    }
    // full spectrum
    vec3 a = vec3(0.5), b = vec3(0.5), c = vec3(1.0), d = vec3(0.0, 0.33, 0.67);
    return a + b * cos(TAU * (c * t + d));
}

// Regular-polygon distance metric: iso-contours of the returned value trace
// an n-sided polygon rather than a circle, so tunnel "rings" read as faceted
// wireframe hoops instead of smooth circles.
float ngonDist(vec2 p, float sides) {
    float a = atan(p.x, p.y) + PI;
    float seg = TAU / sides;
    return cos(floor(0.5 + a / seg) * seg - a) * length(p);
}

void main() {
    vec2 uv = v_pos;
    float aspect = iResolution.x / max(iResolution.y, 1.0);

    float t = iTime * (0.9 + iSpeed * 0.6);
    float energy = clamp((iBass + iMid + iTreble) / 3.0, 0.0, 1.0);

    // Roll spin + FOV punch on beat, continuous slow drift otherwise.
    float roll = t * 0.08 * iSpin + iKick * iSpinGain * 1.1 * iSpin;
    float zoom = 1.0 - (iBass * 0.10 + iKick * 0.18) * iZoomGain;
    vec2 p = (uv - 0.5) * vec2(aspect, 1.0) * zoom;
    float cr = cos(roll), sr = sin(roll);
    p = mat2(cr, -sr, sr, cr) * p;

    float dist = length(p) + 1e-4;
    float pd = abs(ngonDist(p, iSides)) + 1e-4;
    float ang = atan(p.y, p.x);

    // Forward-flight depth: rings race toward the viewer, speed floor from bass.
    float flight = t * (0.55 + iBass * 0.9 + energy * 0.6);
    float depth = 0.24 / pd - flight;

    vec3 col = vec3(0.0);

    // --- polygon wireframe rings (faceted hoops receding into the tunnel) ---
    float ringPos = fract(depth);
    float ring = smoothstep(0.06, 0.0, min(ringPos, 1.0 - ringPos));
    float ringDepth = floor(depth);
    float ringHue = fract(ringDepth * 0.09 + t * (0.05 + iMid * 0.22));
    float fog = clamp(1.0 - pd * 1.15, 0.0, 1.0);
    col += palette(ringHue) * ring * fog * (0.75 + iIntensity * 0.55) * (0.55 + iBass * 0.9);

    // --- laser spokes: thin radial beams at each polygon vertex ---
    float segAng = TAU / iSides;
    float spokeA = abs(fract((ang + roll * 0.0) / segAng) - 0.5);
    float spoke = smoothstep(0.028, 0.0, spokeA) * fog;
    col += palette(fract(ringHue + 0.33)) * spoke * (0.6 + iMid * 1.3);

    // --- bright core glow at the vanishing point ---
    col += palette(fract(t * 0.06 + 0.12)) * smoothstep(0.22, 0.0, dist) * (0.5 + iTreble * 0.8);

    // --- warp-speed sparks streaking past, treble-driven density ---
    for (int i = 0; i < 24; i++) {
        float fi = float(i);
        if (fi > 6.0 + iTreble * 18.0) break;
        float sa = hash11(fi * 3.7) * TAU;
        float sr0 = 0.15 + hash11(fi * 5.1) * 0.9;
        float sp = fract(t * (0.9 + hash11(fi * 2.3) * 2.4) + hash11(fi * 7.3));
        vec2 sPos = vec2(cos(sa), sin(sa)) * mix(sr0, sr0 * 1.4, sp);
        float streak = smoothstep(0.010, 0.0, length(p - sPos)) * smoothstep(0.0, 0.25, sp) * smoothstep(1.0, 0.6, sp);
        col += palette(fract(sa / TAU + 0.5)) * streak * (0.5 + iTreble * 1.2);
    }

    // --- beat laser pulse: a bright ring rocketing down the tube ---
    float pulseDepth = mix(2.2, 0.0, 1.0 - iPulse);
    float pulseRing = smoothstep(0.10, 0.0, abs(depth - pulseDepth));
    col += palette(fract(t * 0.1)) * pulseRing * iPulse * 1.6 * iStrobeGain;

    // --- neon bloom (cheap): boost anything already hot ---
    col += pow(max(col - 0.55, 0.0), vec3(1.5)) * 1.5;

    // Chromatic aberration, heavier on the beat kick.
    float ca = 0.0018 + iKick * 0.010 + iPulse * 0.006;
    col.r += ca * 40.0 * ring * fog;
    col.b -= ca * 20.0 * ring * fog;

    // Full-room strobe flash on the hardest hits.
    col += vec3(1.0, 0.9, 1.0) * iKick * iKick * 0.20 * iStrobeGain;

    // Vignette + flicker + tonemap.
    col *= 0.96 + 0.04 * hash11(floor(t * 26.0));
    col *= smoothstep(1.3, 0.35, length(uv - 0.5));
    col = col / (1.0 + col * 0.55);
    col = pow(clamp(col, 0.0, 1.0), vec3(0.85));
    fragColor = vec4(col, 1.0);
}
"""


class LaserTunnel(BaseEffect):
    NAME = "Laser Tunnel"
    AUTHOR = "unicorn-viz"
    TAGS = ['vector', 'immersive', 'retro', 'tech', 'neon', 'laser', 'intense', 'hard']
    PING_PONG_FRIENDS = [
        # Vector / retro neighbours
        'Vector',
        '3D Cube',
        'Disco Ball',
        'Tron Grid',
        'Copper Bars',
        'Fractal Zoom',
        # Immersive / tech friends
        'Tunnel',
        'Wormhole',
        'Cathedral of Bass',
        'Cyber War',
        'Hacker Terminal',
        'Threat Matrix',
        'Reactor Breach',
        # Audio-analysis visualizers
        'Audio Spectrum',
        'Audio Waveforms',
    ]

    def _init(self) -> None:
        self.parameters = {
            "speed": float(self.config.get("speed", 1.0)),
            "intensity": float(self.config.get("intensity", 1.0)),
            "zoom": float(self.config.get("zoom", 1.0)),
            "spin_gain": float(self.config.get("spin_gain", 1.0)),
            "strobe": float(self.config.get("strobe", 1.0)),
            # Startup randomisation: re-roll the warp-spark field.
            "seed": float(self.rng.uniform(0.0, 100.0)),
        }
        # Discrete per-activation variety: polygon sides, palette, spin dir.
        self._sides = float(self.rng.integers(5, 11))
        self._palette = float(self.rng.integers(4))
        self._spin = 1.0 if self.rng.random() < 0.5 else -1.0
        self._bass = 0.0
        self._mid = 0.0
        self._treble = 0.0
        self._pulse = 0.0
        self._kick = 0.0
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad(self._prog)

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass_n
        self._mid = audio.mid_n
        self._treble = audio.treble_n
        # Envelopes with decay; a beat re-triggers the pulse race + kick.
        self._pulse = max(0.0, self._pulse - dt * 1.1)
        self._kick = max(0.0, self._kick - dt * 4.2)
        if audio.beat:
            self._pulse = 1.0
            self._kick = 1.0
        # Heavy low end keeps a slight recoil alive between hits.
        self._kick = max(self._kick, self._bass * 0.30)

    def render(self) -> None:
        p = self._prog
        p["iTime"].value = self.time
        p["iResolution"].value = (float(self.width), float(self.height))
        p["iBass"].value = self._bass
        p["iMid"].value = self._mid
        p["iTreble"].value = self._treble
        p["iPulse"].value = self._pulse
        p["iKick"].value = self._kick
        p["iSeed"].value = self.parameters["seed"]
        p["iSpeed"].value = self.parameters["speed"]
        p["iIntensity"].value = self.parameters["intensity"]
        p["iZoomGain"].value = self.parameters["zoom"]
        p["iSpinGain"].value = self.parameters["spin_gain"]
        p["iStrobeGain"].value = self.parameters["strobe"]
        p["iPalette"].value = self._palette
        p["iSides"].value = self._sides
        p["iSpin"].value = self._spin
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
