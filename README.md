# My Tasks — PyQt6 Windows App

A self-contained task manager desktop app using PyQt6 + SQLite.
No server required. Data is stored in `~/tasks.db`.

## Run from source

```bash
pip install -r requirements.txt
python main.py
```

## Build a Windows .exe

Run this **on a Windows machine** (or Windows VM):

```cmd
pip install -r requirements.txt
pyinstaller taskapp.spec
```

The output is at:
```
dist\MyTasks.exe
```

Double-click to run — no Python installation needed on the target machine.

## Features

- Add tasks with a category (work / personal / health / learning)
- Check off tasks as done
- Inline edit task titles — click ✎
- Delete tasks with confirmation
- Filter by status or category
- Live stats — Total / Done / Pending
- Data persists in `~/tasks.db` (SQLite, single file)
- Old unfinished tasks roll into `previous_tasks` on the next day
- Closing or minimizing hides the app to the system tray

## Project layout

```
taskapp/
├── main.py          # All app code — DB, models, UI
├── taskapp.spec     # PyInstaller build config
├── requirements.txt
└── README.md
```

## Adding an icon

1. Put `icon.ico` in the project folder
2. In `taskapp.spec`, change `icon=None` → `icon='icon.ico'`
3. Rebuild

## Customising categories

Edit `CATEGORY_COLORS`, the category filter list, and the `cat_combo.addItems(...)` call in `_build_ui()`.
