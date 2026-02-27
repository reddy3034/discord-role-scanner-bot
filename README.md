# Event Role Bot

Built this because manually giving roles to 400+ event submissions was a nightmare. The bot scans a channel or thread, checks each message, and gives the role to everyone except people whose submission has a cross reaction on it.

---

## Setup

You'll need Python 3.12+ and a bot token. That's it.

Install the one dependency:
```bash
pip install discord.py
```

Set your token as an environment variable:

**Windows CMD:**
```cmd
set TOKEN=your_bot_token_here
```
**PowerShell:**
```powershell
$env:TOKEN="your_bot_token_here"
```
**Mac/Linux:**
```bash
export TOKEN=your_bot_token_here
```

Then just run it:
```bash
python bot.py
```

---

## Permissions

The bot needs these three permissions in your server — if it's missing any of them it'll either error out or silently fail:

- **Manage Roles** — obviously, to give roles
- **Read Message History** — to scan through the submissions
- **View Channel** — to actually see the channel

One thing that catches people out: the bot's role in Server Settings → Roles needs to be **above** whatever role you're trying to assign. If it's below, every assignment will fail. Just drag it up.

Only people with **Manage Roles** permission can run the commands. Admins and the server owner always have access.

---

## Commands

### `/giverolechannel`
Use this when submissions are in a regular text channel.

- `channel` — which channel to scan *(required)*
- `role` — which role to give out *(required)*
- `attachment_filter` — see below *(optional, default: everyone)*
- `start_message` — paste a message link to start from *(optional)*
- `end_message` — paste a message link to stop at *(optional)*

If you don't set a start/end, it'll just scan the whole channel.

---

### `/giverolethread`
Same thing but for threads. Run it from inside the thread itself — no need to specify which thread.

- `role` — which role to give out *(required)*
- `attachment_filter` — see below *(optional, default: everyone)*
- `start_message` — paste a message link to start from *(optional)*
- `end_message` — paste a message link to stop at *(optional)*

If the thread is archived it'll unarchive it automatically before scanning.

---

## Attachment Filter

Sometimes you only want to give the role to people who actually sent something specific. The filter has three options:

- `none` — don't filter at all, everyone gets the role (this is the default)
- `image` — only people who attached an image
- `link` — only people who included a URL in their message

---

## Cross Reactions

Any submission with a cross reaction gets skipped — that person won't receive the role. Works with ❌ ❎ ✖ ✕ and any custom emoji with "cross", "x", "reject", "wrong" or "fail" in the name.

This is always on, there's no way to disable it.

If someone submitted multiple times and only some of their posts have a cross on them — as long as one submission is clean, they still get the role.

---

## The Report

After every scan you'll get a private message (only you can see it) breaking down what happened:

- How many people were scanned in total
- How many got the role
- How many already had it
- How many were skipped due to a cross reaction
- How many were filtered out by the attachment filter
- How many submitted more than once
- Anyone the bot failed to assign (with a reason)

---

## A Few Things Worth Knowing

**Getting a message link** — Right-click any message → Copy Message Link. That's what you paste into start/end message.

**Big events** — For 400-500 submissions the bot takes a few minutes. There's a small delay between each role assignment to avoid getting rate limited by Discord. You'll see a live counter so you know it's still running.

**Bot stopped halfway?** — Most likely a permissions issue. Check that the bot role is above the target role, and that it has View Channel + Read Message History on that specific channel.
