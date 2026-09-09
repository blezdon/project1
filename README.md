# CS 418 Rasterizer MP

Software rasterizer implementing a WebGL2-inspired input language: DDA/scanline triangle fill, perspective divide, viewport transform, and electives (depth, sRGB, hyp, frustum, cull, FSAA, alpha, matrices, textures, points, decals).

## Build & run

```bash
make build
make run file=testdata/rast-gray.txt
```

Requires Python 3 and Pillow (`pip install pillow`).

## Electives implemented

All listed electives: `elements`, `depth`, `sRGB`, `hyp`, `frustum`, `cull`, `fsaa`, `color 4`, `uniformMatrix`, `position 2/3`, `texture`/`texcoord`, `pointsize`/`drawArraysPoints`, `decals`.
