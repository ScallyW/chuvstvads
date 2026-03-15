import os
import disnake
from disnake.ext import commands
from dotenv import load_dotenv
from database import db

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))


class Bot(commands.Bot):
    def __init__(self):
        intents = disnake.Intents.default()
        intents.members = True
        intents.message_content = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        
        self._first_ready = True
    
    async def on_ready(self):
        # Устанавливаем статус бота
        await self.change_presence(
            activity=disnake.Activity(
                type=disnake.ActivityType.watching,
                name=f"Смотрит за {sum(g.member_count for g in self.guilds)} участниками"
            )
        )
        
        print(f"✅ Бот {self.user} запущен!")
        
        await db.init()
        print("✅ База данных инициализирована")
        
        # Загрузка когов только при первом запуске
        if self._first_ready:
            self._first_ready = False
            
            for filename in os.listdir("./cogs"):
                if filename.endswith(".py"):
                    cog_name = f"cogs.{filename[:-3]}"
                    if cog_name not in self.extensions:
                        try:
                            self.load_extension(cog_name)
                            print(f"✅ Ког {filename} загружен")
                        except Exception as e:
                            print(f"❌ Ошибка загрузки {filename}: {e}")
            
            # Синхронизация слеш-команд
            try:
                await disnake.utils.sleep_until(disnake.utils.utcnow())
                
                if GUILD_ID:
                    # Синхронизация для конкретного сервера
                    guild = disnake.Object(id=GUILD_ID)
                    # В disnake 2.x используем sync_application_commands
                    if hasattr(self, 'sync_application_commands'):
                        await self.sync_application_commands(guild=guild)
                        print(f"✅ Слеш-команды синхронизированы для сервера {GUILD_ID}")
                    else:
                        print(f"✅ Слеш-команды загружены для сервера {GUILD_ID}")
                else:
                    print("ℹ️ Укажите GUILD_ID в .env для синхронизации слеш-команд")
            except Exception as e:
                print(f"⚠️ Ошибка синхронизации: {e}")


bot = Bot()


if __name__ == "__main__":
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        print("❌ Укажите BOT_TOKEN в файле .env")
        exit(1)
    
    # Создаем папку cogs если не существует
    if not os.path.exists("./cogs"):
        os.makedirs("./cogs")
        print("📁 Создана папка cogs/")
    
    bot.run(BOT_TOKEN)
