import discord
from discord.ext import commands
from discord import app_commands
import db
import asyncio


async def _add_link_buttons(view: discord.ui.View, guild_id, cfg_key_prefix: str):
    """Add optional link buttons from config (up to 3)."""
    from cogs.tickets import get_cached_config
    cfg = await get_cached_config(str(guild_id))
    for i in range(1, 4):
        label = cfg.get(f"{cfg_key_prefix}_{i}_label", "")
        url   = cfg.get(f"{cfg_key_prefix}_{i}_url",   "")
        if label and url and url.startswith("http"):
            view.add_item(discord.ui.Button(label=label, url=url, style=discord.ButtonStyle.link))


# ── Trade Ticket Modal ────────────────────────────────────────────────────────

class TradeTicketModal(discord.ui.Modal):
    def __init__(self, guild_id, cfg):
        modal_title = (cfg.get("ticket_panel_title") or "Trade Ticket")[:45]
        super().__init__(title=modal_title)
        self.guild_id = guild_id

        q1 = (cfg.get("trade_q1") or "What are you trading?")[:45]
        q2 = (cfg.get("trade_q2") or "Trade value (USD estimate)?")[:45]
        q3 = (cfg.get("trade_q3") or "Any additional info?")[:45]

        self.ans1 = discord.ui.TextInput(label=q1, style=discord.TextStyle.paragraph, max_length=400)
        self.ans2 = discord.ui.TextInput(label=q2, max_length=100)
        self.ans3 = discord.ui.TextInput(label=q3, style=discord.TextStyle.paragraph, required=False, max_length=400)
        self.add_item(self.ans1)
        self.add_item(self.ans2)
        self.add_item(self.ans3)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        bl = await asyncio.to_thread(db.is_blacklisted, str(interaction.user.id), str(interaction.guild_id))
        if bl:
            await interaction.followup.send("You are blacklisted from opening tickets.", ephemeral=True)
            return
        cog = interaction.client.get_cog("Tickets")
        if not cog:
            await interaction.followup.send("Ticket system unavailable.", ephemeral=True)
            return
        channel, err = await cog.open_ticket(interaction.guild, interaction.user, "trade")
        if err == "blacklisted":
            await interaction.followup.send("You are blacklisted from opening tickets.", ephemeral=True)
            return
        if not channel:
            await interaction.followup.send("Failed to create ticket.", ephemeral=True)
            return

        from cogs.tickets import get_cached_config, TicketButtons
        cfg = await get_cached_config(str(interaction.guild_id))
        q1  = cfg.get("trade_q1") or "What are you trading?"
        q2  = cfg.get("trade_q2") or "Trade value (USD estimate)?"
        q3  = cfg.get("trade_q3") or "Any additional info?"

        embed = discord.Embed(title="📋 Trade Details", color=discord.Color.green())
        embed.add_field(name="Opened by", value=interaction.user.mention, inline=True)
        embed.add_field(name="\u200b",    value="\u200b",                  inline=True)
        embed.add_field(name="\u200b",    value="\u200b",                  inline=True)
        embed.add_field(name=q1, value=self.ans1.value, inline=False)
        embed.add_field(name=q2, value=self.ans2.value, inline=False)
        if self.ans3.value:
            embed.add_field(name=q3, value=self.ans3.value, inline=False)
        embed.set_footer(text=f"Submitted by {interaction.user}")
        await channel.send(embed=embed, view=TicketButtons())
        await interaction.followup.send(f"✅ Your ticket has been created: {channel.mention}", ephemeral=True)


# ── Support Ticket Modal ──────────────────────────────────────────────────────

class SupportTicketModal(discord.ui.Modal):
    def __init__(self, guild_id, cfg):
        modal_title = (cfg.get("support_panel_title") or "Support Ticket")[:45]
        super().__init__(title=modal_title)
        self.guild_id = guild_id

        q1 = (cfg.get("support_q1") or "What would you like help with?")[:45]
        q2 = (cfg.get("support_q2") or "How urgent is this? (1-10)")[:45]

        self.ans1 = discord.ui.TextInput(label=q1, style=discord.TextStyle.paragraph, max_length=400)
        self.ans2 = discord.ui.TextInput(label=q2, max_length=50)
        self.add_item(self.ans1)
        self.add_item(self.ans2)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        bl = await asyncio.to_thread(db.is_blacklisted, str(interaction.user.id), str(interaction.guild_id))
        if bl:
            await interaction.followup.send("You are blacklisted from opening tickets.", ephemeral=True)
            return
        cog = interaction.client.get_cog("Tickets")
        if not cog:
            await interaction.followup.send("Ticket system unavailable.", ephemeral=True)
            return
        channel, err = await cog.open_ticket(interaction.guild, interaction.user, "support")
        if err == "blacklisted":
            await interaction.followup.send("You are blacklisted from opening tickets.", ephemeral=True)
            return
        if not channel:
            await interaction.followup.send("Failed to create ticket.", ephemeral=True)
            return

        from cogs.tickets import get_cached_config, TicketButtons
        cfg = await get_cached_config(str(interaction.guild_id))
        q1  = cfg.get("support_q1") or "What would you like help with?"
        q2  = cfg.get("support_q2") or "How urgent is this? (1-10)"

        embed = discord.Embed(title="🆘 Support Request", color=discord.Color.orange())
        embed.add_field(name="Opened by", value=interaction.user.mention, inline=True)
        embed.add_field(name="\u200b",    value="\u200b",                  inline=True)
        embed.add_field(name="\u200b",    value="\u200b",                  inline=True)
        embed.add_field(name=q1, value=self.ans1.value, inline=False)
        embed.add_field(name=q2, value=self.ans2.value, inline=False)
        embed.set_footer(text=f"Submitted by {interaction.user}")
        await channel.send(embed=embed, view=TicketButtons())
        await interaction.followup.send(f"✅ Your support ticket has been created: {channel.mention}", ephemeral=True)


# ── Auto MM Panel View (select directly in panel, no button required) ─────────

class AutoMMPanelView(discord.ui.View):
    """
    Persistent view with a service select menu embedded directly in the panel message.
    User picks a service → ticket creates immediately (no second step).
    Options are baked in at panel-post time via /autommpanel.
    For bot-restart persistence, we attach with a placeholder option — Discord
    stores the real options in the message so the callback still receives the
    correct value from interaction.data["values"].
    """
    def __init__(self, options: list = None, placeholder: str = "Select a service to open your ticket…"):
        super().__init__(timeout=None)
        select_options = [
            discord.SelectOption(label=opt[:100], value=opt[:100])
            for opt in (options or ["placeholder"])
        ]
        self._select = discord.ui.Select(
            placeholder=placeholder[:150],
            options=select_options,
            custom_id="automm_panel_select"
        )
        self._select.callback = self._on_select
        self.add_item(self._select)

    async def _on_select(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        bl = await asyncio.to_thread(db.is_blacklisted, str(interaction.user.id), str(interaction.guild_id))
        if bl:
            await interaction.followup.send(
                embed=discord.Embed(description="🚫 You are blacklisted from opening tickets.", color=discord.Color.red()),
                ephemeral=True
            )
            return

        selected    = interaction.data["values"][0]
        automm_cog  = interaction.client.get_cog("AutoMM")
        tickets_cog = interaction.client.get_cog("Tickets")

        if automm_cog:
            automm_cog._preselected_service[str(interaction.user.id)] = selected

        if not tickets_cog:
            await interaction.followup.send(
                embed=discord.Embed(description="❌ Ticket system unavailable.", color=discord.Color.red()),
                ephemeral=True
            )
            return

        channel, err = await tickets_cog.open_ticket(interaction.guild, interaction.user, "automm")
        if err == "blacklisted":
            await interaction.followup.send(
                embed=discord.Embed(description="🚫 You are blacklisted from opening tickets.", color=discord.Color.red()),
                ephemeral=True
            )
        elif channel:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="✅ Ticket Created",
                    description=f"Your **{selected}** ticket has been created: {channel.mention}",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                embed=discord.Embed(description="❌ Failed to create ticket. Please try again.", color=discord.Color.red()),
                ephemeral=True
            )


# ── Trade / Support panel views (persistent buttons) ─────────────────────────

class OpenTradeTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Trade Ticket", style=discord.ButtonStyle.green, custom_id="panel_open_trade", emoji="🎫")
    async def open_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets import get_cached_config
        cfg = await get_cached_config(str(interaction.guild_id))
        await interaction.response.send_modal(TradeTicketModal(interaction.guild_id, cfg))


class OpenSupportTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Support Ticket", style=discord.ButtonStyle.blurple, custom_id="panel_open_support", emoji="🆘")
    async def open_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets import get_cached_config
        cfg = await get_cached_config(str(interaction.guild_id))
        await interaction.response.send_modal(SupportTicketModal(interaction.guild_id, cfg))


# ── Panels Cog ────────────────────────────────────────────────────────────────

class Panels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(OpenTradeTicketView())
        self.bot.add_view(OpenSupportTicketView())
        # Persistent re-attach for AutoMM panel (placeholder options; real
        # options are stored in the Discord message component data)
        self.bot.add_view(AutoMMPanelView())

    async def _make_embed(self, guild_id, cfg_prefix, default_title, default_desc):
        from cogs.tickets import get_cached_config
        cfg    = await get_cached_config(str(guild_id))
        title  = cfg.get(f"{cfg_prefix}_title")  or default_title
        desc   = cfg.get(f"{cfg_prefix}_desc")   or default_desc
        footer = cfg.get(f"{cfg_prefix}_footer", "")
        image  = cfg.get(f"{cfg_prefix}_image",  "")
        embed  = discord.Embed(title=title, description=desc, color=discord.Color.blurple())
        if footer: embed.set_footer(text=footer)
        if image:  embed.set_image(url=image)
        return embed

    @app_commands.command(name="ticketpanel", description="Post the trade ticket panel")
    async def ticketpanel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only staff can post panels.", ephemeral=True)
            return
        embed = await self._make_embed(interaction.guild_id, "ticket_panel", "🎫 Trade Tickets", "Click below to open a trade ticket.")
        view  = OpenTradeTicketView()
        await _add_link_buttons(view, interaction.guild_id, "ticket_panel_button")
        await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send("✅ Trade ticket panel posted.", ephemeral=True)

    @app_commands.command(name="supportpanel", description="Post the support ticket panel")
    async def supportpanel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only staff can post panels.", ephemeral=True)
            return
        embed = await self._make_embed(interaction.guild_id, "support_panel", "🆘 Support Tickets", "Click below to open a support ticket.")
        view  = OpenSupportTicketView()
        await _add_link_buttons(view, interaction.guild_id, "support_panel_button")
        await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send("✅ Support ticket panel posted.", ephemeral=True)

    @app_commands.command(name="autommpanel", description="Post the Auto MM panel with service select")
    async def autommPanel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets import is_mm_or_admin
        if not await is_mm_or_admin(interaction.user):
            await interaction.followup.send("Only staff can post panels.", ephemeral=True)
            return
        from cogs.automm import _parse_dropdown_options
        from cogs.tickets import get_cached_config
        cfg         = await get_cached_config(str(interaction.guild_id))
        options     = await asyncio.to_thread(_parse_dropdown_options, str(interaction.guild_id))
        placeholder = cfg.get("automm_dropdown_label") or "Select a service to open your ticket…"
        embed       = await self._make_embed(
            interaction.guild_id, "automm_panel",
            "🤖 Auto Middleman",
            "Select your service from the dropdown below — your ticket will be created instantly."
        )
        view = AutoMMPanelView(options=options, placeholder=placeholder)
        await _add_link_buttons(view, interaction.guild_id, "automm_panel_button")
        await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send(
            "✅ Auto MM panel posted.\n\n"
            "⚠️ If you change service options via `$botedit`, re-run `/autommpanel` to update the dropdown.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Panels(bot))
