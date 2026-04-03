## Why Is the Format Structured This Way?

### Design Decision

The format `TRIGGER:<TYPE>COMMAND xREPEAT` is not chosen at random. It's a compromise between:

- **Simplicity** (Users can understand it)
- **Machine readability** (Code can parse it)
- **Flexibility** (various command types)

---

### Alternatives (and Why They Weren't Chosen)

**Alternative 1: JSON format**

```json
{
  "triggers": [
    {
      "id": "follow",
      "command": "/give @a diamond",
      "repeat": 1
    }
  ]
}
```

**Pro:** Structured, easy to parse
**Con:** Too strict, users make a lot of mistakes with brackets/commas

---

**Alternative 2: Config-based (YAML)**

```yaml
actions:
  follow:
    command: /give @a diamond
    repeat: 1
```

**Pro:** Readable
**Con:** Too much setup

---

**Alternative 3: SQL database**

```sql
INSERT INTO actions VALUES ('follow', '/give @a diamond', 1);
```

**Pro:** Powerful, data persistent
**Con:** Overkill, needs external tools

---

### The Chosen Format: Why It Is Better

```
follow:/give @a diamond x1
```

**Advantages:**

1. **One line per action** – Easy to understand
2. **Separation with `:` and `x`** – Clear structure without brackets
3. **Minimal, concise** – Beginners understand it quickly
4. **Not too strict** (Optional: `x` may be missing)
5. **Comment support** (#) – Simply deactivate lines
6. **Compatible** – Works in regular text editors

---

### Parsing Is Easy

For the code:

```python
# Example: "follow:/give @a diamond x3"
parts = line.split(":")
trigger = parts[0]           # "follow"
cmd_with_repeat = parts[1]   # "/give @a diamond x3"

# Extract repeat count
if "x" in cmd_with_repeat:
    cmd, repeat = cmd_with_repeat.rsplit("x", 1)
    repeat_count = int(repeat)
else:
    cmd = cmd_with_repeat
    repeat_count = 1

# Determine type
if cmd.startswith("/"):
    kind = "vanilla"
elif cmd.startswith("!"):
    kind = "plugin"
elif cmd.startswith("$"):
    kind = "built_in"
```

**Simple, efficient, robust!**

---

### Final Note

The format works because it has found a **sweet spot** between manual editing and machine processing. Not too flexible, not too strict – just right.

---
