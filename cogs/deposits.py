import discord
from discord.ext import commands
from discord import app_commands
from discord.app_commands import Choice
import asyncio
import db


DEPOSIT_TYPES = [
    Choice(name="In-Game Item", value="ingame"),
    Choice(name="Real Money (PayPal, etc.)", value="realmoney"),
    Choice(name="Custom / Other", value="custom"),
]


# ── Modals ────────────────────────────────────────────────────────────────────

class IngameDepositModal(discord.ui.Modal, title="Log In-Game Deposit"):
    game  = discord.ui.TextInput(label="Game",  placeholder="e.g. Runescape, WoW, Roblox")
    item  = discord.ui.TextInput(label="Item",  placeholder="e.g. Party Hat, 10M Gold, Sword")
    value = discord.ui.TextInput(label="Value", placeholder="e.g. $50 or 100M gold")
    date  = discord.ui.TextInput(label="Date",  placeholder="e.g. 2025-06-06", required=False)

    def __init__(self, user: discord.Member):
        super().__init__()
        self.target_user = user

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        date_str = self.date.value.strip() or "Not specified"
        amount_str = f"{self.item.value} ({self.game.value})"
        note_str   = f"Value: {self.value.value} | Date: {date_str}"

        await asyncio.to_thread(
            db.add_deposit,
            str(self.target_user.id),
            str(interaction.guild_id),
            "ingame",
            amount_str,
            note_str,
            str(interaction.user.id)
        )

        embed = discord.Embed(title="Deposit Logged 💰", color=discord.Color.green())
        embed.add_field(name="User",  value=self.target_user.mention, inline=True)
        embed.add_field(name="Type",  value="In-Game Item",           inline=True)
        embed.add_field(name="Game",  value=self.game.value,          inline=True)
        embed.add_field(name="Item",  value=self.item.value,          inline=True)
        embed.add_field(name="Value", value=self.value.value,         inline=True)
        embed.add_field(name="Date",  value=date_str,                 inline=True)
        embed.set_footer(text=f"Logged by {interaction.user}")

        deposit_log_id = await asyncio.to_thread(db.get_config, str(interaction.guild_id), "deposit_log_channel")
        if deposit_log_id:
            lc = interaction.guild.get_channel(int(deposit_log_id))
            if lc:
                await lc.send(embed=embed)

        await interaction.followup.send(embed=embed, ephemeral=True)


class GeneralDepositModal(discord.ui.Modal, title="Log Deposit"):
    amount = discord.ui.TextInput(label="Amount / Item", placeholder="e.g. $50 PayPal or 500 gold")
    date   = discord.ui.TextInput(label="Date",          placeholder="e.g. 2025-06-06", required=False)
    note   = discord.ui.TextInput(label="Note (optional)", required=False, placeholder="Any additional info")

    def __init__(self, user: discord.Member, deposit_type: str):
        super().__init__()
        self.target_user  = user
        self.deposit_type = deposit_type

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        date_str = self.date.value.strip() or "Not specified"
        note_str = f"Date: {date_str}"
        if self.note.value:
            note_str += f" | {self.note.value}"

        await asyncio.to_thread(
            db.add_deposit,
            str(self.target_user.id),
            str(interaction.guild_id),
            self.deposit_type,
            self.amount.value,
            note_str,
            str(interaction.user.id)
        )

        type_labels = {"realmoney": "Real Money", "custom": "Custom/Other"}
        embed = discord.Embed(title="Deposit Logged 💰", color=discord.Color.green())
        embed.add_field(name="User",   value=self.target_user.mention, inline=True)
        embed.add_field(name="Type",   value=type_labels.get(self.deposit_type, self.deposit_type), inline=True)
        embed.add_field(name="Amount", value=self.amount.value, inline=True)
        embed.add_field(name="Date",   value=date_str,          inline=True)
        if self.note.value:
            embed.add_field(name="Note", value=self.note.value, inline=False)
        embed.set_footer(text=f"Logged by {interaction.user}")

        deposit_log_id = await asyncio.to_thread(db.get_config, str(interaction.guild_id), "deposit_log_channel")
        if deposit_log_id:
            lc = interaction.guild.get_channel(int(deposit_log_id))
            if lc:
                await lc.send(embed=embed)

        await interaction.followup.send(embed=embed, ephemeral=True)


# ── Cog ───────────────────────────────────────────────────────────────────────

class Deposits(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="depositset", description="[MM+] Log a deposit for a user")
    @app_commands.describe(user="The user making the deposit", deposit_type="Type of deposit")
    @app_commands.choices(deposit_type=DEPOSIT_TYPES)
    async def depositset(self, interaction: discord.Interaction, user: discord.Member, deposit_type: Choice[str]):
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.response.send_message("Only MM role or higher can log deposits.", ephemeral=True)
            return
        if deposit_type.value == "ingame":
            await interaction.response.send_modal(IngameDepositModal(user))
        else:
            await interaction.response.send_modal(GeneralDepositModal(user, deposit_type.value))

    @app_commands.command(name="depositcheck", description="View deposit history for a user")
    @app_commands.describe(user="The user to check")
    async def depositcheck(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only staff can check deposits.", ephemeral=True)
            return

        deposits = await asyncio.to_thread(db.get_deposits, str(user.id), str(interaction.guild_id))
        if not deposits:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ No deposit records found for **{user.display_name}**.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

        type_labels = {"ingame": "In-Game", "realmoney": "Real Money", "custom": "Custom"}

        embed = discord.Embed(
            title=f"Deposit History — {user.display_name}",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        for d in deposits[:10]:
            staff = interaction.guild.get_member(int(d["staff_id"]))
            staff_name = staff.display_name if staff else f"<@{d['staff_id']}>"
            label = type_labels.get(d["deposit_type"], d["deposit_type"])
            val = f"**{d['amount']}**\nType: {label}\nBy: {staff_name}"
            if d.get("note"):
                val += f"\n{d['note']}"
            embed.add_field(name=f"Deposit #{d['id']}", value=val, inline=False)

        if len(deposits) > 10:
            embed.set_footer(text=f"Showing 10 of {len(deposits)} deposits.")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="depositdelete", description="[Staff] Delete a deposit record by ID")
    @app_commands.describe(user="The user", deposit_id="Deposit ID to delete")
    async def depositdelete(self, interaction: discord.Interaction, user: discord.Member, deposit_id: int):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only staff can delete deposits.", ephemeral=True)
            return
        await asyncio.to_thread(db.delete_deposit, deposit_id)
        await interaction.followup.send(
            f"Deposit `#{deposit_id}` for {user.mention} has been deleted.",
            ephemeral=True
        )

    # ── Prefix Commands ───────────────────────────────────────────────────────

    @commands.command(name="depositcheck")
    async def depositcheck_prefix(self, ctx: commands.Context, user: discord.Member):
        """View deposit history for a user."""
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only staff can check deposits.", delete_after=10)
            return

        deposits = await asyncio.to_thread(db.get_deposits, str(user.id), str(ctx.guild.id))
        if not deposits:
            await ctx.send(embed=discord.Embed(
                description=f"❌ No deposit records found for **{user.display_name}**.",
                color=discord.Color.red()
            ))
            return

        type_labels = {"ingame": "In-Game", "realmoney": "Real Money", "custom": "Custom"}
        embed = discord.Embed(title=f"Deposit History — {user.display_name}", color=discord.Color.gold())
        embed.set_thumbnail(url=user.display_avatar.url)

        for d in deposits[:10]:
            staff = ctx.guild.get_member(int(d["staff_id"]))
            staff_name = staff.display_name if staff else f"<@{d['staff_id']}>"
            label = type_labels.get(d["deposit_type"], d["deposit_type"])
            val = f"**{d['amount']}**\nType: {label}\nBy: {staff_name}"
            if d.get("note"):
                val += f"\n{d['note']}"
            embed.add_field(name=f"Deposit #{d['id']}", value=val, inline=False)

        if len(deposits) > 10:
            embed.set_footer(text=f"Showing 10 of {len(deposits)} deposits.")

        await ctx.send(embed=embed)

    @commands.command(name="depositdelete")
    async def depositdelete_prefix(self, ctx: commands.Context, user: discord.Member, deposit_id: int):
        """Delete a deposit record by ID."""
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only staff can delete deposits.", delete_after=10)
            return
        await asyncio.to_thread(db.delete_deposit, deposit_id)
        await ctx.send(f"Deposit `#{deposit_id}` for {user.mention} has been deleted.")


async def setup(bot):
    await bot.add_cog(Deposits(bot))
