# CLAUDE.md — Invest Workbench

미국시장 학습용 대시보드 + 데모 트레이딩 + 매매일지. **단일 `index.html`** 하나가 앱 전체다 — 서버·빌드·의존성 없음. GitHub Pages로 배포됨 (`gbbackhome.github.io/invest-workbench/`).

## 세션 컨텍스트

- 어시스턴트 애칭은 **아스라다(ASURADA)** — 신세기 사이버 포뮬러의 AI에서 딴 이름. 대화는 한국어, 편하고 실용적인 톤.
- 소유자(경배님, GitHub: gbbackhome)는 데이터/마케팅 전략가이자 주식 초보 학습자. UI 문구·설명은 쉬운 한국어로, 금융 용어는 풀어서.
- 관련 저장소: gbbackhome.github.io(포트폴리오), amc-workbench(DSP 툴), Projects, gb-s-portfolio — 각각 CLAUDE.md 있음.

## 절대 규칙

- **API 키는 절대 커밋 금지.** repo가 public이다. Finnhub 키와 Claude API 키 모두 사용자가 페이지 "설정"에서 입력 → 브라우저 localStorage에만 저장. 코드·README·커밋 메시지 어디에도 실제 키를 넣지 말 것. 커밋 전 키 패턴 스캔.
- 아스라다 챗봇은 브라우저에서 Claude API 직접 호출 (`anthropic-dangerous-direct-browser-access` 헤더, 기본 모델 claude-opus-4-8, adaptive thinking). 챗봇 시스템 프롬프트는 종목 추천 금지·교육 목적 유지 — 이 제약을 풀지 말 것. 멀티턴 히스토리는 응답 content 배열을 원본 그대로 보존해야 함 (thinking 블록 포함).
- 사용자 데이터(계좌·매매일지·키)는 전부 localStorage(`invest-workbench-v1`)에만 존재. 서버로 보내는 코드 추가 금지.
- 단일 HTML 유지 — 빌드 도입은 경배님과 상의 후.
- 교육용 시뮬레이터 정체성 유지 — 투자 권유로 읽힐 문구 금지, 하단 면책 문구 유지.

## 학습 철학 (설계에 반영됨 — 약화 금지)

이 툴의 목적은 수익이 아니라 **매매 습관 훈련**:
1. 진입 전 "왜"를 문장으로 — 주문 다이얼로그에서 근거 10자 이상 필수 입력 (이 툴의 존재 이유, 선택사항으로 바꾸지 말 것)
2. 청산 후 복기 남기기 (일지 복기 칸)
3. 데모 수익 ≠ 실력 (실전 심리 빠짐) — UI 곳곳 경고 유지
- 미국엔 상·하한가 없음(한국 제도) — 학습 포인트는 지지/저항·갭·거래량·근거 있는 매매
- 페니스톡 급등(예: WHLR +76%)은 수급 게임 — 학습 대상 비추천 안내 유지
- "이유를 모르면 내 돈이 이유"

## 디자인 (Variant 시안 기준 — 유지)

- 순수 블랙(#000) 배경 + 진회색 카드(#0f1013), radius 18px, 토스증권 다크 느낌, Pretendard 계열, 파랑 액센트 #3182f6
- **빨강 = 상승(--up), 파랑 = 하락(--down)** — 한국 컨벤션, 절대 뒤집지 말 것
- 레이아웃 순서: 상단 슬림 티커 스트립 → 좌측 큰 차트 + 섹터 히트맵 / 우측 Trending Stocks + Economic Calendar → 내부자 동향 → 데모 트레이딩 → 설정
- 학습 사이드노트는 `details.edu` 아코디언 + `ℹ️/⚠️` note 박스 스타일 — 새 섹션 추가 시 같은 스타일의 학습 노트를 함께 붙이는 것이 이 버전의 방향

## 구조 (index.html 내부, v3)

| 영역 | 구현 | 키 필요 |
|---|---|---|
| 티커 스트립·차트·Trending·히트맵·경제캘린더 | TradingView 임베드 위젯 (`mountTV()`) | ❌ |
| 시세 조회·"이 종목 왜 떠?" 뉴스(`loadNews()`)·내부자 매매(SEC Form 4) | Finnhub REST (`fh()` 헬퍼, 무료 티어 분당 60회) | ✅ |
| 계좌·포지션·매매일지·복기·CSV 내보내기 | 순수 JS + localStorage | ❌ |

- 상태 객체(v2, 멀티 프로필): `S = {profiles:[{name,cash,positions,trades}], active, key}` — localStorage 키 `invest-workbench-v2`, 구버전 v1은 로드 시 자동 이전. `P()`가 활성 프로필. 스키마 변경 시 기존 데이터 마이그레이션 필수.
- **데모 트레이딩이 이 프로젝트의 최우선 영역** (경배님 지시) — 멀티 프로필로 여러 사람이 겨루는 구조, 리더보드 포함. 개선 우선순위를 여기에 둘 것.
- ⚠️ 테이블 데이터 행을 지울 땐 반드시 `clearRows()` 사용 — `insertAdjacentHTML`로 넣은 `<tr>`은 별도 tbody에 들어가서 `tr:not(:first-child)` 선택자로는 안 지워짐 (행 중복 버그의 원인이었음).
- v3 학습 콘텐츠: 급등/급락 이유 8가지 가이드, 경제지표 사이드노트 8개(NFP·평균임금·CPI·FOMC·실업수당·PMI·GDP·소비자심리), 핵심 원리 = "예상치 대비 서프라이즈" + "좋은 뉴스가 나쁜 뉴스"
- 한국어 로케일: TradingView `locale:'kr'`, 타임존 `Asia/Seoul`.

## 다음 단계 백로그 (경배님과 논의된 방향)

- 지정가/손절가 주문 (현재 시장가만)
- 일지 통계 대시보드 — 셋업 태그별 승률, 요일/시간대 분석 (CSV → 파이썬 분석 연계 좋음, 경배님이 데이터 분석가)
- 관심종목(워치리스트) 카드
- 호가창 느낌의 주문 UI
- 포트폴리오 손익 차트 (일별 스냅샷 localStorage 누적)

## 작업 방식

- 파일이 하나뿐이므로 수정 후 브라우저에서 직접 열어 확인 (빌드 불필요). main에 푸시하면 Pages에 곧 반영.
- 미국 제도 관련 학습 노트 추가·수정 시 사실 확인 필수 (LULD 서킷브레이커, Form 4 공시 기한 등).
- git identity는 이 저장소에 로컬 설정돼 있음 (gbbackhome / gyeongbae311@gmail.com).
