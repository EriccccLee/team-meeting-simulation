"""simulation/slack_collector.py 단위 테스트"""
import pytest
from simulation.slack_collector import generate_slug, _is_noise


# ── generate_slug ─────────────────────────────────────────────────────────────

def test_generate_slug_english_spaces():
    assert generate_slug("John Kim") == "johnkim"


def test_generate_slug_english_dots():
    assert generate_slug("john.kim") == "johnkim"


def test_generate_slug_korean():
    result = generate_slug("이창영")
    # unidecode 변환 결과 — 영소문자+숫자만 남아야 함
    assert result.isalnum()
    assert result == result.lower()
    assert len(result) > 0


def test_generate_slug_mixed():
    result = generate_slug("홍 Gil-dong")
    assert result.isalnum()
    assert result == result.lower()


def test_generate_slug_fallback_empty():
    # 변환 후 알파뉴메릭이 없으면 "member" 반환
    assert generate_slug("!!!") == "member"
    assert generate_slug("   ") == "member"


# ── _is_noise ─────────────────────────────────────────────────────────────────

def test_is_noise_empty():
    assert _is_noise("") is True
    assert _is_noise("   ") is True


def test_is_noise_pure_emoji():
    assert _is_noise("👍") is True
    assert _is_noise("😊😊😊") is True
    assert _is_noise("🎉🎊") is True


def test_is_noise_bare_mention_only():
    assert _is_noise("<@U012AB3CD>") is True
    assert _is_noise("<@U012AB3CD> <@U999XYZ>") is True


def test_is_noise_mention_with_text():
    # 멘션 + 실질 텍스트가 있으면 노이즈가 아님
    assert _is_noise("<@U012AB3CD> 확인했습니다") is False


def test_is_noise_too_short():
    assert _is_noise("네") is True   # 2자
    assert _is_noise("ok") is True   # 2자


def test_is_noise_normal_message():
    assert _is_noise("오늘 배포 일정 확인했어요") is False
    assert _is_noise("내일 오후로 확정입니다") is False
