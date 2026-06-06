import discord
from discord.ext import commands
import db


DIVIDER = "─" * 32


class Boost(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since is None and after.premium_since is not None:
            await self._send_boost_message(after)

    # Backup: catch the system boost message Discord posts in the channel
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.type == discord.MessageType.premium_guild_subscription
            and not message.author.bot
        ):
            await self._send_boost_message(message.author)

    async def _send_boost_message(self, member: discord.Member):
        guild_id = str(member.guild.id)
        channel_id = db.get_config(guild_id, "boost_channel")
        if not channel_id or not channel_id.isdigit():
            return

        channel = member.guild.get_channel(int(channel_id))
        if not channel:
            return

        cfg = db.get_all_config(guild_id)
        custom_msg = cfg.get("boost_message") or (
            f"**{member.display_name}** just boosted the server! 💖\n"
            "DM the **owner** to claim your **free rewards**!"
        )
        image = cfg.get("boost_image", "")

        # Replace {user} placeholder with mention
        custom_msg = custom_msg.replace("{user}", member.mention)

        embed = discord.Embed(
            description=(
                f"{DIVIDER}\n\n"
                f"✨ **Thank you for boosting, {member.mention}!** ✨\n\n"
                f"{custom_msg}\n\n"
                f"{DIVIDER}"
            ),
            color=discord.Color.from_rgb(255, 115, 250)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        if image:
            embed.set_image(url=image)

        try:
            await channel.send(content=member.mention, embed=embed)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(Boost(bot))
