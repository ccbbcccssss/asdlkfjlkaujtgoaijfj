import discord
from discord.ext import commands
import yt_dlp as youtube_dl

TOKEN = 'MTMzMzAyODQ1NDc2OTM2MDkzNg.GCuBFj.E8IMHCGShlYzVP-_aW4ZIEW7A0GIkw78lrcVGY'

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True  # Keep this enabled for voice states

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot {bot.user} is ready!')
    print(f'Enabled Intents: {bot.intents}')

@bot.command(name='join')
async def join(ctx):
    try:
        print(f"Join command from {ctx.author}")
        if not ctx.author.voice:
            await ctx.send("❗ You're not in a voice channel!")
            return
            
        channel = ctx.author.voice.channel
        print(f"Attempting to connect to {channel.name}")
        voice_client = await channel.connect()
        await ctx.send(f"✅ Joined {channel.name}")
        
    except Exception as e:
        print(f"Join error: {str(e)}")
        await ctx.send(f"❌ Failed to join: {str(e)}")

@bot.command(name='play')
async def play(ctx, url):
    try:
        if not ctx.author.voice:
            return await ctx.send("❗ You're not in a voice channel!")
            
        voice_client = ctx.voice_client or await ctx.author.voice.channel.connect()
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'opus',  # Changed to opus
                'preferredquality': '192',
            }],
            'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'restrictfilenames': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'geo_bypass': True,
            'default_search': 'auto',
            'source_address': '0.0.0.0',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']
            
        if voice_client.is_playing():
            voice_client.stop()
            
        # Modified audio source with proper FFmpeg options
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -b:a 128k -ac 2'
        }
        
        source = discord.FFmpegOpusAudio(
            audio_url,
            **ffmpeg_options
        )
        
        voice_client.play(source)
        await ctx.send(f"🔊 Now playing: {info['title']}")
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")
        print(f"Play error details: {repr(e)}")

@bot.command(name='leave')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("✅ Left the voice channel")
    else:
        await ctx.send("❌ Not in a voice channel")

bot.run(TOKEN)
