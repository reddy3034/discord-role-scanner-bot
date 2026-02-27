import os
import re
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from collections import defaultdict
from enum import Enum

# ---------- INTENTS ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- ATTACHMENT FILTER ENUM ----------
class AttachmentFilter(str, Enum):
    none       = "none"        # No filter — everyone gets role (default)
    image      = "image"       # Only people who sent an image
    link       = "link"        # Only people who sent a URL in their message

# URL detection regex
URL_REGEX = re.compile(r"https?://\S+")


# ---------- ON READY ----------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


# ---------- CUSTOM PERMISSION CHECK ----------
def has_manage_roles():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild.owner_id == interaction.user.id:
            return True
        perms = interaction.user.guild_permissions
        if perms.manage_roles or perms.administrator:
            return True
        raise app_commands.MissingPermissions(["manage_roles"])
    return app_commands.check(predicate)


# ---------- CROSS REACTION DETECTOR ----------
def is_cross_reaction(reaction: discord.Reaction) -> bool:
    unicode_crosses = {"❌", "❎", "✖", "✕"}
    if isinstance(reaction.emoji, str):
        return reaction.emoji in unicode_crosses
    if isinstance(reaction.emoji, discord.Emoji):
        name = reaction.emoji.name.lower()
        return any(word in name for word in ["cross", "x", "reject", "wrong", "fail"])
    return False


# ---------- ATTACHMENT FILTER CHECK ----------
def passes_attachment_filter(message: discord.Message, filter: AttachmentFilter) -> bool:
    if filter == AttachmentFilter.none:
        return True  # No filter, everyone passes

    if filter == AttachmentFilter.image:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                return True
        return False

    if filter == AttachmentFilter.link:
        return bool(URL_REGEX.search(message.content))

    return True


# ---------- SHARED PROCESSING LOGIC ----------
async def process_messages(interaction, messages, role, attachment_filter: AttachmentFilter):
    # Role hierarchy check upfront
    if role >= interaction.guild.me.top_role:
        await interaction.followup.send(
            "❌ I can't assign that role — it's higher than or equal to my highest role. "
            "Please move my bot role above the target role in Server Settings → Roles.",
            ephemeral=True
        )
        return

    user_has_clean = defaultdict(bool)
    user_message_count = defaultdict(int)
    all_users = set()
    filter_failed_users = set()

    async for message in messages:
        if message.author.bot:
            continue

        all_users.add(message.author)
        user_message_count[message.author] += 1

        # Check cross reaction
        has_cross = any(
            is_cross_reaction(r) and r.count > 0
            for r in message.reactions
        )
        if has_cross:
            continue

        # Check attachment filter
        if not passes_attachment_filter(message, attachment_filter):
            filter_failed_users.add(message.author)
            continue

        user_has_clean[message.author] = True

    valid_users = {u for u, ok in user_has_clean.items() if ok}
    excluded_users = all_users - valid_users
    duplicate_users = {u for u, c in user_message_count.items() if c > 1}

    guild = interaction.guild
    assigned_users = []
    already_had_role = []
    failed_users = []

    total = len(valid_users)
    processed = 0

    progress_msg = await interaction.followup.send(
        f"⏳ Assigning roles... `0/{total}` done.",
        ephemeral=True
    )

    for user in valid_users:
        member = guild.get_member(user.id)
        if not member:
            failed_users.append(f"{user} (left server?)")
            processed += 1
            continue

        if role in member.roles:
            already_had_role.append(user)
            processed += 1
            continue

        try:
            await member.add_roles(role, reason="Event submission scan")
            assigned_users.append(user)
        except discord.Forbidden:
            failed_users.append(f"{user} (permission denied)")
        except discord.HTTPException as e:
            failed_users.append(f"{user} (HTTP error: {e.status})")

        processed += 1

        if processed % 10 == 0:
            try:
                await progress_msg.edit(
                    content=f"⏳ Assigning roles... `{processed}/{total}` done."
                )
            except Exception:
                pass

        await asyncio.sleep(0.3)

    # Filter label for report
    filter_label = {
        AttachmentFilter.none:  "None (everyone)",
        AttachmentFilter.image: "Image only",
        AttachmentFilter.link:  "URL/Link only",
    }[attachment_filter]

    failed_section = ""
    if failed_users:
        display_failed = failed_users[:20]
        failed_section = (
            f"\n⚠️ **Failed assignments ({len(failed_users)}):**\n"
            + "\n".join(f"  • {u}" for u in display_failed)
        )
        if len(failed_users) > 20:
            failed_section += f"\n  ... and {len(failed_users) - 20} more."

    report = (
        f"✅ **Scan Complete**\n\n"
        f"🔍 **Attachment filter:** {filter_label}\n"
        f"👥 **Total users scanned:** {len(all_users)}\n"
        f"🏷️ **New roles assigned:** {len(assigned_users)}\n"
        f"🟦 **Already had role:** {len(already_had_role)}\n"
        f"❌ **Disqualified (cross reaction):** {len(excluded_users - filter_failed_users)}\n"
        f"🖼️ **Disqualified (attachment filter):** {len(filter_failed_users)}\n"
        f"🔁 **Duplicate submitters:** {len(duplicate_users)}\n"
        f"💥 **Failed to assign:** {len(failed_users)}"
        + failed_section
    )

    try:
        await progress_msg.edit(content=report)
    except Exception:
        await interaction.followup.send(report, ephemeral=True)


# ---------- PARSE MESSAGE ID FROM LINK ----------
def parse_message_id(link: str) -> int | None:
    try:
        return int(link.strip().split("/")[-1])
    except Exception:
        return None


# ---------- /giverolechannel ----------
@bot.tree.command(
    name="giverolechannel",
    description="Scan a channel and assign roles to valid submitters"
)
@has_manage_roles()
@app_commands.describe(
    channel="The channel to scan (required)",
    role="The role to assign (required)",
    attachment_filter="Give role only to: image senders, link senders, or everyone (default: everyone)",
    start_message="Message link to start from (optional — scans from beginning if not set)",
    end_message="Message link to end at (optional — scans to latest message if not set)"
)
async def giverolechannel(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    role: discord.Role,
    attachment_filter: AttachmentFilter = AttachmentFilter.none,
    start_message: str = None,
    end_message: str = None
):
    await interaction.response.defer(ephemeral=True)

    start_id = None
    end_id = None

    if start_message:
        start_id = parse_message_id(start_message)
        if start_id is None:
            await interaction.followup.send(
                "❌ Invalid start message link. Right-click a message → Copy Message Link.",
                ephemeral=True
            )
            return

    if end_message:
        end_id = parse_message_id(end_message)
        if end_id is None:
            await interaction.followup.send(
                "❌ Invalid end message link. Right-click a message → Copy Message Link.",
                ephemeral=True
            )
            return

    if start_id and end_id and start_id >= end_id:
        await interaction.followup.send(
            "❌ Start message must be older than the end message.",
            ephemeral=True
        )
        return

    history_kwargs = {"limit": None, "oldest_first": True}
    if start_id:
        history_kwargs["after"] = discord.Object(id=start_id - 1)
    if end_id:
        history_kwargs["before"] = discord.Object(id=end_id + 1)

    messages = channel.history(**history_kwargs)
    await process_messages(interaction, messages, role, attachment_filter)


# ---------- /giverolethread ----------
@bot.tree.command(
    name="giverolethread",
    description="Scan a thread and assign roles to valid submitters"
)
@has_manage_roles()
@app_commands.describe(
    role="The role to assign (required)",
    attachment_filter="Give role only to: image senders, link senders, or everyone (default: everyone)",
    start_message="Message link to start from (optional — scans from beginning if not set)",
    end_message="Message link to end at (optional — scans to latest message if not set)"
)
async def giverolethread(
    interaction: discord.Interaction,
    role: discord.Role,
    attachment_filter: AttachmentFilter = AttachmentFilter.none,
    start_message: str = None,
    end_message: str = None
):
    await interaction.response.defer(ephemeral=True)

    if not isinstance(interaction.channel, discord.Thread):
        await interaction.followup.send(
            "❌ This command must be used inside a thread.",
            ephemeral=True
        )
        return

    # Unarchive thread if needed
    if interaction.channel.archived:
        try:
            await interaction.channel.edit(archived=False)
        except Exception:
            await interaction.followup.send(
                "❌ This thread is archived and I couldn't unarchive it.",
                ephemeral=True
            )
            return

    start_id = None
    end_id = None

    if start_message:
        start_id = parse_message_id(start_message)
        if start_id is None:
            await interaction.followup.send("❌ Invalid start message link.", ephemeral=True)
            return

    if end_message:
        end_id = parse_message_id(end_message)
        if end_id is None:
            await interaction.followup.send("❌ Invalid end message link.", ephemeral=True)
            return

    if start_id and end_id and start_id >= end_id:
        await interaction.followup.send(
            "❌ Start message must be older than the end message.",
            ephemeral=True
        )
        return

    history_kwargs = {"limit": None, "oldest_first": True}
    if start_id:
        history_kwargs["after"] = discord.Object(id=start_id - 1)
    if end_id:
        history_kwargs["before"] = discord.Object(id=end_id + 1)

    messages = interaction.channel.history(**history_kwargs)
    await process_messages(interaction, messages, role, attachment_filter)


# ---------- ERROR HANDLER ----------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ You need the **Manage Roles** permission to use this command."
    else:
        msg = f"❌ An unexpected error occurred: `{error}`"

    try:
        await interaction.followup.send(msg, ephemeral=True)
    except Exception:
        await interaction.response.send_message(msg, ephemeral=True)


# ---------- RUN BOT ----------
if __name__ == "__main__":
    token = os.getenv("TOKEN")
    if not token:
        raise ValueError("No TOKEN environment variable set.")
    bot.run(token)
