# trazere_extract.py — Usage Reference

## Commands

### decode — decompress any PAC to raw bytes
    python3 trazere_extract.py decode PACS/TITLE.PAC title.raw

### tiles — fixed-size 3-plane tile sheets (floors)
    python3 trazere_extract.py tiles PACS/TILES2.PAC tiles2.png --pal game1
Defaults: --width 32 --height 16 --planes 3 --skip 64 (exactly TILES2's format:
64-byte shared ellipse mask, then 118 floor tiles). Options: --cols, --scale.

Live tile mapping editor:
    python3 trazere_extract.py tiles PACS/TILES2.PAC tiles_live.png --live --stream 0 --pal game1
Optional live flags:
    --mapping-values "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15"
    --map-file tile_mappings.txt

### sprites — SPIT character/NPC frame sheets (3-plane chunks)
    python3 trazere_extract.py sprites SPIT/M09.PAC m09.png --remap 12 --pal game1
    python3 trazere_extract.py sprites SPIT/M1B.PAC m1b.png --height 32 --remap 12 --pal game1
Defaults: --width 32 --height 40. If output reports a remainder, try --height 32
or --width 16. --remap N applies live remap entry N (0=identity, 0-127).
Without --remap you get logical-slot placeholder colors.

Live sprite mapping editor:
    python3 trazere_extract.py sprites SPIT/M1B.PAC m1b_live.png --live --map M1B --pal game1
Optional live flags:
    --mapping-values "0,4,12,10,2,15,1,8,8,9,10,11,12,13,14,15"
    --map-file sprite_mappings.txt

### fsprites — F0/F1/F2 dungeon object sprites (4-plane, directory-driven)
    python3 trazere_extract.py fsprites PACS/F0.PAC f0.png --append PACS/TILES2.PAC
--append supplies the data the loader appends in memory (sprites whose pointers
run past the file end). Prints a tiling diagnostic; "N/N adjacent" = healthy.
Default palette: game1.

### strip — exploration renderer for unknown formats
    python3 trazere_extract.py strip PACS/SPELBITS.PAC sb.png --width 32 --planes 3 --pal game1
Renders the whole file as a continuous strip of 16px chunks. For figuring out
files we haven't mapped yet (SPELBITS, TILESX, A-files, WORLD, UINV...).

## Palettes (--pal)
    game1   in-game dungeon/UI palette  (EXE 0x2CD6E, screenshot-verified)
    game2   title screen palette        (EXE 0x2D1DA, user-verified)
    game3   bright/menu variant         (EXE 0x2D3DA)
    ega     standard EGA placeholder

## Live Mode Controls (sprites and tiles)
    Left/Right  select source index (0..F)
    Up/Down     increment/decrement mapped value
    0-9, A-F    set mapped value directly
    R           reset mapping to identity
    Z           set all mapping values to 0
    S           save current rendered PNG
    M           save mapping dictionary entry to --map-file
    L           load another PAC path without quitting
    [ / ]       previous/next compressed stream in current PAC
    Q or Esc    quit live mode

Notes:
- Mapping value for source index 0 is forced to 0 to preserve transparency.
- Live mode uses pygame. Install if needed: pip install pygame

## Mapping Save File Format
Pressing M updates the mapping file by key (PAC filename without extension).
The file is rewritten with all known keys preserved when parsing succeeds.

Example:
    {
        "M1B": {0:0, 1:4, 2:12, 3:10, 4:2, 5:15, 6:1, 7:8, 8:8, 9:9, 10:10, 11:11, 12:12, 13:13, 14:14, 15:15}
    }

## File format summary
    TITLE/MCGA/PARTYUSA/4XUSA  32000 B = 320x200, 4 planes, plane-sequential
    TILES2   64 B ellipse mask + 118 floor tiles, 32x16, 3-plane 6-byte chunks
    F0/F1/F2 mapping table @0, dims @0x248, pointers @0x444, gfx @0x542,
             4-plane 8-byte chunks, transparency = all planes zero
    SPIT/*   uniform frames (32x40 or 32x32), 3-plane chunks, combo 0 transparent
    ROOMS/*  2048 B room grid data (not graphics)
    *.BIN    MIDI music (MThd/MTrk)

## Remap/outfit system (for the fan game)
Character sprites store logical slots. Live remap table (128 entries, embedded
in the script as REMAPS) maps slots -> palette colors via NIB2COLOR. Entry 0 is
identity. Re-clothe internals still partially unsolved; mechanism documented in
the script comments.
