# 09 — Doing Flow images and Pixabay downloads yourself (only with browser access)

Default (02/04): Bil generates images in Google Flow and downloads sounds, you prepare prompts and import.
Use this file only if your workspace has a browser that is signed in to Bil's Google account (flow.google.com)
and Bil asked you to do it. Never sign in, enter passwords or change browser settings yourself.

## Google Flow
- One Flow project per story ("Juru Kunci"), one collection per episode ("Juru Kunci - Eps 02").
- Characters are saved as Flow Characters (Bayu, Sekar, Mbah Karto, Sumirah; Pak Darno failed to save, so
  describe him with his full character_block).
- Work in the agent panel ("What do you want to create?"):
  1. Add references with `@` + the character name, and **search the picker by name**. Pick the entry whose type
     says "Character", then "Add to prompt". Never trust the picker order; it changes as images are added
     (batch 7 of ep01 got Sekar's face on Bayu's scenes this way).
  2. Batch 6-8 beats that share characters/locations; paste the beat prompts from `output/flow_prompts.md`.
  3. Submit with the arrow / "Start generation" button (Enter does not submit). Wait for the batch to finish.
- Rename each result to `[bXXX]`; when regenerating, rename the old one to `[bXXX]-old`.
- Check every image (see 02 §3 and 08). Common misses: torii or Western iron gates, horse-carriage hearse with
  umbrellas, "REST IN PEACE" text, friendly ghost smiles. Fix with the image editor ("What do you want to
  change?") or regenerate.
- Thumbnails `thumb_epXX_16x9` and `thumb_epXX_9x16` in the same session; text = story title + "EPISODE N"
  only. Put the previous episode's thumbnail in the prompt as a reference for identical title lettering.
- Download with "Download collection" (zip). 1K is enough for scenes; 2K upscaling is slow.
- Flow AI credits reset monthly. If Flow shows a low-credits warning, tell Bil how many images are still
  missing before continuing, and prefer `reuse` + `crop` in script.yaml over near-duplicate images.

## Pixabay sounds
- Search pixabay.com/sound-effects with 1-3 English keywords; prefer clean recordings without voices/music.
- Click Download and **wait ~15 s for the "Nice one!" modal** before leaving the page, or the download is lost.
- One download at a time. Pixabay throttles: if pages time out, pause a few minutes; keep in-page waits < 40 s.
- If downloads keep failing, send Bil the list of item URLs to download manually instead of retrying.
- License: Pixabay Content License (commercial use, no attribution). Music bed: YouTube Audio Library tracks
  marked "Attribution not required" only. Never use audio ripped from films, games, YouTube or TikTok.
- Register every new key in `stories/<slug>/sound_assets.yaml` (slug with trailing numeric id, or title +
  artist), then `sound-import`. Reuse existing keys across episodes; only fetch what's new.
- Javanese fit: night crickets/wind, rain on a tin roof, roosters and motorbikes in the morning, kentongan
  (3 hits, pause, 3 hits), rattan creak, wooden door knock (always 3 knocks). No church bells or English voices.
