"""
The Abyss
=========
A procedurally generated dungeon crawler.

Every floor is unique — rooms placed at random, corridors carved between
them.  Descend as deep as you dare, fighting goblins, skeletons and demons
with torchlight as your only guide.

Controls
--------
    W / A / S / D  or  Arrow keys  — move
    SPACE                          — attack
    ESC                            — quit
"""

import pygame
import sys
import random
import math
from collections import deque

pygame.init()

# ── Window ─────────────────────────────────────────────────────────────────────
SW, SH  = 960, 640
GAME_H  = SH - 72
FPS     = 60
screen  = pygame.display.set_mode((SW, SH))
pygame.display.set_caption("The Abyss")
clock   = pygame.time.Clock()

# ── Map ────────────────────────────────────────────────────────────────────────
TILE     = 32
MAP_W    = 54
MAP_H    = 42
WALL     = 0
FLOOR    = 1
STAIRS   = 2
PLAYER_R = 0.30   # collision radius in tile-units

# ── Palette ────────────────────────────────────────────────────────────────────
C_BG         = (6,   4,   2)
C_WALL       = (44,  36,  26)
C_WALL_TOP   = (66,  55,  40)
C_FLOOR_A    = (68,  58,  44)
C_FLOOR_B    = (58,  48,  36)
C_STAIRS_C   = (112, 92,  62)
C_ARMOR      = (168, 180, 198)
C_SKIN       = (215, 180, 145)
C_SWORD      = (198, 212, 232)
C_SHIELD     = (142, 105, 48)
C_CAPE       = (145, 32,  32)
C_HP_RED     = (212, 50,  50)
C_HP_DARK    = (72,  26,  26)
C_GOLD       = (250, 196, 36)
C_WHITE      = (255, 255, 255)
C_BLACK      = (0,   0,   0)
C_HIT        = (255, 110, 70)
C_MM_WALL    = (30,  24,  16)
C_MM_FLOOR   = (90,  78,  58)
C_MM_STAIR   = (142, 118, 78)
C_MM_PLAYER  = (220, 210, 175)
C_MM_ENEMY   = (185, 50,  40)
C_MM_ITEM    = (80,  170, 80)

ENEMY_BODY = {
    'goblin':   ((65,  140, 60),  (100, 175, 90)),
    'skeleton': ((192, 185, 165), (212, 205, 185)),
    'demon':    ((52,  36,  92),  (82,  58,  135)),
}
ENEMY_STATS = {
    'goblin':   {'hp': 2, 'spd': 3.8, 'dmg': 1, 'sight': 8,  'ar': 0.85},
    'skeleton': {'hp': 3, 'spd': 2.6, 'dmg': 1, 'sight': 11, 'ar': 0.9},
    'demon':    {'hp': 7, 'spd': 2.0, 'dmg': 2, 'sight': 6,  'ar': 1.05},
}

# ── Pre-render lighting mask ───────────────────────────────────────────────────
_LR = 172   # light radius in pixels

def _make_light(radius):
    """
    Pre-render a radial-gradient torch-light mask.

    When blitted with pygame.BLEND_RGB_MULT the area inside the radius
    appears lit and everything outside fades to black.

    Parameters:
        radius (int): Light radius in pixels.

    Returns:
        pygame.Surface: RGB surface, bright at centre and black at edges.
    """
    s = pygame.Surface((radius * 2, radius * 2))
    s.fill(C_BLACK)
    for r in range(radius, 0, -2):
        v = int(255 * (1.0 - r / radius) ** 0.46)
        pygame.draw.circle(s, (v, v, v), (radius, radius), r)
    return s

LIGHT_MASK = _make_light(_LR)


# ── Dungeon generation ─────────────────────────────────────────────────────────

def generate_dungeon(floor_num):
    """
    Procedurally generate a dungeon floor using random room placement
    and L-shaped corridor connections.

    Rooms are placed without overlap then chained with corridors so
    every room is reachable.  Enemy density and type variety scale with
    the floor number.

    Parameters:
        floor_num (int): Current floor (1-indexed).

    Returns:
        dict: Keys — 'tiles', 'rooms', 'player_pos', 'stairs_pos',
              'enemies', 'items'.
    """
    tiles = [[WALL] * MAP_W for _ in range(MAP_H)]
    rooms = []

    target = random.randint(9, 16)
    for _ in range(400):
        if len(rooms) >= target:
            break
        rw = random.randint(4, 12)
        rh = random.randint(4, 8)
        rx = random.randint(1, MAP_W - rw - 1)
        ry = random.randint(1, MAP_H - rh - 1)
        if any(rx < r['x']+r['w']+1 and rx+rw > r['x']-1 and
               ry < r['y']+r['h']+1 and ry+rh > r['y']-1 for r in rooms):
            continue
        rooms.append({'x': rx, 'y': ry, 'w': rw, 'h': rh})
        for ty in range(ry, ry + rh):
            for tx in range(rx, rx + rw):
                tiles[ty][tx] = FLOOR

    # Fallback if generation stalls
    if len(rooms) < 5:
        rooms = [
            {'x': 3,  'y': 3,  'w': 9, 'h': 6},
            {'x': 18, 'y': 4,  'w': 9, 'h': 7},
            {'x': 34, 'y': 3,  'w': 9, 'h': 6},
            {'x': 42, 'y': 14, 'w': 9, 'h': 7},
            {'x': 26, 'y': 18, 'w': 9, 'h': 6},
            {'x': 8,  'y': 20, 'w': 9, 'h': 7},
            {'x': 3,  'y': 32, 'w': 9, 'h': 6},
            {'x': 24, 'y': 31, 'w': 9, 'h': 7},
        ]
        for r in rooms:
            for ty in range(r['y'], r['y'] + r['h']):
                for tx in range(r['x'], r['x'] + r['w']):
                    tiles[ty][tx] = FLOOR

    rooms.sort(key=lambda r: r['x'] * 0.6 + r['y'] * 0.4)

    def _carve(ax, ay, bx, by):
        """
        Carve a 2-tile-wide L-shaped corridor from (ax, ay) to (bx, by).

        First moves horizontally then vertically so every pair of
        adjacent rooms is connected by a walkable path.

        Parameters:
            ax, ay (int): Start tile coordinates.
            bx, by (int): End tile coordinates.

        Returns:
            None
        """
        x, y = ax, ay
        while x != bx:
            if 0 <= y < MAP_H and 0 <= x < MAP_W:
                tiles[y][x] = FLOOR
                if y + 1 < MAP_H:
                    tiles[y + 1][x] = FLOOR
            x += 1 if x < bx else -1
        while y != by:
            if 0 <= y < MAP_H and 0 <= x < MAP_W:
                tiles[y][x] = FLOOR
                if x + 1 < MAP_W:
                    tiles[y][x + 1] = FLOOR
            y += 1 if y < by else -1

    for i in range(len(rooms) - 1):
        r1, r2 = rooms[i], rooms[i + 1]
        _carve(r1['x'] + r1['w']//2, r1['y'] + r1['h']//2,
               r2['x'] + r2['w']//2, r2['y'] + r2['h']//2)

    r0, rl  = rooms[0], rooms[-1]
    player_pos = (r0['x'] + r0['w']//2, r0['y'] + r0['h']//2)
    stairs_pos = (rl['x'] + rl['w']//2, rl['y'] + rl['h']//2)
    tiles[stairs_pos[1]][stairs_pos[0]] = STAIRS

    # Enemy population
    pop_table = [
        [('goblin', .90), ('skeleton', .10), ('demon', .00)],
        [('goblin', .50), ('skeleton', .40), ('demon', .10)],
        [('goblin', .20), ('skeleton', .40), ('demon', .40)],
    ]
    pop  = pop_table[min(floor_num - 1, 2)]
    etypes, ewts = zip(*pop)

    enemies = []
    for room in rooms[1:]:
        n = min(random.randint(1 + floor_num // 2, 2 + floor_num), 6)
        for _ in range(n):
            et = random.choices(etypes, weights=ewts)[0]
            st = ENEMY_STATS[et]
            ex = random.randint(room['x'] + 1, room['x'] + room['w'] - 2)
            ey = random.randint(room['y'] + 1, room['y'] + room['h'] - 2)
            enemies.append({
                'x': float(ex) + 0.5, 'y': float(ey) + 0.5,
                'type':   et,
                'hp':     st['hp'] + floor_num - 1,
                'max_hp': st['hp'] + floor_num - 1,
                'spd':    st['spd'],
                'dmg':    st['dmg'],
                'sight':  st['sight'],
                'ar':     st['ar'],
                'state':  'idle',
                'path':   [],
                'path_t': 0.0,
                'atk_t':  0.0,
                'hit_t':  0,
                'facing': [1, 0],
                'alive':  True,
            })

    # Item placement
    items = []
    for room in rooms[2:]:
        if random.random() < 0.55:
            ix = random.randint(room['x'] + 1, room['x'] + room['w'] - 2)
            iy = random.randint(room['y'] + 1, room['y'] + room['h'] - 2)
            itype = random.choices(['potion', 'gold', 'gold', 'gold'], k=1)[0]
            items.append({'x': ix, 'y': iy, 'type': itype, 'collected': False})

    return {
        'tiles': tiles, 'rooms': rooms,
        'player_pos': player_pos, 'stairs_pos': stairs_pos,
        'enemies': enemies, 'items': items,
    }


def bfs_path(tiles, start, goal, max_dist=28):
    """
    Find the shortest path from start to goal using breadth-first search.

    Only traverses non-WALL tiles.  Returns an empty list if no path
    is found within max_dist steps.

    Parameters:
        tiles    (list[list[int]]): Tile grid.
        start    (tuple[int,int]):  Start tile coords.
        goal     (tuple[int,int]):  Goal tile coords.
        max_dist (int):             Max search depth.

    Returns:
        list[tuple[int,int]]: Path from start (exclusive) to goal
        (inclusive), or [] if unreachable.
    """
    sx, sy = int(start[0]), int(start[1])
    gx, gy = int(goal[0]),  int(goal[1])
    if sx == gx and sy == gy:
        return []
    q       = deque([(sx, sy, [])])
    visited = {(sx, sy)}
    while q:
        x, y, path = q.popleft()
        if len(path) >= max_dist:
            continue
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in visited:
                continue
            if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
                continue
            if tiles[ny][nx] == WALL:
                continue
            np = path + [(nx, ny)]
            if nx == gx and ny == gy:
                return np
            visited.add((nx, ny))
            q.append((nx, ny, np))
    return []


def has_los(tiles, ax, ay, bx, by):
    """
    Check whether there is an unobstructed line of sight between two
    tile positions using ray-marching along the connecting line.

    Parameters:
        tiles (list[list[int]]): Tile grid.
        ax, ay (float):          Source position in tile units.
        bx, by (float):          Target position in tile units.

    Returns:
        bool: True if no WALL tile intersects the line, False otherwise.
    """
    steps = max(2, int(math.hypot(bx - ax, by - ay) * 3))
    for i in range(steps + 1):
        t  = i / steps
        tx = int(ax + (bx - ax) * t)
        ty = int(ay + (by - ay) * t)
        if 0 <= tx < MAP_W and 0 <= ty < MAP_H:
            if tiles[ty][tx] == WALL:
                return False
    return True


# ── Drawing: tiles ─────────────────────────────────────────────────────────────

def draw_tile(surf, tile, sx, sy, floor_num):
    """
    Render a single map tile at the given screen-pixel position.

    Wall tiles show a top-lit highlight edge.  Floor tiles use a
    two-tone checkerboard.  Stairs show carved step lines and a
    downward arrow.

    Parameters:
        surf      (pygame.Surface): Target surface.
        tile      (int):            Tile type ID (WALL / FLOOR / STAIRS).
        sx        (int):            Screen x (top-left pixel).
        sy        (int):            Screen y (top-left pixel).
        floor_num (int):            Current floor for colour darkening.

    Returns:
        None
    """
    d = min((floor_num - 1) * 6, 24)
    r = pygame.Rect(sx, sy, TILE, TILE)

    if tile == WALL:
        c = tuple(max(0, C_WALL[i] - d)     for i in range(3))
        t = tuple(max(0, C_WALL_TOP[i] - d) for i in range(3))
        pygame.draw.rect(surf, c, r)
        pygame.draw.line(surf, t, (sx, sy),        (sx + TILE - 1, sy), 2)
        pygame.draw.line(surf, t, (sx, sy),        (sx, sy + TILE - 1), 1)

    elif tile == FLOOR:
        base = C_FLOOR_B if (sx // TILE + sy // TILE) % 2 == 0 else C_FLOOR_A
        c    = tuple(max(0, base[i] - d) for i in range(3))
        g    = tuple(max(0, c[i] - 10)   for i in range(3))
        pygame.draw.rect(surf, c, r)
        pygame.draw.line(surf, g, (sx, sy), (sx + TILE, sy), 1)
        pygame.draw.line(surf, g, (sx, sy), (sx, sy + TILE), 1)

    elif tile == STAIRS:
        pygame.draw.rect(surf, C_STAIRS_C, r)
        for i in range(1, 5):
            lx = sx + i * (TILE // 5)
            pygame.draw.line(surf, (82, 66, 44), (lx, sy + 2), (lx, sy + TILE - 2), 2)
        mx, my = sx + TILE // 2, sy + TILE // 2
        pygame.draw.polygon(surf, (70, 56, 36),
                            [(mx - 7, my - 5), (mx + 7, my - 5), (mx, my + 7)])


# ── Drawing: player ────────────────────────────────────────────────────────────

def draw_player(surf, cx, cy, facing, atk_t):
    """
    Draw the armoured player knight centred at (cx, cy).

    The sword lunges in the facing direction during an attack and rests
    at the player's side otherwise.

    Parameters:
        surf    (pygame.Surface): Target surface.
        cx      (int):            Screen centre x.
        cy      (int):            Screen centre y.
        facing  (list[float]):    Normalised facing direction [dx, dy].
        atk_t   (float):          Remaining attack animation seconds.

    Returns:
        None
    """
    r    = TILE // 2 - 3
    fd   = (facing[0], facing[1])
    perp = (-fd[1], fd[0])

    # Cape
    pygame.draw.circle(surf, C_CAPE,
                       (int(cx - fd[0] * 5), int(cy - fd[1] * 5)), r + 2)
    # Body armour
    pygame.draw.circle(surf, C_ARMOR, (cx, cy), r)
    pygame.draw.circle(surf, (185, 196, 215), (cx, cy), r - 2)
    # Head
    hx, hy = int(cx + fd[0] * 6), int(cy + fd[1] * 6)
    pygame.draw.circle(surf, C_SKIN,  (hx, hy), 5)
    pygame.draw.circle(surf, C_ARMOR, (hx, hy), 5, 2)

    # Sword
    if atk_t > 0:
        bp = (int(cx + fd[0] * (r - 2)), int(cy + fd[1] * (r - 2)))
        tp = (int(cx + fd[0] * (r + 14)), int(cy + fd[1] * (r + 14)))
        pts = [
            (bp[0] + int(perp[0]*3),  bp[1] + int(perp[1]*3)),
            (tp[0] + int(perp[0]*2),  tp[1] + int(perp[1]*2)),
            (tp[0] - int(perp[0]*2),  tp[1] - int(perp[1]*2)),
            (bp[0] - int(perp[0]*3),  bp[1] - int(perp[1]*3)),
        ]
        pygame.draw.polygon(surf, C_SWORD, pts)
    else:
        s0 = (int(cx + perp[0] * (r - 1)), int(cy + perp[1] * (r - 1)))
        s1 = (int(s0[0] + perp[0]*7 + fd[0]*3),
              int(s0[1] + perp[1]*7 + fd[1]*3))
        pygame.draw.line(surf, C_SWORD, s0, s1, 3)

    # Shield
    shx = int(cx - perp[0] * (r - 1))
    shy = int(cy - perp[1] * (r - 1))
    pygame.draw.circle(surf, C_SHIELD,       (shx, shy), 5)
    pygame.draw.circle(surf, (182, 140, 65), (shx, shy), 5, 2)


# ── Drawing: enemies ───────────────────────────────────────────────────────────

def draw_enemy(surf, cx, cy, enemy):
    """
    Draw an enemy sprite with a type-specific appearance and HP bar.

    The sprite flashes orange-red for a few frames after taking a hit.

    Parameters:
        surf  (pygame.Surface): Target surface.
        cx    (int):            Screen centre x.
        cy    (int):            Screen centre y.
        enemy (dict):           Enemy state dictionary.

    Returns:
        None
    """
    bc, hc = ENEMY_BODY[enemy['type']]
    bc     = C_HIT if enemy['hit_t'] > 0 else bc
    r      = TILE // 2 - 5

    if enemy['type'] == 'goblin':
        pygame.draw.circle(surf, bc, (cx, cy), r)
        pygame.draw.circle(surf, hc, (cx, cy - r + 2), 4)
        # Pointy ears
        pygame.draw.polygon(surf, bc,
                            [(cx - r, cy - 2), (cx - r - 6, cy - 8), (cx - r + 2, cy - 6)])
        pygame.draw.polygon(surf, bc,
                            [(cx + r, cy - 2), (cx + r + 6, cy - 8), (cx + r - 2, cy - 6)])
        # Eyes
        pygame.draw.circle(surf, (255, 220, 0), (cx - 3, cy - r + 3), 2)
        pygame.draw.circle(surf, (255, 220, 0), (cx + 3, cy - r + 3), 2)

    elif enemy['type'] == 'skeleton':
        pygame.draw.circle(surf, bc, (cx, cy), r)
        pygame.draw.circle(surf, hc, (cx, cy - r + 2), 5)
        # Cross-bone detail
        pygame.draw.line(surf, (140, 135, 120), (cx - r + 2, cy), (cx + r - 2, cy), 2)
        pygame.draw.line(surf, (140, 135, 120), (cx, cy - r + 2), (cx, cy + r - 2), 2)
        # Eye sockets
        pygame.draw.circle(surf, C_BLACK, (cx - 2, cy - r + 3), 2)
        pygame.draw.circle(surf, C_BLACK, (cx + 2, cy - r + 3), 2)

    else:  # demon
        pygame.draw.circle(surf, bc, (cx, cy), r + 2)
        pygame.draw.circle(surf, (30, 20, 60), (cx, cy), r + 2, 2)
        pygame.draw.circle(surf, hc, (cx, cy - r), 5)
        # Horns
        pygame.draw.polygon(surf, bc,
                            [(cx - 5, cy - r - 1), (cx - 2, cy - r - 1),
                             (cx - 6, cy - r - 9)])
        pygame.draw.polygon(surf, bc,
                            [(cx + 5, cy - r - 1), (cx + 2, cy - r - 1),
                             (cx + 6, cy - r - 9)])
        # Glowing eyes
        pygame.draw.circle(surf, (255, 80, 0), (cx - 3, cy - r + 1), 2)
        pygame.draw.circle(surf, (255, 80, 0), (cx + 3, cy - r + 1), 2)

    # HP bar
    bw = 24
    bx = cx - bw // 2
    by = cy - r - 9
    filled = int(bw * enemy['hp'] / max(enemy['max_hp'], 1))
    pygame.draw.rect(surf, C_HP_DARK, (bx, by, bw, 4))
    if filled > 0:
        pygame.draw.rect(surf, C_HP_RED, (bx, by, filled, 4))


# ── Drawing: items ─────────────────────────────────────────────────────────────

def draw_item(surf, sx, sy, itype, frame):
    """
    Draw a collectible item — health potion or gold coin.

    Items bob up and down gently using a sine-wave offset.

    Parameters:
        surf  (pygame.Surface): Target surface.
        sx    (int):            Screen x (tile top-left pixel).
        sy    (int):            Screen y (tile top-left pixel).
        itype (str):            'potion' or 'gold'.
        frame (int):            Global frame counter for bob animation.

    Returns:
        None
    """
    bob = int(2 * math.sin(frame * 0.10))
    cx  = sx + TILE // 2
    cy  = sy + TILE // 2 + bob

    if itype == 'potion':
        pygame.draw.rect(surf, (50, 162, 72),  (cx - 5, cy - 7, 10, 13), border_radius=4)
        pygame.draw.rect(surf, (70, 198, 90),  (cx - 3, cy - 5,  6,  8), border_radius=2)
        pygame.draw.rect(surf, (50, 162, 72),  (cx - 3, cy - 11, 6,  5))
        pygame.draw.rect(surf, (148, 112, 60), (cx - 3, cy - 13, 6,  3))
    else:
        pygame.draw.circle(surf, C_GOLD,         (cx, cy), 7)
        pygame.draw.circle(surf, (190, 150, 25), (cx, cy), 7, 2)
        pygame.draw.circle(surf, (255, 215, 75), (cx - 2, cy - 2), 3)


# ── Drawing: minimap ───────────────────────────────────────────────────────────

def draw_minimap(surf, tiles, enemies, items, player_pos):
    """
    Draw a compact overview minimap of the current floor in the top-right.

    Shows all tiles as small coloured blocks with player, enemy and item
    positions marked.

    Parameters:
        surf       (pygame.Surface):   Main screen surface.
        tiles      (list[list[int]]): 2D tile grid.
        enemies    (list[dict]):       Enemy state list.
        items      (list[dict]):       Item state list.
        player_pos (tuple[float]):     Player (x, y) in tile units.

    Returns:
        None
    """
    MT     = 3
    MW, MH = MAP_W * MT, MAP_H * MT
    MARGIN = 8

    mm = pygame.Surface((MW, MH))
    mm.fill(C_BG)

    for ty in range(MAP_H):
        for tx in range(MAP_W):
            t = tiles[ty][tx]
            c = C_MM_WALL if t == WALL else (C_MM_STAIR if t == STAIRS else C_MM_FLOOR)
            pygame.draw.rect(mm, c, (tx * MT, ty * MT, MT - 1, MT - 1))

    for it in items:
        if not it['collected']:
            pygame.draw.rect(mm, C_MM_ITEM,
                             (it['x'] * MT, it['y'] * MT, MT, MT))
    for e in enemies:
        if e['alive']:
            pygame.draw.rect(mm, C_MM_ENEMY,
                             (int(e['x']) * MT, int(e['y']) * MT, MT, MT))

    px, py = int(player_pos[0]) * MT, int(player_pos[1]) * MT
    pygame.draw.rect(mm, C_MM_PLAYER, (px, py, MT + 1, MT + 1))
    pygame.draw.rect(mm, (80, 68, 50), (0, 0, MW, MH), 1)

    surf.blit(mm, (SW - MW - MARGIN, MARGIN))


# ── Drawing: HUD ───────────────────────────────────────────────────────────────

def draw_hud(surf, player, gold, floor_num, font_big):
    """
    Draw the heads-up display showing HP hearts, gold total, and floor number.

    Parameters:
        surf      (pygame.Surface):   Main screen surface.
        player    (dict):             Player state dictionary.
        gold      (int):              Gold collected so far.
        floor_num (int):              Current floor number.
        font_big  (pygame.font.Font): Font for labels.

    Returns:
        None
    """
    hy = GAME_H
    pygame.draw.rect(surf, (14, 10, 7), (0, hy, SW, SH - hy))
    pygame.draw.line(surf, (60, 50, 36), (0, hy), (SW, hy), 2)

    # HP hearts
    for i in range(player['max_hp']):
        filled = i < player['hp']
        col = C_HP_RED if filled else C_HP_DARK
        cx, cy = 20 + i * 30, hy + 30
        pygame.draw.circle(surf, col, (cx - 4, cy - 3), 6)
        pygame.draw.circle(surf, col, (cx + 4, cy - 3), 6)
        pygame.draw.polygon(surf, col, [(cx - 9, cy), (cx + 9, cy), (cx, cy + 10)])

    # Gold
    gx = SW // 2 - 50
    gy = hy + 22
    pygame.draw.circle(surf, C_GOLD,         (gx, gy + 10), 8)
    pygame.draw.circle(surf, (188, 148, 22), (gx, gy + 10), 8, 2)
    gs = font_big.render(str(gold), True, C_GOLD)
    surf.blit(gs, (gx + 14, gy + 2))

    # Floor
    fl = font_big.render(f"Floor  {floor_num}", True, (168, 155, 135))
    surf.blit(fl, (SW - fl.get_width() - 22, hy + 20))


# ── Overlay screens ────────────────────────────────────────────────────────────

def draw_start_screen(surf, font_title, font_big, best_floor):
    """
    Draw the title screen with controls and best-floor display.

    Parameters:
        surf       (pygame.Surface):    Screen surface.
        font_title (pygame.font.Font):  Large title font.
        font_big   (pygame.font.Font):  Body font.
        best_floor (int):               Deepest floor ever reached.

    Returns:
        None
    """
    surf.fill(C_BG)
    cx = SW // 2

    t1 = font_title.render("THE", True, (165, 150, 120))
    t2 = font_title.render("ABYSS", True, (145, 30, 30))
    surf.blit(t1, (cx - t1.get_width() // 2, 130))
    surf.blit(t2, (cx - t2.get_width() // 2, 200))

    lines = [
        ("A procedurally generated dungeon crawler.", (128, 118, 100)),
        ("",                                          (0, 0, 0)),
        ("WASD / Arrows — move     SPACE — attack",  (105, 96, 80)),
        ("",                                          (0, 0, 0)),
        ("Press  ENTER  to descend",                  (182, 168, 132)),
    ]
    for i, (txt, col) in enumerate(lines):
        if txt:
            s = font_big.render(txt, True, col)
            surf.blit(s, (cx - s.get_width() // 2, 320 + i * 36))

    if best_floor > 0:
        bf = font_big.render(f"Deepest floor: {best_floor}", True, C_GOLD)
        surf.blit(bf, (cx - bf.get_width() // 2, 500))


def draw_death_screen(surf, font_title, font_big, floor_num, gold):
    """
    Draw the death overlay on top of the last rendered game frame.

    Parameters:
        surf      (pygame.Surface):    Screen surface.
        font_title(pygame.font.Font):  Large font.
        font_big  (pygame.font.Font):  Body font.
        floor_num (int):               Floor the player died on.
        gold      (int):               Gold collected.

    Returns:
        None
    """
    ov = pygame.Surface((SW, SH), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 205))
    surf.blit(ov, (0, 0))

    cx = SW // 2
    t  = font_title.render("YOU DIED", True, (195, 38, 38))
    surf.blit(t, (cx - t.get_width() // 2, 175))

    for i, (txt, col) in enumerate([
        (f"Reached floor {floor_num}", (175, 160, 135)),
        (f"Gold collected: {gold}",     C_GOLD),
        ("",                            C_BLACK),
        ("ENTER — try again",           (145, 132, 110)),
    ]):
        s = font_big.render(txt, True, col)
        surf.blit(s, (cx - s.get_width() // 2, 295 + i * 40))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    """
    Initialise Pygame and run The Abyss game loop.

    Three game states:
        'start'   — title screen, waiting for ENTER.
        'playing' — live dungeon gameplay.
        'dead'    — death overlay, waiting for ENTER to restart.

    Core data structures:
        dungeon   (dict)         — floor data: tiles, rooms, enemies, items.
        player    (dict)         — player state: position, HP, facing, timers.
        enemies   (list[dict])   — all enemy states on the current floor.
        items     (list[dict])   — all collectible states on the current floor.
        particles (list[dict])   — active visual particles.

    Returns:
        None
    """
    try:
        font_title = pygame.font.SysFont('Georgia', 68, bold=True)
        font_big   = pygame.font.SysFont('Arial',   26)
    except Exception:
        font_title = pygame.font.Font(None, 74)
        font_big   = pygame.font.Font(None, 30)

    state      = 'start'
    paused     = False
    best_floor = 0
    frame      = 0

    def _new_player(pos):
        """
        Create a fresh player state dictionary at the given tile position.

        Parameters:
            pos (tuple[int, int]): Tile coordinates for the player spawn.

        Returns:
            dict: Player state with keys x, y, hp, max_hp, facing,
                  atk_t, atk_cd, inv_t, alive.
        """
        return {
            'x': float(pos[0]) + 0.5, 'y': float(pos[1]) + 0.5,
            'hp': 5, 'max_hp': 5,
            'facing': [1, 0],
            'atk_t':  0.0,
            'atk_cd': 0.0,
            'inv_t':  0.0,
            'alive':  True,
        }

    def _load_floor(floor_num, gold=0):
        """
        Generate a new dungeon floor and place the player at the start room.

        Parameters:
            floor_num (int): Floor number to generate (affects enemy difficulty).
            gold      (int): Carry-over gold from the previous floor.

        Returns:
            tuple: (dungeon dict, player dict, gold int)
        """
        d      = generate_dungeon(floor_num)
        player = _new_player(d['player_pos'])
        return d, player, gold

    floor_num = 1
    gold      = 0
    dungeon, player, gold = _load_floor(floor_num, gold)
    particles = []

    game_surf = pygame.Surface((SW, GAME_H))

    ATK_CD    = 0.42
    ATK_REACH = 1.5
    ATK_DUR   = 0.16
    SPEED     = 5.2
    ENEMY_ACD = 0.80
    PATH_INT  = 0.48

    while True:
        dt    = min(clock.tick(FPS) / 1000.0, 0.05)
        frame += 1

        # ── Events ─────────────────────────────────────────────────────────
        attack_key = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key == pygame.K_p and state == 'playing':
                    paused = not paused
                if event.key == pygame.K_RETURN:
                    if state == 'start':
                        state = 'playing'
                    elif state == 'dead':
                        floor_num = 1
                        gold      = 0
                        dungeon, player, gold = _load_floor(floor_num, gold)
                        particles = []
                        state     = 'playing'
                if event.key == pygame.K_SPACE:
                    attack_key = True

        # ── Title screen ────────────────────────────────────────────────────
        if state == 'start':
            draw_start_screen(screen, font_title, font_big, best_floor)
            pygame.display.flip()
            continue

        # ── Death screen ────────────────────────────────────────────────────
        if state == 'dead':
            screen.blit(game_surf, (0, 0))
            draw_death_screen(screen, font_title, font_big, floor_num, gold)
            pygame.display.flip()
            continue

        # ── Playing ─────────────────────────────────────────────────────────
        tiles   = dungeon['tiles']
        enemies = dungeon['enemies']
        items   = dungeon['items']

        # ── Paused ──────────────────────────────────────────────────────────
        if paused:
            screen.blit(game_surf, (0, 0))
            draw_hud(screen, player, gold, floor_num, font_big)
            draw_minimap(screen, tiles, enemies, items, (player['x'], player['y']))
            ov = pygame.Surface((SW, SH), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 140))
            screen.blit(ov, (0, 0))
            pt = font_title.render("PAUSED", True, (255, 255, 255))
            screen.blit(pt, pt.get_rect(center=(SW // 2, SH // 2 - 20)))
            ph = font_big.render("Press P to resume", True, (200, 200, 200))
            screen.blit(ph, ph.get_rect(center=(SW // 2, SH // 2 + 20)))
            pygame.display.flip()
            clock.tick(30)
            continue

        # Player movement
        keys = pygame.key.get_pressed()
        pdx  = ((keys[pygame.K_RIGHT] or keys[pygame.K_d]) -
                 (keys[pygame.K_LEFT]  or keys[pygame.K_a])) * 1.0
        pdy  = ((keys[pygame.K_DOWN]  or keys[pygame.K_s]) -
                 (keys[pygame.K_UP]   or keys[pygame.K_w])) * 1.0

        if pdx and pdy:
            pdx *= 0.707; pdy *= 0.707

        if abs(pdx) > abs(pdy) and pdx:
            player['facing'] = [1 if pdx > 0 else -1, 0]
        elif pdy:
            player['facing'] = [0, 1 if pdy > 0 else -1]

        def walkable(nx, ny):
            """
            Check whether the player can occupy position (nx, ny).

            Tests all four corners of the player's bounding box against
            the tile grid; returns False if any corner lands on a WALL.

            Parameters:
                nx (float): Candidate x position in tile units.
                ny (float): Candidate y position in tile units.

            Returns:
                bool: True if position is fully clear of walls.
            """
            for ox, oy in ((-PLAYER_R,-PLAYER_R),(-PLAYER_R,PLAYER_R),
                           ( PLAYER_R,-PLAYER_R),( PLAYER_R, PLAYER_R)):
                tx, ty = int(nx + ox), int(ny + oy)
                if not (0 <= tx < MAP_W and 0 <= ty < MAP_H):
                    return False
                if tiles[ty][tx] == WALL:
                    return False
            return True

        nx = player['x'] + pdx * SPEED * dt
        ny = player['y'] + pdy * SPEED * dt
        if walkable(nx, player['y']): player['x'] = nx
        if walkable(player['x'], ny): player['y'] = ny

        # Player timers
        player['atk_t']  = max(0.0, player['atk_t']  - dt)
        player['atk_cd'] = max(0.0, player['atk_cd'] - dt)
        player['inv_t']  = max(0.0, player['inv_t']  - dt)

        # Attack
        if attack_key and player['atk_cd'] <= 0:
            player['atk_t']  = ATK_DUR
            player['atk_cd'] = ATK_CD
            fd = player['facing']
            for e in enemies:
                if not e['alive']:
                    continue
                if math.hypot(e['x'] - player['x'], e['y'] - player['y']) < ATK_REACH:
                    e['hp']   -= 1
                    e['hit_t'] = 6
                    if e['hp'] <= 0:
                        e['alive'] = False
                        for _ in range(5):
                            particles.append({
                                'x': e['x'], 'y': e['y'],
                                'vx': random.uniform(-2.5, 2.5),
                                'vy': random.uniform(-3.0, -0.5),
                                'life': random.uniform(0.4, 0.9),
                                'col': random.choice([C_GOLD, (220, 60, 60)]),
                                'size': random.randint(2, 4),
                            })

        # Item pickup
        for it in items:
            if it['collected']:
                continue
            if math.hypot(it['x'] - player['x'], it['y'] - player['y']) < 0.65:
                it['collected'] = True
                if it['type'] == 'potion':
                    player['hp'] = min(player['max_hp'], player['hp'] + 2)
                    for _ in range(6):
                        particles.append({
                            'x': it['x'], 'y': it['y'],
                            'vx': random.uniform(-1.5, 1.5),
                            'vy': random.uniform(-2.5, -0.5),
                            'life': 0.55,
                            'col': (80, 205, 100),
                            'size': 3,
                        })
                else:
                    gold += 1

        # Stairs
        sx2, sy2 = dungeon['stairs_pos']
        if math.hypot(player['x'] - (sx2 + 0.5), player['y'] - (sy2 + 0.5)) < 0.72:
            floor_num += 1
            if floor_num > best_floor:
                best_floor = floor_num
            dungeon, player, gold = _load_floor(floor_num, gold)
            particles = []
            continue

        # Enemy AI
        for e in enemies:
            if not e['alive']:
                continue
            if e['hit_t'] > 0:
                e['hit_t'] -= 1
            e['atk_t'] = max(0.0, e['atk_t'] - dt)
            dist = math.hypot(e['x'] - player['x'], e['y'] - player['y'])

            if dist < e['sight'] and has_los(tiles, e['x'], e['y'],
                                              player['x'], player['y']):
                e['state'] = 'chasing'
            elif e['state'] == 'chasing' and dist > e['sight'] + 3:
                e['state'] = 'idle'

            if e['state'] == 'chasing':
                e['path_t'] += dt
                if e['path_t'] >= PATH_INT or not e['path']:
                    e['path_t'] = 0.0
                    e['path']   = bfs_path(
                        tiles,
                        (int(e['x']), int(e['y'])),
                        (int(player['x']), int(player['y'])),
                    )

                if e['path']:
                    tx2, ty2 = float(e['path'][0][0]), float(e['path'][0][1])
                    ddx, ddy = tx2 - e['x'], ty2 - e['y']
                    dn       = math.hypot(ddx, ddy)
                    if dn < 0.12:
                        e['x'], e['y'] = tx2, ty2
                        e['path'].pop(0)
                    else:
                        step     = e['spd'] * dt
                        e['x']  += (ddx / dn) * step
                        e['y']  += (ddy / dn) * step
                        e['facing'] = [ddx / dn, ddy / dn]

                if dist < e['ar'] and e['atk_t'] <= 0 and player['inv_t'] <= 0:
                    player['hp']   -= e['dmg']
                    player['inv_t'] = 0.85
                    e['atk_t']      = ENEMY_ACD
                    if player['hp'] <= 0:
                        player['alive'] = False

        # Particles
        for p in particles[:]:
            p['x']    += p['vx'] * dt
            p['y']    += p['vy'] * dt
            p['life'] -= dt
            if p['life'] <= 0:
                particles.remove(p)

        # Death check
        if not player['alive']:
            state = 'dead'
            continue

        # ── Camera ─────────────────────────────────────────────────────────
        cam_x = max(0, min(int(player['x'] * TILE - SW     // 2),
                           MAP_W * TILE - SW))
        cam_y = max(0, min(int(player['y'] * TILE - GAME_H // 2),
                           MAP_H * TILE - GAME_H))

        def w2s(wx, wy):
            """
            Convert world-space tile coordinates to screen-space pixels.

            Parameters:
                wx (float): X position in tile units.
                wy (float): Y position in tile units.

            Returns:
                tuple[int, int]: (screen_x, screen_y) pixel position.
            """
            return int(wx * TILE - cam_x), int(wy * TILE - cam_y)

        # ── Render to game_surf ─────────────────────────────────────────────
        game_surf.fill(C_BG)

        stx = max(0, cam_x // TILE)
        etx = min(MAP_W, (cam_x + SW)     // TILE + 2)
        sty = max(0, cam_y // TILE)
        ety = min(MAP_H, (cam_y + GAME_H) // TILE + 2)

        for ty in range(sty, ety):
            for tx in range(stx, etx):
                draw_tile(game_surf, tiles[ty][tx],
                          tx * TILE - cam_x, ty * TILE - cam_y, floor_num)

        for it in items:
            if not it['collected']:
                draw_item(game_surf, *w2s(it['x'], it['y']), it['type'], frame)

        for e in enemies:
            if e['alive']:
                sx3, sy3 = w2s(e['x'], e['y'])
                draw_enemy(game_surf, sx3, sy3, e)

        px_s, py_s = w2s(player['x'], player['y'])

        # Flicker when invincible
        if player['inv_t'] <= 0 or frame % 6 < 4:
            draw_player(game_surf, px_s, py_s, player['facing'], player['atk_t'])

        # Particles
        for p in particles:
            ps_x, ps_y = w2s(p['x'], p['y'])
            pygame.draw.circle(game_surf, p['col'], (ps_x, ps_y), p['size'])

        # ── Torch lighting (full-screen dark overlay with light cutout) ─────
        dark = pygame.Surface((SW, GAME_H))
        dark.fill(C_BLACK)
        dark.blit(LIGHT_MASK, (px_s - _LR, py_s - _LR))
        game_surf.blit(dark, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

        # ── Composite ───────────────────────────────────────────────────────
        screen.blit(game_surf, (0, 0))
        draw_hud(screen, player, gold, floor_num, font_big)
        draw_minimap(screen, tiles, enemies, items, (player['x'], player['y']))
        pygame.display.flip()


if __name__ == '__main__':
    main()
