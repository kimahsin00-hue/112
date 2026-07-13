"""
패널 watchdog cog.

원본의 /패널복구 명령어는 수동으로 눌러야 했고, 6개 패널(join/report/anon/qna/coupon/util)만
커버했습니다. 보스알림/축복·에다니아 제보/파티신청·캘린더/장기미접/인게임시간 패널은
복구 대상에서 아예 빠져 있었습니다.

이 cog는:
1. 10분마다 자동으로 panels.json에 기록된 모든 패널이 실제로 살아있는지 확인하고,
   사라진 게 있으면 자동으로 다시 만듭니다 (관리자가 아무것도 안 눌러도 됩니다).
2. 기존처럼 수동으로 즉시 확인하고 싶을 때 쓸 /패널복구 명령어도 유지합니다.

새 패널을 추가하는 cog는 PANEL_REGISTRY에 항목 하나만 추가하면 watchdog이 자동으로
그 패널도 감시 대상에 포함시킵니다. coupon/weekly_dm/chzzk_alert cog를 옮길 때
여기에 등록을 추가해주세요 (지금은 아직 마이그레이션 전이라 목록에 없습니다).
"""
import json
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import PANEL_FILE, ADMIN_ROLE_ID
from db import get_db, save_panel


def _is_admin(user: discord.Member) -> bool:
    return bool(getattr(user.guild_permissions, 'administrator', False)) or bool(user.get_role(ADMIN_ROLE_ID))


def _load_panel_data() -> dict:
    if os.path.exists(PANEL_FILE):
        try:
            with open(PANEL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


class PanelWatchdogCog(commands.Cog):
    """
    PANEL_REGISTRY: panel_name -> async 콜백(bot, channel) -> (embed_or_None, view)
    콜백은 '이 채널에 새로 보낼 패널의 embed와 view를 만들어서 돌려주는' 역할만 합니다.
    실제 전송/삭제/panels.json 갱신은 이 cog가 공통으로 처리합니다.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.panel_watchdog_loop.start()

    def cog_unload(self):
        self.panel_watchdog_loop.cancel()

    def _build_registry(self):
        """다른 cog들이 로드된 뒤에 호출해야 해서 __init__이 아니라 여기서 지연 구성합니다."""
        from cogs.bdo_time import BdoTimeView
        from cogs.boss_alert import SetupBossView
        from cogs.status_report import StatusViewPanel
        from cogs.tickets import SetupJoinView, QnaTicketView, ReportTicketView, AnonTicketView, AbsenceTicketView
        from cogs.party_system import PartyTicketView, PartyCalendarView, build_party_embed, build_calendar_embed
        from datetime import datetime
        from config import KST

        bot = self.bot

        async def _bdo_time(bot, channel):
            return discord.Embed(title="검은사막 인게임시간", color=0x2b2d31), BdoTimeView()

        async def _boss(bot, channel):
            e = discord.Embed(title="월드보스 시간표", description="월드보스 출현 일정 조회 및 개인 DM 알림 설정을 제공합니다.", color=0x2b2d31)
            return e, SetupBossView()

        async def _blessing(bot, channel):
            e = discord.Embed(title="아침의 축복 현황", description="하단 버튼을 통해 새로운 위치를 제보하거나 현황을 확인하세요.", color=0x2b2d31)
            return e, StatusViewPanel(bot, "blessing", "아침의 축복")

        async def _edana(bot, channel):
            e = discord.Embed(title="에다니아 현황", description="하단 버튼을 통해 새로운 위치를 제보하거나 현황을 확인하세요.", color=0x2b2d31)
            return e, StatusViewPanel(bot, "edana", "에다니아")

        async def _join(bot, channel):
            e = discord.Embed(title="📋 가입 상담", description="가입을 원하시면 아래 버튼을 눌러 상담 티켓을 생성해주세요.", color=0x3498db)
            return e, SetupJoinView()

        async def _qna(bot, channel):
            e = discord.Embed(title="💬 문의/건의", description="문의나 건의사항이 있으시면 아래 버튼을 눌러 티켓을 생성해주세요.", color=0x2ecc71)
            return e, QnaTicketView()

        async def _report(bot, channel):
            e = discord.Embed(title="🚨 불편사항 제보", description="불편사항이 있으시면 아래 버튼을 눌러 제보해주세요.", color=0xe74c3c)
            return e, ReportTicketView()

        async def _anon(bot, channel):
            e = discord.Embed(title="🕵️ 익명 제보", description="익명으로 제보하시려면 아래 버튼을 눌러주세요.", color=0x95a5a6)
            return e, AnonTicketView()

        async def _absence(bot, channel):
            e = discord.Embed(
                title="📋 장기미접 사유 신고",
                description="장기간 게임에 접속하지 못하는 경우 아래 버튼으로 사유를 남겨주세요.\n\n미접 기간과 사유를 입력하면 관리자에게 전달됩니다.",
                color=0xe67e22,
            )
            return e, AbsenceTicketView(bot)

        async def _party(bot, channel):
            e = build_party_embed()
            return e, PartyTicketView()

        async def _party_calendar(bot, channel):
            now = datetime.now(KST)
            e = build_calendar_embed(channel.guild.id, now.year, now.month)
            return e, PartyCalendarView()

        self.PANEL_REGISTRY = {
            "bdo_time": _bdo_time,
            "boss": _boss,
            "blessing": _blessing,
            "edana": _edana,
            "join": _join,
            "qna": _qna,
            "report": _report,
            "anon": _anon,
            "absence": _absence,
            "party": _party,
            "party_calendar": _party_calendar,
            # coupon, weekly_dm(패널 없음), chzzk_alert(패널 없음) — coupon 마이그레이션 시 여기 추가
        }

        # party/party_calendar는 patch DB 테이블도 같이 갱신해야 하므로 별도 매핑에 기록
        self._panel_db_table = {
            "party": ("party_panel", "guild_id", "channel_id", "message_id"),
            "party_calendar": ("party_calendar_panel", "guild_id", "channel_id", "message_id"),
        }

    async def _recreate_panel(self, name: str, channel: discord.abc.Messageable) -> bool:
        if not hasattr(self, "PANEL_REGISTRY"):
            self._build_registry()
        builder = self.PANEL_REGISTRY.get(name)
        if not builder:
            return False
        try:
            embed, view = await builder(self.bot, channel)
            msg = await channel.send(embed=embed, view=view)
            save_panel(name, msg)
            if name in self._panel_db_table:
                table, gcol, ccol, mcol = self._panel_db_table[name]
                conn = get_db()
                conn.execute(f"INSERT OR REPLACE INTO {table} ({gcol}, {ccol}, {mcol}) VALUES (?, ?, ?)", (channel.guild.id, channel.id, msg.id))
                conn.commit()
            return True
        except Exception as e:
            print(f"⚠️ 패널 '{name}' 재생성 실패: {e}")
            return False

    async def _check_all_panels(self, force_channel: discord.abc.Messageable = None) -> list:
        """
        모든 저장된 패널을 확인하고 사라진 것만 재생성합니다.
        force_channel이 주어지면(수동 /패널복구), 기록이 아예 없는 패널도 그 채널에 새로 만듭니다.
        반환값: 사람이 읽을 결과 로그 리스트
        """
        if not hasattr(self, "PANEL_REGISTRY"):
            self._build_registry()

        data = _load_panel_data()
        results = []

        names_to_check = set(self.PANEL_REGISTRY.keys())
        for name in names_to_check:
            entry = data.get(name)
            if entry:
                channel_id, message_id = entry
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        await channel.fetch_message(message_id)
                        continue  # 살아있음 — 건드릴 필요 없음
                    except discord.NotFound:
                        pass  # 메시지가 삭제됨 → 아래에서 재생성
                    except Exception as e:
                        print(f"⚠️ 패널 '{name}' 확인 중 오류(건너뜀): {e}")
                        continue
                    ok = await self._recreate_panel(name, channel)
                    results.append(f"{'✅ 자동 재생성' if ok else '❌ 재생성 실패'}: {name} ({channel.mention})")
                else:
                    # 채널 자체가 사라짐 — force_channel이 있을 때만(수동 복구 시) 새 채널에 만들어줌
                    if force_channel:
                        ok = await self._recreate_panel(name, force_channel)
                        results.append(f"{'✅ 채널 없음 → 새 채널에 생성' if ok else '❌ 실패'}: {name}")
            elif force_channel:
                # 기록 자체가 없음 (한 번도 설치 안 함) — 수동 복구일 때만 현재 채널에 생성
                ok = await self._recreate_panel(name, force_channel)
                results.append(f"{'✅ 신규 생성' if ok else '❌ 실패'}: {name}")

        return results

    @tasks.loop(minutes=10)
    async def panel_watchdog_loop(self):
        results = await self._check_all_panels()
        if results:
            print("🐕 패널 watchdog 자동 복구:\n" + "\n".join(results))

    @panel_watchdog_loop.before_loop
    async def _before_watchdog(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="패널복구", description="[관리자] 사라진 패널을 즉시 확인하고 복구합니다")
    @app_commands.default_permissions(administrator=True)
    async def cmd_panel_recover(self, interaction: discord.Interaction):
        if not _is_admin(interaction.user):
            await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        results = await self._check_all_panels(force_channel=interaction.channel)
        if not results:
            await interaction.followup.send("✅ 모든 패널이 정상입니다. 복구할 항목이 없습니다.", ephemeral=True)
        else:
            await interaction.followup.send("패널 점검 결과:\n" + "\n".join(results), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelWatchdogCog(bot))
