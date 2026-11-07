# Rules

Business rules carry a `BR-xx` id so code, tests and documentation can cite the same thing.
Parameters are the numbers those rules use; if a value changes, it changes here first.

Origin: **Decision** means the author decided it. **Initial** means a starting value that will be
measured and adjusted with real episodes.

## Parameters

| Parameter | Value | Used by |
|---|---|---|
| Minimum anchor position | `0.5` (second half of the episode) | BR-01 |
| Maximum distance from the anchor to the end | `720` s | BR-02 |

## Anchor detection

| ID | Rule | Origin |
|---|---|---|
| BR-01 | A candidate match only counts if it falls in the second half of the episode. | Initial |
| BR-02 | A candidate match only counts if it is at most 720 s from the end of the episode. | Initial |
| BR-03 | Among the kinds detected, the earliest one sets `anchor_s`; the others are kept in `anchor_kinds`. | Initial |
| BR-04 | The state is `ok` when both `juego` and `peli` appear, `parcial` when at least one appears and the other does not, and `sin_ancla` when none appear. | Initial |
| BR-05 | Without a subtitle file, the anchor step succeeds with `subtitles_available = false` and `anchor_state = sin_ancla`. The audio step uses its fallback. | Decision |
| BR-06 | One subtitle language per episode. Preference: `es`, `es-orig`, `es-419`, `es-mx`, `es-es`, then any other `es*`. Non-chosen files are deleted. | Initial |
| BR-07 | Rolling-caption prefixes are dropped before matching, so the same sentence is not counted several times. | Initial |
| BR-08 | Anchor data and evidence are internal. They are used to review a detection and are never published. | Decision |

## How the initial values are validated

After processing the 50 existing episodes, measure:

- The distribution of `ok`, `parcial` and `sin_ancla`.
- How many `ok` detections point at a plausible section when checked by hand.
- How many anchors would cut off the start of the section, which is what the margin in the audio
  step will correct.

With that, adjust BR-01 and BR-02 before touching the margins.
