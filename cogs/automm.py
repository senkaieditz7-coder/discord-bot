import discord
from discord.ext import commands
from discord import app_commands
import db
import asyncio

PAYMENT_METHODS = ["LTC", "BTC", "PayPal", "SOL", "CashApp", "Apple Pay", "Venmo", "Zelle", "ETH", "USDT"]

METHOD_EMOJIS = {
    "LTC": "🪙", "BTC": "₿", "PayPal": "💳", "SOL": "◎",
    "CashApp": "💚", "Apple Pay": "🍎", "Venmo": "💜",
    "Zelle": "🟡", "ETH": "💎", "USDT": "💵",
}


def get_bank_name(guild_id):
    return db.get_config(str(guild_id), "automm_bank_name") or "G2G MARKETPLACE"


def get_support_channel_mention(guild, guild_id):
    ch_id = db.get_config(str(guild_id), "automm_support_channel")
    if ch_id and ch_id.isdigit():
        ch = guild.get_channel(int(ch_id))
        if ch:
            return ch.mention
    return "#support"


def _parse_dropdown_options(guild_id):
    """Return list of option strings from config, with sane defaults."""
    raw = db.get_config(str(guild_id), "automm_dropdown_options") or ""
    if "\n" in raw:
        opts = [o.strip() for o in raw.splitlines() if o.strip()]
    else:
        opts = [o.strip() for o in raw.split(",") if o.strip()]
    if not opts:
        opts = ["Gold Trading", "Account Services", "Boosting", "Item Trading", "Other"]
    return opts[:25]


# ── Auto MM Dropdown View ─────────────────────────────────────────────────────

class AutoMMDropdownView(discord.ui.View):
    def __init__(self, channel_id: str, opener: discord.Member, options: list):
        super().__init__(timeout=300)
        self.channel_id = channel_id
        self.opener = opener

        select_options = [
            discord.SelectOption(label=opt[:100], value=opt[:100])
            for opt in options
        ]
        select = discord.ui.Select(
            placeholder="Select an option…",
            options=select_options,
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.opener.id:
            await interaction.response.send_message(
                "Only the ticket opener can make this selection.", ephemeral=True
            )
            return

        selected = interaction.data["values"][0]
        self.stop()

        bank = await asyncio.to_thread(get_bank_name, interaction.guild_id)
        embed = discord.Embed(
            title="✅ Service Selected",
            description=f"**{self.opener.mention}** selected: **{selected}**",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Auto Middleman — {bank}")
        await interaction.response.edit_message(embed=embed, view=None)

        mm_role_id = await asyncio.to_thread(db.get_config, str(interaction.guild_id), "mm_role")
        ping = f"<@&{mm_role_id}>" if mm_role_id else "@MM Staff"
        await interaction.channel.send(
            f"{ping} — {self.opener.mention} opened an Auto MM ticket and selected **{selected}**"
        )

        cog = interaction.client.get_cog("AutoMM")
        if cog:
            await asyncio.to_thread(db.update_automm_session, self.channel_id, state="waiting_user2")
            cog._waiting_for_user2.add(self.channel_id)

            cfg    = await asyncio.to_thread(db.get_all_config, str(interaction.guild_id))
            title  = cfg.get("automm_panel_title") or "🤖 Auto Middleman"
            footer = cfg.get("automm_panel_footer", "")

            embed2 = discord.Embed(
                title=title,
                description=(
                    f"Welcome, {self.opener.mention}!\n\n"
                    "**Step 1:** Please **mention** the other trader or type their **user ID** below."
                ),
                color=discord.Color.blurple()
            )
            if footer:
                embed2.set_footer(text=footer)
            await interaction.channel.send(embed=embed2)


# ── Role Selection View ───────────────────────────────────────────────────────

class RoleSelectView(discord.ui.View):
    def __init__(self, channel_id: str, user1: discord.Member, user2: discord.Member):
        super().__init__(timeout=300)
        self.channel_id = channel_id
        self.user1 = user1
        self.user2 = user2
        self._selections = {}

    def _make_status_embed(self, bank_name: str) -> discord.Embed:
        lines = []
        for uid in [str(self.user1.id), str(self.user2.id)]:
            member = self.user1 if uid == str(self.user1.id) else self.user2
            role = self._selections.get(uid)
            if role == "sender":
                lines.append(f"💸 {member.mention} — **Money Sender**")
            elif role == "receiver":
                lines.append(f"📥 {member.mention} — **Money Receiver**")
            else:
                lines.append(f"⏳ {member.mention} — *Choosing…*")

        return discord.Embed(
            title=f"🤖 Auto Middleman — {bank_name}",
            description=(
                "**Each trader: press your role below.**\n"
                "Use 🔄 Reset if you made a mistake.\n\n"
                + "\n".join(lines)
            ),
            color=discord.Color.blurple()
        )

    async def _try_advance(self, interaction: discord.Interaction) -> bool:
        uid = str(interaction.user.id)
        if uid not in [str(self.user1.id), str(self.user2.id)]:
            await interaction.response.send_message("You are not part of this trade.", ephemeral=True)
            return False

        if len(self._selections) == 2:
            roles = list(self._selections.values())
            if roles.count("sender") == 1 and roles.count("receiver") == 1:
                sender_id   = next(k for k, v in self._selections.items() if v == "sender")
                receiver_id = next(k for k, v in self._selections.items() if v == "receiver")
                await asyncio.to_thread(
                    db.update_automm_session, self.channel_id,
                    sender_id=sender_id, receiver_id=receiver_id, state="waiting_method"
                )
                self.stop()
                await self._show_method_select(interaction)
                return True
        return False

    async def _show_method_select(self, interaction: discord.Interaction):
        session  = await asyncio.to_thread(db.get_automm_session, self.channel_id)
        sender   = interaction.guild.get_member(int(session["sender_id"]))
        receiver = interaction.guild.get_member(int(session["receiver_id"]))
        bank     = await asyncio.to_thread(get_bank_name, interaction.guild_id)

        embed = discord.Embed(
            title=f"💳 Select Payment Method — {bank}",
            description=(
                f"💸 **Sender:** {sender.mention}\n"
                f"📥 **Receiver:** {receiver.mention}\n\n"
                "Select the payment method for this trade:"
            ),
            color=discord.Color.gold()
        )
        view = MethodSelectView(self.channel_id, sender, receiver)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="I am Money Sender", style=discord.ButtonStyle.green, emoji="💸", row=0)
    async def be_sender(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        if uid not in [str(self.user1.id), str(self.user2.id)]:
            await interaction.response.send_message("You are not part of this trade.", ephemeral=True)
            return
        other = str(self.user2.id) if uid == str(self.user1.id) else str(self.user1.id)
        if self._selections.get(other) == "sender":
            await interaction.response.send_message(
                "The other trader already chose Sender. Please choose Receiver.", ephemeral=True
            )
            return
        self._selections[uid] = "sender"
        if await self._try_advance(interaction):
            return
        bank_name = await asyncio.to_thread(get_bank_name, interaction.guild_id)
        embed = self._make_status_embed(bank_name)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="I am Money Receiver", style=discord.ButtonStyle.blurple, emoji="📥", row=0)
    async def be_receiver(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        if uid not in [str(self.user1.id), str(self.user2.id)]:
            await interaction.response.send_message("You are not part of this trade.", ephemeral=True)
            return
        other = str(self.user2.id) if uid == str(self.user1.id) else str(self.user1.id)
        if self._selections.get(other) == "receiver":
            await interaction.response.send_message(
                "The other trader already chose Receiver. Please choose Sender.", ephemeral=True
            )
            return
        self._selections[uid] = "receiver"
        if await self._try_advance(interaction):
            return
        bank_name = await asyncio.to_thread(get_bank_name, interaction.guild_id)
        embed = self._make_status_embed(bank_name)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.red, emoji="🔄", row=1)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        if uid not in [str(self.user1.id), str(self.user2.id)]:
            await interaction.response.send_message("You are not part of this trade.", ephemeral=True)
            return
        self._selections.clear()
        await asyncio.to_thread(db.update_automm_session, self.channel_id, sender_id=None, receiver_id=None)
        bank_name = await asyncio.to_thread(get_bank_name, interaction.guild_id)
        embed = self._make_status_embed(bank_name)
        await interaction.response.edit_message(embed=embed, view=self)


# ── Payment Method Select View ────────────────────────────────────────────────

class MethodSelectView(discord.ui.View):
    def __init__(self, channel_id: str, sender: discord.Member, receiver: discord.Member):
        super().__init__(timeout=300)
        self.channel_id = channel_id
        self.sender = sender
        self.receiver = receiver

        options = [
            discord.SelectOption(label=m, value=m, emoji=METHOD_EMOJIS.get(m, "💰"))
            for m in PAYMENT_METHODS
        ]
        select = discord.ui.Select(
            placeholder="Choose payment method…",
            options=options,
            custom_id=f"automm_method_{channel_id}"
        )
        select.callback = self._method_chosen
        self.add_item(select)

    async def _method_chosen(self, interaction: discord.Interaction):
        uid     = str(interaction.user.id)
        session = await asyncio.to_thread(db.get_automm_session, self.channel_id)
        if not session:
            await interaction.response.send_message("Session expired.", ephemeral=True)
            return
        if uid not in [session["user1_id"], session["user2_id"]]:
            await interaction.response.send_message("You are not part of this trade.", ephemeral=True)
            return

        method = interaction.data["values"][0]
        await asyncio.to_thread(db.update_automm_session, self.channel_id, payment_method=method, state="waiting_done")
        self.stop()

        emoji = METHOD_EMOJIS.get(method, "💰")
        bank  = await asyncio.to_thread(get_bank_name, interaction.guild_id)

        embed = discord.Embed(
            title=f"{emoji} Payment Method: {method}",
            description=(
                f"💸 **Sender:** {self.sender.mention}\n"
                f"📥 **Receiver:** {self.receiver.mention}\n"
                f"💳 **Method:** {method}\n\n"
                "✅ **Both traders: when you are ready to proceed, type `done` in this channel.**"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Auto Middleman — {bank}")
        await interaction.response.edit_message(embed=embed, view=None)


# ── DM Confirmation View ──────────────────────────────────────────────────────

class DMConfirmView(discord.ui.View):
    def __init__(self, channel_id: str, guild_id: int, ticket_channel: discord.TextChannel):
        super().__init__(timeout=600)
        self.channel_id     = channel_id
        self.guild_id       = guild_id
        self.ticket_channel = ticket_channel

    @discord.ui.button(label="✅ Confirm — Money Sent", style=discord.ButtonStyle.green)
    async def confirm_sent(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = await asyncio.to_thread(db.get_automm_session, self.channel_id)
        if not session or session["state"] != "waiting_automm":
            await interaction.response.send_message("This session is no longer active.", ephemeral=True)
            self.stop()
            return

        await asyncio.to_thread(db.update_automm_session, self.channel_id, state="waiting_trade_done")
        self.stop()

        guild           = interaction.client.get_guild(self.guild_id)
        bank            = await asyncio.to_thread(get_bank_name, self.guild_id)
        support_mention = await asyncio.to_thread(get_support_channel_mention, guild, self.guild_id)

        embed = discord.Embed(
            title="✅ Money Received by Bank",
            description=(
                f"**Money has been sent to {bank} bank successfully.**\n\n"
                f"📥 Money receiver — please give the item/service to the money sender now.\n\n"
                f"When **both traders** type `.done` in this ticket, the money will be released to the receiver's bank.\n\n"
                f"⚠️ If the receiver does **not** deliver the item/service, please open a support ticket in {support_mention}."
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Auto Middleman — {bank}")

        try:
            await self.ticket_channel.send(embed=embed)
        except Exception:
            pass

        await interaction.response.edit_message(
            content="✅ Confirmed! The ticket has been updated.",
            view=None
        )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled. Type `.automm` again when ready.", view=None)
        self.stop()


# ── Auto MM Cog ───────────────────────────────────────────────────────────────

class AutoMM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._waiting_for_user2: set = set()
        self._preselected_service: dict = {}

    async def _start_session(self, channel: discord.TextChannel, guild: discord.Guild, opener: discord.Member):
        service = self._preselected_service.pop(str(opener.id), None)

        await asyncio.to_thread(db.create_automm_session, str(channel.id), str(guild.id), str(opener.id))

        cfg    = await asyncio.to_thread(db.get_all_config, str(guild.id))
        title  = cfg.get("automm_panel_title") or "🤖 Auto Middleman"
        footer = cfg.get("automm_panel_footer", "")
        image  = cfg.get("automm_panel_image",  "")

        if service:
            await asyncio.to_thread(db.update_automm_session, str(channel.id), state="waiting_user2")
            self._waiting_for_user2.add(str(channel.id))

            mm_role_id = await asyncio.to_thread(db.get_config, str(guild.id), "mm_role")
            ping       = f"<@&{mm_role_id}>" if mm_role_id else "@MM Staff"
            bank       = await asyncio.to_thread(get_bank_name, guild.id)
            await channel.send(
                f"{ping} — {opener.mention} opened an Auto MM ticket for **{service}**"
            )

            embed = discord.Embed(
                title=title,
                description=(
                    f"✅ **Service:** {service}\n\n"
                    f"Welcome, {opener.mention}!\n\n"
                    "**Step 1:** Please **mention** the other trader or type their **user ID** below."
                ),
                color=discord.Color.blurple()
            )
            if footer: embed.set_footer(text=footer)
            if image:  embed.set_image(url=image)
            await channel.send(embed=embed)
        else:
            await asyncio.to_thread(db.update_automm_session, str(channel.id), state="waiting_dropdown")
            dropdown_label = cfg.get("automm_dropdown_label") or "What service do you need?"
            options        = await asyncio.to_thread(_parse_dropdown_options, str(guild.id))

            embed = discord.Embed(
                title=title,
                description=(
                    f"Welcome, {opener.mention}!\n\n"
                    f"**{dropdown_label}**\n"
                    "Please select an option below to continue."
                ),
                color=discord.Color.blurple()
            )
            if footer: embed.set_footer(text=footer)
            if image:  embed.set_image(url=image)

            view = AutoMMDropdownView(str(channel.id), opener, options)
            await channel.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return

        channel_id = str(message.channel.id)
        content    = message.content.strip()

        # ── .automm ───────────────────────────────────────────────────────────
        if content.lower() == ".automm":
            session = await asyncio.to_thread(
                db.get_automm_session_by_sender, str(message.guild.id), str(message.author.id)
            )
            if not session:
                return
            try:
                await message.delete()
            except Exception:
                pass

            ticket_channel = message.guild.get_channel(int(session["channel_id"]))
            if not ticket_channel:
                return

            bank = await asyncio.to_thread(get_bank_name, message.guild.id)
            embed = discord.Embed(
                title=f"💸 Confirm Payment — {bank}",
                description=(
                    f"You indicated that you have sent your **{session['payment_method']}** payment.\n\n"
                    "Click **Confirm** to notify the ticket that money has been received by the bank."
                ),
                color=discord.Color.gold()
            )
            view = DMConfirmView(session["channel_id"], message.guild.id, ticket_channel)
            try:
                await message.author.send(embed=embed, view=view)
                await message.channel.send(
                    f"{message.author.mention} Check your DMs to confirm your payment! 📩",
                    delete_after=10
                )
            except discord.Forbidden:
                await message.channel.send(
                    f"{message.author.mention} I couldn't DM you. Please enable DMs from server members and try again.",
                    delete_after=15
                )
            return

        # ── .done ─────────────────────────────────────────────────────────────
        if content.lower() == ".done":
            session = await asyncio.to_thread(db.get_automm_session, channel_id)
            if not session or session["state"] != "waiting_trade_done":
                return

            uid = str(message.author.id)
            if uid not in [session["user1_id"], session["user2_id"]]:
                return

            field = "trade_done_1" if uid == session["user1_id"] else "trade_done_2"
            await asyncio.to_thread(db.update_automm_session, channel_id, **{field: 1})
            session = await asyncio.to_thread(db.get_automm_session, channel_id)

            await message.channel.send(f"✅ {message.author.mention} marked as done.")

            if session["trade_done_1"] and session["trade_done_2"]:
                await asyncio.to_thread(db.update_automm_session, channel_id, state="complete")
                bank     = await asyncio.to_thread(get_bank_name, message.guild.id)
                receiver = message.guild.get_member(int(session["receiver_id"]))

                embed = discord.Embed(
                    title="🎉 Trade Complete!",
                    description=(
                        f"**Money has been released to {receiver.mention if receiver else 'the receiver'}'s bank.**\n\n"
                        f"Thank you for using **{bank}** Auto Middleman!\n"
                        "Both traders: you may now leave this ticket."
                    ),
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Auto Middleman — {bank}")
                await message.channel.send(embed=embed)
            return

        # ── "done" (step 4: both ready to proceed) ────────────────────────────
        if content.lower() == "done":
            session = await asyncio.to_thread(db.get_automm_session, channel_id)
            if not session or session["state"] != "waiting_done":
                return

            uid = str(message.author.id)
            if uid not in [session["user1_id"], session["user2_id"]]:
                return

            field = "user1_ready" if uid == session["user1_id"] else "user2_ready"
            await asyncio.to_thread(db.update_automm_session, channel_id, **{field: 1})
            session = await asyncio.to_thread(db.get_automm_session, channel_id)

            await message.add_reaction("✅")

            if session["user1_ready"] and session["user2_ready"]:
                await asyncio.to_thread(db.update_automm_session, channel_id, state="waiting_automm")
                sender   = message.guild.get_member(int(session["sender_id"]))
                receiver = message.guild.get_member(int(session["receiver_id"]))
                method   = session["payment_method"]
                bank     = await asyncio.to_thread(get_bank_name, message.guild.id)

                embed = discord.Embed(
                    title="💸 Ready to Proceed",
                    description=(
                        f"Both traders are ready!\n\n"
                        f"**{sender.mention if sender else 'Money Sender'}** — please send your **{method}** payment "
                        f"to **{receiver.mention if receiver else 'Money Receiver'}** now.\n\n"
                        f"Once you have sent the payment, type **`.automm`** in **any channel** in this server.\n"
                        f"The bot will DM you to confirm."
                    ),
                    color=discord.Color.gold()
                )
                embed.set_footer(text=f"Auto Middleman — {bank}")
                await message.channel.send(embed=embed)
            return

        # ── Waiting for User 2 ────────────────────────────────────────────────
        if channel_id not in self._waiting_for_user2:
            return

        session = await asyncio.to_thread(db.get_automm_session, channel_id)
        if not session or session["state"] != "waiting_user2":
            self._waiting_for_user2.discard(channel_id)
            return

        if str(message.author.id) != session["user1_id"]:
            return

        target_member = None
        if message.mentions:
            target_member = message.mentions[0]
        else:
            raw = content.strip().strip("<@!>")
            if raw.isdigit():
                target_member = message.guild.get_member(int(raw))

        if not target_member:
            await message.channel.send(
                f"{message.author.mention} ❌ I couldn't find that user. Please **@mention** them or paste their **user ID**.",
                delete_after=10
            )
            return

        if target_member.bot:
            await message.channel.send(f"{message.author.mention} ❌ You cannot trade with a bot.", delete_after=8)
            return

        if target_member.id == message.author.id:
            await message.channel.send(f"{message.author.mention} ❌ You cannot trade with yourself.", delete_after=8)
            return

        self._waiting_for_user2.discard(channel_id)
        await asyncio.to_thread(db.update_automm_session, channel_id, user2_id=str(target_member.id), state="waiting_roles")

        await message.channel.set_permissions(target_member, read_messages=True, send_messages=True)
        await asyncio.to_thread(db.add_ticket_user, channel_id, str(target_member.id))

        user1     = message.guild.get_member(int(session["user1_id"]))
        bank      = await asyncio.to_thread(get_bank_name, message.guild.id)

        embed = discord.Embed(
            title="👥 Traders Confirmed",
            description=(
                f"✅ {target_member.mention} has been added to the ticket!\n\n"
                f"**{user1.mention if user1 else '<User 1>'}** and **{target_member.mention}** — "
                "please select your roles below:"
            ),
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Auto Middleman — {bank}")
        view = RoleSelectView(channel_id, user1 or message.author, target_member)
        await message.channel.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_ticket_opened(self, channel: discord.TextChannel, guild: discord.Guild, opener: discord.Member):
        ticket = await asyncio.to_thread(db.get_ticket, str(channel.id))
        if ticket and ticket.get("ticket_type") == "automm":
            await self._start_session(channel, guild, opener)


async def setup(bot):
    await bot.add_cog(AutoMM(bot))
