import discord
from discord.ext import commands
from discord import app_commands
import asyncio


class Fill(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _compute_fill(self, member: discord.Member, guild: discord.Guild):
        member_roles = [r for r in member.roles if r != guild.default_role]
        if not member_roles:
            return None, None, []

        highest_role = max(member_roles, key=lambda r: r.position)
        highest_pos  = highest_role.position

        bot_member  = guild.get_member(self.bot.user.id)
        bot_highest = max(bot_member.roles, key=lambda r: r.position).position

        member_role_ids = {r.id for r in member.roles}
        roles_to_add = [
            role for role in guild.roles
            if role != guild.default_role
            and not role.managed
            and role.position < highest_pos
            and role.position < bot_highest
            and role.id not in member_role_ids
        ]
        return highest_role, highest_pos, roles_to_add

    async def _do_fill(self, member: discord.Member, guild: discord.Guild):
        highest_role, highest_pos, roles_to_add = self._compute_fill(member, guild)
        if highest_role is None:
            return None, None, [], []

        added, failed = [], []
        for role in roles_to_add:
            try:
                await member.add_roles(role, reason=f"fill command by {member}")
                added.append(role)
            except (discord.Forbidden, discord.HTTPException):
                failed.append(role)

        return highest_role, len(roles_to_add), added, failed

    @app_commands.command(name="fill", description="Grant yourself all roles below your highest role that you don't already have")
    async def fill(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only MM staff or higher can use the fill command.", ephemeral=True)
            return

        highest_role, total, added, failed = await self._do_fill(interaction.user, interaction.guild)

        if highest_role is None:
            await interaction.followup.send("You don't have any roles to fill from.", ephemeral=True)
            return

        if not added and not failed:
            await interaction.followup.send(f"✅ You already have all roles below **{highest_role.name}**.", ephemeral=True)
            return

        embed = discord.Embed(
            title="✅ Roles Filled",
            color=discord.Color.green() if not failed else discord.Color.orange()
        )
        embed.add_field(name="Highest Role", value=highest_role.mention, inline=True)
        embed.add_field(name=f"Roles Added ({len(added)})", value=", ".join(r.mention for r in added) if added else "None", inline=False)
        if failed:
            embed.add_field(name=f"Could Not Add ({len(failed)})", value=", ".join(r.mention for r in failed), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.command(name="fill")
    async def fill_prefix(self, ctx: commands.Context):
        """Grant yourself all roles below your highest role. (MM or higher only)"""
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only MM staff or higher can use the fill command.", delete_after=10)
            return

        highest_role, total, added, failed = await self._do_fill(ctx.author, ctx.guild)

        if highest_role is None:
            await ctx.send("You don't have any roles to fill from.")
            return

        if not added and not failed:
            await ctx.send(f"✅ You already have all roles below **{highest_role.name}**.")
            return

        embed = discord.Embed(
            title="✅ Roles Filled",
            color=discord.Color.green() if not failed else discord.Color.orange()
        )
        embed.add_field(name="Highest Role", value=highest_role.mention, inline=True)
        embed.add_field(name=f"Roles Added ({len(added)})", value=", ".join(r.mention for r in added) if added else "None", inline=False)
        if failed:
            embed.add_field(name=f"Could Not Add ({len(failed)})", value=", ".join(r.mention for r in failed), inline=False)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Fill(bot))
