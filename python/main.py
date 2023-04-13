import asyncio
import os
import sql
import helper
from dotenv import load_dotenv
from telethon import TelegramClient, events

if 'ON_HEROKU' not in os.environ:
    load_dotenv()

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
bot_token = os.environ['BOT_TOKEN']


async def main():
    client = TelegramClient('bot', api_id, api_hash)
    client.parse_mode = 'html'
    await client.start(bot_token=bot_token)
    sql.init()

    @client.on(events.NewMessage(func=helper.check))
    async def handler(event):
        await helper.do(client, event)

    @client.on(events.CallbackQuery(func=helper.check))
    async def handler(event):
        await helper.do(client, event)

    await client.run_until_disconnected()


asyncio.run(main())
