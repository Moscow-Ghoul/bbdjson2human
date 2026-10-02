# Balanced by Daylight → Discord forum posts

Turns your [Balanced by Daylight](https://balancedbydaylight.com) ruleset (hosted on GitHub) into ready-to-paste Discord forum posts: one per killer, one per tier. When you update the ruleset, it tells you which posts changed so you only repost those.

## Requirements

* Python 3.8+ (no extra packages)
* Internet connection
* Your ruleset `.json` hosted in a GitHub repository

## Quick start

```bash
python bbdjson2human.py
```

**First run:** the script asks for the GitHub link to your ruleset file (open the file on github.com and copy the address bar, e.g. `https://github.com/<user>/<repo>/blob/main/Ruleset.json`). It saves the link in `config.json` and doesn't ask again.

**Every run:**

1. Downloads the newest perk / addon / map / item / offering lists from the site creator's repo.
2. Downloads your newest ruleset from GitHub.
3. Compares it to the version you last posted and prints what changed, per killer and tier.
4. Writes the changed posts to `output/<date>_<commit>/`, one `.txt` per post (named after the killer or tier, containing only the post body).
5. Asks: *"Did you post these? (would you like to update the saved ruleset to the latest version?)"*

   * `y` → saves this version as your baseline; the next run compares against it.
   * `n` (or close the window) → nothing is saved; the same changes show up next time.

The very first run has no baseline, so every post is written.

## Options

| Option                | What it does                                                                          |
| --------------------- | ------------------------------------------------------------------------------------- |
| *(none)*              | The normal run described above.                                                       |
| `--all`               | Write every post, not just the changed ones.                                          |
| `--print`             | Also print the written posts in the terminal.                                         |
| `--no-save`           | Preview only: never updates the saved "last posted" version (no question at the end). |
| `--since <commit id>` | Compare against a specific older version of your ruleset instead of the saved one.    |
| `--set-url [LINK]`    | Change the saved ruleset link. Give the link, or leave it empty to be asked.          |
| `--no-data-update`    | Skip downloading the perk/addon/map/item/offering lists (use the copies in `data/`).  |
| `--data <folder>`     | Use a different folder for the data lists (default: `data/`).                         |
| `--out <folder>`      | Write posts to a different folder (default: `output/`).                               |
| `<file.json>`         | Use a local ruleset file instead of GitHub (no comparison, nothing saved).            |

Examples:

```bash
python bbdjson2human.py --all
python bbdjson2human.py --print --no-save
python bbdjson2human.py --since 2a90a65
python bbdjson2human.py --set-url
python bbdjson2human.py MyRuleset.json
```

## Unknown IDs (after a DBD update)

The data lists come from the site creator's repo and are refreshed every run. If your ruleset uses a perk, addon, map, item or offering that the lists don't know yet, the script asks for its name in the terminal and shows where it's used (e.g. *"Unknown perk ID 321, used in: The Nurse > Killer perks"*). Your answers are saved in `data/custom_names.json`, so each ID is asked once. Press Enter to skip an ID; it will be asked again next run. Run the script in a normal terminal so it can ask.

## Files it creates

| Path               | Purpose                                              |
| ------------------ | ---------------------------------------------------- |
| `config.json`      | Your saved ruleset link.                             |
| `last_posted.json` | The GitHub version (commit id) you last posted.      |
| `data/`            | The downloaded data lists, plus `custom_names.json`. |
| `output/`          | One folder per run containing the post files.        |

## Good to know

* **Special notes:** "Two firecrackers are allowed!" becomes `Firecracker x2` in Items, and "Double Vigo's Shroud must be used!" becomes `Vigo's Shroud x2` in Survivor offerings. Those notes are then left out of the Notes block.
* **Pasting:** the post files contain real Discord `ansi` colour codes (invisible characters). Copy the whole file content and paste it into the forum post.
* **Length:** Discord limits a message to 2000 characters. The script doesn't split posts; the General tier post is usually the one that goes over.
* **Private repo:** set an environment variable `GITHUB_TOKEN` to a personal access token with read access.
* **Rate limits:** if GitHub's API is busy, the script falls back to GitHub's public commit feed automatically.
* **After a name change in the lists:** posts aren't flagged as changed (old and new are rendered with current names). Run with `--all` to regenerate everything.
* **Changing the look:** colours, section labels, and wording are in the settings block at the top of `bbdjson2human.py`.

## Credits

The perk, addon, map, item and offering lists are maintained by the creator of
[Balanced by Daylight](https://github.com/kylestarrtech/Balanced-by-Daylight) and are
downloaded from their repository when the script runs. This tool is an unofficial
companion and is not affiliated with or endorsed by Balanced by Daylight or Dead by Daylight.
Thanks to Broc for helping figure it all out.
