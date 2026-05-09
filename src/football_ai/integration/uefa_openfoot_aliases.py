"""Map Polish Flashscore display names toward OpenFootball plaintext club labels (deterministic joins)."""

from __future__ import annotations

from football_ai.integration.normalize import norm_club

# Keys: ``norm_club`` of Flashscore PL (or shorthand) labels; values: OpenFootball name before ``(CTR)`` strip.
_FLASH_TO_OF: dict[str, str] = {
    "ajax": "AFC Ajax",
    "arsenal": "Arsenal FC",
    "atalanta": "Atalanta BC",
    "ath. bilbao": "Athletic Club",
    "athletic bilbao": "Athletic Club",
    "atl. madryt": "Club Atlético de Madrid",
    "barcelona": "FC Barcelona",
    "fcb": "FC Barcelona",
    "bayern monachium": "FC Bayern München",
    "benfica": "Sport Lisboa e Benfica",
    "bodø/glimt": "FK Bodø/Glimt",
    "bodoe/glimt": "FK Bodø/Glimt",
    "bodo glimt": "FK Bodø/Glimt",
    "borussia dortmund": "Borussia Dortmund",
    "bayer leverkusen": "Bayer 04 Leverkusen",
    "bayer 04 leverkusen": "Bayer 04 Leverkusen",
    "club brugge": "Club Brugge KV",
    "chelsea": "Chelsea FC",
    "crvena zvezda": "FK Crvena zvezda",
    "eintracht frankfurt": "Eintracht Frankfurt",
    "galatasaray": "Galatasaray SK",
    "inter mediolan": "FC Internazionale Milano",
    "juventus": "Juventus FC",
    "liverpool": "Liverpool FC",
    "manchester city": "Manchester City FC",
    "monaco": "AS Monaco FC",
    "newcastle united": "Newcastle United FC",
    "olympiakos pireus": "PAE Olympiakos SFP",
    "psg": "Paris Saint-Germain FC",
    "psv": "PSV",
    "raków czestochowa": "Raków Czestochowa",
    "rakow czestochowa": "Raków Czestochowa",
    "real madryt": "Real Madrid CF",
    "royale union sg": "Royale Union Saint-Gilloise",
    "slavia praga": "SK Slavia Praha",
    "sporting": "Sporting Clube de Portugal",
    "sporting cp": "Sporting Clube de Portugal",
    "ssc napoli": "SSC Napoli",
    "tottenham": "Tottenham Hotspur FC",
    "fc porto": "FC Porto",
    "young boys": "BSC Young Boys",
    "copenhagen": "FC København",
    "kobenhavn": "FC København",
    "marseille": "Olympique de Marseille",
    "villarreal": "Villarreal CF",
    "nice": "OGC Nice",
}


def canonical_uefa_club_display(text: str) -> str:
    """If ``text`` is a known UEFA Flashscore Polish label, return an OpenFootball-friendly label."""
    key = norm_club(text or "")
    if not key:
        return text or ""
    return _FLASH_TO_OF.get(key, text or "")


def norm_club_uefa_flashscore_vs_openfoot(text: str) -> str:
    """Normalize for joining FS metadata rows to indexed OpenFootball plaintext."""
    return norm_club(canonical_uefa_club_display(text))
