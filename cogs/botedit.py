import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import db


CATEGORIES = {
    "roles": {
        "label": "🛡️ Roles",
        "fields": [
            ("mm_role",    "MM Role ID"),
            ("admin_role", "Admin Role ID"),
            ("trade_role", "Trade Role ID"),
        ]
    },
    "channels": {
        "label": "📢 Channels",
        "fields": [
            ("log_channel",         "Log Channel ID"),
            ("staff_log_channel",   "Staff Log Channel ID"),
            ("transcript_channel",  "Transcript Channel ID"),
            ("automm_channel",      "Auto MM Channel ID"),
        ]
    },
    "categories": {
        "label": "🗂️ Categories",
        "fields": [
            ("ticket_category",  "Ticket Category ID"),
            ("support_category", "Support Ticket Category ID"),
            ("automm_category",  "Auto MM Ticket Category ID"),
        ]
    },
    "mercy": {
        "label": "💜 Mercy",
        "fields": [
            ("mercy_role",      "Mercy Role ID"),
            ("mercy_message",   "Mercy Message (shown in channel)"),
            ("mercy_dm_title",  "DM Title (sent to user on accept)"),
            ("mercy_dm_body",   "DM Body (sent to user on accept)"),
            ("mercy_dm_image",  "DM Image URL (optional)"),
        ]
    },
    "ticket_panel": {
        "label": "🎫 Ticket Panel",
        "fields": [
            ("ticket_panel_title",  "Title"),
            ("ticket_panel_desc",   "Description"),
            ("ticket_panel_footer", "Footer"),
            ("ticket_panel_image",  "Image URL"),
            ("ticket_panel_button", "Link Buttons (Label | URL, one per line)"),
        ]
    },
    "ticket_modal": {
        "label": "🎫 Ticket Modal Questions",
        "fields": [
            ("ticket_q1", "Q1 — Trade description question"),
            ("ticket_q2", "Q2 — Other user question"),
            ("ticket_q3", "Q3 — Private server question"),
        ]
    },
    "support_panel": {
        "label": "🆘 Support Panel",
        "fields": [
            ("support_panel_title",  "Title"),
            ("support_panel_desc",   "Description"),
            ("support_panel_footer", "Footer"),
            ("support_panel_image",  "Image URL"),
            ("support_panel_button", "Link Buttons (Label | URL, one per line)"),
        ]
    },
    "support_modal": {
        "label": "🆘 Support Modal Questions",
        "fields": [
            ("support_q1", "Q1 — Help request question"),
            ("support_q2", "Q2 — Urgency question"),
        ]
    },
    "automm_panel": {
        "label": "🤖 Auto MM Panel",
        "fields": [
            ("automm_panel_title",  "Title"),
            ("automm_panel_desc",   "Description"),
            ("automm_panel_footer", "Footer"),
            ("automm_panel_image",  "Image URL"),
            ("automm_panel_button", "Link Buttons (Label | URL, one per line)"),
        ]
    },
    "automm_options": {
        "label": "🤖 Auto MM Dropdown Options",
        "fields": [
            ("automm_dropdown_label",   "Dropdown question / label"),
            ("automm_dropdown_options", "Options (one per line or comma-separated)"),
        ]
    },
    "automm_settings": {
        "label": "🤖 Auto MM Settings",
        "fields": [
            ("automm_bank_name",       "Bank Name (e.g. G2G MARKETPLACE)"),
            ("automm_support_channel", "Support Channel ID for disputes"),
        ]
    },
    "boost": {
        "label": "🚀 Server Boost",
        "fields": [
            ("boost_channel", "Boost Channel ID"),
            ("boost_message", "Boost Message (use {user} for their mention)"),
            ("boost_image",   "Boost Image URL"),
        ]
    },
    "confirm": {
        "label": "✅ Confirm Embed",
        "fields": [
            ("confirm_title",  "Title"),
            ("confirm_desc",   "Description"),
            ("confirm_footer", "Footer"),
            ("confirm_image",  "Image URL"),
        ]
    },
    "fees": {
        "label": "💸 Fees Embed",
        "fields": [
            ("fees_title",  "Title"),
            ("fees_desc",   "Description"),
            ("fees_footer", "Footer"),
            ("fees_image",  "Image URL"),
        ]
    },
    "vouch": {
        "label": "⭐ Vouch Embed",
        "fields": [
            ("vouch_title",  "Title"),
            ("vouch_footer", "Footer"),
            ("vouch_image",  "Image URL"),
        ]
    },
    "deposits": {
        "label": "💰 Deposits",
        "fields": [
            ("deposit_log_channel", "Deposit Log Channel ID"),
        ]
    },
    "aboutus": {
        "label": "📖 About Us",
        "fields": [
            ("aboutus_message", "About Us Message"),
            ("aboutus_image",   "About Us Image URL"),
        ]
    },
}


class BotEditModal(discord.ui.Modal):
    def __init__(self, guild_id: str, category_key: str, current: dict):
        cat = CATEGORIES[category_key]
        super().__init__(title=f"Edit — {cat['label']}"[:45])
        self.guild_id     = guild_id
        self.category_key = category_key
        self.field_inputs = []

        for config_key, label in cat["fields"]:
            use_paragraph = (
                "message" in config_key
                or "desc"  in config_key
                or "options" in config_key
                or "body"  in config_key
                or "button" in config_key
            )
            inp = discord.ui.TextInput(
                label=label[:45],
                custom_id=config_key,
                required=False,
                default=current.get(config_key, ""),
                style=discord.TextStyle.paragraph if use_paragraph else discord.TextStyle.short,
                max_length=1000
            )
            self.add_item(inp)
            self.field_inputs.append((config_key, inp))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        for config_key, inp in self.field_inputs:
            await asyncio.to_thread(db.set_config, self.guild_id, config_key, inp.value)
        cat = CATEGORIES[self.category_key]
        await interaction.followup.send(
            f"✅ **{cat['label']}** settings updated successfully! Changes take effect immediately.",
            ephemeral=True
        )


class CategorySelect(discord.ui.Select):
    def __init__(self, guild_id: str):
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label=cat["label"], value=key, description=f"Edit {cat['label']} settings")
            for key, cat in CATEGORIES.items()
        ]
        super().__init__(placeholder="Choose a category to edit…", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        category_key = self.values[0]
        current = await asyncio.to_thread(db.get_all_config, self.guild_id)
        modal = BotEditModal(self.guild_id, category_key, current)
        await interaction.response.send_modal(modal)


class BotEditView(discord.ui.View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=120)
        self.add_item(CategorySelect(guild_id))


class BotEdit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="botedit", description="[Owner] Edit all bot settings from Discord")
    async def botedit(self, interaction: discord.Interaction):
        if interaction.user.id != 1461290677647179816:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚙️ Bot Configuration",
            description=(
                "Select a category below to edit its settings.\n"
                "All changes take effect **immediately** — no restart required.\n\n"
                + "\n".join(
                    f"**{cat['label']}** — {len(cat['fields'])} setting(s)"
                    for cat in CATEGORIES.values()
                )
            ),
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, view=BotEditView(str(interaction.guild_id)), ephemeral=True)


async def setup(bot):
    await bot.add_cog(BotEdit(bot))
