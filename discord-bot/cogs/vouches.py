import discord
from discord.ext import commands
from discord import app_commands
import db


class Vouches(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="vouch", description="Vouch for a user after a trade")
    @app_commands.describe(user="The user to vouch for", note="Optional note about the trade")
    async def vouch(self, interaction: discord.Interaction, user: discord.Member, note: str = ""):
        if user.id == interaction.user.id:
            await interaction.response.send_message("You cannot vouch for yourself.", ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message("You cannot vouch for bots.", ephemeral=True)
            return

        if db.has_vouched_recently(str(interaction.user.id), str(user.id), str(interaction.guild_id), hours=24):
            await interaction.response.send_message(
                "You have already vouched for this user in the last 24 hours. Spam protection is active.",
                ephemeral=True
            )
            return

        db.add_vouch(str(interaction.user.id), str(user.id), str(interaction.guild_id), note)
        count = db.count_vouches(str(user.id), str(interaction.guild_id))

        cfg    = db.get_all_config(str(interaction.guild_id))
        title  = cfg.get("vouch_title")  or "Vouch Added ⭐"
        footer = cfg.get("vouch_footer") or ""
        image  = cfg.get("vouch_image")  or ""

        embed = discord.Embed(title=title, color=discord.Color.yellow())
        embed.add_field(name="Vouched For",   value=user.mention,               inline=True)
        embed.add_field(name="By",            value=interaction.user.mention,    inline=True)
        embed.add_field(name="Total Vouches", value=f"⭐ {count}",               inline=True)
        if note:
            embed.add_field(name="Note", value=note, inline=False)
        if footer:
            embed.set_footer(text=footer)
        if image:
            embed.set_image(url=image)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rep", description="Check a user's reputation/vouch count")
    @app_commands.describe(user="The user to check")
    async def rep(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        vouches = db.get_vouches(str(target.id), str(interaction.guild_id))
        count   = len(vouches)

        embed = discord.Embed(
            title=f"Reputation — {target.display_name}",
            color=discord.Color.yellow()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Total Vouches", value=f"⭐ {count}", inline=False)

        if vouches:
            recent = vouches[:5]
            lines  = []
            for v in recent:
                from_member = interaction.guild.get_member(int(v["from_user"]))
                from_name   = from_member.mention if from_member else f"<@{v['from_user']}>"
                note_part   = f" — *{v['note']}*" if v.get("note") else ""
                date        = v["created_at"][:10]
                lines.append(f"{from_name}{note_part} `{date}`")
            embed.add_field(name="Recent Vouches", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setvouches", description="[Staff] Manually set a user's vouch count")
    @app_commands.describe(user="Target user", count="New vouch count")
    async def setvouches(self, interaction: discord.Interaction, user: discord.Member, count: int):
        from cogs.tickets import is_mm_or_admin
        if not is_mm_or_admin(interaction.user):
            await interaction.response.send_message("Only staff can set vouches.", ephemeral=True)
            return
        if count < 0:
            await interaction.response.send_message("Count cannot be negative.", ephemeral=True)
            return
        db.set_vouches(str(user.id), str(interaction.guild_id), count)
        embed = discord.Embed(
            title="Vouches Updated",
            description=f"Set {user.mention}'s vouches to **{count}**.",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="deletevouch", description="[Staff] Delete the latest vouch from one user to another")
    @app_commands.describe(user="The user whose vouch to delete", voucher="The user who gave the vouch")
    async def deletevouch(self, interaction: discord.Interaction, user: discord.Member, voucher: discord.Member):
        from cogs.tickets import is_mm_or_admin
        if not is_mm_or_admin(interaction.user):
            await interaction.response.send_message("Only staff can delete vouches.", ephemeral=True)
            return
        deleted = db.delete_latest_vouch(str(voucher.id), str(user.id), str(interaction.guild_id))
        if deleted:
            await interaction.response.send_message(
                f"Deleted the latest vouch from {voucher.mention} to {user.mention}.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("No vouch found to delete.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Vouches(bot))
