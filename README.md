# twitcho

`twitcho` streams one stereo pair from an audio input device to Twitch while
using a low-resolution pre-rendered animation as the video source.

The first version is intentionally small and independent of `recs`.

## Configuration

Create a JSON config file:

```json
{
  "device_name": "X18",
  "channel": 17,
  "video": "visual-bed.mp4",
  "twitch_key": "live_..."
}
```

Then run:

```bash
twitcho --config config.json
```

`channel` is one-based and names the first channel of the stereo pair. For
example, `17` streams channels 17 and 18.

`twitcho` requires `ffmpeg` to be installed.

## Rendering a visual bed

Use `scripts/render.py` to turn looped videos and still images into one prepared
video for Twitcho:

```bash
scripts/render.py \
  --inputs a-looped.mp4 b-looped.mp4 still.png \
  --output visual-bed.mp4 \
  --duration 3600 \
  --seed 1234 \
  --title-card title.png
```

The renderer starts from black, optionally fades through the title card, and then
chooses inputs at random. It crossfades slowly between scenes and occasionally
fades the title card over the current scene without changing the underlying media
sequence. Each crossfade lasts half the length of the longer adjacent input, and
shorter inputs are looped when necessary to cover the fade.
