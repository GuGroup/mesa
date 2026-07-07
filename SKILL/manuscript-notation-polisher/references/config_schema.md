# Notation Config Schema

```json
{
  "rules": [
    {
      "pattern": "MoS2",
      "segments": [
        {"text": "MoS"},
        {"text": "2", "subscript": true}
      ]
    },
    {
      "pattern": "Delta G_H",
      "segments": [
        {"text": "ΔG"},
        {"text": "H", "subscript": true}
      ]
    }
  ]
}
```

Rules are literal string matches, applied longest pattern first.
