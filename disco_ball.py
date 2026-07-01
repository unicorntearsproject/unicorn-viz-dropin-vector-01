"""Disco Ball drop-in effect.

Full raymarched disco ball with mirror-tile reflections, audio-reactive
coloured spot beams, animated room geometry, floor bounce, and beat-triggered
camera shakes.

Config keys (under [effects.DiscoBall]):
    speed         float   overall animation speed multiplier  (default 1.0)
    num_tiles_u   int     tile columns  (default 16)
    num_tiles_v   int     tile rows     (default 12)
    rotation_speed float  disco-ball spin rate               (default 1.0)
    laser_intensity float occasional refractive laser boost  (default 1.0)
"""
from __future__ import annotations

import moderngl

from unicornviz.effects.base import BaseEffect, AudioData

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
uniform float iSpeed;
uniform float iNumTilesU;
uniform float iNumTilesV;
uniform float iRotationSpeed;
uniform float iLaserIntensity;
uniform float iZoom;

in vec2  v_uv;
out vec4 fragColor;

// ── constants ────────────────────────────────────────────────────────────────
#define PI  3.14159265
#define TAU 6.28318530

// ── palette ──────────────────────────────────────────────────────────────────
vec3 palette(float t) {
    return 0.5 + 0.5 * cos(TAU * (vec3(1.0) * t + vec3(0.0, 0.33, 0.67)));
}

// ── SDF helpers ──────────────────────────────────────────────────────────────
float sdSphere(vec3 p, float r) { return length(p) - r; }

float sdFloor(vec3 p) { return p.y + 2.2; }

// ── ray-sphere exact intersection ─────────────────────────────────────────────
bool hitSphere(vec3 ro, vec3 rd, float r, out float t) {
    float b = dot(ro, rd);
    float c = dot(ro, ro) - r * r;
    float h = b * b - c;
    if (h < 0.0) return false;
    t = -b - sqrt(h);
    return t > 0.001;
}

mat3 rotY(float a) {
    float s = sin(a), c = cos(a);
    return mat3(
         c, 0.0, s,
       0.0, 1.0, 0.0,
        -s, 0.0, c
    );
}

mat3 rotX(float a) {
    float s = sin(a), c = cos(a);
    return mat3(
        1.0, 0.0, 0.0,
        0.0, c,  -s,
        0.0, s,   c
    );
}

// ── tile normal on sphere ────────────────────────────────────────────────────
// Returns the outward-pointing normal of the tile's flat face.
vec3 tileNormal(vec3 nSphere) {
    float nu = iNumTilesU;
    float nv = iNumTilesV;
    // Spherical coords
    float theta = atan(nSphere.x, nSphere.z);   // azimuth  [-pi, pi]
    float phi   = acos(clamp(nSphere.y, -1.0, 1.0)); // polar [0, pi]
    // Quantise to tile centres
    float tu = floor(theta / TAU * nu + 0.5) / nu * TAU;
    float tv = floor(phi  / PI  * nv + 0.5) / nv * PI;
    float st = sin(tv); float ct = cos(tv);
    float sp = sin(tu); float cp = cos(tu);
    return normalize(vec3(st * sp, ct, st * cp));
}

// ── room colour given a ray direction ────────────────────────────────────────
vec3 roomColour(vec3 dir, float t) {
    // Simple procedural ceiling/walls/floor
    vec3 col = vec3(0.03, 0.02, 0.05);

    // Grid lines on the floor and ceiling
    vec2 grid = abs(fract(dir.xz / max(0.001, abs(dir.y)) * 2.0) - 0.5);
    float gf  = smoothstep(0.03, 0.0, min(grid.x, grid.y));
    col += gf * vec3(0.08, 0.03, 0.14);

    // Three rotating spot lights
    for (int i = 0; i < 3; i++) {
        float off = float(i) * TAU / 3.0;
        vec3 lDir = normalize(vec3(
            sin(t * 0.7 + off),
            -0.8,
            cos(t * 0.5 + off + 1.0)
        ));
        float spot = pow(max(0.0, dot(dir, lDir)), 18.0);
        col += spot * palette(float(i) / 3.0 + t * 0.07) * (1.0 + iBass * 0.8);
    }
    return col;
}

// ── main ─────────────────────────────────────────────────────────────────────
void main() {
    vec2 uv = (v_uv * 2.0 - 1.0) * vec2(iResolution.x / iResolution.y, 1.0);
    uv /= max(iZoom, 0.01);

    float t = iTime * iSpeed;

    // Camera with beat-triggered shake
    float shk  = iBeat * 0.06;
    vec3 ro = vec3(
        sin(t * 0.18) * 0.3 + shk * sin(t * 13.0),
        0.5 + sin(t * 0.11) * 0.15 + shk * cos(t * 17.0),
        3.5 + cos(t * 0.13) * 0.4
    );
    vec3 target = vec3(0.0, 0.3, 0.0);
    vec3 fwd    = normalize(target - ro);
    vec3 rgt    = normalize(cross(fwd, vec3(0.0, 1.0, 0.0)));
    vec3 up     = cross(rgt, fwd);
    vec3 rd     = normalize(fwd + uv.x * rgt + uv.y * up);

    float ballR = 1.0 + iBass * 0.06;

    float tHit;
    vec3 col;

    if (hitSphere(ro, rd, ballR, tHit)) {
        vec3 p  = ro + rd * tHit;
        vec3 nS = normalize(p);                  // smooth sphere normal

        // Rotate the ball in local space, then rotate tile normals back out.
        mat3 ballRot = rotY(t * 0.65 * iRotationSpeed) * rotX(t * 0.27 * iRotationSpeed);
        vec3 nLocal = transpose(ballRot) * nS;
        vec3 nTileLocal = tileNormal(nLocal);
        vec3 nT = normalize(ballRot * nTileLocal); // tile face normal in world space

        // Tile edge darkening (grout lines)
        float edge = length(nS - nT) * iNumTilesU;
        float grout = smoothstep(0.18, 0.30, edge);

        // Mirror reflection direction
        vec3 refl  = reflect(rd, nT);
        vec3 refrd = refract(rd, nT, 0.82);
        vec3 rcol  = roomColour(refl, t);

        // Specular highlight from overhead lamp
        vec3 lPos  = vec3(0.0, 4.0, 0.0);
        vec3 lDir  = normalize(lPos - p);
        float spec = pow(max(0.0, dot(refl, lDir)), 64.0) * (1.0 + iTreble * 2.0);

        // Fresnel rim glow
        float fres = pow(1.0 - abs(dot(rd, nT)), 3.0);

        // Occasional refractive laser sweeps crossing the ball.
        float pulseA = smoothstep(0.93, 1.0, sin(t * 0.55 + 1.4));
        float pulseB = smoothstep(0.95, 1.0, sin(t * 0.73 + 3.1));
        float pulse = max(pulseA, pulseB);
        vec3 l1 = normalize(vec3(sin(t * 0.9 + 0.4), -0.12, cos(t * 1.1 + 0.2)));
        vec3 l2 = normalize(vec3(cos(t * 1.2 + 1.7), 0.08, sin(t * 0.8 + 2.2)));
        float beam1 = pow(max(0.0, dot(refrd, l1)), 42.0);
        float beam2 = pow(max(0.0, dot(refrd, l2)), 52.0);
        vec3 laserCol = beam1 * vec3(0.35, 0.95, 1.0) + beam2 * vec3(1.0, 0.35, 0.9);
        laserCol *= pulse * (0.45 + iTreble * 0.9) * iLaserIntensity;

        col  = mix(rcol, rcol * 0.25, grout);    // grout darkens reflection
        col += spec * vec3(1.0, 0.95, 0.8);
        col += fres * palette(t * 0.1 + float(int(nT.x * 10.0 + nT.y * 7.0)) * 0.07)
                    * (0.4 + iMid * 0.6);
        col += laserCol;

        // Beat flash on ball surface
        col += iBeat * 0.35 * vec3(1.0, 0.8, 0.4);

    } else {
        // Environment / room
        col = roomColour(rd, t);

        // Floor reflections: hit the y=-2.2 plane
        if (rd.y < -0.001) {
            float tF = (-2.2 - ro.y) / rd.y;
            vec3 fp  = ro + rd * tF;
            // Spot lights reflected on floor
            for (int i = 0; i < 3; i++) {
                float off = float(i) * TAU / 3.0;
                vec3 lDir = normalize(vec3(
                    sin(t * 0.7 + off),
                    0.8,
                    cos(t * 0.5 + off + 1.0)
                ));
                float spot = pow(max(0.0, dot(rd, lDir)), 24.0);
                col += spot * palette(float(i) / 3.0 + t * 0.07) * (0.7 + iBass);
            }
            // Soft grid on floor
            vec2 fg  = abs(fract(fp.xz * 1.2) - 0.5);
            float gl = smoothstep(0.04, 0.0, min(fg.x, fg.y));
            col += gl * vec3(0.1, 0.04, 0.22) * (1.0 + iMid);
        }
    }

    // Vignette
    float vig = 1.0 - 0.45 * dot(v_uv - 0.5, v_uv - 0.5) * 4.0;
    col *= vig;

    // Filmic tone-map
    col = col / (col + 0.9);
    col = pow(max(col, 0.0), vec3(0.85));

    fragColor = vec4(col, 1.0);
}
"""


class DiscoBall(BaseEffect):
    """Audio-reactive raymarched disco ball with mirror tiles and sweeping spot beams.

    The ball surface is divided into a configurable grid of mirror tiles.
    Each tile reflects the surrounding room geometry independently,
    creating the classic disco-ball shimmer. Beat triggers camera shake;
    bass modulates ball radius; treble boosts specular highlights.
    """

    NAME = 'Disco Ball'
    AUTHOR = 'unicorn-viz drop-in'
    TAGS = ['vector', 'disco', 'raymarching', 'reflections']
    PING_PONG_FRIENDS = ['Vector', '3D Cube']

    def _init(self) -> None:
        self.parameters = {
            'speed': float(self.config.get('speed', 1.0)),
            'num_tiles_u': float(self.config.get('num_tiles_u', 16)),
            'num_tiles_v': float(self.config.get('num_tiles_v', 12)),
            'rotation_speed': float(self.config.get('rotation_speed', 1.0)),
            'laser_intensity': float(self.config.get('laser_intensity', 1.0)),
            'zoom': float(self.config.get('zoom', 1.0)),
        }

        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad(self._prog)

        self._bass   = 0.0
        self._mid    = 0.0
        self._treble = 0.0
        self._beat   = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass   = audio.bass_n
        self._mid    = audio.mid_n
        self._treble = audio.treble_n
        # Exponential decay for beat so it flashes briefly on each hit.
        self._beat   = max(0.0, self._beat - dt * 4.0)
        if audio.beat:
            self._beat = 1.0

    def _set(self, name: str, value) -> None:
        try:
            self._prog[name].value = value
        except KeyError:
            pass

    def render(self) -> None:
        self._set('iTime',       self.time)
        self._set('iResolution', (float(self.width), float(self.height)))
        self._set('iBass',       self._bass)
        self._set('iMid',        self._mid)
        self._set('iTreble',     self._treble)
        self._set('iBeat',       self._beat)
        self._set('iSpeed',      max(0.05, self.parameters['speed']))
        self._set('iNumTilesU',  max(4.0, self.parameters['num_tiles_u']))
        self._set('iNumTilesV',  max(3.0, self.parameters['num_tiles_v']))
        self._set('iRotationSpeed', max(0.05, self.parameters['rotation_speed']))
        self._set('iLaserIntensity', max(0.0, self.parameters['laser_intensity']))
        self._set('iZoom',           max(0.1, self.parameters['zoom']))
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
