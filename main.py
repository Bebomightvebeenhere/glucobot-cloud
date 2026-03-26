import os
import asyncio
from aiohttp import web
import discord
from pydexcom import Dexcom
from datetime import datetime, timezone

# Read environment variables
DEXCOM_USERNAME = os.getenv("DEXCOM_USERNAME")
DEXCOM_PASSWORD = os.getenv("DEXCOM_PASSWORD")
DEXCOM_REGION   = os.getenv("DEXCOM_REGION")  # optional, e.g. "OUS" or "JP"
DISCORD_TOKEN   = os.getenv("DISCORD_TOKEN")
CHANNEL_ID_STR  = os.getenv("CHANNEL_ID")

# Validate environment variables
if not all([DEXCOM_USERNAME, DEXCOM_PASSWORD, DISCORD_TOKEN, CHANNEL_ID_STR]):
    raise RuntimeError("Missing one or more required environment variables: DEXCOM_USERNAME, DEXCOM_PASSWORD, DISCORD_TOKEN, CHANNEL_ID")

CHANNEL_ID = int(CHANNEL_ID_STR)

# Initialize Dexcom client
if DEXCOM_REGION:
    dexcom = Dexcom(username=DEXCOM_USERNAME, password=DEXCOM_PASSWORD, region=DEXCOM_REGION)
else:
    dexcom = Dexcom(username=DEXCOM_USERNAME, password=DEXCOM_PASSWORD)

# Initialize Discord client
intents = discord.Intents.default()
client = discord.Client(intents=intents)

async def fetch_glucose():
    """Fetch current glucose reading from Dexcom Share."""
    reading = dexcom.get_current_glucose_reading()
    value = reading.value
    arrow = reading.trend_arrow
    ts = reading.datetime
    if ts is None:
        # If timestamp not provided, just return current time
        return value, arrow, None
    # Ensure timezone aware
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return value, arrow, ts

async def post_glucose_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    while not client.is_closed():
        try:
            value, arrow, ts = await asyncio.get_event_loop().run_in_executor(None, fetch_glucose_sync)
            # compute time since reading
            if ts:
                now = datetime.now(timezone.utc)
                minutes_ago = int((now - ts).total_seconds() // 60)
                time_text = f"{minutes_ago} min ago"
            else:
                time_text = "just now"
            message = f" **BG:** \n {value}mg/dL {arrow} \n\u23F1 Updated {time_text}"
            await channel.send(message)
        except Exception as e:
            print(f"Error during glucose fetch/post: {e}")
        # Wait 5 minutes
        await asyncio.sleep(300)

def fetch_glucose_sync():
    """Wrapper to call synchronous Dexcom get_current_glucose_reading in executor."""
    reading = dexcom.get_current_glucose_reading()
    value = reading.value
    arrow = reading.trend_arrow
    ts = reading.datetime
    if ts and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return value, arrow, ts

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    client.loop.create_task(post_glucose_loop())

# HTTP server handler
async def handle(request):
    return web.Response(text="GlucoBot is running.")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")
    # Keep running indefinitely
    await asyncio.Event().wait()

async def start_discord_bot():
    await client.start(DISCORD_TOKEN)

async def main():
    await asyncio.gather(start_discord_bot(), start_web_server())

if __name__ == "__main__":
    asyncio.run(main())
