# The Abyss

A procedurally generated dungeon crawler built in Python with pygame.

Every floor is unique — rooms are placed at random, corridors carved between them.
Descend as deep as you dare, fighting goblins, skeletons and demons with only torchlight to guide you.

## Features

- **Procedural generation** — no two floors are the same (random room placement + L-shaped corridor carving)
- **3 enemy types** — Goblin, Skeleton, Demon, each with unique stats and behaviour
- **BFS pathfinding** — enemies navigate around walls to hunt you down
- **Torch lighting** — radial gradient light mask limits your field of view
- **Collectibles** — health potions and gold coins scattered through rooms
- **Minimap** — top-right overview of the floor layout
- **Pause** — press P to pause at any time

## Controls

| Key | Action |
|-----|--------|
| W / A / S / D or Arrow keys | Move |
| SPACE | Attack (circle radius around player) |
| P | Pause / Resume |
| ESC | Quit |

## How to Run

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the game:
   ```
   python src/dungeon.py
   ```

## Project Structure

```
the-abyss/
├── src/
│   └── dungeon.py      # Main game — all logic, rendering, and AI
├── requirements.txt    # Python dependencies
└── README.md
```

## Code Highlights

- **Data structures**: `dict` for player/enemy state, `list[list[int]]` tile grid, `list[dict]` for enemies/items/particles
- **Algorithms**: BFS shortest-path (enemy AI), ray-marching line-of-sight, radial gradient pre-render
- **Error handling**: `try/except` around font loading with safe fallback fonts
- **Docstrings**: every function documents purpose, parameters, and return value

## Requirements

- Python 3.10+
- pygame-ce 2.5+
