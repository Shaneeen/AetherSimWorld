# Comparison Block World

## Purpose

This is the simplified comparison map used by:
- [compare_humanoid_agents.py](/abs/path/d:/SimWorld/scripts/NativeAgents/compare_humanoid_agents.py)

It uses small block markers instead of large buildings so:
- the center stays open
- targets are easier to see
- agents are less likely to spawn under or inside large geometry
- semantic comparisons are easier to interpret

## Center Area

The area around:

```text
(0, 0)
```

is intentionally kept mostly empty.

Rough idea:
- first ~1000 cm around origin should feel clear
- semantic markers are placed outside that open zone

## Marker Semantics

### Stores

Stores are small pink blocks.

Examples:
- `Visible_Store_Marker_1`
- `Store_Marker_2`

### Buildings

Buildings are blue-toned blocks with slightly larger or taller shapes.

Examples:
- `Office_Marker_1`
- `Apartment_Marker_1`
- `Tall_Building_Marker_1`

### Trees

Trees are green narrow blocks.

Examples:
- `ComparisonTree_1`
- `ComparisonTree_2`

### Trash

Trash is a small gray block.

Example:
- `ComparisonTrash_1`

## How Meaning Is Assigned

The bots do not rely only on visible color.

For reliability, semantics are mostly inferred from:
- object names
- marker naming patterns

So:
- pink helps you visually
- names help the code reason correctly

## Main File

- [comparison_world.py](/abs/path/d:/SimWorld/scripts/NativeAgents/comparison_world.py)

That file controls:
- which markers exist
- where they are placed
- what box asset they use
- what scale they have
- what color they get after loading

## How To Customize

If you want to add your own target type, edit:
- `nodes`
- `MARKER_COLORS`

in [comparison_world.py](/abs/path/d:/SimWorld/scripts/NativeAgents/comparison_world.py)

Example pattern:

```python
_node('Library_Marker_1', 'BP_Box2_C', 2400.0, -1200.0, z=40.0, scale=(0.6, 0.4, 0.8))
```

Then add a color like:

```python
'Library_Marker_1': (255, 215, 0)
```

If you want the bots to understand that new type semantically, also update:
- [native_semantics.py](/abs/path/d:/SimWorld/scripts/NativeAgents/native_semantics.py)
- and, if needed, [humanoid_map.py](/abs/path/d:/SimWorld/scripts/humanoid/map/humanoid_map.py)
