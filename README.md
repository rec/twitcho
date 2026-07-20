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
