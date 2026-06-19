import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import time
import db


MERCY_CLOSE_DELAY = 300  # 5 minutes in seconds


class MercyView(discord.ui.View):
    def __init__(self, inviter: discord.Member, invitee: discord.Member, role_id: int):
        super().__init__(timeout=300)
        self.inviter   = inviter
        self.invitee   = invitee
        self.role_id   = role_id
        self.responded = False

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invitee.id:
            await interaction.response.send_message("This invite is not for you.", ephemeral=True)
            return
        if self.responded:
            await interaction.response.send_message("Already responded.", ephemeral=True)
            return
        self.responded = True
        self.stop()

        role = interaction.guild.get_role(self.role_id)
        if role:
            try:
                await self.invitee.add_roles(role, reason="Mercy invite accepted")
            except discord.Forbidden:
                pass

        embed = discord.Embed(
            title="Mercy Invite Accepted ✅",
            description=f"{self.invitee.mention} has accepted the mercy invite from {self.inviter.mention}.",
            color=discord.Color.green()
        )
        if role:
            embed.add_field(name="Role Granted", value=role.mention)
        await interaction.response.edit_message(embed=embed, view=None)

        from cogs.tickets import get_cached_config
        cfg      = await get_cached_config(str(interaction.guild_id))
        dm_title = cfg.get("mercy_dm_title", "").strip() or "🎉 Mercy Invite Accepted"
        dm_body  = cfg.get("mercy_dm_body",  "").strip() or (
            f"Welcome! Your mercy invite from **{interaction.guild.name}** has been accepted "
            "and your role has been granted."
        )
        dm_image = cfg.get("mercy_dm_image", "").strip()

        dm_embed = discord.Embed(title=dm_title, description=dm_body, color=discord.Color.green())
        dm_embed.set_footer(text=interaction.guild.name)
        if dm_image:
            dm_embed.set_image(url=dm_image)
        try:
            await self.invitee.send(embed=dm_embed)
        except discord.Forbidden:
            pass

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji="❌")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invitee.id:
            await interaction.response.send_message("This invite is not for you.", ephemeral=True)
            return
        if self.responded:
            await interaction.response.send_message("Already responded.", ephemeral=True)
            return
        self.responded = True
        self.stop()
        await interaction.response.edit_message(embed=discord.Embed(
            title="Mercy Invite Declined ❌",
            description=f"{self.invitee.mention} has declined the mercy invite.",
            color=discord.Color.red()
        ), view=None)

    async def on_timeout(self):
        pass


class Mercy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # channel_id → asyncio.Task (the running close countdown)
        self._timers: dict[str, asyncio.Task] = {}
        # channel_id → monotonic timestamp when current task started
        self._started_at: dict[str, float] = {}
        # channel_id → total delay the current task was given
        self._task_delay: dict[str, float] = {}
        # channel_id → remaining seconds (set when hold is called)
        self._remaining: dict[str, float] = {}
        # channels currently on hold
        self._held: set[str] = set()
        # channel_id → (channel, guild, closer) for restart after unhold
        self._ctx_store: dict[str, tuple] = {}

    # ── Internal timer ────────────────────────────────────────────────────────

    async def _close_task(self, channel_id: str, delay: float):
        """Sleep then auto-close. Cancelled cleanly by hold."""
        await asyncio.sleep(delay)
        info = self._ctx_store.get(channel_id)
        if not info:
            return
        channel, guild, closer = info
        # Clean up state
        self._timers.pop(channel_id, None)
        self._started_at.pop(channel_id, None)
        self._task_delay.pop(channel_id, None)
        self._remaining.pop(channel_id, None)
        self._ctx_store.pop(channel_id, None)
        self._held.discard(channel_id)

        from cogs.tickets import close_ticket_channel
        try:
            await channel.send(embed=discord.Embed(
                title="⏰ Mercy Timer Expired",
                description="This ticket is being **automatically closed** — the mercy close timer has ended.",
                color=discord.Color.red()
            ))
            await close_ticket_channel(channel, guild, closer)
        except Exception:
            pass

    def _launch_timer(self, channel_id: str, delay: float):
        task = asyncio.create_task(self._close_task(channel_id, delay))
        self._timers[channel_id] = task
        self._started_at[channel_id] = time.monotonic()
        self._task_delay[channel_id] = delay

    def _cancel_timer(self, channel_id: str) -> float:
        """Cancel running task, return remaining seconds."""
        task = self._timers.pop(channel_id, None)
        if task:
            task.cancel()
        started  = self._started_at.pop(channel_id, None)
        delay    = self._task_delay.pop(channel_id, None)
        if started is not None and delay is not None:
            elapsed   = time.monotonic() - started
            remaining = max(0.0, delay - elapsed)
        else:
            remaining = self._remaining.get(channel_id, MERCY_CLOSE_DELAY)
        return remaining

    def has_active_timer(self, channel_id: str) -> bool:
        return channel_id in self._timers or channel_id in self._held

    def is_held(self, channel_id: str) -> bool:
        return channel_id in self._held

    # ── Core mercy logic ──────────────────────────────────────────────────────

    async def _send_mercy(self, channel, guild, user, inviter, cfg):
        """Send the mercy invite embed and start auto-close timer if in a ticket."""
        mercy_role_id_str = cfg.get("mercy_role", "")
        mercy_message     = cfg.get("mercy_message", "You have been selected for a special opportunity. Do you accept?")
        role_id = int(mercy_role_id_str) if mercy_role_id_str.isdigit() else 0
        role    = guild.get_role(role_id) if role_id else None

        embed = discord.Embed(
            title="🌟 You've Been Invited",
            description=f"{user.mention}\n\n{mercy_message}",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Invited by {inviter}")
        if role:
            embed.add_field(name="Role on Acceptance", value=role.mention)

        await channel.send(content=user.mention, embed=embed, view=MercyView(inviter, user, role_id))

        # Check if this is a ticket channel — if so, start auto-close timer
        ticket = await asyncio.to_thread(db.get_ticket, str(channel.id))
        if ticket:
            channel_id = str(channel.id)
            # Cancel any previous timer on this channel
            if self.has_active_timer(channel_id):
                self._cancel_timer(channel_id)
                self._held.discard(channel_id)

            self._ctx_store[channel_id] = (channel, guild, inviter)
            self._remaining[channel_id] = MERCY_CLOSE_DELAY
            self._launch_timer(channel_id, MERCY_CLOSE_DELAY)

            await channel.send(embed=discord.Embed(
                title="⏳ Auto-Close Timer Started",
                description=(
                    "This ticket will be **automatically closed in 5 minutes**.\n\n"
                    "Use `$hold` / `/hold` to pause the timer.\n"
                    "Use `$unhold` / `/unhold` to resume it."
                ),
                color=discord.Color.orange()
            ).set_footer(text="Timer started by mercy command"))

    # ── Slash Commands ────────────────────────────────────────────────────────

    @app_commands.command(name="mercy", description="Send a mercy/special invite embed to a user")
    @app_commands.describe(user="The user to invite")
    async def mercy(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer()
        from cogs.tickets import is_mm_or_admin, get_cached_config
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only MM staff can send mercy invites.", ephemeral=True)
            return
        if user.bot:
            await interaction.followup.send("Cannot send mercy invites to bots.", ephemeral=True)
            return
        cfg = await get_cached_config(str(interaction.guild_id))
        await interaction.followup.send("✅ Mercy invite sent.", ephemeral=True)
        await self._send_mercy(interaction.channel, interaction.guild, user, interaction.user, cfg)

    @app_commands.command(name="hold", description="Pause the mercy auto-close timer for this ticket")
    async def hold(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=discord.Embed(description="🚫 Only MM staff can use this.", color=discord.Color.red()), ephemeral=True)
            return
        channel_id = str(interaction.channel_id)
        if not self.has_active_timer(channel_id):
            await interaction.followup.send(embed=discord.Embed(description="⚠️ No active mercy timer in this channel.", color=discord.Color.yellow()), ephemeral=True)
            return
        if self.is_held(channel_id):
            await interaction.followup.send(embed=discord.Embed(description="⚠️ Timer is already on hold.", color=discord.Color.yellow()), ephemeral=True)
            return
        remaining = self._cancel_timer(channel_id)
        self._remaining[channel_id] = remaining
        self._held.add(channel_id)
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        await interaction.channel.send(embed=discord.Embed(
            title="⏸️ Timer Paused",
            description=(
                f"{interaction.user.mention} has paused the auto-close timer.\n\n"
                f"**Time remaining:** `{mins}m {secs}s`\n"
                "Use `$unhold` / `/unhold` to resume."
            ),
            color=discord.Color.blue()
        ))
        await interaction.followup.send("⏸️ Timer paused.", ephemeral=True)

    @app_commands.command(name="unhold", description="Resume the mercy auto-close timer for this ticket")
    async def unhold(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send(embed=discord.Embed(description="🚫 Only MM staff can use this.", color=discord.Color.red()), ephemeral=True)
            return
        channel_id = str(interaction.channel_id)
        if not self.has_active_timer(channel_id) and channel_id not in self._held:
            await interaction.followup.send(embed=discord.Embed(description="⚠️ No mercy timer exists for this channel.", color=discord.Color.yellow()), ephemeral=True)
            return
        if not self.is_held(channel_id):
            await interaction.followup.send(embed=discord.Embed(description="⚠️ Timer is not currently on hold.", color=discord.Color.yellow()), ephemeral=True)
            return
        remaining = self._remaining.get(channel_id, MERCY_CLOSE_DELAY)
        self._held.discard(channel_id)
        self._launch_timer(channel_id, remaining)
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        await interaction.channel.send(embed=discord.Embed(
            title="▶️ Timer Resumed",
            description=(
                f"{interaction.user.mention} has resumed the auto-close timer.\n\n"
                f"**Time remaining:** `{mins}m {secs}s`\n"
                "Use `$hold` / `/hold` to pause again."
            ),
            color=discord.Color.green()
        ))
        await interaction.followup.send("▶️ Timer resumed.", ephemeral=True)

    # ── Prefix Commands ───────────────────────────────────────────────────────

    @commands.command(name="mercy")
    async def mercy_prefix(self, ctx: commands.Context, user: discord.Member):
        from cogs.tickets import is_mm_or_admin, get_cached_config
        if not await is_mm_or_admin(ctx.author):
            await ctx.send("Only MM staff can send mercy invites.", delete_after=10)
            return
        if user.bot:
            await ctx.send("Cannot send mercy invites to bots.", delete_after=10)
            return
        cfg = await get_cached_config(str(ctx.guild.id))
        await self._send_mercy(ctx.channel, ctx.guild, user, ctx.author, cfg)

    @commands.command(name="hold")
    async def hold_prefix(self, ctx: commands.Context):
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send(embed=discord.Embed(description="🚫 Only MM staff can use this.", color=discord.Color.red()), delete_after=10)
            return
        channel_id = str(ctx.channel.id)
        if not self.has_active_timer(channel_id):
            await ctx.send(embed=discord.Embed(description="⚠️ No active mercy timer in this channel.", color=discord.Color.yellow()))
            return
        if self.is_held(channel_id):
            await ctx.send(embed=discord.Embed(description="⚠️ Timer is already on hold.", color=discord.Color.yellow()))
            return
        remaining = self._cancel_timer(channel_id)
        self._remaining[channel_id] = remaining
        self._held.add(channel_id)
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        await ctx.send(embed=discord.Embed(
            title="⏸️ Timer Paused",
            description=(
                f"{ctx.author.mention} has paused the auto-close timer.\n\n"
                f"**Time remaining:** `{mins}m {secs}s`\n"
                "Use `$unhold` / `/unhold` to resume."
            ),
            color=discord.Color.blue()
        ))

    @commands.command(name="unhold")
    async def unhold_prefix(self, ctx: commands.Context):
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(ctx.author):
            await ctx.send(embed=discord.Embed(description="🚫 Only MM staff can use this.", color=discord.Color.red()), delete_after=10)
            return
        channel_id = str(ctx.channel.id)
        if channel_id not in self._held and not self.has_active_timer(channel_id):
            await ctx.send(embed=discord.Embed(description="⚠️ No mercy timer exists for this channel.", color=discord.Color.yellow()))
            return
        if not self.is_held(channel_id):
            await ctx.send(embed=discord.Embed(description="⚠️ Timer is not currently on hold.", color=discord.Color.yellow()))
            return
        remaining = self._remaining.get(channel_id, MERCY_CLOSE_DELAY)
        self._held.discard(channel_id)
        self._launch_timer(channel_id, remaining)
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        await ctx.send(embed=discord.Embed(
            title="▶️ Timer Resumed",
            description=(
                f"{ctx.author.mention} has resumed the auto-close timer.\n\n"
                f"**Time remaining:** `{mins}m {secs}s`\n"
                "Use `$hold` / `/hold` to pause again."
            ),
            color=discord.Color.green()
        ))


async def setup(bot):
    await bot.add_cog(Mercy(bot))
