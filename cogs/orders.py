import os
import disnake
from disnake.ext import commands
from database import db

ORDERS_CHANNEL_ID = int(os.getenv("ORDERS_CHANNEL_ID", 0))
ORDER_PING_ROLE_IDS = [int(x.strip()) for x in os.getenv("ORDER_PING_ROLE_IDS", "").split(",") if x.strip()]


class OrderModal(disnake.ui.Modal):
    """Модальное окно для создания заказа"""
    
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Описание заказа",
                placeholder="Подробно опишите, что вам нужно...",
                custom_id="order_description",
                style=disnake.TextInputStyle.paragraph,
                min_length=10,
                max_length=1000,
                required=True
            ),
            disnake.ui.TextInput(
                label="Бюджет",
                placeholder="Например: 1000₽ или договорная",
                custom_id="order_budget",
                style=disnake.TextInputStyle.short,
                max_length=100,
                required=False
            ),
            disnake.ui.TextInput(
                label="Сроки",
                placeholder="Когда нужно выполнить?",
                custom_id="order_deadline",
                style=disnake.TextInputStyle.short,
                max_length=100,
                required=False
            ),
        ]
        super().__init__(
            title="Создание заказа",
            custom_id="order_modal",
            components=components
        )
    
    async def callback(self, inter: disnake.ModalInteraction):
        description = inter.text_values["order_description"]
        budget = inter.text_values.get("order_budget", "Не указан")
        deadline = inter.text_values.get("order_deadline", "Не указаны")
        
        order_id = await db.create_order(
            user_id=inter.user.id,
            username=str(inter.user),
            description=description,
            budget=budget,
            deadline=deadline
        )
        
        if ORDERS_CHANNEL_ID:
            channel = inter.bot.get_channel(ORDERS_CHANNEL_ID)
            if channel:
                embed = disnake.Embed(
                    title=f"📦 Новый заказ #{order_id}",
                    description=description,
                    color=0x2f3136,
                    timestamp=disnake.utils.utcnow()
                )
                embed.add_field(name="Бюджет", value=budget, inline=True)
                embed.add_field(name="Сроки", value=deadline, inline=True)
                embed.add_field(name="Заказчик", value=inter.user.mention, inline=False)
                embed.set_footer(text=f"ID заказа: {order_id}")
                
                ping_mentions = " ".join([f"<@&{role_id}>" for role_id in ORDER_PING_ROLE_IDS])
                
                msg = await channel.send(
                    content=ping_mentions if ping_mentions else None,
                    embed=embed
                )
                
                await db.update_order_message_id(order_id, msg.id)
        
        await inter.response.send_message(
            f"✅ Ваш заказ #{order_id} успешно создан!", 
            ephemeral=True
        )


class OrderButtonView(disnake.ui.View):
    """Персистентная кнопка для создания заказа - работает после рестарта"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @disnake.ui.button(
        label="Создать заказ", 
        style=disnake.ButtonStyle.primary,
        emoji="📦",
        custom_id="persistent_order_button"
    )
    async def create_order_button(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_modal(OrderModal())


class OrdersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Регистрируем персистентный View сразу
        self.bot.add_view(OrderButtonView())
        print("✅ OrderButtonView зарегистрирован")
    
    @commands.command(name="button_ord")
    @commands.has_permissions(administrator=True)
    async def button_ord(self, ctx):
        """Отправить embed с кнопкой создания заказа"""
        embed = disnake.Embed(
            title="📦 Создание заказа",
            description="Нажмите кнопку ниже, чтобы создать новый заказ.\n\n"
                        "**Вам нужно указать:**\n"
                        "• Описание заказа\n"
                        "• Бюджет (опционально)\n"
                        "• Сроки (опционально)",
            color=0x2f3136
        )
        
        view = OrderButtonView()
        await ctx.send(embed=embed, view=view)
    
    @commands.command(name="order_info")
    async def order_info(self, ctx, order_id: int):
        """Информация о заказе по ID"""
        order = await db.get_order(order_id)
        if not order:
            await ctx.send("❌ Заказ не найден!")
            return
        
        embed = disnake.Embed(
            title=f"📦 Заказ #{order_id}",
            description=order["description"],
            color=0x2f3136
        )
        embed.add_field(name="Заказчик", value=f"<@{order['user_id']}> ({order['username']})", inline=False)
        embed.add_field(name="Бюджет", value=order["budget"] or "Не указан", inline=True)
        embed.add_field(name="Сроки", value=order["deadline"] or "Не указаны", inline=True)
        embed.add_field(name="Статус", value=order["status"], inline=True)
        embed.add_field(name="Создан", value=order["created_at"], inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.slash_command(name="setup_order", description="Отправить панель создания заказа")
    @commands.has_permissions(administrator=True)
    async def setup_order_slash(self, inter: disnake.ApplicationCommandInteraction):
        """Слеш-команда для отправки панели заказа"""
        embed = disnake.Embed(
            title="📦 Создание заказа",
            description="Нажмите кнопку ниже, чтобы создать новый заказ.\n\n"
                        "**Вам нужно указать:**\n"
                        "• Описание заказа\n"
                        "• Бюджет (опционально)\n"
                        "• Сроки (опционально)",
            color=0x2f3136
        )
        
        view = OrderButtonView()
        await inter.response.send_message(embed=embed, view=view)

    @commands.slash_command(name="order_info_slash", description="Информация о заказе по ID")
    @commands.has_permissions(administrator=True)
    async def order_info_slash(self, inter: disnake.ApplicationCommandInteraction, order_id: int):
        """Слеш-команда для информации о заказе"""
        order = await db.get_order(order_id)
        if not order:
            await inter.response.send_message("❌ Заказ не найден!", ephemeral=True)
            return
        
        embed = disnake.Embed(
            title=f"📦 Заказ #{order_id}",
            description=order["description"],
            color=0x2f3136
        )
        embed.add_field(name="Заказчик", value=f"<@{order['user_id']}> ({order['username']})", inline=False)
        embed.add_field(name="Бюджет", value=order["budget"] or "Не указан", inline=True)
        embed.add_field(name="Сроки", value=order["deadline"] or "Не указаны", inline=True)
        embed.add_field(name="Статус", value=order["status"], inline=True)
        embed.add_field(name="Создан", value=order["created_at"], inline=False)
        
        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="test_orders")
    @commands.has_permissions(administrator=True)
    async def test_orders(self, ctx):
        """Тест системы заказов (админская команда)"""
        embed = disnake.Embed(
            title="[ТЕСТ] Система заказов",
            description="Проверка работы системы заказов...",
            color=0x99aab5,
            timestamp=disnake.utils.utcnow()
        )
        
        # Создаем тестовый заказ
        test_order_id = await db.create_order(
            user_id=ctx.author.id,
            username=str(ctx.author),
            description="Тестовый заказ для проверки системы",
            budget="1000₽ (тест)",
            deadline="Сегодня (тест)"
        )
        
        embed.add_field(name="Статус", value="✅ База данных работает", inline=False)
        embed.add_field(name="Тестовый заказ", value=f"ID: #{test_order_id}", inline=True)
        embed.add_field(name="Канал заказов", value=f"<#{ORDERS_CHANNEL_ID}>" if ORDERS_CHANNEL_ID else "❌ Не настроен", inline=True)
        
        if ORDER_PING_ROLE_IDS:
            roles = ", ".join([f"<@&{r}>" for r in ORDER_PING_ROLE_IDS])
            embed.add_field(name="Роли для пинга", value=roles, inline=False)
        else:
            embed.add_field(name="Роли для пинга", value="❌ Не настроены", inline=False)
        
        # Отправляем тестовое сообщение с кнопкой
        test_view = OrderButtonView()
        embed2 = disnake.Embed(
            title="[ТЕСТ] Кнопка заказа",
            description="Нажмите кнопку ниже для теста модального окна",
            color=0x2f3136
        )
        
        await ctx.send(embed=embed)
        await ctx.send(embed=embed2, view=test_view)



def setup(bot):
    bot.add_cog(OrdersCog(bot))
