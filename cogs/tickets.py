import os
import asyncio
import disnake
from disnake.ext import commands
from database import db

# Импортируем ReviewModal для кнопки отзыва в ЛС
try:
    from cogs.reviews import ReviewModal
except ImportError:
    ReviewModal = None  # Если reviews загружен позже

# ID ролей для пинга при создании тикета
ORDER_PING_ROLE_IDS = [int(r.strip()) for r in os.getenv("ORDER_PING_ROLE_IDS", "").split(",") if r.strip()]
# ID категории где создавать тикеты
TICKETS_CATEGORY_ID = int(os.getenv("TICKETS_CATEGORY_ID", 0))
# ID роли администраторов
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", 0))


class TicketOrderModal(disnake.ui.Modal):
    """Модальное окно для создания заказа (тикета)"""
    
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Описание заказа",
                placeholder="Подробно опишите что вам нужно сделать...",
                custom_id="ticket_description",
                style=disnake.TextInputStyle.paragraph,
                min_length=10,
                max_length=2000,
                required=True
            ),
            disnake.ui.TextInput(
                label="Бюджет",
                placeholder="Пример: 1000₽, 50$, договорная",
                custom_id="ticket_budget",
                style=disnake.TextInputStyle.short,
                min_length=1,
                max_length=50,
                required=False
            ),
            disnake.ui.TextInput(
                label="Сроки",
                placeholder="Пример: Сегодня, через 3 дня, неделя",
                custom_id="ticket_deadline",
                style=disnake.TextInputStyle.short,
                min_length=1,
                max_length=50,
                required=False
            )
        ]
        super().__init__(title="🎫 Создание заказа", components=components, custom_id="ticket_order_modal")
    
    async def callback(self, inter: disnake.ModalInteraction):
        """Создание тикета при отправке модального окна"""
        # Сразу отвечаем что обрабатываем (чтобы не было таймаута)
        await inter.response.defer(ephemeral=True)
        
        description = inter.text_values["ticket_description"]
        budget = inter.text_values.get("ticket_budget", "Не указан")
        deadline = inter.text_values.get("ticket_deadline", "Не указаны")
        
        # Сохраняем в БД
        order_id = await db.create_order(
            user_id=inter.user.id,
            username=str(inter.user),
            description=description,
            budget=budget,
            deadline=deadline
        )
        
        await inter.edit_original_response(
            f"✅ Заказ #{order_id} создан! Создаю канал для обсуждения..."
        )
        
        # Создаем канал
        try:
            guild = inter.guild
            category = guild.get_channel(TICKETS_CATEGORY_ID) if TICKETS_CATEGORY_ID else None
            
            # Права для канала
            overwrites = {
                guild.default_role: disnake.PermissionOverwrite(view_channel=False),
                inter.user: disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                guild.me: disnake.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
            }
            
            # Добавляем права для админов
            if ADMIN_ROLE_ID:
                admin_role = guild.get_role(ADMIN_ROLE_ID)
                if admin_role:
                    overwrites[admin_role] = disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            
            channel_name = f"заказ-{order_id}-{inter.user.name[:15]}"
            
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Заказ #{order_id} от {inter.user}"
            )
            
            # Сохраняем ID канала
            await db.update_order_ticket(order_id, channel_id=channel.id, status="pending")
            
            # Создаем embed с заказом
            embed = disnake.Embed(
                title=f"📦 Заказ #{order_id}",
                description=description,
                color=0x2f3136,
                timestamp=disnake.utils.utcnow()
            )
            embed.add_field(name="👤 Заказчик", value=inter.user.mention, inline=True)
            embed.add_field(name="💰 Бюджет", value=budget, inline=True)
            embed.add_field(name="⏰ Сроки", value=deadline, inline=True)
            embed.set_thumbnail(url=inter.user.display_avatar.url)
            
            # Создаем кнопки принять/отклонить
            view = AcceptRejectView(order_id, inter.user.id)
            
            # Формируем пинг ролей
            ping_message = " ".join([f"<@&{r}>" for r in ORDER_PING_ROLE_IDS]) if ORDER_PING_ROLE_IDS else ""
            
            message = await channel.send(
                content=ping_message,
                embed=embed,
                view=view
            )
            
            await db.update_order_message_id(order_id, message.id)
            
            # Пиним сообщение
            await message.pin()
            
            # Сообщаем пользователю ссылку
            await inter.edit_original_response(
                f"✅ Канал создан: {channel.mention}\nОжидайте, пока администратор примет ваш заказ."
            )
            
        except Exception as e:
            print(f"Ошибка создания канала: {e}")
            await inter.edit_original_response(
                f"❌ Ошибка при создании канала: {e}"
            )


class RejectReasonModal(disnake.ui.Modal):
    """Модальное окно для причины отклонения"""
    
    def __init__(self, order_id: int, user_id: int, channel_id: int):
        self.order_id = order_id
        self.user_id = user_id
        self.channel_id = channel_id
        
        components = [
            disnake.ui.TextInput(
                label="Причина отклонения",
                placeholder="Напишите почему заказ отклонен...",
                custom_id="reject_reason",
                style=disnake.TextInputStyle.paragraph,
                min_length=5,
                max_length=500,
                required=True
            )
        ]
        super().__init__(title="❌ Отклонение заказа", components=components, custom_id=f"reject_modal_{order_id}")
    
    async def callback(self, inter: disnake.ModalInteraction):
        reason = inter.text_values["reject_reason"]
        
        # Обновляем статус в БД
        await db.update_order_ticket(self.order_id, status="rejected", reject_reason=reason)
        
        # Отправляем причину в ЛС заказчику
        dm_sent = False
        try:
            user = await inter.bot.fetch_user(self.user_id)
            dm_embed = disnake.Embed(
                title=f"❌ Заказ #{self.order_id} отклонен",
                description=f"**Причина:** {reason}",
                color=0x99aab5,
                timestamp=disnake.utils.utcnow()
            )
            await user.send(embed=dm_embed)
            dm_sent = True
        except:
            pass
        
        # Сначала отвечаем админу
        await inter.response.send_message(
            f"✅ Заказ #{self.order_id} отклонен.\n" + 
            ("📨 Причина отправлена в ЛС." if dm_sent else "⚠️ Не удалось отправить ЛС (закрыты)."),
            ephemeral=True
        )
        
        # Получаем канал и удаляем (после ответа)
        channel = inter.bot.get_channel(self.channel_id)
        if channel:
            try:
                await channel.delete(reason=f"Заказ #{self.order_id} отклонен: {reason}")
            except Exception as e:
                print(f"Ошибка удаления канала: {e}")


class AcceptRejectView(disnake.ui.View):
    """Кнопки принять/отклонить заказ"""
    
    def __init__(self, order_id: int, user_id: int):
        super().__init__(timeout=None)
        self.order_id = order_id
        self.user_id = user_id
    
    @disnake.ui.button(label="✅ Принять", style=disnake.ButtonStyle.green, custom_id="accept_order_btn")
    async def accept_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Проверяем что у пользователя есть права
        if not inter.permissions.administrator and not any(r.id == ADMIN_ROLE_ID for r in inter.user.roles):
            await inter.response.send_message("❌ Только администраторы могут принимать заказы!", ephemeral=True)
            return
        
        # Обновляем статус
        await db.update_order_ticket(self.order_id, status="accepted", assigned_to=inter.user.id)
        
        # Отключаем кнопки
        for child in self.children:
            child.disabled = True
        
        # Обновляем embed
        embed = inter.message.embeds[0]
        embed.color = 0x99aab5
        embed.add_field(name="✅ Статус", value=f"Принят {inter.user.mention}", inline=False)
        
        await inter.message.edit(embed=embed, view=self)
        
        # Отправляем ЛС заказчику
        try:
            user = await inter.bot.fetch_user(self.user_id)
            dm_embed = disnake.Embed(
                title=f"✅ Заказ #{self.order_id} принят!",
                description=f"Ваш заказ принят администратором {inter.user.mention}\nОбсуждение ведется в канале {inter.channel.mention}",
                color=0x99aab5,
                timestamp=disnake.utils.utcnow()
            )
            await user.send(embed=dm_embed)
        except:
            pass
        
        await inter.response.send_message("✅ Заказ принят!", ephemeral=True)
        
        # Отправляем в канал сообщение с кнопкой закрытия
        close_view = CloseTicketView(self.order_id, self.user_id)
        close_embed = disnake.Embed(
            title="🔒 Управление заказом",
            description="Когда заказ будет выполнен, нажмите кнопку ниже для закрытия.",
            color=0x2f3136
        )
        await inter.channel.send(embed=close_embed, view=close_view)
    
    @disnake.ui.button(label="❌ Отклонить", style=disnake.ButtonStyle.red, custom_id="reject_order_btn")
    async def reject_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Проверяем что у пользователя есть права
        if not inter.permissions.administrator and not any(r.id == ADMIN_ROLE_ID for r in inter.user.roles):
            await inter.response.send_message("❌ Только администраторы могут отклонять заказы!", ephemeral=True)
            return
        
        # Открываем модальное окно для причины
        modal = RejectReasonModal(self.order_id, self.user_id, inter.channel.id)
        await inter.response.send_modal(modal)


class CloseTicketView(disnake.ui.View):
    """Кнопка закрытия тикета в канале"""
    
    def __init__(self, order_id: int, user_id: int):
        super().__init__(timeout=None)
        self.order_id = order_id
        self.user_id = user_id
    
    @disnake.ui.button(label="🔒 Закрыть заказ", style=disnake.ButtonStyle.gray, custom_id="close_ticket_btn")
    async def close_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Проверяем что у пользователя есть права
        if not inter.permissions.administrator and not any(r.id == ADMIN_ROLE_ID for r in inter.user.roles):
            await inter.response.send_message("❌ Только администраторы могут закрывать заказы!", ephemeral=True)
            return
        
        # Обновляем статус
        await db.update_order_ticket(self.order_id, status="closed")
        
        # Отключаем кнопку закрытия
        button.disabled = True
        await inter.message.edit(view=self)
        
        # Отправляем ЛС заказчику с просьбой оставить отзыв
        dm_sent = False
        try:
            user = await inter.bot.fetch_user(self.user_id)
            
            # Создаем embed с просьбой оставить отзыв
            review_embed = disnake.Embed(
                title="📝 Оставьте отзыв!",
                description=f"Ваш заказ #{self.order_id} был закрыт.\n\n"
                           f"Будем признательны, если вы оставите отзыв о нашей работе! 💫",
                color=0x2f3136,
                timestamp=disnake.utils.utcnow()
            )
            review_embed.set_footer(text="Нажмите кнопку ниже, чтобы оставить отзыв")
            
            # Создаем View с кнопкой для отзыва
            review_view = ReviewRequestButtonView()
            
            await user.send(embed=review_embed, view=review_view)
            dm_sent = True
        except Exception as e:
            print(f"Ошибка отправки ЛС: {e}")
            dm_sent = False
        
        # Скрываем канал от заказчика (оставляем только для админов)
        try:
            guild = inter.guild
            channel = inter.channel
            
            # Убираем права у заказчика
            user_member = guild.get_member(self.user_id)
            if user_member:
                await channel.set_permissions(user_member, view_channel=False, send_messages=False)
            
            # Убираем права у @everyone если есть
            await channel.set_permissions(guild.default_role, view_channel=False)
            
            # Оставляем права для админов
            if ADMIN_ROLE_ID:
                admin_role = guild.get_role(ADMIN_ROLE_ID)
                if admin_role:
                    await channel.set_permissions(admin_role, view_channel=True, send_messages=True, read_message_history=True)
            
            # Оставляем права для бота
            await channel.set_permissions(guild.me, view_channel=True, send_messages=True, manage_channels=True)
            
            permissions_updated = True
        except Exception as e:
            print(f"Ошибка изменения прав: {e}")
            permissions_updated = False
        
        # Отвечаем в канал
        close_embed = disnake.Embed(
            title=f"🔒 Заказ #{self.order_id} закрыт",
            description=f"Заказ закрыт администратором {inter.user.mention}\n\n"
                       f"Канал теперь доступен только администраторам.",
            color=0x99aab5
        )
        if not dm_sent:
            close_embed.add_field(name="⚠️", value="Не удалось отправить ЛС заказчику", inline=False)
        if not permissions_updated:
            close_embed.add_field(name="⚠️", value="Не удалось изменить права канала", inline=False)
        
        await inter.response.send_message(embed=close_embed)
        
        # Отправляем сообщение с кнопками управления архивом
        archive_view = ArchiveManageView(self.order_id, self.user_id, channel.id)
        archive_embed = disnake.Embed(
            title="📁 Управление архивом",
            description="Используйте кнопки ниже для управления каналом:\n\n"
                       "🔓 **Открыть** - вернуть доступ заказчику\n"
                       "🗑️ **Удалить** - полностью удалить канал",
            color=0x2f3136
        )
        await inter.channel.send(embed=archive_embed, view=archive_view)


class ArchiveManageView(disnake.ui.View):
    """Кнопки управления архивированным каналом"""
    
    def __init__(self, order_id: int, user_id: int, channel_id: int):
        super().__init__(timeout=None)
        self.order_id = order_id
        self.user_id = user_id
        self.channel_id = channel_id
    
    @disnake.ui.button(label="🔓 Открыть для заказчика", style=disnake.ButtonStyle.green, custom_id="reopen_ticket_btn")
    async def reopen_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Проверяем что у пользователя есть права
        if not inter.permissions.administrator and not any(r.id == ADMIN_ROLE_ID for r in inter.user.roles):
            await inter.response.send_message("❌ Только администраторы могут открывать заказы!", ephemeral=True)
            return
        
        # Обновляем статус
        await db.update_order_ticket(self.order_id, status="reopened")
        
        # Восстанавливаем права заказчику
        try:
            guild = inter.guild
            channel = inter.channel
            
            user_member = guild.get_member(self.user_id)
            if user_member:
                await channel.set_permissions(user_member, view_channel=True, send_messages=True, read_message_history=True)
            
            # Отключаем эту кнопку, включаем кнопку закрытия
            button.disabled = True
            await inter.message.edit(view=self)
            
            await inter.response.send_message(
                f"✅ Канал открыт для {user_member.mention if user_member else 'заказчика'}!",
                ephemeral=True
            )
            
            # Отправляем уведомление в канал
            reopen_embed = disnake.Embed(
                title=f"🔓 Заказ #{self.order_id} открыт",
                description=f"Канал снова открыт администратором {inter.user.mention}",
                color=0x99aab5
            )
            await channel.send(embed=reopen_embed)
            
        except Exception as e:
            await inter.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
    
    @disnake.ui.button(label="🗑️ Удалить канал", style=disnake.ButtonStyle.red, custom_id="delete_ticket_btn")
    async def delete_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Проверяем что у пользователя есть права
        if not inter.permissions.administrator and not any(r.id == ADMIN_ROLE_ID for r in inter.user.roles):
            await inter.response.send_message("❌ Только администраторы могут удалять каналы!", ephemeral=True)
            return
        
        # Создаем View с подтверждением удаления
        confirm_view = ConfirmDeleteView(self.order_id, inter.channel.id)
        
        await inter.response.send_message(
            "⚠️ **Вы уверены?**\n"
            "Канал будет удален безвозвратно!\n\n"
            "Нажмите кнопку ниже для подтверждения:",
            view=confirm_view,
            ephemeral=True
        )


class ConfirmDeleteView(disnake.ui.View):
    """Подтверждение удаления канала"""
    
    def __init__(self, order_id: int, channel_id: int):
        super().__init__(timeout=30)  # 30 секунд на подтверждение
        self.order_id = order_id
        self.channel_id = channel_id
    
    @disnake.ui.button(label="✅ Да, удалить", style=disnake.ButtonStyle.red, custom_id="confirm_delete_btn")
    async def confirm_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Обновляем статус
        await db.update_order_ticket(self.order_id, status="deleted")
        
        # Отвечаем что удаляем
        await inter.response.send_message("🗑️ Удаление канала...", ephemeral=True)
        
        # Удаляем канал
        try:
            channel = inter.bot.get_channel(self.channel_id)
            if channel:
                await channel.delete(reason=f"Заказ #{self.order_id} удален администратором")
        except Exception as e:
            await inter.followup.send(f"❌ Ошибка удаления: {e}", ephemeral=True)
    
    @disnake.ui.button(label="❌ Отмена", style=disnake.ButtonStyle.gray, custom_id="cancel_delete_btn")
    async def cancel_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_message("✅ Удаление отменено.", ephemeral=True)


class ReviewRequestButtonView(disnake.ui.View):
    """Кнопка для открытия модального окна отзыва в ЛС"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @disnake.ui.button(label="📝 Оставить отзыв", style=disnake.ButtonStyle.primary, custom_id="review_request_dm_btn")
    async def review_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Проверяем что ReviewModal доступен
        if ReviewModal is None:
            await inter.response.send_message(
                "❌ Система отзывов временно недоступна. Попробуйте позже или напишите администратору.", 
                ephemeral=True
            )
            return
        
        # Открываем модальное окно для отзыва
        modal = ReviewModal()
        await inter.response.send_modal(modal)


class TicketButtonView(disnake.ui.View):
    """Кнопка для создания заказа (тикета)"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @disnake.ui.button(
        label="🎫 Создать заказ",
        style=disnake.ButtonStyle.primary,
        custom_id="create_ticket_btn"
    )
    async def create_ticket_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        # Открываем модальное окно для создания заказа
        modal = TicketOrderModal()
        await inter.response.send_modal(modal)


class TicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Регистрируем персистентные View
        self.bot.add_view(TicketButtonView())
        print("✅ TicketButtonView зарегистрирован")
        
        self.bot.add_view(CloseTicketView(0, 0))
        print("✅ CloseTicketView зарегистрирован")
        
        self.bot.add_view(ArchiveManageView(0, 0, 0))
        print("✅ ArchiveManageView зарегистрирован")
        
        self.bot.add_view(ConfirmDeleteView(0, 0))
        print("✅ ConfirmDeleteView зарегистрирован")
        
        self.bot.add_view(ReviewRequestButtonView())
        print("✅ ReviewRequestButtonView зарегистрирован")
    
    @commands.command(name="setup_ticket")
    @commands.has_permissions(administrator=True)
    async def setup_ticket_cmd(self, ctx):
        """Отправить панель создания тикета"""
        embed = disnake.Embed(
            title="🎫 Система заказов",
            description="Нажмите кнопку ниже, чтобы создать новый заказ.\n\n"
                        "**Вам нужно указать:**\n"
                        "• Описание заказа\n"
                        "• Бюджет (опционально)\n"
                        "• Сроки (опционально)\n\n"
                        "После создания будет автоматически создан канал для обсуждения.",
            color=0x2f3136
        )
        
        view = TicketButtonView()
        await ctx.send(embed=embed, view=view)
    
    @commands.slash_command(name="setup_ticket_slash", description="Отправить панель создания тикета")
    @commands.has_permissions(administrator=True)
    async def setup_ticket_slash(self, inter: disnake.ApplicationCommandInteraction):
        """Слеш-команда для отправки панели тикета"""
        embed = disnake.Embed(
            title="🎫 Система заказов",
            description="Нажмите кнопку ниже, чтобы создать новый заказ.\n\n"
                        "**Вам нужно указать:**\n"
                        "• Описание заказа\n"
                        "• Бюджет (опционально)\n"
                        "• Сроки (опционально)\n\n"
                        "После создания будет автоматически создан канал для обсуждения.",
            color=0x2f3136
        )
        
        view = TicketButtonView()
        await inter.response.send_message(embed=embed, view=view)
    
    @commands.slash_command(name="delete_ticket", description="Удалить канал тикета (только для администраторов)")
    @commands.has_permissions(administrator=True)
    async def delete_ticket_slash(self, inter: disnake.ApplicationCommandInteraction):
        """Слеш-команда для удаления канала тикета"""
        # Проверяем что канал является тикетом
        order = await db.get_order_by_channel(inter.channel.id)
        if not order:
            await inter.response.send_message("❌ Этот канал не является тикетом заказа!", ephemeral=True)
            return
        
        # Создаем View с подтверждением
        confirm_view = ConfirmDeleteView(order["id"], inter.channel.id)
        
        await inter.response.send_message(
            f"⚠️ **Вы уверены что хотите удалить заказ #{order['id']}?**\n"
            f"Канал будет удален безвозвратно!\n\n"
            f"Нажмите кнопку ниже для подтверждения:",
            view=confirm_view,
            ephemeral=True
        )


    @commands.command(name="close_ticket_force")
    @commands.has_permissions(administrator=True)
    async def close_ticket_force_cmd(self, ctx):
        """Принудительно удалить канал тикета (архив)"""
        # Проверяем что канал является тикетом
        order = await db.get_order_by_channel(ctx.channel.id)
        if not order:
            await ctx.send("❌ Этот канал не является тикетом заказа!")
            return
        
        # Обновляем статус
        await db.update_order_ticket(order["id"], status="archived")
        
        embed = disnake.Embed(
            title=f"🗑️ Заказ #{order['id']} архивирован",
            description=f"Канал будет удален администратором {ctx.author.mention}",
            color=0x99aab5
        )
        await ctx.send(embed=embed)
        
        # Удаляем канал через 3 секунды
        await asyncio.sleep(3)
        await ctx.channel.delete(reason=f"Заказ #{order['id']} архивирован")


    @commands.command(name="close_ticket")
    @commands.has_permissions(administrator=True)
    async def close_ticket_cmd(self, ctx):
        """Закрыть тикет (канал заказа) - устаревшая команда, используйте кнопки"""
        await ctx.send("ℹ️ Используйте кнопку '🔒 Закрыть заказ' в канале или `!close_ticket_force` для удаления.")


def setup(bot):
    bot.add_cog(TicketsCog(bot))
