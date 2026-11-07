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
| Margin with an `ok` anchor | `90` s | BR-09 |
| Margin with a `parcial` anchor | `240` s | BR-10 |
| Short-tail threshold | `150` s | BR-10 |
| Margin with a `parcial` anchor and a short tail | `420` s | BR-10 |
| Fallback share when there is no anchor | `0.45` of the episode | BR-11 |
| Fallback cap | `1500` s | BR-11 |
| Expanded-window share | `0.60` of the episode | BR-14 |
| Expanded-window cap | `2400` s | BR-14 |

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

## Audio window

| ID | Rule | Origin |
|---|---|---|
| BR-09 | With an `ok` anchor, the window starts 90 s before it and reaches the end of the episode. | Initial |
| BR-10 | With a `parcial` anchor, the margin is 240 s. If the tail is shorter than 150 s, the margin is 420 s. | Initial |
| BR-11 | Without an anchor, the window is the last 45 % of the episode, capped at 1500 s. | Initial |
| BR-12 | The window start is never below 0, and the window always reaches the end of the episode. | Decision |
| BR-13 | `window_origin` records why the window was chosen: `anchor`, `fallback` or `expanded`. | Decision |
| BR-14 | The expanded window is the last 60 % of the episode, capped at 2400 s. It is used only when the extraction is incomplete; its trigger belongs to phase 6. | Initial |
| BR-15 | Audio is downloaded and kept only for analysis. It is never published, uploaded or shared. | Decision |

## How the initial values are validated

After processing the 50 existing episodes, measure:

- The distribution of `ok`, `parcial` and `sin_ancla`.
- How many `ok` detections point at a plausible section when checked by hand.
- How many anchors would cut off the start of the section, which is what the margin in the audio
  step will correct.

With that, adjust BR-01 and BR-02 before touching the margins.

After the first 5 to 10 windows are downloaded, also check:

- How many episodes used `fallback` instead of an anchor.
- Whether the margins are larger than needed: how far before the anchor the section actually
  starts in the audio.
- Whether any window exceeds the transcription size limit. If so, BR-14 or the transcription
  chunking will absorb it.
