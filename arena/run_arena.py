#!/usr/bin/env python3
"""AI 투자 아레나 — 페르소나 일일 실행기.

매 실행마다:
1) 만기 도달한 예측을 채점 (Stooq 무료 시세, 키 불필요)
2) 각 페르소나가 자신의 메모리·과거 성적을 읽고 새 예측 1건 생성 (Claude API)
3) 리더보드 갱신, 메모리에 교훈 축적

데이터는 전부 arena/data/·arena/memory/ 파일로 저장 → git 커밋이 곧 빅데이터 축적.
ANTHROPIC_API_KEY 없이 실행하면 채점·리더보드만 수행 (로컬 테스트용).
"""
import json
import os
import sys
import urllib.request
import datetime as dt

# Windows 콘솔(cp949)에서도 한글·특수문자 출력 가능하게
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
MEM = os.path.join(ROOT, "memory")
PRED_FILE = os.path.join(DATA, "predictions.json")
BOARD_FILE = os.path.join(DATA, "leaderboard.json")
MODEL = os.environ.get("ARENA_MODEL") or "claude-opus-4-8"
NOTIONAL = 1000  # 예측 1건당 가상 베팅액($)

TODAY = dt.date.today()


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


# ---------- 시세 (야후 파이낸스 차트 API — 무료, 키 불필요) ----------

def yahoo_symbol(ticker):
    return ticker.upper().replace(".", "-")  # BRK.B → BRK-B, ^GSPC는 그대로


def fetch_closes(ticker, d1, d2):
    """[(YYYY-MM-DD, close)] 오름차순. 실패 시 []."""
    ts1 = int(dt.datetime.combine(d1, dt.time.min, dt.timezone.utc).timestamp())
    ts2 = int(dt.datetime.combine(d2 + dt.timedelta(days=1), dt.time.min, dt.timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol(ticker)}"
           f"?period1={ts1}&period2={ts2}&interval=1d")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=20).read())
        res = data["chart"]["result"][0]
        stamps = res.get("timestamp") or []
        closes = res["indicators"]["quote"][0].get("close") or []
        out = []
        for t, c in zip(stamps, closes):
            if c is not None:
                day = dt.datetime.fromtimestamp(t, dt.timezone.utc).date()
                out.append((str(day), round(float(c), 4)))
        return out
    except Exception as e:
        print(f"  [시세실패] {ticker}: {e}", file=sys.stderr)
        return []


def latest_close(ticker):
    closes = fetch_closes(ticker, TODAY - dt.timedelta(days=14), TODAY)
    return closes[-1] if closes else None  # (date, price) | None


# ---------- 채점 ----------

def grade(preds):
    graded = 0
    for p in preds:
        if p["status"] != "open" or p["end_date"] > str(TODAY):
            continue
        end = dt.date.fromisoformat(p["end_date"])
        closes = fetch_closes(p["ticker"], end - dt.timedelta(days=10), end)
        if not closes:
            p["status"] = "void"
            continue
        end_price = closes[-1][1]
        move = (end_price / p["start_price"] - 1) * 100  # 실제 등락 %
        correct = (move > 0) == (p["direction"] == "up")
        p["end_price"] = round(end_price, 4)
        p["move_pct"] = round(move, 2)
        # 예측 방향대로 $1000 베팅했을 때의 수익률
        p["return_pct"] = round(move if p["direction"] == "up" else -move, 2)
        p["status"] = "correct" if correct else "wrong"
        p["graded_at"] = str(TODAY)
        graded += 1
        print(f"  [채점] {p['persona']} {p['ticker']} {p['direction']} → "
              f"{p['status']} (실제 {move:+.1f}%)")
    return graded


# ---------- 리더보드 ----------

def build_leaderboard(preds, personas):
    board = {}
    for key, meta in personas.items():
        mine = [p for p in preds if p["persona"] == key]
        done = [p for p in mine if p["status"] in ("correct", "wrong")]
        hits = [p for p in done if p["status"] == "correct"]
        points = sum(p["confidence"] if p["status"] == "correct" else -p["confidence"]
                     for p in done)
        pnl = sum(p["return_pct"] / 100 * NOTIONAL for p in done)
        board[key] = {
            "name": meta["name"], "emoji": meta["emoji"], "color": meta["color"],
            "style": meta["style"],
            "points": points,
            "graded": len(done), "hits": len(hits),
            "hit_rate": round(len(hits) / len(done) * 100, 1) if done else None,
            "virtual_pnl": round(pnl, 2),
            "open": sum(1 for p in mine if p["status"] == "open"),
            "total": len(mine),
        }
    return {"updated": str(TODAY), "notional": NOTIONAL, "personas": board}


# ---------- 페르소나 턴 (Claude) ----------

SCHEMA = {
    "type": "object",
    "properties": {
        "predictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "horizon_days": {"type": "integer"},
                    "confidence": {"type": "integer"},
                    "rationale": {"type": "string"},
                },
                "required": ["ticker", "direction", "horizon_days", "confidence", "rationale"],
                "additionalProperties": False,
            },
        },
        "market_view": {"type": "string"},
        "memory_update": {"type": "string"},
    },
    "required": ["predictions", "market_view", "memory_update"],
    "additionalProperties": False,
}


def market_snapshot():
    lines = []
    for sym, label in [("^GSPC", "S&P 500"), ("^NDX", "나스닥100")]:
        closes = fetch_closes(sym, TODAY - dt.timedelta(days=14), TODAY)
        if len(closes) >= 2:
            chg = (closes[-1][1] / closes[-2][1] - 1) * 100
            wk = (closes[-1][1] / closes[0][1] - 1) * 100
            lines.append(f"- {label}: {closes[-1][1]:.1f} (전일 {chg:+.2f}%, 최근 2주 {wk:+.2f}%)")
    return "\n".join(lines) or "- (시장 스냅샷 조회 실패)"


def memory_path(key):
    return os.path.join(MEM, f"{key}.md")


def persona_turn(client, key, meta, preds, snapshot, board):
    mem = ""
    if os.path.exists(memory_path(key)):
        with open(memory_path(key), encoding="utf-8") as f:
            mem = f.read()[-4000:]  # 최근 교훈 위주
    mine = [p for p in preds if p["persona"] == key]
    open_preds = [f"- {p['ticker']} {p['direction']} (만기 {p['end_date']}, "
                  f"진입가 ${p['start_price']})" for p in mine if p["status"] == "open"]
    recent = [f"- {p['ticker']} {p['direction']} → {p['status']} (실제 {p.get('move_pct', 0):+.1f}%) "
              f"| 당시 근거: {p['rationale'][:80]}"
              for p in mine if p["status"] in ("correct", "wrong")][-5:]
    stats = board["personas"][key]

    prompt = f"""오늘은 {TODAY}. 너의 하루 1회 예측 시간이다.

[시장 스냅샷]
{snapshot}

[너의 성적] 채점 완료 {stats['graded']}건 중 적중 {stats['hits']}건, 점수 {stats['points']}점, 가상손익 ${stats['virtual_pnl']}
[진행 중인 예측]
{chr(10).join(open_preds) or '(없음)'}
[최근 채점 결과]
{chr(10).join(recent) or '(아직 없음)'}
[너의 투자 노트 (누적 메모리)]
{mem or '(첫 출전 — 아직 기록 없음)'}

임무: 너의 투자 철학에 충실하게, 미국 상장 자산(주식/ETF) 중 하나를 골라 **정확히 1건**의 방향 예측을 남겨라.
- horizon_days: 1~365 사이 (너의 스타일에 맞는 기간)
- confidence: 1(약한 확신)~5(강한 확신)
- rationale: 한국어 2~4문장. 왜 이 방향인지, 무엇이 틀리면 실패인지. (초보 투자자도 배울 수 있게)
- 이미 진행 중인 예측과 같은 종목·방향의 중복은 피하라
- market_view: 오늘 시장을 보는 너의 한 줄 관점 (한국어)
- memory_update: 오늘 기록할 교훈·관찰 1~2문장 (한국어). 최근 채점 결과에서 배운 점이 있으면 반드시 반영하라."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=meta["system_prompt"] + "\n\n너는 AI 투자 아레나의 경주마다. 예측은 실제 시세로 자동 채점되어 순위가 매겨진다. 오답은 감점이므로 확신 없는 베팅에 confidence를 낭비하지 마라.",
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if resp.stop_reason == "refusal":
        print(f"  [건너뜀] {meta['name']}: 응답 거부", file=sys.stderr)
        return
    out = json.loads(next(b.text for b in resp.content if b.type == "text"))

    for pr in out["predictions"][:1]:  # 하루 1건
        ticker = pr["ticker"].upper().strip()
        quote = latest_close(ticker)
        if not quote:
            print(f"  [건너뜀] {meta['name']}: {ticker} 시세 조회 실패", file=sys.stderr)
            continue
        horizon = max(1, min(365, int(pr["horizon_days"])))
        preds.append({
            "id": f"{key}-{TODAY}-{len(preds)}",
            "persona": key,
            "ticker": ticker,
            "direction": pr["direction"],
            "start_date": str(TODAY),
            "end_date": str(TODAY + dt.timedelta(days=horizon)),
            "horizon_days": horizon,
            "start_price": quote[1],
            "confidence": max(1, min(5, int(pr["confidence"]))),
            "rationale": pr["rationale"].strip(),
            "market_view": out["market_view"].strip(),
            "status": "open",
        })
        print(f"  [예측] {meta['name']}: {ticker} {pr['direction']} "
              f"{horizon}일 (확신 {pr['confidence']})")

    os.makedirs(MEM, exist_ok=True)
    with open(memory_path(key), "a", encoding="utf-8") as f:
        f.write(f"\n\n## {TODAY}\n시장관: {out['market_view'].strip()}\n"
                f"교훈: {out['memory_update'].strip()}")


def main():
    personas = load(os.path.join(ROOT, "personas.json"), {})
    preds = load(PRED_FILE, [])

    print(f"=== AI 아레나 {TODAY} ===")
    print(f"[1/3] 만기 예측 채점: {grade(preds)}건")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        import anthropic
        client = anthropic.Anthropic()
        snapshot = market_snapshot()
        board = build_leaderboard(preds, personas)  # 프롬프트용 중간 성적
        print(f"[2/3] 페르소나 예측 ({MODEL})")
        for key, meta in personas.items():
            try:
                persona_turn(client, key, meta, preds, snapshot, board)
            except Exception as e:
                print(f"  [오류] {meta['name']}: {e}", file=sys.stderr)
    else:
        print("[2/3] ANTHROPIC_API_KEY 없음 — 예측 생략 (채점·리더보드만)")

    dump(PRED_FILE, preds)
    dump(BOARD_FILE, build_leaderboard(preds, personas))
    print(f"[3/3] 저장 완료 — 누적 예측 {len(preds)}건")


if __name__ == "__main__":
    main()
