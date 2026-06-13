#!/usr/bin/env python3
"""
trazere_extract.py -- The Four Crystals of Trazere / Legend asset extractor

1) Decompresses PAC files (recursive byte-pair encoding, reverse engineered
   from LEGGO.EXE FUN_1000_c976/c9c5/c9e8/c9fa).
2) Renders tile sheets in the game's native sprite format:
   16-pixel chunks of 3 big-endian plane words (6 bytes per chunk),
   i.e. the renderer's "SI += 6" stride.

Usage:
  python3 trazere_extract.py decode FILE.PAC [out.raw]
  python3 trazere_extract.py tiles  FILE.PAC out.png [--width 32] [--height 16]
        [--skip 64] [--planes 3] [--cols 10] [--scale 3]

Examples:
  python3 trazere_extract.py tiles PACS/TILES2.PAC tiles2.png
  python3 trazere_extract.py tiles PACS/TILESX.PAC tilesx.png --skip 0
  python3 trazere_extract.py decode PACS/TITLE.PAC   # then render 320x200 planar
"""
import sys, os, argparse


# ---------------- PAC decompressor (BPE) ----------------

def decompress_pac(data, verbose=False):
    pos = 0
    output = bytearray()
    chunk_num = 0
    while pos + 4 <= len(data):
        b0, b1, b2, b3 = data[pos:pos+4]
        pos += 4
        more = (b0 & 0x80) != 0
        count = ((b0 & 0x7F) << 8) | b1
        in_n  = ((b2 << 8) | b3) + 1
        n     = count + 1
        if pos + 3*n > len(data):
            break
        ta = data[pos:pos+n]; pos += n
        tb = data[pos:pos+n]; pos += n
        tc = data[pos:pos+n]; pos += n

        td = bytearray(256)
        for bx in range(count, -1, -1):
            sym = ta[bx]
            if td[sym] == 0 and (bx & 0xFF) < 0x80:
                td[sym] = (bx & 0xFF) | 0x80
            else:
                td[sym] = 0xFF

        start = len(output)
        for _ in range(in_n):
            if pos >= len(data):
                break
            al = data[pos]; pos += 1
            bp = count
            stack = []
            running = True
            while running:
                d = td[al]
                branch = False
                if d == 0xFF:
                    while bp >= 0 and ta[bp] != al:
                        bp -= 1
                    branch = bp >= 0
                elif d & 0x80:
                    idx = d - 0x80
                    if bp >= idx:
                        bp = idx
                        branch = True
                if branch:
                    stack.append(bp)
                    al = tc[bp]
                    bp -= 1
                    if bp >= 0:
                        continue
                    output.append(al)
                else:
                    output.append(al)
                while True:
                    if not stack:
                        running = False
                        break
                    saved = stack.pop()
                    al = tb[saved]
                    bp = saved - 1
                    if bp >= 0:
                        break
                    output.append(al)
        if verbose:
            print(f"  chunk {chunk_num}: tables={n} in={in_n} out={len(output)-start}")
        chunk_num += 1
        if not more:
            break
    return bytes(output)




def decompress_all(data, verbose=False):
    """Decode ALL concatenated compressed streams in a PAC file.
    Dungeon files (per FUN_1000_b765) can contain several streams."""
    streams = []
    pos = 0
    while pos < len(data) - 4:
        out, newpos = _decompress_stream(data, pos)
        if newpos == pos or not out:
            break
        if verbose:
            print(f"stream {len(streams)}: [{pos:#x}..{newpos:#x}) -> {len(out)} bytes")
        streams.append(out)
        pos = newpos
    return streams


def _decompress_stream(data, pos):
    output = bytearray()
    while pos + 4 <= len(data):
        b0, b1, b2, b3 = data[pos:pos+4]
        pos += 4
        more = (b0 & 0x80) != 0
        count = ((b0 & 0x7F) << 8) | b1
        in_n  = ((b2 << 8) | b3) + 1
        n = count + 1
        if pos + 3*n > len(data):
            break
        ta = data[pos:pos+n]; pos += n
        tb = data[pos:pos+n]; pos += n
        tc = data[pos:pos+n]; pos += n
        td = bytearray(256)
        for bx in range(count, -1, -1):
            sym = ta[bx]
            if td[sym] == 0 and (bx & 0xFF) < 0x80:
                td[sym] = (bx & 0xFF) | 0x80
            else:
                td[sym] = 0xFF
        for _ in range(in_n):
            if pos >= len(data):
                break
            al = data[pos]; pos += 1
            bp = count; stack = []
            running = True
            while running:
                d = td[al]; branch = False
                if d == 0xFF:
                    while bp >= 0 and ta[bp] != al:
                        bp -= 1
                    branch = bp >= 0
                elif d & 0x80:
                    idx = d - 0x80
                    if bp >= idx:
                        bp = idx; branch = True
                if branch:
                    stack.append(bp); al = tc[bp]; bp -= 1
                    if bp >= 0:
                        continue
                    output.append(al)
                else:
                    output.append(al)
                while True:
                    if not stack:
                        running = False; break
                    sv = stack.pop(); al = tb[sv]; bp = sv - 1
                    if bp >= 0:
                        break
                    output.append(al)
        if not more:
            break
    return bytes(output), pos



# LIVE remap table (128 entries x 6 bytes), captured from the running game at
# DS:BC96. Entry 0 = identity. Entry index = per-sprite remap ID (AL passed to
# the patcher at CS:7510). Each byte's low nibble -> color via NIB2COLOR.

# Empirical character color mappings, derived by pixel-matching frames
# against an in-game screenshot. Each maps storage combos 0-7 -> palette indices.
# These reproduce the on-screen appearance exactly.
# (The corresponding remap nibbles aren't in the EXE's default remap table;
# party-member colors live in character records / save data.)
CHAR_MAPS = {
    'M1A': {0:0, 1:4, 2:12, 3:10, 4:14, 5:15, 6:12, 7:6}, # warrior
    'M1B': {0:0, 1:4, 2:12, 3:10, 4:2, 5:15, 6:1, 7:8},   # bard
    'M1C': {0:0, 1:4, 2:8, 3:2, 4:14, 5:15, 6:12, 7:10},  # stealthy dude
    'M1D': {0:0, 1:4, 2:12, 3:6, 4:15, 5:7, 6:9, 7:13},   # wizard
    # M1E (4th party character) wasn't visible on the verification screenshot
}

TILE_MAPS = {
    "TILESX": {0:0, 1:4, 2:1, 3:5, 4:3, 5:7, 6:8, 7:2, 8:8, 9:9, 10:10, 11:11, 12:12, 13:13, 14:14, 15:15},  # skip = 0
    "DUNGEON": {0:0, 1:4, 2:1, 3:5, 4:3, 5:7, 6:8, 7:2, 8:8, 9:9, 10:10, 11:11, 12:12, 13:13, 14:14, 15:15},
    "WATER": {0:0, 1:4, 2:1, 3:5, 4:3, 5:7, 6:8, 7:2, 8:8, 9:9, 10:10, 11:11, 12:12, 13:13, 14:14, 15:15},
    "BROWN": {0:0, 1:4, 2:1, 3:5, 4:3, 5:7, 6:12, 7:10, 8:8, 9:9, 10:10, 11:11, 12:12, 13:13, 14:14, 15:15},
    "RUNES": {0:0, 1:4, 2:1, 3:5, 4:3, 5:15, 6:10, 7:14, 8:8, 9:9, 10:10, 11:11, 12:12, 13:13, 14:14, 15:15},
    "BROWN_RUNES": {0:0, 1:4, 2:12, 3:10, 4:14, 5:15, 6:10, 7:14, 8:8, 9:9, 10:10, 11:11, 12:12, 13:13, 14:14, 15:15},
    "GRASS": {0:0, 1:4, 2:9, 3:13, 4:11, 5:7, 6:9, 7:13, 8:8, 9:9, 10:10, 11:11, 12:12, 13:13, 14:14, 15:15},
    "GRASS_DARK": {0:0, 1:4, 2:4, 3:1, 4:9, 5:7, 6:4, 7:1, 8:8, 9:9, 10:10, 11:11, 12:12, 13:13, 14:14, 15:15}
}


REMAPS = [[2, 3, 4, 5, 6, 7], [12, 3, 4, 5, 13, 14], [13, 9, 10, 5, 14, 5], [2, 4, 10, 5, 8, 14], [2, 3, 4, 5, 13, 14], [13, 14, 15, 5, 3, 4], [12, 8, 4, 5, 14, 15], [2, 3, 4, 12, 13, 14], [2, 9, 10, 12, 13, 14], [12, 13, 4, 5, 9, 10], [2, 9, 15, 5, 13, 14], [4, 5, 4, 5, 13, 14], [12, 13, 14, 15, 4, 5], [2, 3, 4, 5, 4, 5], [12, 13, 14, 15, 9, 10], [12, 13, 14, 15, 12, 8], [12, 13, 14, 15, 6, 7], [12, 13, 14, 5, 6, 7], [12, 13, 14, 5, 12, 8], [12, 13, 14, 5, 14, 15], [12, 13, 14, 5, 10, 11], [12, 13, 14, 5, 3, 4], [12, 13, 14, 5, 13, 14], [9, 10, 11, 5, 6, 7], [2, 9, 10, 11, 13, 15], [2, 3, 4, 5, 9, 10], [2, 9, 10, 5, 14, 15], [2, 3, 4, 5, 12, 13], [13, 14, 15, 5, 2, 3], [2, 9, 10, 5, 12, 8], [2, 7, 4, 5, 13, 15], [2, 3, 4, 5, 14, 15], [13, 14, 15, 5, 9, 10], [13, 14, 15, 5, 6, 7], [2, 3, 4, 5, 12, 8], [1, 2, 3, 4, 6, 7], [12, 12, 13, 14, 6, 7], [13, 15, 5, 5, 6, 7], [12, 8, 14, 15, 6, 7], [3, 4, 5, 5, 6, 7], [3, 15, 5, 5, 6, 7], [12, 13, 14, 15, 5, 5], [12, 3, 4, 5, 14, 15], [12, 3, 4, 5, 8, 15], [12, 3, 4, 5, 13, 14], [8, 9, 10, 5, 8, 15], [12, 8, 14, 5, 3, 4], [12, 13, 14, 14, 2, 13], [9, 3, 4, 5, 10, 11], [3, 4, 5, 5, 10, 11], [3, 4, 11, 5, 9, 10], [2, 11, 4, 5, 9, 10], [12, 13, 14, 7, 0, 8], [13, 14, 15, 7, 13, 14], [12, 8, 10, 11, 0, 0], [13, 14, 4, 5, 8, 15], [2, 2, 9, 10, 0, 0], [2, 10, 11, 5, 0, 0], [2, 10, 5, 5, 0, 0], [12, 12, 8, 14, 0, 0], [1, 2, 6, 7, 0, 0], [1, 6, 7, 4, 0, 0], [13, 14, 5, 5, 0, 0], [1, 1, 2, 3, 0, 0], [2, 3, 4, 5, 2, 9], [2, 3, 4, 5, 10, 11], [2, 3, 4, 5, 11, 5], [2, 3, 4, 5, 8, 15], [2, 3, 4, 5, 15, 5], [2, 3, 4, 5, 7, 4], [2, 3, 4, 5, 2, 3], [8, 14, 15, 5, 6, 0], [12, 8, 14, 15, 5, 0], [2, 9, 10, 5, 8, 0], [2, 9, 10, 11, 5, 0], [2, 9, 4, 5, 8, 0], [2, 9, 4, 5, 5, 0], [2, 7, 4, 5, 5, 0], [2, 6, 7, 4, 5, 0], [13, 14, 15, 5, 12, 8], [2, 9, 4, 5, 6, 7], [2, 9, 10, 5, 4, 5], [8, 14, 15, 5, 2, 3], [9, 10, 11, 5, 12, 8], [14, 15, 15, 5, 0, 0], [13, 14, 15, 5, 8, 14], [13, 14, 15, 5, 13, 14], [12, 6, 7, 5, 13, 14], [1, 2, 3, 0, 2, 3], [1, 2, 9, 0, 2, 9], [1, 12, 13, 0, 12, 13], [2, 3, 4, 5, 3, 4], [2, 3, 4, 14, 12, 8], [9, 10, 11, 5, 10, 11], [13, 14, 15, 5, 14, 15], [2, 3, 4, 15, 13, 14], [2, 3, 4, 10, 2, 9], [2, 3, 12, 13, 6, 7], [12, 13, 14, 15, 13, 14], [6, 7, 4, 0, 7, 4], [6, 7, 4, 0, 12, 8], [2, 9, 10, 11, 9, 10], [2, 3, 4, 4, 2, 3], [2, 9, 10, 11, 12, 8], [12, 13, 14, 15, 3, 4], [1, 2, 9, 0, 1, 2], [1, 2, 3, 0, 1, 2], [1, 12, 13, 0, 1, 12], [9, 10, 11, 0, 9, 10], [12, 13, 14, 15, 12, 13], [6, 7, 4, 0, 6, 7], [2, 9, 10, 0, 2, 9], [12, 13, 14, 15, 8, 13], [12, 13, 14, 15, 3, 5], [13, 14, 15, 7, 48, 49], [50, 51, 1, 2, 3, 4], [5, 0, 12, 13, 14, 15], [5, 0, 12, 13, 12, 13], [2, 3, 4, 5, 14, 15], [15, 15, 8, 8, 126, 68], [72, 80, 96, 64, 64, 0], [16, 40, 68, 130, 68, 40], [16, 0, 16, 56, 84, 146], [16, 16, 16, 0, 68, 68], [68, 68, 68, 68, 68, 0], [16, 32, 64, 254, 4, 8], [16, 0, 144, 80, 48, 16], [24, 20, 18, 0, 16, 24]]
# Live XLAT semantics (rebuilt at runtime; nibble -> screen color, 0 = no-op):
NIB2COLOR = {0: None, 1: 4, 2: 1, 3: 5, 4: 3, 5: 7, 6: 8, 7: 2, 8: 6, 9: 9,
             10: 13, 11: 11, 12: 12, 13: 10, 14: 14, 15: 15}
COMBO_ORDER = [2, 3, 4, 5, 6, 7]


def mapping_to_values(mapping, default_identity=True):
    """Normalize mapping into a 16-entry list of palette indices (0-15)."""
    base = list(range(16)) if default_identity else [0] * 16
    if mapping is None:
        vals = base
    elif isinstance(mapping, dict):
        vals = base[:]
        for k, v in mapping.items():
            vals[int(k) & 0x0F] = int(v) & 0x0F
    else:
        vals = [int(v) & 0x0F for v in mapping]
        if len(vals) < 16:
            vals.extend(base[len(vals):16])
        vals = vals[:16]
    vals[0] = 0
    return vals


def parse_mapping_values(text):
    """Parse comma/space separated 16-value mapping string."""
    parts = text.replace(',', ' ').split()
    if len(parts) != 16:
        raise SystemExit("--mapping-values needs exactly 16 values (0-15)")
    vals = []
    for p in parts:
        v = int(p, 0)
        if v < 0 or v > 15:
            raise SystemExit(f"mapping value out of range: {v} (expected 0..15)")
        vals.append(v)
    vals[0] = 0
    return vals


def _mapping_dict_literal(mapping_values):
    """Return mapping text in the requested dict-literal style."""
    return '{' + ', '.join(f'{i}:{int(v) & 0x0F}' for i, v in enumerate(mapping_values[:16])) + '}'


def save_mapping_config(map_file, pac_path, mapping_values):
    """Save current mapping as {"PAC_BASENAME": {0:0, ...}} text.
    Existing file content is preserved and updated in-place by key."""
    key = os.path.splitext(os.path.basename(pac_path))[0]
    entry = f'"{key}": {_mapping_dict_literal(mapping_values)}'

    existing = {}
    if os.path.exists(map_file):
        txt = open(map_file, 'r', encoding='utf-8').read().strip()
        if txt:
            try:
                parsed = eval(txt, {"__builtins__": {}}, {})
                if isinstance(parsed, dict):
                    existing = parsed
            except Exception:
                existing = {}

    existing[key] = {i: int(mapping_values[i]) & 0x0F for i in range(16)}

    lines = ['{']
    keys = sorted(existing.keys())
    for i, k in enumerate(keys):
        vals = [existing[k].get(x, x) for x in range(16)]
        suffix = ',' if i < len(keys) - 1 else ''
        lines.append(f'    "{k}": {_mapping_dict_literal(vals)}{suffix}')
    lines.append('}')
    open(map_file, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    return key, entry


def load_pac_stream(pac_path, stream=0, verbose=True):
    """Read PAC and return selected decompressed stream raw bytes."""
    raw_in = open(pac_path, 'rb').read()
    streams = decompress_all(raw_in, verbose=verbose)
    if not streams:
        raise SystemExit(f"failed to decompress any stream from {pac_path}")
    if stream < 0 or stream >= len(streams):
        raise SystemExit(f"stream index out of range for {pac_path}: {stream} (have {len(streams)})")
    return streams[stream], len(streams)


def build_sprite_sheet_image(raw, mapping_values, width=32, height=32, cols=10, palette=None,
                             planes=3, pad=3, bg=(50, 50, 60)):
    """Build a PIL image for sprite data using 16-entry mapping values."""
    from PIL import Image
    pal = palette or PALETTES['game1']
    mv = mapping_to_values(mapping_values)
    wch = width // 16
    row_b = wch * 2 * planes
    fsz = row_b * height
    n = len(raw) // fsz
    rows = (n + cols - 1) // cols if n else 1
    img = Image.new('RGB', (cols * (width + pad), rows * (height + pad)), bg)
    px = img.load()
    for s in range(n):
        base = s * fsz
        ox = (s % cols) * (width + pad)
        oy = (s // cols) * (height + pad)
        for y in range(height):
            for ch in range(wch):
                cb = base + y * row_b + ch * 2 * planes
                pw = [(raw[cb + 2 * p] << 8) | raw[cb + 2 * p + 1] for p in range(planes)]
                for bit in range(16):
                    bm = 0x8000 >> bit
                    c = sum(((pw[p] & bm) != 0) << p for p in range(planes))
                    if c < 16:
                        c = mv[c]
                    if c != 0:
                        px[ox + ch * 16 + bit, oy + y] = pal[c % len(pal)]
    return img, n


def build_tiles_sheet_image(raw, mapping_values, width=32, height=16, planes=3, skip=64,
                            cols=12, palette=None, pad=3, bg=(0, 0, 0)):
    """Build a PIL image for tile data using 16-entry mapping values."""
    from PIL import Image
    pal = palette or PALETTES['game1']
    mv = mapping_to_values(mapping_values)
    data = raw[skip:]
    chunks = width // 16
    row_b = chunks * 2 * planes
    tile_b = row_b * height
    n = len(data) // tile_b
    rows = (n + cols - 1) // cols if n else 1
    img = Image.new('RGB', (cols * (width + pad), rows * (height + pad)), bg)
    px = img.load()
    for s in range(n):
        base = s * tile_b
        ox = (s % cols) * (width + pad)
        oy = (s // cols) * (height + pad)
        for y in range(height):
            for ch in range(chunks):
                cb = base + y * row_b + ch * 2 * planes
                pw = [(data[cb + 2 * p] << 8) | data[cb + 2 * p + 1] for p in range(planes)]
                for bit in range(16):
                    bm = 0x8000 >> bit
                    c = sum(((pw[p] & bm) != 0) << p for p in range(planes))
                    if c < 16:
                        c = mv[c]
                    px[ox + ch * 16 + bit, oy + y] = pal[c % len(pal)]
    return img, n



def render_sprites_with_mapping(raw, out_png, mapping, width=32, height=32, cols=10, scale=3, palette=None):
    """Render sprite sheet using an explicit combo->palette-index mapping dict."""
    from PIL import Image
    img, n = build_sprite_sheet_image(raw, mapping_to_values(mapping), width, height, cols, palette, planes=3)
    img.resize((img.width*scale, img.height*scale), Image.NEAREST).save(out_png)
    print(f"saved {out_png} ({n} frames {width}x{height})")


def render_sprites_with_mapping_live(raw, mapping_values, width=32, height=40, cols=10, scale=3,
                                     palette=None, out_png='sprites_live.png', pac_path=None,
                                     stream=0, map_file='sprite_mappings.txt'):
    """Interactive pygame viewer for live editing of 16 mapping values."""
    try:
        import importlib
        pygame = importlib.import_module('pygame')
    except ImportError as exc:
        raise SystemExit("pygame is required for --live mode. Install with: pip install pygame") from exc

    from PIL import Image
    pal = palette or PALETTES['game1']
    mapping = mapping_to_values(mapping_values)
    selected = 0
    help_h = 240
    view_width = max(16, (width // 16) * 16)
    view_height = max(1, height)
    view_planes = max(1, min(4, 3))
    current_pac = pac_path or 'unknown.pac'
    current_stream = stream
    status_msg = 'ready'
    load_mode = False
    load_input = ''

    pygame.init()
    pygame.font.init()
    font = pygame.font.SysFont('Menlo', 18)
    small = pygame.font.SysFont('Menlo', 14)

    sheet, nframes = build_sprite_sheet_image(raw, mapping, view_width, view_height, cols, pal, planes=view_planes)
    scaled_sheet = sheet.resize((sheet.width * scale, sheet.height * scale), Image.NEAREST)
    sheet_surf = pygame.image.fromstring(scaled_sheet.tobytes(), scaled_sheet.size, scaled_sheet.mode)

    win_w = max(sheet_surf.get_width(), 700)
    win_h = sheet_surf.get_height() + help_h
    screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
    pygame.display.set_caption('Sprite Mapping Viewer')

    def ensure_window_size():
        nonlocal screen
        min_w = max(sheet_surf.get_width(), 700)
        min_h = sheet_surf.get_height() + help_h
        cur_w, cur_h = screen.get_size()
        if cur_w < min_w or cur_h < min_h:
            screen = pygame.display.set_mode((max(cur_w, min_w), max(cur_h, min_h)), pygame.RESIZABLE)

    def rebuild_sheet():
        nonlocal sheet, scaled_sheet, sheet_surf, nframes
        sheet, nframes = build_sprite_sheet_image(raw, mapping, view_width, view_height, cols, pal, planes=view_planes)
        scaled_sheet = sheet.resize((sheet.width * scale, sheet.height * scale), Image.NEAREST)
        sheet_surf = pygame.image.fromstring(scaled_sheet.tobytes(), scaled_sheet.size, scaled_sheet.mode)
        ensure_window_size()

    def draw_ui():
        screen.fill((24, 24, 30))
        screen.blit(sheet_surf, (0, 0))
        panel_y = sheet_surf.get_height()
        pygame.draw.rect(screen, (18, 18, 22), (0, panel_y, screen.get_width(), screen.get_height() - panel_y))

        title = font.render(
            f'file={os.path.basename(current_pac)} stream={current_stream} frames={nframes} '
            f'w={view_width} h={view_height} pl={view_planes} '
            f'selected={selected:02X} map[{selected:X}]={mapping[selected]:X}',
            True, (230, 230, 235)
        )
        screen.blit(title, (10, panel_y + 8))

        instructions = [
            'Left/Right: select source value   Up/Down: change mapped value',
            'Type 0-9 or A-F to set mapped value directly',
            'Shift+Left/Right: width -/+16   Shift+Up/Down: height -/+1',
            'PgUp/PgDn: planes +/-1   R: reset identity   Z: zero all   S: save PNG',
            'M: save map file   L: load PAC path   [/]: stream -/+   Q/Esc: quit',
        ]
        instr_y = panel_y + 40
        line_step = small.get_linesize() + 2
        for i, line in enumerate(instructions):
            text = small.render(line, True, (170, 170, 180))
            screen.blit(text, (10, instr_y + i * line_step))

        start_x = 10
        start_y = instr_y + len(instructions) * line_step + 8
        cell_w = 78
        cell_h = 28
        for idx in range(16):
            r = idx // 8
            c = idx % 8
            x = start_x + c * (cell_w + 6)
            y = start_y + r * (cell_h + 6)
            bg = (45, 55, 95) if idx == selected else (38, 38, 44)
            pygame.draw.rect(screen, bg, (x, y, cell_w, cell_h), border_radius=3)
            label = small.render(f'{idx:X}->{mapping[idx]:X}', True, (240, 240, 245))
            screen.blit(label, (x + 8, y + 6))

        status_line = status_msg
        if load_mode:
            status_line = f'LOAD PAC MODE: type path then Enter | Esc cancel  > {load_input}'
        status = small.render(status_line, True, (250, 210, 140) if load_mode else (130, 210, 170))
        status_y = start_y + (2 * (cell_h + 6)) + 8
        screen.blit(status, (10, status_y))

        pygame.display.flip()

    dirty = True
    clock = pygame.time.Clock()
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
                continue
            if ev.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((ev.w, ev.h), pygame.RESIZABLE)
                dirty = True
                continue
            if ev.type != pygame.KEYDOWN:
                continue

            k = ev.key
            mods = ev.mod
            if load_mode:
                if k == pygame.K_ESCAPE:
                    load_mode = False
                    load_input = ''
                    status_msg = 'load canceled'
                    dirty = True
                elif k == pygame.K_RETURN:
                    candidate = os.path.expanduser(load_input.strip())
                    if candidate:
                        try:
                            new_raw, stream_count = load_pac_stream(candidate, current_stream, verbose=True)
                            raw = new_raw
                            current_pac = candidate
                            rebuild_sheet()
                            status_msg = f'loaded {os.path.basename(candidate)} (streams={stream_count}, using {current_stream})'
                        except Exception as exc:
                            status_msg = f'load failed: {exc}'
                    else:
                        status_msg = 'load failed: empty path'
                    load_mode = False
                    load_input = ''
                    dirty = True
                elif k == pygame.K_BACKSPACE:
                    load_input = load_input[:-1]
                    dirty = True
                else:
                    if ev.unicode and ev.unicode.isprintable():
                        load_input += ev.unicode
                        dirty = True
                continue

            if k in (pygame.K_q, pygame.K_ESCAPE):
                running = False
            elif mods & pygame.KMOD_SHIFT and k == pygame.K_LEFT:
                next_width = max(16, view_width - 16)
                if next_width != view_width:
                    view_width = next_width
                    rebuild_sheet()
                    status_msg = f'width={view_width}'
                dirty = True
            elif mods & pygame.KMOD_SHIFT and k == pygame.K_RIGHT:
                view_width += 16
                rebuild_sheet()
                status_msg = f'width={view_width}'
                dirty = True
            elif mods & pygame.KMOD_SHIFT and k == pygame.K_UP:
                view_height += 1
                rebuild_sheet()
                status_msg = f'height={view_height}'
                dirty = True
            elif mods & pygame.KMOD_SHIFT and k == pygame.K_DOWN:
                next_height = max(1, view_height - 1)
                if next_height != view_height:
                    view_height = next_height
                    rebuild_sheet()
                    status_msg = f'height={view_height}'
                dirty = True
            elif k == pygame.K_PAGEUP:
                if view_planes < 4:
                    view_planes += 1
                    rebuild_sheet()
                    status_msg = f'planes={view_planes}'
                else:
                    status_msg = 'planes already at max 4'
                dirty = True
            elif k == pygame.K_PAGEDOWN:
                if view_planes > 1:
                    view_planes -= 1
                    rebuild_sheet()
                    status_msg = f'planes={view_planes}'
                else:
                    status_msg = 'planes already at min 1'
                dirty = True
            elif k == pygame.K_LEFT:
                selected = (selected - 1) & 0x0F
                dirty = True
            elif k == pygame.K_RIGHT:
                selected = (selected + 1) & 0x0F
                dirty = True
            elif k == pygame.K_UP:
                mapping[selected] = (mapping[selected] + 1) & 0x0F
                mapping[0] = 0
                rebuild_sheet()
                dirty = True
            elif k == pygame.K_DOWN:
                mapping[selected] = (mapping[selected] - 1) & 0x0F
                mapping[0] = 0
                rebuild_sheet()
                dirty = True
            elif k == pygame.K_r:
                mapping[:] = list(range(16))
                mapping[0] = 0
                rebuild_sheet()
                dirty = True
            elif k == pygame.K_z:
                mapping[:] = [0] * 16
                rebuild_sheet()
                dirty = True
            elif k == pygame.K_s:
                scaled_sheet.save(out_png)
                print(f'saved {out_png}')
                print('mapping:', ','.join(str(v) for v in mapping))
                status_msg = f'png saved: {out_png}'
                dirty = True
            elif k == pygame.K_m:
                key, _entry = save_mapping_config(map_file, current_pac, mapping)
                status_msg = f'map saved: {map_file} key="{key}"'
                print(f'saved map: {map_file} key="{key}"')
                print('{')
                print(f'    "{key}": {_mapping_dict_literal(mapping)}')
                print('}')
                dirty = True
            elif k == pygame.K_l:
                load_mode = True
                load_input = ''
                status_msg = 'enter PAC path'
                dirty = True
            elif k == pygame.K_LEFTBRACKET:
                next_stream = max(0, current_stream - 1)
                if next_stream != current_stream:
                    try:
                        new_raw, stream_count = load_pac_stream(current_pac, next_stream, verbose=True)
                        raw = new_raw
                        current_stream = next_stream
                        rebuild_sheet()
                        status_msg = f'stream {current_stream}/{stream_count-1}'
                    except Exception as exc:
                        status_msg = f'stream change failed: {exc}'
                else:
                    status_msg = 'already at stream 0'
                dirty = True
            elif k == pygame.K_RIGHTBRACKET:
                next_stream = current_stream + 1
                try:
                    new_raw, stream_count = load_pac_stream(current_pac, next_stream, verbose=True)
                    raw = new_raw
                    current_stream = next_stream
                    rebuild_sheet()
                    status_msg = f'stream {current_stream}/{stream_count-1}'
                except Exception as exc:
                    status_msg = f'stream change failed: {exc}'
                dirty = True
            else:
                hex_keys = {
                    pygame.K_0: 0, pygame.K_1: 1, pygame.K_2: 2, pygame.K_3: 3,
                    pygame.K_4: 4, pygame.K_5: 5, pygame.K_6: 6, pygame.K_7: 7,
                    pygame.K_8: 8, pygame.K_9: 9, pygame.K_a: 10, pygame.K_b: 11,
                    pygame.K_c: 12, pygame.K_d: 13, pygame.K_e: 14, pygame.K_f: 15,
                }
                if k in hex_keys:
                    mapping[selected] = hex_keys[k]
                    mapping[0] = 0
                    rebuild_sheet()
                    status_msg = f'map[{selected:X}]={mapping[selected]:X}'
                    dirty = True

        if dirty:
            draw_ui()
            dirty = False
        clock.tick(60)

    print('final mapping:', ','.join(str(v) for v in mapping))
    pygame.quit()


def render_tiles_with_mapping_live(raw, mapping_values, width=32, height=16, planes=3, skip=64,
                                   cols=10, scale=3, palette=None, out_png='tiles_live.png',
                                   pac_path=None, stream=0, map_file='tile_mappings.txt'):
    """Interactive pygame viewer for live editing of tile mapping values."""
    try:
        import importlib
        pygame = importlib.import_module('pygame')
    except ImportError as exc:
        raise SystemExit("pygame is required for --live mode. Install with: pip install pygame") from exc

    from PIL import Image
    pal = palette or PALETTES['game1']
    mapping = mapping_to_values(mapping_values)
    selected = 0
    help_h = 240
    view_width = max(16, (width // 16) * 16)
    view_height = max(1, height)
    view_planes = max(1, min(4, planes))
    view_skip = max(0, skip)
    current_pac = pac_path or 'unknown.pac'
    current_stream = stream
    status_msg = 'ready'
    load_mode = False
    load_input = ''

    pygame.init()
    pygame.font.init()
    font = pygame.font.SysFont('Menlo', 18)
    small = pygame.font.SysFont('Menlo', 14)

    sheet, ntiles = build_tiles_sheet_image(raw, mapping, view_width, view_height, view_planes, view_skip, cols, pal)
    scaled_sheet = sheet.resize((sheet.width * scale, sheet.height * scale), Image.NEAREST)
    sheet_surf = pygame.image.fromstring(scaled_sheet.tobytes(), scaled_sheet.size, scaled_sheet.mode)

    win_w = max(sheet_surf.get_width(), 700)
    win_h = sheet_surf.get_height() + help_h
    screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
    pygame.display.set_caption('Tile Mapping Viewer')

    def ensure_window_size():
        nonlocal screen
        min_w = max(sheet_surf.get_width(), 700)
        min_h = sheet_surf.get_height() + help_h
        cur_w, cur_h = screen.get_size()
        if cur_w < min_w or cur_h < min_h:
            screen = pygame.display.set_mode((max(cur_w, min_w), max(cur_h, min_h)), pygame.RESIZABLE)

    def rebuild_sheet():
        nonlocal sheet, scaled_sheet, sheet_surf, ntiles
        sheet, ntiles = build_tiles_sheet_image(raw, mapping, view_width, view_height, view_planes, view_skip, cols, pal)
        scaled_sheet = sheet.resize((sheet.width * scale, sheet.height * scale), Image.NEAREST)
        sheet_surf = pygame.image.fromstring(scaled_sheet.tobytes(), scaled_sheet.size, scaled_sheet.mode)
        ensure_window_size()

    def draw_ui():
        screen.fill((24, 24, 30))
        screen.blit(sheet_surf, (0, 0))
        panel_y = sheet_surf.get_height()
        pygame.draw.rect(screen, (18, 18, 22), (0, panel_y, screen.get_width(), screen.get_height() - panel_y))

        title = font.render(
            f'file={os.path.basename(current_pac)} stream={current_stream} tiles={ntiles} '
            f'w={view_width} h={view_height} pl={view_planes} skip={view_skip} '
            f'selected={selected:02X} map[{selected:X}]={mapping[selected]:X}',
            True, (230, 230, 235)
        )
        screen.blit(title, (10, panel_y + 8))

        instructions = [
            'Left/Right: select source value   Up/Down: change mapped value',
            'Type 0-9 or A-F to set mapped value directly',
            'Shift+Left/Right: width -/+16   Shift+Up/Down: height -/+1',
            'PgUp/PgDn: planes +/-1   ,/.: skip -/+1   Shift+,/.: skip -/+16',
            'R: reset identity   Z: zero all   S: save PNG',
            'M: save map file   L: load PAC path   [/]: stream -/+   Q/Esc: quit',
        ]
        instr_y = panel_y + 40
        line_step = small.get_linesize() + 2
        for i, line in enumerate(instructions):
            text = small.render(line, True, (170, 170, 180))
            screen.blit(text, (10, instr_y + i * line_step))

        start_x = 10
        start_y = instr_y + len(instructions) * line_step + 8
        cell_w = 78
        cell_h = 28
        for idx in range(16):
            r = idx // 8
            c = idx % 8
            x = start_x + c * (cell_w + 6)
            y = start_y + r * (cell_h + 6)
            bg = (45, 55, 95) if idx == selected else (38, 38, 44)
            pygame.draw.rect(screen, bg, (x, y, cell_w, cell_h), border_radius=3)
            label = small.render(f'{idx:X}->{mapping[idx]:X}', True, (240, 240, 245))
            screen.blit(label, (x + 8, y + 6))

        status_line = status_msg
        if load_mode:
            status_line = f'LOAD PAC MODE: type path then Enter | Esc cancel  > {load_input}'
        status = small.render(status_line, True, (250, 210, 140) if load_mode else (130, 210, 170))
        status_y = start_y + (2 * (cell_h + 6)) + 8
        screen.blit(status, (10, status_y))

        pygame.display.flip()

    dirty = True
    clock = pygame.time.Clock()
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
                continue
            if ev.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((ev.w, ev.h), pygame.RESIZABLE)
                dirty = True
                continue
            if ev.type != pygame.KEYDOWN:
                continue

            k = ev.key
            mods = ev.mod
            if load_mode:
                if k == pygame.K_ESCAPE:
                    load_mode = False
                    load_input = ''
                    status_msg = 'load canceled'
                    dirty = True
                elif k == pygame.K_RETURN:
                    candidate = os.path.expanduser(load_input.strip())
                    if candidate:
                        try:
                            new_raw, stream_count = load_pac_stream(candidate, current_stream, verbose=True)
                            raw = new_raw
                            current_pac = candidate
                            rebuild_sheet()
                            status_msg = f'loaded {os.path.basename(candidate)} (streams={stream_count}, using {current_stream})'
                        except Exception as exc:
                            status_msg = f'load failed: {exc}'
                    else:
                        status_msg = 'load failed: empty path'
                    load_mode = False
                    load_input = ''
                    dirty = True
                elif k == pygame.K_BACKSPACE:
                    load_input = load_input[:-1]
                    dirty = True
                else:
                    if ev.unicode and ev.unicode.isprintable():
                        load_input += ev.unicode
                        dirty = True
                continue

            if k in (pygame.K_q, pygame.K_ESCAPE):
                running = False
            elif mods & pygame.KMOD_SHIFT and k == pygame.K_LEFT:
                next_width = max(16, view_width - 16)
                if next_width != view_width:
                    view_width = next_width
                    rebuild_sheet()
                    status_msg = f'width={view_width}'
                dirty = True
            elif mods & pygame.KMOD_SHIFT and k == pygame.K_RIGHT:
                view_width += 16
                rebuild_sheet()
                status_msg = f'width={view_width}'
                dirty = True
            elif mods & pygame.KMOD_SHIFT and k == pygame.K_UP:
                view_height += 1
                rebuild_sheet()
                status_msg = f'height={view_height}'
                dirty = True
            elif mods & pygame.KMOD_SHIFT and k == pygame.K_DOWN:
                next_height = max(1, view_height - 1)
                if next_height != view_height:
                    view_height = next_height
                    rebuild_sheet()
                    status_msg = f'height={view_height}'
                dirty = True
            elif k == pygame.K_PAGEUP:
                if view_planes < 4:
                    view_planes += 1
                    rebuild_sheet()
                    status_msg = f'planes={view_planes}'
                else:
                    status_msg = 'planes already at max 4'
                dirty = True
            elif k == pygame.K_PAGEDOWN:
                if view_planes > 1:
                    view_planes -= 1
                    rebuild_sheet()
                    status_msg = f'planes={view_planes}'
                else:
                    status_msg = 'planes already at min 1'
                dirty = True
            elif k == pygame.K_COMMA:
                delta = 16 if mods & pygame.KMOD_SHIFT else 1
                next_skip = max(0, view_skip - delta)
                if next_skip != view_skip:
                    view_skip = next_skip
                    rebuild_sheet()
                    status_msg = f'skip={view_skip}'
                else:
                    status_msg = 'skip already at 0'
                dirty = True
            elif k == pygame.K_PERIOD:
                delta = 16 if mods & pygame.KMOD_SHIFT else 1
                view_skip += delta
                rebuild_sheet()
                status_msg = f'skip={view_skip}'
                dirty = True
            elif k == pygame.K_LEFT:
                selected = (selected - 1) & 0x0F
                dirty = True
            elif k == pygame.K_RIGHT:
                selected = (selected + 1) & 0x0F
                dirty = True
            elif k == pygame.K_UP:
                mapping[selected] = (mapping[selected] + 1) & 0x0F
                mapping[0] = 0
                rebuild_sheet()
                dirty = True
            elif k == pygame.K_DOWN:
                mapping[selected] = (mapping[selected] - 1) & 0x0F
                mapping[0] = 0
                rebuild_sheet()
                dirty = True
            elif k == pygame.K_r:
                mapping[:] = list(range(16))
                mapping[0] = 0
                rebuild_sheet()
                dirty = True
            elif k == pygame.K_z:
                mapping[:] = [0] * 16
                rebuild_sheet()
                dirty = True
            elif k == pygame.K_s:
                scaled_sheet.save(out_png)
                print(f'saved {out_png}')
                print('mapping:', ','.join(str(v) for v in mapping))
                status_msg = f'png saved: {out_png}'
                dirty = True
            elif k == pygame.K_m:
                key, _entry = save_mapping_config(map_file, current_pac, mapping)
                status_msg = f'map saved: {map_file} key="{key}"'
                print(f'saved map: {map_file} key="{key}"')
                print('{')
                print(f'    "{key}": {_mapping_dict_literal(mapping)}')
                print('}')
                dirty = True
            elif k == pygame.K_l:
                load_mode = True
                load_input = ''
                status_msg = 'enter PAC path'
                dirty = True
            elif k == pygame.K_LEFTBRACKET:
                next_stream = max(0, current_stream - 1)
                if next_stream != current_stream:
                    try:
                        new_raw, stream_count = load_pac_stream(current_pac, next_stream, verbose=True)
                        raw = new_raw
                        current_stream = next_stream
                        rebuild_sheet()
                        status_msg = f'stream {current_stream}/{stream_count-1}'
                    except Exception as exc:
                        status_msg = f'stream change failed: {exc}'
                else:
                    status_msg = 'already at stream 0'
                dirty = True
            elif k == pygame.K_RIGHTBRACKET:
                next_stream = current_stream + 1
                try:
                    new_raw, stream_count = load_pac_stream(current_pac, next_stream, verbose=True)
                    raw = new_raw
                    current_stream = next_stream
                    rebuild_sheet()
                    status_msg = f'stream {current_stream}/{stream_count-1}'
                except Exception as exc:
                    status_msg = f'stream change failed: {exc}'
                dirty = True
            else:
                hex_keys = {
                    pygame.K_0: 0, pygame.K_1: 1, pygame.K_2: 2, pygame.K_3: 3,
                    pygame.K_4: 4, pygame.K_5: 5, pygame.K_6: 6, pygame.K_7: 7,
                    pygame.K_8: 8, pygame.K_9: 9, pygame.K_a: 10, pygame.K_b: 11,
                    pygame.K_c: 12, pygame.K_d: 13, pygame.K_e: 14, pygame.K_f: 15,
                }
                if k in hex_keys:
                    mapping[selected] = hex_keys[k]
                    mapping[0] = 0
                    rebuild_sheet()
                    status_msg = f'map[{selected:X}]={mapping[selected]:X}'
                    dirty = True

        if dirty:
            draw_ui()
            dirty = False
        clock.tick(60)

    print('final mapping:', ','.join(str(v) for v in mapping))
    pygame.quit()

def render_sprites(raw, out_png, width=32, height=40, cols=10, scale=3, palette=None, remap=None):
    """SPIT-style uniform frame sheets: 3-plane 16px chunks, combo0=transparent."""
    from PIL import Image
    pal = palette or [(255,0,255),(40,40,40),(170,85,0),(220,180,140),(0,120,0),(200,0,0),(180,180,60),(240,240,240)]
    cmap = None
    if remap is not None:
        rm = REMAPS[remap]
        cmap = {0: None, 1: 1}
        for i, c in enumerate(COMBO_ORDER):
            cmap[c] = NIB2COLOR[rm[i] & 0x0F]
    wch = width // 16
    row_b = wch * 6
    fsz = row_b * height
    n = len(raw) // fsz
    pad = 3
    rows = (n + cols - 1)//cols
    img = Image.new('RGB', (cols*(width+pad), rows*(height+pad)), (60,60,80))
    px = img.load()
    for s in range(n):
        base = s*fsz
        ox = (s%cols)*(width+pad); oy = (s//cols)*(height+pad)
        for y in range(height):
            for ch in range(wch):
                cb = base + y*row_b + ch*6
                pw = [(raw[cb+2*p]<<8)|raw[cb+2*p+1] for p in range(3)]
                for bit in range(16):
                    bm = 0x8000>>bit
                    c = sum(((pw[p]&bm)!=0)<<p for p in range(3))
                    if cmap is not None:
                        m = cmap.get(c)
                        if m is None:
                            continue
                        c = m
                    px[ox+ch*16+bit, oy+y] = pal[c % len(pal)]
    img.resize((img.width*scale, img.height*scale), Image.NEAREST).save(out_png)
    print(f"saved {out_png} ({n} frames {width}x{height}, remainder {len(raw)%fsz})")

# ---------------- tile sheet renderer ----------------

# Placeholder 8/16-color palettes; swap in real game palettes when known.
EGA = [(0,0,0),(0,0,170),(0,170,0),(0,170,170),(170,0,0),(170,0,170),(170,85,0),(170,170,170),
       (85,85,85),(85,85,255),(85,255,85),(85,255,255),(255,85,85),(255,85,255),(255,255,85),(255,255,255)]



# Real game palettes extracted from the executables:
#  - 'title': DOS LEGGO.EXE @0x2D1DA, cross-platform confirmed vs Amiga leggo @0x42E
#  - 'title_amiga': the Amiga-side version of the same palette
#  - 'dungeon_dark': DOS palette bank @0x291F6 (first entry) - probable in-game dungeon palette
#  - 'startup': Amiga leggo @0x1D6D6, copied to color registers at boot
PALETTES = {
    'ega': None,  # placeholder resolved to EGA below
    'title': [(0,0,0),(24,57,57),(142,134,77),(77,113,113),(8,16,16),(49,85,85),(105,28,0),(117,134,134),(57,0,113),(0,85,57),(85,57,24),(85,142,57),(57,28,12),(57,113,28),(113,85,36),(142,109,45)],
    'title_amiga': [(0,0,0),(34,68,68),(68,102,204),(102,136,136),(0,17,17),(68,102,102),(136,34,0),(170,170,170),(34,68,204),(0,102,68),(102,68,34),(102,170,68),(68,34,0),(68,136,34),(136,102,34),(170,136,68)],
    'dungeon_dark': [(0,0,0),(0,0,0),(49,53,57),(61,53,57),(53,57,45),(61,36,40),(24,28,57),(61,49,53),(49,32,61),(20,53,57),(49,65,24),(61,65,24),(69,61,93),(16,12,101),(65,24,69),(61,85,81)],
    'game1': [(0, 0, 0), (24, 57, 57), (53, 77, 158), (77, 113, 113), (8, 16, 16), (49, 85, 85), (105, 28, 0), (134, 142, 142), (24, 53, 158), (0, 85, 57), (85, 57, 24), (85, 142, 57), (57, 28, 12), (57, 113, 28), (113, 85, 36), (142, 109, 45)],
    'game2': [(0, 0, 0), (24, 57, 57), (142, 134, 77), (77, 113, 113), (8, 16, 16), (49, 85, 85), (105, 28, 0), (117, 134, 134), (57, 0, 113), (0, 85, 57), (85, 57, 24), (85, 142, 57), (57, 28, 12), (57, 113, 28), (113, 85, 36), (142, 109, 45)],
    'game3': [(0, 0, 0), (85, 85, 85), (0, 20, 150), (142, 142, 142), (16, 16, 16), (198, 198, 198), (142, 28, 0), (206, 170, 113), (0, 0, 101), (61, 85, 0), (117, 85, 28), (121, 142, 57), (89, 57, 0), (89, 113, 28), (146, 113, 57), (178, 142, 85)],
    'game1_tiles': [(85, 57, 24), (85, 142, 57), (57, 28, 12), (57, 113, 28), (113, 85, 36), (142, 109, 45), (0, 65, 69), (28, 0, 28)],
    'game2_tiles': [(85, 57, 24), (85, 142, 57), (57, 28, 12), (57, 113, 28), (113, 85, 36), (142, 109, 45), (0, 65, 89), (28, 0, 28)],
    'startup': [(255,102,0),(17,68,0),(85,136,0),(102,204,0),(0,136,0),(51,0,0),(51,136,0),(0,0,0),(0,0,0),(0,17,136),(0,0,0),(0,0,0),(0,119,68),(0,0,0),(0,17,136),(51,204,68)],
}

def get_palette(name):
    if name in (None, 'ega'):
        return EGA
    if name not in PALETTES or PALETTES[name] is None:
        raise SystemExit(f"unknown palette '{name}', choices: {list(PALETTES)}")
    return PALETTES[name]


def render_tiles(raw, out_png, width=32, height=16, planes=3, skip=64,
                 cols=12, scale=2, palette=None, remap=None):
    """Floor tiles. Screen-verified color pipeline (unified with sprites):
    combo 0 -> palette 0, combo 1 -> palette 4 (fixed),
    combos 2-7 -> NIB2COLOR[remap_nibbles[i]] via the live remap system.
    Default remap [2,3,4,5,2,3] reproduces plain dungeon floors exactly."""
    from PIL import Image
    pal = palette or PALETTES['game1']
    rm = REMAPS[remap] if isinstance(remap, int) else (remap or [2,3,4,5,2,3])
    cmap = {0: 0, 1: 4}
    for i, combo in enumerate(COMBO_ORDER):
        cmap[combo] = NIB2COLOR[rm[i] & 0x0F] or 0
    data = raw[skip:]
    chunks = width // 16
    row_b = chunks * 2 * planes
    tile_b = row_b * height
    n = len(data) // tile_b
    print(f"{n} tiles of {width}x{height} {planes}pl ({tile_b}B), remainder {len(data)%tile_b}")
    pad = 3
    rows = (n + cols - 1) // cols
    img = Image.new('RGB', (cols*(width+pad), rows*(height+pad)), (0, 0, 0))
    px = img.load()
    for s in range(n):
        base = s * tile_b
        ox = (s % cols) * (width+pad); oy = (s // cols) * (height+pad)
        for y in range(height):
            for ch in range(chunks):
                cb = base + y*row_b + ch*2*planes
                pw = [(data[cb+2*p] << 8) | data[cb+2*p+1] for p in range(planes)]
                for bit in range(16):
                    bm = 0x8000 >> bit
                    c = sum(((pw[p] & bm) != 0) << p for p in range(planes))
                    px[ox+ch*16+bit, oy+y] = pal[cmap.get(c, c) % len(pal)]
    img.resize((img.width*scale, img.height*scale), Image.NEAREST).save(out_png)
    print(f"saved {out_png}")


def render_strip(raw, out_png, width=48, planes=4, skip=0, colh=420, scale=2, palette=None):
    """Render whole file as a continuous strip of 16px chunks — for exploring
    unknown files. Graphics regions become visible; tables look like noise."""
    from PIL import Image
    pal = palette or EGA
    data = raw[skip:]
    chunks = width // 16
    cb_sz = 2 * planes
    row_b = chunks * cb_sz
    nrows = len(data) // row_b
    img = Image.new('RGB', (width, nrows), (0, 0, 0))
    px = img.load()
    for r in range(nrows):
        for ch in range(chunks):
            cb = r*row_b + ch*cb_sz
            pw = [(data[cb+2*p] << 8) | data[cb+2*p+1] for p in range(planes)]
            for bit in range(16):
                bm = 0x8000 >> bit
                c = sum(((pw[p] & bm) != 0) << p for p in range(planes))
                px[ch*16+bit, r] = pal[c % len(pal)]
    ncols = (nrows + colh - 1) // colh
    sheet = Image.new('RGB', ((width+6)*ncols, colh), (40, 40, 60))
    for c in range(ncols):
        region = img.crop((0, c*colh, width, min((c+1)*colh, nrows)))
        sheet.paste(region, (c*(width+6), 0))
    sheet.resize((sheet.width*scale, sheet.height*scale), Image.NEAREST).save(out_png)
    print(f"saved {out_png}  ({nrows} rows x {width}px, {planes} planes)")



def render_fsprites(raw, out_png, scale=2, palette=None, append=None):
    """F0/F1/F2 dungeon object sprites, decoded per the blitter at EXE 0x7657:
    dims table @0x248 (4B/entry: w_chunks-1, h-1, BE placement word),
    pointer table @0x444 (BE words), graphics base 0x542,
    4-plane 8-byte chunks, transparency = all planes zero.
    Pass append=TILES2_raw to recover sprites past the file end."""
    from PIL import Image, ImageDraw
    pal = palette or EGA
    data = raw + (append or b'')

    N = (0x542 - 0x444) // 2
    sprites, bad = [], []
    for k in range(N):
        w = data[0x248 + 4*k] + 1
        h = data[0x249 + 4*k] + 1
        ptr = (data[0x444 + 2*k] << 8) | data[0x445 + 2*k]
        off = 0x542 + ptr
        if w > 8 or h > 120 or off + w*8*h > len(data):
            bad.append(k)
            continue
        sprites.append((k, w, h, off))

    # tiling diagnostic
    uniq = sorted(set((off, w*8*h) for k, w, h, off in sprites))
    adj = sum(1 for i in range(len(uniq)-1) if uniq[i][0]+uniq[i][1] == uniq[i+1][0])
    print(f"{len(sprites)} valid sprites, {len(bad)} skipped"
          + (f" {bad}" if bad else "")
          + f"; tiling {adj}/{max(len(uniq)-1,1)} adjacent")

    # pre-compute layout, then allocate exact canvas
    SHEET_W, pad_x, pad_y = 1280, 0, 0
    pos = []
    x, y, rowh = 4, 12, 0
    for k, w, h, off in sprites:
        W = w*16
        if x + W > SHEET_W - 4:
            x = 4; y += rowh + pad_y; rowh = 0
        pos.append((x, y, k, w, h, off))
        x += W + pad_x; rowh = max(rowh, h)
    sheet_h = y + rowh + 8

    sheet = Image.new('RGB', (SHEET_W, sheet_h), (45, 45, 60))
    d = ImageDraw.Draw(sheet)
    px = sheet.load()
    for x, y, k, w, h, off in pos:
        #d.text((x, y-10), str(k), fill=(255, 255, 0))
        for yy in range(h):
            for ch in range(w):
                cb = off + yy*w*8 + ch*8
                pw = [(data[cb+2*p] << 8) | data[cb+2*p+1] for p in range(4)]
                for bit in range(16):
                    bm = 0x8000 >> bit
                    c = sum(((pw[p] & bm) != 0) << p for p in range(4))
                    if c:
                        color = pal[c % len(pal)]
                    else:
                        color = (50, 50, 50)
                    px[x+ch*16+bit, y+yy] = color
    sheet.resize((sheet.width*scale, sheet.height*scale), Image.NEAREST).save(out_png)
    print(f"saved {out_png}")


# ---------------- CLI ----------------

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)

    d = sub.add_parser('decode')
    d.add_argument('pac'); d.add_argument('out', nargs='?')

    t = sub.add_parser('tiles')
    t.add_argument('pac'); t.add_argument('out', nargs='?', default='tiles.png')
    t.add_argument('--width', type=int, default=32)
    t.add_argument('--height', type=int, default=16)
    t.add_argument('--planes', type=int, default=3)
    t.add_argument('--skip', type=int, default=64)
    t.add_argument('--stream', type=int, default=0)
    t.add_argument('--cols', type=int, default=10)
    t.add_argument('--scale', type=int, default=3)
    t.add_argument('--pal', default='game1')
    t.add_argument('--remap', type=int, default=None)
    t.add_argument('--mapping-values', default=None,
                   help='16 values (0-15), comma/space separated for live mode')
    t.add_argument('--live', action='store_true',
                   help='open live pygame viewer for dynamic tile mapping edits')
    t.add_argument('--map-file', default='tile_mappings.txt',
                   help='path used by tile live mode for saving mapping dictionaries')


    s = sub.add_parser('strip')
    s.add_argument('pac'); s.add_argument('out')
    s.add_argument('--width', type=int, default=48)
    s.add_argument('--planes', type=int, default=4)
    s.add_argument('--skip', type=int, default=0)
    s.add_argument('--colh', type=int, default=420)
    s.add_argument('--scale', type=int, default=2)
    s.add_argument('--pal', default='ega')

    sp = sub.add_parser('sprites')
    sp.add_argument('pac'); sp.add_argument('out', nargs='?', default='sprites.png')
    sp.add_argument('--width', type=int, default=32)
    sp.add_argument('--height', type=int, default=40)
    sp.add_argument('--stream', type=int, default=0)
    sp.add_argument('--cols', type=int, default=10)
    sp.add_argument('--scale', type=int, default=3)
    sp.add_argument('--remap', type=int, default=None)
    sp.add_argument('--map', default=None, help='empirical mapping name (e.g. M1B)')
    sp.add_argument('--mapping-values', default=None,
                    help='16 values (0-15), comma/space separated, e.g. "0,4,12,10,2,15,1,8,8,9,10,11,12,13,14,15"')
    sp.add_argument('--live', action='store_true',
                    help='open live pygame viewer for dynamic mapping edits')
    sp.add_argument('--map-file', default='sprite_mappings.txt',
                    help='path used by live mode for saving mapping dictionaries')
    sp.add_argument('--pal', default=None)

    f = sub.add_parser('fsprites')
    f.add_argument('pac'); f.add_argument('out')
    f.add_argument('--scale', type=int, default=2)
    f.add_argument('--pal', default='game1')
    f.add_argument('--append', default=None, help='path to TILES2 raw/PAC for overflow sprites')

    a = ap.parse_args()
    raw_in = open(a.pac, 'rb').read()
    print(f"{a.pac}: {len(raw_in)} bytes compressed")
    streams = decompress_all(raw_in, verbose=True)
    raw = streams[getattr(a, 'stream', 0)] if streams else b''
    print(f"decompressed: {len(raw)} bytes ({len(streams)} stream(s))")

    if a.cmd == 'fsprites':
        app = None
        if a.append:
            ad = open(a.append, 'rb').read()
            app = ad if a.append.endswith('.raw') else decompress_all(ad)[0]
        render_fsprites(raw, a.out, a.scale, get_palette(a.pal), app)
        return
    if a.cmd == 'sprites':
        pal = get_palette(a.pal) if a.pal else PALETTES['game1']
        base_mapping = None
        if a.mapping_values:
            base_mapping = parse_mapping_values(a.mapping_values)
        elif a.map and a.map in CHAR_MAPS:
            base_mapping = mapping_to_values(CHAR_MAPS[a.map])

        if a.live:
            render_sprites_with_mapping_live(
                raw,
                base_mapping,
                a.width,
                a.height,
                a.cols,
                a.scale,
                palette=pal,
                out_png=a.out,
                pac_path=a.pac,
                stream=a.stream,
                map_file=a.map_file,
            )
            return

        if a.map and a.map in CHAR_MAPS:
            render_sprites_with_mapping(raw, a.out, CHAR_MAPS[a.map], a.width, a.height, a.cols, a.scale, palette=pal)
        else:
            render_sprites(raw, a.out, a.width, a.height, a.cols, a.scale, palette=pal, remap=a.remap)
        return
    if a.cmd == 'strip':
        render_strip(raw, a.out, a.width, a.planes, a.skip, a.colh, a.scale, palette=get_palette(a.pal))
        return
    if a.cmd == 'decode':
        out = a.out or os.path.splitext(a.pac)[0] + '.raw'
        open(out, 'wb').write(raw)
        print(f"saved {out}")
    else:
        pal = get_palette(a.pal)
        if a.cmd == 'tiles' and a.live:
            base_mapping = parse_mapping_values(a.mapping_values) if a.mapping_values else None
            render_tiles_with_mapping_live(
                raw,
                base_mapping,
                a.width,
                a.height,
                a.planes,
                a.skip,
                a.cols,
                a.scale,
                palette=pal,
                out_png=a.out,
                pac_path=a.pac,
                stream=a.stream,
                map_file=a.map_file,
            )
            return
        render_tiles(raw, a.out, a.width, a.height, a.planes, a.skip, a.cols, a.scale, palette=pal, remap=a.remap)


if __name__ == '__main__':
    main()
