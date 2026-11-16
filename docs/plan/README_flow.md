흐름 그림 원본 (2026.11.16, 고친 기록 P-097까지 들어간 코드 기준 · 최종 구성 D + 규칙 분류)

| 파일 | 그림 |
|---|---|
| flow_full | 전체본: 모든 분기를 한 장에 |
| flow_summary | 한 장 요약: 노드 단위 |
| flow_summary_slide | 한 장 요약의 슬라이드용 (칸 안 설명을 뺌) |
| flow_unknown_word | 사전에서 못 찾은 말의 네 갈래 (요약) |
| flow_unknown_word_detail | 사전에서 못 찾은 말 (코드 그대로) |
| flow_answer | 답변 생성 칸 안 |
| flow_after_ask | 되묻기 · 설명 뒤 다음 턴 |

- 파란 칸은 LLM이 판단해 길이 갈리는 곳, 회색 칸은 코드가 가르는 곳, 흰 칸은 하는 일과 나가는 문장
- 다시 그리기 (mermaid-cli 11): `mmdc -i flow_full.mmd -o flow_full.png -c mermaid_config.json -C mermaid_style.css -s 2 -b white -w 2000`
- 슬라이드용은 `-c mermaid_config_slide.json -w 1600`

---

**GitHub 그림으로 보기**

아래는 같은 원본(.mmd)을 GitHub가 직접 그린 그림입니다. 그림 오른쪽 아래 버튼으로 확대 · 이동할 수 있습니다. PNG는 위 표의 파일 그대로입니다.

**flow_full** · 전체본: 모든 분기를 한 장에 ([PNG](flow_full.png))

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "Noto Sans CJK KR, Noto Sans KR, sans-serif", "fontSize": "15px", "primaryColor": "#ffffff", "primaryBorderColor": "#9aa3b5", "primaryTextColor": "#1f2430", "lineColor": "#7d879c", "edgeLabelBackground": "#ffffff", "clusterBkg": "#f7f8fb", "clusterBorder": "#b8bfcc", "tertiaryColor": "#ffffff"}, "flowchart": {"curve": "linear", "htmlLabels": true, "nodeSpacing": 34, "rankSpacing": 42, "padding": 10, "wrappingWidth": 400}, "layout": "elk", "elk": {"mergeEdges": false, "nodePlacementStrategy": "BRANDES_KOEPF"}, "themeCSS": ".node .label {line-height:1.35} .edgeLabel {font-size:13px; color:#4b5363} .cluster-label {font-weight:700}"}}%%
flowchart TD
    Q(["사용자 질문"]) --> N0["<b>0 질문 재구성</b><br/><small>앞 대화 3턴으로 생략·지시어를 채움 (앞 대화가 있을 때만 LLM)</small>"]
    N0 --> N1["<b>1 사전 정규화</b><br/><small>은어·종목 약어·오타·관용구를 사전으로 풀어 덧붙임 · 원문은 그대로</small>"]
    N1 -->|"앞 턴이 되묻기로 끝남"| A0
    N1 -->|"앞 턴이 사전 밖 용어를 설명했고<br/>이번 말이 '…래'"| UT
    N1 -->|"그 밖"| R1

    subgraph S2A["2 LLM 정규화 칸 안 · 되묻기 · 설명 뒤 다음 턴&nbsp;&nbsp;"]
        UT["<b>사용자 설명으로 적음 (코드)</b><br/><small>LLM을 부르지 않음</small>"]
        A0("이번에 사용자가 한 말<br/><small>정해 둔 짧은 대답인가 (코드)</small>")
        A0 -->|"'맞아요'<br/>앞 턴이 후보 하나를 물었음"| A1["그 후보를 확인된 오타로 적음<br/><small>빛투 → 빚투</small>"]
        A0 -->|"그 밖<br/>(뜻을 알려 줌, 다른 질문)"| A2["<b>LLM 정규화</b><br/><small>사용자가 알려 준 뜻은 '사용자 설명'으로 적음</small>"]
    end
    A0 -->|"몰라요"| N9X["<b>9 확인 못 함</b><br/><small>'○○'는 저도 확인된 뜻을 찾지 못했어요.<br/>다시 묻지 않고 끝냄</small>"]
    A0 -->|"다른 뜻이에요<br/>확인할 후보가 없는 '맞아요'"| N9B["<b>9 다시 묻기</b><br/><small>어떤 뜻으로 들으셨는지 알려주시면<br/>이어서 설명해드릴게요.</small>"]
    A1 --> R1
    UT --> R1
    A2 -->|"풀림"| R1
    A2 -->|"뜻을 확인하지 못함"| N9Q

    subgraph S3["3 의도 분류 칸 안"]
        R1("자살·자해 위험 표현인가<br/><small>규칙 (죽고 싶다 등)</small>")
        R1 -->|"아니오"| R2("앞 턴이 되묻기가 아니고<br/>이번 말이 '맞아요'·'네'뿐인가<br/><small>규칙</small>")
        R2 -->|"아니오"| R3("뜻만 묻는 단순 질문<br/>+ 사전 용어인가<br/><small>규칙</small>")
        R3 -->|"아니오"| L3["<b>LLM 의도 분류</b><br/><small>용어 설명 / 매매 판단 요청 / 범위 밖<br/>설명할 용어와 종목도 뽑음</small>"]
        L3 --> C3["<b>코드가 한 번 더 봄</b><br/><small>· 용어 설명인데 사고팔기 판단을 묻는 꼴 → 매매 판단 요청<br/>· 되묻기 · 설명 뒤 뜻을 알려 준 답을 하소연·범위 밖으로 고름 → 용어 설명<br/>· 위험 표현으로 고른 근거가 민감 관용구뿐 → 다시 분류<br/>&nbsp;&nbsp;(그래도 위험 표현이고 사고팔기 질문이면 매매 판단 요청)<br/>· 용어 설명인데 용어를 못 뽑음 → '○○이 뭐야?'의 ○○을 용어로<br/>· 뽑은 용어를 질문 글자와 대조: 사전이 오타로 이은 말은 고친 사전 말로,<br/>&nbsp;&nbsp;질문에 오타로 쓴 말은 오타 확인 문구</small>"]
    end
    L3 -->|"정해진 형식으로<br/>두 번 답하지 못함"| N8
    R1 -->|"예"| N8H["<b>8 상담 안내 고정 문구</b><br/><small>자살예방 상담전화(109)</small>"]
    R2 -->|"예 (짧은 수긍)"| N8S["<b>8 짧은 수긍 고정 문구</b><br/><small>네, 더 궁금한 주식 용어가 있으면 물어봐 주세요.</small>"]
    R3 -->|"예 → 용어 설명"| N4
    C3 -->|"용어 설명<br/>매매 판단 + 용어 있음"| N4["<b>4 용어 사전 조회</b><br/><small>표준 용어 이름과 정확히 일치할 때만</small>"]
    C3 -->|"매매 판단, 용어 없음"| W0
    C3 -->|"하소연"| V5
    C3 -->|"범위 밖 (일반 · 불법·유해)"| N8["<b>8 범위 밖 고정 문구</b><br/><small>주식 용어 설명만 다룬다고 안내</small>"]
    C3 -->|"자살·자해 위험 표현"| N8H

    N4 -->|"사전에 없는 용어가 있음<br/>(한 턴에 한 번만)"| D0
    N4 -->|"모두 사전에 있음<br/>또는 LLM 정규화를 이미 거침"| W0

    subgraph S2B["2 LLM 정규화 칸 안 · 조회에서 못 찾은 용어&nbsp;&nbsp;"]
        D0("사전 말 그대로이거나<br/>은어·종목 약어와 자모 하나 차이인가<br/><small>코드</small>")
        D0 -->|"아니오"| DL["<b>LLM 정규화</b><br/><small>확신 / 짐작 / 모름 / 기본 어휘 중 하나로 적음</small>"]
        DL --> D1("LLM 풀이 안에 사전 말이 있고<br/>원래 글자와 자모가 가까운가<br/><small>코드 · 숀졀 = 손해를 보고 팖(손절)</small>")
        D1 -->|"아니오"| D2("LLM이 어떻게 적었나")
        D2 -->|"확신으로 풂"| D3("자모가 가까운<br/>은어·종목 약어가 있는가<br/><small>코드</small>")
        D2 -->|"기본 어휘<br/>(고가, 미수)"| DK["오타로 보지 않음"]
        D2 -->|"짐작 · 모름<br/>어느 칸에도 없음"| D4("사전 말과 자모가 가까운가<br/><small>코드</small>")
        D4 -->|"가까운 말 없음"| D5("짐작 또는 모름으로 적었나")
        D3 -->|"없음"| PASS["<b>답변으로 넘김</b><br/><small>확신이면 풀이를 붙임<br/>↩ 3 의도 분류 → 4 조회 → 5 답변</small>"]
        DK --> PASS
        D5 -->|"어느 칸에도 없음"| PASS
    end
    D0 -->|"예"| LK["<b>사전으로 잇기 + 오타 확인 문구</b><br/><small>'익쩔'을 '익절'로 보고 설명드릴게요.<br/>↩ 3 의도 분류 → 4 조회 → 5 답변 (사전 설명으로)</small>"]
    D1 -->|"예"| LK
    D4 -->|"표준 용어와<br/>자모 하나 차이"| LK
    D3 -->|"하나 또는 둘"| N9C["<b>9 후보를 보여 주며 되묻기</b><br/><small>혹시 '떡상'을 말씀하신 건가요?</small>"]
    D4 -->|"후보 둘 · 자모 둘 차이"| N9C
    D5 -->|"예"| N9Q["<b>9 되묻기 (뜻을 말하지 않음)</b><br/><small>'○○'는 확인되지 않은 단어예요.<br/>어떤 뜻으로 들으셨는지 알려주시면…</small>"]

    subgraph S5["5 답변 생성 칸 안"]
        V5["<b>하소연</b><br/><small>공감 한 문장 (LLM)<br/>+ 서비스 안내 · 용어 제안 (고정 문장)</small>"]
        W0["<b>LLM 답변</b><br/><small>응답 정책대로 · 매매 판단을 묻는 질문이면<br/>분류와 상관없이 첫 문장에 판단 불가 안내</small>"]
        W0 --> W1("LLM이 뜻을 아는가")
        W1 -->|"앎"| W2["<b>문장 조립 (코드)</b><br/><small>· 사전 밖 용어: 사전 밖 안내 첫 문장<br/>· 오타로 읽은 말: 오타 확인 문구<br/>· 사용자가 알려 준 뜻: 들은 뜻으로 받음</small>"]
        W1 -->|"모름 표시"| W3["<b>되묻기 문장으로 바꿈 (코드)</b><br/><small>매매 판단이면 판단 불가 안내를 앞에</small>"]
    end
    V5 --> N6
    W2 --> N6
    W3 --> N6
    N6("<b>6 검수</b><br/><small>답과 질문을 함께 봄</small>")
    N6 -->|"위반: 5로 돌아가<br/>다시 쓰기 (2번까지)"| W0
    N6 -->|"위반 · 하소연:<br/>공감 한 문장을 다시"| V5
    N6 -->|"2번 뒤에도 위반"| N7("<b>7 안전 답변</b><br/><small>남은 위반이 판단 불가 안내 누락뿐인가</small>")
    N7 -->|"예"| N7A["안내 문장을 앞에 붙여<br/>답을 내보냄"]
    N7 -->|"아니오"| N7B["안전 답변 고정 문구"]
    N6 -->|"통과"| F
    N7A --> F
    N7B --> F
    N8 --> F
    N8H --> F
    N8S --> F
    N9X --> F
    N9B --> F
    N9C --> F
    N9Q --> F
    F(["<b>끝</b><br/><small>민감 표현 · 약한 위험 표현(죽을 것 같다 등)이 있으면<br/>상담 안내 한 문장을 붙임 (109 안내가 이미 있으면 빼고)<br/>대화 기억에 저장 (되묻기·설명으로 끝났는지 남김 → 다음 턴의 갈래)</small>"])

    classDef llm fill:#eef3ff,stroke:#1d4ed8,stroke-width:2.5px,color:#1d4ed8
    classDef dec fill:#f3f4f7,stroke:#9aa3b5,stroke-width:1.2px
    classDef ask fill:#fffdf5,stroke:#b58a1b,stroke-width:1.2px
    class A0,R1,R2,R3,D0,D1,D2,D3,D4,D5,W1,N6,N7 dec
    class A2,L3,DL,D2,W0,W1,N6 llm
```

**flow_summary** · 한 장 요약: 노드 단위 ([PNG](flow_summary.png))

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "Noto Sans CJK KR, Noto Sans KR, sans-serif", "fontSize": "15px", "primaryColor": "#ffffff", "primaryBorderColor": "#9aa3b5", "primaryTextColor": "#1f2430", "lineColor": "#7d879c", "edgeLabelBackground": "#ffffff", "clusterBkg": "#f7f8fb", "clusterBorder": "#b8bfcc", "tertiaryColor": "#ffffff"}, "flowchart": {"curve": "linear", "htmlLabels": true, "nodeSpacing": 34, "rankSpacing": 42, "padding": 10, "wrappingWidth": 400}, "layout": "elk", "elk": {"mergeEdges": false, "nodePlacementStrategy": "BRANDES_KOEPF"}, "themeCSS": ".node .label {line-height:1.35} .edgeLabel {font-size:13px; color:#4b5363} .cluster-label {font-weight:700}"}}%%
flowchart TD
    N0["<b>0 질문 재구성</b><br/><small>사용자 질문 · 앞 대화 3턴으로 채움</small>"] --> N1["<b>1 사전 정규화</b><br/><small>은어·종목 약어·오타·관용구</small>"]
    N1 -->|"앞 턴이 되묻기<br/>설명 뒤 '…래'"| N2
    N1 -->|"그 밖"| N3["<b>3 의도 분류</b><br/><small>규칙이 먼저 받는 말 있음</small>"]
    N3 -->|"용어 있음"| N4["<b>4 용어 사전 조회</b>"]
    N4 -->|"사전에 없는 용어<br/>(한 턴에 한 번만)"| N2["<b>2 LLM 정규화</b><br/><small>사전으로 다시 잇기 + LLM</small>"]
    N2 -->|"풀림"| N3
    N2 -->|"모르는 말 · 오타 후보<br/>되묻기 뒤 짧은 대답"| N9["<b>9 되묻기</b><br/><small>매매 판단이면 판단 불가 안내 먼저</small>"]
    N4 -->|"모두 사전에 있음"| N5["<b>5 답변 생성</b><br/><small>매매 판단을 묻는 질문이면<br/>첫 문장에 판단 불가 안내</small>"]
    N3 -->|"매매 판단<br/>용어 없음"| N5
    N3 -->|"하소연"| N5C["<b>5 공감 한 문장</b><br/><small>+ 서비스 안내 · 용어 제안</small>"]
    N3 -->|"범위 밖<br/>설명 뒤 짧은 수긍"| N8["<b>8 범위 밖 고정 문구</b>"]
    N3 -->|"자살·자해 위험 표현<br/>(규칙)"| N8H["<b>8 상담 안내 고정 문구</b><br/><small>상담전화 109</small>"]
    N5 --> N6["<b>6 검수</b><br/><small>답과 질문을 함께 봄</small>"]
    N5C --> N6
    N6 -->|"위반: 다시 쓰기<br/>2번까지"| N5
    N6 -->|"위반 · 하소연"| N5C
    N6 -->|"2번 뒤에도 위반"| N7["<b>7 안전 답변</b><br/><small>안내만 빠졌으면 안내를 붙임<br/>그 밖이면 고정 문구</small>"]
    N6 -->|"통과"| F(["<b>끝</b><br/><small>민감 · 약한 위험 표현이면 상담 안내 한 문장<br/>(109 안내가 있으면 빼고) · 대화 기억에 저장</small>"])
    N7 --> F
    N8 --> F
    N8H --> F
    N9 --> F
    classDef llm fill:#eef3ff,stroke:#1d4ed8,stroke-width:2.5px,color:#1d4ed8
    class N3,N6 llm
```

**flow_summary_slide** · 한 장 요약의 슬라이드용 (칸 안 설명을 뺌) ([PNG](flow_summary_slide.png))

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "Noto Sans CJK KR, Noto Sans KR, sans-serif", "fontSize": "18px", "primaryColor": "#ffffff", "primaryBorderColor": "#9aa3b5", "primaryTextColor": "#1f2430", "lineColor": "#7d879c", "edgeLabelBackground": "#ffffff", "clusterBkg": "#f7f8fb", "clusterBorder": "#b8bfcc", "tertiaryColor": "#ffffff"}, "flowchart": {"curve": "linear", "htmlLabels": true, "nodeSpacing": 28, "rankSpacing": 30, "padding": 10, "wrappingWidth": 400}, "layout": "elk", "elk": {"mergeEdges": false, "nodePlacementStrategy": "BRANDES_KOEPF"}, "themeCSS": ".node .label {line-height:1.35} .edgeLabel {font-size:13px; color:#4b5363} .cluster-label {font-weight:700}"}}%%
flowchart TD
    N0["<b>0 질문 재구성</b>"] --> N1["<b>1 사전 정규화</b>"]
    N1 -->|"앞 턴이 되묻기 · 설명 뒤 '…래'"| N2
    N1 -->|"그 밖"| N3["<b>3 의도 분류</b>"]
    N3 -->|"용어 있음"| N4["<b>4 용어 사전 조회</b>"]
    N4 -->|"사전에 없는 용어"| N2["<b>2 LLM 정규화</b>"]
    N2 -->|"풀림"| N3
    N2 -->|"모르는 말 · 오타 후보"| N9["<b>9 되묻기</b>"]
    N4 -->|"모두 사전에 있음"| N5["<b>5 답변 생성</b>"]
    N3 -->|"매매 판단, 용어 없음"| N5
    N3 -->|"하소연"| N5C["<b>5 공감 한 문장</b>"]
    N3 -->|"범위 밖 · 짧은 수긍"| N8["<b>8 범위 밖 고정 문구</b>"]
    N3 -->|"자살·자해 위험 표현"| N8H["<b>8 상담 안내 109</b>"]
    N5 --> N6["<b>6 검수</b>"]
    N5C --> N6
    N6 -->|"위반: 2번까지 다시 쓰기"| N5
    N6 -->|"위반 · 하소연"| N5C
    N6 -->|"2번 뒤에도 위반"| N7["<b>7 안전 답변</b>"]
    N6 -->|"통과"| F(["<b>끝</b> · 대화 기억에 저장"])
    N7 --> F
    N8 --> F
    N8H --> F
    N9 --> F
    classDef llm fill:#eef3ff,stroke:#1d4ed8,stroke-width:2.5px,color:#1d4ed8
    class N3,N6 llm
```

**flow_unknown_word** · 사전에서 못 찾은 말의 네 갈래 (요약) ([PNG](flow_unknown_word.png))

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "Noto Sans CJK KR, Noto Sans KR, sans-serif", "fontSize": "15px", "primaryColor": "#ffffff", "primaryBorderColor": "#9aa3b5", "primaryTextColor": "#1f2430", "lineColor": "#7d879c", "edgeLabelBackground": "#ffffff", "clusterBkg": "#f7f8fb", "clusterBorder": "#b8bfcc", "tertiaryColor": "#ffffff"}, "flowchart": {"curve": "linear", "htmlLabels": true, "nodeSpacing": 34, "rankSpacing": 42, "padding": 10, "wrappingWidth": 400}, "layout": "elk", "elk": {"mergeEdges": false, "nodePlacementStrategy": "BRANDES_KOEPF"}, "themeCSS": ".node .label {line-height:1.35} .edgeLabel {font-size:13px; color:#4b5363} .cluster-label {font-weight:700}"}}%%
flowchart TD
    A["<b>조회에서 못 찾은 용어</b>"] --> B("<b>사전 말과 글자가 가까운가</b><br/><small>코드</small>")
    B -->|"가깝고 후보가 하나<br/>(자모 하나 차이)"| R1["<b>① 사전으로 잇기 + 오타 확인 문구</b><br/><small>'익쩔'을 '익절'로 보고 설명드릴게요.</small>"]
    B -->|"가깝지만 확실하지 않음<br/>(후보 둘, 또는 자모 둘 차이)"| R2["<b>② 후보를 보여 주며 되묻기</b><br/><small>혹시 '떡상'을 말씀하신 건가요?</small>"]
    B -->|"가까운 말 없음"| C("<b>LLM이 뜻을 아는가</b><br/><small>확신 / 짐작 / 모름 / 기본 어휘 중 하나로 적음</small>")
    C -->|"확신 · 기본 어휘"| R3["<b>③ 사전 밖 안내 + 단정하지 않는 설명</b><br/><small>첫 문장은 코드가 붙임<br/>'상폐'는 사전에 등록되지 않은 용어라<br/>일반적인 설명으로 안내해요.<br/>+ 공식 자료 확인</small>"]
    C -->|"짐작 · 모름"| R4["<b>④ 뜻을 말하지 않고 되묻기</b><br/><small>'○○'는 확인되지 않은 단어예요.<br/>어떤 뜻으로 들으셨는지 알려주시면<br/>이어서 설명해드릴게요.</small>"]
    classDef llm fill:#eef3ff,stroke:#1d4ed8,stroke-width:2.5px,color:#1d4ed8
    classDef dec fill:#f3f4f7,stroke:#9aa3b5,stroke-width:1.2px
    class B dec
    class C llm
```

**flow_unknown_word_detail** · 사전에서 못 찾은 말 (코드 그대로) ([PNG](flow_unknown_word_detail.png))

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "Noto Sans CJK KR, Noto Sans KR, sans-serif", "fontSize": "15px", "primaryColor": "#ffffff", "primaryBorderColor": "#9aa3b5", "primaryTextColor": "#1f2430", "lineColor": "#7d879c", "edgeLabelBackground": "#ffffff", "clusterBkg": "#f7f8fb", "clusterBorder": "#b8bfcc", "tertiaryColor": "#ffffff"}, "flowchart": {"curve": "linear", "htmlLabels": true, "nodeSpacing": 34, "rankSpacing": 42, "padding": 10, "wrappingWidth": 400}, "layout": "elk", "elk": {"mergeEdges": false, "nodePlacementStrategy": "BRANDES_KOEPF"}, "themeCSS": ".node .label {line-height:1.35} .edgeLabel {font-size:13px; color:#4b5363} .cluster-label {font-weight:700}"}}%%
flowchart TD
    A(["조회에서 못 찾은 용어"]) --> D0("<b>사전 말 그대로이거나<br/>은어·종목 약어와 자모 하나 차이인가</b><br/><small>코드 · 후보가 하나일 때</small>")
    D0 -->|"아니오"| DL["<b>LLM 정규화</b><br/><small>확신 / 짐작 / 모름 / 기본 어휘 중 하나로 적음</small>"]
    DL --> D1("<b>LLM 풀이 안에 사전 말이 있고<br/>원래 글자와 자모가 가까운가</b><br/><small>코드 · 숀졀 = 손해를 보고 팖(손절)</small>")
    D1 -->|"아니오"| D2("<b>LLM이 어떻게 적었나</b>")
    D2 -->|"확신으로 풂"| D3("<b>자모가 가까운<br/>은어·종목 약어가 있는가</b><br/><small>코드</small>")
    D2 -->|"기본 어휘<br/>(고가, 미수)"| DK["오타로 보지 않음"]
    D2 -->|"짐작 · 모름<br/>어느 칸에도 없음"| D4("<b>사전 말과 자모가 가까운가</b><br/><small>코드</small>")
    D4 -->|"가까운 말 없음"| D5("<b>짐작 또는 모름으로 적었나</b>")
    D0 -->|"예"| LK["<b>사전으로 잇기 + 오타 확인 문구</b><br/><small>'익쩔'을 '익절'로 보고 설명드릴게요.<br/>사전 설명으로 답변</small>"]
    D1 -->|"예"| LK
    D4 -->|"표준 용어와 자모 하나 차이<br/>(공메도 → 공매도)"| LK
    D3 -->|"하나 또는 둘"| ASK["<b>9 후보를 보여 주며 되묻기</b><br/><small>혹시 '손절'이나 '본절'을 말씀하신 건가요?</small>"]
    D4 -->|"후보 둘 (쏜절)<br/>자모 둘 차이 (뗙샹)"| ASK
    D5 -->|"예"| ASK0["<b>9 되묻기 (뜻을 말하지 않음)</b><br/><small>'○○'는 확인되지 않은 단어예요.<br/>어떤 뜻으로 들으셨는지 알려주시면<br/>이어서 설명해드릴게요.</small>"]
    D3 -->|"없음"| G["<b>5 답변으로</b><br/><small>확신이면 풀이를 붙여 넘김</small>"]
    DK --> G
    D5 -->|"어느 칸에도 없음"| G
    G --> H("<b>노드 5 LLM이 뜻을 아는가</b>")
    H -->|"앎"| I["<b>사전 밖 안내 첫 문장 (코드가 붙임)</b><br/><small>+ 단정하지 않는 설명 (…로 쓰이는 것으로 보여요)<br/>+ 공식 자료 확인</small>"]
    H -->|"모름 표시"| ASK0
    classDef llm fill:#eef3ff,stroke:#1d4ed8,stroke-width:2.5px,color:#1d4ed8
    classDef dec fill:#f3f4f7,stroke:#9aa3b5,stroke-width:1.2px
    class D0,D1,D3,D4,D5 dec
    class DL,D2,H llm
```

**flow_answer** · 답변 생성 칸 안 ([PNG](flow_answer.png))

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "Noto Sans CJK KR, Noto Sans KR, sans-serif", "fontSize": "15px", "primaryColor": "#ffffff", "primaryBorderColor": "#9aa3b5", "primaryTextColor": "#1f2430", "lineColor": "#7d879c", "edgeLabelBackground": "#ffffff", "clusterBkg": "#f7f8fb", "clusterBorder": "#b8bfcc", "tertiaryColor": "#ffffff"}, "flowchart": {"curve": "linear", "htmlLabels": true, "nodeSpacing": 34, "rankSpacing": 42, "padding": 10, "wrappingWidth": 400}, "layout": "elk", "elk": {"mergeEdges": false, "nodePlacementStrategy": "BRANDES_KOEPF"}, "themeCSS": ".node .label {line-height:1.35} .edgeLabel {font-size:13px; color:#4b5363} .cluster-label {font-weight:700}"}}%%
flowchart TD
    IN(["노드 5로 들어옴<br/><small>용어 설명 · 매매 판단 요청 · 하소연</small>"]) --> V("<b>하소연인가</b><br/><small>의도 분류 결과</small>")
    V -->|"예"| V5["<b>공감 한 문장 (LLM)</b><br/><small>+ 서비스 안내 · 용어 제안 (고정 문장)</small>"]
    V -->|"아니오"| W0["<b>LLM 답변</b><br/><small>응답 정책대로 · 사전 설명을 근거로<br/>매매 판단을 묻는 질문이면 분류와 상관없이 첫 문장에 판단 불가 안내</small>"]
    W0 --> W1("<b>LLM이 뜻을 아는가</b>")
    W1 -->|"모름 표시"| W3["<b>되묻기 문장으로 바꿈 (코드)</b><br/><small>'○○'는 확인되지 않은 단어예요…<br/>매매 판단이면 판단 불가 안내를 앞에</small>"]
    W1 -->|"앎"| W2("<b>문장 조립 (코드)</b><br/><small>답에 무엇이 들어 있나</small>")
    W2 -->|"사전 밖 용어"| X1["<b>사전 밖 안내 첫 문장</b><br/><small>사용자가 쓴 말 그대로 · 매매 판단이면 판단 불가 안내 다음</small>"]
    W2 -->|"오타로 고쳐 읽은 말"| X2["<b>오타 확인 문구</b><br/><small>'익쩔'을 '익절'로 보고 설명드릴게요.</small>"]
    W2 -->|"사용자가 알려 준 뜻"| X3["<b>들은 뜻으로 받음</b><br/><small>맞다고 확인해 주지 않음 · 사전 밖 안내 없음</small>"]
    V5 --> N6
    W3 --> N6
    X1 --> N6
    X2 --> N6
    X3 --> N6
    N6("<b>6 검수 (LLM)</b><br/><small>답과 질문을 함께 봄</small>")
    N6 -->|"위반: 5로 돌아가 다시 쓰기 (2번까지)"| V
    N6 -->|"통과"| F(["끝"])
    N6 -->|"2번 뒤에도 위반"| N7["<b>7 안전 답변</b><br/><small>안내만 빠졌으면 안내를 붙여 내보냄 · 그 밖이면 고정 문구</small>"]
    classDef llm fill:#eef3ff,stroke:#1d4ed8,stroke-width:2.5px,color:#1d4ed8
    classDef dec fill:#f3f4f7,stroke:#9aa3b5,stroke-width:1.2px
    class V,W2 dec
    class W0,W1,N6 llm
```

**flow_after_ask** · 되묻기 · 설명 뒤 다음 턴 ([PNG](flow_after_ask.png))

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "Noto Sans CJK KR, Noto Sans KR, sans-serif", "fontSize": "15px", "primaryColor": "#ffffff", "primaryBorderColor": "#9aa3b5", "primaryTextColor": "#1f2430", "lineColor": "#7d879c", "edgeLabelBackground": "#ffffff", "clusterBkg": "#f7f8fb", "clusterBorder": "#b8bfcc", "tertiaryColor": "#ffffff"}, "flowchart": {"curve": "linear", "htmlLabels": true, "nodeSpacing": 34, "rankSpacing": 42, "padding": 10, "wrappingWidth": 400}, "layout": "elk", "elk": {"mergeEdges": false, "nodePlacementStrategy": "BRANDES_KOEPF"}, "themeCSS": ".node .label {line-height:1.35} .edgeLabel {font-size:13px; color:#4b5363} .cluster-label {font-weight:700}"}}%%
flowchart TD
    S(["앞 턴이 되묻기로 끝남"]) --> T("<b>이번에 사용자가 한 말</b><br/><small>정해 둔 짧은 대답인가 (코드)</small>")
    T -->|"몰라요"| U1["<b>9 확인 못 함 · 끝</b><br/><small>'○○'는 저도 확인된 뜻을 찾지 못했어요.<br/>증권사 안내나 공식 자료에서 확인해 보세요.<br/>다시 묻지 않음</small>"]
    T -->|"다른 뜻이에요<br/>확인할 후보가 없는 '맞아요'"| U2["<b>9 다시 묻기</b><br/><small>어떤 뜻으로 들으셨는지 알려주시면<br/>이어서 설명해드릴게요.</small>"]
    T -->|"'맞아요'<br/>앞 턴이 후보 하나를 물었음"| U3["<b>그 후보로 설명</b><br/><small>빛투 → 빚투(차입 투자)</small>"]
    T -->|"그 밖"| L("<b>LLM 정규화</b><br/><small>뜻을 알려 준 말인가</small>")
    L -->|"뜻을 알려 줌<br/>(장기 투자래)"| U4["<b>들은 뜻으로 받음</b><br/><small>'거북이 매매'를 '장기 투자'라는 뜻으로 들으셨군요.<br/>들으신 뜻이 맞는지는 제가 확인할 수 없어요.<br/>+ 설명 속 사전 용어가 있으면 사전 설명 한 문장<br/>+ 공식 자료 확인</small>"]
    L -->|"다른 질문"| U5["평소 흐름<br/><small>3 의도 분류부터</small>"]
    S2(["앞 턴이 되묻기 없이 끝남<br/><small>용어 설명 · 매매 판단 답 · 범위 밖 안내 등</small>"]) --> T2("<b>이번에 사용자가 한 말</b><br/><small>코드</small>")
    T2 -->|"'맞아요' · '네'뿐"| V1["<b>8 짧은 수긍 고정 문구</b><br/><small>네, 더 궁금한 주식 용어가 있으면 물어봐 주세요.</small>"]
    T2 -->|"앞 턴이 사전 밖 용어 설명이고<br/>'…래'로 뜻을 말함"| UT["<b>사용자 설명으로 적음 (코드)</b><br/><small>LLM을 부르지 않음</small>"]
    UT -->|"3 의도 분류 → 5 답변"| U4
    T2 -->|"그 밖"| U5
    classDef llm fill:#eef3ff,stroke:#1d4ed8,stroke-width:2.5px,color:#1d4ed8
    classDef dec fill:#f3f4f7,stroke:#9aa3b5,stroke-width:1.2px
    class T,T2 dec
    class L llm
```
