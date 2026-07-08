# Equation Number Config Schema

```json
{
  "mode": "auto",
  "start_number": 1,
  "number_on": "middle",
  "placement": {
    "style": "three_column_table",
    "table_width_twips": 9360,
    "side_width_twips": 900
  },
  "exclude_lines": []
}
```

Top-level fields:

- `mode`: `auto` or `explicit`. Default: `auto` when no `groups` are provided.
- `start_number`: first equation number. Default: `1`.
- `number_on`: where to place a number for automatically detected multi-line
  equation groups: `first`, `middle`, or `last`. Default: `middle`.
- `placement`: number placement style. Default is a borderless three-column
  table that keeps the equation centered while placing `(N)` in a separate
  right cell.
- `exclude_lines`: optional matchers for displayed equations to skip.
- `groups`: explicit ordered equation groups, used when `mode` is `explicit`.
  Numbers are assigned sequentially unless a group sets `number` explicitly.

Placement fields:

- `style`: `three_column_table`, `spaces`, or `right_tab`. Prefer
  `three_column_table` for stable centered equation appearance.
- `table_width_twips`: total table width for `three_column_table`.
- `side_width_twips`: equal left and right side-column width for
  `three_column_table`.
- `space_count`: fixed number of spaces before `(N)` when `style` is `spaces`.
- `target_column`: optional adaptive spacing target. When present, the skill
  pads each numbered line toward this approximate character column.
- `min_space_count` / `max_space_count`: bounds for adaptive spacing.
- `right_tab_twips`: right tab stop when `style` is `right_tab`.

Group fields:

- `label`: optional report label.
- `lines`: one or more line matchers. A multi-line group receives one equation
  number.
- `number`: optional explicit integer number.
- `number_on`: where to place the number for multi-line groups: `first`,
  `middle`, or `last`. Default: `last`.

Line matchers:

- String: normalized exact match.
- `{"exact": "..."}`: normalized exact match.
- `{"contains": "..."}`: normalized substring match.
- `{"regex": "..."}`: Python regular expression match after normalization.

Normalization removes whitespace differences and maps common mathematical
variants such as `−` to `-`, `⇌` to `<->`, and `→` to `->`.

Automatic mode detects displayed Word math (`m:oMathPara` or direct `m:oMath`)
paragraphs. Consecutive displayed equation paragraphs are grouped and receive
one number.
