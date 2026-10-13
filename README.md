# Prompt Video Editor

Edit and combine your videos and photos by typing what you want in plain English.
Free, open source, and fully local: a free LLM running on your own computer
(through [Ollama](https://ollama.com)) understands the instruction, plain Python
does all the time math, and FFmpeg does the cutting and joining.

> **Example:** you upload two videos and one photo, then type
>
> *"From video1 take 2:34 to 2:55 and 5:12 to 5:50. Then combine clip 1, the
> picture for 4 seconds, clip 2, and finally video2."*
>
> You get one MP4: clip 1 (21s), the photo (4s), clip 2 (38s), then all of video2.

## How it works

```
 your sentence ──► local LLM (Ollama) ──► JSON plan ──► Python checks + math ──► FFmpeg ──► final.mp4
                    or offline rules          ▲                                    
                                              └── you can review and edit it here
```

1. **Upload.** Each file gets a short name: `video1`, `video2`, `photo1`, and so on.
   The app reads every file's length, size and whether it has sound.
2. **Understand.** The LLM turns your sentence into a plan and copies times exactly
   as you wrote them (`"2:34"`). It never does arithmetic. If Ollama is not running,
   a built in rule based parser handles the common phrasings instead.
3. **Check.** Python converts every time to seconds (2:34 = 154), works out each
   clip's length and the total, and catches mistakes such as a clip ending after
   the video ends. If the LLM made a mistake, it is told exactly what was wrong and
   gets one retry.
4. **Review.** You see a timeline of the final video and can edit the plan by hand.
5. **Render.** FFmpeg cuts each clip, turns photos into short silent clips, fits
   everything to the same size (black bars instead of stretching), and joins them.

## Setup on a Mac

You need [Homebrew](https://brew.sh) and Python 3.10 or newer.

```bash
# 1. Tools
brew install ffmpeg ollama

# 2. A free local model (about 4.7 GB; use qwen2.5:3b on Macs with 8 GB RAM)
ollama serve &            # or just open the Ollama app
ollama pull qwen2.5:7b

# 3. The app
git clone https://github.com/pavankonam/prompt-video-editor.git
cd prompt-video-editor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Run it (opens http://127.0.0.1:7860 in your browser)
python app.py
```

No Ollama? The app still works with the offline rule parser; just pick
"Offline rules only" or leave it on "Auto".

### Try it with sample media

```bash
python scripts/make_samples.py   # creates samples/video1.mp4 (6:10), samples/video2.mp4, samples/photo1.png
```

Upload the three files in that order and press **Make plan** with the example prompt.

## Writing instructions

Refer to files by their short names (`video1`, `photo1`), by their original file
names (`beach.jpg`), or naturally (`the picture`, `the second video`).

| You can write | Meaning |
|---|---|
| `2:34 to 2:55`, `2:34-2:55`, `between 2:34 and 2:55` | a clip |
| `1:02:03`, `154s`, `2m34s` | other time formats |
| `clip 1`, `the first clip`, `the last clip` | a clip you defined earlier |
| `the photo for 4 seconds` | photo length (default is 3 seconds) |
| `video2`, `the second video` | a whole video |
| `then`, `after that`, `finally` | order |

More examples:

* `take 0:05 to 0:10 from party.mov, then show beach.jpg for 2 seconds, then trip`
* `cut video2 0:01 to 0:03 and 0:10 to 0:12`
* `photo1 for 5 seconds then video1 then photo2 for 5 seconds`

## Choosing a model

| Model | RAM | Notes |
|---|---|---|
| `qwen2.5:7b` (default) | 8 GB free | most accurate |
| `qwen2.5:3b` | 4 GB free | faster, good for simple prompts |
| `llama3.2:3b` | 4 GB free | alternative small model |

Change it in the app's "Ollama model" box, or set `PVE_MODEL=qwen2.5:3b` before
starting. Set `OLLAMA_HOST` if Ollama runs somewhere other than `localhost:11434`.

## Project layout

```
app.py              Gradio web interface (upload, prompt, timeline, player)
editor/
  media.py          names uploads and reads their properties with ffprobe
  llm.py            asks the local Ollama model for a JSON plan
  rules.py          offline rule based parser (no LLM needed)
  planner.py        picks the engine, validates, retries, falls back
  plan.py           checks the plan and does all the time math
  timecode.py       parses "2:34", "1:02:03", "45s" and formats times
  render.py         FFmpeg cutting, photo to clip, scaling and joining
scripts/make_samples.py   generates test media
tests/              unit tests plus an end to end render test
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The planner tests use a fake Ollama server, so they pass without a model installed.

## Roadmap

* Transitions (fades, crossfades)
* Background music and volume control
* Text titles and captions
* Speed changes and muting parts
* Drag and drop timeline editing

## License

MIT
