import discord
from discord.ext import commands
from discord import app_commands
import db


def _parse_link_buttons(raw: str) -> list:
    """Parse one or more 'Label | URL' lines into a list of (label, url) tuples."""
    buttons = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|", 1)
        label = parts[0].strip()[:80]
        url   = parts[1].strip()
        if label and url.startswith("http"):
            buttons.append((label, url))
    return buttons[:4]


def _add_link_buttons(view: discord.ui.View, guild_id, btn_key):
    """Attach up to 4 link buttons to a view from config (row 1)."""
    cfg = db.get_all_config(str(guild_id))
    buttons = _parse_link_buttons(cfg.get(btn_key, ""))
    for label, url in buttons:
        view.add_item(discord.ui.Button(
            style=discord.ButtonStyle.link,
            label=label,
            url=url,
            row=1
        ))
    return view


# ── Trade ticket modal ────────────────────────────────────────────────────────

class TradeTicketModal(discord.ui.Modal):
    def __init__(self, guild_id):
        cfg = db.get_all_config(str(guild_id))
        modal_title = (cfg.get("ticket_panel_title") or "Trade Ticket")[:45]
        super().__init__(title=modal_title)
        self.guild_id = guild_id

        q1 = (cfg.get("ticket_q1") or "What is the trade?")[:45]
        q2 = (cfg.get("ticket_q2") or "Other user (ID, @mention, or username)")[:45]
        q3 = (cfg.get("ticket_q3") or "Can you join private servers using links?")[:45]

        self.ans1 = discord.ui.TextInput(label=q1, style=discord.TextStyle.paragraph, max_length=500)
        self.ans2 = discord.ui.TextInput(label=q2, max_length=200)
        self.ans3 = discord.ui.TextInput(label=q3, max_length=100)
        self.add_item(self.ans1)
        self.add_item(self.ans2)
        self.add_item(self.ans3)

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Tickets")
        if not cog:
            await interaction.response.send_message("Ticket system unavailable.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        channel, err = await cog.open_ticket(interaction.guild, interaction.user, "trade")

        if err == "blacklisted":
            await interaction.followup.send("You are blacklisted from opening tickets.", ephemeral=True)
            return
        if not channel:
            await interaction.followup.send("Failed to create ticket.", ephemeral=True)
            return

        cfg = db.get_all_config(str(interaction.guild_id))
        q1 = cfg.get("ticket_q1") or "What is the trade?"
        q2 = cfg.get("ticket_q2") or "Other user (ID, @mention, or username)"
        q3 = cfg.get("ticket_q3") or "Can you join private servers using links?"

        embed = discord.Embed(title="📋 Trade Details", color=discord.Color.green())
        embed.add_field(name=q1, value=self.ans1.value, inline=False)
        embed.add_field(name=q2, value=self.ans2.value, inline=False)
        embed.add_field(name=q3, value=self.ans3.value, inline=False)
        embed.set_footer(text=f"Submitted by {interaction.user}")
        await channel.send(embed=embed)

        await interaction.followup.send(
            f"✅ Your ticket has been created: {channel.mention}", ephemeral=True
        )


# ── Support ticket modal ──────────────────────────────────────────────────────

class SupportTicketModal(discord.ui.Modal):
    def __init__(self, guild_id):
        cfg = db.get_all_config(str(guild_id))
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
        cog = interaction.client.get_cog("Tickets")
        if not cog:
            await interaction.response.send_message("Ticket system unavailable.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        channel, err = await cog.open_ticket(interaction.guild, interaction.user, "support")

        if err == "blacklisted":
            await interaction.followup.send("You are blacklisted from opening tickets.", ephemeral=True)
            return
        if not channel:
            await interaction.followup.send("Failed to create ticket.", ephemeral=True)
            return

        cfg = db.get_all_config(str(interaction.guild_id))
        q1 = cfg.get("support_q1") or "What would you like help with?"
        q2 = cfg.get("support_q2") or "How urgent is this? (1-10)"

        embed = discord.Embed(title="🆘 Support Request Details", color=discord.Color.orange())
        embed.add_field(name=q1, value=self.ans1.value, inline=False)
        embed.add_field(name=q2, value=self.ans2.value, inline=False)
        embed.set_footer(text=f"Submitted by {interaction.user}")
        await channel.send(embed=embed)

        await interaction.followup.send(
            f"✅ Your support ticket has been created: {channel.mention}", ephemeral=True
        )


# ── Auto MM — panel-level service select (ephemeral, before ticket creation) ──

class PanelServiceSelectView(discord.ui.View):
    """Shown ephemerally in the panel channel so the user picks a service
    before the Auto MM ticket is created."""

    def __init__(self, opener: discord.Member, guild_id: str, options: list):
        super().__init__(timeout=120)
        self.opener   = opener
        self.guild_id = guild_id

        select_options = [
            discord.SelectOption(label=opt[:100], value=opt[:100])
            for opt in options
        ]
        select = discord.ui.Select(
            placeholder="Choose a service…",
            options=select_options,
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.opener.id:
            await interaction.response.send_message(
                "Only you can select a service for your own ticket.", ephemeral=True
            )
            return

        selected = interaction.data["values"][0]

        # Register the pre-selection so _start_session skips the in-ticket dropdown
        automm_cog = interaction.client.get_cog("AutoMM")
        if automm_cog:
            automm_cog._preselected_service[str(interaction.user.id)] = selected

        tickets_cog = interaction.client.get_cog("Tickets")
        if not tickets_cog:
            await interaction.response.edit_message(
                content="Ticket system unavailable.", embed=None, view=None
            )
            return

        await interaction.response.edit_message(
            content="⏳ Creating your ticket…", embed=None, view=None
        )

        channel, err = await tickets_cog.open_ticket(interaction.guild, interaction.user, "automm")

        if err == "blacklisted":
            await interaction.edit_original_response(
                content="You are blacklisted from opening tickets."
            )
        elif channel:
            await interaction.edit_original_response(
                content=f"✅ Your Auto MM ticket has been created: {channel.mention}"
            )
        else:
            await interaction.edit_original_response(content="Failed to create ticket.")


# ── Persistent panel views ────────────────────────────────────────────────────

class OpenTradeTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Trade Ticket", style=discord.ButtonStyle.green, custom_id="panel_open_trade", emoji="🎫")
    async def open_trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if db.is_blacklisted(str(interaction.user.id), str(interaction.guild_id)):
            await interaction.response.send_message("You are blacklisted from opening tickets.", ephemeral=True)
            return
        await interaction.response.send_modal(TradeTicketModal(interaction.guild_id))


class OpenSupportTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Support Ticket", style=discord.ButtonStyle.blurple, custom_id="panel_open_support", emoji="🆘")
    async def open_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        if db.is_blacklisted(str(interaction.user.id), str(interaction.guild_id)):
            await interaction.response.send_message("You are blacklisted from opening tickets.", ephemeral=True)
            return
        await interaction.response.send_modal(SupportTicketModal(interaction.guild_id))


class AutoMMView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Auto-MM", style=discord.ButtonStyle.green, custom_id="panel_open_automm", emoji="🤖")
    async def open_automm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if db.is_blacklisted(str(interaction.user.id), str(interaction.guild_id)):
            await interaction.response.send_message("You are blacklisted from opening tickets.", ephemeral=True)
            return

        # Lazy import to avoid circular dependency
        from cogs.automm import _parse_dropdown_options

        cfg           = db.get_all_config(str(interaction.guild_id))
        dropdown_label = cfg.get("automm_dropdown_label") or "What service do you need?"
        options        = _parse_dropdown_options(str(interaction.guild_id))

        embed = discord.Embed(
            title="🤖 Auto Middleman",
            description=f"**{dropdown_label}**\nSelect a service below to open your ticket.",
            color=discord.Color.blurple()
        )
        view = PanelServiceSelectView(interaction.user, str(interaction.guild_id), options)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ── Panels cog ────────────────────────────────────────────────────────────────

class Panels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(OpenTradeTicketView())
        self.bot.add_view(OpenSupportTicketView())
        self.bot.add_view(AutoMMView())

    def _make_embed(self, guild_id, cfg_prefix, default_title, default_desc):
        cfg    = db.get_all_config(str(guild_id))
        title  = cfg.get(f"{cfg_prefix}_title")  or default_title
        desc   = cfg.get(f"{cfg_prefix}_desc")   or default_desc
        footer = cfg.get(f"{cfg_prefix}_footer", "")
        image  = cfg.get(f"{cfg_prefix}_image",  "")
        embed  = discord.Embed(title=title, description=desc, color=discord.Color.blurple())
        if footer:
            embed.set_footer(text=footer)
        if image:
            embed.set_image(url=image)
        return embed

    @app_commands.command(name="ticketpanel", description="Post the trade ticket panel")
    async def ticketpanel(self, interaction: discord.Interaction):
        from cogs.tickets import is_mm_or_admin
        if not is_mm_or_admin(interaction.user):
            await interaction.response.send_message("Only staff can post panels.", ephemeral=True)
            return
        embed = self._make_embed(interaction.guild_id, "ticket_panel", "🎫 Trade Tickets", "Click below to open a trade ticket.")
        view  = OpenTradeTicketView()
        _add_link_buttons(view, interaction.guild_id, "ticket_panel_button")
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Trade ticket panel posted.", ephemeral=True)

    @app_commands.command(name="supportpanel", description="Post the support ticket panel")
    async def supportpanel(self, interaction: discord.Interaction):
        from cogs.tickets import is_mm_or_admin
        if not is_mm_or_admin(interaction.user):
            await interaction.response.send_message("Only staff can post panels.", ephemeral=True)
            return
        embed = self._make_embed(interaction.guild_id, "support_panel", "🆘 Support Tickets", "Click below to open a support ticket.")
        view  = OpenSupportTicketView()
        _add_link_buttons(view, interaction.guild_id, "support_panel_button")
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Support ticket panel posted.", ephemeral=True)

    @app_commands.command(name="autommpanel", description="Post the Auto MM panel")
    async def autommPanel(self, interaction: discord.Interaction):
        from cogs.tickets import is_mm_or_admin
        if not is_mm_or_admin(interaction.user):
            await interaction.response.send_message("Only staff can post panels.", ephemeral=True)
            return
        embed = self._make_embed(interaction.guild_id, "automm_panel", "🤖 Auto Middleman", "Click below to request an automatic middleman.")
        view  = AutoMMView()
        _add_link_buttons(view, interaction.guild_id, "automm_panel_button")
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Auto MM panel posted.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Panels(bot))
