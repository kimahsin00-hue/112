"""
TTS(텍스트 채널 → 음성 채널 읽어주기) cog.

원본 cian24.py에는 이 기능이 별도의 cogs/tts.py 파일로 이미 분리되어 있었는데
(setup_hook에서 bot.load_extension("cogs.tts")로 로드), 그 파일 자체는 업로드된
cian24.py 안에 내용이 없어서 이번에 새로 작성했습니다. DB 스키마(tts_settings 테이블:
guild_id, text_ch_id, voice_ch_id, enabled)는 원본에 이미 있던 걸 그대로 씁니다.

자연스러운 음성을 위해 gTTS 대신 edge-tts(마이크로소프트 엣지 뉴럴 TTS, 무료)를 사용합니다.
기본 목소리는 'ko-KR-SunHiNeural'(여성)이고, /tts목소리 명령어로 바꿀 수 있습니다.

필요 조건 (서버에 설치되어 있어야 합니다):
    pip install edge-tts --break-system-packages
    ffmpeg (voice 재생용, 이미 설치되어 있어야 합니다)

동작 방식:
1. /설치-tts 로 텍스트채널/음성채널을 지정하면 tts_settings에 저장됩니다.
2. 지정된 텍스트채널에 메시지가 오면 큐에 쌓이고, 봇이 음성채널에 자동 접속해서
   순서대로 읽어줍니다 (동시에 여러 메시지가 겹쳐 재생되지 않도록 길드별 큐 사용).
3. 메시지 안의 멘션/커스텀이모지/링크는 읽기 전에 정리합니다.
4. 큐가 일정 시간(기본 5분) 비어있으면 자동으로 음성채널에서 나갑니다 (리소스 절약).
"""
import asyncio
import os
import re
import tempfile

import discord
from discord import app_commands
from discord.ext import commands

from config import ADMIN_ROLE_ID
from db import get_db

try:
    import edge_tts
except ImportError:
    edge_tts = None

DEFAULT_VOICE = "ko-KR-SunHiNeural"
AVAILABLE_VOICES = {
    "선히 (여성, 기본)": "ko-KR-SunHiNeural",
    "인준 (남성)": "ko-KR-InJoonNeural",
    "현수 (남성, 밝은 톤)": "ko-KR-HyunsuMultilingualNeural",
}
MAX_TTS_LENGTH = 200  # 너무 긴 메시지는 앞부분만 읽음
AUTO_LEAVE_SECONDS = 300  # 큐가 이만큼 비어있으면 자동으로 음성채널에서 나감

_MENTION_RE = re.compile(r"<@!?\d+>")
_ROLE_MENTION_RE = re.compile(r"<@&\d+>")
_CHANNEL_MENTION_RE = re.compile(r"<#\d+>")
_CUSTOM_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")
_URL_RE = re.compile(r"https?://\S+")


def _is_admin(user: discord.Member) -> bool:
    return bool(getattr(user.guild_permissions, 'administrator', False)) or bool(user.get_role(ADMIN_ROLE_ID))


def sanitize_for_tts(text: str) -> str:
    """멘션/커스텀이모지/링크를 읽기 좋은 말로 정리하고, 너무 길면 잘라낸다."""
    text = _MENTION_RE.sub("누군가", text)
    text = _ROLE_MENTION_RE.sub("역할", text)
    text = _CHANNEL_MENTION_RE.sub("채널", text)
    text = _CUSTOM_EMOJI_RE.sub("", text)
    text = _URL_RE.sub("링크", text)
    text = text.strip()
    if len(text) > MAX_TTS_LENGTH:
        text = text[:MAX_TTS_LENGTH] + " 이하 생략"
    return text


def get_guild_tts_settings(guild_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT text_ch_id, voice_ch_id, enabled FROM tts_settings WHERE guild_id=?", (guild_id,)
    ).fetchone()
    return row  # (text_ch_id, voice_ch_id, enabled) 또는 None


def get_guild_voice(guild_id: int) -> str:
    conn = get_db()
    row = conn.execute("SELECT voice FROM tts_voice_settings WHERE guild_id=?", (guild_id,)).fetchone()
    return row[0] if row else DEFAULT_VOICE


class TTSCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 길드별 재생 큐와 워커 태스크
        self.queues: dict[int, asyncio.Queue] = {}
        self.workers: dict[int, asyncio.Task] = {}

        conn = get_db()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tts_voice_settings (guild_id INTEGER PRIMARY KEY, voice TEXT NOT NULL)"
        )
        conn.commit()

        if edge_tts is None:
            print("⚠️ edge-tts가 설치되어 있지 않습니다. 'pip install edge-tts --break-system-packages'로 설치해주세요.")

    def cog_unload(self):
        for task in self.workers.values():
            task.cancel()

    def _get_queue(self, guild_id: int) -> asyncio.Queue:
        if guild_id not in self.queues:
            self.queues[guild_id] = asyncio.Queue()
        if guild_id not in self.workers or self.workers[guild_id].done():
            self.workers[guild_id] = self.bot.loop.create_task(self._worker(guild_id))
        return self.queues[guild_id]

    async def _worker(self, guild_id: int):
        """길드별로 하나씩 돌아가는 재생 워커 — 큐에서 꺼내서 순서대로 읽어줍니다."""
        queue = self.queues[guild_id]
        while True:
            try:
                text, voice_channel = await asyncio.wait_for(queue.get(), timeout=AUTO_LEAVE_SECONDS)
            except asyncio.TimeoutError:
                guild = self.bot.get_guild(guild_id)
                if guild and guild.voice_client:
                    await guild.voice_client.disconnect(force=True)
                continue

            try:
                await self._speak(guild_id, text, voice_channel)
            except Exception as e:
                print(f"⚠️ TTS 재생 실패 (guild={guild_id}): {e}")
            finally:
                queue.task_done()

    async def _speak(self, guild_id: int, text: str, voice_channel: discord.VoiceChannel):
        if edge_tts is None:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        vc = guild.voice_client
        if vc is None or not vc.is_connected():
            vc = await voice_channel.connect()
        elif vc.channel.id != voice_channel.id:
            await vc.move_to(voice_channel)

        voice = get_guild_voice(guild_id)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(tmp_path)

            source = discord.FFmpegPCMAudio(tmp_path)
            finished = asyncio.Event()

            def _after_play(error):
                if error:
                    print(f"⚠️ TTS 재생 중 오류: {error}")
                self.bot.loop.call_soon_threadsafe(finished.set)

            vc.play(source, after=_after_play)
            await finished.wait()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        settings = get_guild_tts_settings(message.guild.id)
        if not settings:
            return
        text_ch_id, voice_ch_id, enabled = settings
        if not enabled or message.channel.id != text_ch_id:
            return

        voice_channel = message.guild.get_channel(voice_ch_id)
        if not isinstance(voice_channel, discord.VoiceChannel):
            return
        if len(voice_channel.members) == 0:
            return  # 음성채널에 아무도 없으면 굳이 접속 안 함

        content = sanitize_for_tts(message.content)
        if not content:
            return

        queue = self._get_queue(message.guild.id)
        await queue.put((content, voice_channel))

    @app_commands.command(name="설치-tts", description="[관리자] TTS 텍스트채널/음성채널을 지정합니다")
    @app_commands.describe(텍스트채널="이 채널의 메시지를 읽어줍니다", 음성채널="여기서 읽어줍니다")
    @app_commands.default_permissions(administrator=True)
    async def setup_tts(self, interaction: discord.Interaction, 텍스트채널: discord.TextChannel, 음성채널: discord.VoiceChannel):
        if not _is_admin(interaction.user):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        conn = get_db()
        conn.execute(
            "INSERT OR REPLACE INTO tts_settings (guild_id, text_ch_id, voice_ch_id, enabled) VALUES (?, ?, ?, 1)",
            (interaction.guild.id, 텍스트채널.id, 음성채널.id),
        )
        conn.commit()
        await interaction.response.send_message(
            f"✅ TTS 설정 완료!\n**텍스트채널:** {텍스트채널.mention}\n**음성채널:** {음성채널.mention}", ephemeral=True
        )

    @app_commands.command(name="tts끄기", description="[관리자] TTS 기능을 끕니다 (설정은 유지됨)")
    @app_commands.default_permissions(administrator=True)
    async def disable_tts(self, interaction: discord.Interaction):
        if not _is_admin(interaction.user):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        conn = get_db()
        conn.execute("UPDATE tts_settings SET enabled=0 WHERE guild_id=?", (interaction.guild.id,))
        conn.commit()
        await interaction.response.send_message("✅ TTS를 껐습니다.", ephemeral=True)

    @app_commands.command(name="tts켜기", description="[관리자] TTS 기능을 다시 켭니다")
    @app_commands.default_permissions(administrator=True)
    async def enable_tts(self, interaction: discord.Interaction):
        if not _is_admin(interaction.user):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        conn = get_db()
        row = conn.execute("SELECT guild_id FROM tts_settings WHERE guild_id=?", (interaction.guild.id,)).fetchone()
        if not row:
            await interaction.response.send_message("먼저 `/설치-tts`로 채널을 지정해주세요.", ephemeral=True)
            return
        conn.execute("UPDATE tts_settings SET enabled=1 WHERE guild_id=?", (interaction.guild.id,))
        conn.commit()
        await interaction.response.send_message("✅ TTS를 켰습니다.", ephemeral=True)

    @app_commands.command(name="tts나가기", description="[관리자] 봇을 음성채널에서 즉시 내보냅니다")
    @app_commands.default_permissions(administrator=True)
    async def leave_tts(self, interaction: discord.Interaction):
        if not _is_admin(interaction.user):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect(force=True)
            await interaction.response.send_message("✅ 음성채널에서 나갔습니다.", ephemeral=True)
        else:
            await interaction.response.send_message("현재 음성채널에 접속해 있지 않습니다.", ephemeral=True)

    @app_commands.command(name="tts목소리", description="[관리자] TTS 목소리를 변경합니다")
    @app_commands.choices(목소리=[app_commands.Choice(name=label, value=v) for label, v in AVAILABLE_VOICES.items()])
    @app_commands.default_permissions(administrator=True)
    async def set_tts_voice(self, interaction: discord.Interaction, 목소리: app_commands.Choice[str]):
        if not _is_admin(interaction.user):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO tts_voice_settings (guild_id, voice) VALUES (?, ?)", (interaction.guild.id, 목소리.value))
        conn.commit()
        await interaction.response.send_message(f"✅ TTS 목소리를 **{목소리.name}**(으)로 변경했습니다.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TTSCog(bot))
