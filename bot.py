import discord
from discord.ext import commands
from discord import PCMVolumeTransformer
import yt_dlp as youtube_dl
from collections import deque
import asyncio

TOKEN = 'MTMzMzAyODQ1NDc2OTM2MDkzNg.GCuBFj.E8IMHCGShlYzVP-_aW4ZIEW7A0GIkw78lrcVGY'

# Queue structure: {guild_id: {'queue': deque(), 'loop': False, 'now_playing': None}}
queues = {}

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

class YTDLSource(PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'opus',
                'preferredquality': '192',
            }],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            }
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                return [ydl.sanitize_info(entry) for entry in info['entries']]
            else:
                return [ydl.sanitize_info(info)]

async def play_next(ctx):
    guild_id = ctx.guild.id
    try:
        if queues[guild_id]['queue']:
            if queues[guild_id]['loop']:
                queues[guild_id]['queue'].append(queues[guild_id]['now_playing'])

            next_song = queues[guild_id]['queue'].popleft()
            queues[guild_id]['now_playing'] = next_song

            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': '-vn'
            }
            
            source = await discord.FFmpegOpusAudio.from_probe(next_song['url'], **ffmpeg_options)
            ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
            
            await ctx.send(f"🔊 Now playing: {next_song['title']}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.event
async def on_ready():
    print(f'Bot {bot.user} is ready!')
    print(f'Enabled Intents: {bot.intents}')

@bot.command(name='join')
async def join(ctx):
    try:
        if not ctx.author.voice:
            await ctx.send("❗ You're not in a voice channel!")
            return
            
        channel = ctx.author.voice.channel
        voice_client = await channel.connect()
        await ctx.send(f"✅ Joined {channel.name}")
        
    except Exception as e:
        await ctx.send(f"❌ Failed to join: {str(e)}")

@bot.command(name='play')
async def play(ctx, *, url):
    try:
        if not ctx.author.voice:
            return await ctx.send("❗ You're not in a voice channel!")
            
        voice_client = ctx.voice_client or await ctx.author.voice.channel.connect()
        
        async with ctx.typing():
            data = await YTDLSource.from_url(url)
            
            guild_id = ctx.guild.id
            if guild_id not in queues:
                queues[guild_id] = {'queue': deque(), 'loop': False, 'now_playing': None}
            
            for song in data:
                queues[guild_id]['queue'].append(song)
                await ctx.send(f"🎶 Queued: {song['title']}")
            
            if not voice_client.is_playing():
                await play_next(ctx)
                
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='pause')
async def pause(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused")
    else:
        await ctx.send("❌ Nothing is playing")

@bot.command(name='resume')
async def resume(ctx):
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed")
    else:
        await ctx.send("❌ Player is not paused")

@bot.command(name='stop')
async def stop(ctx):
    if ctx.voice_client:
        if ctx.guild.id in queues:
            queues[ctx.guild.id]['queue'].clear()
            queues[ctx.guild.id]['now_playing'] = None
        ctx.voice_client.stop()
        await ctx.send("⏹️ Stopped and cleared queue")

@bot.command(name='skip')
async def skip(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("⏭️ Skipped")
        await play_next(ctx)

@bot.command(name='queue')
async def show_queue(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues and (queues[guild_id]['queue'] or queues[guild_id]['now_playing']):
        message = []
        if queues[guild_id]['now_playing']:
            message.append(f"**Now Playing:** {queues[guild_id]['now_playing']['title']}")
        
        if queues[guild_id]['queue']:
            message.append("\n**Queue:**")
            for i, song in enumerate(queues[guild_id]['queue'], 1):
                message.append(f"{i}. {song['title']}")
        
        await ctx.send("\n".join(message[:10]))
    else:
        await ctx.send("❌ Queue is empty")

@bot.command(name='loop')
async def loop(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues:
        queues[guild_id]['loop'] = not queues[guild_id]['loop']
        status = "✅ Enabled" if queues[guild_id]['loop'] else "❌ Disabled"
        await ctx.send(f"🔁 Loop {status}")
    else:
        await ctx.send("❌ Nothing in queue")

@bot.command(name='volume', help='Adjust volume (0-100)')
async def volume(ctx, volume: int):
    if ctx.voice_client.source:
        if 0 < volume <= 100:
            ctx.voice_client.source.volume = volume / 100
            await ctx.send(f"🔊 Volume set to {volume}%")
        else:
            await ctx.send("❌ Volume must be between 1 and 100")

@bot.command(name='leave')
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("✅ Left the voice channel")
    else:
        await ctx.send("❌ Not in a voice channel")

bot.run(TOKEN)
