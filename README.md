# bbdjson2human: Balanced by Daylight → Discord forum posts

Turns your [Balanced by Daylight](https://balancedbydaylight.com) ruleset (hosted on GitHub) into Discord forum posts: one per killer and one per tier. The script can publish them for you through a webhook, and when the ruleset changes it edits only the messages that changed.

## Requirements

- Python 3.8+ (no extra packages)
- Internet connection
- Your ruleset `.json` hosted in a GitHub repository
- A Discord forum channel and the Manage Webhooks permission (to publish)

## Quick start

```
python bbdjson2human.py
```

**First run:** the script asks, once each, for:
1. the GitHub link to your ruleset file (open the file on github.com and copy the address bar),
2. your webhook URL (see below),
3. the tag ID of each tier tag (S, A, B, C, D),
4. the folder with your post pictures.

It saves your answers and doesn't ask again. Then it shows what it will publish and asks `Publish these? [y/N]`. Nothing is sent before you say `y`.

**Try it on a test forum first.** Create a throwaway forum channel with the same tags, make a webhook for it, and run:

```
python bbdjson2human.py --test
```

`--test` publishes only 3 posts: General, one tier post and one killer. Posts are remembered per webhook, so switching to your real webhook later (`--set-webhook`) starts clean.

## Publishing to Discord

### Setting up the webhook

In your forum channel: Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL. Paste it when the script asks. **Treat the URL like a password**: anyone who has it can post in your forum. Never share it or upload it anywhere. If it leaks, delete the webhook in Discord and make a new one.

### What gets posted

| Post | Contents |
|---|---|
| Each killer and each tier S–D | A forum post with the title, the picture and the tier tag, then one message under it with the body. |
| General | The same, but each category (killer perk bans, survivor perk bans, killer combo bans, survivor combo bans) is its own message. |

- **Order:** tier posts first, then killer posts, so killer posts can link to the tier posts. The script reads each tier post's link from Discord itself, so you never paste links.
- **Tags:** each killer gets its tier's tag. A killer's tier is the one letter shared by its killer bans (General counts as D) and its survivor bans (General counts as S). If there is no single match, the post is created without a tag and you get a warning. Tier posts get their own tier's tag, and General gets none. You can skip a tag by pressing Enter when asked for its ID (`--set-tags` to enter them again).
- **Pictures:** the script matches a picture to a post by file name (ignoring "The", capital letters, spaces and punctuation, so `Nurse.png` matches "The Nurse"; for tier posts `Tier S`, `S Tier` or `S` all work). Formats: png, jpg, jpeg, webp, gif. If a picture can't be matched, it asks once for the file name and remembers it. Posts without a picture get their title as the first message.
- **Updating:** a later run compares each message with what it published last time. Changed messages are edited in place (the post, its picture and its link stay the same), new messages are added, and unchanged ones are left alone. A change on a tier post doesn't force a repost of the killer posts unless the link itself changed.
- **Rate limits:** the script paces itself and waits when Discord asks it to. A full first publish takes a couple of minutes.
- **If something fails midway**, everything published so far is saved. Fix the problem and run again to continue.

### Limits of webhooks

- Only the script can edit its messages. Nobody, including you, can edit a webhook's messages by hand in Discord. Fix things through the ruleset and the script.
- A webhook can't rename posts, change their tags or delete them. If a title or a killer's tier changes, the script warns you and you do it by hand. Messages that are no longer part of a post, and posts of killers you removed, also have to be deleted by hand (moderators can).
- Your existing posts can't be adopted. The first publish creates a fresh set, and you delete the old ones yourself.
- Messages are limited to 2000 characters. A longer message is skipped with a warning (it is never split automatically).
- If you delete a post in Discord, the script notices when it next needs to edit it and creates it again.

### Without a terminal

Prompts need a terminal. If the script is run without one, add `--yes` to publish without confirmation.

## Writing files instead (`--no-publish`)

```
python bbdjson2human.py --no-publish
```

Writes the posts as `.txt` files (one per post, containing only the body) to `output/<date>_<commit>/`, and tells you which killers and tiers changed since the version you last posted.

1. Downloads your newest ruleset and compares it to the version you last posted.
2. Writes the changed **tier posts** first and asks for the Discord link of each (right-click the post → Copy link). Killer posts then show those links instead of text lines like "B Tier bans". Links are saved in `tier_links.json`; Enter keeps a saved link or skips a missing one (the killer post then shows the plain text line).
3. Writes the changed **killer posts**.
4. Asks: *"Did you post these? (would you like to update the saved ruleset to the latest version?)"* `y` saves this version as your baseline; `n` keeps it, so the same changes show up next run.

## Options

| Option | What it does |
|---|---|
| *(none)* | Publish to Discord if a webhook is saved (asks for one on first run). |
| `--test` | Publish only 3 posts: General, one tier post and one killer. |
| `--dry-run` | Show what would be published; send nothing. |
| `--yes` | Publish without the confirmation question. |
| `--no-publish` | Write post files instead of publishing (see above). |
| `--set-webhook [URL]` | Change the saved webhook. Give the URL, or leave it empty to be asked. |
| `--set-tags` | Enter the tier tag IDs again. |
| `--set-images [FOLDER]` | Change the folder with your post pictures. |
| `--set-url [LINK]` | Change the saved ruleset link. |
| `--no-data-update` | Skip downloading the perk/addon/map/item/offering lists (use `data/`). |
| `--data <folder>` | Use a different folder for the data lists (default: `data/`). |
| `<file.json>` | Use a local ruleset file instead of GitHub. |

Options for file mode (`--no-publish`) only:

| Option | What it does |
|---|---|
| `--all` | Write every post, not just the changed ones. |
| `--print` | Also print the written posts in the terminal. |
| `--no-save` | Preview only: don't save the "last posted" version or ask for tier links. |
| `--links` | Ask for every tier post's link again. |
| `--no-links` | Never ask for tier post links (saved ones are still used). |
| `--since <commit id>` | Compare against a specific older version of your ruleset. |
| `--out <folder>` | Write posts to a different folder (default: `output/`). |

Examples:

```
python bbdjson2human.py --test
python bbdjson2human.py --dry-run
python bbdjson2human.py --set-webhook
python bbdjson2human.py --no-publish --all
```

## Unknown IDs (after a DBD update)

The data lists come from the site creator's repo and are refreshed every run. If your ruleset uses a perk, addon, map, item or offering the lists don't know yet, the script asks for its name in the terminal and shows where it's used (e.g. *"Unknown perk ID 321, used in: The Nurse > Killer perks"*). Answers are saved in `data/custom_names.json`, so each ID is asked once. Press Enter to skip; it will be asked again next run. Run the script in a normal terminal so it can ask.

## Files it creates

| Path | Purpose |
|---|---|
| `config.json` | Your ruleset link, webhook URL, tag IDs and picture settings. **Contains your webhook URL: keep it private.** |
| `published.json` | Which posts and messages were published where. **Don't delete it**: without it the script can't find its earlier posts and would publish duplicates. |
| `last_posted.json`, `tier_links.json` | File mode only: your last posted version and tier links. |
| `data/` | The downloaded data lists, plus `custom_names.json`. |
| `output/` | File mode only: the post files. |

## Good to know

- **Special notes:** "Two firecrackers are allowed!" becomes `Firecracker x2` in Items, and "Double Vigo's Shroud must be used!" becomes `Vigo's Shroud x2` in Survivor offerings. Those notes are then left out of the Notes block. Other notes stay in Notes.
- **After a name change in the lists:** posts aren't flagged as changed if only a perk's name changed in the data lists. Edit the ruleset or use file mode with `--all` to regenerate.
- **Private repo:** set an environment variable `GITHUB_TOKEN` to a personal access token with read access.
- **Rate limits (GitHub):** if GitHub's API is busy, the script falls back to GitHub's public commit feed automatically.
- **Changing the look:** colours, section labels and wording are in the settings block at the top of `bbdjson2human.py`.
- **If you share this script:** share only `bbdjson2human.py` and `README.md`. Never share `config.json`, `published.json`, or anything else this script created.

The perk, addon, map, item and offering lists are maintained by the creator of
[Balanced by Daylight](https://github.com/kylestarrtech/Balanced-by-Daylight) and are
downloaded from their repository when the script runs. This tool is an unofficial
companion and is not affiliated with or endorsed by Balanced by Daylight or Dead by Daylight.
Thanks to Broc for helping figure it all out.
